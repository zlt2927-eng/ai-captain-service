"""Unit tests for cart backend gateway."""

import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.services.cart_backend_gateway import CartBackendGateway
from app.core.constants import (
    ERROR_CODE_INVALID_ADDON,
    ERROR_CODE_DISH_NOT_AVAILABLE,
    ERROR_CODE_DISH_NOT_FOUND,
    ERROR_CODE_CROSS_TENANT_VIOLATION,
    ERROR_CODE_VALIDATION_ERROR,
)


class TestCartBackendGateway:
    """Test cart backend gateway functionality."""

    @pytest.fixture
    def mock_http_client(self):
        """Provide mock HTTP client."""
        mock = MagicMock()
        mock.post_json = AsyncMock()
        mock.get_json = AsyncMock()
        return mock

    @pytest.fixture
    def gateway(self, mock_http_client, test_settings):
        """Provide CartBackendGateway with mocked HTTP client."""
        return CartBackendGateway(mock_http_client, test_settings)

    def test_generate_idempotency_key(self, gateway):
        """Test idempotency key generation."""
        key = gateway._generate_idempotency_key(
            session_id="sess_123",
            turn_id="turn_001",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        assert key.startswith("cart_mutation:")
        assert len(key) == len("cart_mutation:") + 32  # 32 chars from SHA256
        
        # Same inputs should generate same key
        key2 = gateway._generate_idempotency_key(
            session_id="sess_123",
            turn_id="turn_001",
            action="add",
            dish_id=101,
            quantity=2,
        )
        assert key == key2
        
        # Different inputs should generate different keys
        key3 = gateway._generate_idempotency_key(
            session_id="sess_123",
            turn_id="turn_001",
            action="add",
            dish_id=101,
            quantity=3,  # Different quantity
        )
        assert key != key3

    def test_generate_idempotency_key_consistency(self, gateway):
        """Test idempotency key is deterministic."""
        keys = []
        for _ in range(10):
            key = gateway._generate_idempotency_key(
                session_id="sess_123",
                turn_id="turn_001",
                action="add",
                dish_id=101,
                quantity=2,
            )
            keys.append(key)
        
        # All keys should be identical
        assert len(set(keys)) == 1

    @pytest.mark.asyncio
    async def test_update_cart_success(self, gateway, mock_http_client):
        """Test successful cart update."""
        mock_http_client.post_json.return_value = {
            "success": True,
            "message": "Cart updated",
            "cart": {"items": [{"dish_id": 101, "quantity": 2}]},
            "cart_event": {"action": "add", "dish_id": 101},
        }
        
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        assert result["success"] is True
        assert "cart" in result
        assert "idempotency_key" in result
        mock_http_client.post_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_cart_with_addons(self, gateway, mock_http_client):
        """Test cart update with addons."""
        mock_http_client.post_json.return_value = {
            "success": True,
            "cart": {"items": []},
            "cart_event": {},
        }
        
        addons = [{"addon_id": 501, "quantity": 1}]
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
            addons=addons,
        )
        
        assert result["success"] is True
        # Verify addons were passed in payload
        call_args = mock_http_client.post_json.call_args
        payload = call_args[0][1]
        assert "addons" in payload

    @pytest.mark.asyncio
    async def test_update_cart_with_notes(self, gateway, mock_http_client):
        """Test cart update with special notes."""
        mock_http_client.post_json.return_value = {
            "success": True,
            "cart": {"items": []},
            "cart_event": {},
        }
        
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
            notes="بدون بصل",
        )
        
        assert result["success"] is True
        call_args = mock_http_client.post_json.call_args
        payload = call_args[0][1]
        assert payload["notes"] == "بدون بصل"

    @pytest.mark.asyncio
    async def test_update_cart_laravel_error_dish_not_available(self, gateway, mock_http_client):
        """Test handling of dish not available error from Laravel."""
        mock_http_client.post_json.return_value = {
            "success": False,
            "error": "DISH_NOT_AVAILABLE",
            "error_code": ERROR_CODE_DISH_NOT_AVAILABLE,
            "message": "Dish not available",
        }
        
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        assert result["success"] is False
        assert result["error_code"] == ERROR_CODE_DISH_NOT_AVAILABLE

    @pytest.mark.asyncio
    async def test_update_cart_laravel_error_invalid_addon(self, gateway, mock_http_client):
        """Test handling of invalid addon error from Laravel."""
        mock_http_client.post_json.return_value = {
            "success": False,
            "error": "INVALID_ADDON",
            "error_code": ERROR_CODE_INVALID_ADDON,
        }
        
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        assert result["success"] is False
        assert result["error_code"] == ERROR_CODE_INVALID_ADDON

    @pytest.mark.asyncio
    async def test_update_cart_http_error(self, gateway, mock_http_client):
        """Test handling of HTTP error."""
        from app.infrastructure.http_client import HTTPClientError
        mock_http_client.post_json.side_effect = HTTPClientError("Connection failed")
        
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        assert result["success"] is False
        assert "error" in result
        assert "idempotency_key" in result

    @pytest.mark.asyncio
    async def test_update_cart_invalid_addons(self, gateway, mock_http_client):
        """Test validation of addon structure."""
        mock_http_client.post_json.return_value = {
            "success": True,
            "cart": {"items": []},
            "cart_event": {},
        }
        
        # Addons without addon_id should be caught
        addons = [{"quantity": 1}]  # Missing addon_id
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
            addons=addons,
        )
        
        # Should fail validation
        assert result["success"] is False
        assert "invalid_addons" in result

    @pytest.mark.asyncio
    async def test_validate_offer_code_success(self, gateway, mock_http_client):
        """Test successful offer code validation."""
        mock_http_client.post_json.return_value = {
            "valid": True,
            "code": "SAVE20",
            "discount_type": "percentage",
            "discount_value": 20,
            "discount_amount": 30.0,
        }
        
        result = await gateway.validate_offer_code(
            restaurant_id="rest_1",
            session_id="sess_123",
            turn_id="turn_001",
            code="SAVE20",
            subtotal=150.0,
        )
        
        assert result["valid"] is True
        assert result["discount_type"] == "percentage"
        assert result["discount_amount"] == 30.0

    @pytest.mark.asyncio
    async def test_validate_offer_code_invalid(self, gateway, mock_http_client):
        """Test invalid offer code."""
        mock_http_client.post_json.return_value = {
            "valid": False,
            "error": "OFFER_CODE_NOT_FOUND",
        }
        
        result = await gateway.validate_offer_code(
            restaurant_id="rest_1",
            session_id="sess_123",
            turn_id="turn_001",
            code="INVALID",
            subtotal=150.0,
        )
        
        assert result["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_offer_code_http_error(self, gateway, mock_http_client):
        """Test offer code validation with HTTP error."""
        from app.infrastructure.http_client import HTTPClientError
        mock_http_client.post_json.side_effect = HTTPClientError("Connection failed")
        
        result = await gateway.validate_offer_code(
            restaurant_id="rest_1",
            session_id="sess_123",
            turn_id="turn_001",
            code="SAVE20",
            subtotal=150.0,
        )
        
        assert result["valid"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_session_order_success(self, gateway, mock_http_client):
        """Test getting session order."""
        mock_http_client.get_json.return_value = {
            "success": True,
            "order": {
                "id": 123,
                "order_number": "ORD-001",
                "total": 150.0,
            },
        }
        
        result = await gateway.get_session_order("rest_1", "sess_123")
        
        assert result["success"] is True
        assert result["order"]["id"] == 123

    @pytest.mark.asyncio
    async def test_get_session_order_not_found(self, gateway, mock_http_client):
        """Test getting session order when not found."""
        mock_http_client.get_json.return_value = {
            "success": False,
            "message": "No order found",
        }
        
        result = await gateway.get_session_order("rest_1", "sess_123")
        
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_session_order_http_error(self, gateway, mock_http_client):
        """Test getting session order with HTTP error."""
        from app.infrastructure.http_client import HTTPClientError
        mock_http_client.get_json.side_effect = HTTPClientError("Connection failed")
        
        result = await gateway.get_session_order("rest_1", "sess_123")
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_update_cart_idempotency_key_included(self, gateway, mock_http_client):
        """Test that idempotency key is included in result."""
        mock_http_client.post_json.return_value = {
            "success": True,
            "cart": {"items": []},
            "cart_event": {},
        }
        
        result = await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        assert "idempotency_key" in result
        assert result["idempotency_key"].startswith("cart_mutation:")

    @pytest.mark.asyncio
    async def test_update_cart_headers_include_correlation(self, gateway, mock_http_client):
        """Test that headers include correlation IDs."""
        mock_http_client.post_json.return_value = {
            "success": True,
            "cart": {"items": []},
            "cart_event": {},
        }
        
        await gateway.update_cart(
            session_id="sess_123",
            turn_id="turn_001",
            restaurant_id="rest_1",
            action="add",
            dish_id=101,
            quantity=2,
        )
        
        # Verify headers were passed
        call_args = mock_http_client.post_json.call_args
        headers = call_args[1].get("headers", {})
        assert "X-Idempotency-Key" in headers
        assert "X-Session-Id" in headers
        assert "X-Turn-Id" in headers