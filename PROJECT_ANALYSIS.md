# AI Captain Service - Comprehensive Project Analysis

**Analysis Date**: 2026-06-29  
**Analyst**: Senior Software Architect / Security Engineer / Performance Engineer  
**Project Version**: 1.0.0 (Phase 2 Complete)  
**Repository**: https://github.com/zlt2927-eng/ai-captain-service.git

---

## SECTION 1 - Executive Summary

### Project Purpose

The AI Captain Service is a production-grade FastAPI microservice that acts as an AI-powered digital waiter for restaurant ordering systems. It provides real-time conversational ordering through WebSocket connections, supporting both text and voice input/output with Arabic-first language support.

### Business Domain

**Primary Domain**: Restaurant Technology / Food Service  
**Target Market**: Multi-tenant restaurant platforms requiring AI-powered ordering  
**Scale Target**: 1,000+ restaurants with horizontal scaling capability  
**Key Use Cases**:
- Voice-enabled restaurant ordering
- Cart management with dish-addon modeling
- Abandoned cart recovery
- Multi-dialect Arabic support (Gulf, Saudi, Emirati, Egyptian, Levantine, Iraqi, MSA)
- Cross-platform integration (WebSocket, Telegram)

### Overall Architecture

The service follows a **layered microservice architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    Client Layer                          │
│  (WebSocket / Telegram Bot)                             │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│              API Layer (FastAPI)                         │
│  - WebSocket Endpoints                                   │
│  - Telegram Bot Handlers                                 │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           WebSocket Runtime Layer                        │
│  - Authentication, Connection Context, Message Routing   │
│  - Handlers (Ping, Text, Audio), Response Sender         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│            Business Logic Layer                          │
│  - Gemini Orchestrator (LLM coordination)                │
│  - Session Service, Recovery Service                     │
│  - Tool Execution Coordinator                            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│           Infrastructure Layer                           │
│  - HTTP Client (with retries)                            │
│  - Redis Client (session/cart persistence)               │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│         External Services Layer                          │
│  - Google Gemini (LLM)                                   │
│  - Groq (STT)                                            │
│  - ElevenLabs (TTS)                                      │
│  - Laravel Backend (cart/order management)               │
└─────────────────────────────────────────────────────────┘
```

### Technologies Used

**Core Framework & Runtime**:
- **FastAPI** (0.115.12) - Async web framework
- **Uvicorn** (0.34.3) - ASGI server
- **Python 3.11+** - Runtime

**AI/ML Services**:
- **Google Generative AI** (0.8.4) - Gemini LLM for conversation orchestration
- **Groq API** - Whisper Large V3 for speech-to-text
- **ElevenLabs API** - Streaming text-to-speech

**Data & State Management**:
- **Redis** (5.2.1) - Session persistence, cart snapshots, recovery scheduling
- **Pydantic** (2.10.4) - Data validation and settings management
- **Pydantic Settings** (2.8.1) - Configuration management

**Integration & Communication**:
- **HTTPX** (0.28.1) - Async HTTP client with retry logic
- **WebSockets** (14.0) - Real-time bidirectional communication
- **python-telegram-bot** (21.10) - Telegram bot integration
- **PyJWT** (2.10.1) - JWT authentication for WebSocket

**Development & Quality**:
- **pytest** (8.3.4) - Testing framework
- **black, flake8, mypy, isort** - Code quality tools
- **locust** (2.32.4) - Load testing

### Estimated Project Maturity

**Phase 2 Complete** - Production-Hardened Foundation

**Maturity Indicators**:
- ✅ Comprehensive error handling and retry logic
- ✅ Structured logging with correlation tracking
- ✅ Idempotent operations for cart mutations
- ✅ Per-session turn serialization
- ✅ Distributed locking with Redis
- ✅ Atomic operations via Redis pipelines
- ✅ Feature flags for optional components
- ✅ Configuration validation with Pydantic
- ⚠️ Test suite implementation pending (Phase 3)
- ⚠️ No CI/CD pipeline visible
- ⚠️ No Docker/Kubernetes manifests in repository

**Estimated Production Readiness**: 75% - Core functionality complete, needs testing and deployment automation

### Strengths

1. **Excellent Architecture Decomposition**: Phase 2 refactoring created clean separation of concerns with specialized components (PromptBuilder, MenuContextProvider, CartBackendGateway, ToolExecutionCoordinator)

2. **Production-Grade Resilience**:
   - Exponential backoff with jitter for retries
   - Timeout protection (30s turn processing)
   - Distributed locking to prevent race conditions
   - Idempotency keys prevent duplicate mutations

3. **Security-Conscious Design**:
   - JWT authentication with strict algorithm validation
   - Cross-tenant validation enforced at Laravel backend
   - No sensitive data in tokens
   - Structured logging without secret exposure

4. **Observability**:
   - Correlation IDs for end-to-end tracing
   - Structured logging with context
   - HTTP client latency tracking
   - Comprehensive error context

5. **Arabic-First Design**: Native support for multiple Arabic dialects with intelligent mirroring

6. **Flexible Deployment**: Feature flags allow selective enabling of optional services (STT, TTS, Telegram, Recovery)

### Weaknesses

1. **No Test Coverage**: Zero automated tests - critical for production deployment

2. **In-Memory State in Some Components**:
   - MenuContextProvider has in-memory cache (not shared across instances)
   - AudioBufferService stores buffers in memory
   - RecoveryService tracks tasks in memory

3. **Limited Input Validation**:
   - No rate limiting on WebSocket messages
   - No message size limits beyond audio buffer
   - Limited validation of Gemini tool arguments

4. **Hardcoded Values**:
   - Turn timeout hardcoded to 30 seconds
   - Cache TTL hardcoded to 5 minutes
   - Default restaurant ID in Telegram bot

5. **Missing Operational Features**:
   - No health check metrics export
   - No Prometheus/OpenTelemetry integration
   - No circuit breakers for external dependencies
   - No request/response size limits

6. **Documentation Gaps**:
   - No API documentation (Swagger/OpenAPI)
   - No deployment guides beyond basic Docker
   - No runbooks for common failures

### Overall Code Quality Score: 8/10

**Breakdown**:
- Architecture & Design: 9/10 (excellent decomposition, clean layers)
- Code Organization: 9/10 (clear separation, consistent patterns)
- Error Handling: 8/10 (comprehensive but could be more granular)
- Documentation: 7/10 (good README, missing inline docs in places)
- Testing: 2/10 (no test suite - major gap)
- Security: 8/10 (strong auth, needs rate limiting)
- Performance: 7/10 (good caching, some in-memory state)
- Maintainability: 8/10 (clean code, good naming, some duplication)

**Deductions**:
- -1 for no test coverage
- -1 for in-memory state limiting horizontal scaling
- +1 for excellent Phase 2 refactoring

---

## SECTION 2 - Folder Structure

### Root Level

```
ai-captain-service/
├── .env.example                 # Environment configuration template
├── LARAVEL_BACKEND_REQUIREMENTS.md  # Laravel backend API specification
├── README.md                    # Comprehensive project documentation
├── requirements-dev.txt         # Development dependencies
├── requirements.txt             # Production dependencies
└── app/                         # Main application package
```

**Responsibility**: Root level contains configuration templates, documentation, and dependency specifications.

**Why It Exists**: Standard Python project structure with clear separation of configuration, documentation, and source code.

**Important Files**:
- `.env.example` - Documents all 30+ environment variables with defaults
- `LARAVEL_BACKEND_REQUIREMENTS.md` - Critical integration specification for backend team
- `README.md` - 1338 lines of comprehensive documentation

**Dependencies**: None (root level)

---

### app/ - Main Application Package

```
app/
├── __init__.py                  # Package marker
├── main.py                      # FastAPI app entry point & lifespan
├── api/                         # API layer (endpoints)
├── core/                        # Core utilities (config, logging, constants)
├── infrastructure/              # Infrastructure layer (HTTP, Redis)
├── integrations/                # External integrations (Telegram)
├── schemas/                     # Pydantic data models
├── services/                    # Business logic layer
├── tools/                       # Tool implementations for LLM
└── websocket/                   # WebSocket runtime (Phase 2)
```

**Responsibility**: Contains all application code organized by architectural layer.

**Why It Exists**: Enforces clean architecture with dependency flow: API → WebSocket → Services → Infrastructure → External

**Important Files**: All files in this directory are critical (see Section 3 for details)

**Dependencies**: Python 3.11+, all packages in requirements.txt

---

### app/api/ - API Layer

```
app/api/
├── __init__.py
├── websocket_endpoints.py       # WebSocket route handler
└── telegram_bot.py              # Telegram bot message handlers
```

**Responsibility**: Entry points for all client connections. Thin layer that delegates to WebSocket runtime or integration services.

**Why It Exists**: FastAPI routers provide routing, middleware application, and connection management.

**Important Files**:
- `websocket_endpoints.py` - Single WebSocket route at `/ws/captain/{restaurant_id}/{session_id}`
- `telegram_bot.py` - Telegram bot handlers using python-telegram-bot library

**Dependencies**: FastAPI, WebSocket, telegram library

---

### app/core/ - Core Utilities

```
app/core/
├── __init__.py
├── config.py                    # Pydantic Settings with validation
├── constants.py                 # Application constants & system prompt
└── logging.py                   # Structured logging setup
```

**Responsibility**: Foundational utilities used throughout the application.

**Why It Exists**: Centralizes configuration, constants, and logging to avoid duplication and ensure consistency.

**Important Files**:
- `config.py` - Settings class with 30+ environment variables, validators, and feature flags
- `constants.py` - System prompt for Gemini, Redis key prefixes, error codes, WebSocket close codes
- `logging.py` - LogContext class for structured logging with restaurant/session context

**Dependencies**: Pydantic, logging

---

### app/infrastructure/ - Infrastructure Layer

```
app/infrastructure/
├── __init__.py
├── http_client.py               # Async HTTP client with retries
└── redis_client.py              # Async Redis client with locking/pipelines
```

**Responsibility**: Low-level communication with external systems (HTTP APIs, Redis).

**Why It Exists**: Provides reusable, production-hardened clients with retry logic, structured logging, and error handling.

**Important Files**:
- `http_client.py` - HTTPClient with exponential backoff, jitter, structured logging, retry on 5xx for idempotent methods
- `redis_client.py` - RedisClient with pipeline support, distributed locking (Lua scripts), atomic operations, TTL management

**Dependencies**: httpx, redis, asyncio

---

### app/integrations/ - External Integrations

```
app/integrations/
├── __init__.py                  # Lazy import for Telegram
└── telegram/
    ├── __init__.py
    └── service.py               # Telegram bot lifecycle management
