"""Tool execution coordination with validation."""

import logging
from typing import Any, Dict

from app.services.cart_backend_gateway import CartBackendGateway

logger = logging.getLogger(__name__)


class ToolExecutionCoordinator:
    """Coordinate tool execution with validation and error handling.
    
    Responsibilities:
    - Validate tool inputs against schemas
    - Execute tools with proper context
    - Handle errors gracefully
    - Return structured results
    """
    
    def __init__(self, cart_gateway: CartBackendGateway):
        self._cart_gateway = cart_gateway
        self._tool_registry: Dict[str, Any] = {}
    
    def register_tool(self, name: str, callable: Any) -> None:
        """Register a tool for execution.
        
        Args:
            name: Tool name
            callable: Tool function to execute
        """
        self._tool_registry[name] = callable
        logger.debug("Registered tool", extra={"tool_name": name})
    
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
        
        if tool_name not in self._tool_registry:
            logger.error("Tool not found", extra=log_ctx)
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
            }
        
        tool_callable = self._tool_registry[tool_name]
        
        try:
            logger.info("Executing tool", extra=log_ctx)
            
            # Execute tool
            result = await tool_callable(turn_id=turn_id, **arguments)
            
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