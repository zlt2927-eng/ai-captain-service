"""Application configuration using Pydantic v2."""

from typing import Optional
from pydantic import Field, field_validator
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

    # Gemini
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"
    TELEGRAM_BOT_TOKEN: str

    # Groq STT
    GROQ_API_KEY: str
    GROQ_STT_MODEL: str = "whisper-large-v3"

    # ElevenLabs TTS
    ELEVENLABS_API_KEY: str
    ELEVENLABS_VOICE_ID: str
    ELEVENLABS_MODEL_ID: str

    # Laravel backend integration
    LARAVEL_BACKEND_URL: str
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
    ALLOWED_CORS_ORIGINS: str = "http://localhost:3000"
    ENABLE_DEBUG_ROUTES: bool = False

    @field_validator("ALLOWED_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse comma-separated CORS origins."""
        if isinstance(v, list):
            return v
        return [origin.strip() for origin in v.split(",") if origin.strip()]

    @field_validator(
        "GEMINI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "GROQ_API_KEY",
        "ELEVENLABS_API_KEY",
        "WEBSOCKET_AUTH_SECRET",
    )
    @classmethod
    def validate_secrets_not_empty(cls, v: str) -> str:
        """Ensure required secrets are not blank."""
        if not v or not v.strip():
            raise ValueError("Secret must not be blank")
        return v

    @property
    def cart_update_url(self) -> str:
        """Computed Laravel cart update URL."""
        base = self.LARAVEL_BACKEND_URL.rstrip("/")
        path = self.LARAVEL_CART_UPDATE_PATH.lstrip("/")
        return f"{base}/{path}"

    @property
    def abandoned_cart_url(self) -> str:
        """Computed Laravel abandoned cart webhook URL."""
        base = self.LARAVEL_BACKEND_URL.rstrip("/")
        path = self.LARAVEL_ABANDONED_CART_PATH.lstrip("/")
        return f"{base}/{path}"


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()
