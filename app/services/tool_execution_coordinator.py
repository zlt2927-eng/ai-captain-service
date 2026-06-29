"""Tool execution coordination with validation.

Phase 11: Integrated with ToolCallValidator for LLM output validation.
"""

import logging
from typing import Any, Dict, Optional

from app.services.cart_backend_gateway import CartBackendGateway
from app.services.tool_call_validator import ToolCallValidator, ToolCallValidationResult

logger = logging.getLogger(__name__)


class ToolExecutionCoordinator:
    """Coordinate tool execution with validation and error handling.
    
    Responsibilities:
    - Validate tool inputs against schemas (Phase 11)
    - Execute tools with proper context
    - Handle errors gracefully
    - Return structured results
    """
    
    def __init__(self, cart_gateway: CartBackendGateway, tool_call_validator: Optional[ToolCallValidator] = None):
        self._cart_gateway = cart_gateway
        self._tool_registry: Dict[str, Any] = {}
        self._tool_call_validator = tool_call_validator or ToolCallValidator(
            # Use defaults if no settings provided
            __import__('types').SimpleNamespace(
                TOOL_VALIDATION_STRICT=True,
                TOOL_VALIDATION_MAX_ARGUMENTS=20,
                TOOL_VALIDATION_MAX_STRING_LENGTH=10000,
                TOOL_VALIDATION_MAX_ARRAY_LENGTH=100,
                TOOL_VALIDATION_MAX_NUMBER_VALUE=1_000_000_000.0,
                TOOL_VALIDATION_MIN_NUMBER_VALUE=-1_000_000_000.0,
                PROMPT_VALIDATION_STRICT=True,
                PROMPT_MAX_RENDERED_CHARS=100_000,
                PROMPT_MAX_TEMPLATE_DEPTH=5,
                PROMPT_HOT_RELOAD_INTERVAL_SECONDS=60,
                PROMPT_HOT_RELOAD_ENABLED=True,
            )
        )
    
    def register_tool(self, name: str, callable: Any) -> None:
        """Register a tool for execution.
        
        Args:
            name: Tool name
            callable: Tool function to execute
        """
        self._tool_registry[name] = callable
        logger.debug("Registered tool", extra={"tool_name": name})
    
    def get_tool(self, name: str) -> Optional[Any]:
        """Get a registered tool by name.
        
        Args:
            name: Tool name
            
        Returns:
            Tool callable or None if not found
        """
        return self._tool_registry.get(name)
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered.
        
        Args:
            name: Tool name
            
        Returns:
            True if tool is registered, False otherwise
        """
        return name in self._tool_registry
    
    async def execute_tool(
        self,
        tool_name: str,
        turn_id: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool with validation.
        
        Args:
            tool_name: Name of tool to execute
            turn_id: Turn identifier for correlation
            arguments: Tool arguments from LLM
            
        Returns:
            Tool execution result
        """
        log_ctx = {"tool_name": tool_name, "turn_id": turn_id}
        
        tool_callable = self.get_tool(tool_name)
        if tool_callable is None:
            logger.error("Tool not found", extra=log_ctx)
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
            }
        
        try:
            logger.info("Executing tool", extra=log_ctx)
            
            # Phase 11: Validate tool call arguments before execution
            validation_result = self._tool_call_validator.validate(
                tool_name=tool_name,
                arguments=arguments,
                turn_id=turn_id,
            )
            
            if not validation_result.valid:
                logger.warning(
                    "Tool call validation failed, returning error",
                    extra={**log_ctx, "errors": [str(e) for e in validation_result.errors]},
                )
                return {
                    "success": False,
                    "error": f"Tool call validation failed: {validation_result.errors[0].reason if validation_result.errors else 'Unknown error'}",
                    "validation_errors": [str(e) for e in validation_result.errors],
                }
            
            # Use sanitized arguments from validator
            sanitized_args = validation_result.sanitized_arguments
            
            # Inject turn_id into arguments if not present
            if "turn_id" not in sanitized_args:
                sanitized_args["turn_id"] = turn_id
            
            # Execute tool with sanitized arguments
            result = await tool_callable(**sanitized_args)
            
            logger.info(
                "Tool execution completed",
                extra={**log_ctx, "success": result.get("success", False)}
            )
            
            return result
            
        except Exception as exc:
            logger.exception("Tool execution failed", extra=log_ctx)
            return {
                "success": False,
                "error": str(exc),
            }
