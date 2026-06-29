"""Unit tests for WebSocket authentication."""

import jwt
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import Settings
from app.websocket.auth import WebSocketAuth, AuthResult
from app.core.constants import WS_CLOSE_UNAUTHORIZED


class TestWebSocketAuth:
    """Test WebSocket authentication."""

    @pytest.fixture
    def test_settings(self):
        """Provide test settings."""
        return Settings()

    @pytest.fixture
    def auth(self, test_settings):
        """Provide WebSocketAuth instance."""
        return WebSocketAuth(test_settings)

    @pytest.fixture
    def mock_websocket(self):
        """Provide mock WebSocket."""
        mock_ws = MagicMock()
        mock_ws.close = AsyncMock()
        return mock_ws

    def test_generate_valid_token(self, test_settings):
        """Test JWT token generation."""
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, test_settings.WEBSOCKET_AUTH_SECRET, algorithm="HS256")
        assert token is not None
        assert isinstance(token, str)

    @pytest.mark.asyncio
    async def test_authenticate_success(self, auth, mock_websocket):
        """Test successful authentication."""
        # Generate valid token
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, "test-secret-key-for-testing-only", algorithm="HS256")

        result = await auth.authenticate(mock_websocket, token, "rest_1", "sess_123")
        
        assert result.success is True
        assert result.restaurant_id == "rest_1"
        assert result.session_id == "sess_123"
        assert result.error_reason is None

    @pytest.mark.asyncio
    async def test_authenticate_expired_token(self, auth, mock_websocket):
        """Test authentication with expired token."""
        # Generate expired token
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) - 3600,  # Expired 1 hour ago
        }
        token = jwt.encode(payload, "test-secret-key-for-testing-only", algorithm="HS256")

        result = await auth.authenticate(mock_websocket, token, "rest_1", "sess_123")
        
        assert result.success is False
        assert result.error_reason == "Token expired"
        assert result.close_code == WS_CLOSE_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_authenticate_invalid_token(self, auth, mock_websocket):
        """Test authentication with invalid token."""
        result = await auth.authenticate(mock_websocket, "invalid-token", "rest_1", "sess_123")
        
        assert result.success is False
        assert result.error_reason == "Invalid token"

    @pytest.mark.asyncio
    async def test_authenticate_restaurant_id_mismatch(self, auth, mock_websocket):
        """Test authentication with wrong restaurant_id."""
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, "test-secret-key-for-testing-only", algorithm="HS256")

        result = await auth.authenticate(mock_websocket, token, "rest_2", "sess_123")
        
        assert result.success is False
        assert "restaurant_id mismatch" in result.error_reason

    @pytest.mark.asyncio
    async def test_authenticate_session_id_mismatch(self, auth, mock_websocket):
        """Test authentication with wrong session_id."""
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, "test-secret-key-for-testing-only", algorithm="HS256")

        result = await auth.authenticate(mock_websocket, token, "rest_1", "sess_456")
        
        assert result.success is False
        assert "session_id mismatch" in result.error_reason

    @pytest.mark.asyncio
    async def test_authenticate_wrong_secret(self, auth, mock_websocket):
        """Test authentication with wrong secret."""
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        # Encode with different secret
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        result = await auth.authenticate(mock_websocket, token, "rest_1", "sess_123")
        
        assert result.success is False
        assert result.error_reason == "Invalid token"

    @pytest.mark.asyncio
    async def test_authenticate_algorithm_none_attack(self, auth, mock_websocket):
        """Test authentication prevents 'alg: none' attack."""
        # Create token with alg: none (PyJWT should reject this)
        import json
        header = {"typ": "JWT", "alg": "none"}
        payload_data = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        
        # Manually create token with none algorithm
        header_b64 = jwt.utils.base64url_encode(json.dumps(header).encode())
        payload_b64 = jwt.utils.base64url_encode(json.dumps(payload_data).encode())
        token = f"{header_b64.decode()}.{payload_b64.decode()}."

        result = await auth.authenticate(mock_websocket, token, "rest_1", "sess_123")
        
        assert result.success is False

    @pytest.mark.asyncio
    async def test_close_unauthorized(self, auth, mock_websocket):
        """Test closing WebSocket with unauthorized status."""
        auth_result = AuthResult(
            success=False,
            error_reason="Token expired",
            close_code=WS_CLOSE_UNAUTHORIZED,
        )
        
        await auth.close_unauthorized(mock_websocket, auth_result)
        
        mock_websocket.close.assert_called_once_with(
            code=WS_CLOSE_UNAUTHORIZED,
            reason="Token expired"
        )

    @pytest.mark.asyncio
    async def test_close_unauthorized_default_reason(self, auth, mock_websocket):
        """Test closing WebSocket with default reason."""
        auth_result = AuthResult(
            success=False,
            error_reason=None,
            close_code=WS_CLOSE_UNAUTHORIZED,
        )
        
        await auth.close_unauthorized(mock_websocket, auth_result)
        
        mock_websocket.close.assert_called_once_with(
            code=WS_CLOSE_UNAUTHORIZED,
            reason="Unauthorized"
        )

    @pytest.mark.asyncio
    async def test_authenticate_missing_exp_claim(self, auth, mock_websocket):
        """Test authentication requires exp claim."""
        # Create token without exp claim
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
        }
        token = jwt.encode(payload, "test-secret-key-for-testing-only", algorithm="HS256")

        result = await auth.authenticate(mock_websocket, token, "rest_1", "sess_123")
        
        assert result.success is False
        assert "Invalid token" in result.error_reason