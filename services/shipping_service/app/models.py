"""Domain models and in-memory repository for Shipping & Fulfillment Service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from services.shipping_service.app.core.config import DEFAULT_CARRIER


class ShipmentStatus(str, Enum):
    PENDING_DISPATCH = "PENDING_DISPATCH"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class Shipment(BaseModel):
    shipment_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    user_id: str
    tracking_number: str = Field(
        default_factory=lambda: f"TRK-{uuid.uuid4().hex[:10].upper()}"
    )
    carrier: str = DEFAULT_CARRIER
    status: ShipmentStatus = ShipmentStatus.PENDING_DISPATCH
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dispatched_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class CreateShipmentRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    carrier: Optional[str] = None


class ShipmentRepository:
    """In-memory shipment store indexed by order_id for O(1) lookup and idempotency."""

    def __init__(self) -> None:
        self._by_order: Dict[str, Shipment] = {}

    def create_or_get(
        self, order_id: str, user_id: str, carrier: Optional[str] = None
    ) -> tuple[Shipment, bool]:
        existing = self._by_order.get(order_id)
        if existing is not None:
            return existing, False

        shipment = Shipment(
            order_id=order_id,
            user_id=user_id,
            carrier=(carrier.strip() if carrier and carrier.strip() else DEFAULT_CARRIER),
        )
        self._by_order[order_id] = shipment
        return shipment, True

    def get_by_order(self, order_id: str) -> Optional[Shipment]:
        return self._by_order.get(order_id)

    def list_all(
        self, user_id: Optional[str] = None, status: Optional[ShipmentStatus] = None
    ) -> List[Shipment]:
        items = list(self._by_order.values())
        if user_id:
            items = [s for s in items if s.user_id == user_id]
        if status:
            items = [s for s in items if s.status == status]
        return sorted(items, key=lambda s: s.created_at, reverse=True)

    def dispatch(self, order_id: str) -> Shipment:
        shipment = self._by_order.get(order_id)
        if shipment is None:
            raise KeyError(order_id)
        if shipment.status != ShipmentStatus.PENDING_DISPATCH:
            raise ValueError(
                f"Cannot dispatch shipment in status {shipment.status.value}"
            )
        shipment.status = ShipmentStatus.IN_TRANSIT
        shipment.dispatched_at = datetime.now(timezone.utc)
        return shipment

    def deliver(self, order_id: str) -> Shipment:
        shipment = self._by_order.get(order_id)
        if shipment is None:
            raise KeyError(order_id)
        if shipment.status != ShipmentStatus.IN_TRANSIT:
            raise ValueError(
                f"Cannot deliver shipment in status {shipment.status.value}"
            )
        shipment.status = ShipmentStatus.DELIVERED
        shipment.delivered_at = datetime.now(timezone.utc)
        return shipment

    def cancel(self, order_id: str) -> Shipment:
        shipment = self._by_order.get(order_id)
        if shipment is None:
            raise KeyError(order_id)
        if shipment.status != ShipmentStatus.PENDING_DISPATCH:
            raise ValueError(
                f"Cannot cancel shipment in status {shipment.status.value}"
            )
        shipment.status = ShipmentStatus.CANCELLED
        shipment.cancelled_at = datetime.now(timezone.utc)
        return shipment

    def clear(self) -> None:
        self._by_order.clear()


shipment_repo = ShipmentRepository()

