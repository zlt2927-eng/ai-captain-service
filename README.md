# AI Captain Service

A production-grade microservice that acts as an AI Digital Captain for restaurant ordering. Provides interactive voice + text conversation, real-time menu integration, and cart management for multi-tenant restaurant platforms.

## Overview

The AI Captain Service is a FastAPI-based microservice designed for horizontal scaling across 1,000+ restaurants. It orchestrates:

- **Real-time conversation** via WebSocket
- **Voice input** (audio transcription using Groq Whisper Large V3)
- **Voice output** (streaming TTS using ElevenLabs)
- **Intelligent ordering** using Gemini LLM with native function calling
- **Cart management** with ERD-aware dish-addon modeling
- **Multi-tenant isolation** per restaurant
- **Abandoned cart recovery** with configurable delay
- **Redis session persistence** for horizontal scaling

## Architecture

### High-Level Flow

```
WebSocket Client
    ↓
[WebSocket Endpoint] → Token Validation
    ↓
[Text Input / Audio Input]
    ├→ STT (Groq Whisper) if audio
    ├→ Gemini Orchestrator (LLM reasoning)
    ├→ Cart Tool (for dish-addon updates)
    ├→ TTS (ElevenLabs streaming)
    └→ WebSocket Response (text + audio chunks)
```

### Components

- **WebSocket Endpoints** (`app/api/websocket_endpoints.py`): Real-time message handling
- **Gemini Orchestrator** (`app/services/gemini_orchestrator.py`): LLM conversation logic + tool calling
- **STT Service** (`app/services/stt_service.py`): Audio transcription via Groq
- **TTS Service** (`app/services/tts_service.py`): Streaming TTS via ElevenLabs
- **Cart Tools** (`app/tools/cart_tools.py`): Gemini-callable cart update integration
- **Session Service** (`app/services/session_service.py`): Redis-backed session persistence
- **Recovery Service** (`app/services/recovery_service.py`): Abandoned cart webhooks
- **Redis Client** (`app/infrastructure/redis_client.py`): Async Redis wrapper
- **HTTP Client** (`app/infrastructure/http_client.py`): Retry-enabled async HTTP

### Tenant Isolation

Each restaurant has a unique menu context that is loaded during session initialization. The Gemini system prompt is built per-restaurant with:

1. Global AI Captain persona rules
2. Restaurant-specific menu (categories, dishes, add-ons)
3. Allergen/ingredient constraints

**Critical:** No menu data bleeds across restaurants.

## Features

### 1. Multi-Modal Input

- **Text**: Direct user text input
- **Audio**: Binary audio chunks (WAV, WebM) → Groq transcription

### 2. Intelligent Ordering

- Arabic dialect mirroring (Gulf, Saudi, Emirati, Egyptian, Levantine, MSA, Iraqi)
- Dish-aware upselling (suggest compatible sides/drinks)
- Allergy awareness (block incompatible dishes)
- Ambiguous quantity resolution
- Clarification discipline (ask 1 question instead of guessing)

### 3. Cart Management (ERD-Aware)

Cart model aligns with Laravel domain:

```
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "action": "add",          # add|remove|update
  "dish_id": 101,           # dish PK
  "quantity": 2,
  "notes": "بدون بصل",       # special requests
  "addons": [               # dish_addon selections
    {"addon_id": 501, "quantity": 1},
    {"addon_id": 502, "quantity": 2}
  ]
}
```

### 4. Real-Time TTS Streaming

Assistant responses are streamed as TTS audio chunks via WebSocket:

```json
{
  "type": "assistant_audio_chunk",
  "audio_base64": "...",
  "sequence": 0
}
```

### 5. Session Persistence

All session state is persisted in Redis:

- Session metadata
- Last user message
- Last assistant message
- Current cart snapshot
- Active/inactive markers
- Recovery markers

### 6. Abandoned Cart Recovery

If a user disconnects before checkout:

1. Session marked inactive
2. Recovery marker scheduled in Redis (default 15 min)
3. After delay, session snapshot collected
4. Webhook POSTed to Laravel:

```json
{
  "restaurant_id": "rest_1",
  "session_id": "sess_123",
  "disconnected_at": "2026-06-23T16:02:07Z",
  "last_user_message": "...",
  "last_assistant_message": "...",
  "cart_snapshot": {...}
}
```

## Environment Variables

See `.env.example` for all required variables. Key groups:

### App / Runtime

