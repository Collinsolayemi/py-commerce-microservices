"""Shared package for event contracts and messaging helpers across all microservices."""

from common.events import (
    BaseEvent,
    OrderItem,
    OrderCreatedEvent,
    InventoryReservedEvent,
    InventoryFailedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    OrderConfirmedEvent,
    OrderCancelledEvent,
)
from common.config import (
    ECOMMERCE_EXCHANGE,
    RoutingKeys,
    Queues,
)
from common.rabbitmq import RabbitMQClient
from common.security import (
    verify_token,
    get_current_user_id,
    get_optional_user_id,
)

__all__ = [
    "BaseEvent",
    "OrderItem",
    "OrderCreatedEvent",
    "InventoryReservedEvent",
    "InventoryFailedEvent",
    "PaymentSucceededEvent",
    "PaymentFailedEvent",
    "OrderConfirmedEvent",
    "OrderCancelledEvent",
    "ECOMMERCE_EXCHANGE",
    "RoutingKeys",
    "Queues",
    "RabbitMQClient",
    "verify_token",
    "get_current_user_id",
    "get_optional_user_id",
]

