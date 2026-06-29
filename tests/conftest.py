"""Test configuration and shared fixtures."""

import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.redis_client import RedisClient
from app.services.session_service import SessionService
from app.services.gemini_orchestrator import GeminiOrchestrator
from app.services.cart_backend_gateway import CartBackendGateway
from app.services.tool_execution_coordinator import ToolExecutionCoordinator
from app.services.recovery_service import RecoveryService
from app.services.stt_service import STTService
from app.services.tts_service import TTSService
from app.services.prompt_builder import PromptBuilder
from app.services.menu_context_provider import MockMenuContextProvider
from app.websocket.auth import WebSocketAuth
from app.websocket.audio_buffer_service import AudioBufferService
from app.websocket.message_router import MessageRouter
from app.websocket.response_sender import ResponseSender
from app.schemas.websocket_schemas import (
    TextMessage,
    AudioChunkMessage,
    AudioEndMessage,
    PingMessage,
    MessageType,
)
from app.schemas.cart_schemas import CartAction, CartAddonSelection, CartUpdatePayload


# -----------------------------------------------------------------------------
# Environment Configuration
# -----------------------------------------------------------------------------

os.environ["APP_ENV"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["WEBSOCKET_AUTH_SECRET"] = "test-secret-key-for-testing-only"
os.environ["LARAVEL_BACKEND_URL"] = "http://localhost:8001"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # Use DB 1 for tests


# -----------------------------------------------------------------------------
# Event Loop
# -----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# -----------------------------------------------------------------------------
# Settings
# -----------------------------------------------------------------------------

@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings."""
    return Settings()


# -----------------------------------------------------------------------------
# Redis Client (using fakeredis)
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Provide mock Redis client."""
    mock_redis = MagicMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.exists = AsyncMock(return_value=0)
    mock_redis.rpush = AsyncMock(return_value=1)
    mock_redis.lrange = AsyncMock(return_value=[])
    mock_redis.eval = AsyncMock(return_value=1)
    mock_redis.pipeline = MagicMock()
    
    # Mock pipeline
    mock_pipe = MagicMock()
    mock_pipe.setex = AsyncMock(return_value=None)
    mock_pipe.execute = AsyncMock(return_value=[True, True])
    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)
    mock_redis.pipeline.return_value = mock_pipe
    
    return mock_redis


@pytest.fixture
def redis_client(mock_redis_client: MagicMock) -> RedisClient:
    """Provide RedisClient with mocked connection."""
    client = RedisClient(Settings())
    client._client = mock_redis_client
    return client


# -----------------------------------------------------------------------------
# HTTP Client
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_http_client() -> MagicMock:
    """Provide mock HTTP client."""
    mock_client = MagicMock(spec=HTTPClient)
    mock_client.request = AsyncMock()
    mock_client.post_json = AsyncMock()
    mock_client.get_json = AsyncMock()
    mock_client.stream = AsyncMock()
    return mock_client


@pytest.fixture
def http_client(mock_http_client: MagicMock, test_settings: Settings) -> HTTPClient:
    """Provide HTTPClient with mocked transport."""
    client = HTTPClient(test_settings)
    # Mock the internal client
    client._client = MagicMock()
    return client


# -----------------------------------------------------------------------------
# Services
# -----------------------------------------------------------------------------

@pytest.fixture
def session_service(redis_client: RedisClient, test_settings: Settings) -> SessionService:
    """Provide SessionService with mocked Redis."""
    return SessionService(redis_client, test_settings.SESSION_TTL_SECONDS)


@pytest.fixture
def cart_backend_gateway(mock_http_client: MagicMock, test_settings: Settings) -> CartBackendGateway:
    """Provide CartBackendGateway with mocked HTTP client."""
    return CartBackendGateway(mock_http_client, test_settings)


@pytest.fixture
def tool_coordinator(cart_backend_gateway: CartBackendGateway) -> ToolExecutionCoordinator:
    """Provide ToolExecutionCoordinator with cart gateway."""
    coordinator = ToolExecutionCoordinator(cart_backend_gateway)
    # Register test tools
    coordinator.register_tool("update_cart", lambda **kwargs: {"success": True})
    return coordinator


@pytest.fixture
def prompt_builder() -> PromptBuilder:
    """Provide PromptBuilder instance."""
    return PromptBuilder()


@pytest.fixture
def menu_context_provider() -> MockMenuContextProvider:
    """Provide MockMenuContextProvider."""
    return MockMenuContextProvider()


