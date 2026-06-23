import asyncio
import json

import pytest

from app.services.gemini_orchestrator import GeminiOrchestrator, GeminiClient, ToolExecutor
from app.core.config import Settings


class DummySessionService:
    async def collect_session_snapshot(self, r, s):
        return {"last_user_message": "hi", "last_assistant_message": "hello"}

    async def persist_conversation_turn(self, r, s, u, a):
        return None

    async def save_cart_snapshot(self, r, s, snapshot):
        return None


class FakeLLM:
    def __init__(self, response):
        self._response = response

    async def create_chat_completion(self, messages, functions=None, function_call=None, temperature=0.2):
        return self._response


class FakeToolExec:
    def __init__(self, result):
        self._result = result

    async def execute(self, tool_name, tool_args):
        return self._result


@pytest.mark.asyncio
async def test_no_tool_turn(monkeypatch):
    settings = Settings(GEMINI_API_KEY="g", GEMINI_MODEL="m", WEBSOCKET_AUTH_SECRET="s", LARAVEL_BACKEND_URL="http://localhost")
    session = DummySessionService()

    # LLM returns no tool call and a simple assistant content
    llm_resp = {"choices": [{"message": {"content": "assistant reply"}}]}
    orch = GeminiOrchestrator(settings, session, None)
    orch._llm = FakeLLM(llm_resp)
    orch._tool_executor = FakeToolExec({})

    res = await orch.process_user_message("r", "s", "hello")
    assert res["assistant_text"] == "assistant reply"


@pytest.mark.asyncio
async def test_tool_call_success(monkeypatch):
    settings = Settings(GEMINI_API_KEY="g", GEMINI_MODEL="m", WEBSOCKET_AUTH_SECRET="s", LARAVEL_BACKEND_URL="http://localhost")
    session = DummySessionService()

    # LLM returns a function call
    call_args = json.dumps({"action": "add", "dish_id": 1, "quantity": 1})
    llm_resp = {"choices": [{"message": {"function_call": {"name": "update_cart", "arguments": call_args}}}]}

    orch = GeminiOrchestrator(settings, session, None)
    orch._llm = FakeLLM(llm_resp)
    tool_result = {"tool": "update_cart", "success": True, "result": {"cart": {"items": []}, "cart_event": {}}}
    orch._tool_executor = FakeToolExec(tool_result)

    res = await orch.process_user_message("r", "s", "add burger")
    assert res["tool_results"]
    assert res["cart_snapshot"] == {"items": []}


@pytest.mark.asyncio
async def test_tool_call_failure(monkeypatch):
    settings = Settings(GEMINI_API_KEY="g", GEMINI_MODEL="m", WEBSOCKET_AUTH_SECRET="s", LARAVEL_BACKEND_URL="http://localhost")
    session = DummySessionService()

    call_args = json.dumps({"action": "add", "dish_id": 1, "quantity": 1})
    llm_resp = {"choices": [{"message": {"function_call": {"name": "update_cart", "arguments": call_args}}}]}

    orch = GeminiOrchestrator(settings, session, None)
    orch._llm = FakeLLM(llm_resp)
    # Simulate tool failure
    tool_result = {"tool": "update_cart", "success": False, "result": {"error": "backend down"}}
    orch._tool_executor = FakeToolExec(tool_result)

    res = await orch.process_user_message("r", "s", "add burger")
    assert res["tool_results"]
    assert res["tool_results"][0]["success"] is False
