"""Unit tests for WebSocket security - Phase 14."""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock

from app.core.config import Settings
from app.websocket.security import WebSocketSecurity, SecurityResult
from app.core.constants import WS_CLOSE_UNAUTHORIZED


class TestWebSocketSecurity:
    """Test WebSocket security functionality."""

    @pytest.fixture
    def mock_redis_client(self):
        """Provide mock Redis client."""
        mock = MagicMock()
        mock._ensure_client = AsyncMock(return_value=mock)
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock(return_value=True)
        mock.delete = AsyncMock(return_value=1)
        mock.exists = AsyncMock(return_value=0)
        mock.sadd = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=1)
        mock.scard = AsyncMock(return_value=0)
        return mock

    @pytest.fixture
    def test_settings(self):
        """Provide test settings with security configuration."""
        settings = Settings()
        settings.JWT_ALLOWED_ALGORITHMS = ["HS256"]
        settings.JWT_VALIDATE_ISSUER = False
        settings.JWT_VALIDATE_AUDIENCE = False
        settings.JWT_REQUIRE_KEY_ID = False
        settings.ENABLE_TOKEN_REVOCATION = True
        settings.TOKEN_REVOCATION_CHECK_INTERVAL_SECONDS = 300
        settings.MAX_HEADER_SIZE_BYTES = 8192
        settings.SECURITY_HEADERS_ENABLED = True
        settings.ALLOWED_CORS_ORIGINS = ["http://localhost:3000"]
        return settings

    @pytest.fixture
    def security(self, test_settings, mock_redis_client):
        """Provide WebSocketSecurity instance."""
        return WebSocketSecurity(mock_redis_client, test_settings)

    @pytest.mark.asyncio
    async def test_validate_jwt_token_success(self, security, test_settings):
        """Test JWT token validation succeeds for valid token."""
        import jwt
        import time
        
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        token = jwt.encode(payload, test_settings.WEBSOCKET_AUTH_SECRET, algorithm="HS256")
        
        result = await security.validate_jwt_token(token)
        
        assert result.valid is True
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_validate_jwt_token_expired(self, security, test_settings):
        """Test JWT token validation fails for expired token."""
        import jwt
        import time
        
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) - 3600,  # Expired
        }
        token = jwt.encode(payload, test_settings.WEBSOCKET_AUTH_SECRET, algorithm="HS256")
        
        result = await security.validate_jwt_token(token)
        
        assert result.valid is False
        assert "expired" in result.reason.lower()
        assert result.close_code == WS_CLOSE_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_validate_jwt_token_invalid_algorithm(self, security, test_settings):
        """Test JWT token validation fails for invalid algorithm."""
        import jwt
        
        # Create token with RS256 (not in allowed list)
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
        }
        # This will fail because we're using HS256 but claiming RS256
        token = jwt.encode(payload, test_settings.WEBSOCKET_AUTH_SECRET, algorithm="HS256")
        
        # Manually modify header to claim RS256
        import base64
        header = {"typ": "JWT", "alg": "RS256"}
        header_b64 = base64.urlsafe_b64encode(
            __import__('json').dumps(header).encode()
        ).decode().rstrip("=")
        
        parts = token.split(".")
        modified_token = f"{header_b64}.{parts[1]}.{parts[2]}"
        
        result = await security.validate_jwt_token(modified_token)
        
        assert result.valid is False
        assert "algorithm" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_validate_jwt_token_with_issuer(self, security, test_settings):
        """Test JWT token validation with issuer checking."""
        import jwt
        import time
        
        test_settings.JWT_VALIDATE_ISSUER = True
        test_settings.JWT_EXPECTED_ISSUER = "https://auth.example.com"
        
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
            "iss": "https://auth.example.com",
        }
        token = jwt.encode(payload, test_settings.WEBSOCKET_AUTH_SECRET, algorithm="HS256")
        
        result = await security.validate_jwt_token(token)
        
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_validate_jwt_token_wrong_issuer(self, security, test_settings):
        """Test JWT token validation fails with wrong issuer."""
        import jwt
        import time
        
        test_settings.JWT_VALIDATE_ISSUER = True
        test_settings.JWT_EXPECTED_ISSUER = "https://auth.example.com"
        
        payload = {
            "restaurant_id": "rest_1",
            "session_id": "sess_123",
            "exp": int(time.time()) + 3600,
            "iss": "https://wrong-issuer.com",
        }
        token = jwt.encode(payload, test_settings.WEBSOCKET_AUTH_SECRET, algorithm="HS256")
        
        result = await security.validate_jwt_token(token)
        
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_revoke_token(self, security, mock_redis_client):
        """Test token revocation."""
        await security.revoke_token("token-id-123")
        
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert "token:revoked:token-id-123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_revoke_token_disabled(self, test_settings, mock_redis_client):
        """Test token revocation when disabled."""
        test_settings.ENABLE_TOKEN_REVOCATION = False
        security = WebSocketSecurity(mock_redis_client, test_settings)
        
        await security.revoke_token("token-id-123")
        
        # Should not call Redis when disabled
        mock_redis_client.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_is_token_revoked(self, security, mock_redis_client):
        """Test checking if token is revoked."""
        mock_redis_client.exists.return_value = 1  # Token is revoked
        
        result = await security._is_token_revoked("token-id-123")
        
        assert result is True
        mock_redis_client.exists.assert_called_once_with("token:revoked:token-id-123")

    @pytest.mark.asyncio
    async def test_is_token_not_revoked(self, security, mock_redis_client):
        """Test checking if token is not revoked."""
        mock_redis_client.exists.return_value = 0  # Token is not revoked
        
        result = await security._is_token_revoked("token-id-123")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self, security, mock_redis_client):
        """Test revoking all tokens for a user session."""
        count = await security.revoke_all_user_tokens("rest_1", "sess_123")
        
        assert count == 1
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert "token:revoked:session:rest_1:sess_123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_is_session_token_revoked(self, security, mock_redis_client):
        """Test checking if session tokens are revoked."""
        mock_redis_client.exists.return_value = 1
        
        result = await security.is_session_token_revoked("rest_1", "sess_123")
        
        assert result is True

    def test_sanitize_headers_valid(self, security):
        """Test header sanitization with valid headers."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer token123",
        }
        
        sanitized = security.sanitize_headers(headers)
        
        assert sanitized["Content-Type"] == "application/json"
        assert sanitized["Authorization"] == "Bearer token123"

    def test_sanitize_headers_invalid_name(self, security):
        """Test header sanitization removes invalid header names."""
        headers = {
            "Valid-Header": "value",
            "Invalid\r\nHeader": "value",  # Contains control characters
            "": "value",  # Empty name
        }
        
        sanitized = security.sanitize_headers(headers)
        
        assert "Valid-Header" in sanitized
        assert "Invalid\r\nHeader" not in sanitized
        assert "" not in sanitized

    def test_sanitize_headers_too_large(self, security):
        """Test header sanitization removes oversized headers."""
        headers = {
            "Small-Header": "value",
            "Large-Header": "x" * 10000,  # Very large value
        }
        
        sanitized = security.sanitize_headers(headers)
        
        assert "Small-Header" in sanitized
        # Large header should be skipped
        assert "Large-Header" not in sanitized or len(sanitized.get("Large-Header", "")) < 10000

    def test_validate_request_origin_allowed(self, security):
        """Test origin validation allows valid origins."""
        result = security.validate_request_origin("http://localhost:3000")
        
        assert result.valid is True

    def test_validate_request_origin_wildcard(self, security):
        """Test origin validation allows wildcard."""
        security._settings.ALLOWED_CORS_ORIGINS = ["*"]
        result = security.validate_request_origin("http://any-origin.com")
        
        assert result.valid is True

    def test_validate_request_origin_disallowed(self, security):
        """Test origin validation rejects disallowed origins."""
        result = security.validate_request_origin("http://evil.com")
        
        assert result.valid is False
        assert "not allowed" in result.reason.lower()

    def test_validate_request_origin_no_origin(self, security):
        """Test origin validation allows no origin (direct connection)."""
        result = security.validate_request_origin(None)
        
        assert result.valid is True

    def test_validate_websocket_subprotocol(self, security):
        """Test WebSocket subprotocol validation."""
        result = security.validate_websocket_subprotocol(["protocol1", "protocol2"])
        
        assert result == "protocol1"

    def test_validate_websocket_subprotocol_empty(self, security):
        """Test WebSocket subprotocol validation with empty list."""
        result = security.validate_websocket_subprotocol([])
        
        assert result is None

    def test_compute_connection_fingerprint(self, security):
        """Test connection fingerprint computation."""
        mock_websocket = MagicMock()
        mock_websocket.client = MagicMock(host="192.168.1.1", port=12345)
        mock_websocket.headers = {"user-agent": "TestClient/1.0"}
        
        fingerprint = security.compute_connection_fingerprint(mock_websocket)
        
        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 16  # SHA256 truncated to 16 chars

    @pytest.mark.asyncio
    async def test_check_connection_anomaly_normal(self, security, mock_redis_client):
        """Test connection anomaly check passes for normal activity."""
        mock_redis_client.scard.return_value = 1  # Only 1 connection
        
        result = await security.check_connection_anomaly("conn_1", "fingerprint_1")
        
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_check_connection_anomaly_suspicious(self, security, mock_redis_client):
        """Test connection anomaly check detects suspicious activity."""
        mock_redis_client.scard.return_value = 15  # Many connections
        
        result = await security.check_connection_anomaly("conn_1", "fingerprint_1")
        
        assert result.valid is False
        assert "too many" in result.reason.lower()