"""Abandoned cart recovery service - Phase 2 hardened with deduplication."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient, HTTPClientError
from app.infrastructure.redis_client import RedisClient
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)


class RecoveryServiceError(Exception):
    pass


class RecoveryService:
    """Manage abandoned cart recovery flow with deduplication.
    
    Phase 2 enhancements:
    - Deduplication via recovery_status markers
    - Event ID tracking for each recovery
    - Durable scheduling using Redis TTL
    - Improved payload quality with schema versioning
    - No duplicate webhooks for same abandoned state
    """
    
    def __init__(
        self,
        settings: Settings,
        http_client: HTTPClient,
        redis_client: RedisClient,
        session_service: SessionService,
    ):
        self._settings = settings
        self._http_client = http_client
        self._redis = redis_client
        self._session_service = session_service
        self._scheduled_tasks: dict[str, asyncio.Task] = {}
    
    def _task_key(self, restaurant_id: str, session_id: str) -> str:
        return f"{restaurant_id}:{session_id}"
    
    async def schedule_recovery(self, restaurant_id: str, session_id: str) -> None:
        """Schedule abandoned cart recovery with deduplication.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
        """
        task_key = self._task_key(restaurant_id, session_id)
        
        # Check if recovery already scheduled or completed
        existing_marker = await self._redis.get_recovery_marker(restaurant_id, session_id)
        if existing_marker:
            status = existing_marker.get("recovery_status")
            if status in ("scheduled", "completed"):
                logger.info(
                    "Recovery already %s",
                    status,
                    extra={"restaurant_id": restaurant_id, "session_id": session_id}
                )
                return
        
        # Schedule recovery marker in Redis
        created = await self._redis.schedule_recovery_marker(
            restaurant_id, session_id, self._settings.RECOVERY_DELAY_SECONDS
        )
        if not created:
            logger.info("Recovery marker already exists", extra={"restaurant_id": restaurant_id, "session_id": session_id})
            return
        
        # Check if task already running
        task = self._scheduled_tasks.get(task_key)
        if task is not None and not task.done():
            logger.info(
                "Recovery task already running",
                extra={"restaurant_id": restaurant_id, "session_id": session_id}
            )
            return
        
        logger.info(
            "Scheduled recovery task",
            extra={"restaurant_id": restaurant_id, "session_id": session_id}
        )
        
        # Create background task
        self._scheduled_tasks[task_key] = asyncio.create_task(
            self._execute_recovery_if_abandoned(restaurant_id, session_id)
        )
    
    async def _execute_recovery_if_abandoned(self, restaurant_id: str, session_id: str) -> None:
        """Execute recovery if session is still abandoned after delay.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
        """
        task_key = self._task_key(restaurant_id, session_id)
        
        try:
            # Wait for recovery delay
            await asyncio.sleep(self._settings.RECOVERY_DELAY_SECONDS)
            
            # Check if recovery was cancelled
            has_marker = await self._redis.check_recovery_marker(restaurant_id, session_id)
            if not has_marker:
                logger.info(
                    "Recovery marker cleared before execution",
                    extra={"restaurant_id": restaurant_id, "session_id": session_id}
                )
                return
            
            # Check if session reactivated
            if await self._session_service.is_session_active(restaurant_id, session_id):
                logger.info(
                    "Session reactivated, aborting recovery",
                    extra={"restaurant_id": restaurant_id, "session_id": session_id}
                )
                await self._redis.cancel_recovery_marker(restaurant_id, session_id)
                return
            
            # Check if already completed (deduplication)
            marker = await self._redis.get_recovery_marker(restaurant_id, session_id) or {}
            if marker.get("recovery_status") == "completed":
                logger.info(
                    "Recovery already completed, skipping",
                    extra={"restaurant_id": restaurant_id, "session_id": session_id}
                )
                return
            
            # Build recovery payload
            payload = await self._session_service.build_recovery_payload(restaurant_id, session_id)
            payload["recovery_event_id"] = str(uuid.uuid4())
            payload["schema_version"] = "1.0"
            
            # Send recovery webhook
            await self._send_recovery_webhook(payload)
            
            # Mark as completed to prevent duplicate webhooks
            await self._redis.mark_recovery_completed(restaurant_id, session_id)
            
            logger.info(
                "Recovery webhook delivered",
                extra={
                    "restaurant_id": restaurant_id,
                    "session_id": session_id,
                    "recovery_event_id": payload["recovery_event_id"]
                }
            )
            
        except asyncio.CancelledError:
            logger.info(
                "Recovery task canceled",
                extra={"restaurant_id": restaurant_id, "session_id": session_id}
            )
        except Exception as exc:
            logger.error(
                "Recovery execution failed",
                exc_info=True,
                extra={
                    "restaurant_id": restaurant_id,
                    "session_id": session_id,
                    "error": str(exc),
                }
            )
        finally:
            self._scheduled_tasks.pop(task_key, None)
    
    async def _send_recovery_webhook(self, payload: Dict[str, Any]) -> None:
        """Send abandoned cart recovery webhook to Laravel backend.
        
        Args:
            payload: Recovery payload with session and cart data
            
        Raises:
            RecoveryServiceError: If webhook delivery fails
        """
        try:
            await self._http_client.post_json(
                self._settings.abandoned_cart_url,
                payload,
                service_name="laravel_backend",
                endpoint_name="abandoned_cart_webhook",
                correlation_id=payload.get("recovery_event_id"),
            )
        except HTTPClientError as exc:
            logger.error("Failed to send abandoned cart webhook", exc_info=True)
            raise RecoveryServiceError(str(exc)) from exc
    
    async def cancel_recovery(self, restaurant_id: str, session_id: str) -> None:
        """Cancel pending recovery for a session.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
        """
        task_key = self._task_key(restaurant_id, session_id)
        
        # Cancel in-memory task if running
        task = self._scheduled_tasks.get(task_key)
        if task and not task.done():
            task.cancel()
            logger.info(
                "Canceled in-process recovery task",
                extra={"restaurant_id": restaurant_id, "session_id": session_id}
            )
        
        # Cancel Redis marker
        await self._redis.cancel_recovery_marker(restaurant_id, session_id)
        self._scheduled_tasks.pop(task_key, None)
        
        logger.debug(
            "Recovery cancelled",
            extra={"restaurant_id": restaurant_id, "session_id": session_id}
        )
    
    async def get_recovery_status(self, restaurant_id: str, session_id: str) -> Dict[str, Any]:
        """Get current recovery status for a session.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            Recovery status dictionary
        """
        marker = await self._redis.get_recovery_marker(restaurant_id, session_id)
        
        if not marker:
            return {"status": "none"}
        
        return {
            "status": marker.get("recovery_status", "unknown"),
            "scheduled_at": marker.get("scheduled_at"),
            "disconnected_at": marker.get("disconnected_at"),
            "completed_at": marker.get("completed_at"),
        }