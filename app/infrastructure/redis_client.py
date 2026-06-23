"""Async Redis client for session and cart persistence."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as redis

from app.core.config import Settings
from app.core.constants import (
    REDIS_AUDIO_PREFIX,
    REDIS_CART_PREFIX,
    REDIS_RECOVERY_PREFIX,
    REDIS_SESSION_PREFIX,
)


class RedisClient:
    """Async Redis wrapper for session management."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: Optional[redis.Redis] = None

    async def _ensure_client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis client has not been initialized")
        return self._client

    async def connect(self) -> None:
        self._client = redis.from_url(self._settings.REDIS_URL, decode_responses=True)
        await self._client.ping()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def is_connected(self) -> bool:
        if not self._client:
            return False
        try:
            return await self._client.ping() is True
        except Exception:
            return False

    def _build_key(self, prefix: str, restaurant_id: str, session_id: str, suffix: Optional[str] = None) -> str:
        if suffix:
            return f"{prefix}:{restaurant_id}:{session_id}:{suffix}"
        return f"{prefix}:{restaurant_id}:{session_id}"

    async def _serialize(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    async def _deserialize(self, raw: Optional[str]) -> Optional[Any]:
        if raw is None:
            return None
        return json.loads(raw)

    async def save_session_state(self, restaurant_id: str, session_id: str, state: dict, ttl_seconds: int) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id)
        await client.setex(key, ttl_seconds, await self._serialize(state))

    async def load_session_state(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id)
        raw = await client.get(key)
        return await self._deserialize(raw)

    async def delete_session_state(self, restaurant_id: str, session_id: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id)
        await client.delete(key)

    async def save_cart_snapshot(self, restaurant_id: str, session_id: str, cart: dict) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_CART_PREFIX, restaurant_id, session_id)
        await client.setex(key, self._settings.SESSION_TTL_SECONDS, await self._serialize(cart))

    async def load_cart_snapshot(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        client = await self._ensure_client()
        key = self._build_key(REDIS_CART_PREFIX, restaurant_id, session_id)
        raw = await client.get(key)
        return await self._deserialize(raw)

    async def delete_cart_snapshot(self, restaurant_id: str, session_id: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_CART_PREFIX, restaurant_id, session_id)
        await client.delete(key)

    async def append_audio_buffer_metadata(self, restaurant_id: str, session_id: str, metadata: dict) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_AUDIO_PREFIX, restaurant_id, session_id)
        await client.rpush(key, await self._serialize(metadata))
        await client.expire(key, self._settings.AUDIO_BUFFER_TTL_SECONDS)

    async def get_audio_buffer_metadata(self, restaurant_id: str, session_id: str) -> list[dict]:
        client = await self._ensure_client()
        key = self._build_key(REDIS_AUDIO_PREFIX, restaurant_id, session_id)
        entries = await client.lrange(key, 0, -1)
        return [json.loads(entry) for entry in entries if entry]

    async def schedule_recovery_marker(self, restaurant_id: str, session_id: str, ttl_seconds: int) -> bool:
        client = await self._ensure_client()
        key = self._build_key(REDIS_RECOVERY_PREFIX, restaurant_id, session_id)
        payload = {
            "disconnected_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        }
        return await client.set(key, await self._serialize(payload), ex=ttl_seconds, nx=True) is True

    async def cancel_recovery_marker(self, restaurant_id: str, session_id: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_RECOVERY_PREFIX, restaurant_id, session_id)
        await client.delete(key)

    async def check_recovery_marker(self, restaurant_id: str, session_id: str) -> bool:
        client = await self._ensure_client()
        key = self._build_key(REDIS_RECOVERY_PREFIX, restaurant_id, session_id)
        return await client.exists(key) == 1

    async def get_recovery_marker(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        client = await self._ensure_client()
        key = self._build_key(REDIS_RECOVERY_PREFIX, restaurant_id, session_id)
        raw = await client.get(key)
        return await self._deserialize(raw)

    async def mark_session_active(self, restaurant_id: str, session_id: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "active")
        await client.setex(key, self._settings.SESSION_TTL_SECONDS, "1")

    async def mark_session_inactive(self, restaurant_id: str, session_id: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "active")
        await client.delete(key)

    async def is_session_active(self, restaurant_id: str, session_id: str) -> bool:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "active")
        return await client.exists(key) == 1

    async def save_last_user_message(self, restaurant_id: str, session_id: str, message: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "last_user_msg")
        await client.setex(key, self._settings.SESSION_TTL_SECONDS, message)

    async def load_last_user_message(self, restaurant_id: str, session_id: str) -> Optional[str]:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "last_user_msg")
        value = await client.get(key)
        return value if isinstance(value, str) else None

    async def save_last_assistant_message(self, restaurant_id: str, session_id: str, message: str) -> None:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "last_asst_msg")
        await client.setex(key, self._settings.SESSION_TTL_SECONDS, message)

    async def load_last_assistant_message(self, restaurant_id: str, session_id: str) -> Optional[str]:
        client = await self._ensure_client()
        key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id, "last_asst_msg")
        value = await client.get(key)
        return value if isinstance(value, str) else None
