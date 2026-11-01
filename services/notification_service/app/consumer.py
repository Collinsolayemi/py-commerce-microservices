"""RabbitMQ event consumer for Notification Service.

Listens to order and payment lifecycle events and dispatches simulated
email, SMS, and push notifications to customers.
"""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from aio_pika.abc import AbstractIncomingMessage

from common.config import RoutingKeys, Queues
from common.rabbitmq import RabbitMQClient

logger = logging.getLogger("notification_service.consumer")


class NotificationStore:
    """In-memory audit log for sent notifications."""
    _notifications: List[Dict[str, Any]] = []

    @classmethod
    def record(
        cls,
        event_type: str,
        channel: str,
        recipient_id: str,
        order_id: Optional[str],
        subject: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "channel": channel,
            "recipient_id": recipient_id,
            "order_id": order_id,
            "subject": subject,
            "message": message,
            "metadata": metadata or {},
        }
        cls._notifications.append(entry)
        return entry

    @classmethod
    def list(cls, order_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if order_id:
            return [n for n in cls._notifications if n.get("order_id") == order_id]
        return list(cls._notifications)

    @classmethod
    def clear(cls) -> None:
        cls._notifications.clear()


class NotificationConsumer:
    """Consumes domain events to dispatch real-time alerts to customers."""

    def __init__(self, rabbitmq_client: RabbitMQClient):
        self.client = rabbitmq_client

    async def start(self) -> None:
        """Register queue bindings and start listening for domain events."""
        try:
            await self.client.setup_consumer(
                queue_name=Queues.NOTIFICATION_SERVICE,
                routing_keys=[
                    RoutingKeys.ORDER_CREATED,
                    RoutingKeys.ORDER_CONFIRMED,
                    RoutingKeys.ORDER_CANCELLED,
                    RoutingKeys.PAYMENT_SUCCEEDED,
                    RoutingKeys.PAYMENT_FAILED,
                    RoutingKeys.INVENTORY_FAILED,
                ],
                callback=self.handle_message,
            )
            logger.info("Notification Event Consumer initialized and listening.")
        except Exception as exc:
            logger.warning(f"Could not start Notification Event Consumer: {exc}")

    async def handle_message(self, message: AbstractIncomingMessage) -> None:
        """Dispatch incoming messages to specific notification handlers."""
        async with message.process():
            routing_key = message.routing_key
            body = json.loads(message.body.decode("utf-8"))
            logger.info(f"Notification Service received event: '{routing_key}'")

            if routing_key == RoutingKeys.ORDER_CREATED:
                await self._handle_order_created(body)
            elif routing_key == RoutingKeys.ORDER_CONFIRMED:
                await self._handle_order_confirmed(body)
            elif routing_key == RoutingKeys.ORDER_CANCELLED:
                await self._handle_order_cancelled(body)
            elif routing_key == RoutingKeys.PAYMENT_SUCCEEDED:
                await self._handle_payment_succeeded(body)
            elif routing_key == RoutingKeys.PAYMENT_FAILED:
                await self._handle_payment_failed(body)
            elif routing_key == RoutingKeys.INVENTORY_FAILED:
                await self._handle_inventory_failed(body)

    async def _handle_order_created(self, data: dict) -> None:
        user_id = data.get("user_id", "unknown")
        order_id = data.get("order_id", "unknown")
        total = data.get("total_amount", 0.0)

        subject = f"Order Received #{order_id[:8]}"
        content = (
            f"Hi User {user_id}, we have received your order #{order_id} "
            f"for ${total:.2f}. We are currently reserving your items."
        )
        entry = NotificationStore.record(
            event_type="order.created",
            channel="EMAIL",
            recipient_id=user_id,
            order_id=order_id,
            subject=subject,
            message=content,
            metadata={"total_amount": total},
        )
        logger.info(f"[EMAIL DISPATCHED] To: {user_id} | Subject: {subject}")

    async def _handle_order_confirmed(self, data: dict) -> None:
        user_id = data.get("user_id", "unknown")
        order_id = data.get("order_id", "unknown")

        subject = f"Order Confirmed #{order_id[:8]}! 🚀"
        content = (
            f"Great news! Your order #{order_id} has been fully confirmed and is "
            f"now being prepared for fulfillment."
        )
        NotificationStore.record(
            event_type="order.confirmed",
            channel="EMAIL",
            recipient_id=user_id,
            order_id=order_id,
            subject=subject,
            message=content,
        )
        logger.info(f"[EMAIL DISPATCHED] To: {user_id} | Subject: {subject}")

    async def _handle_order_cancelled(self, data: dict) -> None:
        user_id = data.get("user_id", "unknown")
        order_id = data.get("order_id", "unknown")
        reason = data.get("reason", "Order processing could not be completed.")

        subject = f"Order Cancellation Notice #{order_id[:8]}"
        content = (
            f"We are sorry to inform you that your order #{order_id} was cancelled. "
            f"Reason: {reason}. Any holds or charges will be released."
        )
        NotificationStore.record(
            event_type="order.cancelled",
            channel="EMAIL",
            recipient_id=user_id,
            order_id=order_id,
            subject=subject,
            message=content,
            metadata={"reason": reason},
        )
        logger.warning(f"[EMAIL DISPATCHED] To: {user_id} | Subject: {subject}")

    async def _handle_payment_succeeded(self, data: dict) -> None:
        user_id = data.get("user_id", "unknown")
        order_id = data.get("order_id", "unknown")
        amount = data.get("amount", 0.0)
        payment_id = data.get("payment_id", "unknown")

        subject = f"Payment Receipt for Order #{order_id[:8]}"
        content = (
            f"Your payment of ${amount:.2f} (TxID: {payment_id}) has been successfully processed."
        )
        NotificationStore.record(
            event_type="payment.succeeded",
            channel="SMS",
            recipient_id=user_id,
            order_id=order_id,
            subject=subject,
            message=content,
            metadata={"payment_id": payment_id, "amount": amount},
        )
        logger.info(f"[SMS DISPATCHED] To: {user_id} | Text: {content}")

    async def _handle_payment_failed(self, data: dict) -> None:
        user_id = data.get("user_id", "unknown")
        order_id = data.get("order_id", "unknown")
        reason = data.get("reason", "Declined by issuing bank.")

        subject = f"Payment Failed for Order #{order_id[:8]}"
        content = (
            f"Your payment for order #{order_id} failed. Reason: {reason}. "
            f"Please update your payment method."
        )
        NotificationStore.record(
            event_type="payment.failed",
            channel="SMS",
            recipient_id=user_id,
            order_id=order_id,
            subject=subject,
            message=content,
            metadata={"reason": reason},
        )
        logger.warning(f"[SMS DISPATCHED] To: {user_id} | Text: {content}")

    async def _handle_inventory_failed(self, data: dict) -> None:
        order_id = data.get("order_id", "unknown")
        reason = data.get("reason", "Item out of stock.")

        subject = f"Inventory Shortage for Order #{order_id[:8]}"
        content = f"We were unable to secure stock for order #{order_id}. Reason: {reason}"
        NotificationStore.record(
            event_type="inventory.failed",
            channel="EMAIL",
            recipient_id="customer",
            order_id=order_id,
            subject=subject,
            message=content,
            metadata={"reason": reason},
        )
        logger.warning(f"[EMAIL DISPATCHED] Order: {order_id} | Subject: {subject}")