@pytest.fixture
def gemini_orchestrator(
    test_settings: Settings,
    session_service: SessionService,
    mock_http_client: MagicMock,
    redis_client: RedisClient,
) -> GeminiOrchestrator:
    """Provide GeminiOrchestrator with mocked dependencies."""
    with patch("app.services.gemini_orchestrator.genai") as mock_genai:
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.configure = MagicMock()
        
        orchestrator = GeminiOrchestrator(
            test_settings,
            session_service,
            mock_http_client,
            redis_client,
        )
        return orchestrator


@pytest.fixture
def recovery_service(
    test_settings: Settings,
    mock_http_client: MagicMock,
    redis_client: RedisClient,
    session_service: SessionService,
) -> RecoveryService:
    """Provide RecoveryService with mocked dependencies."""
    return RecoveryService(test_settings, mock_http_client, redis_client, session_service)


@pytest.fixture
def stt_service(mock_http_client: MagicMock, test_settings: Settings) -> STTService:
    """Provide STTService with mocked HTTP client."""
    return STTService(mock_http_client, test_settings)


@pytest.fixture
def tts_service(mock_http_client: MagicMock, test_settings: Settings) -> TTSService:
    """Provide TTSService with mocked HTTP client."""
    return TTSService(mock_http_client, test_settings)


# -----------------------------------------------------------------------------
# WebSocket Components
# -----------------------------------------------------------------------------

@pytest.fixture
def websocket_auth(test_settings: Settings) -> WebSocketAuth:
    """Provide WebSocketAuth instance."""
    return WebSocketAuth(test_settings)


@pytest.fixture
def audio_buffer_service(test_settings: Settings) -> AudioBufferService:
    """Provide AudioBufferService instance."""
    return AudioBufferService(test_settings)


@pytest.fixture
def message_router() -> MessageRouter:
    """Provide MessageRouter instance."""
    return MessageRouter()


@pytest.fixture
def response_sender() -> MagicMock:
    """Provide mock ResponseSender."""
    mock_sender = MagicMock(spec=ResponseSender)
    mock_sender.send_text = AsyncMock()
    mock_sender.send_audio_chunk = AsyncMock()
    mock_sender.send_cart_update = AsyncMock()
    mock_sender.send_error = AsyncMock()
    mock_sender.send_pong = AsyncMock()
    mock_sender.send_raw = AsyncMock()
    return mock_sender


# -----------------------------------------------------------------------------
# Test Data
# -----------------------------------------------------------------------------

@pytest.fixture
def sample_restaurant_id() -> str:
    """Provide sample restaurant ID."""
    return "rest_1"


@pytest.fixture
def sample_session_id() -> str:
    """Provide sample session ID."""
    return "sess_123"


@pytest.fixture
def sample_turn_id() -> str:
    """Provide sample turn ID."""
    return "turn_abc123"


@pytest.fixture
def sample_jwt_token() -> str:
    """Provide sample JWT token for testing."""
    import jwt
    import time
    
    payload = {
        "restaurant_id": "rest_1",
        "session_id": "sess_123",
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, "test-secret-key-for-testing-only", algorithm="HS256")


@pytest.fixture
def sample_text_message() -> TextMessage:
    """Provide sample text message."""
    return TextMessage(text="أبغى برجر لحم")


@pytest.fixture
def sample_audio_chunk_message() -> AudioChunkMessage:
    """Provide sample audio chunk message."""
    return AudioChunkMessage(
        audio_base64="SGVsbG8gV29ybGQ=",  # "Hello World" in base64
        mime_type="audio/wav",
        sequence=0,
    )


@pytest.fixture
def sample_cart_addon() -> CartAddonSelection:
    """Provide sample cart addon."""
    return CartAddonSelection(addon_id=501, quantity=1)


@pytest.fixture
def sample_cart_update_payload(
    sample_restaurant_id: str,
    sample_session_id: str,
    sample_turn_id: str,
) -> CartUpdatePayload:
    """Provide sample cart update payload."""
    return CartUpdatePayload(
        restaurant_id=sample_restaurant_id,
        session_id=sample_session_id,
        action=CartAction.add,
        dish_id=101,
        quantity=2,
        notes="بدون بصل",
        addons=[CartAddonSelection(addon_id=501, quantity=1)],
        source="ai_captain",
    )


# -----------------------------------------------------------------------------
# FastAPI Test Client
# -----------------------------------------------------------------------------

@pytest.fixture
def test_app():
    """Provide FastAPI test app."""
    from app.main import create_app
    return create_app()


@pytest.fixture
def test_client(test_app) -> Generator[TestClient, None, None]:
    """Provide FastAPI test client."""
    with TestClient(test_app) as client:
        yield client


@pytest.fixture
async def async_test_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Provide async HTTP test client."""
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        yield client