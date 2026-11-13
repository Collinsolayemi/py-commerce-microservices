"""RabbitMQ event consumer for Shipping & Fulfillment Service."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from common.config import ECOMMERCE_EXCHANGE, Queues, RoutingKeys
from common.events import (
    OrderCancelledEvent,
    OrderConfirmedEvent,
    ShipmentCreatedEvent,
)
from common.rabbitmq import RabbitMQClient
from services.shipping_service.app.models import ShipmentStatus, shipment_repo

logger = logging.getLogger("shipping_service.consumer")


class ShippingConsumer:
    """Consumes order lifecycle events to provision or cancel shipments."""

    def __init__(self, rabbitmq_client: Optional[RabbitMQClient] = None) -> None:
        self.rabbitmq = rabbitmq_client

    async def start(self) -> None:
        if self.rabbitmq is None:
            return
        await self.rabbitmq.consume(
            queue_name=Queues.SHIPPING_SERVICE,
            routing_keys=[
                RoutingKeys.ORDER_CONFIRMED,
                RoutingKeys.ORDER_CANCELLED,
            ],
            callback=self.handle_event,
        )

    async def handle_event(self, payload: Dict[str, Any], routing_key: str) -> None:
        if routing_key == RoutingKeys.ORDER_CONFIRMED:
            event = OrderConfirmedEvent(**payload)
            shipment, created = shipment_repo.create_or_get(
                order_id=event.order_id,
                user_id=event.user_id,
            )
            if created and self.rabbitmq is not None:
                await self.rabbitmq.publish(
                    exchange_name=ECOMMERCE_EXCHANGE,
                    routing_key=RoutingKeys.SHIPMENT_CREATED,
                    message=ShipmentCreatedEvent(
                        shipment_id=shipment.shipment_id,
                        order_id=shipment.order_id,
                        user_id=shipment.user_id,
                        tracking_number=shipment.tracking_number,
                        carrier=shipment.carrier,
                    ),
                )
            logger.info(
                "Order %s confirmed -> shipment %s (%s)",
                event.order_id,
                shipment.tracking_number,
                "created" if created else "existing",
            )
        elif routing_key == RoutingKeys.ORDER_CANCELLED:
            event = OrderCancelledEvent(**payload)
            existing = shipment_repo.get_by_order(event.order_id)
            if existing and existing.status == ShipmentStatus.PENDING_DISPATCH:
                shipment_repo.cancel(event.order_id)
                logger.info(
                    "Order %s cancelled -> shipment %s marked CANCELLED",
                    event.order_id,
                    existing.tracking_number,
                )
