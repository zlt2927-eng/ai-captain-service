"""WebSocket runtime package for AI Captain service.

This package provides hardened WebSocket handling with:
- Per-session serialized turn processing
- Turn correlation IDs and observability
- Safe audio buffering
- Connection context management
"""

__all__ = [
    "ConnectionContext",
    "AuthResult",
    "MessageRouter",
    "AudioBufferService",
    "TurnProcessor",
    "ResponseSender",
]