- `APP_NAME`: Service name (default: `ai-captain-service`)
- `APP_ENV`: Environment (default: `development`)
- `APP_HOST`: Listen host (default: `0.0.0.0`)
- `APP_PORT`: Listen port (default: `8000`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

### AI / LLM

- `GEMINI_API_KEY`: Google Gemini API key
- `GEMINI_MODEL`: Model ID (default: `gemini-1.5-flash`)
- `GROQ_API_KEY`: Groq API key for STT
- `GROQ_STT_MODEL`: STT model (default: `whisper-large-v3`)
- `ELEVENLABS_API_KEY`: ElevenLabs API key
- `ELEVENLABS_VOICE_ID`: Voice ID for TTS
- `ELEVENLABS_MODEL_ID`: Model ID for TTS (default: `eleven_monolingual_v1`)

### Laravel Integration

- `LARAVEL_BACKEND_URL`: Base URL of Laravel API
- `LARAVEL_CART_UPDATE_PATH`: Cart update endpoint (default: `/api/v1/cart/update`)
- `LARAVEL_ABANDONED_CART_PATH`: Abandoned cart webhook (default: `/api/v1/cart/abandoned`)

### Redis

- `REDIS_URL`: Redis connection URL (default: `redis://localhost:6379/0`)

### WebSocket Security

- `WEBSOCKET_AUTH_SECRET`: JWT signing secret
- `WEBSOCKET_AUTH_ALGORITHM`: JWT algorithm (default: `HS256`)

### Timing & Resources

- `SESSION_TTL_SECONDS`: Session Redis TTL (default: `3600`)
- `RECOVERY_DELAY_SECONDS`: Recovery webhook delay (default: `900`)
- `HTTP_TIMEOUT_SECONDS`: HTTP timeout (default: `30`)
- `HTTP_MAX_RETRIES`: Retry count (default: `3`)
- `HTTP_BACKOFF_BASE_SECONDS`: Exponential backoff base (default: `1.0`)
- `MAX_AUDIO_BUFFER_BYTES`: Max audio buffer size (default: `10000000`)

### CORS

- `ALLOWED_CORS_ORIGINS`: Comma-separated list of allowed origins

## Local Setup

### Prerequisites

- Python 3.11+
- Redis (running locally or via Docker)
- API keys for Gemini, Groq, and ElevenLabs

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
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

## Health & Readiness

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "service": "ai-captain-service"
}
```

### Readiness Check

```bash
curl http://localhost:8000/ready
```

Response:
```json
{
  "ready": true,
  "service": "ai-captain-service"
}
```

## WebSocket Usage

### Generate Auth Token

Token payload:
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

### Connect & Send Text

```javascript
const token = "..."; // signed JWT
const ws = new WebSocket(`ws://localhost:8000/ws/captain/rest_1/sess_123?token=${token}`);

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: "text",
    text: "أبغى برجر لحم مع بطاطس"
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  console.log(msg.type, msg);
  
  if (msg.type === "assistant_text") {
    console.log("Assistant:", msg.text);
  } else if (msg.type === "assistant_audio_chunk") {
    // Decode base64 and play audio
    const audioBytes = atob(msg.audio_base64);
  } else if (msg.type === "cart_updated") {
    console.log("Cart updated:", msg.payload);
  }
};
```

### Send Audio

```javascript
// Record audio and collect chunks
const audioChunks = [];
const mediaRecorder = new MediaRecorder(stream);

mediaRecorder.ondataavailable = (event) => {
  const reader = new FileReader();
  reader.onload = (e) => {
    const base64Audio = btoa(
      new Uint8Array(e.target.result).reduce(
        (a, b) => a + String.fromCharCode(b), ''
      )
    );
    ws.send(JSON.stringify({
      type: "audio_chunk",
      audio_base64: base64Audio,
      mime_type: "audio/webm",
      sequence: audioChunks.length
    }));
  };
  reader.readAsArrayBuffer(event.data);
};

mediaRecorder.onstop = () => {
  ws.send(JSON.stringify({
    type: "audio_end"
  }));
};
```

### Message Types

#### Incoming

**Text Input**
```json
{
  "type": "text",
  "text": "I want a burger with fries"
}
```

**Audio Chunk**
```json
{
  "type": "audio_chunk",
  "audio_base64": "...",
  "mime_type": "audio/wav",
  "sequence": 0
}
```

**Audio End**
```json
{
  "type": "audio_end"
}
```

**Ping**
```json
{
  "type": "ping"
}
```

#### Outgoing

**Assistant Text**
```json
{
  "type": "assistant_text",
  "text": "Great! I added a burger and fries. Would you like a drink?"
}
```

**Assistant Audio Chunk**
```json
{
  "type": "assistant_audio_chunk",
  "audio_base64": "...",
  "sequence": 0
}
```

**Cart Updated**
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

**Error**
```json
{
  "type": "error",
  "message": "Human readable error message"
}
```

**Pong**
```json
{
  "type": "pong"
}
```

## System Prompt & AI Behavior

The AI Captain uses an advanced system prompt defined in `app/core/constants.py` that enforces:

1. **Arabic Dialect Mirroring**: Instantly mirrors user's Arabic dialect (Gulf, Saudi, Emirati, Egyptian, Levantine, Iraqi, MSA)
2. **Voice UX Brevity**: Responses are 1–2 sentences max for natural speech
3. **Dish-Aware Cross-Selling**: Suggests one compatible side/drink only, from menu only
4. **Allergy Guardrails**: Blocks incompatible dishes; suggests safe alternatives
5. **Ambiguous Resolution**: Latest quantity intent overrides earlier statements
6. **Cart Discipline**: Never claims cart updated unless tool succeeded
7. **Tenant Discipline**: Uses only active restaurant menu; never invents dishes
8. **Clarification Discipline**: Asks one clarification instead of guessing
9. **Tool Grounding**: Tool results are source of truth
10. **Warm Tone**: Restaurant-host tone, never robotic

## Menu Context & ERD Model

The service is deeply aware of the restaurant ordering domain:

**Entities**
- `restaurants`: Restaurant identity and metadata
- `categories`: Menu categories
- `dishes`: Menu items with pricing, ingredients, allergens, prep time
- `dish_addons`: Modifiers (extra cheese, sauces, etc.)

**Orders (Laravel mapping)**
- `orders`: Order header
- `order_items`: Order line items (dishes + quantity + notes)
- `order_item_addons`: Add-ons per order item

The AI Captain manages a draft **cart/session** that eventually maps into Laravel orders.

## Mocked vs. Real Integration

### Mocked (For Demonstration)

**Menu Context** (`gemini_orchestrator.get_menu_context()`)

Currently returns a hardcoded mock menu. In production:

```python
async def get_menu_context(self, restaurant_id: str) -> dict:
    # Instead of mocking, call:
    # GET {LARAVEL_BACKEND_URL}/api/v1/restaurants/{restaurant_id}/menu
    response = await self.http_client.get_json(
        f"{self.settings.laravel_backend_url}/api/v1/restaurants/{restaurant_id}/menu"
    )
    return response
