"""Text-to-Speech service using ElevenLabs."""

import logging
from typing import AsyncIterator

from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient, HTTPClientError

logger = logging.getLogger(__name__)


class TTSServiceError(Exception):
    pass


class TTSService:
    """ElevenLabs streaming text-to-speech service."""

    def __init__(self, http_client: HTTPClient, settings: Settings):
        self._http_client = http_client
        self._settings = settings
        self._base_url = "https://api.elevenlabs.io/v1"

    async def stream_tts_audio(self, text: str) -> AsyncIterator[bytes]:
        if not text or not text.strip():
            raise TTSServiceError("Text cannot be empty")

        url = f"{self._base_url}/text-to-speech/{self._settings.ELEVENLABS_VOICE_ID}/stream"
        headers = {
            "xi-api-key": self._settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": self._settings.ELEVENLABS_MODEL_ID,
        }

        try:
            async for chunk in self._http_client.stream("POST", url, headers=headers, json_data=payload):
                if chunk:
                    yield chunk
        except HTTPClientError as exc:
            logger.error("TTS request failed", exc_info=True)
            raise TTSServiceError(str(exc)) from exc
        except Exception as exc:
            logger.error("TTS streaming error", exc_info=True)
            raise TTSServiceError(str(exc)) from exc
