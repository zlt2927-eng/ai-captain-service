"""Cart backend gateway with idempotency support and validation."""

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

from app.infrastructure.http_client import HTTPClient, HTTPClientError
from app.core.config import Settings

logger = logging.getLogger(__name__)


class CartBackendGateway:
    """Gateway for cart operations with idempotency and validation.
    
    Provides:
    - Idempotent cart mutations
    - Cross-tenant dish/addon validation
    - Offer code validation
    - Structured error handling
    - Correlation with session/turn context
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
        """Update cart with idempotency and validation.
        
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
        
        # Validate addons if provided
        validated_addons = addons or []
        if validated_addons:
            validation_result = await self._validate_addons(
                restaurant_id, dish_id, validated_addons
            )
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": validation_result["error"],
                    "error_code": "INVALID_ADDON",
                    "invalid_addons": validation_result.get("invalid_addons", []),
                    "idempotency_key": idempotency_key,
                }
        
        # Build payload
        payload = {
            "restaurant_id": restaurant_id,
            "session_id": session_id,
            "action": action,
            "dish_id": dish_id,
            "quantity": quantity,
            "notes": notes,
            "addons": validated_addons,
            "source": "ai_captain",
            "turn_id": turn_id,
            "idempotency_key": idempotency_key,
            "price_type": "external",  # Always use external_price
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
            
            # Handle validation errors from Laravel
            if result.get("error_code") in ("DISH_NOT_AVAILABLE", "DISH_NOT_FOUND", "CROSS_TENANT_VIOLATION"):
                logger.warning(
                    "Dish validation failed",
                    extra={**log_ctx, "error": result.get("error")}
                )
                return {
                    "success": False,
                    "error": result.get("message", "Dish validation failed"),
                    "error_code": result.get("error_code"),
                    "idempotency_key": idempotency_key,
                }
            
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
            # Check if it's a validation error (422)
            if "422" in str(exc) or "validation" in str(exc).lower():
                logger.error("Cart validation error", extra=log_ctx)
                return {
                    "success": False,
                    "error": "Validation failed. Please check your order.",
                    "error_code": "VALIDATION_ERROR",
                    "idempotency_key": idempotency_key,
                }
            
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
    
    async def _validate_addons(
        self,
        restaurant_id: str,
        dish_id: int,
        addons: list[dict],
    ) -> Dict[str, Any]:
        """Validate that addons belong to the dish and restaurant.
        
        Args:
            restaurant_id: Restaurant identifier
            dish_id: Dish identifier
            addons: List of addon selections
            
        Returns:
            Validation result with valid flag and error details
        """
        # In production, this would call Laravel validation endpoint
        # For now, we'll do basic structural validation
        
        invalid_addons = []
        for addon in addons:
            addon_id = addon.get("addon_id")
            if not addon_id:
                invalid_addons.append({
                    "addon": addon,
                    "reason": "Missing addon_id"
                })
        
        if invalid_addons:
            return {
                "valid": False,
                "error": "Some addons are invalid",
                "invalid_addons": invalid_addons,
            }
        
        # Note: Full validation requires Laravel endpoint:
        # POST /api/v1/cart/validate-addons
        # {
        #   "restaurant_id": "...",
        #   "dish_id": 101,
        #   "addons": [{"addon_id": 501, "quantity": 1}]
        # }
        
        return {"valid": True}
    
    async def validate_offer_code(
        self,
        restaurant_id: str,
        session_id: str,
        turn_id: str,
        code: str,
        subtotal: float,
    ) -> dict:
        """Validate offer code against subtotal.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            turn_id: Turn identifier
            code: Offer code to validate
            subtotal: Cart subtotal before discount
            
        Returns:
            Validation result with discount details
        """
        log_ctx = {
            "restaurant_id": restaurant_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "offer_code": code,
            "subtotal": subtotal,
        }
        
        logger.info("Validating offer code", extra=log_ctx)
        
        try:
            # Call Laravel offer code validation endpoint
            url = f"{self._settings.LARAVEL_BACKEND_URL}/api/v1/cart/validate-offer"
            
            payload = {
                "restaurant_id": restaurant_id,
                "code": code,
                "subtotal": subtotal,
            }
            
            headers = {
                "X-Session-Id": session_id,
                "X-Turn-Id": turn_id,
            }
            
            result = await self._http_client.post_json(
                url,
                payload,
                headers=headers,
                service_name="laravel_backend",
                endpoint_name="validate_offer_code",
                correlation_id=turn_id,
            )
            
            logger.info(
                "Offer code validation completed",
                extra={**log_ctx, "valid": result.get("valid", False)}
            )
            
            return result
            
        except HTTPClientError as exc:
            logger.error("Offer code validation failed", exc_info=True, extra=log_ctx)
            return {
                "valid": False,
                "error": str(exc),
            }
        except Exception as exc:
            logger.error("Offer code validation error", exc_info=True, extra=log_ctx)
            return {
                "valid": False,
                "error": str(exc),
            }
    
    async def get_session_order(
        self,
        restaurant_id: str,
        session_id: str,
    ) -> dict:
        """Get order linked to session.
        
        Args:
            restaurant_id: Restaurant identifier
            session_id: Session identifier
            
        Returns:
            Order data or empty dict if not found
        """
        try:
            url = f"{self._settings.LARAVEL_BACKEND_URL}/api/v1/sessions/{session_id}/order"
            
            result = await self._http_client.get_json(
                url,
                service_name="laravel_backend",
                endpoint_name="get_session_order",
            )
            
            return result
            
        except HTTPClientError as exc:
            logger.error(
                "Failed to fetch session order",
                exc_info=True,
                extra={"restaurant_id": restaurant_id, "session_id": session_id}
            )
            return {}
        except Exception as exc:
            logger.error(
                "Session order fetch error",
                exc_info=True,
                extra={"restaurant_id": restaurant_id, "session_id": session_id}
            )
            return {}