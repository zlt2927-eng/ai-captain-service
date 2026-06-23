"""WebSocket endpoints for real-time conversation."""

import base64
import json
import logging

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.constants import WS_CLOSE_UNAUTHORIZED
from app.core.logging import LogContext
from app.schemas.websocket_schemas import (
    IncomingMessage,
    make_assistant_audio_chunk,
    make_assistant_text,
    make_cart_updated,
    make_error,
    make_pong,
)
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.recovery_service import RecoveryService
from app.services.session_service import SessionService
from app.services.stt_service import STTService, STTServiceError
from app.services.tts_service import TTSService, TTSServiceError

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_runtime_services(websocket: WebSocket):
    state = websocket.app.state
    required = [
        "settings",
        "redis_client",
        "http_client",
        "session_service",
        "stt_service",
        "tts_service",
        "gemini_orchestrator",
        "recovery_service",
    ]
    missing = [name for name in required if not hasattr(state, name)]
    if missing:
        raise RuntimeError(f"App state missing required services: {missing}")

    return (
        state.settings,
        state.session_service,
        state.stt_service,
        state.tts_service,
        state.gemini_orchestrator,
        state.recovery_service,
    )


@router.websocket("/ws/captain/{restaurant_id}/{session_id}")
async def websocket_captain(
    websocket: WebSocket,
    restaurant_id: str,
    session_id: str,
    token: str = Query(...),
) -> None:
    settings, session_service, stt_service, tts_service, gemini_orchestrator, recovery_service = _get_runtime_services(websocket)
    log_ctx = LogContext(logger, restaurant_id, session_id)

    try:
        try:
            payload = jwt.decode(
                token,
                settings.WEBSOCKET_AUTH_SECRET,
                algorithms=[settings.WEBSOCKET_AUTH_ALGORITHM],
            )
            if payload.get("restaurant_id") != restaurant_id or payload.get("session_id") != session_id:
                log_ctx.error("Token payload mismatch")
                await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Invalid token payload")
                return
        except jwt.ExpiredSignatureError:
            log_ctx.error("WebSocket token expired")
            await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Token expired")
            return
        except jwt.InvalidTokenError:
            log_ctx.error("WebSocket token invalid")
            await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="Invalid token")
            return

        await websocket.accept()
        log_ctx.info("WebSocket connection accepted")

        await recovery_service.cancel_recovery(restaurant_id, session_id)
        await session_service.mark_session_active(restaurant_id, session_id)

        audio_buffer = bytearray()
        audio_mime_type = "audio/wav"

        while True:
            raw_text = await websocket.receive_text()
            try:
                message = IncomingMessage.model_validate(json.loads(raw_text))
            except Exception:
                log_ctx.warning("Invalid websocket payload")
                await websocket.send_text(make_error("Invalid message format").model_dump_json())
                continue

            if message.type == "ping":
                await websocket.send_text(make_pong().model_dump_json())
                continue

            if message.type == "text":
                await _handle_text_message(
                    websocket,
                    log_ctx,
                    restaurant_id,
                    session_id,
                    message.text,
                    gemini_orchestrator,
                    session_service,
                    tts_service,
                )
                continue

            if message.type == "audio_chunk":
                try:
                    chunk_bytes = base64.b64decode(message.audio_base64)
                except Exception:
                    await websocket.send_text(make_error("Invalid audio chunk").model_dump_json())
                    continue

                if message.mime_type not in {"audio/wav", "audio/webm"}:
                    await websocket.send_text(make_error("Unsupported audio mime_type").model_dump_json())
                    continue

                audio_buffer.extend(chunk_bytes)
                audio_mime_type = message.mime_type

                if len(audio_buffer) > settings.MAX_AUDIO_BUFFER_BYTES:
                    log_ctx.warning("Audio buffer exceeded maximum size")
                    await websocket.send_text(make_error("Audio buffer exceeded maximum size").model_dump_json())
                    audio_buffer.clear()
                continue

            if message.type == "audio_end":
                if not audio_buffer:
                    await websocket.send_text(make_error("No audio to transcribe").model_dump_json())
                    continue

                await _handle_audio_end_message(
                    websocket,
                    log_ctx,
                    restaurant_id,
                    session_id,
                    bytes(audio_buffer),
                    audio_mime_type,
                    gemini_orchestrator,
                    session_service,
                    stt_service,
                    tts_service,
                )
                audio_buffer.clear()
                audio_mime_type = "audio/wav"
                continue

            await websocket.send_text(make_error("Unsupported message type").model_dump_json())

    except WebSocketDisconnect:
        log_ctx.info("WebSocket disconnected")
        await _handle_disconnect(restaurant_id, session_id, session_service, recovery_service, log_ctx)
    except Exception:
        log_ctx.error("WebSocket unexpected error", exc_info=True)
        await _handle_disconnect(restaurant_id, session_id, session_service, recovery_service, log_ctx)


