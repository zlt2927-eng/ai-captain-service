"""Async Redis client for session and cart persistence - Phase 2 hardened."""

import json
import logging
import uuid
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

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis wrapper for session management with Phase 2 enhancements.
    
    Phase 2 additions:
    - Pipeline support for atomic multi-key operations
    - Locking primitives for session/turn coordination
    - Improved key naming strategy
    - Helper methods for idempotency and recovery workflows
    """
    
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
        logger.info("Redis client connected")
    
    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis client disconnected")
    
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
    
    # Session state methods
    
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
    
    # Cart snapshot methods
    
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
    
    # Audio buffer methods
    
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
    
    # Recovery methods
    
    async def schedule_recovery_marker(self, restaurant_id: str, session_id: str, ttl_seconds: int) -> bool:
        client = await self._ensure_client()
        key = self._build_key(REDIS_RECOVERY_PREFIX, restaurant_id, session_id)
        payload = {
            "disconnected_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "recovery_status": "scheduled",
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
    
    async def mark_recovery_completed(self, restaurant_id: str, session_id: str) -> None:
        """Mark recovery as completed to prevent duplicate webhooks."""
        client = await self._ensure_client()
        key = self._build_key(REDIS_RECOVERY_PREFIX, restaurant_id, session_id)
        marker = await self.get_recovery_marker(restaurant_id, session_id) or {}
        marker["recovery_status"] = "completed"
        marker["completed_at"] = datetime.now(timezone.utc).isoformat()
        await client.setex(key, 60, await self._serialize(marker))  # Keep for 60s after completion
    
    # Session active/inactive methods
    
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
    
    # Message storage methods
    
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
    
    # Phase 2: Locking and pipeline helpers
    
    async def acquire_lock(self, lock_key: str, ttl_seconds: int = 10) -> tuple[bool, str]:
        """Acquire a distributed lock.
        
        Args:
            lock_key: Lock identifier
            ttl_seconds: Lock TTL (auto-releases after timeout)
            
        Returns:
            Tuple of (success, lock_value) - lock_value needed for release
        """
        client = await self._ensure_client()
        lock_value = str(uuid.uuid4())
        result = await client.set(lock_key, lock_value, ex=ttl_seconds, nx=True)
        return (result is True, lock_value)
    
    async def release_lock(self, lock_key: str, lock_value: str) -> bool:
        """Release a distributed lock.
        
        Args:
            lock_key: Lock identifier
            lock_value: Lock value (must match to prevent releasing others' locks)
            
        Returns:
            True if lock released, False otherwise
        """
        client = await self._ensure_client()
        # Use Lua script for atomic check-and-delete
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await client.eval(lua_script, 1, lock_key, lock_value)
        return result == 1
    
    async def pipeline(self):
        """Get Redis pipeline for atomic multi-key operations.
        
        Returns:
            Redis pipeline context manager
        """
        client = await self._ensure_client()
        return client.pipeline()
    
    async def save_session_state_atomic(
        self,
        restaurant_id: str,
        session_id: str,
        state: dict,
        cart: dict,
        ttl_seconds: int,
    ) -> None:
        """Atomically save session state and cart snapshot.
        
        Uses Redis pipeline to ensure both writes succeed or fail together.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            state: Session metadata
            cart: Cart snapshot
            ttl_seconds: TTL for both keys
        """
        async with self.pipeline() as pipe:
            session_key = self._build_key(REDIS_SESSION_PREFIX, restaurant_id, session_id)
            cart_key = self._build_key(REDIS_CART_PREFIX, restaurant_id, session_id)
            
            await pipe.setex(session_key, ttl_seconds, await self._serialize(state))
            await pipe.setex(cart_key, ttl_seconds, await self._serialize(cart))
            await pipe.execute()
        
        logger.debug(
            "Session state saved atomically",
            extra={"restaurant_id": restaurant_id, "session_id": session_id}
        )