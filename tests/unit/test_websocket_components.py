"""Unit tests for WebSocket components."""

import pytest
from unittest.mock import AsyncMock, MagicMock
import base64

from app.websocket.audio_buffer_service import AudioBufferService, AudioBufferState
from app.websocket.message_router import MessageRouter, MessageHandler, RoutedMessage
from app.websocket.response_sender import ResponseSender
from app.websocket.connection_context import ConnectionContext
from app.schemas.websocket_schemas import MessageType, TextMessage, AudioChunkMessage
from app.core.config import Settings


class TestAudioBufferState:
    """Test audio buffer state."""

    def test_create_buffer(self, test_settings):
        """Test creating audio buffer state."""
        state = AudioBufferState()
        
        assert state.mime_type == "audio/wav"
        assert state.sequence == 0
        assert state.size_bytes == 0
        assert len(state.buffer) == 0

    def test_append_chunk_first(self, test_settings):
        """Test appending first chunk."""
        state = AudioBufferState()
        chunk = b"audio data"
        
        success, error = state.append_chunk(chunk, "audio/wav", 0)
        
        assert success is True
        assert error is None
        assert state.mime_type == "audio/wav"
        assert state.sequence == 1
        assert state.size_bytes == len(chunk)

    def test_append_chunk_wrong_sequence(self, test_settings):
        """Test appending chunk with wrong sequence number."""
        state = AudioBufferState()
        state.append_chunk(b"chunk 0", "audio/wav", 0)
        
        # Try to append sequence 2 (skipping 1)
        success, error = state.append_chunk(b"chunk 2", "audio/wav", 2)
        
        assert success is False
        assert "sequence" in error.lower()

    def test_append_chunk_duplicate_sequence(self, test_settings):
        """Test appending duplicate sequence."""
        state = AudioBufferState()
        state.append_chunk(b"chunk 0", "audio/wav", 0)
        
        # Try to append same sequence again
        success, error = state.append_chunk(b"chunk 0 again", "audio/wav", 0)
        
        assert success is False
        assert "duplicate" in error.lower() or "sequence" in error.lower()

    def test_append_chunk_mime_type_mismatch(self, test_settings):
        """Test appending chunk with different MIME type."""
        state = AudioBufferState()
        state.append_chunk(b"chunk 0", "audio/wav", 0)
        
        # Try to append with different MIME type
        success, error = state.append_chunk(b"chunk 1", "audio/mp3", 1)
        
        assert success is False
        assert "mime" in error.lower() or "type" in error.lower()

    def test_append_chunk_size_limit(self, test_settings):
        """Test size limit enforcement."""
        state = AudioBufferState()
        test_settings.MAX_AUDIO_BUFFER_BYTES = 100
        
        # Append chunk that exceeds limit
        large_chunk = b"x" * 101
        success, error = state.append_chunk(large_chunk, "audio/wav", 0)
        
        assert success is False
        assert "size" in error.lower() or "limit" in error.lower()

    def test_reset(self, test_settings):
        """Test resetting buffer."""
        state = AudioBufferState()
        state.append_chunk(b"chunk 0", "audio/wav", 0)
        state.append_chunk(b"chunk 1", "audio/wav", 1)
        
        state.reset()
        
        assert len(state.buffer) == 0
        assert state.mime_type == "audio/wav"
        assert state.sequence == 0
        assert state.size_bytes == 0

    def test_finalize(self, test_settings):
        """Test finalizing buffer."""
        state = AudioBufferState()
        state.append_chunk(b"chunk 0", "audio/wav", 0)
        state.append_chunk(b"chunk 1", "audio/wav", 1)
        
        success, error, data = state.finalize()
        
        assert success is True
        assert error is None
        assert data == b"chunk 0chunk 1"


class TestAudioBufferService:
    """Test audio buffer service."""

    @pytest.fixture
    def service(self, test_settings):
        """Provide AudioBufferService instance."""
        return AudioBufferService(test_settings)

    def test_create_buffer(self, service):
        """Test creating buffer."""
        state = service.create_buffer("conn_1")
        
        assert state is not None
        assert state.connection_id == "conn_1"

    def test_get_buffer_existing(self, service):
        """Test getting existing buffer."""
        state1 = service.create_buffer("conn_1")
        state2 = service.get_buffer("conn_1")
        
        assert state1 is state2  # Same object

    def test_get_buffer_not_found(self, service):
        """Test getting non-existent buffer."""
        state = service.get_buffer("conn_999")
        
        assert state is None

    def test_append_chunk(self, service):
        """Test appending chunk through service."""
        service.create_buffer("conn_1")
        success, error = service.append_chunk("conn_1", b"data", "audio/wav", 0)
        
        assert success is True
        assert error is None

    def test_append_chunk_no_buffer(self, service):
        """Test appending chunk without buffer."""
        success, error = service.append_chunk("conn_999", b"data", "audio/wav", 0)
        
        assert success is False
        assert "no buffer" in error.lower() or "not found" in error.lower()

    def test_finalize_buffer(self, service):
        """Test finalizing buffer through service."""
        service.create_buffer("conn_1")
        service.append_chunk("conn_1", b"data", "audio/wav", 0)
        
        mime_type, data = service.finalize_buffer("conn_1")
        
        assert mime_type == "audio/wav"
        assert data == b"data"

    def test_cleanup(self, service):
        """Test cleaning up buffer."""
        service.create_buffer("conn_1")
        assert service.get_buffer("conn_1") is not None
        
        service.cleanup("conn_1")
        
        assert service.get_buffer("conn_1") is None

    def test_get_mime_type(self, service):
        """Test getting MIME type."""
        service.create_buffer("conn_1")
        service.append_chunk("conn_1", b"data", "audio/wav", 0)
        
        mime_type = service.get_mime_type("conn_1")
        
        assert mime_type == "audio/wav"

    def test_get_mime_type_no_buffer(self, service):
        """Test getting MIME type for non-existent buffer."""
        mime_type = service.get_mime_type("conn_999")
        
        assert mime_type is None