async def _handle_text_message(
    websocket: WebSocket,
    log_ctx: LogContext,
    restaurant_id: str,
    session_id: str,
    user_text: str,
    gemini_orchestrator: GeminiOrchestrator,
    session_service: SessionService,
    tts_service: TTSService,
) -> None:
    log_ctx.info("Text message received")

    try:
        result = await gemini_orchestrator.process_user_message(restaurant_id, session_id, user_text)
        assistant_text = (result.get("assistant_text") or "").strip()
        if not assistant_text:
            assistant_text = "عذراً، لم أفهم طلبك. هل يمكنك إعادة صياغته؟"

        await websocket.send_text(make_assistant_text(assistant_text).model_dump_json())
        log_ctx.info("Sent assistant text")

        cart_events = result.get("cart_events", [])
        cart_snapshot = result.get("cart_snapshot")
        if cart_snapshot is not None:
            await session_service.save_cart_snapshot(restaurant_id, session_id, cart_snapshot)

        for cart_event in cart_events:
            await websocket.send_text(make_cart_updated(cart_event).model_dump_json())
            log_ctx.info("Sent cart event")

        await _stream_tts_response(websocket, assistant_text, tts_service)
    except Exception:
        log_ctx.error("Text handler failed", exc_info=True)
        await websocket.send_text(make_error("Processing failed").model_dump_json())


async def _handle_audio_end_message(
    websocket: WebSocket,
    log_ctx: LogContext,
    restaurant_id: str,
    session_id: str,
    audio_bytes: bytes,
    mime_type: str,
    gemini_orchestrator: GeminiOrchestrator,
    session_service: SessionService,
    stt_service: STTService,
    tts_service: TTSService,
) -> None:
    log_ctx.info("Received full audio buffer")

    try:
        transcript = await stt_service.transcribe_audio(audio_bytes, mime_type)
        log_ctx.info("Transcription complete")
        await _handle_text_message(
            websocket,
            log_ctx,
            restaurant_id,
            session_id,
            transcript,
            gemini_orchestrator,
            session_service,
            tts_service,
        )
    except STTServiceError:
        log_ctx.error("Transcription failed", exc_info=True)
        await websocket.send_text(make_error("Transcription failed").model_dump_json())
    except Exception:
        log_ctx.error("Audio processing failed", exc_info=True)
        await websocket.send_text(make_error("Audio processing failed").model_dump_json())


async def _stream_tts_response(websocket: WebSocket, text: str, tts_service: TTSService) -> None:
    try:
        sequence = 0
        async for chunk in tts_service.stream_tts_audio(text):
            if not chunk:
                continue
            encoded = base64.b64encode(chunk).decode("utf-8")
            await websocket.send_text(make_assistant_audio_chunk(encoded, sequence).model_dump_json())
            sequence += 1
        logger.info("Completed TTS stream")
    except TTSServiceError:
        logger.error("TTS stream failed", exc_info=True)
        await websocket.send_text(make_error("Audio generation failed").model_dump_json())


async def _handle_disconnect(
    restaurant_id: str,
    session_id: str,
    session_service: SessionService,
    recovery_service: RecoveryService,
    log_ctx: LogContext,
) -> None:
    """Handle WebSocket disconnect and schedule recovery."""
    try:
        await session_service.mark_session_inactive(restaurant_id, session_id)
        await recovery_service.schedule_recovery(restaurant_id, session_id)
        log_ctx.info("Session cleanup and recovery scheduled")
    except Exception:
        log_ctx.error("Disconnect handling failed", exc_info=True)