```

### Fully Implemented

- ✅ WebSocket message handling
- ✅ Gemini native function calling
- ✅ Groq Whisper transcription
- ✅ ElevenLabs streaming TTS
- ✅ JWT token validation
- ✅ Redis session persistence
- ✅ HTTP retry logic with exponential backoff
- ✅ Abandoned cart recovery webhooks
- ✅ Multi-tenant isolation
- ✅ Structured logging
- ✅ Error handling

## Deployment

### Docker

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

### Kubernetes

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
    port: 8000
    targetPort: 8000
  type: LoadBalancer
```

## Monitoring & Debugging

### Structured Logs

Logs include context:

```
2026-06-23 16:02:07 | INFO     | app.api.websocket_endpoints | WebSocket connection accepted [restaurant_id=rest_1] [session_id=sess_123]
2026-06-23 16:02:08 | INFO     | app.services.stt_service | Transcribed 12345 bytes: أبغى برجر لحم
2026-06-23 16:02:10 | INFO     | app.services.tts_service | TTS audio streamed for text: تم، أضفت البرجر
2026-06-23 16:02:11 | INFO     | app.services.recovery_service | Scheduled recovery for rest_1:sess_123 in 900s
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
```

## Troubleshooting

### "Token mismatch" on WebSocket connect

- Verify token `restaurant_id` and `session_id` match URL params
- Check token expiration (`exp` claim)
- Verify `WEBSOCKET_AUTH_SECRET` matches between signing and validation

### "Redis unhealthy" on /ready

- Ensure Redis is running and accessible
- Check `REDIS_URL` environment variable
- Test connection: `redis-cli ping`

### "Gemini API error" in logs

- Verify `GEMINI_API_KEY` is correct
- Check API quota and billing
- Ensure model name is valid

### "Groq transcription failed" on audio input

- Verify `GROQ_API_KEY` is valid
- Check audio format (supported: WAV, WebM, MP3, OGG, FLAC)
- Verify audio is not corrupted

### "ElevenLabs TTS timeout"

- Check network connectivity
- Verify `ELEVENLABS_API_KEY` is correct
- Ensure `ELEVENLABS_VOICE_ID` exists in account
- Test with shorter text first

### Audio buffer exceeds max size

- Reduce audio chunk sizes on client
- Increase `MAX_AUDIO_BUFFER_BYTES` if needed
- Check for client sending oversized chunks

## Performance Characteristics

| Metric | Target | Notes |
|--------|--------|-------|
| WebSocket connect | < 100ms | Token validation + Redis init |
| Text message latency | 2–5s | Gemini + TTS streaming |
| Audio transcription | 2–10s | Depends on audio length |
| TTS streaming | Real-time | Chunks streamed as generated |
| Cart update POST | 500–2000ms | Includes HTTP retry backoff |
| Abandoned cart webhook | 900s+ | Configurable delay |

## Scaling Considerations

### Horizontal Scaling

The service is stateless except for Redis:

- No in-memory session state
- All session data in Redis with TTL
- Multiple instances can run behind a load balancer
- WebSocket sticky sessions recommended for user continuity

### Redis as a Bottleneck

- Consider Redis cluster for high load
- Use Redis pipelining for bulk operations
- Implement cache warming for popular restaurants

### Gemini Rate Limits

- Batch similar requests when possible
- Implement request queuing for bursts
- Monitor API quota

## Contributing

Code guidelines:

- Type hints required
- Async-first design
- Structured logging with context
- Pydantic validation for all inputs
- Error handling with meaningful messages
- No blocking I/O in async functions

## License

Proprietary — All rights reserved.

## Support

For issues or questions, contact the platform engineering team.
