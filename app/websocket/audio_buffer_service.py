"""WebSocket audio buffer management with safety controls."""

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class AudioBufferState:
    """Tracks audio buffering state for a single turn."""
    
    buffer: bytearray = field(default_factory=bytearray)
    mime_type: str = "audio/wav"
    sequence: int = 0
    is_complete: bool = False
    size_bytes: int = 0
    
    def reset(self) -> None:
        """Reset buffer state for new turn."""
        self.buffer.clear()
        self.mime_type = "audio/wav"
        self.sequence = 0
        self.is_complete = False
        self.size_bytes = 0
    
    def append_chunk(self, chunk_bytes: bytes, mime_type: str, sequence: int) -> tuple[bool, Optional[str]]:
        """Append audio chunk to buffer.
        
        Returns:
            Tuple of (success, error_message)
        """
        # Validate sequence order
        if sequence != self.sequence:
            return False, f"Invalid audio sequence: expected {self.sequence}, got {sequence}"
        
        # Validate MIME type consistency
        if self.mime_type != "audio/wav" and self.mime_type != mime_type:
            return False, f"MIME type mismatch: buffer has {self.mime_type}, chunk has {mime_type}"
        
        self.mime_type = mime_type
        self.buffer.extend(chunk_bytes)
        self.size_bytes += len(chunk_bytes)
        self.sequence += 1
        
        return True, None
    
    def finalize(self) -> tuple[bool, Optional[str], bytes]:
        """Finalize audio buffer for transcription.
        
        Returns:
            Tuple of (success, error_message, audio_bytes)
        """
        if self.is_complete:
            return False, "Audio already finalized", b""
        
        if not self.buffer:
            return False, "No audio data to finalize", b""
        
        self.is_complete = True
        audio_bytes = bytes(self.buffer)
        return True, None, audio_bytes


class AudioBufferService:
    """Manage audio buffering per WebSocket connection.
    
    Ensures:
    - Size limits are enforced
    - Audio turns don't mix
    - Buffers are cleaned up properly
    """
    
    def __init__(self, settings: Settings):
        self._settings = settings
        self._buffers: dict[str, AudioBufferState] = {}
    
    def _get_buffer_key(self, connection_id: str) -> str:
        """Get Redis key for audio buffer metadata."""
        return f"audio_buffer:{connection_id}"
    
    def create_buffer(self, connection_id: str) -> AudioBufferState:
        """Create new audio buffer for connection.
        
        Args:
            connection_id: Unique connection identifier
            
        Returns:
            New AudioBufferState instance
        """
        if connection_id in self._buffers:
            self._buffers[connection_id].reset()
        else:
            self._buffers[connection_id] = AudioBufferState()
        
        logger.debug("Created audio buffer", extra={"connection_id": connection_id})
        return self._buffers[connection_id]
    
    def get_buffer(self, connection_id: str) -> Optional[AudioBufferState]:
        """Get existing audio buffer for connection."""
        return self._buffers.get(connection_id)
    
    def append_chunk(self, connection_id: str, chunk_bytes: bytes, 
                     mime_type: str, sequence: int) -> tuple[bool, Optional[str]]:
        """Append audio chunk to connection's buffer.
        
        Returns:
            Tuple of (success, error_message)
        """
        buffer = self.get_buffer(connection_id)
        if buffer is None:
            buffer = self.create_buffer(connection_id)
        
        # Check size limit
        if buffer.size_bytes + len(chunk_bytes) > self._settings.MAX_AUDIO_BUFFER_BYTES:
            logger.warning(
                "Audio buffer size limit exceeded",
                extra={
                    "connection_id": connection_id,
                    "current_size": buffer.size_bytes,
                    "chunk_size": len(chunk_bytes),
                    "limit": self._settings.MAX_AUDIO_BUFFER_BYTES,
                }
            )
            return False, f"Audio buffer exceeded maximum size of {self._settings.MAX_AUDIO_BUFFER_BYTES} bytes"
        
        return buffer.append_chunk(chunk_bytes, mime_type, sequence)
    
    def finalize_buffer(self, connection_id: str) -> tuple[bool, Optional[str], bytes]:
        """Finalize audio buffer for transcription.
        
        Returns:
            Tuple of (success, error_message, audio_bytes)
        """
        buffer = self.get_buffer(connection_id)
        if buffer is None:
            return False, "No audio buffer found", b""
        
        success, error_msg, audio_bytes = buffer.finalize()
        if not success:
            return False, error_msg, b""
        
        logger.info(
            "Audio buffer finalized",
            extra={
                "connection_id": connection_id,
                "size_bytes": len(audio_bytes),
                "mime_type": buffer.mime_type,
            }
        )
        
        return True, None, audio_bytes
    
    def cleanup(self, connection_id: str) -> None:
        """Clean up audio buffer for connection."""
        if connection_id in self._buffers:
            del self._buffers[connection_id]
            logger.debug("Cleaned up audio buffer", extra={"connection_id": connection_id})
    
    def get_mime_type(self, connection_id: str) -> Optional[str]:
        """Get MIME type for connection's audio buffer."""
        buffer = self.get_buffer(connection_id)
        return buffer.mime_type if buffer else None