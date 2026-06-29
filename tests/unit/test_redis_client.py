"""Unit tests for enhanced Redis client.

Tests cover:
- Phase 16: Pooling, retries, health monitoring, batch operations, cluster readiness, distributed locks, TTL monitoring
- Phase 5: Audio buffer storage with TTL and cleanup
- Phase 6: Menu cache with versioning, invalidation, warming
- Phase 7: Recovery state for multi-instance safety
- All existing behavior preserved
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from app.infrastructure.redis_client import (
    RedisClient,
    RedisConnectionError,
    TTLMetrics,
    PoolMetrics,
    _retry_async,
)
from app.core.constants import (
    REDIS_SESSION_PREFIX,
    REDIS_CART_PREFIX,
    REDIS_AUDIO_PREFIX,
    REDIS_RECOVERY_PREFIX,
)


class TestRetryAsync:
    """Test retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_success_first_try(self):
        """Test retry succeeds on first attempt."""
        mock_coro = AsyncMock(return_value="success")
        result = await _retry_async(mock_coro, max_retries=3)
        assert result == "success"
        mock_coro.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_success_after_retries(self):
        """Test retry succeeds after some failures."""
        mock_coro = AsyncMock(side_effect=[ConnectionError("fail"), ConnectionError("fail"), "success"])
        with patch("app.infrastructure.redis_client.asyncio_sleep", AsyncMock()):
            result = await _retry_async(mock_coro, max_retries=3)
        assert result == "success"
        assert mock_coro.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Test retry raises after exhausting attempts."""
        mock_coro = AsyncMock(side_effect=ConnectionError("always fail"))
        with patch("app.infrastructure.redis_client.asyncio_sleep", AsyncMock()):
            with pytest.raises(ConnectionError):
                await _retry_async(mock_coro, max_retries=2)
        assert mock_coro.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_non_retryable_exception(self):
        """Test non-retryable exception is not retried."""
        mock_coro = AsyncMock(side_effect=ValueError("not retryable"))
        with pytest.raises(ValueError):
            await _retry_async(mock_coro, max_retries=3, retryable_exceptions=(ConnectionError,))
        mock_coro.assert_called_once()


class TestRedisClientConnection:
    """Test Redis client connection lifecycle."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.ping = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.rpush = AsyncMock(return_value=1)
        mock.lrange = AsyncMock(return_value=[])
        mock.hset = AsyncMock(return_value=1)
        mock.hgetall = AsyncMock(return_value={})
        mock.hdel = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=True)
        mock.eval = AsyncMock(return_value=1)
        mock.ttl = AsyncMock(return_value=-2)
        mock.mget = AsyncMock(return_value=[])
        mock.register_script = MagicMock()
        mock.pipeline = MagicMock()
        
        # Mock pipeline
        mock_pipe = MagicMock()
        mock_pipe.setex = AsyncMock(return_value=None)
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock.pipeline.return_value = mock_pipe
        
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_connect(self, redis_client, mock_redis):
        """Test Redis connection with pooling."""
        with patch("app.infrastructure.redis_client.ConnectionPool.from_url") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool.return_value = mock_pool_instance
            
            # Create a mock client that doesn't try to use the pool
            mock_client = MagicMock()
            mock_client.ping = AsyncMock(return_value=True)
            
            redis_client._client = None
            redis_client._pool = None
            
            with patch.object(redis_client, '_retry_call', AsyncMock(return_value=True)):
                with patch.object(redis_client, '_register_lua_scripts', AsyncMock()):
                    with patch.object(redis_client, '_start_health_monitoring'):
                        with patch("app.infrastructure.redis_client.redis.Redis", return_value=mock_client):
                            await redis_client.connect()
            
            assert redis_client._client is not None
            assert redis_client._pool is not None

    @pytest.mark.asyncio
    async def test_connect_failure(self, redis_client, mock_redis):
        """Test Redis connection failure raises error."""
        redis_client._client = None
        mock_redis.ping.side_effect = ConnectionError("Redis down")
        with pytest.raises(RedisConnectionError):
            await redis_client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, redis_client, mock_redis):
        """Test Redis disconnection."""
        mock_redis.close = AsyncMock()
        redis_client._pool = MagicMock()
        redis_client._pool.disconnect = AsyncMock()
        
        await redis_client.disconnect()
        
        assert redis_client._client is None
        assert redis_client._pool is None
        assert redis_client._healthy is False
        assert redis_client._closed is True
        mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_true(self, redis_client, mock_redis):
        """Test is_connected returns True when connected."""
        mock_redis.ping.return_value = True
        result = await redis_client.is_connected()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_false(self, redis_client, mock_redis):
        """Test is_connected returns False when disconnected."""
        mock_redis.ping.side_effect = Exception("Connection lost")
        result = await redis_client.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_connected_client_none(self, redis_client):
        """Test is_connected returns False when client is None."""
        redis_client._client = None
        result = await redis_client.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_connected_closed(self, redis_client):
        """Test is_connected returns False when closed."""
        redis_client._closed = True
        result = await redis_client.is_connected()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_cluster_ready(self, redis_client, mock_redis):
        """Test cluster readiness check."""
        mock_redis.info = AsyncMock(return_value={"cluster_enabled": 0})
        result = await redis_client.check_cluster_ready()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_cluster_ready_cluster_enabled(self, redis_client, mock_redis):
        """Test cluster readiness check when cluster is enabled."""
        mock_redis.info = AsyncMock(return_value={"cluster_enabled": 1})
        mock_redis.cluster_info = AsyncMock(return_value={"cluster_state": "ok"})
        result = await redis_client.check_cluster_ready()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_cluster_ready_cluster_fail(self, redis_client, mock_redis):
        """Test cluster readiness check when cluster is failing."""
        mock_redis.info = AsyncMock(return_value={"cluster_enabled": 1})
        mock_redis.cluster_info = AsyncMock(return_value={"cluster_state": "fail"})
        result = await redis_client.check_cluster_ready()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_cluster_ready_client_none(self, redis_client):
        """Test cluster readiness returns False when client is None."""
        redis_client._client = None
        result = await redis_client.check_cluster_ready()
        assert result is False

    def test_get_pool_metrics_no_pool(self, redis_client):
        """Test get_pool_metrics returns empty when no pool."""
        redis_client._pool = None
        metrics = redis_client.get_pool_metrics()
        assert isinstance(metrics, PoolMetrics)
        assert metrics.total_connections == 0


