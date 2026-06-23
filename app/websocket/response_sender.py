"""WebSocket response sending with structured messages."""

import base64
import logging
from typing import Optional

from fastapi import WebSocket

from app.schemas.websocket_schemas import (
    make_assistant_audio_chunk,
    make_assistant_text,
    make_cart_updated,
    make_error,
    make_pong,
)

logger = logging.getLogger(__name__)


class ResponseSender:
    """Send structured WebSocket responses.
    
    Provides type-safe methods for sending all WebSocket message types
    with consistent logging and error handling.
    """
    
    def __init__(self, websocket: WebSocket, connection_id: str):
        self._websocket = websocket
        self._connection_id = connection_id
    
    async def send_text(self, text: str) -> None:
        """Send assistant text response."""
        await self._websocket.send_text(make_assistant_text(text).model_dump_json())
        logger.debug(
            "Sent assistant text",
            extra={"connection_id": self._connection_id, "text_length": len(text)}
        )
    
    async def send_audio_chunk(self, audio_base64: str, sequence: int) -> None:
        """Send audio chunk for TTS streaming."""
        await self._websocket.send_text(
            make_assistant_audio_chunk(audio_base64, sequence).model_dump_json()
        )
        logger.debug(
            "Sent audio chunk",
            extra={"connection_id": self._connection_id, "sequence": sequence}
        )
    
    async def send_cart_update(self, payload: dict) -> None:
        """Send cart update event."""
        await self._websocket.send_text(make_cart_updated(payload).model_dump_json())
        logger.debug(
            "Sent cart update",
            extra={"connection_id": self._connection_id}
        )
    
    async def send_error(self, message: str) -> None:
        """Send error message."""
        await self._websocket.send_text(make_error(message).model_dump_json())
        logger.warning(
            "Sent error to client",
            extra={"connection_id": self._connection_id, "error": message}
        )
    
    async def send_pong(self) -> None:
        """Send pong response."""
        await self._websocket.send_text(make_pong().model_dump_json())
        logger.debug("Sent pong", extra={"connection_id": self._connection_id})
    
    async def send_raw(self, message: str) -> None:
        """Send raw JSON message."""
        await self._websocket.send_text(message)
        logger.debug(
            "Sent raw message",
            extra={"connection_id": self._connection_id, "message_length": len(message)}
        )