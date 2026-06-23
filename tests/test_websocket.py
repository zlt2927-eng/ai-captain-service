import base64
import json
import jwt

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class FakeSTT:
    async def transcribe_audio(self, audio_bytes, mime_type):
        return "hello from audio"


class FakeTTS:
    async def stream_tts_audio(self, text):
        if False:
            yield b""


class FakeSessionService:
    async def mark_session_active(self, r, s):
        return None

    async def mark_session_inactive(self, r, s):
        return None

    async def save_cart_snapshot(self, r, s, snapshot):
        return None

    async def persist_conversation_turn(self, r, s, u, a):
        return None


class FakeOrchestrator:
    async def process_user_message(self, restaurant_id, session_id, user_text):
        return {"assistant_text": "assistant reply", "cart_events": [], "cart_snapshot": None}


class FakeRecovery:
    async def cancel_recovery(self, r, s):
        return None

    async def schedule_recovery(self, r, s):
        return None


@pytest.fixture()
def settings():
    return Settings(GEMINI_API_KEY="g", WEBSOCKET_AUTH_SECRET="secret", WEBSOCKET_AUTH_ALGORITHM="HS256")


def make_token(settings, restaurant_id, session_id):
    payload = {"restaurant_id": restaurant_id, "session_id": session_id}
    return jwt.encode(payload, settings.WEBSOCKET_AUTH_SECRET, algorithm=settings.WEBSOCKET_AUTH_ALGORITHM)


def test_audio_chunk_flow(monkeypatch, settings):
    app = create_app(settings)

    # Inject fake services into app.state
    app.state.settings = settings
    app.state.stt_service = FakeSTT()
    app.state.tts_service = FakeTTS()
    app.state.session_service = FakeSessionService()
    app.state.gemini_orchestrator = FakeOrchestrator()
    app.state.recovery_service = FakeRecovery()
    app.state.redis_client = type("R", (), {"is_connected": lambda self: True})()
    app.state.http_client = None

    client = TestClient(app)
    restaurant_id = "r1"
    session_id = "s1"
    token = make_token(settings, restaurant_id, session_id)

    with client.websocket_connect(f"/ws/captain/{restaurant_id}/{session_id}?token={token}") as ws:
        # send a single audio chunk
        chunk_b64 = base64.b64encode(b"audio-bytes").decode("utf-8")
        ws.send_text(json.dumps({"type": "audio_chunk", "audio_base64": chunk_b64, "mime_type": "audio/wav", "sequence": 0}))

        # then end
        ws.send_text(json.dumps({"type": "audio_end"}))

        # should receive assistant text
        text_msg = ws.receive_text()
        data = json.loads(text_msg)
        assert data.get("type") == "assistant_text"
        assert "assistant reply" in data.get("text", "")


def test_malformed_base64_returns_error(monkeypatch, settings):
    app = create_app(settings)
    app.state.settings = settings
    app.state.stt_service = FakeSTT()
    app.state.tts_service = None
    app.state.session_service = FakeSessionService()
    app.state.gemini_orchestrator = FakeOrchestrator()
    app.state.recovery_service = FakeRecovery()
    app.state.redis_client = type("R", (), {"is_connected": lambda self: True})()
    app.state.http_client = None

    client = TestClient(app)
    restaurant_id = "r2"
    session_id = "s2"
    token = make_token(settings, restaurant_id, session_id)

    with client.websocket_connect(f"/ws/captain/{restaurant_id}/{session_id}?token={token}") as ws:
        ws.send_text(json.dumps({"type": "audio_chunk", "audio_base64": "!!notbase64!!", "mime_type": "audio/wav", "sequence": 0}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data.get("type") == "error"
        assert "Invalid audio chunk" in data.get("message", "")


def test_text_message_flow(monkeypatch, settings):
    app = create_app(settings)
    app.state.settings = settings
    app.state.stt_service = None
    app.state.tts_service = None
    app.state.session_service = FakeSessionService()
    app.state.gemini_orchestrator = FakeOrchestrator()
    app.state.recovery_service = FakeRecovery()
    app.state.redis_client = type("R", (), {"is_connected": lambda self: True})()

    client = TestClient(app)
    restaurant_id = "r3"
    session_id = "s3"
    token = make_token(settings, restaurant_id, session_id)

    with client.websocket_connect(f"/ws/captain/{restaurant_id}/{session_id}?token={token}") as ws:
        ws.send_text(json.dumps({"type": "text", "text": "Hello"}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data.get("type") == "assistant_text"


def test_audio_end_with_empty_buffer_returns_error(monkeypatch, settings):
    app = create_app(settings)
    app.state.settings = settings
    app.state.stt_service = FakeSTT()
    app.state.tts_service = None
    app.state.session_service = FakeSessionService()
    app.state.gemini_orchestrator = FakeOrchestrator()
    app.state.recovery_service = FakeRecovery()
    app.state.redis_client = type("R", (), {"is_connected": lambda self: True})()

    client = TestClient(app)
    restaurant_id = "r4"
    session_id = "s4"
    token = make_token(settings, restaurant_id, session_id)

    with client.websocket_connect(f"/ws/captain/{restaurant_id}/{session_id}?token={token}") as ws:
        ws.send_text(json.dumps({"type": "audio_end"}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data.get("type") == "error"
        assert "No audio to transcribe" in data.get("message", "")


def test_unsupported_message_type_returns_error(monkeypatch, settings):
    app = create_app(settings)
    app.state.settings = settings
    app.state.stt_service = None
    app.state.tts_service = None
    app.state.session_service = FakeSessionService()
    app.state.gemini_orchestrator = FakeOrchestrator()
    app.state.recovery_service = FakeRecovery()
    app.state.redis_client = type("R", (), {"is_connected": lambda self: True})()

    client = TestClient(app)
    restaurant_id = "r5"
    session_id = "s5"
    token = make_token(settings, restaurant_id, session_id)

    with client.websocket_connect(f"/ws/captain/{restaurant_id}/{session_id}?token={token}") as ws:
        ws.send_text(json.dumps({"type": "unknown_type"}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data.get("type") == "error"
        assert "Unsupported message type" in data.get("message", "")


def test_stt_disabled_audio_end_returns_error(monkeypatch, settings):
    app = create_app(settings)
    app.state.settings = settings
    app.state.stt_service = None
    app.state.tts_service = None
    app.state.session_service = FakeSessionService()
    app.state.gemini_orchestrator = FakeOrchestrator()
    app.state.recovery_service = FakeRecovery()
    app.state.redis_client = type("R", (), {"is_connected": lambda self: True})()

    client = TestClient(app)
    restaurant_id = "r6"
    session_id = "s6"
    token = make_token(settings, restaurant_id, session_id)

    with client.websocket_connect(f"/ws/captain/{restaurant_id}/{session_id}?token={token}") as ws:
        chunk_b64 = base64.b64encode(b"audio-bytes").decode("utf-8")
        ws.send_text(json.dumps({"type": "audio_chunk", "audio_base64": chunk_b64, "mime_type": "audio/wav", "sequence": 0}))
        ws.send_text(json.dumps({"type": "audio_end"}))
        msg = ws.receive_text()
        data = json.loads(msg)
        assert data.get("type") == "error"
        assert "Speech-to-text not enabled" in data.get("message", "")

