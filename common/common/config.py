"""Configuration constants for RabbitMQ exchange names, routing keys, and queues."""

import os

# RabbitMQ Connection URL
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# Primary Topic Exchange
ECOMMERCE_EXCHANGE = "ecommerce_events"
ECOMMERCE_EXCHANGE_TYPE = "topic"

# Dead Letter Exchange (for failed / exhausted retries)
ECOMMERCE_DLX = "ecommerce_dlx"
ECOMMERCE_DLQ = "ecommerce_dlq"


class RoutingKeys:
    """Standardized event routing keys."""
    # Order events
    ORDER_CREATED = "order.created"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_CANCELLED = "order.cancelled"

    # Inventory events
    INVENTORY_RESERVED = "inventory.reserved"
    INVENTORY_FAILED = "inventory.failed"

    # Payment events
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"


class Queues:
    """Service-specific queue bindings."""
    PRODUCT_SERVICE = "product_service_queue"
    ORDER_SERVICE = "order_service_queue"
    PAYMENT_SERVICE = "payment_service_queue"
    NOTIFICATION_SERVICE = "notification_service_queue"

