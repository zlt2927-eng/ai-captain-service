"""Unit tests for recovery service.

Phase 7: Tests for multi-instance safe recovery state management.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.recovery_service import RecoveryService, RecoveryServiceError
from app.core.config import Settings


class TestRecoveryService:
    """Test recovery service functionality."""

    @pytest.fixture
    def mock_http_client(self):
        """Provide mock HTTP client."""
        mock = MagicMock()
        mock.post_json = AsyncMock(return_value={"success": True})
        return mock

    @pytest.fixture
    def mock_redis_client(self):
        """Provide mock Redis client with proper async methods."""
        mock = MagicMock()
        mock.get_recovery_marker = AsyncMock(return_value=None)
        mock.schedule_recovery_marker = AsyncMock(return_value=True)
        mock.cancel_recovery_marker = AsyncMock(return_value=None)
        mock.check_recovery_marker = AsyncMock(return_value=False)
        mock.mark_recovery_completed = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def mock_session_service(self):
        """Provide mock session service."""
        mock = MagicMock()
        mock.is_session_active = AsyncMock(return_value=False)
        mock.build_recovery_payload = AsyncMock(return_value={
            "event_id": "test-event-id",
            "session_id": "sess_123",
            "restaurant_id": "rest_1",
            "cart_snapshot": {},
        })
        return mock

    @pytest.fixture
    def recovery_service(self, mock_http_client, mock_redis_client, mock_session_service, test_settings):
        """Provide RecoveryService with mocked dependencies."""
        return RecoveryService(
            test_settings,
            mock_http_client,
            mock_redis_client,
            mock_session_service,
        )

    @pytest.mark.asyncio
    async def test_schedule_recovery_new(self, recovery_service, mock_redis_client):
        """Test scheduling recovery for new session."""
        mock_redis_client.get_recovery_marker.return_value = None  # No existing marker
        mock_redis_client.schedule_recovery_marker.return_value = True  # Successfully created
        
        await recovery_service.schedule_recovery("rest_1", "sess_123")
        
        # Should create recovery marker
        mock_redis_client.schedule_recovery_marker.assert_called_once()
        # Should create background task
        assert len(recovery_service._scheduled_tasks) == 1

    @pytest.mark.asyncio
    async def test_schedule_recovery_already_scheduled(self, recovery_service, mock_redis_client):
        """Test scheduling recovery when already scheduled."""
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "scheduled"}
        
        await recovery_service.schedule_recovery("rest_1", "sess_123")
        
        # Should not create new marker
        mock_redis_client.schedule_recovery_marker.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_recovery_already_completed(self, recovery_service, mock_redis_client):
        """Test scheduling recovery when already completed."""
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "completed"}
        
        await recovery_service.schedule_recovery("rest_1", "sess_123")
        
        # Should not create new marker
        mock_redis_client.schedule_recovery_marker.assert_not_called()

    @pytest.mark.asyncio
    async def test_schedule_recovery_task_already_running(self, recovery_service, mock_redis_client):
        """Test scheduling when task already running."""
        mock_redis_client.get_recovery_marker.return_value = None
        mock_redis_client.schedule_recovery_marker.return_value = True
        
        # Create a mock task that's not done
        mock_task = MagicMock()
        mock_task.done.return_value = False
        recovery_service._scheduled_tasks["rest_1:sess_123"] = mock_task
        
        await recovery_service.schedule_recovery("rest_1", "sess_123")
        
        # Should not create new task
        assert len(recovery_service._scheduled_tasks) == 1

    @pytest.mark.asyncio
    async def test_cancel_recovery(self, recovery_service, mock_redis_client):
        """Test canceling recovery."""
        # Create a mock running task
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        recovery_service._scheduled_tasks["rest_1:sess_123"] = mock_task
        
        await recovery_service.cancel_recovery("rest_1", "sess_123")
        
        # Should cancel task
        mock_task.cancel.assert_called_once()
        # Should delete recovery marker
        mock_redis_client.cancel_recovery_marker.assert_called_once_with("rest_1", "sess_123")
        # Should remove from scheduled tasks
        assert len(recovery_service._scheduled_tasks) == 0

    @pytest.mark.asyncio
    async def test_cancel_recovery_no_task(self, recovery_service, mock_redis_client):
        """Test canceling recovery when no task exists."""
        await recovery_service.cancel_recovery("rest_1", "sess_123")
        
        # Should still delete marker
        mock_redis_client.cancel_recovery_marker.assert_called_once_with("rest_1", "sess_123")

    @pytest.mark.asyncio
    async def test_get_recovery_status_scheduled(self, recovery_service, mock_redis_client):
        """Test getting recovery status when scheduled."""
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "scheduled"}
        
        status = await recovery_service.get_recovery_status("rest_1", "sess_123")
        
        assert status["status"] == "scheduled"

    @pytest.mark.asyncio
    async def test_get_recovery_status_completed(self, recovery_service, mock_redis_client):
        """Test getting recovery status when completed."""
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "completed"}
        
        status = await recovery_service.get_recovery_status("rest_1", "sess_123")
        
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_recovery_status_none(self, recovery_service, mock_redis_client):
        """Test getting recovery status when none exists."""
        mock_redis_client.get_recovery_marker.return_value = None
        
        status = await recovery_service.get_recovery_status("rest_1", "sess_123")
        
        assert status["status"] == "none"

    @pytest.mark.asyncio
    async def test_execute_recovery_success(self, recovery_service, mock_redis_client, mock_http_client, mock_session_service):
        """Test successful recovery execution."""
        # Setup: marker exists, session not active
        mock_redis_client.check_recovery_marker.return_value = True  # Marker exists
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "scheduled"}
        
        # Fast-forward the delay
        with patch("app.services.recovery_service.asyncio.sleep"):
            await recovery_service._execute_recovery_if_abandoned("rest_1", "sess_123")
        
        # Should send webhook
        mock_http_client.post_json.assert_called_once()
        # Should mark as completed
        mock_redis_client.mark_recovery_completed.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_recovery_session_reactivated(self, recovery_service, mock_redis_client, mock_session_service, mock_http_client):
        """Test recovery aborted when session reactivated."""
        mock_redis_client.check_recovery_marker.return_value = True
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "scheduled"}
        mock_session_service.is_session_active.return_value = True  # Session active
        
        with patch("app.services.recovery_service.asyncio.sleep"):
            await recovery_service._execute_recovery_if_abandoned("rest_1", "sess_123")
        
        # Should cancel recovery
        mock_redis_client.cancel_recovery_marker.assert_called_once()
        # Should not send webhook
        assert not mock_http_client.post_json.called

    @pytest.mark.asyncio
    async def test_execute_recovery_marker_cleared(self, recovery_service, mock_redis_client, mock_session_service, mock_http_client):
        """Test recovery aborted when marker cleared."""
        mock_redis_client.check_recovery_marker.return_value = False  # Marker gone
        
        with patch("app.services.recovery_service.asyncio.sleep"):
            await recovery_service._execute_recovery_if_abandoned("rest_1", "sess_123")
        
        # Should not send webhook
        assert not mock_http_client.post_json.called

    @pytest.mark.asyncio
    async def test_execute_recovery_webhook_failure(self, recovery_service, mock_redis_client, mock_http_client):
        """Test recovery with webhook failure."""
        from app.infrastructure.http_client import HTTPClientError
        mock_redis_client.check_recovery_marker.return_value = True
        mock_redis_client.get_recovery_marker.return_value = {"recovery_status": "scheduled"}
        mock_http_client.post_json.side_effect = HTTPClientError("Webhook failed")
        
        with patch("app.services.recovery_service.asyncio.sleep"):
            # Should not raise, should handle error gracefully
            await recovery_service._execute_recovery_if_abandoned("rest_1", "sess_123")
        
        # Should attempt to send webhook
        mock_http_client.post_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_recovery_webhook_success(self, recovery_service, mock_http_client):
        """Test sending recovery webhook."""
        mock_http_client.post_json.return_value = {"success": True}
        
        payload = {
            "event_id": "test-event",
            "session_id": "sess_123",
        }
        
        # Should not raise
        await recovery_service._send_recovery_webhook(payload)
        
        mock_http_client.post_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_recovery_webhook_failure(self, recovery_service, mock_http_client):
        """Test sending recovery webhook with failure."""
        from app.infrastructure.http_client import HTTPClientError
        mock_http_client.post_json.side_effect = HTTPClientError("Connection failed")
        
        payload = {"event_id": "test-event"}
        
        with pytest.raises(RecoveryServiceError, match="Connection failed"):
            await recovery_service._send_recovery_webhook(payload)

    def test_task_key(self, recovery_service):
        """Test task key generation."""
        key = recovery_service._task_key("rest_1", "sess_123")
        assert key == "rest_1:sess_123"