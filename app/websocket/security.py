"""WebSocket security hardening - Phase 14 production hardening."""

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import WebSocket

from app.core.config import Settings
from app.core.constants import WS_CLOSE_UNAUTHORIZED
from app.infrastructure.redis_client import RedisClient

logger = logging.getLogger(__name__)


@dataclass
class SecurityResult:
    """Result of security validation."""
    
    valid: bool
    reason: Optional[str] = None
    close_code: int = WS_CLOSE_UNAUTHORIZED


class WebSocketSecurity:
    """Security hardening for WebSocket connections.
    
    Implements:
    - Enhanced JWT validation (issuer, audience, key ID)
    - Token revocation checking
    - Header sanitization
    - Request validation
    - Secure defaults
    """
    
    def __init__(self, redis_client: RedisClient, settings: Settings):
        self._redis = redis_client
        self._settings = settings
    
    async def validate_jwt_token(self, token: str) -> SecurityResult:
        """Validate JWT token with enhanced security checks.
        
        Args:
            token: JWT token string
            
        Returns:
            SecurityResult indicating if token is valid
        """
        try:
            # Decode header to check algorithm and key ID
            header = jwt.get_unverified_header(token)
            
            # Validate algorithm
            algorithm = header.get("alg", "").upper()
            if algorithm not in [alg.upper() for alg in self._settings.JWT_ALLOWED_ALGORITHMS]:
                logger.warning(
                    "Invalid JWT algorithm",
                    extra={"algorithm": algorithm}
                )
                return SecurityResult(
                    valid=False,
                    reason="Invalid token algorithm",
                    close_code=WS_CLOSE_UNAUTHORIZED
                )
            
            # Validate key ID if required
            if self._settings.JWT_REQUIRE_KEY_ID:
                if "kid" not in header:
                    logger.warning("JWT missing required key ID")
                    return SecurityResult(
                        valid=False,
                        reason="Token missing key ID",
                        close_code=WS_CLOSE_UNAUTHORIZED
                    )
            
            # Build decode options
            decode_options = {
                "verify_alg": True,
                "require": ["exp"],
            }
            
            # Add issuer validation if enabled
            if self._settings.JWT_VALIDATE_ISSUER:
                if not self._settings.JWT_EXPECTED_ISSUER:
                    logger.error("JWT issuer validation enabled but no expected issuer configured")
                    return SecurityResult(
                        valid=False,
                        reason="Server configuration error",
                        close_code=WS_CLOSE_UNAUTHORIZED
                    )
                decode_options["require"].append("iss")
            
            # Add audience validation if enabled
            if self._settings.JWT_VALIDATE_AUDIENCE:
                if not self._settings.JWT_EXPECTED_AUDIENCE:
                    logger.error("JWT audience validation enabled but no expected audience configured")
                    return SecurityResult(
                        valid=False,
                        reason="Server configuration error",
                        close_code=WS_CLOSE_UNAUTHORIZED
                    )
                decode_options["require"].append("aud")
            
            # Decode and validate token
            payload = jwt.decode(
                token,
                self._settings.WEBSOCKET_AUTH_SECRET,
                algorithms=self._settings.JWT_ALLOWED_ALGORITHMS,
                options=decode_options,
                issuer=self._settings.JWT_EXPECTED_ISSUER if self._settings.JWT_VALIDATE_ISSUER else None,
                audience=self._settings.JWT_EXPECTED_AUDIENCE if self._settings.JWT_VALIDATE_AUDIENCE else None,
            )
            
            # Check token revocation if enabled
            if self._settings.ENABLE_TOKEN_REVOCATION:
                jti = payload.get("jti")
                if jti:
                    revoked = await self._is_token_revoked(jti)
                    if revoked:
                        logger.warning(
                            "Revoked token used",
                            extra={"jti": jti}
                        )
                        return SecurityResult(
                            valid=False,
                            reason="Token has been revoked",
                            close_code=WS_CLOSE_UNAUTHORIZED
                        )
            
            return SecurityResult(valid=True)
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return SecurityResult(
                valid=False,
                reason="Token expired",
                close_code=WS_CLOSE_UNAUTHORIZED
            )
        except jwt.InvalidTokenError as exc:
            logger.warning("JWT token invalid", exc_info=exc)
            return SecurityResult(
                valid=False,
                reason="Invalid token",
                close_code=WS_CLOSE_UNAUTHORIZED
            )
        except Exception as exc:
            logger.error("JWT validation error", exc_info=exc)
            return SecurityResult(
                valid=False,
                reason="Token validation error",
                close_code=WS_CLOSE_UNAUTHORIZED
            )
    
    async def _is_token_revoked(self, jti: str) -> bool:
        """Check if token has been revoked.
        
        Args:
            jti: JWT ID claim
            
        Returns:
            True if token is revoked
        """
        key = f"token:revoked:{jti}"
        client = await self._redis._ensure_client()
        return await client.exists(key) == 1
    
    async def revoke_token(self, jti: str, ttl_seconds: Optional[int] = None) -> None:
        """Revoke a JWT token.
        
        Args:
            jti: JWT ID claim
            ttl_seconds: TTL for revocation (defaults to token expiry)
        """
        if not self._settings.ENABLE_TOKEN_REVOCATION:
            return
        
        key = f"token:revoked:{jti}"
        client = await self._redis._ensure_client()
        
        # Use token TTL or default
        ttl = ttl_seconds or self._settings.TOKEN_REVOCATION_CHECK_INTERVAL_SECONDS
        
        await client.setex(key, ttl, "1")
        logger.info("Token revoked", extra={"jti": jti})
    
    async def revoke_all_user_tokens(
        self,
        restaurant_id: str,
        session_id: str
    ) -> int:
        """Revoke all tokens for a user session.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            Number of tokens revoked
        """
        if not self._settings.ENABLE_TOKEN_REVOCATION:
            return 0
        
        # In a production system, you would track active tokens per user
        # For now, we'll use a session-level revocation marker
        key = f"token:revoked:session:{restaurant_id}:{session_id}"
        client = await self._redis._ensure_client()
        
        await client.setex(
            key,
            self._settings.SESSION_TTL_SECONDS,
            str(time.time())
        )
        
        logger.info(
            "All tokens revoked for session",
            extra={"restaurant_id": restaurant_id, "session_id": session_id}
        )
        return 1
    
    async def is_session_token_revoked(
        self,
        restaurant_id: str,
        session_id: str
    ) -> bool:
        """Check if all tokens for a session are revoked.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            True if session tokens are revoked
        """
        key = f"token:revoked:session:{restaurant_id}:{session_id}"
        client = await self._redis._ensure_client()
        return await client.exists(key) == 1
    
    def sanitize_headers(self, headers: dict) -> dict:
        """Sanitize HTTP headers to prevent injection attacks.
        
        Args:
            headers: Raw headers dictionary
            
        Returns:
            Sanitized headers
        """
        sanitized = {}
        
        for key, value in headers.items():
            # Validate header name
            if not self._is_valid_header_name(key):
                logger.warning(
                    "Invalid header name detected",
                    extra={"header_name": key}
                )
                continue
            
            # Validate header size
            if len(key) + len(str(value)) > self._settings.MAX_HEADER_SIZE_BYTES:
                logger.warning(
                    "Header too large",
                    extra={"header_name": key, "size": len(key) + len(str(value))}
                )
                continue
            
            # Sanitize value
            sanitized_value = self._sanitize_header_value(value)
            sanitized[key] = sanitized_value
        
        return sanitized
    
    def _is_valid_header_name(self, name: str) -> bool:
        """Validate HTTP header name.
        
        Args:
            name: Header name
            
        Returns:
            True if header name is valid
        """
        # Header names must be ASCII, no control characters
        if not name or not name.strip():
            return False
        
        # Check for control characters
        try:
            name.encode('ascii')
        except UnicodeEncodeError:
            return False
        
        # Check for invalid characters
        invalid_chars = ['\r', '\n', '\0', '<', '>', '"']
        if any(char in name for char in invalid_chars):
            return False
        
        return True
    
    def _sanitize_header_value(self, value: str) -> str:
        """Sanitize HTTP header value.
        
        Args:
            value: Header value
            
        Returns:
            Sanitized header value
        """
        # Remove control characters
        sanitized = ''.join(char for char in value if ord(char) >= 32 or char in ['\t'])
        
        # Truncate if too long
        max_value_length = self._settings.MAX_HEADER_SIZE_BYTES - 100
        if len(sanitized) > max_value_length:
            sanitized = sanitized[:max_value_length]
        
        return sanitized
    
    def validate_request_origin(self, origin: Optional[str]) -> SecurityResult:
        """Validate request origin against allowed origins.
        
        Args:
            origin: Request Origin header
            
        Returns:
            SecurityResult indicating if origin is valid
        """
        if not self._settings.SECURITY_HEADERS_ENABLED:
            return SecurityResult(valid=True)
        
        if not origin:
            # No origin header - could be direct connection or non-browser client
            # Allow for WebSocket connections
            return SecurityResult(valid=True)
        
        # Check against allowed origins
        allowed_origins = self._settings.ALLOWED_CORS_ORIGINS
        
        # Exact match
        if origin in allowed_origins:
            return SecurityResult(valid=True)
        
        # Wildcard check (if configured)
        for allowed in allowed_origins:
            if allowed == "*":
                return SecurityResult(valid=True)
        
        logger.warning(
            "Invalid request origin",
            extra={"origin": origin, "allowed": allowed_origins}
        )
        
        return SecurityResult(
            valid=False,
            reason="Origin not allowed",
            close_code=WS_CLOSE_UNAUTHORIZED
        )
    
    def validate_websocket_subprotocol(self, subprotocols: list[str]) -> Optional[str]:
        """Validate and select WebSocket subprotocol.
        
        Args:
            subprotocols: List of requested subprotocols
            
        Returns:
            Selected subprotocol or None
        """
        if not subprotocols:
            return None
        
        # In production, define allowed subprotocols
        # For now, accept any but log for monitoring
        logger.debug(
            "WebSocket subprotocol requested",
            extra={"subprotocols": subprotocols}
        )
        
        # Return first subprotocol (or implement selection logic)
        return subprotocols[0] if subprotocols else None
    
    def compute_connection_fingerprint(self, websocket: WebSocket) -> str:
        """Compute a fingerprint for the WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            
        Returns:
            Connection fingerprint hash
        """
        # Collect connection metadata
        client = websocket.client
        headers = dict(websocket.headers)
        
        # Create fingerprint from available data
        fingerprint_data = f"{client.host}:{client.port}:{headers.get('user-agent', '')}"
        
        # Hash the fingerprint
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    
    async def check_connection_anomaly(
        self,
        connection_id: str,
        fingerprint: str
    ) -> SecurityResult:
        """Check for connection anomalies (e.g., multiple connections from same source).
        
        Args:
            connection_id: Connection identifier
            fingerprint: Connection fingerprint
            
        Returns:
            SecurityResult indicating if connection is anomalous
        """
        # Track connections by fingerprint
        key = f"security:connections:{fingerprint}"
        client = await self._redis._ensure_client()
        
        # Add current connection
        await client.sadd(key, connection_id)
        await client.expire(key, 300)  # 5 minutes
        
        # Check connection count
        connection_count = await client.scard(key)
        
        # Threshold for suspicious activity
        max_connections = 10
        
        if connection_count > max_connections:
            logger.warning(
                "Suspicious connection pattern detected",
                extra={
                    "fingerprint": fingerprint,
                    "connection_count": connection_count,
                    "max_allowed": max_connections
                }
            )
            
            return SecurityResult(
                valid=False,
                reason="Too many connections from same source",
                close_code=WS_CLOSE_UNAUTHORIZED
            )
        
        return SecurityResult(valid=True)