"""REST endpoints for Shipping & Fulfillment Service."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, status

from common.config import ECOMMERCE_EXCHANGE, RoutingKeys
from common.events import (
    ShipmentCreatedEvent,
    ShipmentDeliveredEvent,
    ShipmentDispatchedEvent,
)
from services.shipping_service.app.models import (
    CreateShipmentRequest,
    Shipment,
    ShipmentStatus,
    shipment_repo,
)

router = APIRouter(prefix="/shipments", tags=["Shipments"])


async def _publish_if_connected(request: Request, routing_key: str, event) -> None:
    client = getattr(request.app.state, "rabbitmq_client", None)
    if client is not None and getattr(client, "is_connected", False):
        await client.publish(
            exchange_name=ECOMMERCE_EXCHANGE,
            routing_key=routing_key,
            message=event,
        )


@router.get("", response_model=List[Shipment])
async def list_shipments(
    user_id: Optional[str] = Query(default=None),
    status_filter: Optional[ShipmentStatus] = Query(default=None, alias="status"),
):
    return shipment_repo.list_all(user_id=user_id, status=status_filter)


@router.post("", response_model=Shipment, status_code=status.HTTP_201_CREATED)
async def create_shipment(payload: CreateShipmentRequest, request: Request):
    shipment, created = shipment_repo.create_or_get(
        order_id=payload.order_id,
        user_id=payload.user_id,
        carrier=payload.carrier,
    )
    if created:
        await _publish_if_connected(
            request,
            RoutingKeys.SHIPMENT_CREATED,
            ShipmentCreatedEvent(
                shipment_id=shipment.shipment_id,
                order_id=shipment.order_id,
                user_id=shipment.user_id,
                tracking_number=shipment.tracking_number,
                carrier=shipment.carrier,
            ),
        )
    return shipment


@router.get("/{order_id}", response_model=Shipment)
async def get_shipment(order_id: str):
    shipment = shipment_repo.get_by_order(order_id)
    if shipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment for order '{order_id}' not found",
        )
    return shipment


@router.post("/{order_id}/dispatch", response_model=Shipment)
async def dispatch_shipment(order_id: str, request: Request):
    try:
        shipment = shipment_repo.dispatch(order_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment for order '{order_id}' not found",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await _publish_if_connected(
        request,
        RoutingKeys.SHIPMENT_DISPATCHED,
        ShipmentDispatchedEvent(
            shipment_id=shipment.shipment_id,
            order_id=shipment.order_id,
            user_id=shipment.user_id,
            tracking_number=shipment.tracking_number,
            carrier=shipment.carrier,
        ),
    )
    return shipment


@router.post("/{order_id}/deliver", response_model=Shipment)
async def deliver_shipment(order_id: str, request: Request):
    try:
        shipment = shipment_repo.deliver(order_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment for order '{order_id}' not found",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await _publish_if_connected(
        request,
        RoutingKeys.SHIPMENT_DELIVERED,
        ShipmentDeliveredEvent(
            shipment_id=shipment.shipment_id,
            order_id=shipment.order_id,
            user_id=shipment.user_id,
            tracking_number=shipment.tracking_number,
        ),
    )
    return shipment


@router.post("/{order_id}/cancel", response_model=Shipment)
async def cancel_shipment(order_id: str):
    try:
        return shipment_repo.cancel(order_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shipment for order '{order_id}' not found",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
