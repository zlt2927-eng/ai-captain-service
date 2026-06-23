# Engineering Audit — ai-captain-service

## Current architecture (summary)
- FastAPI application with WebSocket endpoint at `/ws/captain/{restaurant_id}/{session_id}` in `app/api/websocket_endpoints.py`.
- Gemini LLM orchestrator in `app/services/gemini_orchestrator.py` that builds prompts and may execute cart update tool.
- Redis-backed session storage and recovery scheduling in `app/services/session_service.py` and `app/services/recovery_service.py` using `app/infrastructure/redis_client.py`.
- STT/TTS services behind `app/services/stt_service.py` and `app/services/tts_service.py` that use `app/infrastructure/http_client.py`.
- Telegram long-polling integration in `app/api/telegram_bot.py`.
- Cart mutation tool at `app/tools/cart_tools.py` which calls a Laravel backend.

## Most likely P0 issues observed (top priority)
1. Settings lifecycle and secret handling — `get_settings()` constructed Settings repeatedly and lacked caching. Optional integrations required tokens unconditionally.
2. .env.example contained apparent real API keys (secret exposure risk).
3. WebSocket `audio_chunk` control-flow risk: audio chunks could fall through and trigger "Unsupported message type" or ambiguous behavior.
4. Recovery logging used unsafe structured arguments which may crash logging calls.
5. `cart_tools.update_cart` fetched settings via `get_settings()` repeatedly causing repeated instantiation and coupling.
6. Startup initializes optional integrations (Telegram/STT/TTS) unconditionally and could fail startup.

## Files inspected in Phase 1
- `app/core/config.py`
- `app/main.py`
- `app/api/websocket_endpoints.py`
- `app/services/recovery_service.py`
- `app/tools/cart_tools.py`
- `app/services/gemini_orchestrator.py`
- `app/api/telegram_bot.py`
- `app/schemas/websocket_schemas.py`

## Phase 1 prioritized remediation plan (implemented changes)
1. Cache settings and add explicit optional flags (`ENABLE_TELEGRAM`, `ENABLE_STT`, `ENABLE_TTS`).
2. Sanitize `.env.example` to remove secret-like placeholders.
3. Make Telegram initialization optional and resilient; make STT/TTS optional.
4. Harden WebSocket message handling: strict schema validation, explicit dispatch, fix audio chunk handling fallthrough.
5. Fix unsafe logging in recovery service.
6. Inject `Settings` into cart tool to avoid repeated get_settings() calls.
7. Add unit tests for config and WebSocket audio flows.

## Notes and immediate risks
- Tests added are unit-level and use injected fakes; external integrations (Gemini, Laravel, Groq, ElevenLabs) are not exercised in Phase 1.
- Session model still stores only last user/assistant messages — multi-turn history is incomplete (Phase 2).

## Next steps (Phase 2 & 3 plan highlights)
- Decompose `gemini_orchestrator` responsibilities into prompt builder, provider adapter, and tool executor.
- Expand `session_service` to store bounded conversation history rather than only last messages.
- Harden recovery scheduling to persist markers in Redis and rehydrate on restart.
- Review `http_client` retry semantics and ensure safe retries for non-idempotent requests.
- Add WebSocket and orchestrator test coverage for tool-call flows, auth failures, and edge cases.

