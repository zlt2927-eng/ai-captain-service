"""FastAPI application entry point and lifecycle management - Phase 2 hardened."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.websocket_endpoints import router as websocket_router
from app.core.config import get_settings
from app.core.logging import LogContext, setup_logging
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.redis_client import RedisClient
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.recovery_service import RecoveryService
from app.services.session_service import SessionService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="AI Digital Captain - Restaurant ordering microservice",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(websocket_router)
    app.state.settings = settings
    app.state.ready = False

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        """Health check endpoint - always returns ok if service is running."""
        return {"status": "ok", "service": settings.APP_NAME}

    @app.get("/ready", tags=["health"])
    async def ready() -> dict:
        """Readiness check endpoint - verifies all dependencies are available."""
        if not getattr(app.state, "ready", False):
            return {"ready": False, "reason": "Service not initialized"}

        redis_client = getattr(app.state, "redis_client", None)
        if not redis_client or not await redis_client.is_connected():
            return {"ready": False, "reason": "Redis not available"}

        if not getattr(app.state, "http_client", None):
            return {"ready": False, "reason": "HTTP client not available"}

        if not getattr(app.state, "gemini_orchestrator", None):
            return {"ready": False, "reason": "Orchestrator not initialized"}

        if settings.ENABLE_STT and not getattr(app.state, "stt_service", None):
            return {"ready": False, "reason": "STT service not initialized"}

        if settings.ENABLE_TTS and not getattr(app.state, "tts_service", None):
            return {"ready": False, "reason": "TTS service not initialized"}

        if settings.ENABLE_TELEGRAM_BOT and not getattr(app.state, "telegram_integration", None):
            return {"ready": False, "reason": "Telegram integration not initialized"}

        return {"ready": True, "service": settings.APP_NAME}

    return app


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown."""
    settings = app.state.settings
    setup_logging(settings.LOG_LEVEL, settings.APP_NAME)
    log_ctx = LogContext(logger, "system", "startup")
    log_ctx.info("Starting %s", settings.APP_NAME)

    # Initialize core infrastructure
    app.state.redis_client = RedisClient(settings)
    await app.state.redis_client.connect()
    log_ctx.info("Redis client connected")

    app.state.http_client = HTTPClient(settings)
    await app.state.http_client.startup()
    log_ctx.info("HTTP client initialized")

    # Initialize core services
    app.state.session_service = SessionService(app.state.redis_client, settings.SESSION_TTL_SECONDS)
    log_ctx.info("Session service initialized")

    # Pass redis_client to orchestrator for menu caching
    app.state.gemini_orchestrator = GeminiOrchestrator(
        settings, 
        app.state.session_service, 
        app.state.http_client,
        app.state.redis_client  # Pass Redis for menu caching
    )
    log_ctx.info("Gemini orchestrator initialized")

    # Initialize optional services based on feature flags
    app.state.stt_service = STTService(app.state.http_client, settings) if settings.ENABLE_STT else None
    if app.state.stt_service:
        log_ctx.info("STT service initialized")

    app.state.tts_service = TTSService(app.state.http_client, settings) if settings.ENABLE_TTS else None
    if app.state.tts_service:
        log_ctx.info("TTS service initialized")

    app.state.recovery_service = RecoveryService(
        settings, app.state.http_client, app.state.redis_client, app.state.session_service
    ) if settings.ENABLE_RECOVERY else None
    if app.state.recovery_service:
        log_ctx.info("Recovery service initialized")

    # Initialize optional integrations
    telegram_integration = None
    if settings.ENABLE_TELEGRAM_BOT:
        try:
            from app.integrations.telegram.service import TelegramIntegration
            
            telegram_integration = TelegramIntegration(
                settings=settings,
                http_client=app.state.http_client,
                session_service=app.state.session_service,
                gemini_orchestrator=app.state.gemini_orchestrator,
            )
            await telegram_integration.start()
            app.state.telegram_integration = telegram_integration
            log_ctx.info("Telegram integration started")
        except Exception:
            log_ctx.exception("Telegram integration failed to start")
            if settings.ENABLE_TELEGRAM_STRICT:
                raise
            log_ctx.warning("Continuing startup without Telegram integration")

    app.state.ready = True
    log_ctx.info("All core services initialized successfully")

    try:
        yield
    finally:
        log_ctx.info("Shutting down %s", settings.APP_NAME)
        app.state.ready = False

        # Shutdown optional integrations
        if getattr(app.state, "telegram_integration", None):
            try:
                await app.state.telegram_integration.shutdown()
                log_ctx.info("Telegram integration shutdown complete")
            except Exception:
                log_ctx.exception("Error during Telegram integration shutdown")

        # Shutdown core services
        if getattr(app.state, "http_client", None):
            await app.state.http_client.shutdown()
            log_ctx.info("HTTP client shutdown complete")

        if getattr(app.state, "redis_client", None):
            await app.state.redis_client.disconnect()
            log_ctx.info("Redis client disconnected")

        log_ctx.info("%s shutdown complete", settings.APP_NAME)


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