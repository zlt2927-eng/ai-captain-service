"""Application configuration using Pydantic v2 - all hardcoded values consolidated.

Phase 10: Every limit, TTL, retry, timeout, queue size, lock parameter is configurable.
Phase 11: Tool call validation configuration.
Phase 18: Prompt Manager configuration.
"""

from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Configuration sub-models for logical grouping
# ---------------------------------------------------------------------------

class CircuitBreakerConfig(BaseModel):
    """Circuit breaker defaults for all services."""
    failure_threshold: int = Field(default=5, ge=1, le=100, description="Consecutive failures before opening circuit")
    recovery_timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Seconds before transitioning to half-open")
    half_open_max_calls: int = Field(default=3, ge=1, le=50, description="Max probe calls in half-open state")


class RetryConfig(BaseModel):
    """Retry defaults for all services."""
    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    base_delay: float = Field(default=1.0, ge=0.05, le=60.0, description="Base delay for exponential backoff (seconds)")
    max_delay: float = Field(default=30.0, ge=0.1, le=300.0, description="Maximum delay (seconds)")
    jitter_factor: float = Field(default=0.1, ge=0.0, le=0.5, description="Jitter factor for backoff")
    use_jitter: bool = Field(default=True, description="Whether to apply jitter")


class RedisConfig(BaseModel):
    """Redis connection and operation configuration."""
    pool_size: int = Field(default=10, ge=1, le=200, description="Connection pool size")
    max_retries: int = Field(default=3, ge=1, le=10, description="Max retries for Redis operations")
    health_interval_seconds: int = Field(default=30, ge=5, le=300, description="Health check interval")
    lock_default_ttl_seconds: int = Field(default=10, ge=1, le=300, description="Default lock TTL")
    lock_auto_extend_at: float = Field(default=0.5, ge=0.1, le=0.9, description="Fraction of TTL at which to auto-extend lock")
    recovery_marker_completion_ttl_seconds: int = Field(default=60, ge=10, le=600, description="TTL for completed recovery marker")


class WebSocketConfig(BaseModel):
    """WebSocket connection and message configuration."""
    turn_timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0, description="Per-turn processing timeout")
    max_connections_per_fingerprint: int = Field(default=10, ge=1, le=1000, description="Max connections from same fingerprint")
    fingerprint_hash_length: int = Field(default=16, ge=8, le=64, description="Length of connection fingerprint hash")
    connection_anomaly_tracking_seconds: int = Field(default=300, ge=30, le=3600, description="Connection anomaly tracking window")
    subprotocol_selection: str = Field(default="first", description="Subprotocol selection strategy (first/none)")
    default_audio_mime_type: str = Field(default="audio/wav", description="Default audio MIME type")


class SecurityConfig(BaseModel):
    """Security configuration."""
    min_audio_chunk_bytes: int = Field(default=100, ge=16, le=1024, description="Minimum audio chunk size")
    default_audio_chunk_size: int = Field(default=8192, ge=256, le=65536, description="Default audio chunk size")
    allowed_audio_mime_types: list[str] = Field(
        default_factory=lambda: ["audio/wav", "audio/mp3", "audio/ogg", "audio/webm"]
    )


class GeminiConfig(BaseModel):
    """Gemini AI configuration."""
    default_temperature: float = Field(default=0.2, ge=0.0, le=2.0, description="Default Gemini temperature")
    max_retries: int = Field(default=3, ge=1, le=10, description="Max retries for Gemini calls")
    base_delay: float = Field(default=0.8, ge=0.1, le=30.0, description="Base delay for Gemini retry")
    max_delay: float = Field(default=10.0, ge=0.5, le=120.0, description="Max delay for Gemini retry")
    jitter_factor: float = Field(default=0.1, ge=0.0, le=0.5, description="Jitter factor for Gemini retry")


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""
    confirm_order_callback: str = Field(default="confirm_order", description="Callback data for confirm order")
    cancel_order_callback: str = Field(default="cancel_order", description="Callback data for cancel order")
    default_restaurant_id: str = Field(default="default_restaurant", description="Default restaurant ID for Telegram")
    checkout_keywords: list[str] = Field(
        default_factory=lambda: ["checkout", "confirm", "تأكيد", "دفع", "طلب", "إتمام"],
        description="Keywords that trigger action buttons"
    )


