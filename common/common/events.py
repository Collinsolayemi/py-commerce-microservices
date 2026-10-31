"""Event payload definitions (data contracts) shared across all microservices."""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """Base event metadata model attached to all emitted domain events."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class OrderItem(BaseModel):
    """Single item line in an order."""
    product_id: str
    quantity: int = Field(gt=0, description="Quantity must be at least 1")
    unit_price: float = Field(ge=0.0, description="Unit price per item")


class OrderCreatedEvent(BaseEvent):
    """Emitted by Order Service when a customer initiates an order."""
    order_id: str
    user_id: str
    items: List[OrderItem]
    total_amount: float


class InventoryReservedEvent(BaseEvent):
    """Emitted by Product/Inventory Service when stock has been successfully locked."""
    order_id: str
    items: List[OrderItem]


class InventoryFailedEvent(BaseEvent):
    """Emitted by Product/Inventory Service when requested items are out of stock."""
    order_id: str
    reason: str


class PaymentSucceededEvent(BaseEvent):
    """Emitted by Payment Service when payment authorization succeeded."""
    payment_id: str
    order_id: str
    user_id: str
    amount: float


class PaymentFailedEvent(BaseEvent):
    """Emitted by Payment Service when card is declined or payment gateway fails."""
    order_id: str
    user_id: str
    amount: float
    reason: str


class OrderConfirmedEvent(BaseEvent):
    """Emitted by Order Service when Saga completes successfully."""
    order_id: str
    user_id: str


class OrderCancelledEvent(BaseEvent):
    """Emitted by Order Service when Saga aborts due to inventory/payment failure."""
    order_id: str
    user_id: str
    reason: str

