"""Cart-related Pydantic schemas."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CartAction(str, Enum):
    """Cart action type."""

    add = "add"
    remove = "remove"
    update = "update"


class CartAddonSelection(BaseModel):
    """Selection of a dish add-on."""

    addon_id: int = Field(..., gt=0, description="Add-on ID")
    quantity: int = Field(default=1, ge=1, description="Quantity of the add-on")


class CartUpdatePayload(BaseModel):
    """Payload for cart update requests."""

    restaurant_id: str = Field(..., description="Restaurant identifier")
    session_id: str = Field(..., description="Session identifier")
    action: CartAction = Field(..., description="Cart action")
    dish_id: int = Field(..., gt=0, description="Dish ID")
    quantity: int = Field(..., ge=0, description="Quantity of the dish")
    notes: Optional[str] = Field(default=None, description="Special notes/requests")
    addons: list[CartAddonSelection] = Field(
        default_factory=list, description="List of add-on selections"
    )
    source: str = Field(default="ai_captain", description="Source of the cart update")

    @field_validator("restaurant_id", "session_id")
    @classmethod
    def validate_identifiers(cls, v: str) -> str:
        """Ensure identifiers are not blank."""
        if not v or not v.strip():
            raise ValueError("Identifier must not be blank")
        return v.strip()
