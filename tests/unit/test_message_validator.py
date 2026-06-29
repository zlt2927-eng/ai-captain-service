"""Unit tests for WebSocket message validation - Phase 4."""

import pytest
from unittest.mock import MagicMock

from app.core.config import Settings
from app.websocket.message_validator import MessageValidator, MessageValidationError
from app.core.constants import WS_CLOSE_PAYLOAD_TOO_LARGE, WS_CLOSE_INVALID_DATA


class TestMessageValidator:
    """Test message validator functionality."""

    @pytest.fixture
    def test_settings(self):
        """Provide test settings with message validation limits."""
        settings = Settings()
        settings.MAX_MESSAGE_SIZE_BYTES = 1024  # 1KB
        settings.MAX_JSON_DEPTH = 10
        settings.MAX_TEXT_LENGTH = 100
        settings.MAX_AUDIO_CHUNK_SIZE_BYTES = 10000  # 10KB
        settings.MAX_AUDIO_TOTAL_SIZE_BYTES = 100000  # 100KB
        settings.MAX_AUDIO_CHUNKS = 10
        settings.ALLOWED_AUDIO_MIME_TYPES = ["audio/wav", "audio/mp3", "audio/ogg"]
        return settings

    @pytest.fixture
    def validator(self, test_settings):
        """Provide MessageValidator instance."""
        return MessageValidator(test_settings)

    def test_validate_message_size_success(self, validator):
        """Test message size validation passes for valid size."""
        validator.validate_message_size("small message")
        assert True

    def test_validate_message_size_exceeded(self, validator):
        """Test message size validation fails for oversized message."""
        large_message = "x" * 2000  # Exceeds 1KB limit
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_message_size(large_message)
        
        assert "exceeds limit" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_PAYLOAD_TOO_LARGE

    def test_validate_json_depth_success(self, validator):
        """Test JSON depth validation passes for valid depth."""
        valid_json = {"a": {"b": {"c": "value"}}}  # Depth 3
        validator.validate_json_depth(valid_json)
        assert True

    def test_validate_json_depth_exceeded(self, validator):
        """Test JSON depth validation fails for excessive depth."""
        # Create deeply nested JSON
        deep_json = {"level": 1}
        current = deep_json
        for i in range(2, 15):  # Exceed max depth of 10
            current["nested"] = {"level": i}
            current = current["nested"]
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_json_depth(deep_json)
        
        assert "depth exceeds" in exc_info.value.reason.lower()
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_text_length_success(self, validator):
        """Test text length validation passes for valid length."""
        validator.validate_text_length("Short text")
        assert True

    def test_validate_text_length_exceeded(self, validator):
        """Test text length validation fails for excessive length."""
        long_text = "x" * 200  # Exceeds 100 char limit
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_text_length(long_text)
        
        assert "exceeds limit" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_PAYLOAD_TOO_LARGE

    def test_validate_audio_chunk_success(self, validator):
        """Test audio chunk validation passes for valid chunk."""
        import base64
        audio_data = base64.b64encode(b"x" * 200).decode()  # 200 bytes, above minimum
        
        size, data = validator.validate_audio_chunk(
            audio_data,
            "audio/wav",
            0,
            0
        )
        
        assert size == 200
        assert data == b"x" * 200

    def test_validate_audio_chunk_invalid_mime_type(self, validator):
        """Test audio chunk validation fails for invalid MIME type."""
        import base64
        audio_data = base64.b64encode(b"audio data").decode()
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_audio_chunk(audio_data, "image/png", 0, 0)
        
        assert "Invalid MIME type" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_audio_chunk_size_exceeded(self, validator):
        """Test audio chunk validation fails for oversized chunk."""
        import base64
        # Create chunk larger than 10KB limit
        large_audio = base64.b64encode(b"x" * 20000).decode()
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_audio_chunk(large_audio, "audio/wav", 0, 0)
        
        assert "exceeds limit" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_PAYLOAD_TOO_LARGE

    def test_validate_audio_chunk_too_small(self, validator):
        """Test audio chunk validation fails for too small chunk."""
        import base64
        small_audio = base64.b64encode(b"ab").decode()  # Only 2 bytes
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_audio_chunk(small_audio, "audio/wav", 0, 0)
        
        assert "too small" in exc_info.value.reason.lower()
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_audio_chunk_invalid_sequence(self, validator):
        """Test audio chunk validation fails for negative sequence."""
        import base64
        audio_data = base64.b64encode(b"x" * 200).decode()  # 200 bytes, above minimum
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_audio_chunk(audio_data, "audio/wav", -1, 0)
        
        assert "Invalid sequence" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_audio_chunk_max_chunks_exceeded(self, validator):
        """Test audio chunk validation fails when max chunks exceeded."""
        import base64
        audio_data = base64.b64encode(b"x" * 200).decode()  # 200 bytes, above minimum
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_audio_chunk(audio_data, "audio/wav", 0, 10)  # Already at max
        
        assert "Maximum chunks" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_PAYLOAD_TOO_LARGE

    def test_validate_total_audio_size_success(self, validator):
        """Test total audio size validation passes."""
        validator.validate_total_audio_size(50000)  # Under 100KB limit
        assert True

    def test_validate_total_audio_size_exceeded(self, validator):
        """Test total audio size validation fails."""
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_total_audio_size(200000)  # Exceeds 100KB limit
        
        assert "exceeds limit" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_PAYLOAD_TOO_LARGE

    def test_validate_message_text_success(self, validator):
        """Test complete message validation for text."""
        message = '{"type": "text", "text": "Hello"}'
        result = validator.validate_message(message, "text")
        
        assert result["type"] == "text"
        assert result["text"] == "Hello"

    def test_validate_message_text_missing_field(self, validator):
        """Test message validation fails for missing text field."""
        message = '{"type": "text"}'
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_message(message, "text")
        
        assert "Missing" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_message_audio_chunk_success(self, validator):
        """Test complete message validation for audio chunk."""
        import base64
        audio_data = base64.b64encode(b"x" * 200).decode()  # 200 bytes, above minimum
        message = f'{{"type": "audio_chunk", "audio_base64": "{audio_data}", "mime_type": "audio/wav", "sequence": 0}}'
        
        result = validator.validate_message(message, "audio_chunk")
        
        assert result["type"] == "audio_chunk"
        assert result["sequence"] == 0

    def test_validate_message_audio_chunk_missing_field(self, validator):
        """Test message validation fails for missing audio field."""
        message = '{"type": "audio_chunk"}'
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_message(message, "audio_chunk")
        
        assert "Missing" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_message_invalid_json(self, validator):
        """Test message validation fails for invalid JSON."""
        message = "not valid json"
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_message(message, "text")
        
        assert "Invalid JSON" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_INVALID_DATA

    def test_validate_message_size_bytes(self, validator):
        """Test message size validation with bytes input."""
        validator.validate_message_size(b"small bytes")
        assert True

    def test_validate_message_size_bytes_exceeded(self, validator):
        """Test message size validation with bytes input exceeded."""
        large_bytes = b"x" * 2000
        
        with pytest.raises(MessageValidationError) as exc_info:
            validator.validate_message_size(large_bytes)
        
        assert "exceeds limit" in exc_info.value.reason
        assert exc_info.value.close_code == WS_CLOSE_PAYLOAD_TOO_LARGE