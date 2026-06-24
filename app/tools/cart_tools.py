"""Cart update tool for Gemini integration - refactored with gateway."""

import logging
from typing import Any, Dict, Optional

from app.services.cart_backend_gateway import CartBackendGateway
from app.schemas.cart_schemas import CartAction, CartUpdatePayload, CartAddonSelection

logger = logging.getLogger(__name__)


async def update_cart(
    cart_gateway: CartBackendGateway,
    turn_id: str,
    restaurant_id: str,
    session_id: str,
    action: str,
    dish_id: int,
    quantity: int,
    notes: Optional[str] = None,
    addons: Optional[list[dict]] = None,
) -> dict:
    """Update user's cart via CartBackendGateway.
    
    This tool is now a thin wrapper around the CartBackendGateway,
    which handles idempotency, HTTP communication, validation, and error handling.
    
    Args:
        cart_gateway: Cart backend gateway instance
        turn_id: Turn identifier for correlation and idempotency
        restaurant_id: Restaurant identifier
        session_id: Session identifier
        action: Cart action (add/remove/update)
        dish_id: Dish identifier
        quantity: New quantity
        notes: Optional special instructions
        addons: Optional addon selections
        
    Returns:
        Cart update result with success status and cart snapshot
    """
    try:
        # Validate addons if provided
        normalized_addons = []
        if addons:
            for addon in addons:
                normalized_addons.append(
                    CartAddonSelection.model_validate(addon).model_dump()
                )
        
        logger.info(
            "Updating cart via tool",
            extra={
                "turn_id": turn_id,
                "restaurant_id": restaurant_id,
                "session_id": session_id,
                "action": action,
                "dish_id": dish_id,
                "quantity": quantity,
            }
        )
        
        # Delegate to gateway (handles idempotency, validation, HTTP, etc.)
        result = await cart_gateway.update_cart(
            session_id=session_id,
            turn_id=turn_id,
            restaurant_id=restaurant_id,
            action=action,
            dish_id=dish_id,
            quantity=quantity,
            notes=notes,
            addons=normalized_addons,
        )
        
        # Transform gateway result to tool result format
        return {
            "success": result.get("success", False),
            "message": result.get("message", "Cart updated"),
            "cart": result.get("cart", {}),
            "cart_event": result.get("cart_event", {}),
            "error": result.get("error"),
            "error_code": result.get("error_code"),
            "idempotency_key": result.get("idempotency_key"),
        }
        
    except Exception as exc:
        logger.error("Cart tool execution failed", exc_info=True)
        return {
            "success": False,
            "error": str(exc),
        }


async def validate_offer_code(
    cart_gateway: CartBackendGateway,
    turn_id: str,
    restaurant_id: str,
    session_id: str,
    code: str,
    subtotal: float,
) -> dict:
    """Validate offer/promo code against cart subtotal.
    
    Args:
        cart_gateway: Cart backend gateway instance
        turn_id: Turn identifier for correlation
        restaurant_id: Restaurant identifier
        session_id: Session identifier
        code: Offer code to validate
        subtotal: Cart subtotal before discount
        
    Returns:
        Validation result with discount details
    """
    try:
        logger.info(
            "Validating offer code via tool",
            extra={
                "turn_id": turn_id,
                "restaurant_id": restaurant_id,
                "session_id": session_id,
                "offer_code": code,
                "subtotal": subtotal,
            }
        )
        
        result = await cart_gateway.validate_offer_code(
            restaurant_id=restaurant_id,
            session_id=session_id,
            turn_id=turn_id,
            code=code,
            subtotal=subtotal,
        )
        
        return {
            "valid": result.get("valid", False),
            "discount_type": result.get("discount_type"),
            "discount_value": result.get("discount_value"),
            "discount_amount": result.get("discount_amount"),
            "message": result.get("message", "Offer code validated"),
            "error": result.get("error"),
        }
        
    except Exception as exc:
        logger.error("Offer code validation failed", exc_info=True)
        return {
            "valid": False,
            "error": str(exc),
        }


async def get_session_order(
    cart_gateway: CartBackendGateway,
    restaurant_id: str,
    session_id: str,
) -> dict:
    """Get order linked to session.
    
    Args:
        cart_gateway: Cart backend gateway instance
        restaurant_id: Restaurant identifier
        session_id: Session identifier
        
    Returns:
        Order data or empty dict if not found
    """
    try:
        logger.info(
            "Fetching session order",
            extra={"restaurant_id": restaurant_id, "session_id": session_id}
        )
        
        result = await cart_gateway.get_session_order(
            restaurant_id=restaurant_id,
            session_id=session_id,
        )
        
        return result
        
    except Exception as exc:
        logger.error("Session order fetch failed", exc_info=True)
        return {}