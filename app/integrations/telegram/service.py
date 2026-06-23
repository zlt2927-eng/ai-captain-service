"""Telegram integration service that manages bot lifecycle."""

import logging
from typing import Optional

from fastapi import FastAPI
from telegram import Application

from app.api.telegram_bot import create_telegram_application
from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)


class TelegramIntegration:
    """Optional Telegram bot integration for the AI Captain service."""

    def __init__(
        self,
        settings: Settings,
        http_client: HTTPClient,
        session_service: SessionService,
        gemini_orchestrator: GeminiOrchestrator,
    ) -> None:
        self._settings = settings
        self._http_client = http_client
        self._session_service = session_service
        self._gemini_orchestrator = gemini_orchestrator
        self._application: Optional[Application] = None

    async def start(self) -> Application:
        self._application = create_telegram_application(self._settings)
        self._application.bot_data["settings"] = self._settings
        self._application.bot_data["http_client"] = self._http_client
        self._application.bot_data["session_service"] = self._session_service
        self._application.bot_data["gemini_orchestrator"] = self._gemini_orchestrator

        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling()

        logger.info("Telegram bot polling started")
        return self._application

    async def shutdown(self) -> None:
        if not self._application:
            return

        await self._application.updater.stop_polling()
        await self._application.stop()
        await self._application.shutdown()
        logger.info("Telegram bot polling stopped")
