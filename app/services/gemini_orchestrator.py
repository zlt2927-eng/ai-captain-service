"""Gemini conversation orchestration for restaurant ordering.

This module separates prompt building, provider integration, tool execution,
and high-level orchestration into distinct components.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Protocol

from app.core.constants import CAPTAIN_SYSTEM_PROMPT, TOOL_NAME_UPDATE_CART
from app.core.config import Settings
from app.infrastructure.http_client import HTTPClient
from app.services.session_service import SessionService
from app.tools.cart_tools import update_cart

logger = logging.getLogger(__name__)


class GeminiOrchestratorError(Exception):
    pass


class MenuContextProvider(Protocol):
    async def get_menu_context(self, restaurant_id: str) -> dict:
        ...


class FallbackMenuContextProvider:
    async def get_menu_context(self, restaurant_id: str) -> dict:
        return {
            "restaurant_id": restaurant_id,
            "restaurant_name": "Unknown Restaurant",
            "currency": "SAR",
            "language": "ar",
            "categories": [],
        }


class PromptBuilder:
    MAX_HISTORY_TURNS = 5

    def build_system_prompt(self, menu_context: dict, session_snapshot: Optional[dict] = None) -> str:
        menu_context_json = json.dumps(menu_context, ensure_ascii=False, indent=2)
        parts = [CAPTAIN_SYSTEM_PROMPT, "\nRESTAURANT_MENU_CONTEXT:\n", menu_context_json]

        if session_snapshot is not None:
            session_metadata = {
                "last_user_message": session_snapshot.get("last_user_message"),
                "last_assistant_message": session_snapshot.get("last_assistant_message"),
            }
            parts.extend(["\nSESSION_METADATA:\n", json.dumps(session_metadata, ensure_ascii=False)])
            if session_snapshot.get("cart_snapshot") is not None:
                parts.extend(["\nCART_SNAPSHOT:\n", json.dumps(session_snapshot["cart_snapshot"], ensure_ascii=False)])

        return "".join(parts)

    def build_conversation_history(self, session_snapshot: Optional[dict]) -> List[dict]:
        history: List[dict] = []
        if not session_snapshot:
            return history

        if isinstance(session_snapshot.get("conversation_history"), list):
            for turn in session_snapshot["conversation_history"][-self.MAX_HISTORY_TURNS:]:
                if turn.get("role") in {"user", "assistant"} and isinstance(turn.get("content"), str):
                    history.append({"role": turn["role"], "content": turn["content"]})
            return history

        last_user = session_snapshot.get("last_user_message")
        last_assistant = session_snapshot.get("last_assistant_message")
        if last_user:
            history.append({"role": "user", "content": last_user})
        if last_assistant:
            history.append({"role": "assistant", "content": last_assistant})
        return history


class GeminiProviderAdapter:
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self._client = None

    def _ensure_client(self):
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise GeminiOrchestratorError(
                "Gemini provider package is not installed. Install google-generativeai."
            ) from exc

        self._client = genai
        self._client.configure(api_key=self._api_key)
        return self._client

    async def create_chat_completion(
        self,
        messages: List[dict],
        functions: Optional[List[dict]] = None,
        function_call: Optional[str] = None,
        temperature: float = 0.2,
    ) -> dict:
        client = self._ensure_client()
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if functions is not None:
            kwargs["functions"] = functions
        if function_call is not None:
            kwargs["function_call"] = function_call

        try:
            response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
            return self._normalize_response(response)
        except Exception as exc:
            logger.exception("Gemini provider call failed")
            raise GeminiOrchestratorError("Gemini provider call failed") from exc

    def _normalize_response(self, response: Any) -> dict:
        if isinstance(response, dict):
            return response

        if hasattr(response, "to_dict"):
            try:
                return response.to_dict()
            except Exception:
                pass

        try:
            return json.loads(json.dumps(response, default=lambda obj: getattr(obj, "__dict__", str(obj)), ensure_ascii=False))
        except Exception:
            return {"choices": []}

    def extract_message(self, choice: dict) -> dict:
        message = choice.get("message") or {}
        if isinstance(message, str):
            return {"content": message}
        if not isinstance(message, dict):
            return {}
        return message

    def extract_tool_invocation(self, message: dict) -> Optional[dict]:
        if not isinstance(message, dict):
            return None

        invocation = message.get("tool_call") or message.get("function_call") or message.get("tool_call_name")
        if isinstance(invocation, dict):
            return invocation
        return None

    def parse_tool_arguments(self, raw_arguments: Any) -> dict:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str):
            try:
                return json.loads(raw_arguments)
            except json.JSONDecodeError:
                return {}
        return {}


class ToolExecutor:
    def __init__(self, http_client: HTTPClient, settings: Settings):
        self._http_client = http_client
        self._settings = settings

    async def execute_tool(self, tool_name: str, tool_args: dict) -> dict:
        if tool_name != TOOL_NAME_UPDATE_CART:
            return {
                "tool": tool_name,
                "success": False,
                "result": {"error": "unsupported tool"},
            }

        try:
            result = await update_cart(self._http_client, self._settings, **tool_args)
            return {
                "tool": TOOL_NAME_UPDATE_CART,
                "success": bool(result.get("success", False)),
                "result": result,
            }
        except Exception as exc:
            logger.exception("Cart tool execution failed")
            return {
                "tool": TOOL_NAME_UPDATE_CART,
                "success": False,
                "result": {"error": str(exc)},
            }


class GeminiOrchestrator:
    def __init__(
        self,
        settings: Settings,
        session_service: SessionService,
        http_client: HTTPClient,
        menu_provider: Optional[MenuContextProvider] = None,
        llm_adapter: Optional[GeminiProviderAdapter] = None,
        tool_executor: Optional[ToolExecutor] = None,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self._settings = settings
        self._session_service = session_service
        self._http_client = http_client
        self._menu_provider = menu_provider or FallbackMenuContextProvider()
        self._llm_adapter = llm_adapter or GeminiProviderAdapter(settings.GEMINI_API_KEY, settings.GEMINI_MODEL)
        self._tool_executor = tool_executor or ToolExecutor(http_client, settings)
        self._prompt_builder = prompt_builder or PromptBuilder()

    async def process_user_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        result = {
            "assistant_text": "",
            "cart_events": [],
            "tool_results": [],
            "cart_snapshot": None,
        }

        menu_context = await self._menu_provider.get_menu_context(restaurant_id)
        session_snapshot = await self._collect_session_snapshot(restaurant_id, session_id)

        system_prompt = self._prompt_builder.build_system_prompt(menu_context, session_snapshot)
        message_history = self._prompt_builder.build_conversation_history(session_snapshot)

        messages = [{"role": "system", "content": system_prompt}] + message_history + [
            {"role": "user", "content": user_message}
        ]

        functions = [
            {
                "name": TOOL_NAME_UPDATE_CART,
                "description": "Update the tenant cart with dish-centric payloads.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "restaurant_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "action": {"type": "string", "enum": ["add", "remove", "update"]},
                        "dish_id": {"type": "integer"},
                        "quantity": {"type": "integer"},
                        "notes": {"type": ["string", "null"]},
                        "addons": {"type": "array"},
                    },
                    "required": ["restaurant_id", "session_id", "action", "dish_id", "quantity"],
                },
            }
        ]

        try:
            response = await self._llm_adapter.create_chat_completion(
                messages=messages,
                functions=functions,
                function_call="auto",
                temperature=0.2,
            )

            choice = (response.get("choices") or [{}])[0]
            message = self._llm_adapter.extract_message(choice)
            tool_invocation = self._llm_adapter.extract_tool_invocation(message)

            if tool_invocation is not None:
                tool_name = tool_invocation.get("name")
                raw_arguments = tool_invocation.get("arguments")
                tool_args = self._llm_adapter.parse_tool_arguments(raw_arguments)
                tool_args.setdefault("restaurant_id", restaurant_id)
                tool_args.setdefault("session_id", session_id)

                tool_result = await self._tool_executor.execute_tool(tool_name, tool_args)
                result["tool_results"].append(tool_result)

                if tool_result.get("success"):
                    payload = tool_result.get("result", {})
                    result["cart_events"].append(payload.get("cart_event") or {})
                    result["cart_snapshot"] = payload.get("cart") or result["cart_snapshot"]

                messages.append(
                    {
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )

                second_response = await self._llm_adapter.create_chat_completion(
                    messages=messages,
                    temperature=0.2,
                )
                second_choice = (second_response.get("choices") or [{}])[0]
                message = self._llm_adapter.extract_message(second_choice)

            assistant_text = (message.get("content") or "").strip()
            if not assistant_text:
                if result["tool_results"] and not result["tool_results"][0].get("success"):
                    assistant_text = "عذراً، لم نتمكن من تحديث السلة الآن. حاول مرة أخرى لاحقاً."
                else:
                    assistant_text = "عذراً، لم أتمكن من معالجة طلبك. هل يمكنك قول ذلك بطريقة مختلفة؟"

            result["assistant_text"] = assistant_text
            await self._persist_session_turn(restaurant_id, session_id, user_message, assistant_text, result["cart_snapshot"])
            return result
        except GeminiOrchestratorError:
            raise
        except Exception as exc:
            logger.exception("Gemini orchestration failed")
            raise GeminiOrchestratorError("Orchestration failed") from exc

    async def _collect_session_snapshot(self, restaurant_id: str, session_id: str) -> Optional[dict]:
        try:
            return await self._session_service.collect_session_snapshot(restaurant_id, session_id)
        except Exception:
            logger.exception("Failed to load session snapshot")
            return None

    async def _persist_session_turn(
        self,
        restaurant_id: str,
        session_id: str,
        user_message: str,
        assistant_text: str,
        cart_snapshot: Optional[dict],
    ) -> None:
        try:
            await self._session_service.persist_conversation_turn(restaurant_id, session_id, user_message, assistant_text)
        except Exception:
            logger.exception("Failed to persist conversation turn")

        if cart_snapshot is not None:
            try:
                await self._session_service.save_cart_snapshot(restaurant_id, session_id, cart_snapshot)
            except Exception:
                logger.exception("Failed to persist cart snapshot")

    async def process_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        return await self.process_user_message(restaurant_id, session_id, user_message)
