# AI Captain Service

A production-grade microservice that acts as an AI Digital Captain for restaurant ordering. Provides interactive voice + text conversation, real-time menu integration, and cart management for multi-tenant restaurant platforms.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Folder Structure](#folder-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [API Documentation](#api-documentation)
- [Database Design](#database-design)
- [Authentication Flow](#authentication-flow)
- [Examples](#examples)
- [Testing](#testing)
- [Deployment](#deployment)
- [Monitoring & Debugging](#monitoring--debugging)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

The AI Captain Service is a FastAPI-based microservice designed for horizontal scaling across 1,000+ restaurants. It orchestrates:

- **Real-time conversation** via WebSocket
- **Voice input** (audio transcription using Groq Whisper Large V3)
- **Voice output** (streaming TTS using ElevenLabs)
- **Intelligent ordering** using Google Gemini LLM with native function calling
- **Cart management** with ERD-aware dish-addon modeling
- **Multi-tenant isolation** per restaurant
- **Abandoned cart recovery** with configurable delay
- **Redis session persistence** for horizontal scaling
- **Optional Telegram bot** integration

### Key Capabilities

- **Arabic-First Design**: Instantly mirrors user's Arabic dialect (Gulf, Saudi, Emirati, Egyptian, Levantine, Iraqi, MSA)
- **Production-Hardened**: Phase 1 & 2 refactoring with comprehensive error handling, retry logic, and observability
- **Idempotent Operations**: Cart mutations include idempotency keys to prevent duplicate side effects
- **Per-Session Serialization**: Conversation turns processed sequentially to prevent race conditions
- **Correlation Tracking**: Every turn has a unique ID for end-to-end tracing

---

## Architecture

### High-Level Flow

```
WebSocket Client
    ↓
[WebSocket Endpoint] → JWT Authentication
    ↓
[Connection Context] → Turn Correlation ID Generation
    ↓
[Message Router] → Type-Based Dispatch
    ↓
[Handlers] → Specialized Processing
    ├→ PingHandler → Pong
    ├→ TextMessageHandler → Gemini Orchestrator → TTS Streaming
    ├→ AudioChunkHandler → Audio Buffer Service
    └→ AudioEndHandler → STT → TextMessageHandler
    ↓
[Gemini Orchestrator] → LLM Reasoning + Tool Calling
    ├→ PromptBuilder → System Prompt Construction
    ├→ MenuContextProvider → Menu Data (Mock/Laravel)
    ├→ ToolExecutionCoordinator → Tool Validation & Execution
    └→ CartBackendGateway → Idempotent Cart Mutations
    ↓
[Laravel Backend] → Cart/Order Management
    ↓
[Redis] → Session Persistence + Recovery Scheduling
    ↓
WebSocket Response (text + audio chunks + cart events)
```

### Component Architecture

#### Phase 1: Foundation (Completed)
- **Configuration**: Pydantic-settings with validation and feature flags
- **HTTP Client**: Retry-enabled client with structured logging and latency tracking
- **Redis Client**: Async wrapper with pipeline support and distributed locking
- **Session Service**: Turn-level session persistence and recovery payload building
- **Recovery Service**: Abandoned cart recovery with deduplication
- **Telegram Integration**: Optional bot with lazy loading

#### Phase 2: Runtime Hardening (Completed)
- **WebSocket Package**: Decomposed endpoint with connection context, auth, audio buffering, message routing, and specialized handlers
- **Gemini Orchestrator**: Decomposed into PromptBuilder, MenuContextProvider, CartBackendGateway, ToolExecutionCoordinator
- **Cart Tooling**: Idempotent mutations with correlation tracking
- **Session Service**: Enhanced with turn history and atomic operations
- **Redis Client**: Locking primitives and pipeline helpers
- **Recovery Service**: State-based deduplication and durable scheduling

---

## Features

### 1. Multi-Modal Input

- **Text**: Direct user text input via WebSocket
- **Audio**: Binary audio chunks (WAV, WebM) → Groq Whisper transcription
- **Real-time Processing**: Streaming TTS responses via ElevenLabs

### 2. Intelligent Ordering

- **Arabic Dialect Mirroring**: Instantly adapts to user's dialect (Gulf, Saudi, Emirati, Egyptian, Levantine, Iraqi, MSA)
- **Dish-Aware Cross-Selling**: Suggests compatible sides/drinks from menu only
- **Allergy Guardrails**: Blocks incompatible dishes based on allergens
- **Ambiguous Resolution**: Latest quantity intent overrides earlier statements
- **Clarification Discipline**: Asks one concise question instead of guessing

### 3. Cart Management (ERD-Aware)

Cart model aligns with Laravel domain:

```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "action": "add",          // add|remove|update
  "dish_id": 101,           // dish PK
  "quantity": 2,
  "notes": "بدون بصل",       // special requests
  "addons": [               // dish_addon selections
    {"addon_id": 501, "quantity": 1},
    {"addon_id": 502, "quantity": 2}
  ],
  "turn_id": "turn_xxx",    // correlation ID
  "idempotency_key": "cart_mutation:abc123..."  // deduplication
}
```

### 4. Real-Time TTS Streaming

Assistant responses streamed as TTS audio chunks via WebSocket:

```json
{
  "type": "assistant_audio_chunk",
  "audio_base64": "...",
  "sequence": 0
}
```

### 5. Session Persistence

All session state persisted in Redis:

- Session metadata with turn count and timestamps
- Last user/assistant messages
- Current cart snapshot
- Active/inactive markers
- Recovery markers with deduplication
- Conversation turn history

### 6. Abandoned Cart Recovery

If a user disconnects before checkout:

1. Session marked inactive
2. Recovery marker scheduled in Redis (default 15 min)
3. After delay, session snapshot collected
4. Deduplication check prevents duplicate webhooks
5. Webhook POSTed to Laravel with enriched payload

### 7. Production Hardening

- **Per-Session Turn Serialization**: No concurrent turn processing
- **Turn Correlation IDs**: End-to-end tracing for every conversation turn
- **Idempotent Cart Mutations**: SHA256-based keys prevent duplicate side effects
- **Distributed Locking**: Redis-based locks for coordination
- **Atomic Operations**: Pipeline-based multi-key updates
- **Structured Logging**: Correlation context in all log entries
- **Retry Logic**: Exponential backoff with jitter for transient failures
- **Timeout Protection**: 30s turn processing timeout

### 8. Optional Integrations

- **Telegram Bot**: Feature-flag driven, lazy-loaded, with strict/non-strict failure modes
- **Groq STT**: Whisper Large V3 for audio transcription
- **ElevenLabs TTS**: Streaming voice output

---

## Folder Structure

```
ai-captain-service/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI app entry point, lifespan management
│   │
│   ├── api/                             # API layer
│   │   ├── __init__.py
│   │   ├── websocket_endpoints.py       # WebSocket route (hardened, thin)
│   │   └── telegram_bot.py              # Telegram bot handlers
│   │
│   ├── core/                            # Core utilities
│   │   ├── __init__.py
│   │   ├── config.py                    # Pydantic-settings configuration
│   │   ├── constants.py                 # Application constants
│   │   └── logging.py                   # Structured logging setup
│   │
│   ├── infrastructure/                  # Infrastructure layer
│   │   ├── __init__.py
│   │   ├── http_client.py               # Async HTTP client with retries
│   │   └── redis_client.py              # Async Redis client with locking/pipelines
│   │
│   ├── integrations/                    # External integrations
│   │   ├── __init__.py                  # Lazy import for Telegram
│   │   └── telegram/
│   │       ├── __init__.py
│   │       └── service.py               # Telegram bot lifecycle
│   │
│   ├── schemas/                         # Data models
│   │   ├── __init__.py
│   │   ├── cart_schemas.py              # Cart validation schemas
│   │   └── websocket_schemas.py         # WebSocket message schemas
│   │
│   ├── services/                        # Business logic layer
│   │   ├── __init__.py
│   │   ├── gemini_orchestrator.py       # LLM orchestration (decomposed)
│   │   ├── prompt_builder.py            # System prompt construction
│   │   ├── menu_context_provider.py     # Menu data abstraction
│   │   ├── cart_backend_gateway.py      # Cart operations with idempotency
│   │   ├── tool_execution_coordinator.py # Tool validation & execution
│   │   ├── session_service.py           # Session state management
│   │   ├── recovery_service.py          # Abandoned cart recovery
│   │   ├── stt_service.py               # Speech-to-text (Groq)
│   │   └── tts_service.py               # Text-to-speech (ElevenLabs)
│   │
│   ├── tools/                           # Tool implementations
│   │   ├── __init__.py
│   │   └── cart_tools.py                # Cart update tool (thin wrapper)
│   │
│   └── websocket/                       # WebSocket runtime (Phase 2)
│       ├── __init__.py
│       ├── connection_context.py        # Per-connection state
│       ├── auth.py                      # JWT authentication
│       ├── audio_buffer_service.py      # Audio buffering with safety
│       ├── message_router.py            # Message type routing
│       ├── handlers.py                  # Message handlers
│       ├── response_sender.py           # Structured response sending
│       └── turn_processor.py            # Turn serialization & timeouts
│
├── .env.example                         # Environment configuration template
├── requirements.txt                     # Python dependencies
└── README.md                            # This file
```

---

## Installation

### Prerequisites

- Python 3.11+
- Redis (running locally or via Docker)
- API keys for Gemini, Groq, and ElevenLabs (optional)
- Laravel backend (for cart/order management)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

### Start Redis (Docker)

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

### Run Service

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or directly:

```bash
python app/main.py
```

Service starts on `http://localhost:8000`

---

## Configuration

### Feature Flags

The service uses feature flags to enable/disable optional components:

- `ENABLE_TELEGRAM_BOT`: Enable Telegram bot integration
- `ENABLE_TELEGRAM_STRICT`: Fail startup if Telegram fails (vs. continue without)
- `ENABLE_TTS`: Enable ElevenLabs text-to-speech
- `ENABLE_STT`: Enable Groq speech-to-text
- `ENABLE_RECOVERY`: Enable abandoned cart recovery webhooks

### Settings Validation

The `Settings` class (Pydantic v2) validates:

- Required secrets (GEMINI_API_KEY, WEBSOCKET_AUTH_SECRET)
- URL formats (LARAVEL_BACKEND_URL, REDIS_URL)
- Feature flag dependencies (e.g., TELEGRAM_BOT_TOKEN required if ENABLE_TELEGRAM_BOT=true)
- CORS origins (comma-separated or list)

---

## Environment Variables

### App / Runtime

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `ai-captain-service` | Service name |
| `APP_ENV` | `development` | Environment (development/staging/production) |
| `APP_HOST` | `0.0.0.0` | Listen host |
| `APP_PORT` | `8000` | Listen port |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_TELEGRAM_BOT` | `false` | Enable Telegram bot |
| `ENABLE_TELEGRAM_STRICT` | `false` | Strict Telegram failure policy |
| `ENABLE_TTS` | `false` | Enable ElevenLabs TTS |
| `ENABLE_STT` | `false` | Enable Groq STT |
| `ENABLE_RECOVERY` | `false` | Enable abandoned cart recovery |

### AI / LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *(required)* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Gemini model ID |
| `TELEGRAM_BOT_TOKEN` | `None` | Telegram bot token (required if ENABLE_TELEGRAM_BOT=true) |
| `GROQ_API_KEY` | `None` | Groq API key (required if ENABLE_STT=true) |
| `GROQ_STT_MODEL` | `whisper-large-v3` | Groq STT model |
| `ELEVENLABS_API_KEY` | `None` | ElevenLabs API key (required if ENABLE_TTS=true) |
| `ELEVENLABS_VOICE_ID` | `None` | ElevenLabs voice ID (required if ENABLE_TTS=true) |
| `ELEVENLABS_MODEL_ID` | `eleven_monolingual_v1` | ElevenLabs model ID |

### Laravel Backend Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `LARAVEL_BACKEND_URL` | *(required)* | Base URL of Laravel API |
| `LARAVEL_CART_UPDATE_PATH` | `/api/v1/cart/update` | Cart update endpoint |
| `LARAVEL_ABANDONED_CART_PATH` | `/api/v1/cart/abandoned` | Abandoned cart webhook |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |

### WebSocket Security

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBSOCKET_AUTH_SECRET` | *(required)* | JWT signing secret |
| `WEBSOCKET_AUTH_ALGORITHM` | `HS256` | JWT algorithm |

### Session / Recovery / HTTP Timing

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TTL_SECONDS` | `3600` | Session Redis TTL (1 hour) |
| `AUDIO_BUFFER_TTL_SECONDS` | `300` | Audio buffer TTL (5 min) |
| `RECOVERY_DELAY_SECONDS` | `900` | Recovery webhook delay (15 min) |
| `HTTP_TIMEOUT_SECONDS` | `30` | HTTP request timeout |
| `HTTP_MAX_RETRIES` | `3` | HTTP retry count |
| `HTTP_BACKOFF_BASE_SECONDS` | `1.0` | Exponential backoff base |
| `MAX_AUDIO_BUFFER_BYTES` | `10000000` | Max audio buffer size (10MB) |

### CORS / Debug

| Variable | Default | Description |
|----------|---------|-------------|
| `ALLOWED_CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `ENABLE_DEBUG_ROUTES` | `false` | Enable debug endpoints |

---

## API Documentation

### Health & Readiness

#### Health Check

```bash
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "ai-captain-service"
}
```

#### Readiness Check

```bash
GET /ready
```

Response:

```json
{
  "ready": true,
  "service": "ai-captain-service"
}
```

Readiness verifies:
- Settings loaded
- Redis connected
- HTTP client initialized
- Gemini orchestrator initialized
- Optional services (STT, TTS, Telegram) if enabled

### WebSocket API

#### Connection

```javascript
const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."; // signed JWT
const ws = new WebSocket(`ws://localhost:8000/ws/captain/rest_1/sess_123?token=${token}`);
```

**Token Payload:**

```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "exp": 1719136927
}
```

Sign with `WEBSOCKET_AUTH_SECRET` using `HS256`:

```python
import jwt
import time

token = jwt.encode(
    {
        "restaurant_id": "rest_1",
        "session_id": "sess_123",
        "exp": int(time.time()) + 3600,
    },
    "your-secret",
    algorithm="HS256"
)
```

#### Message Types

**Incoming Messages:**

1. **Text Input**

```json
{
  "type": "text",
  "text": "أبغى برجر لحم مع بطاطس"
}
```

2. **Audio Chunk**

```json
{
  "type": "audio_chunk",
  "audio_base64": "...",
  "mime_type": "audio/wav",
  "sequence": 0
}
```

3. **Audio End**

```json
{
  "type": "audio_end"
}
```

4. **Ping**

```json
{
  "type": "ping"
}
```

**Outgoing Messages:**

1. **Assistant Text**

```json
{
  "type": "assistant_text",
  "text": "تم، أضفت البرجر للسلّة. هل تريد مشروب؟"
}
```

2. **Assistant Audio Chunk**

```json
{
  "type": "assistant_audio_chunk",
  "audio_base64": "...",
  "sequence": 0
}
```

3. **Cart Updated**

```json
{
  "type": "cart_updated",
  "payload": {
    "restaurant_id": "rest_1",
    "session_id": "sess_123",
    "action": "add",
    "dish_id": 101,
    "quantity": 1,
    "notes": null,
    "addons": []
  }
}
```

4. **Error**

```json
{
  "type": "error",
  "message": "Human readable error message"
}
```

5. **Pong**

```json
{
  "type": "pong"
}
```

---

## Database Design

### Redis Keys

The service uses Redis for all state persistence. Key naming follows a consistent pattern:

#### Session Keys

```
captain:session:{restaurant_id}:{session_id}
  - JSON: Session metadata (created_at, turn_count, last_activity)

captain:session:{restaurant_id}:{session_id}:active
  - TTL: SESSION_TTL_SECONDS
  - Value: "1" if active, deleted if inactive

captain:session:{restaurant_id}:{session_id}:last_user_msg
  - TTL: SESSION_TTL_SECONDS
  - Value: Last user message text

captain:session:{restaurant_id}:{session_id}:last_asst_msg
  - TTL: SESSION_TTL_SECONDS
  - Value: Last assistant message text
```

#### Cart Keys

```
captain:cart:{restaurant_id}:{session_id}
  - TTL: SESSION_TTL_SECONDS
  - JSON: Cart snapshot (items, quantities, addons, totals)
```

#### Recovery Keys

```
captain:recovery:{restaurant_id}:{session_id}
  - TTL: RECOVERY_DELAY_SECONDS
  - JSON: {
      "disconnected_at": "2026-06-23T16:02:07Z",
      "scheduled_at": "2026-06-23T16:02:07Z",
      "recovery_status": "scheduled" | "completed",
      "completed_at": "2026-06-23T16:17:07Z" (if completed)
    }
```

#### Audio Buffer Keys

```
captain:audio:{restaurant_id}:{session_id}
  - TTL: AUDIO_BUFFER_TTL_SECONDS
  - Type: List
  - Value: Serialized audio metadata entries
```

### Laravel Backend Schema

The service integrates with a Laravel backend. Expected endpoints:

#### POST /api/v1/cart/update

Request:

```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "action": "add",
  "dish_id": 101,
  "quantity": 2,
  "notes": "بدون بصل",
  "addons": [
    {"addon_id": 501, "quantity": 1}
  ],
  "source": "ai_captain",
  "turn_id": "turn_xxx",
  "idempotency_key": "cart_mutation:abc123"
}
```

Headers:

```
X-Idempotency-Key: cart_mutation:abc123
X-Session-Id: sess_123
X-Turn-Id: turn_xxx
```

Response:

```json
{
  "success": true,
  "message": "Cart updated",
  "cart": {
    "items": [...],
    "total": 64.0,
    "currency": "SAR"
  },
  "cart_event": { /* echo of request */ }
}
```

#### POST /api/v1/cart/abandoned

Request (Recovery Webhook):

```json
{
  "event_id": "uuid-here",
  "session_id": "sess_123",
  "restaurant_id": "rest_1",
  "occurred_at": "2026-06-23T16:17:07Z",
  "disconnected_at": "2026-06-23T16:02:07Z",
  "last_user_message": "أبغى برجر",
  "last_assistant_message": "تم، أضفت البرجر",
  "cart_snapshot": {
    "items": [...],
    "total": 64.0
  },
  "schema_version": "1.0"
}
```

---

## Authentication Flow

### WebSocket JWT Authentication

1. **Client Generates Token**:

```python
import jwt
import time

payload = {
    "restaurant_id": "rest_1",
    "session_id": "sess_123",
    "exp": int(time.time()) + 3600,  # 1 hour expiry
}

token = jwt.encode(payload, WEBSOCKET_AUTH_SECRET, algorithm="HS256")
```

2. **Client Connects**:

```javascript
const ws = new WebSocket(
    `ws://localhost:8000/ws/captain/rest_1/sess_123?token=${token}`
);
```

3. **Server Validates**:

- Decode JWT using `WEBSOCKET_AUTH_SECRET`
- Verify `restaurant_id` and `session_id` match URL params
- Check token expiration
- Accept connection or close with code 1008 (unauthorized)

4. **Connection Established**:

- Create `ConnectionContext` with unique `connection_id`
- Generate correlation context for logging
- Initialize services (audio buffer, message router, handlers)
- Cancel any pending recovery for session
- Mark session as active

### Security Features

- JWT tokens expire (configurable via `exp` claim)
- Token payload validated against URL parameters
- No sensitive data in tokens (only identifiers)
- Secrets never logged
- CORS configured via whitelist

---

## Examples

### Example 1: Text Message Flow

```javascript
// 1. Connect
const ws = new WebSocket(`ws://localhost:8000/ws/captain/rest_1/sess_123?token=${token}`);

ws.onopen = () => {
    // 2. Send text message
    ws.send(JSON.stringify({
        type: "text",
        text: "أبغى برجر لحم مع جبنة إضافية"
    }));
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    
    switch (msg.type) {
        case "assistant_text":
            console.log("Assistant:", msg.text);
            // "تم، أضفت برجر لحم مع جبنة إضافية. هل تريد بطاطس؟"
            break;
            
        case "cart_updated":
            console.log("Cart updated:", msg.payload);
            // { action: "add", dish_id: 101, quantity: 1, addons: [...] }
            break;
            
        case "assistant_audio_chunk":
            // Decode and play audio
            const audioBytes = atob(msg.audio_base64);
            playAudio(audioBytes, msg.sequence);
            break;
    }
};
```

### Example 2: Audio Message Flow

```javascript
// 1. Connect
const ws = new WebSocket(`ws://localhost:8000/ws/captain/rest_1/sess_123?token=${token}`);

// 2. Record audio
const mediaRecorder = new MediaRecorder(stream);
const audioChunks = [];

mediaRecorder.ondataavailable = (event) => {
    const reader = new FileReader();
    reader.onload = (e) => {
        const base64Audio = btoa(
            new Uint8Array(e.target.result)
                .reduce((a, b) => a + String.fromCharCode(b), '')
        );
        
        // 3. Send audio chunk
        ws.send(JSON.stringify({
            type: "audio_chunk",
            audio_base64: base64Audio,
            mime_type: "audio/webm",
            sequence: audioChunks.length
        }));
        
        audioChunks.push(event.data);
    };
    reader.readAsArrayBuffer(event.data);
};

mediaRecorder.onstop = () => {
    // 4. Signal end of audio
    ws.send(JSON.stringify({
        type: "audio_end"
    }));
};

// Start recording
mediaRecorder.start();
```

### Example 3: Python Backend Integration

```python
import httpx
import json

# Update cart
response = httpx.post(
    "http://localhost:8001/api/v1/cart/update",
    json={
        "restaurant_id": "rest_1",
        "session_id": "sess_123",
        "action": "add",
        "dish_id": 101,
        "quantity": 2,
        "notes": "بدون بصل",
        "addons": [{"addon_id": 501, "quantity": 1}],
        "source": "ai_captain",
        "turn_id": "turn_abc123",
        "idempotency_key": "cart_mutation:def456"
    },
    headers={
        "X-Idempotency-Key": "cart_mutation:def456",
        "X-Session-Id": "sess_123",
        "X-Turn-Id": "turn_abc123"
    }
)

print(response.json())
```

---

## Testing

### Current Test Status

**Note**: Test suite implementation is planned for Phase 3. Currently, the service validates functionality through:

1. **Import Testing**: All modules compile and import successfully
2. **Syntax Validation**: Python compilation checks pass
3. **Manual Integration Testing**: WebSocket connection and message flow

### Planned Test Coverage (Phase 3)

- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end WebSocket flows
- **Load Tests**: Concurrent connection handling
- **Failure Tests**: Timeout, retry, and error handling

### Manual Testing

```bash
# 1. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 2. Start service
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Check health
curl http://localhost:8000/health

# 4. Check readiness
curl http://localhost:8000/ready

# 5. Test WebSocket (using wscat or similar)
wscat -c "ws://localhost:8000/ws/captain/rest_1/sess_123?token=YOUR_JWT_TOKEN"
```

---

## Deployment

### Docker Deployment

**Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY .env .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build and Run:**

```bash
docker build -t ai-captain-service .
docker run -d -p 8000:8000 --env-file .env ai-captain-service
```

### Kubernetes Deployment

**Deployment:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-captain-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-captain-service
  template:
    metadata:
      labels:
        app: ai-captain-service
    spec:
      containers:
      - name: ai-captain
        image: ai-captain-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          value: redis://redis-service:6379/0
        - name: LARAVEL_BACKEND_URL
          value: http://laravel-backend
        - name: GEMINI_API_KEY
          valueFrom:
            secretKeyRef:
              name: ai-captain-secrets
              key: gemini-api-key
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
---
apiVersion: v1
kind: Service
metadata:
  name: ai-captain-service
spec:
  selector:
    app: ai-captain-service
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

**Redis:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: 256Mi
          limits:
            memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: redis-service
spec:
  selector:
    app: redis
  ports:
  - protocol: TCP
    port: 6379
    targetPort: 6379
```

### Horizontal Scaling

The service is stateless except for Redis:

- **No in-memory session state**: All session data in Redis with TTL
- **Multiple instances**: Can run behind a load balancer
- **WebSocket sticky sessions**: Recommended for user continuity
- **Redis cluster**: Consider for high load (1,000+ orders/day)

### Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| WebSocket connect | < 100ms | Token validation + Redis init |
| Text message latency | 2–5s | Gemini + TTS streaming |
| Audio transcription | 2–10s | Depends on audio length |
| TTS streaming | Real-time | Chunks streamed as generated |
| Cart update POST | 500–2000ms | Includes HTTP retry backoff |
| Abandoned cart webhook | 900s+ | Configurable delay |

---

## Monitoring & Debugging

### Structured Logs

All logs include correlation context:

```
2026-06-23 16:02:07 | INFO | app.api.websocket_endpoints | WebSocket connection accepted [restaurant_id=rest_1] [session_id=sess_123] [connection_id=uuid-here]
2026-06-23 16:02:08 | INFO | app.services.stt_service | Transcribed 12345 bytes: أبغى برجر لحم [restaurant_id=rest_1] [session_id=sess_123] [turn_id=turn_xxx]
2026-06-23 16:02:10 | INFO | app.services.tts_service | TTS audio streamed for text: تم، أضفت البرجر [restaurant_id=rest_1] [session_id=sess_123] [turn_id=turn_xxx]
2026-06-23 16:02:11 | INFO | app.services.recovery_service | Scheduled recovery for rest_1:sess_123 in 900s
```

### HTTP Client Logging

Every HTTP request includes:

- `method`: HTTP method
- `url`: Target URL
- `status_code`: Response status
- `latency_ms`: Request duration
- `attempt`: Retry attempt number
- `service_name`: Target service
- `endpoint_name`: Endpoint identifier
- `correlation_id`: Turn/session correlation ID

Example:

```json
{
  "method": "POST",
  "url": "http://laravel-backend/api/v1/cart/update",
  "status_code": 200,
  "latency_ms": 245.32,
  "attempt": 1,
  "service_name": "laravel_backend",
  "endpoint_name": "update_cart",
  "correlation_id": "turn_abc123"
}
```

### Redis Inspection

```bash
# Check session state
redis-cli GET "captain:session:rest_1:sess_123"

# Check cart snapshot
redis-cli GET "captain:cart:rest_1:sess_123"

# Check active sessions
redis-cli KEYS "captain:session:*:active"

# Check recovery markers
redis-cli KEYS "captain:recovery:*"

# Check recovery marker details
redis-cli GET "captain:recovery:rest_1:sess_123"
```

### Key Metrics to Monitor

- **WebSocket connections**: Active connections count
- **Turn processing time**: P50, P95, P99 latency
- **Cart mutation success rate**: Success/failure ratio
- **Gemini API latency**: LLM response times
- **Redis connection pool**: Utilization and errors
- **Recovery webhook delivery**: Success/failure rate
- **Audio transcription time**: STT processing duration
- **TTS streaming time**: Audio generation duration

---

## Troubleshooting

### "Token mismatch" on WebSocket connect

**Symptoms**: Connection closed with code 1008, reason "Invalid token payload"

**Solutions**:
- Verify token `restaurant_id` and `session_id` match URL params
- Check token expiration (`exp` claim)
- Verify `WEBSOCKET_AUTH_SECRET` matches between signing and validation
- Ensure JWT algorithm is `HS256`

### "Redis unhealthy" on /ready

**Symptoms**: `/ready` returns `{"ready": false, "reason": "Redis not available"}`

**Solutions**:
- Ensure Redis is running and accessible
- Check `REDIS_URL` environment variable
- Test connection: `redis-cli ping`
- Verify network connectivity and firewall rules

### "Gemini API error" in logs

**Symptoms**: `GeminiOrchestratorError: Orchestration failed`

**Solutions**:
- Verify `GEMINI_API_KEY` is correct
- Check API quota and billing
- Ensure model name is valid (`gemini-1.5-flash` recommended)
- Check for rate limiting (429 errors) - service retries automatically

### "Groq transcription failed" on audio input

**Symptoms**: `STTServiceError: Transcription failed`

**Solutions**:
- Verify `GROQ_API_KEY` is valid
- Check audio format (supported: WAV, WebM, MP3, OGG, FLAC)
- Verify audio is not corrupted or empty
- Check Groq API status and quota

### "ElevenLabs TTS timeout"

**Symptoms**: `TTSServiceError: TTS streaming failed`

**Solutions**:
- Check network connectivity
- Verify `ELEVENLABS_API_KEY` is correct
- Ensure `ELEVENLABS_VOICE_ID` exists in account
- Test with shorter text first
- Check ElevenLabs API status

### "Audio buffer exceeds max size"

**Symptoms**: Error message "Audio buffer exceeded maximum size"

**Solutions**:
- Reduce audio chunk sizes on client
- Increase `MAX_AUDIO_BUFFER_BYTES` if needed (default 10MB)
- Check for client sending oversized chunks
- Implement client-side audio compression

### "Recovery webhook not firing"

**Symptoms**: Abandoned carts not triggering webhooks

**Solutions**:
- Verify `ENABLE_RECOVERY=true`
- Check `LARAVEL_BACKEND_URL` is correct
- Ensure `RECOVERY_DELAY_SECONDS` is set (default 900s)
- Check Redis for recovery markers: `redis-cli KEYS "captain:recovery:*"`
- Verify Laravel endpoint is accessible
- Check recovery service logs for errors

### High memory usage

**Symptoms**: Service consuming excessive memory

**Solutions**:
- Check for memory leaks in long-running WebSocket connections
- Verify Redis connection pool is properly closed
- Monitor audio buffer cleanup (ensure buffers are cleared)
- Check for accumulated background tasks in RecoveryService
- Consider reducing `SESSION_TTL_SECONDS` to free Redis memory

---

## Contributing

### Code Guidelines

- **Type hints required**: All function signatures must include type hints
- **Async-first design**: Use `async`/`await` for all I/O operations
- **Structured logging**: Use `extra` parameter for context
- **Pydantic validation**: Validate all inputs with schemas
- **Error handling**: Meaningful error messages with context
- **No blocking I/O**: Never use synchronous I/O in async functions
- **Docstrings**: All public methods must have docstrings

### Development Setup

```bash
# Clone repository
git clone https://github.com/zlt2927-eng/ai-captain-service.git
cd ai-captain-service

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Run service
python -m uvicorn app.main:app --reload
```

### Commit Guidelines

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- Reference issue numbers: `feat(websocket): add turn correlation (#123)`
- Keep commits focused and atomic
- Write descriptive commit messages

### Pull Request Process

1. Create feature branch from `main`
2. Implement changes with tests
3. Update documentation
4. Ensure all checks pass
5. Submit PR with description

---

## License

Proprietary — All rights reserved.

---

## Support

For issues or questions, contact the platform engineering team.

---

## Changelog

### Phase 2 (Current)

- WebSocket endpoint decomposition with specialized handlers
- Per-session turn serialization and correlation IDs
- Gemini orchestrator decomposition (PromptBuilder, MenuContextProvider, etc.)
- Cart backend gateway with idempotency
- Session service rework with turn history
- Redis client enhancements (locking, pipelines, atomic operations)
- Recovery service hardening with deduplication
- Comprehensive structured logging

### Phase 1

- Configuration/settings hardening with Pydantic v2
- App startup/lifecycle refactor with FastAPI lifespan
- Telegram decoupling with lazy imports
- HTTP client with retry logic and structured logging
- Redis client foundation
- Session service foundation
- Recovery service foundation
- Environment variable documentation

---

## Roadmap

### Phase 3 (Planned)

- Comprehensive test suite (unit, integration, load)
- README updates and documentation improvements
- Repository cleanup
- Readiness/operational validation automation
- Performance benchmarking

### Future Enhancements

- Multi-language support beyond Arabic
- Advanced analytics and reporting
- A/B testing framework for LLM prompts
- Circuit breakers for external dependencies
- Metrics export (Prometheus/OpenTelemetry)
- Distributed tracing (Jaeger/Zipkin)