```

**Responsibility**: Optional third-party service integrations with lazy loading to avoid import overhead when disabled.

**Why It Exists**: Decouples external service logic from core business logic. Lazy loading prevents unnecessary dependencies when features are disabled.

**Important Files**:
- `__init__.py` - Uses `__getattr__` for lazy import of TelegramIntegration
- `service.py` - Manages Telegram bot lifecycle (start/shutdown), stores references in bot_data

**Dependencies**: python-telegram-bot, FastAPI

---

### app/schemas/ - Data Models

```
app/schemas/
├── __init__.py
├── cart_schemas.py              # Cart validation schemas
└── websocket_schemas.py         # WebSocket message schemas
```

**Responsibility**: Pydantic models for data validation and type safety.

**Why It Exists**: Centralizes data validation, ensures type safety, provides clear contracts between layers.

**Important Files**:
- `cart_schemas.py` - CartAction enum, CartAddonSelection, CartUpdatePayload with validators
- `websocket_schemas.py` - MessageType enum, all incoming/outgoing message schemas, helper constructors

**Dependencies**: Pydantic

---

### app/services/ - Business Logic Layer

```
app/services/
├── __init__.py
├── gemini_orchestrator.py       # LLM orchestration (decomposed)
├── prompt_builder.py            # System prompt construction
├── menu_context_provider.py     # Menu data abstraction (mock/Laravel)
├── cart_backend_gateway.py      # Cart operations with idempotency
├── tool_execution_coordinator.py # Tool validation & execution
├── session_service.py           # Session state management
├── recovery_service.py          # Abandoned cart recovery
├── stt_service.py               # Speech-to-text (Groq)
└── tts_service.py               # Text-to-speech (ElevenLabs)
```

**Responsibility**: Core business logic, LLM orchestration, session management, and external service coordination.

**Why It Exists**: Implements all business rules, coordinates between infrastructure and API layers, manages conversation flow.

**Important Files**:
- `gemini_orchestrator.py` - Main LLM orchestration with tool calling, retry logic, conversation history
- `prompt_builder.py` - Constructs system prompts with menu context
- `menu_context_provider.py` - Abstract menu provider with Mock and Laravel implementations, multi-level caching
- `cart_backend_gateway.py` - Idempotent cart mutations, addon validation, offer code validation
- `tool_execution_coordinator.py` - Tool registry, validation, execution
- `session_service.py` - Session lifecycle, turn history, cart snapshots, order linking
- `recovery_service.py` - Abandoned cart detection, deduplication, webhook delivery
- `stt_service.py` - Groq Whisper integration for audio transcription
- `tts_service.py` - ElevenLabs streaming TTS

**Dependencies**: All infrastructure services, Gemini API, Groq API, ElevenLabs API

---

### app/tools/ - Tool Implementations

```
app/tools/
├── __init__.py
└── cart_tools.py                # Cart update tool (thin wrapper)
```

**Responsibility**: Thin wrappers around CartBackendGateway methods for LLM tool calling.

**Why It Exists**: Provides LLM-callable functions with proper signatures and validation.

**Important Files**:
- `cart_tools.py` - update_cart, validate_offer_code, get_session_order functions

**Dependencies**: CartBackendGateway, Pydantic schemas

---

### app/websocket/ - WebSocket Runtime

```
app/websocket/
├── __init__.py
├── connection_context.py        # Per-connection state
├── auth.py                      # JWT authentication
├── audio_buffer_service.py      # Audio buffering with safety
├── message_router.py            # Message type routing
├── handlers.py                  # Message handlers (Ping, Text, Audio)
├── response_sender.py           # Structured response sending
└── turn_processor.py            # Turn serialization & timeouts
```

**Responsibility**: WebSocket connection lifecycle, message processing pipeline, turn management.

**Why It Exists**: Phase 2 decomposition created specialized components for WebSocket handling, replacing monolithic endpoint logic.

**Important Files**:
- `connection_context.py` - ConnectionContext dataclass with turn correlation, service references
- `auth.py` - WebSocketAuth with JWT validation, algorithm enforcement, token payload verification
- `audio_buffer_service.py` - AudioBufferState with sequence validation, size limits, MIME type checking
- `message_router.py` - MessageRouter with handler registry, type-based dispatch
- `handlers.py` - PingHandler, TextMessageHandler, AudioChunkHandler, AudioEndHandler
- `response_sender.py` - ResponseSender with type-safe methods for all WebSocket message types
- `turn_processor.py` - TurnProcessor with per-session locking, timeout protection, correlation IDs

**Dependencies**: WebSocket, Pydantic schemas, all services

---

## SECTION 3 - File By File Analysis

### 3.1 Configuration & Core Files

#### File: app/main.py

**Purpose**: FastAPI application entry point with lifespan management and dependency injection.

**Responsibilities**:
- Create and configure FastAPI app
- Register CORS middleware
- Include WebSocket router
- Define health/readiness endpoints
- Manage application lifespan (startup/shutdown)
- Initialize all services in correct order
- Handle optional service initialization with error recovery

**Main Classes/Functions**:
- `create_app()` - Factory function for FastAPI app
- `lifespan()` - Async context manager for startup/shutdown
- `health()` - Health check endpoint (always returns ok)
- `ready()` - Readiness check with dependency verification

**Public API**:
- FastAPI app instance (created at module level)
- `/health` - Liveness probe
- `/ready` - Readiness probe with dependency checks

**Internal Logic**:
1. Load settings via `get_settings()`
2. Create FastAPI app with lifespan
3. Add CORS middleware with configured origins
4. Include WebSocket router
5. Store settings in app.state
6. Define health/ready endpoints
7. In lifespan:
   - Setup logging
   - Initialize Redis client and connect
   - Initialize HTTP client
   - Initialize SessionService
   - Initialize GeminiOrchestrator (with Redis for menu caching)
   - Conditionally initialize STT, TTS, Recovery services
   - Conditionally initialize Telegram integration (with strict/non-strict failure modes)
   - Set ready flag
   - On shutdown: reverse order cleanup

**Inputs**: Environment variables via Settings

**Outputs**: FastAPI app instance, health/ready JSON responses

**Dependencies**:
- `app.core.config.get_settings`
- `app.core.logging.LogContext, setup_logging`
- `app.infrastructure.http_client.HTTPClient`
- `app.infrastructure.redis_client.RedisClient`
- `app.services.gemini_orchestrator.GeminiOrchestrator`
- `app.services.recovery_service.RecoveryService`
- `app.services.session_service.SessionService`
- `app.services.stt_service.STTService`
- `app.services.tts_service.TTSService`
- `app.integrations.telegram.service.TelegramIntegration` (lazy import)

**Called By**: Uvicorn server, Docker entrypoint

**Uses**: FastAPI, CORSMiddleware, asynccontextmanager

**External Libraries**: fastapi, uvicorn

**Potential Problems**:
- Telegram integration failure in non-strict mode silently continues, which could mask configuration issues
- No validation that required services initialized successfully before setting ready=True
- Health endpoint doesn't check if service is actually ready (only checks if running)

**Security Concerns**:
- CORS allows all methods and headers (`["*"]`) - should be more restrictive in production
- No rate limiting on health/ready endpoints (minor issue)

**Performance Concerns**:
- Sequential service initialization could be slow (no parallel startup)
- No timeout on service initialization

**Missing Validation**:
- No check that GEMINI_API_KEY is valid during startup
- No check that Redis is actually functional (only checks connection)

**Missing Error Handling**:
- If Redis connection fails, app continues to start (should fail fast)
- No handling of partial initialization failures

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add parallel initialization for independent services
2. Fail fast on critical service initialization failures
3. Add startup timeout
4. Validate API keys during startup (test Gemini connection)
5. Restrict CORS methods/headers to specific values
6. Add metrics endpoint for Prometheus

---

#### File: app/core/config.py

**Purpose**: Application configuration using Pydantic v2 with comprehensive validation.

**Responsibilities**:
- Load environment variables
- Validate required secrets
- Validate URL formats
- Enforce feature flag dependencies
- Provide helper properties for URL construction
- Cache settings singleton

**Main Classes/Functions**:
- `Settings` - Pydantic BaseSettings class with 30+ fields
- `get_settings()` - Cached settings factory function

**Public API**:
- `Settings` class with all configuration fields
- `cart_update_url` property
- `abandoned_cart_url` property
- `get_settings()` singleton accessor

**Internal Logic**:
1. Define all configuration fields with types and defaults
2. Implement validators:
   - `parse_cors_origins` - Parse comma-separated CORS origins
   - `validate_required_secrets` - Ensure secrets are not blank
   - `validate_laravel_url` - Validate Laravel backend URL format
   - `validate_redis_url` - Validate Redis URL format
3. Implement `validate_feature_config` model validator:
   - Check TELEGRAM_BOT_TOKEN if ENABLE_TELEGRAM_BOT
   - Check GROQ_API_KEY if ENABLE_STT
   - Check ELEVENLABS_API_KEY and VOICE_ID if ENABLE_TTS
   - Check LARAVEL_BACKEND_URL if ENABLE_RECOVERY
4. Provide URL construction properties
5. Cache settings with LRU cache

**Inputs**: Environment variables from .env file or system

**Outputs**: Settings instance with validated configuration

**Dependencies**: pydantic, pydantic-settings, urllib.parse

**Called By**: app/main.py, all services during initialization

**Uses**: Pydantic validators, field definitions

**External Libraries**: pydantic-settings

**Potential Problems**:
- LRU cache with maxsize=1 means settings cannot be reloaded without restart
- No validation that API keys are actually valid (only checks they're not blank)
- ALLOWED_CORS_ORIGINS default is ["http://localhost:3000"] which is development-only

**Security Concerns**:
- Secrets validated for non-blank but not for format/strength
- No warning if WEBSOCKET_AUTH_SECRET is weak/default
- CORS origins default to localhost only (good for dev, needs explicit config for prod)

**Performance Concerns**: None (startup-time only)

**Missing Validation**:
- No validation of GEMINI_MODEL format
- No validation of ELEVENLABS_MODEL_ID
- No validation that LOG_LEVEL is a valid logging level
- No validation that numeric ranges are reasonable (e.g., SESSION_TTL_SECONDS > 0)

**Missing Error Handling**:
- Invalid .env file format raises unhandled exception
- No graceful fallback for missing .env file

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add API key format validation (e.g., length, character set)
2. Add model name validation against known lists
3. Add numeric range validators for all numeric config
4. Warn if using default/weak secrets
5. Add configuration reload capability for development
6. Document all environment variables in code (already in .env.example)

---

#### File: app/core/constants.py

**Purpose**: Application constants including system prompt, Redis key prefixes, error codes, and WebSocket constants.

**Responsibilities**:
- Define system prompt for Gemini LLM
- Define Redis key prefixes
- Define WebSocket close codes
- Define audio constraints
- Define tool names
- Define error codes

**Main Constants**:
- `CAPTAIN_SYSTEM_PROMPT` - 50-line system prompt for Gemini
- `REDIS_*_PREFIX` - Redis key prefixes for session, cart, audio, recovery
- `WS_CLOSE_*` - WebSocket close codes
- `TOOL_NAME_*` - Tool names for LLM function calling
- `ERROR_CODE_*` - Standard error codes

**Inputs**: None (constants)

**Outputs**: Constant values

**Dependencies**: None

**Called By**: Multiple services and WebSocket handlers

**Uses**: String constants, enum values

**External Libraries**: None

**Potential Problems**:
- System prompt is hardcoded in Python file (not externalized for A/B testing)
- Error codes are strings (could be enums for better type safety)
- No versioning for error codes

**Security Concerns**: None

**Performance Concerns**: None

**Missing Validation**: N/A

**Missing Error Handling**: N/A

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Externalize system prompt to file/database for A/B testing
2. Convert error codes to enum for type safety
3. Add error code versioning
4. Add tool parameter schemas as constants
5. Consider using dataclasses for related constants

---

#### File: app/core/logging.py

**Purpose**: Structured logging configuration with context support.

**Responsibilities**:
- Configure root logger with console handler
- Set log levels for noisy libraries
- Provide LogContext class for structured logging with restaurant/session context

**Main Classes/Functions**:
- `setup_logging()` - Configure logging with formatter and handlers
- `get_logger()` - Get logger by name
- `LogContext` - Context manager for adding restaurant/session to log messages

**Inputs**: log_level, app_name

**Outputs**: Configured logger, LogContext instances

**Dependencies**: logging, sys

**Called By**: app/main.py during startup, all modules via `logging.getLogger(__name__)`

**Uses**: Python logging module

**External Libraries**: None

**Potential Problems**:
- LogContext is not a true context manager (no `__enter__`/`__exit__`)
- No JSON logging format (only text)
- No log rotation configured
- No external log aggregation support

**Security Concerns**:
- No PII redaction in logs
- No secret masking (relies on developers not logging secrets)

**Performance Concerns**:
- String concatenation in `_format_message` could be optimized
- No lazy evaluation for expensive log messages

**Missing Validation**:
- No validation of log_level parameter
- No check if root logger already configured

**Missing Error Handling**:
- No fallback if logging setup fails

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Implement proper context manager protocol for LogContext
2. Add JSON logging option for structured log aggregation
3. Add log rotation (RotatingFileHandler or TimedRotatingFileHandler)
4. Add PII/secret redaction filters
5. Use lazy formatting (`logger.info("msg %s", var)` instead of f-strings)
6. Add correlation ID injection via logging filters

---

### 3.2 Infrastructure Layer

#### File: app/infrastructure/http_client.py

**Purpose**: Reusable async HTTP client with retry logic and structured logging.

**Responsibilities**:
- Execute HTTP requests with retry logic
- Implement exponential backoff with jitter
- Provide structured logging for all requests
- Support JSON and streaming responses
- Handle timeouts and network errors

**Main Classes/Functions**:
- `HTTPClientError` - Custom exception
- `HTTPClient` - Main client class
  - `startup()` - Initialize client
  - `shutdown()` - Close client
  - `request()` - Generic request with retries
  - `post_json()` - POST with JSON response
  - `get_json()` - GET with JSON response
  - `stream()` - Streaming response

**Public API**:
- `HTTPClient` class with async methods
- `HTTPClientError` exception

**Internal Logic**:
1. `startup()` creates httpx.AsyncClient with configured timeout
2. `request()` implements retry loop:
   - Retry on timeout/network error (all methods)
   - Retry on 5xx for idempotent methods (GET, HEAD, OPTIONS)
   - Optional retry on 5xx for non-idempotent methods (if `retry_on_server_error=True`)
   - Exponential backoff: `base_delay * (2 ^ attempt)`
   - Jitter: ±10% of delay
3. `post_json()` / `get_json()` wrap `request()` with JSON parsing
4. `stream()` yields response chunks for streaming

**Inputs**: HTTP method, URL, headers, params, JSON data, files, correlation ID

**Outputs**: HTTP response or parsed JSON

**Dependencies**: httpx, asyncio, time, json

**Called By**: All services making HTTP calls (GeminiOrchestrator, CartBackendGateway, STT, TTS, Recovery)

**Uses**: httpx.AsyncClient, asyncio.sleep

**External Libraries**: httpx

**Potential Problems**:
- `_sleep_backoff()` uses `__import__('random').random()` which is unconventional
- No circuit breaker pattern (will retry even if service is down)
- No request/response size limits
- `stream()` doesn't implement retry logic
- No connection pooling configuration

**Security Concerns**:
- No TLS certificate validation configuration
- No request signing for sensitive endpoints
- Headers not sanitized before logging (could leak auth tokens)

**Performance Concerns**:
- Sequential retry logic (no parallel retries)
- No connection pool size configuration
- No keep-alive configuration
- Logging every request could impact performance at high volume

**Missing Validation**:
- No validation of URL format
- No validation of HTTP method
- No validation of JSON data before sending
- No timeout per retry attempt (only overall timeout)

**Missing Error Handling**:
- No handling of HTTP/2 errors
- No handling of proxy errors
- No handling of DNS resolution failures specifically

**Dead Code**: None

**Duplicate Logic**:
- `_log_fields()` called in multiple places with similar parameters
- Retry logic duplicated in `request()` for different exception types

**Suggested Improvements**:
1. Use `import random` instead of `__import__('random')`
2. Add circuit breaker pattern (e.g., pybreaker)
3. Add request/response size limits
4. Implement retry in `stream()` method
5. Add connection pool configuration
6. Sanitize headers before logging (remove Authorization, etc.)
7. Add keep-alive configuration
8. Add metrics for request latency, retry count
9. Consider using tenacity library for retry logic

---

#### File: app/infrastructure/redis_client.py

**Purpose**: Async Redis client for session and cart persistence with Phase 2 enhancements.

**Responsibilities**:
- Manage Redis connections
- Provide session state CRUD operations
- Provide cart snapshot CRUD operations
- Manage audio buffer metadata
- Manage recovery markers with deduplication
- Implement distributed locking with Lua scripts
- Provide pipeline support for atomic operations
- Manage session active/inactive state

**Main Classes/Functions**:
- `RedisClient` - Main client class
  - `connect()` / `disconnect()` - Connection management
  - `is_connected()` - Health check
  - Session methods: `save_session_state`, `load_session_state`, `delete_session_state`
  - Cart methods: `save_cart_snapshot`, `load_cart_snapshot`, `delete_cart_snapshot`
  - Audio methods: `append_audio_buffer_metadata`, `get_audio_buffer_metadata`
  - Recovery methods: `schedule_recovery_marker`, `cancel_recovery_marker`, `check_recovery_marker`, `get_recovery_marker`, `mark_recovery_completed`
  - Session state methods: `mark_session_active/inactive`, `is_session_active`
  - Message methods: `save_last_user_message`, `load_last_user_message`, etc.
  - Locking: `acquire_lock`, `release_lock`
  - Pipeline: `pipeline()` context manager
  - Atomic: `save_session_state_atomic()`

**Public API**:
- All methods listed above

**Internal Logic**:
1. `_build_key()` constructs Redis keys with prefix pattern
2. `_serialize()` / `_deserialize()` handle JSON conversion
3. Locking uses `SET key value NX EX` for acquire, Lua script for release
4. Pipeline context manager auto-executes on exit
5. `save_session_state_atomic()` uses pipeline for multi-key writes

**Inputs**: restaurant_id, session_id, data dictionaries, TTL values

**Outputs**: Serialized data, boolean results, lock values

**Dependencies**: redis.asyncio, json, uuid, datetime

**Called By**: SessionService, RecoveryService, MenuContextProvider, WebSocket endpoint

**Uses**: redis.Redis async client

**External Libraries**: redis

**Potential Problems**:
- `_serialize()` and `_deserialize()` are async but don't actually await anything (misleading signature)
- No connection pool configuration
- No handling of Redis cluster/sentinel
- `save_session_state_atomic()` doesn't handle partial failures
- Lock TTL is fixed at 10 seconds (not configurable)
- No handling of Redis memory pressure

**Security Concerns**:
- No Redis authentication configuration exposed
- No TLS configuration for Redis connections
- Keys are predictable (could be enumerated)

**Performance Concerns**:
- No pipelining for batch operations (except atomic method)
- No connection pooling
- Each method creates new Redis command (could batch)
- `load_session_state()` called multiple times in `append_turn()` (N+1 pattern)

**Missing Validation**:
- No validation of restaurant_id/session_id format
- No validation of TTL values (negative, zero, excessive)
- No validation of data size before serialization

**Missing Error Handling**:
- No handling of Redis connection drops during operations
- No handling of Redis memory limits
- No handling of key eviction

**Dead Code**: None

**Duplicate Logic**:
- Key building pattern repeated (centralized in `_build_key()` - good)
- JSON serialization repeated (centralized - good)

**Suggested Improvements**:
1. Make `_serialize()` / `_deserialize()` synchronous (remove async)
2. Add connection pool configuration
3. Add Redis cluster/sentinel support
4. Make lock TTL configurable
5. Add batch operations for common patterns
6. Add Redis memory monitoring
7. Add key TTL monitoring/alerting
8. Implement connection retry logic
9. Add metrics for Redis operations (latency, hit rate)

---

### 3.3 API Layer

#### File: app/api/websocket_endpoints.py

**Purpose**: WebSocket endpoint for AI Captain conversations with hardened runtime.

**Responsibilities**:
- Handle WebSocket connections at `/ws/captain/{restaurant_id}/{session_id}`
- Authenticate connections via JWT
- Create connection context
- Initialize WebSocket services (audio buffer, message router, handlers)
- Main message receive loop
- Route messages to handlers
- Handle disconnection and cleanup

**Main Classes/Functions**:
- `websocket_captain()` - WebSocket endpoint function
- `_get_runtime_services()` - Extract services from app state
- `_handle_disconnect()` - Cleanup on disconnect

**Public API**:
- WebSocket route: `/ws/captain/{restaurant_id}/{session_id}?token={jwt}`

**Internal Logic**:
1. Extract runtime services from app.state
2. Authenticate via WebSocketAuth
3. Accept WebSocket connection
4. Create ConnectionContext with unique connection_id
5. Initialize AudioBufferService and ResponseSender
6. Create MessageRouter and register handlers:
   - PingHandler
   - TextMessageHandler
   - AudioChunkHandler
   - AudioEndHandler
7. Cancel pending recovery for session
8. Mark session as active
9. Main loop:
   - Receive text message
   - Validate with Pydantic TypeAdapter
   - Route to handler
   - Execute handler
   - Catch and log errors
10. On disconnect:
    - Cleanup audio buffer
    - Mark session inactive
    - Schedule recovery

**Inputs**: WebSocket connection, restaurant_id, session_id, JWT token

**Outputs**: WebSocket messages (text, audio, cart updates, errors)

**Dependencies**:
- `app.core.constants.WS_CLOSE_UNAUTHORIZED`
- `app.core.logging.LogContext`
- `app.websocket.auth.WebSocketAuth, AuthResult`
- `app.websocket.connection_context.ConnectionContext`
- `app.websocket.audio_buffer_service.AudioBufferService`
- `app.websocket.message_router.MessageRouter`
- `app.websocket.handlers.*`
- `app.websocket.response_sender.ResponseSender`
- `app.schemas.websocket_schemas.IncomingMessage, MessageType, make_error`
- `pydantic.TypeAdapter, ValidationError`

**Called By**: FastAPI router, WebSocket client connections

**Uses**: FastAPI WebSocket, asyncio

**External Libraries**: fastapi, pydantic

**Potential Problems**:
- Import at bottom of file (`ResponseSender`) to avoid circular imports (code smell)
- No timeout on WebSocket receive_text() (could hang forever)
- No maximum message size validation
- No rate limiting on messages
- TypeAdapter created at module level (not thread-safe for dynamic schemas)
- `_get_runtime_services()` assumes app.state has all services (no validation)

**Security Concerns**:
- JWT token passed in query string (could be logged in server logs)
- No WebSocket message size limit (DoS risk)
- No rate limiting (could be flooded with messages)
- No origin validation beyond CORS

**Performance Concerns**:
- New MessageRouter created per connection (could be shared)
- New handlers created per connection (could pool)
- No connection limit enforcement
- No backpressure mechanism for slow clients

**Missing Validation**:
- No validation of restaurant_id/session_id format
- No validation of JWT token format before passing to auth
- No maximum connections per session
- No message rate limiting

**Missing Error Handling**:
- No handling of WebSocket state errors (sending to closed connection)
- No handling of malformed JSON (caught by TypeAdapter but could be more specific)
- No handling of Redis failures during cleanup

**Dead Code**: None

**Duplicate Logic**:
- Logging context creation repeated
- Error handling pattern repeated

**Suggested Improvements**:
1. Move ResponseSender import to top (refactor to avoid circular import)
2. Add timeout on `receive_text()`
3. Add maximum message size validation
4. Add rate limiting per connection
5. Add connection limit enforcement
6. Validate JWT format before authentication
7. Add WebSocket ping/pong keepalive
8. Add metrics for connection duration, message count
9. Consider pooling handlers instead of creating per connection

---

#### File: app/api/telegram_bot.py

**Purpose**: Telegram bot integration for Digital Captain using long polling.

**Responsibilities**:
- Create Telegram application with handlers
- Handle text messages from users
- Handle callback queries (confirm/cancel order)
- Render inline keyboards for order confirmation

**Main Classes/Functions**:
- `create_telegram_application()` - Factory for Telegram Application
- `handle_text_message()` - Process user text messages
- `handle_callback_query()` - Handle button callbacks
- `_should_render_action_buttons()` - Determine if action buttons should be shown

**Public API**:
- `create_telegram_application()` - Returns configured Telegram Application

**Internal Logic**:
1. `create_telegram_application()`:
   - Create Application with bot token
   - Add MessageHandler for text (excluding commands)
   - Add CallbackQueryHandler for confirm/cancel buttons
2. `handle_text_message()`:
   - Extract chat_id as session_id
   - Call GeminiOrchestrator.process_message()
   - Render inline keyboard if response contains cart or checkout keywords
   - Reply with assistant text
3. `handle_callback_query()`:
   - Answer callback query
   - Edit message based on callback data (confirm/cancel)

**Inputs**: Telegram updates (messages, callback queries)

**Outputs**: Telegram replies, edited messages

**Dependencies**:
- `app.core.config.Settings`
- `app.infrastructure.http_client.HTTPClient`
- `app.services.gemini_orchestrator.GeminiOrchestrator`
- `app.services.session_service.SessionService`
- `telegram` library (Application, handlers, etc.)

**Called By**: TelegramIntegration.service

**Uses**: python-telegram-bot library

**External Libraries**: python-telegram-bot

**Potential Problems**:
- Hardcoded DEFAULT_RESTAURANT_ID ("default_restaurant") - not multi-tenant
- No session cleanup on bot conversation end
- No rate limiting on bot responses
- Callback query handling is simplistic (no actual order confirmation logic)
- No handling of bot commands (/start, /help, etc.)
- No user authentication/authorization

**Security Concerns**:
- No validation of callback query data (could be tampered)
- No rate limiting (could be spammed)
- No user session management (relies on chat_id only)
- No webhook signature verification

**Performance Concerns**:
- No caching of menu context (each message fetches from orchestrator)
- No connection pooling for Telegram API

**Missing Validation**:
- No validation of update.effective_chat
- No validation of callback_data format
- No handling of edited messages

**Missing Error Handling**:
- No handling of Telegram API errors (rate limits, timeouts)
- No handling of Gemini orchestrator failures (partially handled)
- No handling of session service failures

**Dead Code**: None

**Duplicate Logic**:
- Error message strings duplicated

**Suggested Improvements**:
1. Make DEFAULT_RESTAURANT_ID configurable or derive from context
2. Add bot commands (/start, /help, /cancel)
3. Implement proper session management for Telegram users
4. Add rate limiting per user
5. Add webhook signature verification
6. Implement actual order confirmation logic (not just text editing)
7. Add handling for edited messages, channel posts
8. Add user authentication/authorization
9. Add metrics for bot usage

---

### 3.4 WebSocket Layer

#### File: app/websocket/auth.py

**Purpose**: WebSocket JWT authentication and authorization.

**Responsibilities**:
- Validate JWT tokens from query parameters
- Verify token payload matches URL parameters
- Enforce algorithm validation
- Handle authentication errors

**Main Classes/Functions**:
- `AuthResult` - Dataclass for authentication result
- `WebSocketAuth` - Authentication handler
  - `authenticate()` - Validate JWT token
  - `close_unauthorized()` - Close connection with error

**Public API**:
- `authenticate()` - Returns AuthResult
- `close_unauthorized()` - Closes WebSocket with 1008 code

**Internal Logic**:
1. Decode JWT with strict algorithm validation:
   - Enforce HS256 algorithm only
   - Require `exp` claim
   - Verify signature with WEBSOCKET_AUTH_SECRET
2. Extract restaurant_id and session_id from payload
3. Compare with expected values from URL parameters
4. Return AuthResult with success/failure

**Inputs**: WebSocket, JWT token, expected restaurant_id, expected session_id

**Outputs**: AuthResult dataclass

**Dependencies**:
- `app.core.config.Settings`
- `app.core.constants.WS_CLOSE_UNAUTHORIZED`
- `jwt` (PyJWT)

**Called By**: app/api/websocket_endpoints.py

**Uses**: PyJWT decode with algorithm enforcement

**External Libraries**: PyJWT

**Potential Problems**:
- Token passed in query string (visible in logs, browser history)
- No token refresh mechanism
- No revocation list
- No rate limiting on authentication attempts

**Security Concerns**:
- ✅ Algorithm validation prevents "alg: none" attacks
- ✅ Token expiration enforced
- ✅ Payload validated against URL parameters
- ⚠️ Token in query string could be logged by proxies/servers
- ⚠️ No token revocation (compromised tokens valid until expiry)
- ⚠️ No rate limiting (brute force risk)

**Performance Concerns**: None (lightweight operation)

**Missing Validation**:
- No validation of token format before decoding
- No handling of malformed tokens (relies on PyJWT exceptions)
- No maximum token age enforcement beyond exp claim

**Missing Error Handling**:
- Catches all exceptions but returns generic "Authentication error"
- No distinction between expired, invalid, malformed tokens in logs

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Move token from query string to WebSocket headers (if supported by client)
2. Add token revocation list (Redis-backed)
3. Add rate limiting on authentication attempts
4. Add maximum token age (e.g., reject tokens older than 24h even if not expired)
5. Add more specific error messages for debugging (without leaking info to client)
6. Consider adding IP-based rate limiting
7. Add authentication metrics (success/failure rate)

---

#### File: app/websocket/connection_context.py

**Purpose**: Per-connection state management for WebSocket connections.

**Responsibilities**:
- Hold all runtime context for a single connection
- Generate unique turn IDs for correlation
- Provide logging context

**Main Classes/Functions**:
- `ConnectionContext` - Dataclass with connection state
  - `generate_turn_id()` - Generate unique turn ID
  - `get_log_context()` - Get structured logging context

**Public API**:
- ConnectionContext dataclass with fields:
  - settings, session_service, gemini_orchestrator, stt_service, tts_service, recovery_service
  - restaurant_id, session_id
  - connection_id (UUID)
  - connected_at (timestamp)
  - turn_counter, current_turn_id
  - is_processing (bool)

**Internal Logic**:
1. Generate connection_id using UUID
2. Record connected_at timestamp
3. Generate turn IDs with format: `turn_{connection_id[:8]}_{counter:04d}`

**Inputs**: All service references, restaurant_id, session_id

**Outputs**: Turn IDs, logging context dictionaries

**Dependencies**: None (dataclass only)

**Called By**: app/api/websocket_endpoints.py

**Uses**: uuid, time, dataclasses

**External Libraries**: None

**Potential Problems**:
- Turn ID format includes connection_id prefix (could be predictable)
- turn_counter is not persisted (resets on reconnect)
- No connection timeout enforcement
- No maximum turn count

**Security Concerns**: None

**Performance Concerns**: None

**Missing Validation**:
- No validation of service references
- No validation of restaurant_id/session_id format

**Missing Error Handling**: N/A

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add connection timeout enforcement
2. Add maximum turns per connection
3. Add connection metadata (user agent, IP if available)
4. Consider persisting turn_counter in Redis for continuity across reconnects
5. Add connection state machine (connecting, active, closing, closed)

---

#### File: app/websocket/audio_buffer_service.py

**Purpose**: WebSocket audio buffer management with safety controls.

**Responsibilities**:
- Buffer audio chunks per connection
- Validate sequence order
- Enforce size limits
- Validate MIME type consistency
- Cleanup buffers on disconnect

**Main Classes/Functions**:
- `AudioBufferState` - Dataclass for buffer state
  - `reset()` - Clear buffer
  - `append_chunk()` - Add chunk with validation
  - `finalize()` - Prepare for transcription
- `AudioBufferService` - Service managing buffers
  - `create_buffer()` - Initialize new buffer
  - `get_buffer()` - Retrieve existing buffer
  - `append_chunk()` - Add chunk with size check
  - `finalize_buffer()` - Finalize for transcription
  - `cleanup()` - Remove buffer
  - `get_mime_type()` - Get buffer MIME type

**Public API**:
- All methods listed above

**Internal Logic**:
1. `AudioBufferState`:
   - Stores bytearray buffer, mime_type, sequence counter, size_bytes
   - Validates sequence order (no gaps, no duplicates)
   - Validates MIME type consistency (first chunk sets MIME type)
   - Tracks size to enforce limits
2. `AudioBufferService`:
   - Maintains dict of buffers keyed by connection_id
   - Enforces MAX_AUDIO_BUFFER_BYTES limit
   - Logs buffer operations

**Inputs**: connection_id, chunk_bytes, mime_type, sequence number

**Outputs**: Buffer state, success/failure tuples

**Dependencies**: app.core.config.Settings

**Called By**: AudioChunkHandler, AudioEndHandler

**Uses**: bytearray, dataclasses

**External Libraries**: None

**Potential Problems**:
- Buffers stored in memory (not Redis) - lost on service restart
- No cleanup of old buffers (memory leak if connections not properly closed)
- Sequence validation is strict (no recovery from missed chunks)
- MIME type validation only allows wav/webm (despite STT supporting more)

**Security Concerns**:
- Size limit prevents DoS via large audio
- Sequence validation prevents chunk injection
- ⚠️ No validation of audio content (could be malicious files)

**Performance Concerns**:
- In-memory storage limits horizontal scaling
- No compression of buffered audio
- Buffer cleanup relies on explicit calls (could leak)

**Missing Validation**:
- No validation of chunk size (individual chunks could be large)
- No validation of audio format beyond MIME type
- No validation of sequence gaps (could skip sequences)

**Missing Error Handling**:
- No handling of memory pressure
- No handling of corrupted audio data

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add buffer TTL with automatic cleanup
2. Add maximum chunk size validation
3. Support additional MIME types (mp3, ogg, flac)
4. Add audio content validation (magic bytes)
5. Consider Redis-backed buffers for horizontal scaling
6. Add buffer compression
7. Add metrics for buffer size, chunk count

---

#### File: app/websocket/message_router.py

**Purpose**: WebSocket message routing and dispatch.

**Responsibilities**:
- Route incoming messages to appropriate handlers
- Validate message types
- Provide extensible handler registration

**Main Classes/Functions**:
- `MessageHandler` - Base class for handlers
- `RoutedMessage` - Dataclass for routing result
- `MessageRouter` - Router implementation
  - `register_handler()` - Register handler for message type
  - `route()` - Route message to handler

**Public API**:
- `MessageRouter` class
- `MessageHandler` base class

**Internal Logic**:
1. Maintain dict of MessageType → MessageHandler
2. `register_handler()` adds handler to registry
3. `route()` looks up handler by message type, returns RoutedMessage or None

**Inputs**: IncomingMessage (Pydantic model)

**Outputs**: RoutedMessage or None

**Dependencies**: app.schemas.websocket_schemas.IncomingMessage, MessageType

**Called By**: app/api/websocket_endpoints.py

**Uses**: dict, dataclasses

**External Libraries**: None

**Potential Problems**:
- No default handler for unregistered message types (returns None)
- No handler priority/ordering
- No middleware support

**Security Concerns**: None

**Performance Concerns**: None (simple dict lookup)

**Missing Validation**:
- No validation that handler is callable
- No validation of message type before routing

**Missing Error Handling**: None

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add default handler for unregistered types
2. Add handler priority/ordering
3. Add middleware support (e.g., for logging, metrics)
4. Add handler execution timeout
5. Consider using enum for handler registration

---

#### File: app/websocket/handlers.py

**Purpose**: WebSocket message handlers for different message types.

**Responsibilities**:
- Handle ping messages (respond with pong)
- Handle text messages (process through Gemini)
- Handle audio chunks (buffer for transcription)
- Handle audio end (transcribe and process)

**Main Classes/Functions**:
- `PingHandler` - Respond to ping with pong
- `TextMessageHandler` - Process text through Gemini orchestrator
- `AudioChunkHandler` - Buffer audio chunks
- `AudioEndHandler` - Finalize audio, transcribe, process as text

**Public API**:
- All handler classes with `handle()` method

**Internal Logic**:
1. `PingHandler.handle()` - Send pong response
2. `TextMessageHandler.handle()`:
   - Validate text not empty
   - Call orchestrator.process_user_message()
   - Send assistant text
   - Save cart snapshot
   - Send cart update events
   - Check for offer code applications
   - Stream TTS if available
3. `AudioChunkHandler.handle()`:
   - Decode base64 audio
   - Validate MIME type
   - Append to audio buffer
4. `AudioEndHandler.handle()`:
   - Finalize audio buffer
   - Transcribe via STT
   - Create TextMessageHandler and process transcript

**Inputs**: IncomingMessage (typed by handler)

**Outputs**: WebSocket responses via ResponseSender

**Dependencies**:
- app.websocket.connection_context.ConnectionContext
- app.websocket.audio_buffer_service.AudioBufferService
- app.websocket.response_sender.ResponseSender
- app.schemas.websocket_schemas.IncomingMessage, MessageType, make_offer_applied
- app.services.gemini_orchestrator.GeminiOrchestrator
- app.services.session_service.SessionService
- app.services.stt_service.STTService
- app.services.tts_service.TTSService

**Called By**: MessageRouter

**Uses**: base64, logging

**External Libraries**: None

**Potential Problems**:
- TextMessageHandler imports base64 inside method (should be at top)
- AudioEndHandler creates new TextMessageHandler instance (could reuse)
- No timeout on orchestrator processing (relies on TurnProcessor)
- TTS streaming errors only logged (not sent to client)
- Cart snapshot saved even if cart_events empty

**Security Concerns**:
- No validation of assistant_text length (could be very long)
- No validation of cart snapshot size
- Base64 decoding without size validation

**Performance Concerns**:
- New TextMessageHandler created in AudioEndHandler (object creation overhead)
- Sequential cart event sending (could batch)
- TTS streaming sends chunks one-by-one (could buffer)

**Missing Validation**:
- No validation of orchestrator result structure
- No validation of cart event structure
- No validation of offer code application structure

**Missing Error Handling**:
- TTS streaming errors only logged (client never notified)
- Cart snapshot save failures not handled
- Offer code application errors not handled

**Dead Code**: None

**Duplicate Logic**:
- Logging context creation repeated
- Error handling pattern repeated

**Suggested Improvements**:
1. Move base64 import to top of file
2. Add timeout on orchestrator calls
3. Send TTS errors to client
4. Batch cart event sending
5. Add validation of orchestrator results
6. Consider batching TTS chunks
7. Add metrics for handler execution time

---

#### File: app/websocket/response_sender.py

**Purpose**: WebSocket response sending with structured messages.

**Responsibilities**:
- Send all WebSocket message types
- Handle WebSocket disconnection gracefully
- Log all sent messages

**Main Classes/Functions**:
- `ResponseSender` - Response sender
  - `send_text()` - Send assistant text
  - `send_audio_chunk()` - Send TTS audio chunk
  - `send_cart_update()` - Send cart update event
  - `send_error()` - Send error message
  - `send_pong()` - Send pong response
  - `send_raw()` - Send raw JSON

**Public API**:
- All send_* methods

**Internal Logic**:
1. Each method creates appropriate Pydantic model
2. Serializes to JSON
3. Sends via WebSocket
4. Logs success/failure
5. Catches WebSocketDisconnect and RuntimeError

**Inputs**: Message data (text, audio, payloads)

**Outputs**: WebSocket messages

**Dependencies**: app.schemas.websocket_schemas (all make_* functions)

**Called By**: All handlers

**Uses**: fastapi.WebSocket, base64

**External Libraries**: fastapi

**Potential Problems**:
- No send timeout (could block indefinitely)
- No message queue (if WebSocket is slow, handlers block)
- No backpressure handling

**Security Concerns**:
- No validation of message size before sending
- No sanitization of error messages (could leak info)

**Performance Concerns**:
- Sequential sending (no parallelization)
- No message batching
- No send timeout

**Missing Validation**:
- No validation of message content before sending
- No maximum message size check

**Missing Error Handling**:
- Only catches WebSocketDisconnect and RuntimeError
- No handling of other WebSocket errors

**Dead Code**: None

**Duplicate Logic**:
- Error handling pattern repeated in all methods

**Suggested Improvements**:
1. Add send timeout
2. Add message queue for backpressure
3. Add message size validation
4. Add batch send method
5. Add metrics for send latency, failures
6. Extract common error handling to reduce duplication

---

#### File: app/websocket/turn_processor.py

**Purpose**: Per-session serialized turn processing with correlation IDs.

**Responsibilities**:
- Serialize turn processing per session (no concurrent turns)
- Generate unique turn IDs
- Enforce processing timeout
- Track processing time
- Return structured results

**Main Classes/Functions**:
- `TurnResult` - Dataclass for turn result
- `TurnProcessor` - Turn processing orchestrator
  - `process_turn()` - Process turn with locking and timeout
  - `_execute_turn()` - Actual turn logic (base implementation)

**Public API**:
- `process_turn()` - Main entry point
- `TurnResult` - Result dataclass

**Internal Logic**:
1. Generate turn ID via ConnectionContext
2. Log turn start
3. Acquire per-session lock (asyncio.Lock)
4. Set timeout (30 seconds)
5. Execute turn logic
6. Track processing time
7. Log completion
8. Handle timeout and errors
9. Release lock in finally block

**Inputs**: IncomingMessage

**Outputs**: TurnResult

**Dependencies**: app.websocket.connection_context.ConnectionContext, app.schemas.websocket_schemas.IncomingMessage

**Called By**: Not directly used (handlers use orchestrator directly)

**Uses**: asyncio, time, dataclasses

**External Libraries**: None

**Potential Problems**:
- TurnProcessor not actually used in current code (handlers call orchestrator directly)
- Timeout hardcoded to 30 seconds
- Lock is per-ConnectionContext (not shared across reconnects)
- No cancellation token support

**Security Concerns**: None

**Performance Concerns**:
- Lock serializes all turns (could bottleneck)
- No priority for urgent messages

**Missing Validation**:
- No validation of message before processing

**Missing Error Handling**: None (comprehensive)

**Dead Code**: 
- `TurnProcessor` class not used in current implementation
- `_execute_turn()` raises NotImplementedError

**Duplicate Logic**: None

**Suggested Improvements**:
1. Integrate TurnProcessor into handlers (or remove if not needed)
2. Make timeout configurable via settings
3. Add cancellation token support
4. Add turn priority (e.g., audio_end > text)
5. Add metrics for turn queue time, processing time
6. Consider distributed lock for multi-instance deployments

---

### 3.5 Services Layer

#### File: app/services/gemini_orchestrator.py

**Purpose**: Gemini-based conversation orchestrator with decomposed architecture.

**Responsibilities**:
- Orchestrate multi-turn conversations with Gemini
- Manage conversation history
- Execute tool calls from LLM
- Coordinate with PromptBuilder, MenuContextProvider, CartBackendGateway
- Implement retry logic for transient errors
- Persist conversation turns

**Main Classes/Functions**:
- `GeminiOrchestratorError` - Custom exception
- `GeminiOrchestrator` - Main orchestrator
  - `__init__()` - Initialize components, register tools
  - `process_user_message()` - Process user message with full orchestration
  - `_create_cart_tool()` - Create cart update tool callable
  - `_create_offer_code_tool()` - Create offer code validation tool
  - `_retryable()` - Generic retry wrapper

**Public API**:
- `process_user_message()` - Main entry point
- `process_message()` - Alias for process_user_message

**Internal Logic**:
1. Initialize decomposed components:
   - PromptBuilder for system prompts
   - MenuContextProvider for menu data
   - CartBackendGateway for cart operations
   - ToolExecutionCoordinator for tool execution
2. Register tools with coordinator:
   - update_cart (always)
   - validate_offer_code (if ENABLE_OFFER_CODES)
3. `process_user_message()`:
   - Generate turn_id if not provided
   - Get menu context from provider
   - Build system prompt and history
   - Prepare tools for Gemini
   - Start chat with history and tools
   - Send user message with retry
   - Handle function call if present:
     - Parse arguments
     - Inject restaurant_id/session_id
     - Execute tool via coordinator
     - Collect cart events and snapshots
     - Get follow-up response from model
   - Extract assistant text
   - Set default responses if empty
   - Persist conversation turn
   - Save cart snapshot
4. `_retryable()`:
   - Retry on rate limit (429) and timeout errors
   - Exponential backoff with jitter
   - Max 3 retries

**Inputs**: restaurant_id, session_id, user_message, optional turn_id

**Outputs**: Dictionary with assistant_text, cart_events, tool_results, cart_snapshot, turn_id

**Dependencies**:
- app.core.config.Settings
- app.core.constants.TOOL_NAME_UPDATE_CART
- app.services.session_service.SessionService
- app.services.prompt_builder.PromptBuilder
- app.services.menu_context_provider.MenuContextProvider
- app.services.cart_backend_gateway.CartBackendGateway
- app.services.tool_execution_coordinator.ToolExecutionCoordinator
- app.infrastructure.http_client.HTTPClient
- app.infrastructure.redis_client.RedisClient
- google.generativeai

**Called By**: TextMessageHandler, Telegram bot handler

**Uses**: google.generativeai, asyncio, json

**External Libraries**: google-generativeai

**Potential Problems**:
- Tool definitions hardcoded in method (should be externalized)
- Gemini API version compatibility issues (start_chat sync vs async)
- No handling of Gemini content filtering
- No handling of Gemini safety settings
- Tool arguments parsing assumes dict or string (no validation)
- Fallback to `genai.GenerativeModel()` without model name on error (could use wrong model)
- No handling of Gemini quota limits

**Security Concerns**:
- Tool arguments from LLM not validated before execution (relies on ToolExecutionCoordinator)
- No content filtering on user input or LLM output
- System prompt injection risk if menu_context is malicious

**Performance Concerns**:
- Menu context fetched for every message (cached but still HTTP call on miss)
- Sequential tool execution (no parallel tool calls)
- Conversation history grows unbounded (no summarization)
- No streaming of LLM responses (waits for complete response)

**Missing Validation**:
- No validation of Gemini response structure
- No validation of tool arguments before execution
- No validation of menu_context structure

**Missing Error Handling**:
- No handling of Gemini content filtering blocks
- No handling of Gemini safety setting violations
- No handling of token limit exceeded

**Dead Code**: None

**Duplicate Logic**:
- Retry logic similar to HTTPClient (could extract to shared utility)
- Error handling pattern repeated

**Suggested Improvements**:
1. Externalize tool definitions to configuration
2. Add content filtering configuration
3. Add safety settings configuration
4. Implement conversation history summarization
5. Add streaming LLM responses
6. Add validation of tool arguments before execution
7. Add handling of Gemini quota limits
8. Add metrics for LLM latency, token usage
9. Consider parallel tool execution
10. Add fallback model configuration

---

#### File: app/services/prompt_builder.py

**Purpose**: Prompt construction for Gemini orchestrator.

**Responsibilities**:
- Build system prompts
- Integrate session notes
- Format menu context
- Keep prompts concise to avoid token inflation

**Main Classes/Functions**:
- `PromptBuilder` - Prompt construction
  - `build_system_prompt()` - Build complete system prompt
  - `build_initial_history()` - Build initial conversation history
- `_serialize_menu_reference()` - Create lightweight menu reference

**Public API**:
- `build_system_prompt()` - Returns system prompt string
- `build_initial_history()` - Returns list of history messages

**Internal Logic**:
1. `build_system_prompt()`:
   - Start with base system prompt (CAPTAIN_SYSTEM_PROMPT)
   - Append session notes if provided
2. `build_initial_history()`:
   - Create system message with prompt
   - Create system message with menu reference (not full menu)
3. `_serialize_menu_reference()`:
   - Create lightweight reference with restaurant_id and "server_side_menu"
   - Avoids inlining full menu (token inflation)

**Inputs**: Optional session notes, menu_context dict, system prompt

**Outputs**: System prompt string, history list

**Dependencies**: app.core.constants.CAPTAIN_SYSTEM_PROMPT

**Called By**: GeminiOrchestrator

**Uses**: str, dict

**External Libraries**: None

**Potential Problems**:
- Menu reference is a placeholder ("server_side_menu") - actual menu not sent to LLM
- System prompt is static (no personalization)
- No prompt versioning
- No A/B testing support

**Security Concerns**:
- System prompt could be injected if menu_context is malicious (though it's just a reference)

**Performance Concerns**:
- System prompt is 50 lines (could be optimized)
- No token counting/optimization

**Missing Validation**:
- No validation of session notes length
- No validation of menu_context structure

**Missing Error Handling**: N/A

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Externalize system prompt to file/database
2. Add prompt versioning
3. Add A/B testing framework for prompts
4. Add token counting and optimization
5. Add prompt templates with variable interpolation
6. Consider sending actual menu data instead of reference (if token budget allows)

---

#### File: app/services/menu_context_provider.py

**Purpose**: Menu context retrieval and caching for Gemini orchestrator.

**Responsibilities**:
- Retrieve menu data for restaurants
- Implement multi-level caching (memory + Redis)
- Provide mock data for development
- Fallback to mock on backend failure

**Main Classes/Functions**:
- `MenuContextProvider` - Abstract base class
- `MockMenuContextProvider` - Mock implementation with hardcoded menu
- `LaravelMenuContextProvider` - Production implementation with caching
- `create_menu_context_provider()` - Factory function

**Public API**:
- `get_menu_context()` - Retrieve menu for restaurant

**Internal Logic**:
1. `MockMenuContextProvider`:
   - Returns hardcoded Arabic menu (Captain Burger)
   - Includes categories, dishes, addons, prices, allergens
2. `LaravelMenuContextProvider`:
   - Check in-memory cache (5 min TTL)
   - Check Redis cache (5 min TTL)
   - Fetch from Laravel backend if cache miss
   - Normalize response (add external_price, ratings)
   - Cache in memory and Redis
   - Fallback to mock on error
3. `create_menu_context_provider()`:
   - Return MockMenuContextProvider if use_mock or no LARAVEL_BACKEND_URL
   - Return LaravelMenuContextProvider otherwise

**Inputs**: restaurant_id

**Outputs**: Menu context dictionary

**Dependencies**:
- app.infrastructure.http_client.HTTPClient
- app.infrastructure.redis_client.RedisClient
- app.core.config.Settings

**Called By**: GeminiOrchestrator

**Uses**: time, abc.ABC

**External Libraries**: None

**Potential Problems**:
- In-memory cache not shared across instances (each instance has own cache)
- Cache key uses restaurant_id for session state (confusing naming)
- Redis cache uses `save_session_state()` which is semantically wrong (should be dedicated menu cache method)
- Fallback to mock on error could mask backend issues
- No cache invalidation on menu updates
- Mock menu is hardcoded in Python (not externalized)

**Security Concerns**:
- No validation of menu data from backend (could be malicious)
- No signature verification of menu data

**Performance Concerns**:
- In-memory cache improves performance but not shared
- Redis cache adds latency on miss
- No cache warming

**Missing Validation**:
- No validation of restaurant_id format
- No validation of menu data structure from backend
- No validation of cache data structure

**Missing Error Handling**:
- Fallback to mock on any error (could hide issues)
- No alerting on cache failures

**Dead Code**: None

**Duplicate Logic**:
- Cache TTL hardcoded in multiple places (300 seconds)

**Suggested Improvements**:
1. Use dedicated Redis key for menu cache (not session state)
2. Add cache invalidation mechanism
3. Add cache warming on startup
4. Externalize mock menu to JSON file
5. Add validation of menu data structure
6. Add cache metrics (hit rate, miss rate)
7. Consider using Redis hash for menu data
8. Add cache stampede protection (e.g., probabilistic early expiration)

---

#### File: app/services/cart_backend_gateway.py

**Purpose**: Cart backend gateway with idempotency support and validation.

**Responsibilities**:
- Update cart with idempotency
- Validate addons
- Validate offer codes
- Get session orders
- Generate idempotency keys
- Handle Laravel backend errors

**Main Classes/Functions**:
- `CartBackendGateway` - Gateway for cart operations
  - `update_cart()` - Update cart with idempotency
  - `_validate_addons()` - Validate addon selections
  - `validate_offer_code()` - Validate promo codes
  - `get_session_order()` - Get order for session
  - `_generate_idempotency_key()` - Generate SHA256 idempotency key

**Public API**:
- All methods listed above

**Internal Logic**:
1. `_generate_idempotency_key()`:
   - Create stable input: `{session_id}:{turn_id}:{action}:{dish_id}:{quantity}`
   - SHA256 hash, take first 32 chars
   - Prefix with `cart_mutation:`
2. `update_cart()`:
   - Generate idempotency key
   - Validate addons (basic structural validation)
   - Build payload with all fields
   - Send POST to Laravel with idempotency headers
   - Handle Laravel error codes (DISH_NOT_AVAILABLE, etc.)
   - Return structured result
3. `_validate_addons()`:
   - Basic validation: ensure addon_id present
   - Note: Full validation requires Laravel endpoint (not implemented)
4. `validate_offer_code()`:
   - POST to Laravel offer validation endpoint
   - Return validation result
5. `get_session_order()`:
   - GET from Laravel session order endpoint
   - Return order data

**Inputs**: session_id, turn_id, restaurant_id, action, dish_id, quantity, notes, addons

**Outputs**: Cart update result, offer validation result, order data

**Dependencies**:
- app.infrastructure.http_client.HTTPClient, HTTPClientError
- app.core.config.Settings
- app.core.constants (error codes)

**Called By**: ToolExecutionCoordinator, cart_tools.py

**Uses**: hashlib, time

**External Libraries**: None (uses HTTPClient)

**Potential Problems**:
- Addon validation is incomplete (only checks addon_id exists, not if valid for dish)
- No client-side price calculation (relies on Laravel)
- No handling of Laravel schema changes
- Idempotency key doesn't include notes or addons (could cause issues if those change)
- No timeout configuration (uses HTTPClient default)

**Security Concerns**:
- ✅ Idempotency keys prevent duplicate mutations
- ✅ Cross-tenant validation delegated to Laravel (critical)
- ⚠️ No client-side validation of dish availability
- ⚠️ No client-side validation of addon-dish relationship

**Performance Concerns**:
- Sequential HTTP calls (no parallel cart updates)
- No caching of dish/addon validation

**Missing Validation**:
- No validation of action enum (add/remove/update)
- No validation of dish_id > 0
- No validation of quantity >= 0
- No validation of notes length
- No validation of addons structure

**Missing Error Handling**:
- No handling of Laravel 500 errors specifically
- No handling of Laravel timeout
- No fallback if Laravel is down

**Dead Code**: None

**Duplicate Logic**:
- Error code checking repeated

**Suggested Improvements**:
1. Complete addon validation (call Laravel validation endpoint)
2. Add client-side price calculation for validation
3. Include notes and addons in idempotency key
4. Add timeout configuration
5. Add circuit breaker for Laravel backend
6. Add validation of all input parameters
7. Add metrics for cart update latency, success rate
8. Consider caching dish/addon metadata

---

#### File: app/services/tool_execution_coordinator.py

**Purpose**: Tool execution coordination with validation.

**Responsibilities**:
- Register tools for execution
- Validate tool existence
- Execute tools with proper context
- Handle errors gracefully
- Return structured results

**Main Classes/Functions**:
- `ToolExecutionCoordinator` - Tool coordinator
  - `register_tool()` - Register tool callable
  - `get_tool()` - Get tool by name
  - `has_tool()` - Check if tool exists
  - `execute_tool()` - Execute tool with validation

**Public API**:
- All methods listed above

**Internal Logic**:
1. Maintain dict of tool_name → callable
2. `register_tool()` adds to registry
3. `execute_tool()`:
   - Look up tool by name
   - Inject turn_id if not in arguments
   - Execute tool with arguments
   - Return result or error

**Inputs**: tool_name, turn_id, arguments dict

**Outputs**: Tool execution result dict

**Dependencies**: app.services.cart_backend_gateway.CartBackendGateway

**Called By**: GeminiOrchestrator

**Uses**: typing, logging

**External Libraries**: None

**Potential Problems**:
- No validation of tool arguments before execution
- No timeout on tool execution
- No retry logic for tool execution
- Tools registered at startup (no dynamic registration)

**Security Concerns**:
- Tool arguments from LLM not validated (relies on tool implementation)
- No sandboxing of tool execution

**Performance Concerns**: None

**Missing Validation**:
- No validation of tool_name format
- No validation of arguments structure
- No validation of turn_id format

**Missing Error Handling**:
- Catches all exceptions but returns generic error
- No distinction between validation errors, execution errors, etc.

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add tool argument validation (Pydantic schemas per tool)
2. Add timeout on tool execution
3. Add retry logic for transient failures
4. Add tool execution metrics
5. Add tool whitelist/blacklist
6. Consider dynamic tool registration

---

#### File: app/services/session_service.py

**Purpose**: Session state persistence and management with turn-level tracking.

**Responsibilities**:
- Start/get/end sessions
- Persist conversation turns
- Save/load cart snapshots
- Manage session active/inactive state
- Build recovery payloads
- Link orders to sessions

**Main Classes/Functions**:
- `SessionService` - Session management
  - `start_session()` - Initialize session
  - `get_session_context()` - Get full session context
  - `append_turn()` - Add turn to history
  - `persist_conversation_turn()` - Save complete turn
  - `save_cart_snapshot()` / `load_cart_snapshot()` - Cart persistence
  - `mark_session_active/inactive()` - Session state
  - `build_recovery_payload()` - Build recovery webhook payload
  - `link_order_to_session()` - Link order to session
  - `get_linked_order()` - Get linked order

**Public API**:
- All methods listed above

**Internal Logic**:
1. `start_session()`:
   - Create metadata with timestamps, turn_count=0
   - Save to Redis
   - Mark as active
2. `get_session_context()`:
   - Load session metadata and cart snapshot
   - Combine into context dict
3. `append_turn()`:
   - Create turn data with user/assistant messages
   - Save to Redis (overwrites last_turn)
   - Update turn_count and last_activity
4. `persist_conversation_turn()`:
   - Generate turn_id if not provided
   - Save last user/assistant messages
   - Append turn to history
5. `build_recovery_payload()`:
   - Load last messages, cart snapshot, recovery marker
   - Build payload with event_id, timestamps
6. `link_order_to_session()`:
   - Store order_id in Redis with TTL
   - Update session metadata with order_id

**Inputs**: restaurant_id, session_id, various session data

**Outputs**: Session context, recovery payloads, order IDs

**Dependencies**: app.infrastructure.redis_client.RedisClient

**Called By**: GeminiOrchestrator, WebSocket endpoint, RecoveryService

**Uses**: uuid, datetime

**External Libraries**: None

**Potential Problems**:
- Direct access to `redis_client._ensure_client()` in link_order_to_session() and get_linked_order() (breaks encapsulation)
- Turn history not actually stored as list (overwrites last_turn each time)
- No session expiration enforcement (relies on Redis TTL)
- No session cleanup on order completion
- Order linking uses hardcoded Redis key pattern (not using _build_key)

**Security Concerns**:
- No validation of order_id format
- No authorization check for order access

**Performance Concerns**:
- Multiple Redis calls per turn (N+1 pattern)
- No batching of Redis operations
- `append_turn()` loads and saves session metadata (2 operations)

**Missing Validation**:
- No validation of restaurant_id/session_id format
- No validation of turn_id format
- No validation of message lengths

**Missing Error Handling**:
- No handling of Redis failures during critical operations
- No fallback if session state is corrupted

**Dead Code**: None

**Duplicate Logic**:
- Redis key building duplicated in link_order_to_session()

**Suggested Improvements**:
1. Use RedisClient public API instead of _ensure_client()
2. Implement actual turn history as Redis list
3. Add session expiration enforcement
4. Add session cleanup on order completion
5. Use _build_key() for order keys
6. Batch Redis operations with pipeline
7. Add session metrics (active count, average duration)
8. Add session state validation

---

#### File: app/services/recovery_service.py

**Purpose**: Abandoned cart recovery service with deduplication.

**Responsibilities**:
- Schedule recovery for abandoned carts
- Execute recovery after delay
- Deduplicate recovery webhooks
- Send recovery webhooks to Laravel
- Cancel recovery on session reactivation

**Main Classes/Functions**:
- `RecoveryServiceError` - Custom exception
- `RecoveryService` - Recovery management
  - `schedule_recovery()` - Schedule recovery with deduplication
  - `_execute_recovery_if_abandoned()` - Execute recovery after delay
  - `_send_recovery_webhook()` - Send webhook to Laravel
  - `cancel_recovery()` - Cancel pending recovery
  - `get_recovery_status()` - Get recovery status

**Public API**:
- All methods listed above

**Internal Logic**:
1. `schedule_recovery()`:
   - Check if recovery already scheduled/completed
   - Create recovery marker in Redis with TTL
   - Create background asyncio task
   - Task waits for delay, then checks if session still abandoned
2. `_execute_recovery_if_abandoned()`:
   - Wait for RECOVERY_DELAY_SECONDS
   - Check if recovery marker still exists
   - Check if session reactivated
   - Check if already completed
   - Build recovery payload
   - Send webhook to Laravel
   - Mark as completed
3. `_send_recovery_webhook()`:
   - POST to Laravel abandoned cart endpoint
   - Raise RecoveryServiceError on failure

**Inputs**: restaurant_id, session_id, recovery payload

**Outputs**: Recovery status, webhook delivery

**Dependencies**:
- app.core.config.Settings
- app.infrastructure.http_client.HTTPClient, HTTPClientError
- app.infrastructure.redis_client.RedisClient
- app.services.session_service.SessionService

**Called By**: WebSocket endpoint (on disconnect)

**Uses**: asyncio, uuid, datetime

**External Libraries**: None

**Potential Problems**:
- Background tasks stored in dict (lost on service restart)
- No persistence of scheduled tasks (could lose recovery on restart)
- Task cancellation not guaranteed (could leak tasks)
- No retry on webhook delivery failure
- No dead letter queue for failed webhooks
- Recovery delay is fixed (not configurable per restaurant)

**Security Concerns**:
- No webhook signature verification (relies on Laravel to verify)
- No authentication on recovery endpoint (relies on network security)

**Performance Concerns**:
- In-memory task tracking doesn't scale horizontally
- No batching of recovery webhooks
- No rate limiting on webhook sends

**Missing Validation**:
- No validation of recovery payload structure
- No validation of webhook response

**Missing Error Handling**:
- No retry on webhook failure
- No dead letter queue
- No alerting on webhook failures

**Dead Code**: None

**Duplicate Logic**:
- Logging context creation repeated

**Suggested Improvements**:
1. Persist scheduled tasks in Redis (for recovery after restart)
2. Add webhook retry with exponential backoff
3. Add dead letter queue for failed webhooks
4. Add webhook signature verification
5. Add recovery delay configuration per restaurant
6. Add batch webhook sending
7. Add metrics for recovery success rate, latency
8. Consider using Celery/ARQ for background tasks

---

#### File: app/services/stt_service.py

**Purpose**: Speech-to-Text service using Groq Whisper.

**Responsibilities**:
- Transcribe audio bytes to text
- Validate audio format and size
- Call Groq Whisper API

**Main Classes/Functions**:
- `STTServiceError` - Custom exception
- `STTService` - STT service
  - `transcribe_audio()` - Transcribe audio bytes

**Public API**:
- `transcribe_audio()` - Returns transcript string

**Internal Logic**:
1. Validate audio_bytes not empty
2. Validate size <= MAX_AUDIO_BUFFER_BYTES
3. Validate mime_type in SUPPORTED_MIME_TYPES
4. POST to Groq API with audio file
5. Parse response (transcript or text field)
6. Validate transcript not empty
7. Return transcript

**Inputs**: audio_bytes, mime_type

**Outputs**: Transcript string

**Dependencies**:
- app.core.config.Settings
- app.infrastructure.http_client.HTTPClient, HTTPClientError

**Called By**: AudioEndHandler

**Uses**: logging

**External Libraries**: None (uses HTTPClient for Groq API)

**Potential Problems**:
- No timeout configuration (uses HTTPClient default 30s)
- No retry logic (relies on HTTPClient)
- No handling of Groq rate limits
- No audio preprocessing (noise reduction, etc.)
- No language detection (assumes Arabic/English)

**Security Concerns**:
- No validation of audio content (could be malicious)
- API key sent in Authorization header (standard practice)

**Performance Concerns**:
- Synchronous-style error handling in async method
- No streaming transcription (waits for complete audio)

**Missing Validation**:
- No validation of audio format beyond MIME type
- No validation of audio duration
- No validation of sample rate/channels

**Missing Error Handling**:
- No handling of Groq quota limits
- No handling of Groq model errors

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add audio preprocessing (normalization, noise reduction)
2. Add language detection/hinting
3. Add streaming transcription support
4. Add timeout configuration
5. Add retry with backoff for rate limits
6. Add metrics for transcription latency, accuracy
7. Consider caching transcripts for identical audio

---

#### File: app/services/tts_service.py

**Purpose**: Text-to-Speech service using ElevenLabs.

**Responsibilities**:
- Stream TTS audio from text
- Call ElevenLabs streaming API

**Main Classes/Functions**:
- `TTSServiceError` - Custom exception
- `TTSService` - TTS service
  - `stream_tts_audio()` - Stream TTS audio chunks

**Public API**:
- `stream_tts_audio()` - Async iterator of audio bytes

**Internal Logic**:
1. Validate text not empty
2. POST to ElevenLabs streaming endpoint
3. Yield audio chunks as they arrive

**Inputs**: text string

**Outputs**: Async iterator of audio bytes

**Dependencies**:
- app.core.config.Settings
- app.infrastructure.http_client.HTTPClient, HTTPClientError

**Called By**: TextMessageHandler

**Uses**: typing.AsyncIterator

**External Libraries**: None (uses HTTPClient for ElevenLabs API)

**Potential Problems**:
- No timeout configuration
- No retry logic
- No handling of ElevenLabs rate limits
- No voice selection (uses configured voice only)
- No SSML support

**Security Concerns**:
- API key sent in header (standard practice)

**Performance Concerns**:
- Streaming is efficient
- No audio post-processing

**Missing Validation**:
- No validation of text length
- No validation of voice ID format

**Missing Error Handling**:
- No handling of ElevenLabs quota limits
- No handling of voice not found errors

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add text length limits
2. Add timeout configuration
3. Add retry with backoff
4. Add voice selection support
5. Add SSML support
6. Add metrics for TTS latency, chunk count
7. Consider caching common phrases

---

### 3.6 Tools Layer

#### File: app/tools/cart_tools.py

**Purpose**: Cart update tool for Gemini integration (thin wrapper).

**Responsibilities**:
- Provide LLM-callable functions for cart operations
- Validate addon structure
- Delegate to CartBackendGateway
- Transform results to tool result format

**Main Classes/Functions**:
- `update_cart()` - Update cart tool
- `validate_offer_code()` - Validate offer code tool
- `get_session_order()` - Get session order tool

**Public API**:
- All three functions (callable by LLM)

**Internal Logic**:
1. `update_cart()`:
   - Validate addons with CartAddonSelection
   - Delegate to cart_gateway.update_cart()
   - Transform result to tool format
2. `validate_offer_code()`:
   - Delegate to cart_gateway.validate_offer_code()
   - Transform result
3. `get_session_order()`:
   - Delegate to cart_gateway.get_session_order()
   - Return result

**Inputs**: Tool arguments (turn_id, restaurant_id, session_id, etc.)

**Outputs**: Tool result dictionaries

**Dependencies**:
- app.services.cart_backend_gateway.CartBackendGateway
- app.schemas.cart_schemas.CartAction, CartUpdatePayload, CartAddonSelection

**Called By**: GeminiOrchestrator (via ToolExecutionCoordinator)

**Uses**: logging

**External Libraries**: None

**Potential Problems**:
- Functions are thin wrappers (could be inlined)
- Addon validation could be more thorough
- No timeout on tool execution
- No retry logic

**Security Concerns**:
- Tool arguments from LLM validated with Pydantic (good)
- No authorization check (relies on session_id in arguments)

**Performance Concerns**: None

**Missing Validation**:
- No validation of turn_id format
- No validation of restaurant_id/session_id

**Missing Error Handling**:
- Catches all exceptions and returns error dict (good)

**Dead Code**: None

**Duplicate Logic**:
- Logging pattern repeated

**Suggested Improvements**:
1. Add timeout on gateway calls
2. Add more thorough addon validation
3. Add tool execution metrics
4. Consider inlining if wrappers add no value

---

### 3.7 Integrations Layer

#### File: app/integrations/telegram/__init__.py

**Purpose**: Lazy import for Telegram integration.

**Responsibilities**:
- Lazy load TelegramIntegration to avoid import overhead when disabled

**Main Classes/Functions**:
- `__getattr__()` - Lazy import hook

**Public API**:
- TelegramIntegration (lazy loaded)

**Internal Logic**:
1. When TelegramIntegration is accessed, import from service module
2. Return class (not instance)

**Inputs**: name (must be "TelegramIntegration")

**Outputs**: TelegramIntegration class

**Dependencies**: None (lazy)

**Called By**: app/main.py

**Uses**: importlib

**External Libraries**: None

**Potential Problems**:
- Lazy import only works for module-level access
- No error handling if import fails

**Security Concerns**: None

**Performance Concerns**: None (lazy loading is efficient)

**Missing Validation**: None

**Missing Error Handling**: None

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add error handling for import failures
2. Document lazy import pattern

---

#### File: app/integrations/telegram/service.py

**Purpose**: Telegram bot lifecycle management.

**Responsibilities**:
- Start/stop Telegram bot
- Store service references in bot_data
- Manage polling lifecycle

**Main Classes/Functions**:
- `TelegramIntegration` - Bot lifecycle manager
  - `start()` - Initialize and start polling
  - `shutdown()` - Stop polling and cleanup

**Public API**:
- `start()` - Returns Telegram Application
- `shutdown()` - Cleanup

**Internal Logic**:
1. `start()`:
   - Create Telegram application via create_telegram_application()
   - Store settings, http_client, session_service, gemini_orchestrator in bot_data
   - Initialize, start, and start polling
2. `shutdown()`:
   - Stop polling
   - Stop application
   - Shutdown application

**Inputs**: Settings, HTTPClient, SessionService, GeminiOrchestrator

**Outputs**: Telegram Application instance

**Dependencies**:
- app.api.telegram_bot.create_telegram_application
- app.core.config.Settings
- app.infrastructure.http_client.HTTPClient
- app.services.gemini_orchestrator.GeminiOrchestrator
- app.services.session_service.SessionService
- telegram.Application

**Called By**: app/main.py

**Uses**: asyncio

**External Libraries**: python-telegram-bot

**Potential Problems**:
- No error handling if bot fails to start (relies on caller)
- No health check for bot
- No metrics for bot usage
- bot_data pattern is unconventional (uses dict instead of proper DI)

**Security Concerns**:
- Bot token stored in memory (standard practice)
- No webhook signature verification

**Performance Concerns**:
- Long polling could be inefficient (webhooks preferred)
- No connection pooling

**Missing Validation**:
- No validation of bot token format

**Missing Error Handling**:
- No handling of Telegram API errors
- No handling of polling failures

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add error handling for bot startup failures
2. Add bot health check
3. Add metrics for bot usage
4. Consider webhooks instead of long polling
5. Add webhook signature verification
6. Add bot command handlers

---

### 3.8 Schemas

#### File: app/schemas/websocket_schemas.py

**Purpose**: WebSocket message schemas with Pydantic validation.

**Responsibilities**:
- Define message types (enum)
- Define incoming message schemas
- Define outgoing message schemas
- Provide helper constructors

**Main Classes/Functions**:
- `MessageType` - Enum of message types
- Incoming schemas: TextMessage, AudioChunkMessage, AudioEndMessage, PingMessage
- Outgoing schemas: AssistantTextMessage, AssistantAudioChunkMessage, CartUpdatedMessage, OfferAppliedMessage, ErrorMessage, PongMessage
- `IncomingMessage` - Union type for incoming
- `OutgoingMessage` - Union type for outgoing
- Helper functions: make_assistant_text, make_assistant_audio_chunk, etc.

**Public API**:
- All schema classes
- All make_* functions

**Internal Logic**:
1. MessageType enum defines all message types
2. Incoming schemas have validators (text not empty, audio not empty)
3. Outgoing schemas are simple data containers
4. TypeAdapter(IncomingMessage) used for validation in WebSocket endpoint

**Inputs**: Message data

**Outputs**: Validated Pydantic models

**Dependencies**: pydantic

**Called By**: WebSocket handlers, endpoint

**Uses**: pydantic BaseModel, Field, field_validator

**External Libraries**: pydantic

**Potential Problems**:
- TypeAdapter created at module level (not thread-safe for dynamic schemas)
- No validation of audio_base64 size
- No validation of sequence number bounds
- Union type could cause ambiguity in validation

**Security Concerns**:
- No size limit on text field
- No size limit on audio_base64 (could be DoS)

**Performance Concerns**:
- TypeAdapter validation on every message (could be cached)

**Missing Validation**:
- No maximum text length
- No maximum audio_base64 length
- No validation of sequence number range
- No validation of MIME type format

**Missing Error Handling**: N/A

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add size limits to all fields
2. Add sequence number range validation
3. Add MIME type format validation
4. Consider caching TypeAdapter
5. Add message size limits in WebSocket endpoint

---

#### File: app/schemas/cart_schemas.py

**Purpose**: Cart-related Pydantic schemas.

**Responsibilities**:
- Define cart action enum
- Define addon selection schema
- Define cart update payload schema

**Main Classes/Functions**:
- `CartAction` - Enum (add, remove, update)
- `CartAddonSelection` - Addon selection with addon_id and quantity
- `CartUpdatePayload` - Complete cart update payload

**Public API**:
- All schema classes

**Internal Logic**:
1. CartAction enum defines valid actions
2. CartAddonSelection validates addon_id > 0, quantity >= 1
3. CartUpdatePayload validates all fields, identifiers not blank

**Inputs**: Cart update data

**Outputs**: Validated Pydantic models

**Dependencies**: pydantic

**Called By**: cart_tools.py

**Uses**: pydantic BaseModel, Field, field_validator

**External Libraries**: pydantic

**Potential Problems**:
- No validation of dish_id > 0 in CartUpdatePayload (only in addon)
- No validation of quantity for remove action (could be negative)
- No validation of notes length

**Security Concerns**: None

**Performance Concerns**: None

**Missing Validation**:
- No validation of action against dish availability
- No validation of addon_id against dish_id
- No validation of notes content/length

**Missing Error Handling**: N/A

**Dead Code**: None

**Duplicate Logic**: None

**Suggested Improvements**:
1. Add dish_id > 0 validation
2. Add quantity validation per action (remove should be > 0)
3. Add notes length validation
4. Add addon validation against dish
5. Consider adding price validation

---

## SECTION 4 - Application Flow

### Startup Sequence

1. **Uvicorn starts** and imports `app.main:app`
2. **`create_app()` called**:
   - Load settings via `get_settings()` (Pydantic validates environment)
   - Create FastAPI app with lifespan
   - Add CORS middleware
   - Include WebSocket router
   - Store settings in app.state
   - Define health/ready endpoints
3. **Lifespan startup**:
   - Setup logging (console handler, formatter)
   - **Initialize RedisClient**:
     - Create Redis connection from URL
     - Ping Redis to verify connectivity
   - **Initialize HTTPClient**:
     - Create httpx.AsyncClient with timeout
   - **Initialize SessionService**:
     - Pass RedisClient and TTL
   - **Initialize GeminiOrchestrator**:
     - Configure google.generativeai with API key
     - Create PromptBuilder
     - Create MenuContextProvider (mock or Laravel)
     - Create CartBackendGateway
     - Create ToolExecutionCoordinator
     - Register update_cart tool
     - Conditionally register validate_offer_code tool
     - Create GenerativeModel instance
   - **Conditionally initialize STTService** (if ENABLE_STT)
   - **Conditionally initialize TTSService** (if ENABLE_TTS)
   - **Conditionally initialize RecoveryService** (if ENABLE_RECOVERY)
   - **Conditionally initialize TelegramIntegration** (if ENABLE_TELEGRAM_BOT):
     - Lazy import TelegramIntegration
     - Create application with handlers
     - Start polling
     - If fails and ENABLE_TELEGRAM_STRICT, raise exception
     - Otherwise, log warning and continue
   - Set `app.state.ready = True`
4. **Uvicorn begins accepting connections**

### Initialization

**Dependency Injection**: Manual via app.state (not using DI framework)

**Flow**:
1. Settings loaded first (no dependencies)
2. Infrastructure layer initialized (Redis, HTTP) - no dependencies on services
3. Core services initialized (SessionService depends on Redis)
4. Business logic services initialized (GeminiOrchestrator depends on Session, HTTP, Redis)
5. Optional services initialized based on feature flags
6. Integrations initialized last (depend on all services)

**Configuration Loading**:
- Pydantic Settings loads from .env file
- Validates all fields with validators
- Caches settings with LRU cache (maxsize=1)
- Environment variables override .env file

**Environment Variables**:
- 30+ environment variables documented in .env.example
- Loaded by Pydantic Settings
- Validated on load (URLs, secrets, feature flags)
- Feature flags control optional service initialization

### Routing

**HTTP Routes**:
- `GET /health` - Liveness probe (always returns ok)
- `GET /ready` - Readiness probe (checks dependencies)

**WebSocket Routes**:
- `WS /ws/captain/{restaurant_id}/{session_id}?token={jwt}` - Main conversation endpoint

**No other HTTP routes** (all logic via WebSocket)

### Request Lifecycle (WebSocket)

1. **Client connects** with JWT token in query string
2. **Authentication**:
   - WebSocketAuth decodes JWT
   - Validates algorithm (HS256 only)
   - Verifies expiration
   - Validates restaurant_id and session_id match URL
3. **Connection accepted**:
   - Create ConnectionContext with unique connection_id
   - Initialize AudioBufferService
   - Initialize ResponseSender
   - Create MessageRouter
   - Register handlers (Ping, Text, AudioChunk, AudioEnd)
   - Cancel pending recovery
   - Mark session active
4. **Message loop**:
   - Receive text message
   - Validate with Pydantic TypeAdapter
   - Route to handler based on message type
   - Execute handler
   - Send response(s)
   - Catch and log errors
5. **Disconnect**:
   - Cleanup audio buffer
   - Mark session inactive
   - Schedule recovery (if ENABLE_RECOVERY)

### Response Lifecycle

**Text Message**:
1. Handler calls GeminiOrchestrator.process_user_message()
2. Orchestrator returns assistant_text, cart_events, tool_results
3. Handler sends assistant_text via ResponseSender
4. Handler saves cart snapshot
5. Handler sends cart_updated events
6. Handler checks for offer_applied events
7. Handler streams TTS if enabled

**Audio Message**:
1. AudioChunkHandler buffers chunks
2. AudioEndHandler finalizes buffer
3. STT transcribes audio
4. TextMessageHandler processes transcript (same as text message)

**Ping**:
1. PingHandler sends pong immediately

### Background Jobs

**Recovery Service**:
- Scheduled asyncio task on WebSocket disconnect
- Waits for RECOVERY_DELAY_SECONDS (default 900s)
- Checks if session still abandoned
- Sends webhook to Laravel
- Deduplicates via recovery_status marker

**No other background jobs** (no scheduled tasks, no periodic cleanup)

### Scheduling

**Recovery Scheduling**:
- Triggered by WebSocket disconnect
- Uses asyncio.create_task() for background execution
- Redis TTL for durable scheduling
- In-memory task tracking (self._scheduled_tasks dict)

**No other scheduling** (no cron jobs, no periodic tasks)

### Event System

**No formal event system** (direct method calls only)

**Events via WebSocket**:
- assistant_text
- assistant_audio_chunk
- cart_updated
- offer_applied
- error
- pong

**Events via Webhook**:
- abandoned_cart (POST to Laravel)

### Logging

**Structured Logging**:
- Console handler with format: `%(asctime)s | %(levelname)-8s | %(name)s | %(message)s`
- LogContext adds restaurant_id and session_id to messages
- Extra fields for correlation (turn_id, connection_id, etc.)
- Noisy libraries set to WARNING (httpx, redis, google.generativeai)

**Log Levels**:
- Configurable via LOG_LEVEL environment variable
- Default: INFO

**No log aggregation** (relies on external tools like ELK, Datadog)

### Error Handling

**Layered Error Handling**:
1. **Infrastructure layer**: HTTPClient and RedisClient catch and log errors, raise custom exceptions
2. **Service layer**: Services catch exceptions, log with context, return error results
3. **Handler layer**: Handlers catch exceptions, log, send error to client
4. **Endpoint layer**: Catches WebSocketDisconnect and unexpected errors

**Error Patterns**:
- Custom exceptions: HTTPClientError, STTServiceError, TTSServiceError, RecoveryServiceError, GeminiOrchestratorError
- Structured error results: `{"success": False, "error": "...", "error_code": "..."}`
- Client notifications: ErrorMessage via WebSocket

**No error tracking** (no Sentry, Rollbar, etc.)

---

## SECTION 5 - Architecture

### Layers

**1. API Layer** (app/api/)
- FastAPI routers
- WebSocket endpoints
- Telegram bot handlers
- Thin layer, delegates to WebSocket runtime

**2. WebSocket Runtime Layer** (app/websocket/)
- Authentication
- Connection context
- Message routing
- Specialized handlers
- Response sending
- Turn processing

**3. Business Logic Layer** (app/services/)
- Gemini orchestrator
- Session management
- Recovery service
- Tool execution
- Prompt building
- Menu context

**4. Infrastructure Layer** (app/infrastructure/)
- HTTP client with retries
- Redis client with locking

**5. Integration Layer** (app/integrations/)
- Telegram bot
- External API wrappers (STT, TTS)

**6. Schema Layer** (app/schemas/)
- Pydantic models for validation

**7. Tools Layer** (app/tools/)
- LLM-callable functions

### Modules

**Core Module** (app/core/)
- Configuration management
- Constants
- Logging

**WebSocket Module** (app/websocket/)
- Connection lifecycle
- Message processing pipeline
- Audio handling

**Services Module** (app/services/)
- LLM orchestration
- Session management
- Cart operations
- Recovery

### Services

**Stateless Services** (no in-memory state):
- HTTPClient
- RedisClient (connection state only)
- STTService
- TTSService
- PromptBuilder
- ToolExecutionCoordinator
- CartBackendGateway

**Stateful Services** (in-memory state):
- AudioBufferService (per-connection buffers)
- MessageRouter (handler registry)
- RecoveryService (scheduled tasks)
- MenuContextProvider (in-memory cache)

**Session-Persistent Services** (state in Redis):
- SessionService

### Controllers

**No traditional controllers** (FastAPI routers serve as entry points)

**Handler Pattern**:
- PingHandler
- TextMessageHandler
- AudioChunkHandler
- AudioEndHandler

### Models

**Pydantic Models** (app/schemas/):
- WebSocket messages (incoming/outgoing)
- Cart operations (CartUpdatePayload, CartAddonSelection)

**No ORM models** (relies on Laravel backend for data persistence)

### Repositories

**No repositories** (direct Redis and HTTP calls)

**Data Access**:
- RedisClient provides key-value access
- HTTPClient provides REST API access to Laravel

### Helpers

**LogContext** (app/core/logging.py) - Structured logging helper

**ConnectionContext** (app/websocket/connection_context.py) - Connection state helper

**AudioBufferState** (app/websocket/audio_buffer_service.py) - Audio buffer state helper

### Utilities

**HTTPClient** - Reusable HTTP client with retries

**RedisClient** - Reusable Redis client with locking

**MessageRouter** - Message routing utility

**ResponseSender** - Response sending utility

### How Everything Connects

```
Client (WebSocket/Telegram)
    ↓
