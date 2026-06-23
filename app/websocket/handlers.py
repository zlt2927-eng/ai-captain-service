"""WebSocket message handlers for different message types."""

import base64
import logging
from typing import Optional

from app.websocket.connection_context import ConnectionContext
from app.websocket.audio_buffer_service import AudioBufferService
from app.websocket.response_sender import ResponseSender
from app.schemas.websocket_schemas import IncomingMessage, MessageType
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.session_service import SessionService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class PingHandler:
    """Handle ping messages."""
    
    def __init__(self, response_sender: ResponseSender):
        self._sender = response_sender
    
    async def handle(self, message: IncomingMessage) -> None:
        """Send pong response."""
        await self._sender.send_pong()


class TextMessageHandler:
    """Handle text messages from user."""
    
    def __init__(
        self,
        connection_context: ConnectionContext,
        response_sender: ResponseSender,
        gemini_orchestrator: GeminiOrchestrator,
        session_service: SessionService,
        tts_service: Optional[TTSService],
    ):
        self._ctx = connection_context
        self._sender = response_sender
        self._orchestrator = gemini_orchestrator
        self._session_service = session_service
        self._tts_service = tts_service
    
    async def handle(self, message: IncomingMessage) -> None:
        """Process text message through Gemini orchestrator."""
        if message.type != MessageType.text:
            return
        
        text_message = message
        user_text = text_message.text.strip()
        
        if not user_text:
            await self._sender.send_error("Empty message")
            return
        
        log_ctx = self._ctx.get_log_context()
        logger.info("Processing text message", extra={**log_ctx, "text_length": len(user_text)})
        
        try:
            # Process through orchestrator
            result = await self._orchestrator.process_user_message(
                restaurant_id=self._ctx.restaurant_id,
                session_id=self._ctx.session_id,
                user_message=user_text,
            )
            
            assistant_text = (result.get("assistant_text") or "").strip()
            if not assistant_text:
                assistant_text = "عذراً، لم أفهم طلبك. هل يمكنك إعادة صياغته؟"
            
            # Send text response
            await self._sender.send_text(assistant_text)
            
            # Send cart updates if any
            cart_events = result.get("cart_events", [])
            cart_snapshot = result.get("cart_snapshot")
            
            if cart_snapshot is not None:
                await self._session_service.save_cart_snapshot(
                    self._ctx.restaurant_id,
                    self._ctx.session_id,
                    cart_snapshot,
                )
            
            for cart_event in cart_events:
                await self._sender.send_cart_update(cart_event)
                logger.info("Sent cart event", extra=log_ctx)
            
            # Stream TTS if available
            if self._tts_service:
                await self._stream_tts(assistant_text)
            
        except Exception as exc:
            logger.exception("Text message processing failed", extra=log_ctx)
            await self._sender.send_error("Processing failed")
    
    async def _stream_tts(self, text: str) -> None:
        """Stream TTS audio for response text."""
        try:
            sequence = 0
            async for chunk in self._tts_service.stream_tts_audio(text):
                if not chunk:
                    continue
                import base64
                encoded = base64.b64encode(chunk).decode("utf-8")
                await self._sender.send_audio_chunk(encoded, sequence)
                sequence += 1
            logger.debug("TTS stream completed", extra=self._ctx.get_log_context())
        except Exception as exc:
            logger.error("TTS streaming failed", exc_info=exc, extra=self._ctx.get_log_context())


class AudioChunkHandler:
    """Handle incoming audio chunks."""
    
    def __init__(
        self,
        connection_context: ConnectionContext,
        audio_buffer_service: AudioBufferService,
        response_sender: ResponseSender,
    ):
        self._ctx = connection_context
        self._audio_buffer = audio_buffer_service
        self._sender = response_sender
    
    async def handle(self, message: IncomingMessage) -> None:
        """Buffer audio chunk for later transcription."""
        if message.type != MessageType.audio_chunk:
            return
        
        try:
            chunk_bytes = base64.b64decode(message.audio_base64)
        except Exception:
            await self._sender.send_error("Invalid audio chunk")
            return
        
        if message.mime_type not in {"audio/wav", "audio/webm"}:
            await self._sender.send_error("Unsupported audio mime_type")
            return
        
        success, error_msg = self._audio_buffer.append_chunk(
            self._ctx.connection_id,
            chunk_bytes,
            message.mime_type,
            message.sequence,
        )
        
        if not success:
            await self._sender.send_error(error_msg)
            logger.warning(
                "Audio chunk rejected",
                extra={**self._ctx.get_log_context(), "error": error_msg}
            )


class AudioEndHandler:
    """Handle end of audio transmission."""
    
    def __init__(
        self,
        connection_context: ConnectionContext,
        audio_buffer_service: AudioBufferService,
        response_sender: ResponseSender,
        gemini_orchestrator: GeminiOrchestrator,
        session_service: SessionService,
        stt_service: STTService,
        tts_service: Optional[TTSService],
    ):
        self._ctx = connection_context
        self._audio_buffer = audio_buffer_service
        self._sender = response_sender
        self._orchestrator = gemini_orchestrator
        self._session_service = session_service
        self._stt_service = stt_service
        self._tts_service = tts_service
    
    async def handle(self, message: IncomingMessage) -> None:
        """Finalize audio buffer and process transcription."""
        if message.type != MessageType.audio_end:
            return
        
        log_ctx = self._ctx.get_log_context()
        logger.info("Finalizing audio buffer", extra=log_ctx)
        
        # Finalize buffer
        success, error_msg, audio_bytes = self._audio_buffer.finalize_buffer(
            self._ctx.connection_id
        )
        
        if not success:
            await self._sender.send_error(error_msg or "No audio to transcribe")
            logger.warning("Audio finalization failed", extra={**log_ctx, "error": error_msg})
            return
        
        try:
            # Transcribe audio
            mime_type = self._audio_buffer.get_mime_type(self._ctx.connection_id)
            transcript = await self._stt_service.transcribe_audio(audio_bytes, mime_type or "audio/wav")
            logger.info("Transcription complete", extra={**log_ctx, "transcript_length": len(transcript)})
            
            # Process as text message
            text_handler = TextMessageHandler(
                self._ctx,
                self._sender,
                self._orchestrator,
                self._session_service,
                self._tts_service,
            )
            await text_handler.handle(
                IncomingMessage(type=MessageType.text, text=transcript)
            )
            
        except Exception as exc:
            logger.exception("Audio processing failed", extra=log_ctx)
            await self._sender.send_error("Audio processing failed")
        finally:
            # Clean up buffer
            self._audio_buffer.cleanup(self._ctx.connection_id)