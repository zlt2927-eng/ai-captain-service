"""WebSocket rate limiting service - Phase 3 production hardening."""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.core.config import Settings
from app.core.constants import WS_CLOSE_RATE_LIMIT
from app.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


@dataclass
class RateLimitResult:
    """Result of rate limit check."""
    
    allowed: bool
    remaining: int
    reset_time: float
    reason: Optional[str] = None


class RateLimiter:
    """Multi-tier rate limiter for WebSocket connections.
    
    Implements:
    - Per-IP rate limiting
    - Per-Session rate limiting
    - Per-WebSocket message rate limiting
    
    All limits are configurable through Settings.
    """
    
    def __init__(self, redis_client: RedisClient, settings: Settings):
        self._redis = redis_client
        self._settings = settings
    
    async def check_ip_limit(self, ip_address: str) -> RateLimitResult:
        """Check if IP address is within rate limit.
        
        Args:
            ip_address: Client IP address
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        if not self._settings.RATE_LIMIT_ENABLED:
            return RateLimitResult(allowed=True, remaining=0, reset_time=0)
        
        key = f"{self._settings.RATE_LIMIT_REDIS_PREFIX}:ip:{ip_address}"
        return await self._check_limit(
            key,
            self._settings.RATE_LIMIT_PER_IP_WINDOW_SECONDS,
            self._settings.RATE_LIMIT_PER_IP_MAX_REQUESTS,
            "IP rate limit exceeded"
        )
    
    async def check_session_limit(
        self,
        restaurant_id: str,
        session_id: str
    ) -> RateLimitResult:
        """Check if session is within rate limit.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        if not self._settings.RATE_LIMIT_ENABLED:
            return RateLimitResult(allowed=True, remaining=0, reset_time=0)
        
        key = f"{self._settings.RATE_LIMIT_REDIS_PREFIX}:session:{restaurant_id}:{session_id}"
        return await self._check_limit(
            key,
            self._settings.RATE_LIMIT_PER_SESSION_WINDOW_SECONDS,
            self._settings.RATE_LIMIT_PER_SESSION_MAX_REQUESTS,
            "Session rate limit exceeded"
        )
    
    async def check_websocket_limit(
        self,
        connection_id: str
    ) -> RateLimitResult:
        """Check if WebSocket connection is within message rate limit.
        
        Args:
            connection_id: Unique connection identifier
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        if not self._settings.RATE_LIMIT_ENABLED:
            return RateLimitResult(allowed=True, remaining=0, reset_time=0)
        
        key = f"{self._settings.RATE_LIMIT_REDIS_PREFIX}:ws:{connection_id}"
        return await self._check_limit(
            key,
            self._settings.RATE_LIMIT_PER_WEBSOCKET_WINDOW_SECONDS,
            self._settings.RATE_LIMIT_PER_WEBSOCKET_MAX_MESSAGES,
            "WebSocket message rate limit exceeded"
        )
    
    async def _check_limit(
        self,
        key: str,
        window_seconds: int,
        max_requests: int,
        reason: str
    ) -> RateLimitResult:
        """Generic rate limit check using sliding window.
        
        Args:
            key: Redis key for this rate limit
            window_seconds: Time window in seconds
            max_requests: Maximum requests allowed in window
            reason: Reason string for rejection
            
        Returns:
            RateLimitResult indicating if request is allowed
        """
        now = time.time()
        window_start = now - window_seconds
        
        # Use Redis sorted set for sliding window
        # Remove old entries outside the window
        await self._redis._client.zremrangebyscore(key, 0, window_start)
        
        # Count current requests in window
        current_count = await self._redis._client.zcard(key)
        
        if current_count >= max_requests:
            # Get the oldest entry to calculate reset time
            oldest = await self._redis._client.zrange(key, 0, 0, withscores=True)
            if oldest:
                reset_time = oldest[0][1] + window_seconds
            else:
                reset_time = now + window_seconds
            
            logger.warning(
                "Rate limit exceeded",
                extra={
                    "key": key,
                    "current_count": current_count,
                    "max_requests": max_requests,
                    "reason": reason
                }
            )
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_time=reset_time,
                reason=reason
            )
        
        # Add current request
        await self._redis._client.zadd(key, {str(now): now})
        await self._redis._client.expire(key, window_seconds)
        
        remaining = max_requests - current_count - 1
        reset_time = now + window_seconds
        
        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_time=reset_time
        )
    
    async def reset_ip_limit(self, ip_address: str) -> None:
        """Reset rate limit for IP address (admin function).
        
        Args:
            ip_address: Client IP address
        """
        key = f"{self._settings.RATE_LIMIT_REDIS_PREFIX}:ip:{ip_address}"
        await self._redis._client.delete(key)
    
    async def reset_session_limit(
        self,
        restaurant_id: str,
        session_id: str
    ) -> None:
        """Reset rate limit for session (admin function).
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
        """
        key = f"{self._settings.RATE_LIMIT_REDIS_PREFIX}:session:{restaurant_id}:{session_id}"
        await self._redis._client.delete(key)
    
    async def reset_websocket_limit(self, connection_id: str) -> None:
        """Reset rate limit for WebSocket connection (admin function).
        
        Args:
            connection_id: Connection identifier
        """
        key = f"{self._settings.RATE_LIMIT_REDIS_PREFIX}:ws:{connection_id}"
        await self._redis._client.delete(key)