API Layer (websocket_endpoints.py, telegram_bot.py)
    ↓
WebSocket Runtime (auth, connection_context, message_router, handlers)
    ↓
Business Logic (gemini_orchestrator, session_service, recovery_service)
    ↓
Infrastructure (http_client, redis_client)
    ↓
External Services (Gemini, Groq, ElevenLabs, Laravel)
```

**Data Flow**:
1. Client sends message via WebSocket
2. Endpoint authenticates and creates connection context
3. MessageRouter dispatches to appropriate handler
4. Handler processes message (e.g., TextMessageHandler calls GeminiOrchestrator)
5. Orchestrator coordinates with PromptBuilder, MenuContextProvider, ToolExecutionCoordinator
6. ToolExecutionCoordinator executes tools via CartBackendGateway
7. CartBackendGateway makes HTTP calls to Laravel
8. SessionService persists state to Redis
9. ResponseSender sends responses back to client

**State Flow**:
- Session state: Redis (via SessionService)
- Cart state: Redis + Laravel (via CartBackendGateway)
- Audio buffers: In-memory (AudioBufferService)
- Connection state: In-memory (ConnectionContext)
- Menu cache: In-memory + Redis (MenuContextProvider)
- Recovery state: Redis + In-memory (RecoveryService)

---

## SECTION 6 - Database

### Database Engine

**Redis** (version 7+ recommended)

**Purpose**: Session persistence, cart snapshots, audio buffer metadata, recovery markers, menu caching

**No SQL database** (relies on Laravel backend for relational data)

### Tables (Redis Keys)

**Session Keys**:
```
Pattern: captain:session:{restaurant_id}:{session_id}
  - JSON: Session metadata (created_at, turn_count, last_activity, order_id)

