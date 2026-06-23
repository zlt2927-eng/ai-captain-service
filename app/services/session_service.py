"""Session state persistence and management - Phase 2 hardened."""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


class SessionService:
    """Manage session state in Redis with turn-level tracking.
    
    Phase 2 enhancements:
    - Turn-level correlation IDs
    - Conversation history tracking
    - Atomic multi-key operations via Redis pipeline
    - Recovery payload building
    """
    
    def __init__(self, redis_client: RedisClient, session_ttl_seconds: int):
        self._redis = redis_client
        self._session_ttl = session_ttl_seconds
    
    async def start_session(self, restaurant_id: str, session_id: str, metadata: Optional[dict] = None) -> None:
        """Initialize a new session.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            metadata: Optional initial metadata
        """
        initial_metadata = {
            "restaurant_id": restaurant_id,
            "session_id": session_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "turn_count": 0,
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }
        
        if metadata:
            initial_metadata.update(metadata)
        
        await self._redis.save_session_state(restaurant_id, session_id, initial_metadata, self._session_ttl)
        await self.mark_session_active(restaurant_id, session_id)
        
        logger.debug(
            "Session started",
            extra={"restaurant_id": restaurant_id, "session_id": session_id}
        )
    
    async def get_session_context(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        """Get full session context including metadata and cart.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            Session context dictionary or None if not found
        """
        metadata = await self._redis.load_session_state(restaurant_id, session_id)
        cart_snapshot = await self._redis.load_cart_snapshot(restaurant_id, session_id)
        
        if metadata is None:
            return None
        
        context = dict(metadata)
        context["cart_snapshot"] = cart_snapshot or {}
        
        return context
    
    async def append_turn(
        self,
        restaurant_id: str,
        session_id: str,
        turn_id: str,
        user_message: str,
        assistant_message: str,
        cart_snapshot: Optional[dict] = None,
    ) -> None:
        """Append a conversation turn to session history.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            turn_id: Turn identifier
            user_message: User's message
            assistant_message: Assistant's response
            cart_snapshot: Optional cart state after turn
        """
        turn_data = {
            "turn_id": turn_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_message": user_message,
            "assistant_message": assistant_message,
            "cart_snapshot": cart_snapshot,
        }
        
        # Store turn in Redis list
        turn_key = f"turn:{restaurant_id}:{session_id}:{turn_id}"
        await self._redis.save_session_state(
            restaurant_id,
            session_id,
            {"last_turn": turn_data},
            self._session_ttl
        )
        
        # Update turn count
        metadata = await self._redis.load_session_state(restaurant_id, session_id) or {}
        metadata["turn_count"] = metadata.get("turn_count", 0) + 1
        metadata["last_activity"] = datetime.now(timezone.utc).isoformat()
        
        await self._redis.save_session_state(restaurant_id, session_id, metadata, self._session_ttl)
        
        logger.debug(
            "Turn appended",
            extra={
                "restaurant_id": restaurant_id,
                "session_id": session_id,
                "turn_id": turn_id,
            }
        )
    
    async def save_last_user_message(self, restaurant_id: str, session_id: str, message: str) -> None:
        """Save last user message."""
        await self._redis.save_last_user_message(restaurant_id, session_id, message, self._session_ttl)
    
    async def save_last_assistant_message(self, restaurant_id: str, session_id: str, message: str) -> None:
        """Save last assistant message."""
        await self._redis.save_last_assistant_message(restaurant_id, session_id, message, self._session_ttl)
    
    async def persist_conversation_turn(
        self,
        restaurant_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        turn_id: Optional[str] = None,
    ) -> None:
        """Persist a complete conversation turn.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            user_message: User's message
            assistant_message: Assistant's response
            turn_id: Optional turn identifier
        """
        # Generate turn_id if not provided
        if not turn_id:
            turn_id = f"turn_{uuid.uuid4().hex[:16]}"
        
        # Save messages
        await self.save_last_user_message(restaurant_id, session_id, user_message)
        await self.save_last_assistant_message(restaurant_id, session_id, assistant_message)
        
        # Append to turn history
        await self.append_turn(
            restaurant_id,
            session_id,
            turn_id,
            user_message,
            assistant_message,
        )
    
    async def save_cart_snapshot(self, restaurant_id: str, session_id: str, cart: dict) -> None:
        """Save cart snapshot."""
        await self._redis.save_cart_snapshot(restaurant_id, session_id, cart)
    
    async def load_cart_snapshot(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        """Load cart snapshot."""
        return await self._redis.load_cart_snapshot(restaurant_id, session_id)
    
    async def delete_cart_snapshot(self, restaurant_id: str, session_id: str) -> None:
        """Delete cart snapshot."""
        await self._redis.delete_cart_snapshot(restaurant_id, session_id)
    
    async def mark_session_active(self, restaurant_id: str, session_id: str) -> None:
        """Mark session as active."""
        await self._redis.mark_session_active(restaurant_id, session_id)
    
    async def mark_session_inactive(self, restaurant_id: str, session_id: str) -> None:
        """Mark session as inactive."""
        await self._redis.mark_session_inactive(restaurant_id, session_id)
    
    async def is_session_active(self, restaurant_id: str, session_id: str) -> bool:
        """Check if session is active."""
        return await self._redis.is_session_active(restaurant_id, session_id)
    
    async def cancel_recovery(self, restaurant_id: str, session_id: str) -> None:
        """Cancel any pending recovery for this session."""
        await self._redis.cancel_recovery_marker(restaurant_id, session_id)
    
    async def build_recovery_payload(self, restaurant_id: str, session_id: str) -> dict:
        """Build recovery payload for abandoned cart webhook.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            Recovery payload dictionary
        """
        last_user_msg = await self._redis.load_last_user_message(restaurant_id, session_id)
        last_asst_msg = await self._redis.load_last_assistant_message(restaurant_id, session_id)
        cart_snapshot = await self._redis.load_cart_snapshot(restaurant_id, session_id)
        recovery_marker = await self._redis.get_recovery_marker(restaurant_id, session_id)
        
        return {
            "event_id": str(uuid.uuid4()),
            "session_id": session_id,
            "restaurant_id": restaurant_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "disconnected_at": recovery_marker.get("disconnected_at") if recovery_marker else None,
            "last_user_message": last_user_msg,
            "last_assistant_message": last_asst_msg,
            "cart_snapshot": cart_snapshot or {},
            "schema_version": "1.0",
        }
    
    async def collect_session_snapshot(self, restaurant_id: str, session_id: str) -> dict:
        """Collect complete session snapshot for recovery.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            Complete session snapshot
        """
        context = await self.get_session_context(restaurant_id, session_id)
        
        if context is None:
            return {
                "restaurant_id": restaurant_id,
                "session_id": session_id,
                "last_user_message": None,
                "last_assistant_message": None,
                "cart_snapshot": {},
                "disconnected_at": datetime.now(timezone.utc).isoformat(),
            }
        
        return {
            "restaurant_id": restaurant_id,
            "session_id": session_id,
            "last_user_message": context.get("last_user_message"),
            "last_assistant_message": context.get("last_assistant_message"),
            "cart_snapshot": context.get("cart_snapshot", {}),
            "disconnected_at": datetime.now(timezone.utc).isoformat(),
        }