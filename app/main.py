"""FastAPI application entry point and lifecycle management."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

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
        app.state.stt_service = STTService(app.state.http_client, settings)
        app.state.tts_service = TTSService(app.state.http_client, settings)
        app.state.gemini_orchestrator = GeminiOrchestrator(settings, app.state.session_service, app.state.http_client)
        app.state.recovery_service = RecoveryService(settings, app.state.http_client, app.state.redis_client, app.state.session_service)

        logger.info("All services initialized successfully")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("Shutting down %s", settings.APP_NAME)

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