Pattern: captain:session:{restaurant_id}:{session_id}:active
  - TTL: SESSION_TTL_SECONDS (3600s default)
  - Value: "1" if active, deleted if inactive

Pattern: captain:session:{restaurant_id}:{session_id}:last_user_msg
  - TTL: SESSION_TTL_SECONDS
  - Value: Last user message text

Pattern: captain:session:{restaurant_id}:{session_id}:last_asst_msg
  - TTL: SESSION_TTL_SECONDS
  - Value: Last assistant message text
```

**Cart Keys**:
```
Pattern: captain:cart:{restaurant_id}:{session_id}
  - TTL: SESSION_TTL_SECONDS
  - JSON: Cart snapshot (items, quantities, addons, totals)
```

**Recovery Keys**:
```
Pattern: captain:recovery:{restaurant_id}:{session_id}
  - TTL: RECOVERY_DELAY_SECONDS (900s default)
  - JSON: {
      "disconnected_at": "ISO timestamp",
      "scheduled_at": "ISO timestamp",
      "recovery_status": "scheduled" | "completed",
      "completed_at": "ISO timestamp" (if completed)
    }
```

**Audio Buffer Keys**:
```
Pattern: captain:audio:{restaurant_id}:{session_id}
  - TTL: AUDIO_BUFFER_TTL_SECONDS (300s default)
  - Type: List
  - Value: Serialized audio metadata entries
