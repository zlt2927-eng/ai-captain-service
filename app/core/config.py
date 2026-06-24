"""Application configuration using Pydantic v2."""

from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )

    # App / runtime
    APP_NAME: str = "ai-captain-service"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Feature flags
    ENABLE_TELEGRAM_BOT: bool = False
    ENABLE_TELEGRAM_STRICT: bool = False
    ENABLE_TTS: bool = False
    ENABLE_STT: bool = False
    ENABLE_RECOVERY: bool = False

    # New business logic feature flags
    ENABLE_OFFER_CODES: bool = False
    ENABLE_REAL_MENU: bool = False

    # Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Groq STT
    GROQ_API_KEY: Optional[str] = None
    GROQ_STT_MODEL: str = "whisper-large-v3"

    # ElevenLabs TTS
    ELEVENLABS_API_KEY: Optional[str] = None
    ELEVENLABS_VOICE_ID: Optional[str] = None
    ELEVENLABS_MODEL_ID: str = "eleven_monolingual_v1"

    # Laravel backend integration
    LARAVEL_BACKEND_URL: AnyHttpUrl
    LARAVEL_CART_UPDATE_PATH: str = "/api/v1/cart/update"
    LARAVEL_ABANDONED_CART_PATH: str = "/api/v1/cart/abandoned"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # WebSocket auth
    WEBSOCKET_AUTH_SECRET: str
    WEBSOCKET_AUTH_ALGORITHM: str = "HS256"

    # Session / recovery / HTTP
    SESSION_TTL_SECONDS: int = 3600
    AUDIO_BUFFER_TTL_SECONDS: int = 300
    RECOVERY_DELAY_SECONDS: int = 900
    HTTP_TIMEOUT_SECONDS: int = 30
    HTTP_MAX_RETRIES: int = 3
    HTTP_BACKOFF_BASE_SECONDS: float = 1.0
    MAX_AUDIO_BUFFER_BYTES: int = 10_000_000  # 10MB

    # CORS / debug
    ALLOWED_CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    ENABLE_DEBUG_ROUTES: bool = False

    @field_validator("ALLOWED_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Parse comma-separated CORS origins into a real list."""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        raise ValueError("ALLOWED_CORS_ORIGINS must be a list or comma-separated string")

    @field_validator("GEMINI_API_KEY", "WEBSOCKET_AUTH_SECRET")
    @classmethod
    def validate_required_secrets(cls, value: Optional[str]) -> str:
        if not value or not value.strip():
            raise ValueError("Secret must not be blank")
        return value.strip()

    @field_validator("LARAVEL_BACKEND_URL")
    @classmethod
    def validate_laravel_url(cls, value: Any) -> str:
        """Validate Laravel backend URL is properly formatted."""
        url = str(value).rstrip("/")
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("LARAVEL_BACKEND_URL must be a valid HTTP/HTTPS URL")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("LARAVEL_BACKEND_URL must use http or https scheme")
        return url

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        """Validate Redis URL format."""
        if not value.startswith("redis://") and not value.startswith("rediss://"):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")
        return value

    @model_validator(mode="after")
    def validate_feature_config(self) -> "Settings":
        """Validate feature flag dependencies."""
        if self.ENABLE_TELEGRAM_BOT and not self.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required when ENABLE_TELEGRAM_BOT is enabled")

        if self.ENABLE_STT and not self.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is required when ENABLE_STT is enabled")

        if self.ENABLE_TTS:
            if not self.ELEVENLABS_API_KEY:
                raise ValueError("ELEVENLABS_API_KEY is required when ENABLE_TTS is enabled")
            if not self.ELEVENLABS_VOICE_ID:
                raise ValueError("ELEVENLABS_VOICE_ID is required when ENABLE_TTS is enabled")

        if self.ENABLE_RECOVERY:
            if not self.LARAVEL_BACKEND_URL:
                raise ValueError("LARAVEL_BACKEND_URL is required when ENABLE_RECOVERY is enabled")
            if not self.LARAVEL_ABANDONED_CART_PATH:
                raise ValueError("LARAVEL_ABANDONED_CART_PATH is required when ENABLE_RECOVERY is enabled")

        return self

    @property
    def cart_update_url(self) -> str:
        """Construct full cart update URL."""
        base = str(self.LARAVEL_BACKEND_URL).rstrip("/")
        path = self.LARAVEL_CART_UPDATE_PATH.lstrip("/")
        return f"{base}/{path}"

    @property
    def abandoned_cart_url(self) -> str:
        """Construct full abandoned cart webhook URL."""
        base = str(self.LARAVEL_BACKEND_URL).rstrip("/")
        path = self.LARAVEL_ABANDONED_CART_PATH.lstrip("/")
        return f"{base}/{path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings singleton.
    
    Uses LRU cache to ensure settings are loaded once and reused
    throughout the application lifetime.
    """
    return Settings()