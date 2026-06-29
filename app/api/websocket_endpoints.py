"""WebSocket endpoints for real-time conversation - hardened runtime."""

import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.constants import WS_CLOSE_UNAUTHORIZED, WS_CLOSE_RATE_LIMIT
from app.core.logging import LogContext
from app.websocket.auth import WebSocketAuth, AuthResult
from app.websocket.connection_context import ConnectionContext
from app.websocket.audio_buffer_service import AudioBufferService
from app.websocket.message_router import MessageRouter
from app.websocket.message_validator import MessageValidator, MessageValidationError
from app.websocket.rate_limiter import RateLimiter, RateLimitResult
from app.websocket.security import WebSocketSecurity
from app.websocket.handlers import (
    PingHandler,
    TextMessageHandler,
    AudioChunkHandler,
    AudioEndHandler,
)
from app.schemas.websocket_schemas import IncomingMessage, MessageType, make_error
from pydantic import TypeAdapter, ValidationError

# TypeAdapter for validating incoming WebSocket messages (union of Pydantic models)
_incoming_message_adapter = TypeAdapter(IncomingMessage)

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
    - Rate limiting (per IP, per session, per WebSocket)
    - Message validation
    - Security hardening
    """
    # Get runtime services from app state
    settings, session_service, stt_service, tts_service, gemini_orchestrator, recovery_service, redis_client = \
        _get_runtime_services(websocket)
    
    # Get client IP address
    client_ip = _get_client_ip(websocket)
    
    # Initialize security, rate limiter, and message validator
    security = WebSocketSecurity(redis_client, settings)
    rate_limiter = RateLimiter(redis_client, settings)
    message_validator = MessageValidator(settings)
    
    # Phase 14: Security - Validate request origin
    origin = websocket.headers.get("origin")
    security_result = security.validate_request_origin(origin)
    if not security_result.valid:
        await websocket.close(
            code=security_result.close_code,
            reason=security_result.reason
        )
        return
    
    # Phase 14: Security - Check connection anomaly
    connection_fingerprint = security.compute_connection_fingerprint(websocket)
    security_result = await security.check_connection_anomaly("pending", connection_fingerprint)
    if not security_result.valid:
        await websocket.close(
            code=security_result.close_code,
            reason=security_result.reason
        )
        return
    
    # Phase 3: Rate limiting - Check IP limit
    rate_result = await rate_limiter.check_ip_limit(client_ip)
    if not rate_result.allowed:
        await websocket.close(
            code=WS_CLOSE_RATE_LIMIT,
            reason=f"Rate limit exceeded. Try again in {int(rate_result.reset_time - __import__('time').time())} seconds"
        )
        return
    
    # Phase 3: Rate limiting - Check session limit
    rate_result = await rate_limiter.check_session_limit(restaurant_id, session_id)
    if not rate_result.allowed:
        await websocket.close(
            code=WS_CLOSE_RATE_LIMIT,
            reason=f"Session rate limit exceeded. Try again in {int(rate_result.reset_time - __import__('time').time())} seconds"
        )
        return
    
    # Phase 14: Security - Enhanced JWT validation
    security_result = await security.validate_jwt_token(token)
    if not security_result.valid:
        await websocket.close(
            code=security_result.close_code,
            reason=security_result.reason
        )
        return
    
    # Phase 14: Security - Check session token revocation
    if settings.ENABLE_TOKEN_REVOCATION:
        revoked = await security.is_session_token_revoked(restaurant_id, session_id)
        if revoked:
            await websocket.close(
                code=WS_CLOSE_UNAUTHORIZED,
                reason="Session tokens have been revoked"
            )
            return
    
    # Authenticate connection (legacy validation for restaurant_id/session_id)
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
            
            # Phase 3: Rate limiting - Check WebSocket message limit
            rate_result = await rate_limiter.check_websocket_limit(ctx.connection_id)
            if not rate_result.allowed:
                log_ctx.warning("WebSocket rate limit exceeded")
                await response_sender.send_error(
                    f"Message rate limit exceeded. Try again in {int(rate_result.reset_time - __import__('time').time())} seconds"
                )
                continue
            
            # Phase 4: Message validation - Validate message before processing
            try:
                message_type = _extract_message_type(raw_text)
                message_validator.validate_message(raw_text, message_type or "unknown")
            except MessageValidationError as exc:
                log_ctx.warning(
                    "Message validation failed",
                    extra={"reason": exc.reason, "close_code": exc.close_code}
                )
                await websocket.close(code=exc.close_code, reason=exc.reason)
                return
            
            try:
                message = _incoming_message_adapter.validate_python(json.loads(raw_text))
            except ValidationError as exc:
                log_ctx.warning("Invalid websocket payload", extra={"errors": exc.errors()})
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
        state.redis_client,
    )


def _get_client_ip(websocket: WebSocket) -> str:
    """Extract client IP address from WebSocket connection.
    
    Args:
        websocket: WebSocket connection
        
    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (for proxies/load balancers)
    forwarded_for = websocket.headers.get("x-forwarded-for")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = websocket.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct client address
    if websocket.client:
        return websocket.client.host
    
    return "unknown"


def _extract_message_type(raw_text: str) -> Optional[str]:
    """Extract message type from raw JSON.
    
    Args:
        raw_text: Raw message JSON string
        
    Returns:
        Message type or None
    """
    try:
        data = json.loads(raw_text)
        return data.get("type")
    except (json.JSONDecodeError, AttributeError):
        return None


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