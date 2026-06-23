"""Gemini-based conversation orchestrator for restaurant ordering."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

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
    """Orchestrate multi-turn conversations with Gemini."""

    def __init__(
        self,
        settings: Settings,
        session_service: SessionService,
        http_client: HTTPClient,
    ):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._settings = settings
        self._session_service = session_service
        self._http_client = http_client

    async def get_menu_context(self, restaurant_id: str) -> dict:
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

    def _build_system_prompt(self, menu_context: dict, session_notes: Optional[str] = None) -> str:
        menu_payload = json.dumps(menu_context, ensure_ascii=False, indent=2)
        prompt = [CAPTAIN_SYSTEM_PROMPT, "\nRESTAURANT_MENU_CONTEXT:\n", menu_payload]
        if session_notes:
            prompt.extend(["\nSESSION_NOTES:\n", session_notes])
        return "".join(prompt)

    async def _create_completion(self, **kwargs: Any) -> dict:
        return await asyncio.to_thread(genai.chat.completions.create, **kwargs)

    def _normalize_response(self, response: Any) -> dict:
        if isinstance(response, dict):
            return response
        try:
            return json.loads(json.dumps(response, default=lambda obj: getattr(obj, "__dict__", str(obj)), ensure_ascii=False))
        except Exception:
            return {}

    async def process_user_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        menu_context = await self.get_menu_context(restaurant_id)
        system_prompt = self._build_system_prompt(menu_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
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
                        "addons": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "addon_id": {"type": "integer"},
                                    "quantity": {"type": "integer"},
                                },
                                "required": ["addon_id", "quantity"],
                            },
                        },
                    },
                    "required": ["restaurant_id", "session_id", "action", "dish_id", "quantity"],
                },
            }
        ]

        result = {
            "assistant_text": "",
            "cart_events": [],
            "tool_results": [],
            "cart_snapshot": None,
        }

        try:
            response = await self._create_completion(
                model=self._settings.GEMINI_MODEL,
                messages=messages,
                functions=functions,
                function_call="auto",
                temperature=0.2,
            )
            response_data = self._normalize_response(response)
            choice = (response_data.get("choices") or [{}])[0]
            message = choice.get("message", {}) if isinstance(choice, dict) else {}

            if message.get("tool_call") or message.get("function_call"):
                call = message.get("tool_call") or message.get("function_call")
                tool_name = call.get("name")
                args_raw = call.get("arguments")
                tool_args = {}
                if isinstance(args_raw, str):
                    try:
                        tool_args = json.loads(args_raw)
                    except json.JSONDecodeError:
                        tool_args = {}
                elif isinstance(args_raw, dict):
                    tool_args = args_raw

                if tool_name == TOOL_NAME_UPDATE_CART:
                    tool_args["restaurant_id"] = restaurant_id
                    tool_args["session_id"] = session_id
                    tool_result = await update_cart(
                        self._http_client,
                        **tool_args,
                    )
                    result["tool_results"].append({
                        "tool": TOOL_NAME_UPDATE_CART,
                        "success": bool(tool_result.get("success", False)),
                        "result": tool_result,
                    })

                    if tool_result.get("success"):
                        result["cart_events"].append(tool_result.get("cart_event", {}))
                        result["cart_snapshot"] = tool_result.get("cart", {})

                    messages.append({
                        "role": "tool",
                        "name": TOOL_NAME_UPDATE_CART,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    })
                    response = await self._create_completion(
                        model=self._settings.GEMINI_MODEL,
                        messages=messages,
                        temperature=0.2,
                    )
                    response_data = self._normalize_response(response)
                    choice = (response_data.get("choices") or [{}])[0]
                    message = choice.get("message", {}) if isinstance(choice, dict) else {}

            assistant_text = (message.get("content") or "").strip()
            if not assistant_text:
                assistant_text = "عذراً، لم أتمكن من معالجة طلبك. هل يمكنك قول ذلك بطريقة مختلفة؟"

            result["assistant_text"] = assistant_text
            await self._session_service.persist_conversation_turn(
                restaurant_id,
                session_id,
                user_message,
                assistant_text,
            )
            if result["cart_snapshot"] is not None:
                await self._session_service.save_cart_snapshot(
                    restaurant_id, session_id, result["cart_snapshot"]
                )

            return result
        except Exception as exc:
            logger.error("Gemini orchestration failed", exc_info=True)
            raise GeminiOrchestratorError("Orchestration failed") from exc

    async def process_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        """Alias for the public message processing entry point."""
        return await self.process_user_message(restaurant_id, session_id, user_message)
