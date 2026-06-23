"""Per-session serialized turn processing with correlation IDs."""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from app.websocket.connection_context import ConnectionContext
from app.schemas.websocket_schemas import IncomingMessage

logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """Result of processing a conversation turn."""
    
    turn_id: str
    success: bool
    response_messages: list[dict]
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0


class TurnProcessor:
    """Process conversation turns with per-session serialization.
    
    Ensures:
    - Only one turn processes at a time per session
    - Each turn has a unique correlation ID
    - Processing is timeout-protected
    - Results are consistently structured
    """
    
    def __init__(self, connection_context: ConnectionContext):
        self._ctx = connection_context
        self._processing_lock = asyncio.Lock()
        self._turn_timeout_seconds = 30.0  # Configurable via settings if needed
    
    async def process_turn(self, message: IncomingMessage) -> TurnResult:
        """Process a single conversation turn.
        
        This method ensures serialized turn processing per session.
        If another turn is already processing, this will wait for it to complete.
        
        Args:
            message: Validated incoming WebSocket message
            
        Returns:
            TurnResult with processing outcome
        """
        # Generate turn ID for correlation
        turn_id = self._ctx.generate_turn_id()
        start_time = time.perf_counter()
        
        log_ctx = {
            "turn_id": turn_id,
            "message_type": message.type.value,
            "restaurant_id": self._ctx.restaurant_id,
            "session_id": self._ctx.session_id,
        }
        
        logger.info("Processing turn", extra=log_ctx)
        
        # Acquire per-session lock to serialize turns
        async with self._processing_lock:
            self._ctx.is_processing = True
            
            try:
                # Set timeout for turn processing
                result = await asyncio.wait_for(
                    self._execute_turn(turn_id, message),
                    timeout=self._turn_timeout_seconds
                )
                
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                result.processing_time_ms = processing_time_ms
                
                logger.info(
                    "Turn completed",
                    extra={
                        **log_ctx,
                        "success": result.success,
                        "processing_time_ms": round(processing_time_ms, 2),
                        "response_count": len(result.response_messages),
                    }
                )
                
                return result
                
            except asyncio.TimeoutError:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    "Turn processing timeout",
                    extra={**log_ctx, "processing_time_ms": round(processing_time_ms, 2)}
                )
                return TurnResult(
                    turn_id=turn_id,
                    success=False,
                    response_messages=[],
                    error_message="Processing timeout - please try again",
                    processing_time_ms=processing_time_ms,
                )
            except Exception as exc:
                processing_time_ms = (time.perf_counter() - start_time) * 1000
                logger.exception(
                    "Turn processing failed",
                    extra={**log_ctx, "processing_time_ms": round(processing_time_ms, 2)}
                )
                return TurnResult(
                    turn_id=turn_id,
                    success=False,
                    response_messages=[],
                    error_message=f"Processing error: {str(exc)}",
                    processing_time_ms=processing_time_ms,
                )
            finally:
                self._ctx.is_processing = False
                self._ctx.current_turn_id = None
    
    async def _execute_turn(self, turn_id: str, message: IncomingMessage) -> TurnResult:
        """Execute the actual turn processing logic.
        
        This is separated to allow timeout wrapping.
        Subclasses or composition can override this for different message types.
        """
        # This is a base implementation - actual processing is delegated
        # to specialized handlers based on message type
        raise NotImplementedError("Turn processing must be implemented by subclass or composition")