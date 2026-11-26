"""REST endpoints for Persistent Cart & Wishlist Service."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status

from common.config import RoutingKeys
from common.events import BaseEvent, CartUpdatedEvent, WishlistUpdatedEvent
from common.rabbitmq import RabbitMQClient
from common.security import get_current_user_id
from services.cart_service.app.models import (
    AddCartItemRequest,
    AddWishlistRequest,
    CartSummary,
    UpdateCartItemRequest,
    WishlistItem,
    cart_repo,
)

router = APIRouter(tags=["Cart & Wishlist"])


async def _publish_if_connected(request: Request, routing_key: str, event: BaseEvent) -> None:
    client: Optional[RabbitMQClient] = getattr(request.app.state, "rabbitmq_client", None)
    if client is not None and client.exchange is not None:
        await client.publish(routing_key=routing_key, event=event)


@router.get("/cart", response_model=CartSummary)
async def get_cart(user_id: str = Depends(get_current_user_id)):
    return cart_repo.get_cart(user_id)


@router.post("/cart/items", response_model=CartSummary, status_code=status.HTTP_201_CREATED)
async def add_cart_item(
    payload: AddCartItemRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    summary = cart_repo.add_item(user_id, payload)
    await _publish_if_connected(
        request,
        RoutingKeys.CART_UPDATED,
        CartUpdatedEvent(
            user_id=user_id,
            item_count=summary.item_count,
            total_amount=summary.total_amount,
        ),
    )
    return summary


@router.patch("/cart/items/{product_id}", response_model=CartSummary)
async def update_cart_item(
    product_id: str,
    payload: UpdateCartItemRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    try:
        summary = cart_repo.update_item_quantity(user_id, product_id, payload.quantity)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    await _publish_if_connected(
        request,
        RoutingKeys.CART_UPDATED,
        CartUpdatedEvent(
            user_id=user_id,
            item_count=summary.item_count,
            total_amount=summary.total_amount,
        ),
    )
    return summary


@router.delete("/cart/items/{product_id}", response_model=CartSummary)
async def remove_cart_item(
    product_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    try:
        summary = cart_repo.remove_item(user_id, product_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cart item not found",
        )

    await _publish_if_connected(
        request,
        RoutingKeys.CART_UPDATED,
        CartUpdatedEvent(
            user_id=user_id,
            item_count=summary.item_count,
            total_amount=summary.total_amount,
        ),
    )
    return summary


@router.delete("/cart", response_model=CartSummary)
async def clear_cart(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    summary = cart_repo.clear_cart(user_id)
    await _publish_if_connected(
        request,
        RoutingKeys.CART_UPDATED,
        CartUpdatedEvent(
            user_id=user_id,
            item_count=summary.item_count,
            total_amount=summary.total_amount,
        ),
    )
    return summary


@router.get("/wishlist", response_model=List[WishlistItem])
async def list_wishlist(user_id: str = Depends(get_current_user_id)):
    return cart_repo.list_wishlist(user_id)


@router.post(
    "/wishlist/{product_id}",
    response_model=WishlistItem,
    status_code=status.HTTP_201_CREATED,
)
async def add_wishlist_item(
    product_id: str,
    request: Request,
    payload: Optional[AddWishlistRequest] = Body(default=None),
    user_id: str = Depends(get_current_user_id),
):
    item = cart_repo.add_wishlist(user_id, product_id, payload)
    await _publish_if_connected(
        request,
        RoutingKeys.WISHLIST_UPDATED,
        WishlistUpdatedEvent(
            user_id=user_id,
            product_id=product_id,
            action="added",
        ),
    )
    return item


@router.delete("/wishlist/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_wishlist_item(
    product_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    try:
        cart_repo.remove_wishlist(user_id, product_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wishlist item not found",
        )

    await _publish_if_connected(
        request,
        RoutingKeys.WISHLIST_UPDATED,
        WishlistUpdatedEvent(
            user_id=user_id,
            product_id=product_id,
            action="removed",
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
