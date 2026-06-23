"""Cart backend gateway with idempotency support."""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

from app.infrastructure.http_client import HTTPClient, HTTPClientError
from app.core.config import Settings

logger = logging.getLogger(__name__)


class CartBackendGateway:
    """Gateway for cart operations with idempotency.
    
    Provides:
    - Idempotent cart mutations
    - Structured error handling
    - Correlation with session/turn context
    - Retry-safe operations
    """
    
    def __init__(self, http_client: HTTPClient, settings: Settings):
        self._http_client = http_client
        self._settings = settings
    
    def _generate_idempotency_key(
        self,
        session_id: str,
        turn_id: str,
        action: str,
        dish_id: int,
        quantity: int,
    ) -> str:
        """Generate idempotency key for cart mutation.
        
        The key is derived from:
        - session_id: identifies the user session
        - turn_id: identifies the conversation turn
        - action: the cart action (add/remove/update)
        - dish_id: the dish being modified
        - quantity: the new quantity
        
        This ensures that retries of the same turn don't duplicate mutations.
        
        Args:
            session_id: Session identifier
            turn_id: Turn identifier
            action: Cart action (add/remove/update)
            dish_id: Dish identifier
            quantity: New quantity
            
        Returns:
            Idempotency key string
        """
        # Normalize the action identity
        action_identity = f"{action}:{dish_id}:{quantity}"
        
        # Create stable input for hashing
        idempotency_input = f"{session_id}:{turn_id}:{action_identity}"
        
        # Generate SHA256 hash (first 32 chars is sufficient)
        key_hash = hashlib.sha256(idempotency_input.encode()).hexdigest()[:32]
        
        return f"cart_mutation:{key_hash}"
    
    async def update_cart(
        self,
        session_id: str,
        turn_id: str,
        restaurant_id: str,
        action: str,
        dish_id: int,
        quantity: int,
        notes: Optional[str] = None,
        addons: Optional[list[dict]] = None,
    ) -> dict:
        """Update cart with idempotency.
        
        Args:
            session_id: Session identifier
            turn_id: Turn identifier for correlation
            restaurant_id: Restaurant identifier
            action: Cart action (add/remove/update)
            dish_id: Dish identifier
            quantity: New quantity
            notes: Optional special instructions
            addons: Optional addon selections
            
        Returns:
            Cart update result with success status and cart snapshot
        """
        # Generate idempotency key
        idempotency_key = self._generate_idempotency_key(
            session_id, turn_id, action, dish_id, quantity
        )
        
        # Build payload
        payload = {
            "restaurant_id": restaurant_id,
            "session_id": session_id,
            "action": action,
            "dish_id": dish_id,
            "quantity": quantity,
            "notes": notes,
            "addons": addons or [],
            "source": "ai_captain",
            "turn_id": turn_id,
            "idempotency_key": idempotency_key,
        }
        
        log_ctx = {
            "session_id": session_id,
            "turn_id": turn_id,
            "restaurant_id": restaurant_id,
            "action": action,
            "dish_id": dish_id,
            "idempotency_key": idempotency_key,
        }
        
        logger.info("Updating cart via gateway", extra=log_ctx)
        
        try:
            # Send to Laravel backend with idempotency key in header
            headers = {
                "X-Idempotency-Key": idempotency_key,
                "X-Session-Id": session_id,
                "X-Turn-Id": turn_id,
            }
            
            result = await self._http_client.post_json(
                self._settings.cart_update_url,
                payload,
                headers=headers,
                service_name="laravel_backend",
                endpoint_name="update_cart",
                correlation_id=turn_id,
            )
            
            success = bool(result.get("success", True))
            cart_snapshot = result.get("cart", {}) if isinstance(result.get("cart", {}), dict) else {}
            cart_event = result.get("cart_event") or payload
            
            logger.info(
                "Cart update completed",
                extra={**log_ctx, "success": success}
            )
            
            return {
                "success": success,
                "message": result.get("message", "Cart updated"),
                "cart": cart_snapshot,
                "cart_event": cart_event,
                "error": None if success else result.get("error", "Cart update failed"),
                "idempotency_key": idempotency_key,
            }
            
        except HTTPClientError as exc:
            logger.error("Cart update HTTP failure", exc_info=True, extra=log_ctx)
            return {
                "success": False,
                "error": str(exc),
                "idempotency_key": idempotency_key,
            }
        except Exception as exc:
            logger.error("Cart update failed", exc_info=True, extra=log_ctx)
            return {
                "success": False,
                "error": str(exc),
                "idempotency_key": idempotency_key,
            }