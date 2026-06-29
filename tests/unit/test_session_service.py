"""Unit tests for session service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.services.session_service import SessionService
from app.core.constants import REDIS_SESSION_PREFIX


class TestSessionService:
    """Test session service functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock(return_value=True)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.pipeline = MagicMock()
        
        mock_pipe = MagicMock()
        mock_pipe.setex = AsyncMock(return_value=None)
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=None)
        mock.pipeline.return_value = mock_pipe
        
        return mock

    @pytest.fixture
    def session_service(self, mock_redis, test_settings):
        """Provide SessionService with mocked Redis."""
        return SessionService(mock_redis, test_settings.SESSION_TTL_SECONDS)

    @pytest.mark.asyncio
    async def test_start_session(self, session_service, mock_redis):
        """Test starting a new session."""
        await session_service.start_session("rest_1", "sess_123")
        
        # Should save session state and mark as active
        assert mock_redis.setex.call_count >= 1
        mock_redis.setex.assert_any_call(
            "captain:session:rest_1:sess_123:active",
            3600,
            "1"
        )

    @pytest.mark.asyncio
    async def test_start_session_with_metadata(self, session_service, mock_redis):
        """Test starting session with custom metadata."""
        metadata = {"user_id": "user_456"}
        await session_service.start_session("rest_1", "sess_123", metadata)
        
        # Should include custom metadata
        calls = mock_redis.setex.call_args_list
        # Find the session state call (not the active marker)
        session_call = None
        for call in calls:
            if call[0][0] == "captain:session:rest_1:sess_123":
                session_call = call
                break
        
        assert session_call is not None
        # The value should be JSON with metadata
        import json
        saved_data = json.loads(session_call[0][2])
        assert saved_data["user_id"] == "user_456"

    @pytest.mark.asyncio
    async def test_get_session_context_success(self, session_service, mock_redis):
        """Test getting session context."""
        session_data = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "turn_count": 5,
        }
        cart_data = {"items": [{"dish_id": 101}]}
        
        mock_redis.get.side_effect = [
            json.dumps(session_data),  # First call: session state
            json.dumps(cart_data),  # Second call: cart snapshot
        ]
        
        context = await session_service.get_session_context("rest_1", "sess_123")
        
        assert context is not None
        assert context["restaurant_id"] == "rest_1"
        assert context["turn_count"] == 5
        assert context["cart_snapshot"] == cart_data

    @pytest.mark.asyncio
    async def test_get_session_context_not_found(self, session_service, mock_redis):
        """Test getting non-existent session context."""
        mock_redis.get.return_value = None
        
        context = await session_service.get_session_context("rest_1", "sess_123")
        
        assert context is None

    @pytest.mark.asyncio
    async def test_append_turn(self, session_service, mock_redis):
        """Test appending conversation turn."""
        # First call returns existing metadata, second call saves updated
        session_data = {"turn_count": 0, "last_activity": "2024-01-01T00:00:00"}
        mock_redis.get.side_effect = [
            json.dumps(session_data),
            None,  # For save operation
        ]
        
        await session_service.append_turn(
            "rest_1",
            "sess_123",
            "turn_001",
            "أبغى برجر",
            "تم، أضفت البرجر",
            {"items": []},
        )
        
        # Should save turn data and update metadata
        assert mock_redis.setex.call_count >= 1

    @pytest.mark.asyncio
    async def test_persist_conversation_turn(self, session_service, mock_redis):
        """Test persisting complete conversation turn."""
        await session_service.persist_conversation_turn(
            "rest_1",
            "sess_123",
            "أبغى برجر",
            "تم، أضفت البرجر",
            "turn_001",
        )
        
        # Should save messages and append turn
        assert mock_redis.setex.call_count >= 2

    @pytest.mark.asyncio
    async def test_persist_conversation_turn_generates_turn_id(self, session_service, mock_redis):
        """Test that persist generates turn_id if not provided."""
        mock_redis.get.return_value = None
        
        await session_service.persist_conversation_turn(
            "rest_1",
            "sess_123",
            "أبغى برجر",
            "تم، أضفت البرجر",
        )
        
        # Should still work without turn_id
        assert mock_redis.setex.call_count >= 2

    @pytest.mark.asyncio
    async def test_save_and_load_cart_snapshot(self, session_service, mock_redis):
        """Test saving and loading cart snapshot."""
        cart = {"items": [{"dish_id": 101, "quantity": 2}]}
        
        await session_service.save_cart_snapshot("rest_1", "sess_123", cart)
        mock_redis.setex.assert_called_once()
        
        mock_redis.get.return_value = json.dumps(cart)
        loaded_cart = await session_service.load_cart_snapshot("rest_1", "sess_123")
        
        assert loaded_cart == cart

    @pytest.mark.asyncio
    async def test_delete_cart_snapshot(self, session_service, mock_redis):
        """Test deleting cart snapshot."""
        await session_service.delete_cart_snapshot("rest_1", "sess_123")
        mock_redis.delete.assert_called_once_with("captain:cart:rest_1:sess_123")

    @pytest.mark.asyncio
    async def test_mark_session_active(self, session_service, mock_redis):
        """Test marking session as active."""
        await session_service.mark_session_active("rest_1", "sess_123")
        mock_redis.setex.assert_called_once_with(
            "captain:session:rest_1:sess_123:active",
            3600,
            "1"
        )

    @pytest.mark.asyncio
    async def test_mark_session_inactive(self, session_service, mock_redis):
        """Test marking session as inactive."""
        await session_service.mark_session_inactive("rest_1", "sess_123")
        mock_redis.delete.assert_called_once_with("captain:session:rest_1:sess_123:active")

    @pytest.mark.asyncio
    async def test_is_session_active_true(self, session_service, mock_redis):
        """Test is_session_active returns True."""
        mock_redis.exists.return_value = 1
        result = await session_service.is_session_active("rest_1", "sess_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_session_active_false(self, session_service, mock_redis):
        """Test is_session_active returns False."""
        mock_redis.exists.return_value = 0
        result = await session_service.is_session_active("rest_1", "sess_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_recovery(self, session_service, mock_redis):
        """Test canceling recovery."""
        await session_service.cancel_recovery("rest_1", "sess_123")
        mock_redis.delete.assert_called_once_with("captain:recovery:rest_1:sess_123")

    @pytest.mark.asyncio
    async def test_build_recovery_payload(self, session_service, mock_redis):
        """Test building recovery payload."""
        session_data = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "last_user_message": "أبغى برجر",
            "last_assistant_message": "تم، أضفت البرجر",
        }
        cart_data = {"items": [{"dish_id": 101}]}
        recovery_data = {
            "disconnected_at": "2024-01-01T12:00:00Z",
            "recovery_status": "scheduled",
        }
        
        mock_redis.get.side_effect = [
            json.dumps(session_data),
            json.dumps(cart_data),
            json.dumps(recovery_data),
        ]
        
        payload = await session_service.build_recovery_payload("rest_1", "sess_123")
        
        assert payload["session_id"] == "sess_123"
        assert payload["restaurant_id"] == "rest_1"
        assert payload["last_user_message"] == "أبغى برجر"
        assert payload["cart_snapshot"] == cart_data
        assert "event_id" in payload
        assert "schema_version" in payload

    @pytest.mark.asyncio
    async def test_build_recovery_payload_no_data(self, session_service, mock_redis):
        """Test building recovery payload with no data."""
        mock_redis.get.return_value = None
        
        payload = await session_service.build_recovery_payload("rest_1", "sess_123")
        
        assert payload["session_id"] == "sess_123"
        assert payload["restaurant_id"] == "rest_1"
        assert payload["last_user_message"] is None
        assert payload["cart_snapshot"] == {}

    @pytest.mark.asyncio
    async def test_link_order_to_session(self, session_service, mock_redis):
        """Test linking order to session."""
        await session_service.link_order_to_session("rest_1", "sess_123", 456)
        
        # Should save order_id and update session metadata
        assert mock_redis.setex.call_count >= 1
        mock_redis.setex.assert_any_call(
            "captain:order:rest_1:sess_123",
            3600,
            "456"
        )

    @pytest.mark.asyncio
    async def test_get_linked_order(self, session_service, mock_redis):
        """Test getting linked order."""
        mock_redis.get.return_value = "456"
        
        order_id = await session_service.get_linked_order("rest_1", "sess_123")
        
        assert order_id == 456

    @pytest.mark.asyncio
    async def test_get_linked_order_not_found(self, session_service, mock_redis):
        """Test getting linked order when not linked."""
        mock_redis.get.return_value = None
        
        order_id = await session_service.get_linked_order("rest_1", "sess_123")
        
        assert order_id is None

    @pytest.mark.asyncio
    async def test_get_linked_order_invalid_format(self, session_service, mock_redis):
        """Test getting linked order with invalid format."""
        mock_redis.get.return_value = "not-a-number"
        
        order_id = await session_service.get_linked_order("rest_1", "sess_123")
        
        assert order_id is None

    @pytest.mark.asyncio
    async def test_collect_session_snapshot(self, session_service, mock_redis):
        """Test collecting session snapshot."""
        session_data = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "last_user_message": "أبغى برجر",
            "last_assistant_message": "تم، أضفت البرجر",
        }
        cart_data = {"items": [{"dish_id": 101}]}
        
        mock_redis.get.side_effect = [
            json.dumps(session_data),
            json.dumps(cart_data),
        ]
        
        snapshot = await session_service.collect_session_snapshot("rest_1", "sess_123")
        
        assert snapshot["restaurant_id"] == "rest_1"
        assert snapshot["session_id"] == "sess_123"
        assert snapshot["last_user_message"] == "أبغى برجر"
        assert snapshot["cart_snapshot"] == cart_data
        assert "disconnected_at" in snapshot

    @pytest.mark.asyncio
    async def test_collect_session_snapshot_no_data(self, session_service, mock_redis):
        """Test collecting session snapshot with no data."""
        mock_redis.get.return_value = None
        
        snapshot = await session_service.collect_session_snapshot("rest_1", "sess_123")
        
        assert snapshot["restaurant_id"] == "rest_1"
        assert snapshot["session_id"] == "sess_123"
        assert snapshot["last_user_message"] is None
        assert snapshot["cart_snapshot"] == {}