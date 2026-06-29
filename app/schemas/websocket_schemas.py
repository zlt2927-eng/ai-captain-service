"""WebSocket message schemas."""

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator


class MessageType(str, Enum):
    """WebSocket message types."""

    # Incoming
    text = "text"
    audio_chunk = "audio_chunk"
    audio_end = "audio_end"
    ping = "ping"

    # Outgoing
    assistant_text = "assistant_text"
    assistant_audio_chunk = "assistant_audio_chunk"
    cart_updated = "cart_updated"
    offer_applied = "offer_applied"
    error = "error"
    pong = "pong"


# Incoming message schemas


class TextMessage(BaseModel):
    """Incoming text message."""

    type: MessageType = Field(MessageType.text, literal=True)
    text: str = Field(..., description="User text input")

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        """Ensure text is not empty."""
        if not v or not v.strip():
            raise ValueError("Text cannot be empty")
        return v.strip()


class AudioChunkMessage(BaseModel):
    """Incoming audio chunk."""

    type: MessageType = Field(MessageType.audio_chunk, literal=True)
    audio_base64: str = Field(..., description="Base64-encoded audio bytes")
    mime_type: str = Field(default="audio/wav", description="MIME type of audio")
    sequence: int = Field(..., ge=0, description="Sequence number of chunk")

    @field_validator("audio_base64")
    @classmethod
    def audio_not_empty(cls, v: str) -> str:
        """Ensure audio data is not empty."""
        if not v or not v.strip():
            raise ValueError("Audio data cannot be empty")
        return v


class AudioEndMessage(BaseModel):
    """Audio transmission end marker."""

    type: MessageType = Field(MessageType.audio_end, literal=True)


class PingMessage(BaseModel):
    """WebSocket ping."""

    type: MessageType = Field(MessageType.ping, literal=True)


# Outgoing message schemas


class AssistantTextMessage(BaseModel):
    """Assistant text response."""

    type: MessageType = Field(MessageType.assistant_text, literal=True)
    text: str = Field(..., description="Assistant text response")


class AssistantAudioChunkMessage(BaseModel):
    """Assistant audio chunk."""

    type: MessageType = Field(MessageType.assistant_audio_chunk, literal=True)
    audio_base64: str = Field(..., description="Base64-encoded audio chunk")
    sequence: int = Field(..., ge=0, description="Sequence number of chunk")


class CartUpdatedMessage(BaseModel):
    """Cart update event."""

    type: MessageType = Field(MessageType.cart_updated, literal=True)
    payload: dict = Field(..., description="Cart update payload")


class OfferAppliedMessage(BaseModel):
    """Offer code applied event."""

    type: MessageType = Field(MessageType.offer_applied, literal=True)
    payload: dict = Field(..., description="Offer application details")


class ErrorMessage(BaseModel):
    """Error message."""

    type: MessageType = Field(MessageType.error, literal=True)
    message: str = Field(..., description="Error message")


class PongMessage(BaseModel):
    """WebSocket pong response."""

    type: MessageType = Field(MessageType.pong, literal=True)


# Union type for incoming messages
IncomingMessage = TextMessage | AudioChunkMessage | AudioEndMessage | PingMessage

# Union type for outgoing messages
OutgoingMessage = (
    AssistantTextMessage
    | AssistantAudioChunkMessage
    | CartUpdatedMessage
    | OfferAppliedMessage
    | ErrorMessage
    | PongMessage
)


# Helper constructors


def make_assistant_text(text: str) -> AssistantTextMessage:
    """Create assistant text message."""
    return AssistantTextMessage(text=text)


def make_assistant_audio_chunk(audio_base64: str, sequence: int) -> AssistantAudioChunkMessage:
    """Create assistant audio chunk message."""
    return AssistantAudioChunkMessage(audio_base64=audio_base64, sequence=sequence)


def make_cart_updated(payload: dict) -> CartUpdatedMessage:
    """Create cart updated message."""
    return CartUpdatedMessage(payload=payload)


def make_offer_applied(payload: dict) -> OfferAppliedMessage:
    """Create offer applied message."""
    return OfferAppliedMessage(payload=payload)


def make_error(message: str) -> ErrorMessage:
    """Create error message."""
    return ErrorMessage(message=message)


def make_pong() -> PongMessage:
    """Create pong message."""
    return PongMessage()