"""Speech-to-Text service using Groq Whisper."""

import logging
from typing import Optional

from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient, HTTPClientError

logger = logging.getLogger(__name__)


class STTServiceError(Exception):
    pass


class STTService:
    """Groq Whisper Large V3 transcription service."""

    SUPPORTED_MIME_TYPES = {
        "audio/wav",
        "audio/webm",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/flac",
    }

    def __init__(self, http_client: HTTPClient, settings: Settings):
        self._http_client = http_client
        self._settings = settings
        self._url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        if not audio_bytes:
            raise STTServiceError("Audio bytes cannot be empty")

        if len(audio_bytes) > self._settings.MAX_AUDIO_BUFFER_BYTES:
            raise STTServiceError("Audio payload exceeds maximum allowed size")

        if mime_type not in self.SUPPORTED_MIME_TYPES:
            raise STTServiceError(f"Unsupported audio mime_type: {mime_type}")

        headers = {"Authorization": f"Bearer {self._settings.GROQ_API_KEY}"}
        files = {"file": (f"audio.{self._get_file_extension(mime_type)}", audio_bytes, mime_type)}

        try:
            response = await self._http_client.request("POST", self._url, headers=headers, files=files)
            if response.status_code != 200:
                logger.error("Groq STT non-200 response: %s %s", response.status_code, response.text)
                raise STTServiceError("Speech transcription failed")

            result = response.json()
            transcript = (result.get("transcript") or result.get("text") or "").strip()
            if not transcript:
                raise STTServiceError("Speech transcription returned empty text")

            logger.info("STT transcribed %s bytes", len(audio_bytes))
            return transcript
        except HTTPClientError as exc:
            logger.error("STT request failed", exc_info=True)
            raise STTServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error("STT error", exc_info=True)
            raise STTServiceError(str(exc)) from exc

    def _get_file_extension(self, mime_type: str) -> str:
        return {
            "audio/wav": "wav",
            "audio/webm": "webm",
            "audio/mpeg": "mp3",
            "audio/mp3": "mp3",
            "audio/ogg": "ogg",
            "audio/flac": "flac",
        }.get(mime_type, "wav")
