"""Unit tests for tool execution coordinator."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.tool_execution_coordinator import ToolExecutionCoordinator
from app.services.cart_backend_gateway import CartBackendGateway


class TestToolExecutionCoordinator:
    """Test tool execution coordinator functionality."""

    @pytest.fixture
    def mock_cart_gateway(self):
        """Provide mock cart gateway."""
        mock = MagicMock(spec=CartBackendGateway)
        mock.update_cart = AsyncMock(return_value={"success": True})
        return mock

    @pytest.fixture
    def coordinator(self, mock_cart_gateway):
        """Provide ToolExecutionCoordinator with mocked gateway."""
        return ToolExecutionCoordinator(mock_cart_gateway)

    def test_register_tool(self, coordinator):
        """Test tool registration."""
        def test_tool(**kwargs):
            return {"success": True}
        
        coordinator.register_tool("test_tool", test_tool)
        assert coordinator.has_tool("test_tool")
        assert coordinator.get_tool("test_tool") == test_tool

    def test_get_tool_not_found(self, coordinator):
        """Test getting non-existent tool."""
        assert coordinator.get_tool("nonexistent") is None
        assert coordinator.has_tool("nonexistent") is False

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, coordinator):
        """Test successful tool execution."""
        def test_tool(arg1, arg2):
            return {"success": True, "result": f"{arg1} {arg2}"}
        
        coordinator.register_tool("test_tool", test_tool)
        
        result = await coordinator.execute_tool(
            tool_name="test_tool",
            turn_id="turn_001",
            arguments={"arg1": "hello", "arg2": "world"},
        )
        
        assert result["success"] is True
        assert result["result"] == "hello world"

    @pytest.mark.asyncio
    async def test_execute_tool_injects_turn_id(self, coordinator):
        """Test that turn_id is injected if not provided."""
        executed_args = {}
        
        def test_tool(turn_id, **kwargs):
            executed_args["turn_id"] = turn_id
            return {"success": True}
        
        coordinator.register_tool("test_tool", test_tool)
        
        result = await coordinator.execute_tool(
            tool_name="test_tool",
            turn_id="turn_001",
            arguments={"arg1": "value"},
        )
        
        assert executed_args["turn_id"] == "turn_001"
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self, coordinator):
        """Test executing non-existent tool."""
        result = await coordinator.execute_tool(
            tool_name="nonexistent_tool",
            turn_id="turn_001",
            arguments={},
        )
        
        assert result["success"] is False
        assert "Unknown tool" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_tool_exception_handling(self, coordinator):
        """Test tool execution exception handling."""
        def failing_tool(**kwargs):
            raise ValueError("Tool failed")
        
        coordinator.register_tool("failing_tool", failing_tool)
        
        result = await coordinator.execute_tool(
            tool_name="failing_tool",
            turn_id="turn_001",
            arguments={},
        )
        
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_update_cart_tool(self, coordinator, mock_cart_gateway):
        """Test executing update_cart tool."""
        mock_cart_gateway.update_cart.return_value = {
            "success": True,
            "cart": {"items": []},
        }
        
        # Register the cart gateway's update_cart method
        coordinator.register_tool("update_cart", mock_cart_gateway.update_cart)
        
        result = await coordinator.execute_tool(
            tool_name="update_cart",
            turn_id="turn_001",
            arguments={
                "session_id": "sess_123",
                "restaurant_id": "rest_1",
                "action": "add",
                "dish_id": 101,
                "quantity": 2,
            },
        )
        
        assert result["success"] is True
        mock_cart_gateway.update_cart.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_with_complex_arguments(self, coordinator):
        """Test tool execution with complex arguments."""
        executed_args = {}
        
        def complex_tool(items, config, metadata):
            executed_args["items"] = items
            executed_args["config"] = config
            executed_args["metadata"] = metadata
            return {"success": True}
        
        coordinator.register_tool("complex_tool", complex_tool)
        
        result = await coordinator.execute_tool(
            tool_name="complex_tool",
            turn_id="turn_001",
            arguments={
                "items": [{"id": 1}, {"id": 2}],
                "config": {"key": "value"},
                "metadata": {"count": 2},
            },
        )
        
        assert result["success"] is True
        assert len(executed_args["items"]) == 2
        assert executed_args["config"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_multiple_tools_registration(self, coordinator):
        """Test registering multiple tools."""
        def tool1(**kwargs):
            return {"tool": "tool1"}
        
        def tool2(**kwargs):
            return {"tool": "tool2"}
        
        coordinator.register_tool("tool1", tool1)
        coordinator.register_tool("tool2", tool2)
        
        assert coordinator.has_tool("tool1")
        assert coordinator.has_tool("tool2")
        
        result1 = await coordinator.execute_tool("tool1", "turn_001", {})
        result2 = await coordinator.execute_tool("tool2", "turn_001", {})
        
        assert result1["tool"] == "tool1"
        assert result2["tool"] == "tool2"

    @pytest.mark.asyncio
    async def test_tool_overwrite(self, coordinator):
        """Test overwriting registered tool."""
        def tool_v1(**kwargs):
            return {"version": 1}
        
        def tool_v2(**kwargs):
            return {"version": 2}
        
        coordinator.register_tool("tool", tool_v1)
        coordinator.register_tool("tool", tool_v2)  # Overwrite
        
        result = await coordinator.execute_tool("tool", "turn_001", {})
        assert result["version"] == 2