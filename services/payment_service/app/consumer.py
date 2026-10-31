"""RabbitMQ consumer handling inventory.reserved events with idempotency and saga rollback."""

import json
import logging
import random
import uuid
from aio_pika.abc import AbstractIncomingMessage

from common.config import RoutingKeys, Queues
from common.events import (
    InventoryReservedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
)
from common.rabbitmq import RabbitMQClient
from services.payment_service.app.core.config import PAYMENT_SUCCESS_RATE
from services.payment_service.app.database import PaymentRepository
from services.payment_service.app.models.payment import PaymentStatus, IdempotencyStatus

logger = logging.getLogger("payment_service.consumer")


class PaymentEventConsumer:
    """Consumes inventory.reserved events to execute payment authorization."""

    def __init__(self, rabbitmq_client: RabbitMQClient):
        self.client = rabbitmq_client

    async def start(self) -> None:
        """Register queue bindings and start listening for inventory events."""
        try:
            await self.client.setup_consumer(
                queue_name=Queues.PAYMENT_SERVICE,
                routing_keys=[
                    RoutingKeys.INVENTORY_RESERVED,
                ],
                callback=self.handle_message,
            )
            logger.info("Payment Event Consumer initialized and listening.")
        except Exception as exc:
            logger.warning(f"Could not start Payment Event Consumer: {exc}")

    async def handle_message(self, message: AbstractIncomingMessage) -> None:
        """Dispatch incoming messages to specific handlers."""
        async with message.process():
            routing_key = message.routing_key
            body = json.loads(message.body.decode("utf-8"))
            logger.info(f"Received event with routing key: '{routing_key}'")

            if routing_key == RoutingKeys.INVENTORY_RESERVED:
                await self._handle_inventory_reserved(body)

    async def _handle_inventory_reserved(self, data: dict) -> None:
        """Authorize payment idempotently when inventory is locked."""
        event = InventoryReservedEvent(**data)
        order_id = event.order_id
        idempotency_key = f"order_payment_{order_id}"

        logger.info(f"Processing payment authorization for Order: {order_id}")

        # Step 1: Idempotency check
        existing_record = await PaymentRepository.get_idempotency_record(idempotency_key)
        if existing_record and existing_record.status == IdempotencyStatus.COMPLETED.value:
            logger.info(f"Duplicate payment event ignored for Order '{order_id}' (Idempotency key: '{idempotency_key}').")
            return

        if not existing_record:
            try:
                await PaymentRepository.save_idempotency_key(idempotency_key, IdempotencyStatus.PROCESSING)
            except Exception as exc:
                logger.warning(f"Idempotency key conflict or write error: {exc}")

        # Step 2: Compute total amount from reserved items
        total_amount = sum(item.quantity * item.unit_price for item in event.items)
        user_id = data.get("user_id", "customer_default")

        # Step 3: Simulate payment gateway authorization
        is_success = random.random() < PAYMENT_SUCCESS_RATE

        if is_success:
            transaction = await PaymentRepository.create_transaction(
                order_id=order_id,
                user_id=user_id,
                amount=total_amount,
                status=PaymentStatus.SUCCESS,
            )
            await PaymentRepository.update_idempotency_result(
                key=idempotency_key,
                status=IdempotencyStatus.COMPLETED,
                response_payload=json.dumps({"transaction_id": transaction.id, "status": "SUCCESS"}),
            )
            logger.info(f"Payment SUCCESS for Order {order_id} (${total_amount:.2f}). Emitting payment.succeeded.")

            # Publish PaymentSucceededEvent
            try:
                await self.client.publish(
                    routing_key=RoutingKeys.PAYMENT_SUCCEEDED,
                    event=PaymentSucceededEvent(
                        payment_id=transaction.id,
                        order_id=order_id,
                        user_id=user_id,
                        amount=total_amount,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish PaymentSucceededEvent: {exc}")

        else:
            reason = "Payment declined: Simulated card authorization failure"
            transaction = await PaymentRepository.create_transaction(
                order_id=order_id,
                user_id=user_id,
                amount=total_amount,
                status=PaymentStatus.FAILED,
                reason=reason,
            )
            await PaymentRepository.update_idempotency_result(
                key=idempotency_key,
                status=IdempotencyStatus.FAILED,
                response_payload=json.dumps({"transaction_id": transaction.id, "status": "FAILED", "reason": reason}),
            )
            logger.warning(f"Payment FAILED for Order {order_id}. Reason: {reason}. Emitting payment.failed.")

            # Publish PaymentFailedEvent to trigger stock rollback and order cancellation
            try:
                await self.client.publish(
                    routing_key=RoutingKeys.PAYMENT_FAILED,
                    event=PaymentFailedEvent(
                        order_id=order_id,
                        user_id=user_id,
                        amount=total_amount,
                        reason=reason,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish PaymentFailedEvent: {exc}")

