"""Unit tests for WebSocket rate limiting - Phase 3."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings
from app.websocket.rate_limiter import RateLimiter, RateLimitResult


class TestRateLimiter:
    """Test rate limiter functionality."""

    @pytest.fixture
    def mock_redis_client(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        # Mock the _client attribute that RateLimiter accesses
        mock._client = MagicMock()
        mock._client.zremrangebyscore = AsyncMock(return_value=0)
        mock._client.zcard = AsyncMock(return_value=0)
        mock._client.zadd = AsyncMock(return_value=1)
        mock._client.expire = AsyncMock(return_value=1)
        mock._client.zrange = AsyncMock(return_value=[])
        mock._client.delete = AsyncMock(return_value=1)
        return mock

    @pytest.fixture
    def test_settings(self):
        """Provide test settings with rate limiting enabled."""
        settings = Settings()
        settings.RATE_LIMIT_ENABLED = True
        settings.RATE_LIMIT_PER_IP_WINDOW_SECONDS = 60
        settings.RATE_LIMIT_PER_IP_MAX_REQUESTS = 100
        settings.RATE_LIMIT_PER_SESSION_WINDOW_SECONDS = 60
        settings.RATE_LIMIT_PER_SESSION_MAX_REQUESTS = 50
        settings.RATE_LIMIT_PER_WEBSOCKET_WINDOW_SECONDS = 60
        settings.RATE_LIMIT_PER_WEBSOCKET_MAX_MESSAGES = 200
        settings.RATE_LIMIT_REDIS_PREFIX = "ratelimit"
        return settings

    @pytest.fixture
    def rate_limiter(self, test_settings, mock_redis_client):
        """Provide RateLimiter instance."""
        return RateLimiter(mock_redis_client, test_settings)

    @pytest.mark.asyncio
    async def test_check_ip_limit_allowed(self, test_settings, mock_redis_client):
        """Test IP rate limit allows request when under limit."""
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        mock_redis_client._client.zcard.return_value = 50  # Under limit of 100
        
        result = await rate_limiter.check_ip_limit("192.168.1.1")
        
        assert result.allowed is True
        assert result.remaining == 49
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_check_ip_limit_exceeded(self, test_settings, mock_redis_client):
        """Test IP rate limit rejects request when over limit."""
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        mock_redis_client._client.zcard.return_value = 100  # At limit
        
        result = await rate_limiter.check_ip_limit("192.168.1.1")
        
        assert result.allowed is False
        assert result.remaining == 0
        assert "IP rate limit exceeded" in result.reason

    @pytest.mark.asyncio
    async def test_check_session_limit_allowed(self, test_settings, mock_redis_client):
        """Test session rate limit allows request when under limit."""
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        mock_redis_client._client.zcard.return_value = 25  # Under limit of 50
        
        result = await rate_limiter.check_session_limit("rest_1", "sess_123")
        
        assert result.allowed is True
        assert result.remaining == 24
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_check_session_limit_exceeded(self, test_settings, mock_redis_client):
        """Test session rate limit rejects request when over limit."""
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        mock_redis_client._client.zcard.return_value = 50  # At limit
        
        result = await rate_limiter.check_session_limit("rest_1", "sess_123")
        
        assert result.allowed is False
        assert result.remaining == 0
        assert "Session rate limit exceeded" in result.reason

    @pytest.mark.asyncio
    async def test_check_websocket_limit_allowed(self, test_settings, mock_redis_client):
        """Test WebSocket message rate limit allows request when under limit."""
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        mock_redis_client._client.zcard.return_value = 150  # Under limit of 200
        
        result = await rate_limiter.check_websocket_limit("conn_abc123")
        
        assert result.allowed is True
        assert result.remaining == 49
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_check_websocket_limit_exceeded(self, test_settings, mock_redis_client):
        """Test WebSocket message rate limit rejects request when over limit."""
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        mock_redis_client._client.zcard.return_value = 200  # At limit
        
        result = await rate_limiter.check_websocket_limit("conn_abc123")
        
        assert result.allowed is False
        assert result.remaining == 0
        assert "WebSocket message rate limit exceeded" in result.reason

    @pytest.mark.asyncio
    async def test_rate_limit_disabled(self, test_settings, mock_redis_client):
        """Test rate limiting can be disabled."""
        test_settings.RATE_LIMIT_ENABLED = False
        rate_limiter = RateLimiter(mock_redis_client, test_settings)
        
        result = await rate_limiter.check_ip_limit("192.168.1.1")
        
        assert result.allowed is True
        assert result.remaining == 0
        assert result.reset_time == 0
        # Redis should not be called when disabled
        mock_redis_client.zcard.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_ip_limit(self, rate_limiter, mock_redis_client):
        """Test resetting IP rate limit."""
        await rate_limiter.reset_ip_limit("192.168.1.1")
        
        mock_redis_client._client.delete.assert_called_once()
        call_args = mock_redis_client._client.delete.call_args[0][0]
        assert "ratelimit:ip:192.168.1.1" in call_args

    @pytest.mark.asyncio
    async def test_reset_session_limit(self, rate_limiter, mock_redis_client):
        """Test resetting session rate limit."""
        await rate_limiter.reset_session_limit("rest_1", "sess_123")
        
        mock_redis_client._client.delete.assert_called_once()
        call_args = mock_redis_client._client.delete.call_args[0][0]
        assert "ratelimit:session:rest_1:sess_123" in call_args

    @pytest.mark.asyncio
    async def test_reset_websocket_limit(self, rate_limiter, mock_redis_client):
        """Test resetting WebSocket rate limit."""
        await rate_limiter.reset_websocket_limit("conn_abc123")
        
        mock_redis_client._client.delete.assert_called_once()
        call_args = mock_redis_client._client.delete.call_args[0][0]
        assert "ratelimit:ws:conn_abc123" in call_args

    @pytest.mark.asyncio
    async def test_rate_limit_key_format(self, rate_limiter, mock_redis_client):
        """Test rate limit keys are properly formatted."""
        mock_redis_client._client.zcard.return_value = 0
        
        await rate_limiter.check_ip_limit("192.168.1.1")
        await rate_limiter.check_session_limit("rest_1", "sess_123")
        await rate_limiter.check_websocket_limit("conn_abc123")
        
        # Verify key formats
        calls = mock_redis_client._client.zremrangebyscore.call_args_list
        assert len(calls) == 3
        
        # IP key
        assert "ratelimit:ip:192.168.1.1" in calls[0][0][0]
        # Session key
        assert "ratelimit:session:rest_1:sess_123" in calls[1][0][0]
        # WebSocket key
        assert "ratelimit:ws:conn_abc123" in calls[2][0][0]

    @pytest.mark.asyncio
    async def test_rate_limit_sliding_window(self, rate_limiter, mock_redis_client):
        """Test sliding window implementation."""
        # Simulate old entries being removed
        mock_redis_client._client.zremrangebyscore.return_value = 5  # 5 old entries removed
        mock_redis_client._client.zcard.return_value = 10  # 10 current entries
        
        result = await rate_limiter.check_ip_limit("192.168.1.1")
        
        assert result.allowed is True
        assert result.remaining == 89  # 100 - 10 - 1
        
        # Verify zremrangebyscore was called to clean old entries
        mock_redis_client._client.zremrangebyscore.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_with_reset_time(self, rate_limiter, mock_redis_client):
        """Test rate limit includes reset time when exceeded."""
        mock_redis_client._client.zcard.return_value = 100  # At limit
        mock_redis_client._client.zrange.return_value = [("1234567890.0", 1234567890.0)]
        
        result = await rate_limiter.check_ip_limit("192.168.1.1")
        
        assert result.allowed is False
        assert result.reset_time > 0
        # Reset time should be oldest entry + window
        assert result.reset_time == 1234567890.0 + 60
