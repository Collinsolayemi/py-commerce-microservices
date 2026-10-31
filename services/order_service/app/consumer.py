"""RabbitMQ consumer handling payment and inventory events for Order Service."""

import json
import logging
from aio_pika.abc import AbstractIncomingMessage

from common.config import RoutingKeys, Queues
from common.events import (
    PaymentSucceededEvent,
    PaymentFailedEvent,
    InventoryFailedEvent,
    OrderConfirmedEvent,
    OrderCancelledEvent,
)
from common.rabbitmq import RabbitMQClient
from services.order_service.app.database import OrderRepository
from services.order_service.app.models.order import OrderStatus

logger = logging.getLogger("order_service.consumer")


class OrderEventConsumer:
    """Consumes downstream domain events to update the distributed order saga state."""

    def __init__(self, rabbitmq_client: RabbitMQClient):
        self.client = rabbitmq_client

    async def start(self) -> None:
        """Register queue bindings and start listening."""
        try:
            await self.client.setup_consumer(
                queue_name=Queues.ORDER_SERVICE,
                routing_keys=[
                    RoutingKeys.PAYMENT_SUCCEEDED,
                    RoutingKeys.PAYMENT_FAILED,
                    RoutingKeys.INVENTORY_FAILED,
                ],
                callback=self.handle_message,
            )
            logger.info("Order Event Consumer initialized and listening.")
        except Exception as exc:
            logger.warning(f"Could not start Order Event Consumer: {exc}")

    async def handle_message(self, message: AbstractIncomingMessage) -> None:
        """Dispatch incoming messages to specific handlers."""
        async with message.process():
            routing_key = message.routing_key
            body = json.loads(message.body.decode("utf-8"))
            logger.info(f"Received event with routing key: '{routing_key}'")

            if routing_key == RoutingKeys.PAYMENT_SUCCEEDED:
                await self._handle_payment_succeeded(body)
            elif routing_key == RoutingKeys.PAYMENT_FAILED:
                await self._handle_payment_failed(body)
            elif routing_key == RoutingKeys.INVENTORY_FAILED:
                await self._handle_inventory_failed(body)

    async def _handle_payment_succeeded(self, data: dict) -> None:
        """Mark order as CONFIRMED upon successful payment."""
        event = PaymentSucceededEvent(**data)
        logger.info(f"Payment succeeded for Order: {event.order_id}. Confirming order.")
        
        updated_order = await OrderRepository.update_status(event.order_id, OrderStatus.CONFIRMED)
        if updated_order:
            logger.info(f"Order {event.order_id} status updated to CONFIRMED.")
            # Publish saga completion event
            try:
                await self.client.publish(
                    routing_key=RoutingKeys.ORDER_CONFIRMED,
                    event=OrderConfirmedEvent(
                        order_id=updated_order.id,
                        user_id=updated_order.user_id,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish OrderConfirmedEvent: {exc}")
        else:
            logger.warning(f"Order {event.order_id} not found to confirm.")

    async def _handle_payment_failed(self, data: dict) -> None:
        """Mark order as CANCELLED upon failed payment."""
        event = PaymentFailedEvent(**data)
        logger.info(f"Payment failed for Order: {event.order_id}. Reason: {event.reason}. Cancelling order.")

        updated_order = await OrderRepository.update_status(event.order_id, OrderStatus.CANCELLED)
        if updated_order:
            logger.info(f"Order {event.order_id} status updated to CANCELLED.")
            try:
                await self.client.publish(
                    routing_key=RoutingKeys.ORDER_CANCELLED,
                    event=OrderCancelledEvent(
                        order_id=updated_order.id,
                        user_id=updated_order.user_id,
                        reason=event.reason,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish OrderCancelledEvent: {exc}")

    async def _handle_inventory_failed(self, data: dict) -> None:
        """Mark order as CANCELLED upon inventory shortage."""
        event = InventoryFailedEvent(**data)
        logger.info(f"Inventory reservation failed for Order: {event.order_id}. Reason: {event.reason}. Cancelling order.")

        updated_order = await OrderRepository.update_status(event.order_id, OrderStatus.CANCELLED)
        if updated_order:
            logger.info(f"Order {event.order_id} status updated to CANCELLED.")
            try:
                await self.client.publish(
                    routing_key=RoutingKeys.ORDER_CANCELLED,
                    event=OrderCancelledEvent(
                        order_id=updated_order.id,
                        user_id=updated_order.user_id,
                        reason=event.reason,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish OrderCancelledEvent: {exc}")
