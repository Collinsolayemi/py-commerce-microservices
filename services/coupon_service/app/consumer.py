"""RabbitMQ event consumer for Promotions & Coupons Service."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from aio_pika.abc import AbstractIncomingMessage

from common.config import Queues, RoutingKeys
from common.events import CouponReleasedEvent, OrderCancelledEvent
from common.rabbitmq import RabbitMQClient
from services.coupon_service.app.models import coupon_repo

logger = logging.getLogger("coupon_service.consumer")


class CouponConsumer:
    """Consumes order cancellation events to release redeemed promotional quotas."""

    def __init__(self, rabbitmq_client: Optional[RabbitMQClient] = None) -> None:
        self.rabbitmq = rabbitmq_client

    async def start(self) -> None:
        if self.rabbitmq is None:
            return
        await self.rabbitmq.setup_consumer(
            queue_name=Queues.COUPON_SERVICE,
            routing_keys=[RoutingKeys.ORDER_CANCELLED],
            callback=self.handle_message,
        )

    async def handle_message(self, message: AbstractIncomingMessage) -> None:
        async with message.process():
            routing_key = message.routing_key or ""
            payload = json.loads(message.body.decode("utf-8"))
            await self.handle_event(payload, routing_key)

    async def handle_event(self, payload: Dict[str, Any], routing_key: str) -> None:
        if routing_key == RoutingKeys.ORDER_CANCELLED:
            event = OrderCancelledEvent(**payload)
            released = coupon_repo.release_by_order(event.order_id)
            if released is not None:
                if self.rabbitmq is not None:
                    await self.rabbitmq.publish(
                        routing_key=RoutingKeys.COUPON_RELEASED,
                        event=CouponReleasedEvent(
                            redemption_id=released.redemption_id,
                            code=released.code,
                            order_id=released.order_id,
                            user_id=released.user_id,
                            reason=event.reason,
                        ),
                    )
                logger.info(
                    "Order %s cancelled -> released coupon '%s' (redemption %s)",
                    event.order_id,
                    released.code,
                    released.redemption_id,
                )