```

**Order Keys**:
```
Pattern: captain:order:{restaurant_id}:{session_id}
  - TTL: SESSION_TTL_SECONDS
  - Value: Order ID (string)
```

**Menu Cache Keys**:
```
Pattern: captain:session:{restaurant_id}:menu_cache
  - TTL: 300s (5 minutes)
  - JSON: {
      "menu": {...},
      "cached_at": timestamp
    }
```

### Relationships

**No formal relationships** (Redis is key-value store)

**Logical Relationships**:
- Session → Cart (1:1, same restaurant_id:session_id)
- Session → Recovery (1:1, same restaurant_id:session_id)
- Session → Order (1:1, same restaurant_id:session_id)
- Session → Audio Buffer (1:1, per connection)

### Constraints

**Redis Constraints**:
- Key TTL enforced by Redis (automatic expiration)
- String size limit: 512MB
- List size limit: 2^32 - 1 elements
- No foreign key constraints (application-level validation)

**Application Constraints**:
- Session TTL: 3600s (1 hour) default
- Audio buffer TTL: 300s (5 minutes)
- Recovery delay: 900s (15 minutes)
- Max audio buffer: 10MB

### Indexes

**No indexes** (Redis is key-value, not relational)

**Key Design**:
- Keys designed for direct lookup by restaurant_id:session_id
- No secondary indexes
- No scan operations (except KEYS in documentation, which is not recommended)

### Migrations

**No migrations** (Redis is schemaless)

**Laravel Migrations** (in separate Laravel project):
- Add session_id and restaurant_id to orders table
- Create offer_codes table

### ORM Usage

**No ORM** (direct Redis and HTTP calls)

### Query Patterns

**Redis Queries**:
- `GET` - Load session, cart, recovery, messages
- `SETEX` - Save with TTL
- `DELETE` - Remove keys
- `EXISTS` - Check key existence
- `RPUSH` / `LRANGE` - Audio buffer list operations
- `SET NX EX` - Distributed lock acquisition
- `EVAL` - Lua script for atomic lock release
- `PIPELINE` - Batch operations

**HTTP Queries** (to Laravel):
- `GET /api/v1/restaurants/{id}/menu` - Fetch menu
- `POST /api/v1/cart/update` - Update cart
- `POST /api/v1/cart/validate-offer` - Validate offer code
- `GET /api/v1/sessions/{id}/order` - Get session order
- `POST /api/v1/cart/abandoned` - Recovery webhook

### Highlight Inefficient Queries

**N+1 Query Pattern**:
- `SessionService.append_turn()`:
  - Calls `save_session_state()` (writes last_turn)
  - Calls `load_session_state()` (reads metadata)
  - Calls `save_session_state()` (writes updated metadata)
  - **Should use pipeline for atomic read-modify-write**

**Redundant Reads**:
- `SessionService.get_session_context()`:
  - Calls `load_session_state()`
  - Calls `load_cart_snapshot()`
  - **Could be batched**

**Missing Pipeline Usage**:
- Most Redis operations are single commands
- Only `save_session_state_atomic()` uses pipeline
- **Should pipeline common patterns** (e.g., save session + cart together)

**No Connection Pooling**:
- Each Redis method calls `_ensure_client()` (cheap but repeated)
- **Could cache client reference**

---

## SECTION 7 - APIs

### HTTP Endpoints

#### 1. GET /health

**Method**: GET  
**Route**: `/health`  
**Authentication**: None  
**Validation**: None

**Request Body**: None

**Response**:
```json
{
  "status": "ok",
  "service": "ai-captain-service"
}
```

**Status Codes**: 200 (always)

**Internal Flow**:
- Returns hardcoded response
- No dependency checks

**Files Involved**: app/main.py

---

#### 2. GET /ready

**Method**: GET  
**Route**: `/ready`  
**Authentication**: None  
**Validation**: None

**Request Body**: None

**Response (Success)**:
```json
{
  "ready": true,
  "service": "ai-captain-service"
}
```

**Response (Failure)**:
```json
{
  "ready": false,
  "reason": "Redis not available"
}
```

**Status Codes**: 200 (both success and failure)

**Internal Flow**:
1. Check app.state.ready flag
2. Check Redis connection
3. Check HTTP client
4. Check Gemini orchestrator
5. Conditionally check STT, TTS, Telegram
6. Return result

**Files Involved**: app/main.py

---

### WebSocket Endpoints

#### 3. WS /ws/captain/{restaurant_id}/{session_id}

**Method**: WebSocket  
**Route**: `/ws/captain/{restaurant_id}/{session_id}?token={jwt}`  
**Authentication**: JWT token in query parameter  
**Validation**: JWT signature, expiration, payload matches URL params

**Request (Connection)**:
- URL: `ws://localhost:8000/ws/captain/rest_1/sess_123?token={jwt}`
- Headers: None (token in query)
- JWT Payload:
  ```json
  {
    "restaurant_id": "rest_1",
    "session_id": "sess_123",
    "exp": 1719136927
  }
  ```

