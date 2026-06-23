"""Session state persistence and management."""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


class SessionService:
    """Manage session state in Redis."""

    def __init__(self, redis_client: RedisClient, session_ttl_seconds: int):
        self.redis = redis_client
        self.session_ttl = session_ttl_seconds

    async def save_session_metadata(self, restaurant_id: str, session_id: str, metadata: dict) -> None:
        await self.redis.save_session_state(restaurant_id, session_id, metadata, self.session_ttl)
        logger.debug("Session metadata saved for %s:%s", restaurant_id, session_id)

    async def load_session_metadata(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        return await self.redis.load_session_state(restaurant_id, session_id)

    async def delete_session_metadata(self, restaurant_id: str, session_id: str) -> None:
        await self.redis.delete_session_state(restaurant_id, session_id)

    async def save_last_user_message(self, restaurant_id: str, session_id: str, message: str) -> None:
        await self.redis.save_last_user_message(restaurant_id, session_id, message, self.session_ttl)

    async def load_last_user_message(self, restaurant_id: str, session_id: str) -> Optional[str]:
        return await self.redis.load_last_user_message(restaurant_id, session_id)

    async def save_last_assistant_message(self, restaurant_id: str, session_id: str, message: str) -> None:
        await self.redis.save_last_assistant_message(restaurant_id, session_id, message, self.session_ttl)

    async def load_last_assistant_message(self, restaurant_id: str, session_id: str) -> Optional[str]:
        return await self.redis.load_last_assistant_message(restaurant_id, session_id)

    async def persist_conversation_turn(self, restaurant_id: str, session_id: str, user_message: str, assistant_message: str) -> None:
        await self.save_last_user_message(restaurant_id, session_id, user_message)
        await self.save_last_assistant_message(restaurant_id, session_id, assistant_message)
        await self.save_session_metadata(
            restaurant_id,
            session_id,
            {
                "last_user_message": user_message,
                "last_assistant_message": assistant_message,
            },
        )

    async def save_cart_snapshot(self, restaurant_id: str, session_id: str, cart: dict) -> None:
        await self.redis.save_cart_snapshot(restaurant_id, session_id, cart)
        logger.debug("Cart snapshot saved for %s:%s", restaurant_id, session_id)

    async def load_cart_snapshot(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        return await self.redis.load_cart_snapshot(restaurant_id, session_id)

    async def delete_cart_snapshot(self, restaurant_id: str, session_id: str) -> None:
        await self.redis.delete_cart_snapshot(restaurant_id, session_id)

    async def mark_session_active(self, restaurant_id: str, session_id: str) -> None:
        await self.redis.mark_session_active(restaurant_id, session_id)

    async def mark_session_inactive(self, restaurant_id: str, session_id: str) -> None:
        await self.redis.mark_session_inactive(restaurant_id, session_id)

    async def is_session_active(self, restaurant_id: str, session_id: str) -> bool:
        return await self.redis.is_session_active(restaurant_id, session_id)

    async def cancel_recovery(self, restaurant_id: str, session_id: str) -> None:
        await self.redis.cancel_recovery_marker(restaurant_id, session_id)

    async def collect_session_snapshot(self, restaurant_id: str, session_id: str) -> dict:
        last_user_msg = await self.load_last_user_message(restaurant_id, session_id)
        last_asst_msg = await self.load_last_assistant_message(restaurant_id, session_id)
        cart_snapshot = await self.load_cart_snapshot(restaurant_id, session_id)

        return {
            "restaurant_id": restaurant_id,
            "session_id": session_id,
            "last_user_message": last_user_msg,
            "last_assistant_message": last_asst_msg,
            "cart_snapshot": cart_snapshot or {},
            "disconnected_at": datetime.now(timezone.utc).isoformat(),
        }
