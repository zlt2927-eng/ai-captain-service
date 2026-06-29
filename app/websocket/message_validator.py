"""WebSocket message validation - Phase 4 production hardening."""

import base64
import json
import logging
from typing import Optional, Tuple

from app.core.config import Settings
from app.core.constants import (
    WS_CLOSE_PAYLOAD_TOO_LARGE,
    WS_CLOSE_INVALID_DATA,
)
from pydantic import TypeAdapter, ValidationError

logger = logging.getLogger(__name__)


class MessageValidationError(Exception):
    """Raised when message validation fails."""
    
    def __init__(self, reason: str, close_code: int = WS_CLOSE_INVALID_DATA):
        self.reason = reason
        self.close_code = close_code
        super().__init__(reason)


class MessageValidator:
    """Validate WebSocket messages before processing.
    
    Implements:
    - Maximum message size
    - Maximum JSON depth
    - Maximum text length
    - Maximum audio size
    - Maximum audio chunk size
    - Maximum chunks
    - Invalid MIME types
    
    All limits are configurable through Settings.
    """
    
    def __init__(self, settings: Settings):
        self._settings = settings
    
    def validate_message_size(self, raw_data: str | bytes) -> None:
        """Validate message size is within limits.
        
        Args:
            raw_data: Raw message data
            
        Raises:
            MessageValidationError: If message exceeds size limit
        """
        size = len(raw_data) if isinstance(raw_data, bytes) else len(raw_data.encode('utf-8'))
        
        if size > self._settings.MAX_MESSAGE_SIZE_BYTES:
            raise MessageValidationError(
                f"Message size {size} bytes exceeds limit of {self._settings.MAX_MESSAGE_SIZE_BYTES} bytes",
                close_code=WS_CLOSE_PAYLOAD_TOO_LARGE
            )
    
    def validate_json_depth(self, data: dict, max_depth: int = 10) -> None:
        """Validate JSON structure depth.
        
        Args:
            data: Parsed JSON data
            max_depth: Maximum allowed depth
            
        Raises:
            MessageValidationError: If JSON exceeds depth limit
        """
        def _check_depth(obj: any, current_depth: int) -> int:
            if current_depth > max_depth:
                raise MessageValidationError(
                    f"JSON depth exceeds maximum of {max_depth}",
                    close_code=WS_CLOSE_INVALID_DATA
                )
            
            if isinstance(obj, dict):
                max_child_depth = current_depth
                for value in obj.values():
                    child_depth = _check_depth(value, current_depth + 1)
                    max_child_depth = max(max_child_depth, child_depth)
                return max_child_depth
            elif isinstance(obj, list):
                max_child_depth = current_depth
                for item in obj:
                    child_depth = _check_depth(item, current_depth + 1)
                    max_child_depth = max(max_child_depth, child_depth)
                return max_child_depth
            else:
                return current_depth
        
        _check_depth(data, 0)
    
    def validate_text_length(self, text: str) -> None:
        """Validate text message length.
        
        Args:
            text: Text content
            
        Raises:
            MessageValidationError: If text exceeds length limit
        """
        if len(text) > self._settings.MAX_TEXT_LENGTH:
            raise MessageValidationError(
                f"Text length {len(text)} exceeds limit of {self._settings.MAX_TEXT_LENGTH}",
                close_code=WS_CLOSE_PAYLOAD_TOO_LARGE
            )
    
    def validate_audio_chunk(
        self,
        audio_base64: str,
        mime_type: str,
        sequence: int,
        chunk_count: int
    ) -> Tuple[int, bytes]:
        """Validate audio chunk message.
        
        Args:
            audio_base64: Base64-encoded audio data
            mime_type: MIME type of audio
            sequence: Chunk sequence number
            chunk_count: Total chunks received so far
            
        Returns:
            Tuple of (decoded_size, audio_bytes)
            
        Raises:
            MessageValidationError: If validation fails
        """
        # Validate MIME type
        if mime_type not in self._settings.ALLOWED_AUDIO_MIME_TYPES:
            raise MessageValidationError(
                f"Invalid MIME type: {mime_type}. Allowed: {', '.join(self._settings.ALLOWED_AUDIO_MIME_TYPES)}",
                close_code=WS_CLOSE_INVALID_DATA
            )
        
        # Decode base64
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as exc:
            raise MessageValidationError(
                f"Invalid base64 encoding: {exc}",
                close_code=WS_CLOSE_INVALID_DATA
            )
        
        # Validate chunk size
        chunk_size = len(audio_bytes)
        if chunk_size > self._settings.MAX_AUDIO_CHUNK_SIZE_BYTES:
            raise MessageValidationError(
                f"Audio chunk size {chunk_size} bytes exceeds limit of {self._settings.MAX_AUDIO_CHUNK_SIZE_BYTES} bytes",
                close_code=WS_CLOSE_PAYLOAD_TOO_LARGE
            )
        
        # Validate minimum chunk size
        if chunk_size < 100:  # MIN_AUDIO_CHUNK_BYTES
            raise MessageValidationError(
                f"Audio chunk too small: {chunk_size} bytes",
                close_code=WS_CLOSE_INVALID_DATA
            )
        
        # Validate sequence
        if sequence < 0:
            raise MessageValidationError(
                f"Invalid sequence number: {sequence}",
                close_code=WS_CLOSE_INVALID_DATA
            )
        
        # Validate maximum chunks
        if chunk_count >= self._settings.MAX_AUDIO_CHUNKS:
            raise MessageValidationError(
                f"Maximum chunks ({self._settings.MAX_AUDIO_CHUNKS}) exceeded",
                close_code=WS_CLOSE_PAYLOAD_TOO_LARGE
            )
        
        return chunk_size, audio_bytes
    
    def validate_total_audio_size(self, total_size: int) -> None:
        """Validate total audio size across all chunks.
        
        Args:
            total_size: Total size in bytes
            
        Raises:
            MessageValidationError: If total size exceeds limit
        """
        if total_size > self._settings.MAX_AUDIO_TOTAL_SIZE_BYTES:
            raise MessageValidationError(
                f"Total audio size {total_size} bytes exceeds limit of {self._settings.MAX_AUDIO_TOTAL_SIZE_BYTES} bytes",
                close_code=WS_CLOSE_PAYLOAD_TOO_LARGE
            )
    
    def validate_message(
        self,
        raw_data: str,
        message_type: str,
        chunk_count: int = 0
    ) -> dict:
        """Validate complete WebSocket message.
        
        Args:
            raw_data: Raw message string
            message_type: Type of message
            chunk_count: Number of chunks received so far (for audio)
            
        Returns:
            Parsed message data
            
        Raises:
            MessageValidationError: If validation fails
        """
        # Validate message size
        self.validate_message_size(raw_data)
        
        # Parse JSON
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise MessageValidationError(
                f"Invalid JSON: {exc}",
                close_code=WS_CLOSE_INVALID_DATA
            )
        
        # Validate JSON depth
        if isinstance(data, dict):
            self.validate_json_depth(data)
        
        # Type-specific validation
        if message_type == "text":
            if "text" not in data:
                raise MessageValidationError(
                    "Missing 'text' field",
                    close_code=WS_CLOSE_INVALID_DATA
                )
            self.validate_text_length(data["text"])
        
        elif message_type == "audio_chunk":
            if "audio_base64" not in data:
                raise MessageValidationError(
                    "Missing 'audio_base64' field",
                    close_code=WS_CLOSE_INVALID_DATA
                )
            if "mime_type" not in data:
                raise MessageValidationError(
                    "Missing 'mime_type' field",
                    close_code=WS_CLOSE_INVALID_DATA
                )
            if "sequence" not in data:
                raise MessageValidationError(
                    "Missing 'sequence' field",
                    close_code=WS_CLOSE_INVALID_DATA
                )
            
            self.validate_audio_chunk(
                data["audio_base64"],
                data["mime_type"],
                data["sequence"],
                chunk_count
            )
        
        return data