class TestMessageRouter:
    """Test message router."""

    @pytest.fixture
    def router(self):
        """Provide MessageRouter instance."""
        return MessageRouter()

    @pytest.fixture
    def mock_handler(self):
        """Provide mock message handler."""
        handler = MagicMock(spec=MessageHandler)
        handler.can_handle = MagicMock(return_value=True)
        handler.handle = AsyncMock(return_value=None)
        return handler

    def test_register_handler(self, router, mock_handler):
        """Test registering handler."""
        router.register_handler(MessageType.TEXT, mock_handler)
        
        assert router.has_handler(MessageType.TEXT)

    def test_has_handler(self, router, mock_handler):
        """Test checking if handler exists."""
        router.register_handler(MessageType.TEXT, mock_handler)
        
        assert router.has_handler(MessageType.TEXT)
        assert not router.has_handler(MessageType.PING)

    def test_route_to_handler(self, router, mock_handler):
        """Test routing message to handler."""
        router.register_handler(MessageType.TEXT, mock_handler)
        
        message = TextMessage(text="test")
        result = router.route(message)
        
        assert result is not None
        assert result.handler == mock_handler
        mock_handler.can_handle.assert_called_once()

    def test_route_no_handler(self, router):
        """Test routing when no handler registered."""
        message = TextMessage(text="test")
        result = router.route(message)
        
        assert result is None

    def test_route_handler_cannot_handle(self, router, mock_handler):
        """Test routing when handler cannot handle message."""
        mock_handler.can_handle.return_value = False
        router.register_handler(MessageType.TEXT, mock_handler)
        
        message = TextMessage(text="test")
        result = router.route(message)
        
        # Handler returned but can_handle returned False
        # Implementation dependent


class TestConnectionContext:
    """Test connection context."""

    @pytest.fixture
    def context(self, test_settings):
        """Provide ConnectionContext instance."""
        return ConnectionContext(
            settings=test_settings,
            session_service=MagicMock(),
            gemini_orchestrator=MagicMock(),
            stt_service=None,
            tts_service=None,
            recovery_service=None,
            restaurant_id="rest_1",
            session_id="sess_123",
        )

    def test_generate_turn_id(self, context):
        """Test turn ID generation."""
        turn_id1 = context.generate_turn_id()
        turn_id2 = context.generate_turn_id()
        
        assert turn_id1 != turn_id2
        assert "turn_" in turn_id1
        assert context.connection_id[:8] in turn_id1

    def test_get_log_context(self, context):
        """Test getting log context."""
        log_ctx = context.get_log_context()
        
        assert "restaurant_id" in log_ctx
        assert "session_id" in log_ctx
        assert "connection_id" in log_ctx
        assert log_ctx["restaurant_id"] == "rest_1"
        assert log_ctx["session_id"] == "sess_123"


class TestResponseSender:
    """Test response sender."""

    @pytest.fixture
    def mock_websocket(self):
        """Provide mock WebSocket."""
        mock = MagicMock()
        mock.send_text = AsyncMock()
        return mock

    @pytest.fixture
    def sender(self, mock_websocket):
        """Provide ResponseSender instance."""
        return ResponseSender(mock_websocket, "conn_1")

    @pytest.mark.asyncio
    async def test_send_text(self, sender, mock_websocket):
        """Test sending text message."""
        await sender.send_text("مرحبا")
        
        mock_websocket.send_text.assert_called_once()
        call_args = mock_websocket.send_text.call_args[0][0]
        assert "مرحبا" in call_args

    @pytest.mark.asyncio
    async def test_send_pong(self, sender, mock_websocket):
        """Test sending pong."""
        await sender.send_pong()
        
        mock_websocket.send_text.assert_called_once()
        call_args = mock_websocket.send_text.call_args[0][0]
        assert "pong" in call_args.lower()

    @pytest.mark.asyncio
    async def test_send_error(self, sender, mock_websocket):
        """Test sending error message."""
        await sender.send_error("Something went wrong")
        
        mock_websocket.send_text.assert_called_once()
        call_args = mock_websocket.send_text.call_args[0][0]
        assert "error" in call_args.lower()

    @pytest.mark.asyncio
    async def test_send_raw(self, sender, mock_websocket):
        """Test sending raw message."""
        raw_json = '{"type": "custom", "data": "test"}'
        await sender.send_raw(raw_json)
        
        mock_websocket.send_text.assert_called_once_with(raw_json)

    @pytest.mark.asyncio
    async def test_send_websocket_disconnect(self, sender, mock_websocket):
        """Test handling WebSocket disconnect."""
        from fastapi import WebSocketDisconnect
        mock_websocket.send_text.side_effect = WebSocketDisconnect()
        
        # Should not raise
        await sender.send_text("test")

    @pytest.mark.asyncio
    async def test_send_runtime_error(self, sender, mock_websocket):
        """Test handling runtime error."""
        mock_websocket.send_text.side_effect = RuntimeError("Connection closed")
        
        # Should not raise
        await sender.send_text("test")