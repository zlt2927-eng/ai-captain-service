"""Unit tests for configuration management."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.constants import CAPTAIN_SYSTEM_PROMPT


class TestSettings:
    """Test Settings configuration."""

    def test_settings_defaults(self):
        """Test default settings values."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
            APP_ENV="development",
            LOG_LEVEL="INFO",
        )
        assert settings.APP_NAME == "ai-captain-service"
        assert settings.APP_ENV == "development"
        assert settings.APP_PORT == 8000
        assert settings.LOG_LEVEL == "INFO"

    def test_settings_feature_flags_defaults(self):
        """Test feature flag defaults."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
        )
        assert settings.ENABLE_TELEGRAM_BOT is False
        assert settings.ENABLE_TTS is False
        assert settings.ENABLE_STT is False
        assert settings.ENABLE_RECOVERY is False

    def test_settings_validate_required_secrets(self):
        """Test that blank secrets are rejected."""
        with pytest.raises(ValidationError):
            Settings(
                GEMINI_API_KEY="",
                WEBSOCKET_AUTH_SECRET="test-secret",
                LARAVEL_BACKEND_URL="http://localhost:8001",
            )

    def test_settings_validate_laravel_url(self):
        """Test Laravel URL validation."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
        )
        assert settings.LARAVEL_BACKEND_URL == "http://localhost:8001"

    def test_settings_validate_laravel_url_invalid(self):
        """Test that invalid Laravel URLs are rejected."""
        with pytest.raises(ValidationError):
            Settings(
                GEMINI_API_KEY="test-key",
                WEBSOCKET_AUTH_SECRET="test-secret",
                LARAVEL_BACKEND_URL="invalid-url",
            )

    def test_settings_validate_redis_url(self):
        """Test Redis URL validation."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
            REDIS_URL="redis://localhost:6379/0",
        )
        assert settings.REDIS_URL == "redis://localhost:6379/0"

    def test_settings_validate_redis_url_invalid(self):
        """Test that invalid Redis URLs are rejected."""
        with pytest.raises(ValidationError):
            Settings(
                GEMINI_API_KEY="test-key",
                WEBSOCKET_AUTH_SECRET="test-secret",
                LARAVEL_BACKEND_URL="http://localhost:8001",
                REDIS_URL="invalid-redis-url",
            )

    def test_settings_cors_origins_parsing(self):
        """Test CORS origins parsing."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
            ALLOWED_CORS_ORIGINS="http://localhost:3000,http://localhost:5173",
        )
        assert settings.ALLOWED_CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]

    def test_settings_feature_dependencies_telegram(self):
        """Test Telegram feature flag dependencies."""
        with pytest.raises(ValidationError):
            Settings(
                GEMINI_API_KEY="test-key",
                WEBSOCKET_AUTH_SECRET="test-secret",
                LARAVEL_BACKEND_URL="http://localhost:8001",
                ENABLE_TELEGRAM_BOT=True,
                TELEGRAM_BOT_TOKEN=None,
            )

    def test_settings_feature_dependencies_stt(self):
        """Test STT feature flag dependencies."""
        with pytest.raises(ValidationError):
            Settings(
                GEMINI_API_KEY="test-key",
                WEBSOCKET_AUTH_SECRET="test-secret",
                LARAVEL_BACKEND_URL="http://localhost:8001",
                ENABLE_STT=True,
                GROQ_API_KEY=None,
            )

    def test_settings_feature_dependencies_tts(self):
        """Test TTS feature flag dependencies."""
        with pytest.raises(ValidationError):
            Settings(
                GEMINI_API_KEY="test-key",
                WEBSOCKET_AUTH_SECRET="test-secret",
                LARAVEL_BACKEND_URL="http://localhost:8001",
                ENABLE_TTS=True,
                ELEVENLABS_API_KEY=None,
            )

    def test_settings_cart_update_url(self):
        """Test cart update URL construction."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
            LARAVEL_CART_UPDATE_PATH="/api/v1/cart/update",
        )
        assert settings.cart_update_url == "http://localhost:8001/api/v1/cart/update"

    def test_settings_abandoned_cart_url(self):
        """Test abandoned cart URL construction."""
        settings = Settings(
            GEMINI_API_KEY="test-key",
            WEBSOCKET_AUTH_SECRET="test-secret",
            LARAVEL_BACKEND_URL="http://localhost:8001",
            LARAVEL_ABANDONED_CART_PATH="/api/v1/cart/abandoned",
        )
        assert settings.abandoned_cart_url == "http://localhost:8001/api/v1/cart/abandoned"


class TestConstants:
    """Test application constants."""

    def test_system_prompt_exists(self):
        """Test that system prompt is defined."""
        assert CAPTAIN_SYSTEM_PROMPT
        assert len(CAPTAIN_SYSTEM_PROMPT) > 0
        assert "AI Digital Captain" in CAPTAIN_SYSTEM_PROMPT

    def test_redis_key_prefixes(self):
        """Test Redis key prefixes are defined."""
        from app.core.constants import (
            REDIS_SESSION_PREFIX,
            REDIS_CART_PREFIX,
            REDIS_AUDIO_PREFIX,
            REDIS_RECOVERY_PREFIX,
        )
        assert REDIS_SESSION_PREFIX == "captain:session"
        assert REDIS_CART_PREFIX == "captain:cart"
        assert REDIS_AUDIO_PREFIX == "captain:audio"
        assert REDIS_RECOVERY_PREFIX == "captain:recovery"

    def test_websocket_close_codes(self):
        """Test WebSocket close codes."""
        from app.core.constants import WS_CLOSE_UNAUTHORIZED, WS_CLOSE_NORMAL
        assert WS_CLOSE_UNAUTHORIZED == 1008
        assert WS_CLOSE_NORMAL == 1000

    def test_tool_names(self):
        """Test tool names are defined."""
        from app.core.constants import TOOL_NAME_UPDATE_CART, TOOL_NAME_VALIDATE_OFFER_CODE
        assert TOOL_NAME_UPDATE_CART == "update_cart"
        assert TOOL_NAME_VALIDATE_OFFER_CODE == "validate_offer_code"