**Request (Messages)**:
```json
// Text
{"type": "text", "text": "أبغى برجر"}

// Audio Chunk
{"type": "audio_chunk", "audio_base64": "...", "mime_type": "audio/wav", "sequence": 0}

// Audio End
{"type": "audio_end"}

// Ping
{"type": "ping"}
```

**Response (Messages)**:
```json
// Assistant Text
{"type": "assistant_text", "text": "تم، أضفت البرجر"}

// Audio Chunk
{"type": "assistant_audio_chunk", "audio_base64": "...", "sequence": 0}

// Cart Updated
{"type": "cart_updated", "payload": {...}}

// Offer Applied
{"type": "offer_applied", "payload": {...}}

// Error
{"type": "error", "message": "Error message"}

// Pong
{"type": "pong"}
```

**Status Codes**:
- 1000 (Normal closure)
- 1008 (Unauthorized - invalid token)

**Internal Flow**:
1. Authenticate JWT
2. Create ConnectionContext
3. Initialize services
4. Main message loop:
   - Receive and validate message
   - Route to handler
   - Execute handler
   - Send response
5. On disconnect: cleanup and schedule recovery

**Files Involved**:
- app/api/websocket_endpoints.py
- app/websocket/auth.py
- app/websocket/connection_context.py
- app/websocket/message_router.py
- app/websocket/handlers.py
- app/websocket/response_sender.py
- app/websocket/audio_buffer_service.py

