"""Gemini-based conversation orchestrator - decomposed architecture.

Phase 10: All hardcoded values moved to config.
Phase 11: Tool call validation via ToolCallValidator.
Phase 18: Prompt management via PromptManager.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import google.generativeai as genai

from app.core.config import Settings
from app.core.constants import TOOL_NAME_UPDATE_CART
from app.services.session_service import SessionService
from app.services.prompt_builder import PromptBuilder
from app.services.prompt_manager import PromptManager
from app.services.menu_context_provider import MenuContextProvider, create_menu_context_provider
from app.services.cart_backend_gateway import CartBackendGateway
from app.services.tool_execution_coordinator import ToolExecutionCoordinator
from app.services.tool_call_validator import ToolCallValidator
from app.infrastructure.http_client import HTTPClient
from app.infrastructure.redis_client import RedisClient
from app.infrastructure.retry_service import RetryService, RetryPolicy, CircuitBreakerOpenError
from app.infrastructure.circuit_breaker import CircuitBreakerRegistry

logger = logging.getLogger(__name__)


class GeminiOrchestratorError(Exception):
    pass


class GeminiOrchestrator:
    """Orchestrate multi-turn conversations with Gemini using decomposed components.
    
    Architecture:
    - PromptBuilder: Constructs system prompts and history
    - MenuContextProvider: Retrieves menu data (mock or production)
    - CartBackendGateway: Handles cart mutations with idempotency
    - ToolExecutionCoordinator: Coordinates tool execution
    - This class: Composes components and manages conversation flow
    """
    
    def __init__(
        self,
        settings: Settings,
        session_service: SessionService,
        http_client: HTTPClient,
        redis_client: RedisClient,
    ) -> None:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self._settings = settings
        self._session_service = session_service
        self._http_client = http_client
        self._redis_client = redis_client
        
        # Initialize decomposed components
        self._prompt_builder = PromptBuilder()
        self._prompt_manager = PromptManager(settings)
        self._tool_call_validator = ToolCallValidator(settings)
        self._menu_provider = create_menu_context_provider(
            http_client, 
            redis_client, 
            settings,
            use_mock=not settings.ENABLE_REAL_MENU
        )
        self._cart_gateway = CartBackendGateway(http_client, settings)
        self._tool_coordinator = ToolExecutionCoordinator(self._cart_gateway, self._tool_call_validator)
        
        # Register tools
        self._tool_coordinator.register_tool(TOOL_NAME_UPDATE_CART, self._create_cart_tool())
        
        # Register offer code tool if enabled
        if settings.ENABLE_OFFER_CODES:
            from app.tools.cart_tools import validate_offer_code
            self._tool_coordinator.register_tool("validate_offer_code", self._create_offer_code_tool())
        
        # Construct GenerativeModel instance for reuse
        try:
            self._model = genai.GenerativeModel(model=settings.GEMINI_MODEL)
        except Exception:
            self._model = genai.GenerativeModel()
    
    def _create_cart_tool(self):
        """Create the cart update tool callable."""
        async def cart_tool(
            turn_id: str,
            restaurant_id: str,
            session_id: str,
            action: str,
            dish_id: int,
            quantity: int,
            notes: Optional[str] = None,
            addons: Optional[list[dict]] = None,
        ) -> dict:
            """Update cart tool - delegates to gateway."""
            return await self._cart_gateway.update_cart(
                session_id=session_id,
                turn_id=turn_id,
                restaurant_id=restaurant_id,
                action=action,
                dish_id=dish_id,
                quantity=quantity,
                notes=notes,
                addons=addons,
            )
        
        return cart_tool
    
    def _create_offer_code_tool(self):
        """Create the offer code validation tool callable."""
        from app.tools.cart_tools import validate_offer_code
        
        async def offer_code_tool(
            turn_id: str,
            restaurant_id: str,
            session_id: str,
            code: str,
            subtotal: float,
        ) -> dict:
            """Validate offer code tool - delegates to gateway."""
            return await validate_offer_code(
                cart_gateway=self._cart_gateway,
                turn_id=turn_id,
                restaurant_id=restaurant_id,
                session_id=session_id,
                code=code,
                subtotal=subtotal,
            )
        
        return offer_code_tool
    
    async def _retry_genai_call(self, callable, *args, **kwargs):
        """Retry GenAI calls using RetryService with circuit breaker.
        
        Phase 10: All values from settings.
        """
        cb_config = self._settings.circuit_breaker_config
        gemini_config = self._settings.gemini_config
        
        gemini_cb = CircuitBreakerRegistry().get_or_create(
            name="gemini",
            failure_threshold=cb_config.failure_threshold,
            recovery_timeout=cb_config.recovery_timeout,
            half_open_max_calls=cb_config.half_open_max_calls,
        )
        
        retry_policy = RetryPolicy(
            retryable_exceptions=(Exception,),  # Catch all for GenAI errors
            retryable_status_codes=self._settings.retryable_status_codes_set,
            max_attempts=gemini_config.max_retries,
            base_delay=gemini_config.base_delay,
            max_delay=gemini_config.max_delay,
            jitter_factor=gemini_config.jitter_factor,
        )
        
        retry_service = RetryService()
        
        try:
            return await retry_service.execute(
                callable,
                args=args,
                kwargs=kwargs,
                policy=retry_policy,
                circuit_breaker=gemini_cb,
                operation_name="gemini_send_message",
            )
        except CircuitBreakerOpenError as exc:
            raise GeminiOrchestratorError(f"Gemini service unavailable: {exc}") from exc
        except Exception as exc:
            raise GeminiOrchestratorError(f"Gemini call failed after retries: {exc}") from exc
    
    async def process_user_message(
        self,
        restaurant_id: str,
        session_id: str,
        user_message: str,
        turn_id: Optional[str] = None,
    ) -> dict:
        """Process a user message with full orchestration.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            user_message: User's message text
            turn_id: Optional turn ID for correlation (generated if not provided)
            
        Returns:
            Dictionary with assistant text, cart events, tool results, and cart snapshot
        """
        # Generate turn ID if not provided
        if not turn_id:
            turn_id = f"turn_{session_id[:8]}_{__import__('time').time_ns()}"
        
        log_ctx = {
            "turn_id": turn_id,
            "restaurant_id": restaurant_id,
            "session_id": session_id,
        }
        
        logger.info("Processing user message", extra=log_ctx)
        
        # Get menu context
        menu_context = await self._menu_provider.get_menu_context(restaurant_id)
        
        # Build prompt and history
        system_prompt = self._prompt_builder.build_system_prompt()
        history = self._prompt_builder.build_initial_history(menu_context, system_prompt)
        
        result: Dict[str, Any] = {
            "assistant_text": "",
            "cart_events": [],
            "tool_results": [],
            "cart_snapshot": None,
            "turn_id": turn_id,
        }
        
        # Prepare tools for Gemini
        update_cart_tool = self._tool_coordinator.get_tool(TOOL_NAME_UPDATE_CART)
        if update_cart_tool is None:
            raise GeminiOrchestratorError("Update cart tool not registered")
        
        tools = [
            {
                "name": TOOL_NAME_UPDATE_CART,
                "description": "تحديث سلة المستخدم (إضافة/حذف/تعديل) للمطعم",
                "callable": update_cart_tool,
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
        
        # Add offer code tool if enabled
        if self._settings.ENABLE_OFFER_CODES and self._tool_coordinator.has_tool("validate_offer_code"):
            validate_offer_tool = self._tool_coordinator.get_tool("validate_offer_code")
            if validate_offer_tool is not None:
                tools.append({
                    "name": "validate_offer_code",
                    "description": "التحقق من صحة كود الخصم وتطبيقه على السلة",
                    "callable": validate_offer_tool,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "restaurant_id": {"type": "string"},
                            "session_id": {"type": "string"},
                            "code": {"type": "string"},
                            "subtotal": {"type": "number"},
                        },
                        "required": ["restaurant_id", "session_id", "code", "subtotal"],
                    },
                })
        
        gemini_cfg = self._settings.gemini_config

        async def _send_message(chat, msg, temperature=gemini_cfg.default_temperature):
            return await chat.send_message_async(msg, temperature=temperature)
        
        try:
            # Start chat
            try:
                chat = await self._model.start_chat(history=history, tools=tools)
            except TypeError:
                chat = self._model.start_chat(history=history, tools=tools)
            
            # Send user message
            response = await self._retry_genai_call(
                _send_message,
                chat,
                {"role": "user", "content": user_message},
                temperature=gemini_cfg.default_temperature
            )
            
            # Handle function call if present
            function_call = getattr(response, "function_call", None) or (
                response.get("function_call") if isinstance(response, dict) else None
            )
            
            assistant_text = ""
            
            if function_call:
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
                
                # Ensure essential identifiers
                parsed_args.setdefault("restaurant_id", restaurant_id)
                parsed_args.setdefault("session_id", session_id)
                
                # Execute tool through coordinator
                tool_result = await self._tool_coordinator.execute_tool(
                    tool_name=func_name,
                    turn_id=turn_id,
                    arguments=parsed_args,
                )
                
                result["tool_results"].append({
                    "tool": func_name,
                    "result": tool_result,
                    "success": bool(tool_result.get("success", False))
                })
                
                if tool_result.get("success"):
                    if func_name == TOOL_NAME_UPDATE_CART:
                        result["cart_events"].append(tool_result.get("cart_event", {}))
                        result["cart_snapshot"] = tool_result.get("cart", {})
                
                # Get follow-up from model
                tool_message = {
                    "role": "tool",
                    "name": func_name,
                    "content": json.dumps(tool_result, ensure_ascii=False)
                }
                followup = await self._retry_genai_call(_send_message, chat, tool_message, temperature=gemini_cfg.default_temperature)
                
                assistant_text = ""
                if isinstance(followup, dict):
                    assistant_text = (followup.get("content") or "").strip()
                else:
                    assistant_text = getattr(followup, "content", "") or ""
                    assistant_text = assistant_text.strip()
            else:
                # No function call
                if isinstance(response, dict):
                    assistant_text = (response.get("content") or "").strip()
                else:
                    assistant_text = getattr(response, "content", "") or ""
                    assistant_text = assistant_text.strip()
            
            # Default responses
            if not assistant_text and result["tool_results"]:
                assistant_text = "تم تحديث السلة. هل هناك أي شيء آخر أستطيع مساعدتك به؟"
            
            if not assistant_text:
                assistant_text = "عذراً، لم أتمكن من معالجة طلبك. هل يمكنك قول ذلك بطريقة مختلفة؟"
            
            result["assistant_text"] = assistant_text
            
            # Persist conversation turn
            await self._session_service.persist_conversation_turn(
                restaurant_id, session_id, user_message, assistant_text, turn_id
            )
            
            if result["cart_snapshot"] is not None:
                await self._session_service.save_cart_snapshot(restaurant_id, session_id, result["cart_snapshot"])
            
            logger.info("Message processing completed", extra={**log_ctx, "success": True})
            return result
            
        except Exception as exc:
            logger.exception("Gemini orchestration failed", extra=log_ctx)
            raise GeminiOrchestratorError("Orchestration failed") from exc
    
    async def process_message(self, restaurant_id: str, session_id: str, user_message: str) -> dict:
        """Alias for the public message processing entry point."""
        return await self.process_user_message(restaurant_id, session_id, user_message)