class TestRedisClientCore:
    """Test core Redis client functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.ping = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.rpush = AsyncMock(return_value=1)
        mock.lrange = AsyncMock(return_value=[])
        mock.hset = AsyncMock(return_value=1)
        mock.hgetall = AsyncMock(return_value={})
        mock.hdel = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=True)
        mock.eval = AsyncMock(return_value=1)
        mock.ttl = AsyncMock(return_value=-2)
        mock.mget = AsyncMock(return_value=[])
        mock.register_script = MagicMock()
        mock.pipeline = MagicMock()
        
        # Mock pipeline
        mock_pipe = MagicMock()
        mock_pipe.setex = AsyncMock(return_value=None)
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock.pipeline.return_value = mock_pipe
        
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    def test_build_key(self, redis_client):
        """Test Redis key building."""
        key = redis_client._build_key(REDIS_SESSION_PREFIX, "rest_1", "sess_123")
        assert key == "captain:session:rest_1:sess_123"

    def test_build_key_with_suffix(self, redis_client):
        """Test Redis key building with suffix."""
        key = redis_client._build_key(REDIS_SESSION_PREFIX, "rest_1", "sess_123", "active")
        assert key == "captain:session:rest_1:sess_123:active"

    def test_serialize_deserialize(self, redis_client):
        """Test JSON serialization/deserialization."""
        import asyncio
        data = {"key": "value", "number": 42}
        serialized = asyncio.run(redis_client._serialize(data))
        assert isinstance(serialized, str)
        deserialized = asyncio.run(redis_client._deserialize(serialized))
        assert deserialized == data

    def test_serialize_deserialize_none(self, redis_client):
        """Test deserialization of None."""
        import asyncio
        result = asyncio.run(redis_client._deserialize(None))
        assert result is None


class TestRedisClientSession:
    """Test session state management."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.ping = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_save_session_state(self, redis_client, mock_redis):
        """Test saving session state."""
        await redis_client.save_session_state("rest_1", "sess_123", {"key": "value"}, 3600)
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][0] == "captain:session:rest_1:sess_123"
        assert args[0][1] == 3600

    @pytest.mark.asyncio
    async def test_load_session_state(self, redis_client, mock_redis):
        """Test loading session state."""
        mock_redis.get.return_value = '{"key": "value"}'
        result = await redis_client.load_session_state("rest_1", "sess_123")
        assert result == {"key": "value"}
        mock_redis.get.assert_called_once_with("captain:session:rest_1:sess_123")

    @pytest.mark.asyncio
    async def test_load_session_state_not_found(self, redis_client, mock_redis):
        """Test loading non-existent session state."""
        mock_redis.get.return_value = None
        result = await redis_client.load_session_state("rest_1", "sess_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_session_state(self, redis_client, mock_redis):
        """Test deleting session state."""
        await redis_client.delete_session_state("rest_1", "sess_123")
        mock_redis.delete.assert_called_once_with("captain:session:rest_1:sess_123")

    @pytest.mark.asyncio
    async def test_save_cart_snapshot(self, redis_client, mock_redis):
        """Test saving cart snapshot."""
        cart = {"items": [{"dish_id": 101, "quantity": 2}]}
        await redis_client.save_cart_snapshot("rest_1", "sess_123", cart)
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][0] == "captain:cart:rest_1:sess_123"

    @pytest.mark.asyncio
    async def test_load_cart_snapshot(self, redis_client, mock_redis):
        """Test loading cart snapshot."""
        mock_redis.get.return_value = '{"items": []}'
        result = await redis_client.load_cart_snapshot("rest_1", "sess_123")
        assert result == {"items": []}

    @pytest.mark.asyncio
    async def test_mark_session_active(self, redis_client, mock_redis):
        """Test marking session as active."""
        await redis_client.mark_session_active("rest_1", "sess_123")
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][0] == "captain:session:rest_1:sess_123:active"
        assert args[0][1] == 3600  # Default TTL

    @pytest.mark.asyncio
    async def test_mark_session_inactive(self, redis_client, mock_redis):
        """Test marking session as inactive."""
        await redis_client.mark_session_inactive("rest_1", "sess_123")
        mock_redis.delete.assert_called_once_with("captain:session:rest_1:sess_123:active")

    @pytest.mark.asyncio
    async def test_is_session_active_true(self, redis_client, mock_redis):
        """Test is_session_active returns True."""
        mock_redis.exists.return_value = 1
        result = await redis_client.is_session_active("rest_1", "sess_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_session_active_false(self, redis_client, mock_redis):
        """Test is_session_active returns False."""
        mock_redis.exists.return_value = 0
        result = await redis_client.is_session_active("rest_1", "sess_123")
        assert result is False


class TestRedisClientMessages:
    """Test message storage methods."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock(return_value=True)
        mock.ping = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_save_last_user_message(self, redis_client, mock_redis):
        """Test saving last user message."""
        await redis_client.save_last_user_message("rest_1", "sess_123", "Hello")
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][0] == "captain:session:rest_1:sess_123:last_user_msg"

    @pytest.mark.asyncio
    async def test_load_last_user_message(self, redis_client, mock_redis):
        """Test loading last user message."""
        mock_redis.get.return_value = "Hello"
        result = await redis_client.load_last_user_message("rest_1", "sess_123")
        assert result == "Hello"

    @pytest.mark.asyncio
    async def test_save_last_assistant_message(self, redis_client, mock_redis):
        """Test saving last assistant message."""
        await redis_client.save_last_assistant_message("rest_1", "sess_123", "Welcome!")
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][0] == "captain:session:rest_1:sess_123:last_asst_msg"

    @pytest.mark.asyncio
    async def test_load_last_assistant_message(self, redis_client, mock_redis):
        """Test loading last assistant message."""
        mock_redis.get.return_value = "Welcome!"
        result = await redis_client.load_last_assistant_message("rest_1", "sess_123")
        assert result == "Welcome!"


class TestRedisClientRecovery:
    """Test recovery marker methods."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.ping = AsyncMock(return_value=True)
        mock.scan = AsyncMock(return_value=(0, []))
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_schedule_recovery_marker(self, redis_client, mock_redis):
        """Test scheduling recovery marker."""
        mock_redis.set.return_value = True
        result = await redis_client.schedule_recovery_marker("rest_1", "sess_123", 900)
        assert result is True
        mock_redis.set.assert_called_once()
        args = mock_redis.set.call_args
        assert args[0][0] == "captain:recovery:rest_1:sess_123"
        assert args[1]["ex"] == 900
        assert args[1]["nx"] is True

    @pytest.mark.asyncio
    async def test_schedule_recovery_marker_contains_instance_id(self, redis_client, mock_redis):
        """Test recovery marker contains instance_id for multi-instance support."""
        mock_redis.set.return_value = True
        await redis_client.schedule_recovery_marker("rest_1", "sess_123", 900)
        args = mock_redis.set.call_args
        payload = json.loads(args[0][1])
        assert "instance_id" in payload
        assert len(payload["instance_id"]) == 8

    @pytest.mark.asyncio
    async def test_cancel_recovery_marker(self, redis_client, mock_redis):
        """Test canceling recovery marker."""
        await redis_client.cancel_recovery_marker("rest_1", "sess_123")
        mock_redis.delete.assert_called_once_with("captain:recovery:rest_1:sess_123")

    @pytest.mark.asyncio
    async def test_check_recovery_marker_exists(self, redis_client, mock_redis):
        """Test checking recovery marker exists."""
        mock_redis.exists.return_value = 1
        result = await redis_client.check_recovery_marker("rest_1", "sess_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_check_recovery_marker_not_exists(self, redis_client, mock_redis):
        """Test checking recovery marker doesn't exist."""
        mock_redis.exists.return_value = 0
        result = await redis_client.check_recovery_marker("rest_1", "sess_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_recovery_marker(self, redis_client, mock_redis):
        """Test getting recovery marker."""
        mock_redis.get.return_value = '{"recovery_status": "scheduled"}'
        result = await redis_client.get_recovery_marker("rest_1", "sess_123")
        assert result == {"recovery_status": "scheduled"}

    @pytest.mark.asyncio
    async def test_mark_recovery_completed(self, redis_client, mock_redis):
        """Test marking recovery as completed."""
        mock_redis.get.return_value = '{"recovery_status": "scheduled"}'
        await redis_client.mark_recovery_completed("rest_1", "sess_123")
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][1] == 60  # 60 seconds TTL after completion

    @pytest.mark.asyncio
    async def test_save_recovery_state(self, redis_client, mock_redis):
        """Test saving recovery state with NX."""
        mock_redis.set.return_value = True
        result = await redis_client.save_recovery_state("rest_1", "sess_123", {"key": "val"}, 300)
        assert result is True
        mock_redis.set.assert_called_once()
        args = mock_redis.set.call_args
        assert args[0][0] == "captain:recovery:rest_1:sess_123"
        assert args[1]["nx"] is True

    @pytest.mark.asyncio
    async def test_list_active_recoveries(self, redis_client, mock_redis):
        """Test listing active recoveries."""
        mock_redis.scan.return_value = (0, ["captain:recovery:rest_1:sess_123"])
        mock_redis.get.return_value = '{"recovery_status": "scheduled", "instance_id": "abc12345"}'
        markers = await redis_client.list_active_recoveries()
        assert len(markers) == 1
        assert markers[0]["recovery_status"] == "scheduled"


class TestRedisClientLocks:
    """Test distributed lock operations."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.set = AsyncMock(return_value=True)
        mock.eval = AsyncMock(return_value=1)
        mock.ping = AsyncMock(return_value=True)
        mock.register_script = MagicMock()
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, redis_client, mock_redis):
        """Test acquiring lock successfully."""
        mock_redis.set.return_value = True
        success, lock_value = await redis_client.acquire_lock("test_lock", 10)
        assert success is True
        assert lock_value is not None
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, redis_client, mock_redis):
        """Test acquiring lock when already held."""
        mock_redis.set.return_value = None
        success, lock_value = await redis_client.acquire_lock("test_lock", 10)
        assert success is False
        assert lock_value is not None

    @pytest.mark.asyncio
    async def test_acquire_lock_auto_extend(self, redis_client, mock_redis):
        """Test acquiring lock with auto-extension."""
        mock_redis.set.return_value = True
        success, lock_value = await redis_client.acquire_lock("test_lock", 10, auto_extend=True)
        assert success is True
        assert lock_value is not None
        # Should have started extension task
        assert "test_lock" in redis_client._lock_extension_tasks

    @pytest.mark.asyncio
    async def test_release_lock_success(self, redis_client, mock_redis):
        """Test releasing lock successfully."""
        # Set up Lua script as a callable that returns a coroutine
        mock_script = AsyncMock(return_value=1)
        mock_redis.register_script.return_value = mock_script
        await redis_client._register_lua_scripts()
        redis_client._lua_scripts["release_lock"] = mock_script

        lock_value = "test-lock-value"
        result = await redis_client.release_lock("test_lock", lock_value)
        assert result is True
        mock_script.assert_called_once_with(keys=["test_lock"], args=[lock_value])

    @pytest.mark.asyncio
    async def test_release_lock_fallback(self, redis_client, mock_redis):
        """Test releasing lock falls back to eval when no script."""
        redis_client._lua_scripts = {}
        mock_redis.eval.return_value = 1
        result = await redis_client.release_lock("test_lock", "value")
        assert result is True
        mock_redis.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_lock(self, redis_client, mock_redis):
        """Test extending a lock."""
        mock_script = AsyncMock(return_value=1)
        mock_redis.register_script.return_value = mock_script
        await redis_client._register_lua_scripts()
        redis_client._lua_scripts["extend_lock"] = mock_script

        result = await redis_client.extend_lock("test_lock", "value", 10)
        assert result is True
        mock_script.assert_called_once_with(keys=["test_lock"], args=["value", "10"])


class TestRedisClientPipeline:
    """Test pipeline operations."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.ping = AsyncMock(return_value=True)
        mock.pipeline = MagicMock()
        
        mock_pipe = MagicMock()
        mock_pipe.setex = AsyncMock(return_value=None)
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock.pipeline.return_value = mock_pipe
        
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_pipeline(self, redis_client, mock_redis):
        """Test pipeline context manager."""
        async with redis_client.pipeline() as pipe:
            await pipe.setex("key1", 60, "value1")
            await pipe.setex("key2", 60, "value2")
        
        # Pipeline should auto-execute
        mock_redis.pipeline.assert_called_once()
        mock_pipe = mock_redis.pipeline.return_value
        assert mock_pipe.setex.call_count == 2
        mock_pipe.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_session_state_atomic(self, redis_client, mock_redis):
        """Test atomic session state save."""
        await redis_client.save_session_state_atomic(
            "rest_1", "sess_123", {"key": "value"}, {"items": []}, 3600
        )
        mock_redis.pipeline.assert_called_once()
        mock_pipe = mock_redis.pipeline.return_value
        assert mock_pipe.setex.call_count == 2
        mock_pipe.execute.assert_called_once()


class TestRedisClientAudio:
    """Test audio buffer operations (Phase 5)."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.rpush = AsyncMock(return_value=1)
        mock.lrange = AsyncMock(return_value=[])
        mock.expire = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.hset = AsyncMock(return_value=1)
        mock.hgetall = AsyncMock(return_value={})
        mock.hdel = AsyncMock(return_value=1)
        mock.get = AsyncMock(return_value=None)
        mock.exists = AsyncMock(return_value=0)
        mock.delete = AsyncMock(return_value=2)
        mock.ping = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_append_audio_buffer_metadata(self, redis_client, mock_redis):
        """Test appending audio buffer metadata."""
        metadata = {"sequence": 0, "mime_type": "audio/wav"}
        await redis_client.append_audio_buffer_metadata("rest_1", "sess_123", metadata)
        mock_redis.rpush.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_buffer_metadata(self, redis_client, mock_redis):
        """Test getting audio buffer metadata."""
        mock_redis.lrange.return_value = ['{"seq": 0}', '{"seq": 1}']
        result = await redis_client.get_audio_buffer_metadata("rest_1", "sess_123")
        assert len(result) == 2
        assert result[0]["seq"] == 0
        assert result[1]["seq"] == 1

    @pytest.mark.asyncio
    async def test_store_audio_chunk(self, redis_client, mock_redis):
        """Test storing an audio chunk."""
        chunk_bytes = b"test audio data"
        await redis_client.store_audio_chunk(
            "rest_1", "sess_123", "conn_1", chunk_bytes, "audio/wav", 0, 300
        )
        mock_redis.setex.assert_called_once()
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_chunks(self, redis_client, mock_redis):
        """Test retrieving audio chunks."""
        mock_redis.hgetall.return_value = {
            "0": '{"sequence": 0, "mime_type": "audio/wav", "connection_id": "conn_1"}',
            "1": '{"sequence": 1, "mime_type": "audio/wav", "connection_id": "conn_1"}',
        }
        mock_redis.get.side_effect = [b"chunk1", b"chunk2"]
        
        chunks = await redis_client.get_audio_chunks("conn_1")
        assert len(chunks) == 2
        assert chunks[0][0] == 0
        assert chunks[0][1] == b"chunk1"
        assert chunks[1][0] == 1

    @pytest.mark.asyncio
    async def test_get_audio_chunks_empty(self, redis_client, mock_redis):
        """Test retrieving audio chunks when none exist."""
        mock_redis.hgetall.return_value = {}
        chunks = await redis_client.get_audio_chunks("conn_1")
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_delete_audio_data(self, redis_client, mock_redis):
        """Test deleting audio data."""
        mock_redis.hgetall.return_value = {"0": "meta", "1": "meta"}
        await redis_client.delete_audio_data("conn_1")
        mock_redis.delete.assert_called_once()
        # Should delete metadata key + 2 chunk keys
        args = mock_redis.delete.call_args
        assert len(args[0]) == 3

    @pytest.mark.asyncio
    async def test_cleanup_expired_audio(self, redis_client, mock_redis):
        """Test cleaning up expired audio chunks."""
        mock_redis.hgetall.return_value = {"0": "meta", "1": "meta"}
        mock_redis.exists.return_value = 0  # Both expired
        cleaned = await redis_client.cleanup_expired_audio("conn_1")
        assert cleaned == 2
        # hdel should be called once per expired chunk
        assert mock_redis.hdel.call_count == 2


class TestRedisClientMenuCache:
    """Test menu cache operations (Phase 6)."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.setex = AsyncMock(return_value=True)
        mock.set = AsyncMock(return_value=True)
        mock.get = AsyncMock(return_value=None)
        mock.delete = AsyncMock(return_value=1)
        mock.ping = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_save_menu_cache(self, redis_client, mock_redis):
        """Test saving menu cache with versioning."""
        menu_data = {"categories": []}
        await redis_client.save_menu_cache("rest_1", menu_data, ttl_seconds=300, version=1)
        # Should setex for data and set for version
        assert mock_redis.setex.call_count == 1
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_menu_cache(self, redis_client, mock_redis):
        """Test loading menu cache."""
        mock_redis.get.return_value = json.dumps({"menu": {"categories": []}, "cached_at": 1000, "version": 1})
        result = await redis_client.load_menu_cache("rest_1")
        assert result == {"categories": []}

    @pytest.mark.asyncio
    async def test_load_menu_cache_not_found(self, redis_client, mock_redis):
        """Test loading menu cache when not cached."""
        mock_redis.get.return_value = None
        result = await redis_client.load_menu_cache("rest_1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_menu_cache_version(self, redis_client, mock_redis):
        """Test getting menu cache version."""
        mock_redis.get.return_value = "2"
        version = await redis_client.get_menu_cache_version("rest_1")
        assert version == 2

    @pytest.mark.asyncio
    async def test_get_menu_cache_version_not_set(self, redis_client, mock_redis):
        """Test getting menu cache version when not set."""
        mock_redis.get.return_value = None
        version = await redis_client.get_menu_cache_version("rest_1")
        assert version is None

    @pytest.mark.asyncio
    async def test_invalidate_menu_cache(self, redis_client, mock_redis):
        """Test invalidating menu cache."""
        result = await redis_client.invalidate_menu_cache("rest_1")
        assert result is True
        assert mock_redis.delete.call_count == 2  # Data key + version key

    @pytest.mark.asyncio
    async def test_warm_menu_cache(self, redis_client, mock_redis):
        """Test warming menu cache."""
        menu_data = {"categories": []}
        await redis_client.warm_menu_cache("rest_1", menu_data, 300)
        assert mock_redis.setex.call_count == 1


class TestRedisClientBatch:
    """Test batch operations (Phase 16)."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.mget = AsyncMock(return_value=[])
        mock.ping = AsyncMock(return_value=True)
        mock.pipeline = MagicMock()
        mock.register_script = MagicMock()
        
        mock_pipe = MagicMock()
        mock_pipe.setex = AsyncMock(return_value=None)
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock.pipeline.return_value = mock_pipe
        
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    @pytest.mark.asyncio
    async def test_batch_get(self, redis_client, mock_redis):
        """Test batch get."""
        mock_redis.mget.return_value = ['{"a": 1}', '{"b": 2}']
        result = await redis_client.batch_get(["key1", "key2"])
        assert len(result) == 2
        assert result["key1"] == {"a": 1}

    @pytest.mark.asyncio
    async def test_batch_setex(self, redis_client, mock_redis):
        """Test batch setex."""
        items = {"key1": ({"data": 1}, 60), "key2": ({"data": 2}, 120)}
        result = await redis_client.batch_setex(items)
        assert result == 2


class TestRedisClientTTLMonitoring:
    """Test TTL monitoring (Phase 16)."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.ttl = AsyncMock(return_value=100)
        mock.ping = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def redis_client(self, mock_redis, test_settings):
        """Provide RedisClient with mocked connection."""
        client = RedisClient(test_settings)
        client._client = mock_redis
        client._healthy = True
        return client

    def test_track_ttl(self, redis_client):
        """Test tracking TTL for a key."""
        redis_client._track_ttl("test_key", 300)
        assert "test_key" in redis_client._ttl_metrics
        assert redis_client._ttl_metrics["test_key"].ttl_seconds == 300

    def test_get_ttl_metrics(self, redis_client):
        """Test getting TTL metrics."""
        redis_client._track_ttl("key1", 3600)
        redis_client._track_ttl("key2", 300)
        metrics = redis_client.get_ttl_metrics()
        assert "key1" in metrics
        assert "key2" in metrics
        assert metrics["key1"].key == "key1"
        assert metrics["key1"].remaining is not None

    @pytest.mark.asyncio
    async def test_get_ttl(self, redis_client, mock_redis):
        """Test getting TTL for a key."""
        mock_redis.ttl.return_value = -2
        ttl = await redis_client.get_ttl("test_key")
        assert ttl == -2
        mock_redis.ttl.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_check_expired_keys(self, redis_client, mock_redis):
        """Test checking which keys have expired."""
        mock_redis.ttl.side_effect = [100, -2, -2, 50]
        expired = await redis_client.check_expired_keys(["k1", "k2", "k3", "k4"])
        assert expired == ["k2", "k3"]


class TestRedisClientErrors:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_ensure_client_not_initialized(self, redis_client):
        """Test _ensure_client raises when not initialized."""
        redis_client._client = None
        with pytest.raises(RuntimeError, match="not been initialized"):
            await redis_client._ensure_client()

    @pytest.mark.asyncio
    async def test_ensure_client_closed(self, redis_client):
        """Test _ensure_client raises when closed."""
        redis_client._closed = True
        with pytest.raises(RuntimeError, match="been closed"):
            await redis_client._ensure_client()