class LimtsConfig(BaseModel):
    """Various system limits and thresholds."""
    default_response_timeout_seconds: int = Field(default=30, ge=5, le=300, description="Default response timeout")
    default_menu_cache_ttl_seconds: int = Field(default=300, ge=30, le=3600, description="Menu cache TTL")
    max_json_depth_default: int = Field(default=10, ge=2, le=100, description="Default max JSON depth")
    recovery_default_keep_ttl_seconds: int = Field(default=60, ge=10, le=600, description="Keep recovery marker after completion")


# ---------------------------------------------------------------------------
# Main Settings
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """Application settings from environment variables.

    Phase 10: All hardcoded values consolidated here with Pydantic validation.
    Phase 11: Tool call validation config.
    Phase 18: Prompt Manager config.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )

    # ---- App / runtime ----
    APP_NAME: str = "ai-captain-service"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ---- Feature flags ----
    ENABLE_TELEGRAM_BOT: bool = False
    ENABLE_TELEGRAM_STRICT: bool = False
    ENABLE_TTS: bool = False
    ENABLE_STT: bool = False
    ENABLE_RECOVERY: bool = False
    ENABLE_OFFER_CODES: bool = False
    ENABLE_REAL_MENU: bool = False

    # ---- Gemini ----
    GEMINI_API_KEY: str
    GEMINI_MODEL: str = "gemini-1.5-flash"
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # ---- Gemini configuration (Phase 10) ----
    GEMINI_DEFAULT_TEMPERATURE: float = 0.2
    GEMINI_MAX_RETRIES: int = 3
    GEMINI_BASE_DELAY: float = 0.8
    GEMINI_MAX_DELAY: float = 10.0
    GEMINI_JITTER_FACTOR: float = 0.1

    # ---- Groq STT ----
    GROQ_API_KEY: Optional[str] = None
    GROQ_STT_MODEL: str = "whisper-large-v3"

    # ---- ElevenLabs TTS ----
    ELEVENLABS_API_KEY: Optional[str] = None
    ELEVENLABS_VOICE_ID: Optional[str] = None
    ELEVENLABS_MODEL_ID: str = "eleven_monolingual_v1"

    # ---- Laravel backend integration ----
    LARAVEL_BACKEND_URL: AnyHttpUrl
    LARAVEL_CART_UPDATE_PATH: str = "/api/v1/cart/update"
    LARAVEL_ABANDONED_CART_PATH: str = "/api/v1/cart/abandoned"

    # ---- Redis ----
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---- Redis configuration (Phase 10) ----
    REDIS_POOL_SIZE: int = 10
    REDIS_MAX_RETRIES: int = 3
    REDIS_HEALTH_INTERVAL_SECONDS: int = 30
    REDIS_LOCK_DEFAULT_TTL_SECONDS: int = 10
    REDIS_LOCK_AUTO_EXTEND_AT: float = 0.5

    # ---- WebSocket auth ----
    WEBSOCKET_AUTH_SECRET: str
    WEBSOCKET_AUTH_ALGORITHM: str = "HS256"
    WEBSOCKET_TOKEN_EXPIRY_SECONDS: int = 3600

    # ---- Session / recovery / HTTP ----
    SESSION_TTL_SECONDS: int = 3600
    AUDIO_BUFFER_TTL_SECONDS: int = 300
    RECOVERY_DELAY_SECONDS: int = 900
    HTTP_TIMEOUT_SECONDS: int = 30
    HTTP_MAX_RETRIES: int = 3
    HTTP_BACKOFF_BASE_SECONDS: float = 1.0
    MAX_AUDIO_BUFFER_BYTES: int = 10_000_000  # 10MB

    # ---- CORS / debug ----
    ALLOWED_CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    ENABLE_DEBUG_ROUTES: bool = False

    # ---- Phase 3: Rate Limiting Configuration ----
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_IP_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PER_IP_MAX_REQUESTS: int = 100
    RATE_LIMIT_PER_SESSION_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PER_SESSION_MAX_REQUESTS: int = 50
    RATE_LIMIT_PER_WEBSOCKET_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PER_WEBSOCKET_MAX_MESSAGES: int = 200
    RATE_LIMIT_REDIS_PREFIX: str = "ratelimit"

    # ---- Phase 4: Message Validation Configuration ----
    MAX_MESSAGE_SIZE_BYTES: int = 1_048_576  # 1MB
    MAX_JSON_DEPTH: int = 10
    MAX_TEXT_LENGTH: int = 10_000
    MAX_AUDIO_CHUNK_SIZE_BYTES: int = 100_000  # 100KB per chunk
    MAX_AUDIO_TOTAL_SIZE_BYTES: int = 10_000_000  # 10MB total
    MAX_AUDIO_CHUNKS: int = 100
    ALLOWED_AUDIO_MIME_TYPES: list[str] = Field(
        default_factory=lambda: ["audio/wav", "audio/mp3", "audio/ogg", "audio/webm"]
    )

    # ---- Phase 14: Security Configuration ----
    JWT_VALIDATE_ISSUER: bool = False
    JWT_EXPECTED_ISSUER: Optional[str] = None
    JWT_VALIDATE_AUDIENCE: bool = False
    JWT_EXPECTED_AUDIENCE: Optional[str] = None
    JWT_REQUIRE_KEY_ID: bool = False
    JWT_ALLOWED_ALGORITHMS: list[str] = Field(default_factory=lambda: ["HS256"])
    ENABLE_TOKEN_REVOCATION: bool = True
    TOKEN_REVOCATION_CHECK_INTERVAL_SECONDS: int = 300
    MAX_HEADER_SIZE_BYTES: int = 8192
    MAX_PAYLOAD_SIZE_BYTES: int = 1_048_576  # 1MB
    ENABLE_REQUEST_SIGNING: bool = False
    SECURITY_HEADERS_ENABLED: bool = True

    # ---- Phase 10: Circuit breaker defaults ----
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 30.0
    CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS: int = 3

    # ---- Phase 10: WebSocket defaults ----
    WS_TURN_TIMEOUT_SECONDS: float = 30.0
    WS_MAX_CONNECTIONS_PER_FINGERPRINT: int = 10
    WS_FINGERPRINT_HASH_LENGTH: int = 16
    WS_CONNECTION_ANOMALY_TRACKING_SECONDS: int = 300
    WS_SUBPROTOCOL_SELECTION: str = "first"
    WS_DEFAULT_AUDIO_MIME_TYPE: str = "audio/wav"
    WS_MIN_AUDIO_CHUNK_BYTES: int = 100
    WS_DEFAULT_AUDIO_CHUNK_SIZE: int = 8192

    # ---- Phase 10: Telegram defaults ----
    TELEGRAM_CONFIRM_ORDER_CALLBACK: str = "confirm_order"
    TELEGRAM_CANCEL_ORDER_CALLBACK: str = "cancel_order"
    TELEGRAM_DEFAULT_RESTAURANT_ID: str = "default_restaurant"
    TELEGRAM_CHECKOUT_KEYWORDS: list[str] = Field(
        default_factory=lambda: ["checkout", "confirm", "تأكيد", "دفع", "طلب", "إتمام"]
    )

    # ---- Phase 10: Limits ----
    DEFAULT_RESPONSE_TIMEOUT_SECONDS: int = 30
    DEFAULT_MENU_CACHE_TTL_SECONDS: int = 300
    RECOVERY_MARKER_COMPLETION_TTL_SECONDS: int = 60
    RETRYABLE_STATUS_CODES: list[int] = Field(default_factory=lambda: [429, 500, 502, 503, 504])

    # ---- Phase 11: Tool call validation configuration ----
    TOOL_VALIDATION_STRICT: bool = True
    TOOL_VALIDATION_MAX_ARGUMENTS: int = 20
    TOOL_VALIDATION_MAX_STRING_LENGTH: int = 10000
    TOOL_VALIDATION_MAX_ARRAY_LENGTH: int = 100
    TOOL_VALIDATION_MAX_NUMBER_VALUE: float = 1_000_000_000.0
    TOOL_VALIDATION_MIN_NUMBER_VALUE: float = -1_000_000_000.0

    # ---- Phase 18: Prompt Manager configuration ----
    PROMPT_ENABLED: bool = True
    PROMPT_HOT_RELOAD_ENABLED: bool = True
    PROMPT_HOT_RELOAD_INTERVAL_SECONDS: int = 60
    PROMPT_DEFAULT_VERSION: str = "1.0"
    PROMPT_VALIDATION_STRICT: bool = True
    PROMPT_MAX_TEMPLATE_DEPTH: int = 5
    PROMPT_MAX_RENDERED_CHARS: int = 100_000

    # ======================================================================
    # Validators
    # ======================================================================

    @field_validator("ALLOWED_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Parse comma-separated CORS origins into a real list."""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        raise ValueError("ALLOWED_CORS_ORIGINS must be a list or comma-separated string")

    @field_validator("ALLOWED_AUDIO_MIME_TYPES", mode="before")
    @classmethod
    def parse_audio_mime_types(cls, value: Any) -> list[str]:
        """Parse comma-separated audio MIME types into a list."""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [mime.strip() for mime in value.split(",") if mime.strip()]
        raise ValueError("ALLOWED_AUDIO_MIME_TYPES must be a list or comma-separated string")

    @field_validator("ALLOWED_AUDIO_MIME_TYPES")
    @classmethod
    def validate_audio_mime_types(cls, value: list[str]) -> list[str]:
        """Validate audio MIME types format."""
        valid_prefixes = ("audio/", "video/")
        for mime_type in value:
            if not any(mime_type.startswith(prefix) for prefix in valid_prefixes):
                raise ValueError(f"Invalid audio MIME type: {mime_type}")
        return value

    @field_validator("JWT_ALLOWED_ALGORITHMS", mode="before")
    @classmethod
    def parse_jwt_algorithms(cls, value: Any) -> list[str]:
        """Parse comma-separated JWT algorithms into a list."""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [alg.strip() for alg in value.split(",") if alg.strip()]
        raise ValueError("JWT_ALLOWED_ALGORITHMS must be a list or comma-separated string")

    @field_validator("TELEGRAM_CHECKOUT_KEYWORDS", mode="before")
    @classmethod
    def parse_checkout_keywords(cls, value: Any) -> list[str]:
        """Parse comma-separated checkout keywords into a list."""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str):
            return [kw.strip() for kw in value.split(",") if kw.strip()]
        raise ValueError("TELEGRAM_CHECKOUT_KEYWORDS must be a list or comma-separated string")

    @field_validator("RETRYABLE_STATUS_CODES", mode="before")
    @classmethod
    def parse_retryable_status_codes(cls, value: Any) -> list[int]:
        """Parse comma-separated status codes."""
        if isinstance(value, list):
            return [int(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            return [int(code.strip()) for code in value.split(",") if code.strip()]
        raise ValueError("RETRYABLE_STATUS_CODES must be a list or comma-separated string")

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

    # ---- Phase 10: Range validators for critical numeric fields ----

    @field_validator("GEMINI_DEFAULT_TEMPERATURE")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0.0 or value > 2.0:
            raise ValueError("GEMINI_DEFAULT_TEMPERATURE must be between 0.0 and 2.0")
        return value

    @field_validator("REDIS_LOCK_AUTO_EXTEND_AT")
    @classmethod
    def validate_auto_extend(cls, value: float) -> float:
        if value <= 0.0 or value >= 1.0:
            raise ValueError("REDIS_LOCK_AUTO_EXTEND_AT must be between 0.0 and 1.0 (exclusive)")
        return value

    @field_validator("MAX_AUDIO_BUFFER_BYTES")
    @classmethod
    def validate_audio_buffer(cls, value: int) -> int:
        if value < 1024 * 1024:  # Minimum 1MB
            raise ValueError("MAX_AUDIO_BUFFER_BYTES must be at least 1MB (1048576)")
        if value > 500 * 1024 * 1024:  # Maximum 500MB
            raise ValueError("MAX_AUDIO_BUFFER_BYTES must not exceed 500MB")
        return value

    @field_validator("HTTP_TIMEOUT_SECONDS")
    @classmethod
    def validate_http_timeout(cls, value: int) -> int:
        if value < 1 or value > 300:
            raise ValueError("HTTP_TIMEOUT_SECONDS must be between 1 and 300")
        return value

    @field_validator("HTTP_MAX_RETRIES")
    @classmethod
    def validate_retries(cls, value: int) -> int:
        if value < 0 or value > 10:
            raise ValueError("HTTP_MAX_RETRIES must be between 0 and 10")
        return value

    @field_validator("SESSION_TTL_SECONDS")
    @classmethod
    def validate_session_ttl(cls, value: int) -> int:
        if value < 60 or value > 86400:
            raise ValueError("SESSION_TTL_SECONDS must be between 60 and 86400")
        return value

    @field_validator("RECOVERY_DELAY_SECONDS")
    @classmethod
    def validate_recovery_delay(cls, value: int) -> int:
        if value < 30 or value > 86400:
            raise ValueError("RECOVERY_DELAY_SECONDS must be between 30 and 86400")
        return value

    @field_validator("MAX_MESSAGE_SIZE_BYTES")
    @classmethod
    def validate_message_size(cls, value: int) -> int:
        if value < 1024 or value > 100 * 1024 * 1024:
            raise ValueError("MAX_MESSAGE_SIZE_BYTES must be between 1KB and 100MB")
        return value

    @field_validator("MAX_JSON_DEPTH")
    @classmethod
    def validate_json_depth(cls, value: int) -> int:
        if value < 2 or value > 100:
            raise ValueError("MAX_JSON_DEPTH must be between 2 and 100")
        return value

    @field_validator("MAX_AUDIO_CHUNKS")
    @classmethod
    def validate_max_chunks(cls, value: int) -> int:
        if value < 1 or value > 10000:
            raise ValueError("MAX_AUDIO_CHUNKS must be between 1 and 10000")
        return value

    @field_validator("WS_TURN_TIMEOUT_SECONDS")
    @classmethod
    def validate_turn_timeout(cls, value: float) -> float:
        if value < 1.0 or value > 300.0:
            raise ValueError("WS_TURN_TIMEOUT_SECONDS must be between 1.0 and 300.0")
        return value

    @field_validator("CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    @classmethod
    def validate_cb_threshold(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("CIRCUIT_BREAKER_FAILURE_THRESHOLD must be between 1 and 100")
        return value

    @field_validator("CIRCUIT_BREAKER_RECOVERY_TIMEOUT")
    @classmethod
    def validate_cb_recovery(cls, value: float) -> float:
        if value < 1.0 or value > 600.0:
            raise ValueError("CIRCUIT_BREAKER_RECOVERY_TIMEOUT must be between 1.0 and 600.0")
        return value

    @field_validator("CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS")
    @classmethod
    def validate_cb_half_open(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS must be between 1 and 50")
        return value

    @field_validator("REDIS_POOL_SIZE")
    @classmethod
    def validate_pool_size(cls, value: int) -> int:
        if value < 1 or value > 500:
            raise ValueError("REDIS_POOL_SIZE must be between 1 and 500")
        return value

    @field_validator("REDIS_LOCK_DEFAULT_TTL_SECONDS")
    @classmethod
    def validate_lock_ttl(cls, value: int) -> int:
        if value < 1 or value > 300:
            raise ValueError("REDIS_LOCK_DEFAULT_TTL_SECONDS must be between 1 and 300")
        return value

    @field_validator("WS_MAX_CONNECTIONS_PER_FINGERPRINT")
    @classmethod
    def validate_max_connections(cls, value: int) -> int:
        if value < 1 or value > 10000:
            raise ValueError("WS_MAX_CONNECTIONS_PER_FINGERPRINT must be between 1 and 10000")
        return value

    @field_validator("DEFAULT_MENU_CACHE_TTL_SECONDS")
    @classmethod
    def validate_menu_cache_ttl(cls, value: int) -> int:
        if value < 10 or value > 86400:
            raise ValueError("DEFAULT_MENU_CACHE_TTL_SECONDS must be between 10 and 86400")
        return value

    @field_validator("TELEGRAM_DEFAULT_RESTAURANT_ID")
    @classmethod
    def validate_restaurant_id(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("TELEGRAM_DEFAULT_RESTAURANT_ID must not be empty")
        return value.strip()

    # ---- Phase 11: Validators for tool call configuration ----

    @field_validator("TOOL_VALIDATION_MAX_ARGUMENTS")
    @classmethod
    def validate_tool_max_args(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("TOOL_VALIDATION_MAX_ARGUMENTS must be between 1 and 100")
        return value

    @field_validator("TOOL_VALIDATION_MAX_STRING_LENGTH")
    @classmethod
    def validate_tool_max_string(cls, value: int) -> int:
        if value < 1 or value > 1_000_000:
            raise ValueError("TOOL_VALIDATION_MAX_STRING_LENGTH must be between 1 and 1000000")
        return value

    @field_validator("TOOL_VALIDATION_MAX_NUMBER_VALUE")
    @classmethod
    def validate_tool_max_number(cls, value: float) -> float:
        if value < 0 or value > 1_000_000_000_000:
            raise ValueError("TOOL_VALIDATION_MAX_NUMBER_VALUE must be between 0 and 1e12")
        return value

    # ---- Phase 18: Validators for prompt management ----

    @field_validator("PROMPT_HOT_RELOAD_INTERVAL_SECONDS")
    @classmethod
    def validate_hot_reload_interval(cls, value: int) -> int:
        if value < 5 or value > 3600:
            raise ValueError("PROMPT_HOT_RELOAD_INTERVAL_SECONDS must be between 5 and 3600")
        return value

    @field_validator("PROMPT_MAX_TEMPLATE_DEPTH")
    @classmethod
    def validate_template_depth(cls, value: int) -> int:
        if value < 1 or value > 50:
            raise ValueError("PROMPT_MAX_TEMPLATE_DEPTH must be between 1 and 50")
        return value

    @field_validator("PROMPT_MAX_RENDERED_CHARS")
    @classmethod
    def validate_max_rendered_chars(cls, value: int) -> int:
        if value < 1000 or value > 10_000_000:
            raise ValueError("PROMPT_MAX_RENDERED_CHARS must be between 1000 and 10000000")
        return value

    # ---- Cross-field validation ----

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

        # Phase 10: Validate Gemini retry vs circuit breaker consistency
        if self.CIRCUIT_BREAKER_RECOVERY_TIMEOUT < self.GEMINI_MAX_DELAY:
            raise ValueError(
                "CIRCUIT_BREAKER_RECOVERY_TIMEOUT must be >= GEMINI_MAX_DELAY "
                f"({self.CIRCUIT_BREAKER_RECOVERY_TIMEOUT} < {self.GEMINI_MAX_DELAY})"
            )

        # Phase 10: Validate Redis lock auto-extend is sensible
        if self.REDIS_LOCK_AUTO_EXTEND_AT <= 0.0 or self.REDIS_LOCK_AUTO_EXTEND_AT >= 1.0:
            raise ValueError("REDIS_LOCK_AUTO_EXTEND_AT must be between 0.0 and 1.0 (exclusive)")

        return self

    # ---- Computed properties ----

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

    @property
    def circuit_breaker_config(self) -> CircuitBreakerConfig:
        """Get circuit breaker configuration."""
        return CircuitBreakerConfig(
            failure_threshold=self.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            recovery_timeout=self.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            half_open_max_calls=self.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS,
        )

    @property
    def gemini_config(self) -> GeminiConfig:
        """Get Gemini configuration."""
        return GeminiConfig(
            default_temperature=self.GEMINI_DEFAULT_TEMPERATURE,
            max_retries=self.GEMINI_MAX_RETRIES,
            base_delay=self.GEMINI_BASE_DELAY,
            max_delay=self.GEMINI_MAX_DELAY,
            jitter_factor=self.GEMINI_JITTER_FACTOR,
        )

    @property
    def redis_config(self) -> RedisConfig:
        """Get Redis configuration."""
        return RedisConfig(
            pool_size=self.REDIS_POOL_SIZE,
            max_retries=self.REDIS_MAX_RETRIES,
            health_interval_seconds=self.REDIS_HEALTH_INTERVAL_SECONDS,
            lock_default_ttl_seconds=self.REDIS_LOCK_DEFAULT_TTL_SECONDS,
            lock_auto_extend_at=self.REDIS_LOCK_AUTO_EXTEND_AT,
        )

    @property
    def websocket_config(self) -> WebSocketConfig:
        """Get WebSocket configuration."""
        return WebSocketConfig(
            turn_timeout_seconds=self.WS_TURN_TIMEOUT_SECONDS,
            max_connections_per_fingerprint=self.WS_MAX_CONNECTIONS_PER_FINGERPRINT,
            fingerprint_hash_length=self.WS_FINGERPRINT_HASH_LENGTH,
            connection_anomaly_tracking_seconds=self.WS_CONNECTION_ANOMALY_TRACKING_SECONDS,
            default_audio_mime_type=self.WS_DEFAULT_AUDIO_MIME_TYPE,
        )

    @property
    def telegram_config(self) -> TelegramConfig:
        """Get Telegram configuration."""
        return TelegramConfig(
            confirm_order_callback=self.TELEGRAM_CONFIRM_ORDER_CALLBACK,
            cancel_order_callback=self.TELEGRAM_CANCEL_ORDER_CALLBACK,
            default_restaurant_id=self.TELEGRAM_DEFAULT_RESTAURANT_ID,
            checkout_keywords=self.TELEGRAM_CHECKOUT_KEYWORDS,
        )

    @property
    def retryable_status_codes_set(self) -> set[int]:
        """Get retryable status codes as a set."""
        return set(self.RETRYABLE_STATUS_CODES)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings singleton.

    Uses LRU cache to ensure settings are loaded once and reused
    throughout the application lifetime.
    """
    return Settings()