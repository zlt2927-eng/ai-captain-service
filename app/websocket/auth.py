"""WebSocket authentication and authorization."""

import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import WebSocket

from app.core.config import Settings
from app.core.constants import WS_CLOSE_UNAUTHORIZED

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    """Result of WebSocket authentication."""
    
    success: bool
    restaurant_id: Optional[str] = None
    session_id: Optional[str] = None
    error_reason: Optional[str] = None
    close_code: int = WS_CLOSE_UNAUTHORIZED


class WebSocketAuth:
    """Handle WebSocket JWT authentication."""
    
    def __init__(self, settings: Settings):
        self._settings = settings
    
    async def authenticate(self, websocket: WebSocket, token: str, 
                          expected_restaurant_id: str, expected_session_id: str) -> AuthResult:
        """Authenticate WebSocket connection using JWT token.
        
        Args:
            websocket: WebSocket connection
            token: JWT token from query parameter
            expected_restaurant_id: Expected restaurant ID from URL
            expected_session_id: Expected session ID from URL
            
        Returns:
            AuthResult with authentication outcome
        """
        try:
            payload = jwt.decode(
                token,
                self._settings.WEBSOCKET_AUTH_SECRET,
                algorithms=[self._settings.WEBSOCKET_AUTH_ALGORITHM],
            )
            
            token_restaurant_id = payload.get("restaurant_id")
            token_session_id = payload.get("session_id")
            
            if token_restaurant_id != expected_restaurant_id:
                logger.warning(
                    "Token restaurant_id mismatch",
                    extra={
                        "expected": expected_restaurant_id,
                        "actual": token_restaurant_id,
                    }
                )
                return AuthResult(
                    success=False,
                    error_reason="Invalid token payload: restaurant_id mismatch",
                )
            
            if token_session_id != expected_session_id:
                logger.warning(
                    "Token session_id mismatch",
                    extra={
                        "expected": expected_session_id,
                        "actual": token_session_id,
                    }
                )
                return AuthResult(
                    success=False,
                    error_reason="Invalid token payload: session_id mismatch",
                )
            
            return AuthResult(
                success=True,
                restaurant_id=expected_restaurant_id,
                session_id=expected_session_id,
            )
            
        except jwt.ExpiredSignatureError:
            logger.warning("WebSocket token expired")
            return AuthResult(
                success=False,
                error_reason="Token expired",
            )
        except jwt.InvalidTokenError as exc:
            logger.warning("WebSocket token invalid", exc_info=exc)
            return AuthResult(
                success=False,
                error_reason="Invalid token",
            )
        except Exception as exc:
            logger.error("WebSocket authentication error", exc_info=exc)
            return AuthResult(
                success=False,
                error_reason="Authentication error",
            )
    
    async def close_unauthorized(self, websocket: WebSocket, auth_result: AuthResult) -> None:
        """Close WebSocket connection with unauthorized status."""
        await websocket.close(
            code=auth_result.close_code,
            reason=auth_result.error_reason or "Unauthorized"
        )