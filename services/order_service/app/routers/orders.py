"""Order management HTTP endpoints and Saga triggering."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Query, Depends

from common.security import get_current_user_id
from common.config import RoutingKeys
from common.events import OrderCreatedEvent, OrderCancelledEvent, OrderItem as CommonOrderItem
from services.order_service.app.core.broker import get_rabbitmq_client
from services.order_service.app.database import OrderRepository
from services.order_service.app.models.order import (
    OrderCreate,
    OrderResponse,
    OrderStatus,
)

logger = logging.getLogger("order_service.routers.orders")
router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreate, user_id: str = Depends(get_current_user_id)):
    """
    Create a new order in PENDING status and initiate Saga by publishing order.created.
    """
    if payload.user_id is not None and payload.user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot create orders for another customer.")
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least one item.",
        )

    # 1. Persist order and line items to database
    items_data = [
        {
            "product_id": item.product_id,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        }
        for item in payload.items
    ]

    try:
        order = await OrderRepository.create_order(
            user_id=user_id,
            items_data=items_data,
        )
    except Exception as exc:
        logger.error(f"Failed to persist order: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save order to database.",
        )

    # 2. Publish order.created domain event to start distributed Saga
    broker = get_rabbitmq_client()
    if broker:
        try:
            event_items = [
                CommonOrderItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.price,
                )
                for item in order.items
            ]

            event = OrderCreatedEvent(
                order_id=order.id,
                user_id=order.user_id,
                items=event_items,
                total_amount=order.total_price,
            )
            await broker.publish(RoutingKeys.ORDER_CREATED, event)
            logger.info(f"Published OrderCreatedEvent for order '{order.id}'")
        except Exception as exc:
            logger.warning(f"Failed to publish OrderCreatedEvent to RabbitMQ: {exc}")
    else:
        logger.warning("RabbitMQ client not available. Event publishing skipped (development mode).")

    return order


@router.get("", response_model=List[OrderResponse])
async def list_orders(
    user_id: Optional[str] = Query(None, description="Optional legacy filter; must match the authenticated customer"),
    current_user_id: str = Depends(get_current_user_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """List only the authenticated customer's orders, with pagination."""
    if user_id is not None and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Cannot list another customer's orders.")
    return await OrderRepository.list_orders(user_id=current_user_id, skip=skip, limit=limit)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, user_id: str = Depends(get_current_user_id)):
    """Retrieve details and status for a specific order."""
    order = await OrderRepository.get_order(order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' not found.",
        )
    return order


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: str, reason: str = Query("User cancelled"),
    user_id: str = Depends(get_current_user_id),
):
    """Manually cancel a pending order."""
    order = await OrderRepository.get_order(order_id)
    if not order or order.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' not found.",
        )

    if order.status == OrderStatus.CONFIRMED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an already confirmed order.",
        )

    if order.status == OrderStatus.CANCELLED.value:
        return order

    updated = await OrderRepository.update_status(order_id, OrderStatus.CANCELLED)

    broker = get_rabbitmq_client()
    if broker and updated:
        try:
            await broker.publish(
                RoutingKeys.ORDER_CANCELLED,
                OrderCancelledEvent(
                    order_id=updated.id,
                    user_id=updated.user_id,
                    reason=reason,
                ),
            )
        except Exception as exc:
            logger.warning(f"Could not publish OrderCancelledEvent: {exc}")

    return updated

