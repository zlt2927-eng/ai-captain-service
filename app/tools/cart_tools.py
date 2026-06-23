"""Cart update tool for Gemini integration."""

import logging
from typing import Any, Dict, Optional

from app.infrastructure.http_client import HTTPClient, HTTPClientError
from app.schemas.cart_schemas import CartAction, CartUpdatePayload, CartAddonSelection
from app.core.config import Settings

logger = logging.getLogger(__name__)


async def update_cart(
    http_client: HTTPClient,
    settings: Settings,
    restaurant_id: str,
    session_id: str,
    action: str,
    dish_id: int,
    quantity: int,
    notes: Optional[str] = None,
    addons: Optional[list[dict]] = None,
) -> dict:
    """Update user's cart via Laravel backend."""
    try:
        normalized_addons = []
        if addons:
            for addon in addons:
                normalized_addons.append(
                    CartAddonSelection.model_validate(addon).model_dump()
                )

        payload = CartUpdatePayload.model_validate(
            {
                "restaurant_id": restaurant_id,
                "session_id": session_id,
                "action": action,
                "dish_id": dish_id,
                "quantity": quantity,
                "notes": notes,
                "addons": normalized_addons,
                "source": "ai_captain",
            }
        )

        cart_url = settings.cart_update_url

        logger.info(
            "Updating cart for %s:%s action=%s dish_id=%s quantity=%s",
            restaurant_id,
            session_id,
            action,
            dish_id,
            quantity,
        )

        result = await http_client.post_json(cart_url, payload.model_dump())

        success = bool(result.get("success", True))
        cart_snapshot = result.get("cart", {}) if isinstance(result.get("cart", {}), dict) else {}
        cart_event = result.get("cart_event") or payload.model_dump()

        return {
            "success": success,
            "message": result.get("message", "Cart updated"),
            "cart": cart_snapshot,
            "cart_event": cart_event,
            "error": None if success else result.get("error", "Cart update failed"),
        }
    except HTTPClientError as exc:
        logger.error("Cart update HTTP failure", exc_info=True)
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        logger.error("Cart update failed", exc_info=True)
        return {"success": False, "error": str(exc)}
