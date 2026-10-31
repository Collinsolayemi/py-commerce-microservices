"""RabbitMQ consumer handling order.created and payment.failed events."""

import json
import logging
from aio_pika.abc import AbstractIncomingMessage

from common.config import RoutingKeys, Queues
from common.events import (
    OrderCreatedEvent,
    InventoryReservedEvent,
    InventoryFailedEvent,
    PaymentFailedEvent,
    OrderItem,
)
from common.rabbitmq import RabbitMQClient
from services.product_service.app.database import ProductRepository

logger = logging.getLogger("product_service.consumer")


class ProductEventConsumer:
    def __init__(self, rabbitmq_client: RabbitMQClient):
        self.client = rabbitmq_client

    async def start(self) -> None:
        """Register consumer queue and routing keys."""
        try:
            await self.client.setup_consumer(
                queue_name=Queues.PRODUCT_SERVICE,
                routing_keys=[
                    RoutingKeys.ORDER_CREATED,
                    RoutingKeys.PAYMENT_FAILED,
                ],
                callback=self.handle_message,
            )
            logger.info("Product Event Consumer started listening.")
        except Exception as exc:
            logger.warning(f"Could not start RabbitMQ consumer: {exc}")

    async def handle_message(self, message: AbstractIncomingMessage) -> None:
        """Process incoming messages based on routing key."""
        async with message.process():
            routing_key = message.routing_key
            body = json.loads(message.body.decode("utf-8"))
            logger.info(f"Received event with routing key: '{routing_key}'")

            if routing_key == RoutingKeys.ORDER_CREATED:
                await self._handle_order_created(body)
            elif routing_key == RoutingKeys.PAYMENT_FAILED:
                await self._handle_payment_failed(body)

    async def _handle_order_created(self, data: dict) -> None:
        """Attempt to reserve inventory for all items in the order."""
        event = OrderCreatedEvent(**data)
        logger.info(f"Processing inventory reservation for Order: {event.order_id}")

        reserved_items = []
        reservation_failed = False
        failure_reason = ""

        # Step 1: Check and reserve each item
        for item in event.items:
            success = await ProductRepository.reserve_stock(item.product_id, item.quantity)
            if success:
                reserved_items.append(item)
            else:
                reservation_failed = True
                failure_reason = f"Insufficient stock for product '{item.product_id}'"
                break

        # Step 2: If any item failed, rollback already reserved items
        if reservation_failed:
            logger.warning(f"Order {event.order_id} failed reservation: {failure_reason}")
            for item in reserved_items:
                await ProductRepository.release_reserved_stock(item.product_id, item.quantity)

            # Publish InventoryFailedEvent
            fail_event = InventoryFailedEvent(
                order_id=event.order_id,
                reason=failure_reason,
            )
            await self.client.publish(RoutingKeys.INVENTORY_FAILED, fail_event)
        else:
            # Publish InventoryReservedEvent
            logger.info(f"Stock reserved successfully for Order {event.order_id}")
            reserved_event = InventoryReservedEvent(
                order_id=event.order_id,
                items=event.items,
            )
            await self.client.publish(RoutingKeys.INVENTORY_RESERVED, reserved_event)

    async def _handle_payment_failed(self, data: dict) -> None:
        """Compensating action: Payment failed, so release reserved stock."""
        event = PaymentFailedEvent(**data)
        logger.info(f"Releasing stock for cancelled Order {event.order_id} due to payment failure.")
        # In a complete implementation, fetch items from order or store them locally to release

