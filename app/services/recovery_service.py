"""Abandoned cart recovery service."""

import asyncio
import logging
from typing import Any, Dict

from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient, HTTPClientError
from app.infrastructure.redis_client import RedisClient
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)


class RecoveryServiceError(Exception):
    pass


class RecoveryService:
    """Manage abandoned cart recovery flow."""

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
        created = await self._redis.schedule_recovery_marker(
            restaurant_id, session_id, self._settings.RECOVERY_DELAY_SECONDS
        )
        if not created:
            logger.info("Recovery already scheduled for %s %s", restaurant_id, session_id)
            return

        task_key = self._task_key(restaurant_id, session_id)
        task = self._scheduled_tasks.get(task_key)
        if task is not None and not task.done():
            logger.info("Recovery task already running for %s %s", restaurant_id, session_id)
            return

        logger.info("Scheduled recovery task for %s %s", restaurant_id, session_id)
        self._scheduled_tasks[task_key] = asyncio.create_task(
            self._execute_recovery_if_abandoned(restaurant_id, session_id)
        )

    async def _execute_recovery_if_abandoned(self, restaurant_id: str, session_id: str) -> None:
        task_key = self._task_key(restaurant_id, session_id)
        try:
            await asyncio.sleep(self._settings.RECOVERY_DELAY_SECONDS)

            has_marker = await self._redis.check_recovery_marker(restaurant_id, session_id)
            if not has_marker:
                logger.info("Recovery marker cleared before execution for %s %s", restaurant_id, session_id)
                return

            if await self._session_service.is_session_active(restaurant_id, session_id):
                logger.info("Session reactivated, aborting recovery for %s %s", restaurant_id, session_id)
                await self._redis.cancel_recovery_marker(restaurant_id, session_id)
                return

            marker = await self._redis.get_recovery_marker(restaurant_id, session_id) or {}
            snapshot = await self._session_service.collect_session_snapshot(restaurant_id, session_id)
            snapshot["disconnected_at"] = marker.get("disconnected_at", snapshot.get("disconnected_at"))

            await self._send_recovery_webhook(snapshot)
            await self._redis.cancel_recovery_marker(restaurant_id, session_id)
            logger.info("Recovery webhook delivered", restaurant_id=restaurant_id, session_id=session_id)

        except asyncio.CancelledError:
            logger.info("Recovery task canceled", restaurant_id=restaurant_id, session_id=session_id)
        except Exception as exc:
            logger.error(
                "Recovery execution failed",
                exc_info=True,
                restaurant_id=restaurant_id,
                session_id=session_id,
                error=str(exc),
            )
        finally:
            self._scheduled_tasks.pop(task_key, None)

    async def _send_recovery_webhook(self, payload: Dict[str, Any]) -> None:
        try:
            await self._http_client.post_json(self._settings.abandoned_cart_url, payload)
        except HTTPClientError as exc:
            logger.error("Failed to send abandoned cart webhook: %s", str(exc), exc_info=True)
            raise RecoveryServiceError(str(exc)) from exc

    async def cancel_recovery(self, restaurant_id: str, session_id: str) -> None:
        task_key = self._task_key(restaurant_id, session_id)
        task = self._scheduled_tasks.get(task_key)
        if task and not task.done():
            task.cancel()
            logger.info("Canceled in-process recovery task for %s %s", restaurant_id, session_id)
        await self._redis.cancel_recovery_marker(restaurant_id, session_id)
        self._scheduled_tasks.pop(task_key, None)

    async def shutdown(self) -> None:
        """Cancel all scheduled recovery tasks. Should be called during application shutdown."""
        keys = list(self._scheduled_tasks.keys())
        for key in keys:
            task = self._scheduled_tasks.get(key)
            if task and not task.done():
                task.cancel()
                logger.info("Canceled recovery task during shutdown: %s", key)
        # Optionally await tasks to finish cancellation
        for key in keys:
            task = self._scheduled_tasks.pop(key, None)
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("Error while awaiting recovery task cancellation")
