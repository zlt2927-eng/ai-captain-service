"""WebSocket message routing and dispatch."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.schemas.websocket_schemas import IncomingMessage, MessageType

logger = logging.getLogger(__name__)


class MessageHandler:
    """Base class for message handlers."""
    
    async def handle(self, message: IncomingMessage) -> None:
        """Handle incoming message. Override in subclasses."""
        raise NotImplementedError


@dataclass
class RoutedMessage:
    """Result of message routing."""
    
    handler: MessageHandler
    message: IncomingMessage


class MessageRouter:
    """Route incoming WebSocket messages to appropriate handlers.
    
    Provides:
    - Type-based message routing
    - Validation and error handling
    - Extensible handler registration
    """
    
    def __init__(self):
        self._handlers: dict[MessageType, MessageHandler] = {}
    
    def register_handler(self, message_type: MessageType, handler: MessageHandler) -> None:
        """Register a handler for a specific message type.
        
        Args:
            message_type: WebSocket message type
            handler: Handler instance to process this message type
        """
        self._handlers[message_type] = handler
        logger.debug(
            "Registered handler for message type",
            extra={"message_type": message_type.value}
        )
    
    async def route(self, message: IncomingMessage) -> Optional[RoutedMessage]:
        """Route message to appropriate handler.
        
        Args:
            message: Validated incoming message
            
        Returns:
            RoutedMessage with handler and message, or None if no handler found
        """
        handler = self._handlers.get(message.type)
        if handler is None:
            logger.warning(
                "No handler registered for message type",
                extra={"message_type": message.type.value}
            )
            return None
        
        logger.debug(
            "Routed message to handler",
            extra={"message_type": message.type.value}
        )
        
        return RoutedMessage(handler=handler, message=message)