---

### External API Calls (to Laravel)

#### 4. GET /api/v1/restaurants/{restaurant_id}/menu

**Method**: GET  
**Route**: `{LARAVEL_BACKEND_URL}/api/v1/restaurants/{restaurant_id}/menu`  
**Authentication**: Required (Laravel Sanctum/API key)  
**Validation**: restaurant_id

**Request**: No body

**Response**:
```json
{
  "restaurant_id": "rest_1",
  "categories": [
    {
      "id": 10,
      "name": "البرجر",
      "dishes": [
        {
          "id": 101,
          "name": "برجر لحم",
          "price": 32.0,
          "external_price": 32.0,
          "is_available": true,
          "average_rating": 4.5,
          "addons": [...]
        }
      ]
    }
  ]
}
```

**Status Codes**: 200, 404

**Internal Flow**:
- MenuContextProvider fetches menu
- Caches in memory (5 min) and Redis (5 min)
- Falls back to mock on error

**Files Involved**: app/services/menu_context_provider.py

---

#### 5. POST /api/v1/cart/update

**Method**: POST  
**Route**: `{LARAVEL_BACKEND_URL}/api/v1/cart/update`  
**Authentication**: Required  
**Validation**: Cross-tenant dish/addon validation (Laravel)

**Headers**:
```
X-Idempotency-Key: cart_mutation:abc123...
X-Session-Id: sess_123
X-Turn-Id: turn_xxx
```

**Request Body**:
```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "action": "add",
  "dish_id": 101,
  "quantity": 2,
  "notes": "بدون بصل",
  "addons": [{"addon_id": 501, "quantity": 1}],
  "source": "ai_captain",
  "turn_id": "turn_xxx",
  "idempotency_key": "cart_mutation:abc123...",
  "price_type": "external"
}
```

**Response**:
```json
{
  "success": true,
  "cart": {...},
  "cart_event": {...}
}
```

**Status Codes**: 200, 422 (validation error)

**Internal Flow**:
- CartBackendGateway generates idempotency key
- Validates addons (basic)
- POSTs to Laravel with headers
- Handles Laravel error codes

**Files Involved**: app/services/cart_backend_gateway.py

---

#### 6. POST /api/v1/cart/validate-offer

**Method**: POST  
**Route**: `{LARAVEL_BACKEND_URL}/api/v1/cart/validate-offer`  
**Authentication**: Required

**Request Body**:
```json
{
  "restaurant_id": "rest_1",
  "code": "SAVE20",
  "subtotal": 150.0
}
```

**Response**:
```json
{
  "valid": true,
  "discount_type": "percentage",
  "discount_value": 20,
  "discount_amount": 30.0
}
```

**Status Codes**: 200, 422

**Internal Flow**:
- CartBackendGateway.validate_offer_code()
- POSTs to Laravel

**Files Involved**: app/services/cart_backend_gateway.py

---

#### 7. GET /api/v1/sessions/{session_id}/order

**Method**: GET  
**Route**: `{LARAVEL_BACKEND_URL}/api/v1/sessions/{session_id}/order`  
**Authentication**: Required

**Response**:
```json
{
  "success": true,
  "order": {...}
}
```

**Status Codes**: 200, 404

**Internal Flow**:
- CartBackendGateway.get_session_order()
- GET from Laravel

**Files Involved**: app/services/cart_backend_gateway.py

---

#### 8. POST /api/v1/cart/abandoned (Webhook)

**Method**: POST  
**Route**: `{LARAVEL_BACKEND_URL}/api/v1/cart/abandoned`  
**Authentication**: Webhook signature (Laravel should verify)

**Request Body**:
```json
{
  "event_id": "uuid",
  "session_id": "sess_123",
  "restaurant_id": "rest_1",
  "occurred_at": "2024-01-01T12:15:00Z",
  "disconnected_at": "2024-01-01T12:00:00Z",
  "last_user_message": "أبغى برجر",
  "last_assistant_message": "تم، أضفت البرجر",
  "cart_snapshot": {...},
  "schema_version": "1.0"
}
```

**Status Codes**: 200 (should return immediately)

**Internal Flow**:
- RecoveryService._send_recovery_webhook()
- POSTs payload to Laravel

**Files Involved**: app/services/recovery_service.py

---

## SECTION 8 - Authentication & Authorization

### Login Flow

**No traditional login** (JWT-based WebSocket authentication)

**JWT Generation** (client-side):
```python
import jwt
import time

payload = {
    "restaurant_id": "rest_1",
    "session_id": "sess_123",
    "exp": int(time.time()) + 3600,  # 1 hour
}

token = jwt.encode(payload, WEBSOCKET_AUTH_SECRET, algorithm="HS256")
```

### Registration

**No registration** (tokens generated by client application)

### Sessions

**Session Model**:
- Identified by restaurant_id + session_id
- Stored in Redis with TTL (1 hour default)
- State: active/inactive
- Contains: metadata, cart snapshot, last messages, turn history

**Session Lifecycle**:
1. Client generates JWT with restaurant_id and session_id
2. Client connects via WebSocket
3. Server validates JWT
4. Session marked active in Redis
5. Conversation proceeds
6. On disconnect: session marked inactive
7. Recovery scheduled (if enabled)
8. Session expires after TTL (auto-cleanup by Redis)

### JWT

**Algorithm**: HS256 (HMAC-SHA256)  
**Secret**: WEBSOCKET_AUTH_SECRET (required, must be strong)  
**Expiration**: Required (exp claim)  
**Payload**:
```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "exp": 1719136927
}
```

**Validation**:
- Algorithm enforced (no "alg: none" attacks)
- Expiration required
- Payload validated against URL parameters

### OAuth

**No OAuth** (JWT only)

### Permissions

**No fine-grained permissions** (all-or-nothing WebSocket access)

**Authorization Model**:
- Valid JWT grants access to restaurant_id + session_id
- No user-level authentication
- No role-based access control

### Roles

**No roles** (single role: authenticated session)

### Middleware

**CORS Middleware**:
- Allows configured origins
- Allows all methods and headers
- Allows credentials

**No authentication middleware** (auth in WebSocket endpoint)

### Token Lifecycle

1. **Generation**: Client generates JWT with restaurant_id, session_id, exp
2. **Validation**: Server validates on WebSocket connection
3. **Usage**: Token used only for connection (no refresh)
4. **Expiration**: Token expires per exp claim
5. **Renewal**: Client must generate new token and reconnect

**No token refresh mechanism**  
**No token revocation** (compromised tokens valid until expiry)

### Weaknesses

1. **Token in Query String**: Visible in server logs, browser history, proxy logs
2. **No Token Refresh**: Client must reconnect with new token
3. **No Revocation**: Compromised tokens valid until expiration
4. **No Rate Limiting**: Brute force attacks possible
5. **No User Authentication**: Only session authentication (no user identity)
6. **No Fine-Grained Permissions**: All-or-nothing access
7. **Weak Secret Warning**: No enforcement of secret strength
8. **No IP Binding**: Token can be used from any IP

---

## SECTION 9 - Frontend

**No frontend in this repository** (backend microservice only)

**Expected Frontend** (not in repo):
- WebSocket client for real-time conversation
- Audio recording/playback
- Text input
- Cart display
- Order confirmation

**Client Requirements** (from README):
- WebSocket connection with JWT token
- Audio recording (MediaRecorder API)
- Base64 encoding for audio
- Message routing by type
- TTS audio playback

---

## SECTION 10 - External Services

### APIs

**1. Google Gemini API**
- **Purpose**: LLM for conversation orchestration, tool calling
- **Model**: gemini-1.5-flash (configurable)
- **Usage**: Chat completion with function calling
- **Why**: Powers conversational AI with Arabic dialect support

**2. Groq API**
- **Purpose**: Speech-to-text transcription
- **Model**: whisper-large-v3
- **Usage**: Transcribe audio bytes to text
- **Why**: Fast, accurate audio transcription

**3. ElevenLabs API**
- **Purpose**: Text-to-speech audio generation
- **Model**: eleven_monolingual_v1
- **Usage**: Stream TTS audio from text
- **Why**: Natural-sounding voice output

**4. Laravel Backend API**
- **Purpose**: Cart management, order management, menu data, offer codes
- **Endpoints**: /api/v1/cart/update, /api/v1/cart/validate-offer, /api/v1/restaurants/{id}/menu, /api/v1/sessions/{id}/order, /api/v1/cart/abandoned
- **Why**: Source of truth for business logic, pricing, inventory

### SDKs

**1. google-generativeai**
- **Purpose**: Python SDK for Gemini API
- **Usage**: genai.GenerativeModel, chat.send_message_async()

**2. python-telegram-bot**
- **Purpose**: Python SDK for Telegram Bot API
- **Usage**: Application, MessageHandler, CallbackQueryHandler

**3. PyJWT**
- **Purpose**: JWT encoding/decoding
- **Usage**: jwt.encode(), jwt.decode()

### Databases

**1. Redis**
- **Purpose**: Session persistence, cart snapshots, recovery markers, menu cache
- **Why**: Fast, in-memory storage for session data

### Queues

**No message queue** (uses asyncio tasks for background jobs)

**Potential Need**: Celery/ARQ for production background job processing

### Storage

**No file storage** (audio buffered in memory, not persisted)

### Cache

**1. Redis**
- **Purpose**: Menu caching, session caching
- **TTL**: 5 minutes for menu, 1 hour for sessions

**2. In-Memory Cache**
- **Purpose**: Menu context caching (MenuContextProvider)
- **TTL**: 5 minutes
- **Limitation**: Not shared across instances

### Email Provider

**No email integration** (recovery via webhook only)

### Payment Gateway

**No payment integration** (delegated to Laravel backend)

### Third-Party Integrations

**1. Telegram**
- **Purpose**: Optional chat interface
- **Why**: Alternative access channel for users

---

## SECTION 11 - Security Review

### SQL Injection Risks

**Risk Level**: None (no SQL queries in this service)

**Mitigation**: All database operations delegated to Laravel backend

---

### XSS Risks

**Risk Level**: Low

**Findings**:
- Assistant text sent to client without sanitization
- User messages stored in Redis without sanitization

**Mitigation**:
- WebSocket messages are JSON (not HTML)
- Client responsible for sanitization

**Recommendations**:
- Sanitize assistant_text before sending if rendered as HTML
- Add Content-Security-Policy header

---

### CSRF Risks

**Risk Level**: None (WebSocket-only, no cookies)

**Mitigation**: WebSocket doesn't use cookies, JWT in query string

**Concerns**:
- JWT in query string could be exploited via CSRF if browser-based
- **Recommendation**: Move token to WebSocket header

---

### SSRF Risks

**Risk Level**: Medium

**Findings**:
- Laravel backend URL from environment variable
- No validation that URL is internal
- HTTPClient can request any URL

**Attack Vector**:
- Attacker controls LARAVEL_BACKEND_URL via environment
- Could point to internal service (metadata API, etc.)

**Recommendations**:
- Validate LARAVEL_BACKEND_URL is internal (not public IP)
- Use allowlist of allowed domains
- Disable redirects in HTTPClient

---

### RCE Risks

**Risk Level**: Low

**Findings**:
- No eval() or exec()
- No pickle deserialization
- No subprocess calls

**Mitigation**: Pure Python/async code

---

### Command Injection

**Risk Level**: None

**Mitigation**: No shell command execution

---

### Missing Validation

**High Priority**:
1. **No rate limiting** on WebSocket messages (DoS risk)
2. **No message size limits** (except audio buffer)
3. **No validation of Gemini tool arguments** (relies on Laravel)
4. **No validation of menu data** from Laravel (could be malicious)
5. **No validation of audio content** (could be malicious files)

**Medium Priority**:
1. No validation of text message length
2. No validation of restaurant_id/session_id format
3. No validation of turn_id format
4. No validation of notes length in cart updates

---

### Missing Authorization

**High Priority**:
1. **No user authentication** (only session authentication)
2. **No user-level authorization** (anyone with valid JWT can access any session)
3. **No role-based access control**
4. **No IP binding** on tokens

**Medium Priority**:
1. No authorization on recovery webhooks (relies on network security)
2. No authorization on Telegram bot commands

---

### Secret Exposure

**Findings**:
1. **JWT in query string**: Visible in logs, browser history
2. **API keys in environment**: Standard practice but could be leaked in logs
3. **No secret redaction in logs**: Could accidentally log secrets

**Recommendations**:
- Move JWT to WebSocket header
- Add secret redaction filter to logging
- Rotate secrets regularly

---

### Weak Encryption

**Findings**:
- JWT uses HS256 (symmetric) - acceptable but RS256 (asymmetric) preferred for distributed systems
- No encryption of data at rest in Redis

**Recommendations**:
- Consider RS256 for JWT (allows key rotation without downtime)
- Enable Redis encryption at rest

---

### Unsafe File Handling

**Findings**:
- Audio files buffered in memory (no disk I/O)
- No file upload handling

**Risk**: Low

---

### Hardcoded Credentials

**Findings**:
- No hardcoded credentials in code
- All secrets in environment variables
- .env.example has placeholders only

**Risk**: None (good practice)

---

### Security Score: 7/10

**Strengths**:
- JWT algorithm enforcement
- Token expiration
- Cross-tenant validation (delegated to Laravel)
- Idempotency keys
- No SQL injection risk

**Weaknesses**:
- JWT in query string
- No rate limiting
- No user authentication
- No token revocation
- No secret redaction in logs
- No SSRF protection

---

## SECTION 12 - Performance Review

### Slow Algorithms

**Findings**:
1. **Menu context fetching**: HTTP call on every cache miss (acceptable with 5-min cache)
2. **Session state loading**: Multiple Redis calls per turn (N+1 pattern)
3. **Gemini API calls**: 2-5s latency (external dependency)

**Impact**: Medium (mostly external dependencies)

---

### N+1 Queries

**High Priority**:
1. **SessionService.append_turn()**:
   - save_session_state() (write)
   - load_session_state() (read)
   - save_session_state() (write)
   - **Should use pipeline**

2. **SessionService.get_session_context()**:
   - load_session_state()
   - load_cart_snapshot()
   - **Should use pipeline**

**Impact**: Medium (adds latency, Redis is fast)

---

### Memory Leaks

**Findings**:
1. **AudioBufferService**: Buffers cleaned up on disconnect, but no TTL enforcement
2. **RecoveryService**: Scheduled tasks tracked in dict, cleaned up in finally block
3. **MenuContextProvider**: In-memory cache grows unbounded (no eviction)

**Risk**: Low (proper cleanup in most cases)

---

### Blocking Operations

**Findings**:
1. **Gemini API calls**: Async but blocking on external response
2. **Redis operations**: Async but blocking on network
3. **No CPU-bound operations** (good)

**Impact**: Low (all I/O is async)

---

### Duplicate Work

**Findings**:
1. **Menu context**: Fetched for every message (cached but still check)
2. **Session state**: Loaded multiple times per turn
3. **System prompt**: Built for every message (could cache)

