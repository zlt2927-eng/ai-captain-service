"""WebSocket endpoints for real-time conversation - hardened runtime."""

import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.constants import WS_CLOSE_UNAUTHORIZED
from app.core.logging import LogContext
from app.websocket.auth import WebSocketAuth, AuthResult
from app.websocket.connection_context import ConnectionContext
from app.websocket.audio_buffer_service import AudioBufferService
from app.websocket.message_router import MessageRouter
from app.websocket.handlers import (
    PingHandler,
    TextMessageHandler,
    AudioChunkHandler,
    AudioEndHandler,
)
from app.schemas.websocket_schemas import IncomingMessage, make_error

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/captain/{restaurant_id}/{session_id}")
async def websocket_captain(
    websocket: WebSocket,
    restaurant_id: str,
    session_id: str,
    token: str = Query(...),
) -> None:
    """Hardened WebSocket endpoint for AI Captain conversations.
    
    This endpoint now delegates to specialized services:
    - Authentication via WebSocketAuth
    - Connection context management
    - Message routing via MessageRouter
    - Specialized handlers per message type
    """
    # Get runtime services from app state
    settings, session_service, stt_service, tts_service, gemini_orchestrator, recovery_service = \
        _get_runtime_services(websocket)
    
    # Authenticate connection
    auth = WebSocketAuth(settings)
    auth_result = await auth.authenticate(websocket, token, restaurant_id, session_id)
    
    if not auth_result.success:
        await auth.close_unauthorized(websocket, auth_result)
        return
    
    # Accept connection
    await websocket.accept()
    
    # Create connection context
    ctx = ConnectionContext(
        settings=settings,
        session_service=session_service,
        gemini_orchestrator=gemini_orchestrator,
        stt_service=stt_service,
        tts_service=tts_service,
        recovery_service=recovery_service,
        restaurant_id=restaurant_id,
        session_id=session_id,
    )
    
    log_ctx = LogContext(logger, restaurant_id, session_id)
    log_ctx.info("WebSocket connection accepted", extra={"connection_id": ctx.connection_id})
    
    # Initialize services for this connection
    audio_buffer_service = AudioBufferService(settings)
    response_sender = ResponseSender(websocket, ctx.connection_id)
    
    # Create message router and register handlers
    router = MessageRouter()
    router.register_handler(
        MessageType.ping,
        PingHandler(response_sender)
    )
    router.register_handler(
        MessageType.text,
        TextMessageHandler(
            ctx,
            response_sender,
            gemini_orchestrator,
            session_service,
            tts_service,
        )
    )
    router.register_handler(
        MessageType.audio_chunk,
        AudioChunkHandler(ctx, audio_buffer_service, response_sender)
    )
    router.register_handler(
        MessageType.audio_end,
        AudioEndHandler(
            ctx,
            audio_buffer_service,
            response_sender,
            gemini_orchestrator,
            session_service,
            stt_service,
            tts_service,
        )
    )
    
    # Cancel any pending recovery for this session
    await recovery_service.cancel_recovery(restaurant_id, session_id)
    await session_service.mark_session_active(restaurant_id, session_id)
    
    try:
        # Main message loop
        while True:
            raw_text = await websocket.receive_text()
            
            try:
                message = IncomingMessage.model_validate(json.loads(raw_text))
            except Exception:
                log_ctx.warning("Invalid websocket payload")
                await response_sender.send_error("Invalid message format")
                continue
            
            # Route message to appropriate handler
            routed = await router.route(message)
            if routed is None:
                await response_sender.send_error("Unsupported message type")
                continue
            
            # Handle message
            try:
                await routed.handler.handle(routed.message)
            except Exception as exc:
                log_ctx.error("Message handler failed", exc_info=True)
                await response_sender.send_error("Processing failed")
    
    except WebSocketDisconnect:
        log_ctx.info("WebSocket disconnected")
    except Exception:
        log_ctx.error("WebSocket unexpected error", exc_info=True)
    finally:
        # Cleanup
        audio_buffer_service.cleanup(ctx.connection_id)
        await _handle_disconnect(restaurant_id, session_id, session_service, recovery_service, log_ctx)


def _get_runtime_services(websocket: WebSocket):
    """Extract runtime services from FastAPI app state."""
    state = websocket.app.state
    return (
        state.settings,
        state.session_service,
        state.stt_service,
        state.tts_service,
        state.gemini_orchestrator,
        state.recovery_service,
    )


async def _handle_disconnect(
    restaurant_id: str,
    session_id: str,
    session_service,
    recovery_service,
    log_ctx: LogContext,
) -> None:
    """Handle WebSocket disconnect and schedule recovery."""
    try:
        await session_service.mark_session_inactive(restaurant_id, session_id)
        await recovery_service.schedule_recovery(restaurant_id, session_id)
        log_ctx.info("Session cleanup and recovery scheduled")
    except Exception:
        log_ctx.error("Disconnect handling failed", exc_info=True)


# Import at bottom to avoid circular imports
from app.websocket.response_sender import ResponseSender  # noqa: E402