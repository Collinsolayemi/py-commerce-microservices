"""RabbitMQ event consumer for Persistent Cart & Wishlist Service."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from aio_pika.abc import AbstractIncomingMessage

from common.config import Queues, RoutingKeys
from common.events import CartUpdatedEvent, OrderCreatedEvent
from common.rabbitmq import RabbitMQClient
from services.cart_service.app.models import cart_repo

logger = logging.getLogger("cart_service.consumer")


class CartConsumer:
    """Clears a customer's persisted cart automatically when an order is created."""

    def __init__(self, rabbitmq_client: Optional[RabbitMQClient] = None) -> None:
        self.rabbitmq = rabbitmq_client

    async def start(self) -> None:
        if self.rabbitmq is None:
            return
        await self.rabbitmq.setup_consumer(
            queue_name=Queues.CART_SERVICE,
            routing_keys=[RoutingKeys.ORDER_CREATED],
            callback=self.handle_message,
        )

    async def handle_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process():
            routing_key = message.routing_key or ""
            payload = json.loads(message.body.decode("utf-8"))
            await self.handle_event(payload, routing_key)

    async def handle_event(self, payload: Dict[str, Any], routing_key: str) -> None:
        if routing_key == RoutingKeys.ORDER_CREATED:
            event = OrderCreatedEvent(**payload)
            existing = cart_repo.get_cart(event.user_id)
            if existing.item_count > 0:
                summary = cart_repo.clear_cart(event.user_id)
                if self.rabbitmq is not None:
                    await self.rabbitmq.publish(
                        routing_key=RoutingKeys.CART_UPDATED,
                        event=CartUpdatedEvent(
                            user_id=event.user_id,
                            item_count=summary.item_count,
                            total_amount=summary.total_amount,
                        ),
                    )
                logger.info(
                    "Order %s created -> cleared persisted cart for user %s",
                    event.order_id,
                    event.user_id,
                )