**Impact**: Low (caching mitigates)

---

### Large Loops

**Findings**:
1. **Cart addon validation**: Loops through addons (acceptable, usually small)
2. **Menu normalization**: Loops through categories/dishes (acceptable, cached)

**Impact**: None

---

### Expensive Rendering

**N/A** (no frontend rendering)

---

### Unnecessary API Calls

**Findings**:
1. **Menu context**: Fetched even if not used (always used in current flow)
2. **Session state**: Loaded when not needed

**Impact**: Low

---

### Missing Caching

**Findings**:
1. **System prompt**: Built for every message (could cache)
2. **Tool definitions**: Built for every message (could cache)
3. **Gemini chat history**: Not cached (managed by Gemini SDK)

**Impact**: Low

---

### Performance Score: 7/10

**Strengths**:
- Async I/O throughout
- Redis caching for menu and sessions
- Streaming TTS
- Connection pooling (HTTPX)

**Weaknesses**:
- N+1 Redis queries
- In-memory cache not shared
- No connection limit enforcement
- No backpressure handling

**Optimization Suggestions**:
1. Use Redis pipeline for batch operations
2. Share in-memory cache across instances (Redis)
3. Add connection limit enforcement
4. Add backpressure for slow clients
5. Cache system prompt and tool definitions
6. Add metrics for latency tracking
7. Consider connection warming

---

## SECTION 13 - Code Quality

### Code Smells

**Minor**:
1. **Import at bottom** (websocket_endpoints.py imports ResponseSender at bottom)
2. **Long methods** (GeminiOrchestrator.process_user_message() is 200 lines)
3. **Deep nesting** (some try-except blocks)
4. **Magic numbers** (30s timeout, 5min cache TTL)

**Major**:
1. **In-memory state** limits horizontal scaling
2. **Direct access to private methods** (SessionService accesses redis_client._ensure_client())

---

### Large Classes

**Findings**:
1. **GeminiOrchestrator** (347 lines) - Could be split further
2. **CartBackendGateway** (380 lines) - Acceptable
3. **SessionService** (316 lines) - Acceptable
4. **RecoveryService** (242 lines) - Acceptable

**Assessment**: No god objects, but GeminiOrchestrator is doing too much

---

### God Objects

**None** (good separation of concerns)

---

### Circular Dependencies

**Findings**:
1. **websocket_endpoints.py** imports ResponseSender at bottom to avoid circular import
2. **GeminiOrchestrator** imports ToolExecutionCoordinator, which imports CartBackendGateway

**Assessment**: Minimal circular dependencies, workaround in place

---

### Duplicate Code

**Findings**:
1. **Error handling pattern** repeated across handlers
2. **Logging context creation** repeated
3. **Retry logic** similar in HTTPClient and GeminiOrchestrator

**Impact**: Low (could extract to utilities)

---

### Tight Coupling

**Findings**:
1. **Handlers depend on ResponseSender** (tight but acceptable)
2. **GeminiOrchestrator depends on all services** (acceptable for orchestrator)

**Assessment**: Loose coupling overall, good use of interfaces (abstract MenuContextProvider)

---

### Low Cohesion

**Findings**:
1. **ConnectionContext** holds many responsibilities (services, state, logging)
2. **GeminiOrchestrator** manages prompt, menu, tools, cart, session

**Assessment**: Moderate cohesion, could be improved

---

### SOLID Violations

**Single Responsibility**:
- ⚠️ GeminiOrchestrator manages prompt, menu, tools, cart, session (multiple responsibilities)
- ⚠️ ConnectionContext holds services, state, and logging

**Open/Closed**:
- ✅ MenuContextProvider uses abstract base class (open for extension)
- ✅ MessageRouter allows handler registration (open for extension)

**Liskov Substitution**:
- ✅ MockMenuContextProvider substitutable for LaravelMenuContextProvider

**Interface Segregation**:
- ✅ Clients depend on abstractions (MenuContextProvider, MessageHandler)

**Dependency Inversion**:
- ✅ Services depend on abstractions (HTTPClient, RedisClient interfaces)
- ✅ Dependency injection via constructors

---

### Naming Problems

**Findings**:
1. **Redis key methods**: `save_session_state()` used for menu cache (semantic mismatch)
2. **`_retryable()`**: Generic name, could be more specific
3. **`create_menu_context_provider()`**: Factory function name is clear

**Assessment**: Generally good naming, minor issues

---

### Code Quality Score: 8/10

**Strengths**:
- Clean architecture with clear layers
- Good separation of concerns
- Type hints throughout
- Comprehensive error handling
- Structured logging

**Weaknesses**:
- Some long methods
- In-memory state limits scalability
- Minor circular dependency workaround
- Some duplicate error handling

---

## SECTION 14 - Technical Debt

### TODO

**Code**:
- None found (no TODO comments)

**Documentation**:
- README mentions "Phase 3: Comprehensive test suite" (planned)

---

### FIXME

**Code**:
- None found (no FIXME comments)

---

### HACK

**Code**:
- None found (no HACK comments)

---

### Deprecated Code

**None** (no deprecation warnings)

---

### Legacy Code

**None** (Phase 2 refactoring completed)

---

### Unused Files

**None** (all files are used)

---

### Unused Functions

**None** (all public functions are used)

---

### Unused Variables

**None** (no unused variable warnings)

---

### Unused Dependencies

**requirements-dev.txt**:
- `locust` - Load testing (optional, documented)
- `mkdocs`, `mkdocs-material` - Documentation (optional, documented)

**requirements.txt**:
- All dependencies appear to be used

---

### Technical Debt Score: 2/10

**Assessment**: Very low technical debt

**Debt Items**:
1. TurnProcessor not integrated (dead code path)
2. In-memory state in MenuContextProvider and AudioBufferService
3. Direct access to private RedisClient methods
4. No test suite (Phase 3 planned)

**Estimated Cleanup Effort**: 2-3 days
- Integrate or remove TurnProcessor: 0.5 days
- Refactor in-memory state to Redis: 1-2 days
- Fix encapsulation violations: 0.5 days

---

## SECTION 15 - Risks

### Critical Risks

**None** (no immediate showstoppers)

---

### High Risks

**1. No Test Suite**
- **Risk**: Bugs in production, difficult to refactor
- **Impact**: High
- **Mitigation**: Implement Phase 3 test suite (unit, integration, load)
- **Effort**: 2-3 weeks

**2. In-Memory State Limits Scaling**
- **Risk**: Audio buffers, menu cache, recovery tasks lost on restart, not shared across instances
- **Impact**: High (prevents horizontal scaling)
- **Mitigation**: Move state to Redis
- **Effort**: 1-2 weeks

**3. No Rate Limiting**
- **Risk**: DoS attacks, resource exhaustion
- **Impact**: High
- **Mitigation**: Add rate limiting middleware
- **Effort**: 2-3 days

---

### Medium Risks

**1. JWT in Query String**
- **Risk**: Token leakage in logs, browser history
- **Impact**: Medium
- **Mitigation**: Move to WebSocket header
- **Effort**: 1 day

**2. No Token Revocation**
- **Risk**: Compromised tokens valid until expiration
- **Impact**: Medium
- **Mitigation**: Implement revocation list in Redis
- **Effort**: 2-3 days

**3. No Circuit Breaker**
- **Risk**: Cascading failures if Laravel backend is down
- **Impact**: Medium
- **Mitigation**: Add circuit breaker for external calls
- **Effort**: 2-3 days

**4. No Monitoring/Alerting**
- **Risk**: Issues detected late, slow incident response
- **Impact**: Medium
- **Mitigation**: Add metrics export (Prometheus), logging aggregation
- **Effort**: 1 week

---

### Low Risks

**1. Hardcoded Values**
- **Risk**: Inflexibility, unexpected behavior
- **Impact**: Low
- **Mitigation**: Move to configuration
- **Effort**: 1 day

**2. No Log Rotation**
- **Risk**: Disk full on long-running instances
- **Impact**: Low
- **Mitigation**: Add log rotation
- **Effort**: 0.5 days

**3. Telegram Bot Hardcoded Restaurant ID**
- **Risk**: Not multi-tenant
- **Impact**: Low (Telegram is optional)
- **Mitigation**: Make configurable
- **Effort**: 0.5 days

---

## SECTION 16 - Improvement Roadmap

### Priority 1 (Critical) - Must Have for Production

**1. Implement Test Suite** (Phase 3)
- **Complexity**: High
- **Effort**: 2-3 weeks
- **Impact**: Enables safe refactoring, prevents regressions
- **Tasks**:
  - Unit tests for all services
  - Integration tests for WebSocket flow
  - Load tests for concurrent connections
  - Failure tests for timeout/retry

**2. Add Rate Limiting**
- **Complexity**: Medium
- **Effort**: 2-3 days
- **Impact**: Prevents DoS attacks
- **Tasks**:
  - Add rate limiter middleware
  - Limit messages per connection per minute
  - Limit concurrent connections per session

**3. Move State to Redis**
- **Complexity**: High
- **Effort**: 1-2 weeks
- **Impact**: Enables horizontal scaling
- **Tasks**:
  - Move AudioBufferService to Redis
  - Move MenuContextProvider cache to Redis
  - Move RecoveryService tasks to Redis
  - Add connection limit enforcement

---

### Priority 2 (High) - Should Have

**1. Move JWT to WebSocket Header**
- **Complexity**: Low
- **Effort**: 1 day
- **Impact**: Prevents token leakage
- **Tasks**:
  - Update client to send token in header
  - Update server to read from headers
  - Maintain backward compatibility with query param

**2. Add Token Revocation**
- **Complexity**: Medium
- **Effort**: 2-3 days
- **Impact**: Allows immediate token invalidation
- **Tasks**:
  - Implement Redis-backed revocation list
  - Check revocation on authentication
  - Add admin API for revocation

**3. Add Circuit Breaker**
- **Complexity**: Medium
- **Effort**: 2-3 days
- **Impact**: Prevents cascading failures
- **Tasks**:
  - Add circuit breaker for Laravel calls
  - Add circuit breaker for Gemini calls
  - Add fallback behavior

**4. Add Monitoring & Alerting**
- **Complexity**: Medium
- **Effort**: 1 week
- **Impact**: Enables proactive issue detection
- **Tasks**:
  - Add Prometheus metrics export
  - Add structured JSON logging
  - Set up alerting rules
  - Create dashboards

---

### Priority 3 (Medium) - Nice to Have

**1. Add Log Rotation**
- **Complexity**: Low
- **Effort**: 0.5 days
- **Impact**: Prevents disk full
- **Tasks**:
  - Add RotatingFileHandler
  - Configure rotation policy

**2. Add Secret Redaction**
- **Complexity**: Low
- **Effort**: 1 day
- **Impact**: Prevents secret leakage in logs
- **Tasks**:
  - Add logging filter for secrets
  - Redact API keys, JWT tokens

**3. Optimize Redis Queries**
- **Complexity**: Medium
- **Effort**: 2-3 days
- **Impact**: Reduces latency
- **Tasks**:
  - Use pipeline for batch operations
  - Eliminate N+1 queries
  - Add connection pooling

**4. Add Conversation History Summarization**
- **Complexity**: High
- **Effort**: 1 week
- **Impact**: Reduces token usage, improves context
- **Tasks**:
  - Implement summarization when history exceeds threshold
  - Test with Arabic text

---

### Priority 4 (Low) - Future Enhancements

**1. A/B Testing Framework**
- **Complexity**: Medium
- **Effort**: 1 week
- **Impact**: Enables prompt optimization
- **Tasks**:
  - Externalize prompts to database
  - Add experiment tracking
  - Add metrics for A/B tests

**2. Multi-Language Support**
- **Complexity**: Medium
- **Effort**: 1 week
- **Impact**: Expands market
- **Tasks**:
  - Add language detection
  - Translate system prompt
  - Test with non-Arabic languages

**3. Advanced Analytics**
- **Complexity**: High
- **Effort**: 2-3 weeks
- **Impact**: Business insights
- **Tasks**:
  - Track conversation metrics
  - Track cart conversion
  - Track abandonment reasons

**4. Distributed Tracing**
- **Complexity**: Medium
- **Effort**: 1 week
- **Impact**: Improves debugging
- **Tasks**:
  - Add OpenTelemetry instrumentation
  - Set up Jaeger/Zipkin
  - Trace requests across services

---

## SECTION 17 - Overall Scores

### Architecture: 9/10
**Strengths**: Clean layered architecture, excellent decomposition in Phase 2, clear separation of concerns, good use of abstractions  
**Weaknesses**: Some in-memory state, TurnProcessor not integrated

---

### Readability: 8/10
**Strengths**: Type hints throughout, clear naming, good docstrings, consistent style  
**Weaknesses**: Some long methods, complex orchestration logic in GeminiOrchestrator

---

### Maintainability: 8/10
**Strengths**: Modular design, easy to modify individual components, good error handling  
**Weaknesses**: No tests, some tight coupling in orchestrator

---

### Scalability: 6/10
**Strengths**: Stateless design (mostly), Redis for shared state, async I/O  
**Weaknesses**: In-memory state (audio buffers, menu cache, recovery tasks), no connection limits, no horizontal scaling support for all components

---

### Performance: 7/10
**Strengths**: Async I/O, Redis caching, streaming TTS, efficient algorithms  
**Weaknesses**: N+1 queries, no connection pooling, no backpressure handling

---

### Security: 7/10
**Strengths**: JWT validation, cross-tenant checks, idempotency, no SQL injection  
**Weaknesses**: JWT in query string, no rate limiting, no token revocation, no user auth

---

### Testing: 2/10
**Strengths**: None  
**Weaknesses**: No test suite (Phase 3 planned)

---

### Documentation: 8/10
**Strengths**: Comprehensive README (1338 lines), clear API docs, environment variable docs, Laravel requirements doc  
**Weaknesses**: No inline docstrings in some places, no API spec (OpenAPI), no deployment guides

---

### Code Quality: 8/10
**Strengths**: Type hints, error handling, structured logging, clean code  
**Weaknesses**: Some long methods, minor code duplication, no tests

---

### Overall Project Health: 7.5/10

**Assessment**: Production-ready foundation with excellent architecture and security practices, but needs test suite and scalability improvements before large-scale deployment.

**Key Strengths**:
- Excellent Phase 2 refactoring
- Production-hardened error handling
- Security-conscious design
- Comprehensive documentation

**Key Weaknesses**:
- No test coverage
- In-memory state limits scaling
- Missing operational features (monitoring, rate limiting)

**Recommendation**: 
- Deploy to staging with monitoring
- Implement Priority 1 improvements (tests, rate limiting, Redis state)
- Deploy to production with canary release
- Implement Priority 2 improvements (JWT header, token revocation, circuit breaker)

---

## Conclusion

The AI Captain Service is a **well-architected, production-grade microservice** that demonstrates excellent software engineering practices. The Phase 2 refactoring created a clean, maintainable codebase with clear separation of concerns, comprehensive error handling, and security-conscious design.

**Key Achievements**:
- ✅ Clean layered architecture with dependency injection
- ✅ Production-hardened resilience (retries, timeouts, idempotency)
- ✅ Security best practices (JWT validation, cross-tenant checks)
- ✅ Observability (structured logging, correlation IDs)
- ✅ Arabic-first design with multi-dialect support
- ✅ Comprehensive documentation

**Critical Gaps**:
- ❌ No test suite (Phase 3 priority)
- ❌ In-memory state prevents horizontal scaling
- ❌ No rate limiting (security risk)
- ❌ No monitoring/alerting (operational risk)

**Handoff Notes for New Senior Engineer**:

1. **Architecture**: The service follows clean architecture with clear layers. Start with app/main.py for startup flow, then explore app/websocket/ for request handling, and app/services/ for business logic.

2. **Key Patterns**:
   - Dependency injection via app.state (not DI framework)
   - Feature flags for optional services
   - Pydantic for validation throughout
   - Structured logging with LogContext

3. **External Dependencies**:
   - Gemini API for LLM (requires API key)
   - Groq API for STT (optional)
   - ElevenLabs for TTS (optional)
   - Laravel backend for cart/order management (required)
   - Redis for session persistence (required)

4. **Configuration**: 30+ environment variables in .env.example, validated by Pydantic Settings

5. **Testing**: No tests exist - prioritize Phase 3 test suite implementation

6. **Deployment**: Stateless except for Redis, designed for horizontal scaling (but in-memory state needs refactoring)

7. **Monitoring**: Structured logs only - add metrics export (Prometheus) and log aggregation

8. **Security**: Strong foundation but needs rate limiting, token revocation, and JWT moved to header

9. **Performance**: Good async design but has N+1 queries and in-memory caching limitations

10. **Next Steps**: Implement Priority 1 improvements (tests, rate limiting, Redis state migration) before production deployment at scale

The codebase is **ready for staging deployment** with monitoring, and **production-ready** after implementing Priority 1 improvements. The architecture supports the stated goal of scaling to 1,000+ restaurants with the recommended improvements.

---

**End of Analysis**