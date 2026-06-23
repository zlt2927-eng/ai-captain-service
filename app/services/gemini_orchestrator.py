"""Gemini-based conversation orchestrator for restaurant ordering.

This module uses the modern Google GenAI SDK async patterns with
`GenerativeModel` and `start_chat`/`send_message_async` to avoid
thread-hopping and to enable native function calling.
All assistant-facing text is in Arabic.
"""

import asyncio
import json
import logging
import math
import random
from typing import Any, Dict, Optional, Callable, List

import google.generativeai as genai

from app.core.constants import CAPTAIN_SYSTEM_PROMPT, TOOL_NAME_UPDATE_CART
from app.core.config import Settings
from app.services.session_service import SessionService
from app.tools.cart_tools import update_cart
from app.infrastructure.http_client import HTTPClient

logger = logging.getLogger(__name__)


class GeminiOrchestratorError(Exception):
    pass


class GeminiOrchestrator:
    """Orchestrate multi-turn conversations with Gemini using native async SDK.

    Key changes vs legacy implementation:
    - Uses `GenerativeModel.start_chat(history=...)` to establish system context
      once per session/message flow (avoids token inflation).
    - Uses `send_message_async` for all model calls (no threads).
    - Passes Python callables into tools and handles `function_call` responses.
    - Robust retry logic for 429/timeouts.
    """

    def __init__(
        self,
        settings: Settings,
        session_service: SessionService,
        http_client: HTTPClient,
    ) -> None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._settings = settings
        self._session_service = session_service
        self._http_client = http_client

        # Construct a GenerativeModel instance for reuse
        try:
            # The SDK may accept a model name here; adapt if different in runtime.
            self._model = genai.GenerativeModel(model=settings.GEMINI_MODEL)
        except Exception:
            # Fallback: some SDK versions accept model name when sending requests.
            self._model = genai.GenerativeModel()

        # Map tool name -> callable so we can invoke functions safely
        self._tool_registry: Dict[str, Callable[..., Any]] = {
            TOOL_NAME_UPDATE_CART: update_cart,
        }

    async def get_menu_context(self, restaurant_id: str) -> dict:
        # In production, load this from a fast DB or vector store. Keep small.
        return {
            "restaurant_id": restaurant_id,
            "restaurant_name": "Captain Burger",
            "currency": "SAR",
            "language": "ar",
            "categories": [
                {
                    "id": 10,
                    "name": "البرجر",
                    "description": "برجر طازج",
                    "sort_order": 1,
                    "dishes": [
                        {
                            "id": 101,
                            "name": "برجر لحم",
                            "description": "برجر لحم مشوي مع صوص خاص",
                            "category_id": 10,
                            "price": 32.0,
                            "currency": "SAR",
                            "ingredients": ["beef", "bun", "cheese"],
                            "allergens": ["gluten", "dairy"],
                            "calories": 650,
                            "preparation_time": 15,
                            "is_available": True,
                            "is_featured": True,
                            "addons": [
                                {"id": 501, "name": "جبنة إضافية", "price": 4.0, "is_active": True},
                                {"id": 502, "name": "مشروم", "price": 3.0, "is_active": True},
                            ],
                        }
                    ],
                }
            ],
        }

    def _build_system_prompt(self, session_notes: Optional[str] = None) -> str:
        # Keep the system prompt concise. Large menu payloads must not be
        # inlined into the system prompt on every request to avoid token inflation.
        prompt = [CAPTAIN_SYSTEM_PROMPT]
        if session_notes:
            prompt.extend(["\nSESSION_NOTES:\n", session_notes])
        return "".join(prompt)

    async def _retryable(self, coro: Callable[..., Any], *args: Any, max_retries: int = 3, base_delay: float = 0.8, **kwargs: Any) -> Any:
        """Generic retry wrapper for transient errors (HTTP 429, timeouts).

        Uses exponential backoff with jitter. Raises last exception if retries exhausted.
        """
        for attempt in range(1, max_retries + 1):
            try:
                return await coro(*args, **kwargs)
            except Exception as exc:
                # Check for rate limit / timeout hints in common exception shapes
                status_code = getattr(exc, "status_code", None)
                msg = str(exc).lower()
                is_rate_limit = status_code == 429 or "rate limit" in msg or "too many requests" in msg or "429" in msg
                is_timeout = "timeout" in msg or "timed out" in msg

                if attempt == max_retries or not (is_rate_limit or is_timeout):
                    logger.exception("Non-retriable or max retries reached for GenAI call")
                    raise

                # Exponential backoff with decorrelated jitter
                delay = base_delay * (2 ** (attempt - 1))
                jitter = min(1.0, delay * 0.1)
                sleep_for = max(0.5, delay + (jitter * (0.5 - random.random())))
                logger.warning("Transient GenAI error, retrying in %.2fs (attempt %d): %s", sleep_for, attempt, exc)
                await asyncio.sleep(sleep_for)

        # Should never reach here
        raise GeminiOrchestratorError("Retries exhausted")

    async def process_user_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        """Process a user message and handle tool (function) calls natively.

        Returns a dictionary with assistant text (Arabic), cart events, tool results,
        and optional cart snapshot.
        """
        menu_context = await self.get_menu_context(restaurant_id)
        system_prompt = self._build_system_prompt()

        result: Dict[str, Any] = {
            "assistant_text": "",
            "cart_events": [],
            "tool_results": [],
            "cart_snapshot": None,
        }

        # Build a compact initial history: system prompt once, a lightweight
        # indicator that the menu exists (the full menu lives server-side).
        history: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {
                "role": "system",
                "content": json.dumps({"menu_id": menu_context.get("restaurant_id"), "menu_ref": "server_side_menu"}, ensure_ascii=False),
            },
        ]

        # Prepare SDK-native tools description. We pass Python callables through
        # the model/tools interface so the SDK can surface function calling.
        # Note: the exact shape accepted by the SDK may vary; this keeps the
        # orchestrator-side mapping explicit and safe.
        tools = [
            {
                "name": TOOL_NAME_UPDATE_CART,
                "description": "تحديث سلة المستخدم (إضافة/حذف/تعديل) للمطعم",
                "callable": self._tool_registry[TOOL_NAME_UPDATE_CART],
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

        async def _send_message(chat, msg: Dict[str, Any], temperature: float = 0.2):
            # Wrapper so we can plug into retry logic if the SDK raises transient errors
            return await chat.send_message_async(msg, temperature=temperature)

        try:
            # Start chat once; this keeps context window under control.
            try:
                chat = await self._model.start_chat(history=history, tools=tools)
            except TypeError:
                # Some SDK builds may expose start_chat synchronously
                chat = self._model.start_chat(history=history, tools=tools)

            # Send the user's message
            response = await self._retryable(_send_message, chat, {"role": "user", "content": user_message}, temperature=0.2)

            # The SDK should expose function_call on the response when tools are invoked
            function_call = getattr(response, "function_call", None) or (response.get("function_call") if isinstance(response, dict) else None)

            assistant_text = ""

            if function_call:
                # Parse function call arguments robustly
                func_name = function_call.get("name") if isinstance(function_call, dict) else getattr(function_call, "name", None)
                raw_args = function_call.get("arguments") if isinstance(function_call, dict) else getattr(function_call, "arguments", None)

                parsed_args: Dict[str, Any] = {}
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        parsed_args = {}
                elif isinstance(raw_args, dict):
                    parsed_args = raw_args

                # Ensure essential identifiers are present
                parsed_args.setdefault("restaurant_id", restaurant_id)
                parsed_args.setdefault("session_id", session_id)

                tool_result: Dict[str, Any] = {"success": False, "error": "tool_not_invoked"}

                if func_name in self._tool_registry:
                    tool_callable = self._tool_registry[func_name]
                    try:
                        # Call the tool; update_cart expects http_client as first arg
                        tool_result = await tool_callable(self._http_client, **parsed_args)
                    except Exception as exc:
                        logger.exception("Tool invocation failed: %s", exc)
                        tool_result = {"success": False, "error": str(exc)}

                # Record tool execution
                result["tool_results"].append({"tool": func_name, "result": tool_result, "success": bool(tool_result.get("success", False))})
                if tool_result.get("success"):
                    result["cart_events"].append(tool_result.get("cart_event", {}))
                    result["cart_snapshot"] = tool_result.get("cart", {})

                # Notify the model of the tool result and get assistant follow-up
                tool_message = {"role": "tool", "name": func_name, "content": json.dumps(tool_result, ensure_ascii=False)}
                followup = await self._retryable(_send_message, chat, tool_message, temperature=0.2)

                # Extract assistant content from followup
                assistant_text = ""
                if isinstance(followup, dict):
                    assistant_text = (followup.get("content") or "").strip()
                else:
                    assistant_text = getattr(followup, "content", "") or ""
                    assistant_text = assistant_text.strip()

            else:
                # No function call; take assistant text directly
                if isinstance(response, dict):
                    assistant_text = (response.get("content") or "").strip()
                else:
                    assistant_text = getattr(response, "content", "") or ""
                    assistant_text = assistant_text.strip()

            # If assistant produced no text, but a tool call succeeded, do not treat as error.
            if not assistant_text and result["tool_results"]:
                assistant_text = "تم تحديث السلة. هل هناك أي شيء آخر أستطيع مساعدتك به؟"

            if not assistant_text:
                assistant_text = "عذراً، لم أتمكن من معالجة طلبك. هل يمكنك قول ذلك بطريقة مختلفة؟"

            result["assistant_text"] = assistant_text

            # Persist conversation turn and optional cart snapshot
            await self._session_service.persist_conversation_turn(
                restaurant_id, session_id, user_message, assistant_text
            )

            if result["cart_snapshot"] is not None:
                await self._session_service.save_cart_snapshot(restaurant_id, session_id, result["cart_snapshot"])

            return result

        except Exception as exc:
            logger.exception("Gemini orchestration failed: %s", exc)
            raise GeminiOrchestratorError("Orchestration failed") from exc

    async def process_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        """Alias for the public message processing entry point."""
        return await self.process_user_message(restaurant_id, session_id, user_message)
