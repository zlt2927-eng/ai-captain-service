"""FastAPI application entry point and lifecycle management."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Telegram integration is optional; initialize lazily during startup
from app.api.websocket_endpoints import router as websocket_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.redis_client import RedisClient
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.recovery_service import RecoveryService
from app.services.session_service import SessionService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)


def create_app(settings=None) -> FastAPI:
    """Create FastAPI application.

    Accept an optional `settings` object for tests to inject a controlled
    configuration without relying on environment variables.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="AI Digital Captain - Restaurant ordering microservice",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(websocket_router)

    @app.on_event("startup")
    async def startup() -> None:
        setup_logging(settings.LOG_LEVEL, settings.APP_NAME)
        logger.info("Starting %s", settings.APP_NAME)

        app.state.settings = settings
        app.state.redis_client = RedisClient(settings)
        await app.state.redis_client.connect()

        app.state.http_client = HTTPClient(settings)
        await app.state.http_client.startup()

        app.state.session_service = SessionService(app.state.redis_client, settings.SESSION_TTL_SECONDS)
        # Optional services
        if settings.ENABLE_STT:
            app.state.stt_service = STTService(app.state.http_client, settings)
        else:
            app.state.stt_service = None

        if settings.ENABLE_TTS:
            app.state.tts_service = TTSService(app.state.http_client, settings)
        else:
            app.state.tts_service = None
        app.state.gemini_orchestrator = GeminiOrchestrator(settings, app.state.session_service, app.state.http_client)
        app.state.recovery_service = RecoveryService(settings, app.state.http_client, app.state.redis_client, app.state.session_service)

        # Initialize optional Telegram bot without failing startup
        app.state.telegram_app = None
        if settings.ENABLE_TELEGRAM:
            try:
                from app.api.telegram_bot import initialize_telegram_bot

                app.state.telegram_app = await initialize_telegram_bot(app)
            except Exception:
                logger.exception("Failed to initialize Telegram bot; continuing without it")

        logger.info("All services initialized successfully")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("Shutting down %s", settings.APP_NAME)

        if getattr(app.state, "telegram_app", None):
            try:
                from app.api.telegram_bot import shutdown_telegram_bot

                await shutdown_telegram_bot(app.state.telegram_app)
            except Exception:
                logger.exception("Error shutting down Telegram bot")

        if getattr(app.state, "recovery_service", None):
            try:
                await app.state.recovery_service.shutdown()
            except Exception:
                logger.exception("Error shutting down recovery service")

        if getattr(app.state, "http_client", None):
            await app.state.http_client.shutdown()

        if getattr(app.state, "redis_client", None):
            await app.state.redis_client.disconnect()

        logger.info("%s shutdown complete", settings.APP_NAME)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": settings.APP_NAME}

    @app.get("/ready", tags=["health"])
    async def ready() -> dict:
        redis_client = getattr(app.state, "redis_client", None)
        if not redis_client or not await redis_client.is_connected():
            return {"ready": False, "reason": "Redis not available"}
        return {"ready": True, "service": settings.APP_NAME}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
