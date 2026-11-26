"""Domain models and in-memory repository for Persistent Cart & Wishlist Service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CartItemEntry(BaseModel):
    product_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)
    unit_price: float = Field(..., gt=0.0)
    quantity: int = Field(..., ge=1, le=99)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AddCartItemRequest(BaseModel):
    product_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)
    unit_price: float = Field(..., gt=0.0)
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(..., ge=0, le=99)


class CartSummary(BaseModel):
    user_id: str
    items: List[CartItemEntry]
    item_count: int
    total_amount: float
    updated_at: datetime


class WishlistItem(BaseModel):
    product_id: str = Field(..., min_length=1)
    name: str = Field(default="", max_length=200)
    unit_price: Optional[float] = Field(default=None, gt=0.0)
    saved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AddWishlistRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    unit_price: Optional[float] = Field(default=None, gt=0.0)


class CartRepository:
    """In-memory per-customer cart and wishlist store."""

    def __init__(self) -> None:
        self._carts: Dict[str, Dict[str, CartItemEntry]] = {}
        self._wishlists: Dict[str, Dict[str, WishlistItem]] = {}

    def get_cart(self, user_id: str) -> CartSummary:
        items = list(self._carts.get(user_id, {}).values())
        item_count = sum(i.quantity for i in items)
        total_cents = sum(round(i.unit_price * 100) * i.quantity for i in items)
        return CartSummary(
            user_id=user_id,
            items=items,
            item_count=item_count,
            total_amount=round(total_cents / 100.0, 2),
            updated_at=datetime.now(timezone.utc),
        )

    def add_item(self, user_id: str, payload: AddCartItemRequest) -> CartSummary:
        bag = self._carts.setdefault(user_id, {})
        existing = bag.get(payload.product_id)
        if existing is not None:
            new_qty = min(99, existing.quantity + payload.quantity)
            existing.quantity = new_qty
            existing.name = payload.name.strip()
            existing.unit_price = payload.unit_price
            existing.updated_at = datetime.now(timezone.utc)
        else:
            bag[payload.product_id] = CartItemEntry(
                product_id=payload.product_id,
                name=payload.name.strip(),
                unit_price=payload.unit_price,
                quantity=payload.quantity,
            )
        return self.get_cart(user_id)

    def update_item_quantity(
        self, user_id: str, product_id: str, quantity: int
    ) -> CartSummary:
        bag = self._carts.get(user_id)
        if not bag or product_id not in bag:
            raise KeyError(product_id)
        if quantity == 0:
            del bag[product_id]
        else:
            bag[product_id].quantity = quantity
            bag[product_id].updated_at = datetime.now(timezone.utc)
        return self.get_cart(user_id)

    def remove_item(self, user_id: str, product_id: str) -> CartSummary:
        bag = self._carts.get(user_id)
        if not bag or product_id not in bag:
            raise KeyError(product_id)
        del bag[product_id]
        return self.get_cart(user_id)

    def clear_cart(self, user_id: str) -> CartSummary:
        self._carts.pop(user_id, None)
        return self.get_cart(user_id)

    def list_wishlist(self, user_id: str) -> List[WishlistItem]:
        items = list(self._wishlists.get(user_id, {}).values())
        return sorted(items, key=lambda w: w.saved_at, reverse=True)

    def add_wishlist(
        self, user_id: str, product_id: str, payload: Optional[AddWishlistRequest] = None
    ) -> WishlistItem:
        saved = self._wishlists.setdefault(user_id, {})
        if product_id in saved:
            return saved[product_id]
        item = WishlistItem(
            product_id=product_id,
            name=payload.name.strip() if payload and payload.name else "",
            unit_price=payload.unit_price if payload else None,
        )
        saved[product_id] = item
        return item

    def remove_wishlist(self, user_id: str, product_id: str) -> None:
        saved = self._wishlists.get(user_id)
        if not saved or product_id not in saved:
            raise KeyError(product_id)
        del saved[product_id]

    def clear(self) -> None:
        self._carts.clear()
        self._wishlists.clear()


cart_repo = CartRepository()
