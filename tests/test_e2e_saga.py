"""End-to-End Distributed Transaction (Saga Choreography) Verification Suite.

Tests the full event-driven lifecycle across:
- User Service
- Product & Inventory Service
- Order Service
- Payment Service
- Notification Service
"""

from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
import unittest
from contextlib import asynccontextmanager
from typing import Dict, List, Callable, Awaitable

# Ensure workspace root and common/ package are on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(BASE_DIR / "common") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "common"))

# Set SQLite test database paths before importing service modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["MONGODB_URL"] = "mongodb://localhost:27017"

from common.config import RoutingKeys, Queues
from common.events import (
    BaseEvent,
    OrderCreatedEvent,
    OrderItem,
    InventoryReservedEvent,
    InventoryFailedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    OrderConfirmedEvent,
    OrderCancelledEvent,
)

# Product Service
from services.product_service.app.database import ProductRepository, init_db as init_product_db
from services.product_service.app.consumer import ProductEventConsumer

# Order Service
from services.order_service.app.database import (
    OrderRepository,
    init_db as init_order_db,
    close_db as close_order_db,
)
from services.order_service.app.models.order import OrderStatus
from services.order_service.app.consumer import OrderEventConsumer

# Payment Service
from services.payment_service.app.database import (
    PaymentRepository,
    init_db as init_payment_db,
    close_db as close_payment_db,
)
from services.payment_service.app.models.payment import PaymentStatus, IdempotencyStatus
from services.payment_service.app.consumer import PaymentEventConsumer

# Notification Service
from services.notification_service.app.consumer import (
    NotificationConsumer,
    NotificationStore,
)


class MockIncomingMessage:
    """Simulates an aio-pika AbstractIncomingMessage for testing."""

    def __init__(self, routing_key: str, body: bytes):
        self.routing_key = routing_key
        self.body = body

    @asynccontextmanager
    async def process(self):
        yield self


class MockMessageBroker:
    """In-memory event bus simulating RabbitMQ Topic Exchange."""

    def __init__(self):
        self.consumers: List[Dict] = []
        self.published_events: List[Dict] = []

    async def setup_consumer(
        self,
        queue_name: str,
        routing_keys: List[str],
        callback: Callable[[MockIncomingMessage], Awaitable[None]],
    ) -> None:
        self.consumers.append({
            "queue_name": queue_name,
            "routing_keys": routing_keys,
            "callback": callback,
        })

    async def publish(self, routing_key: str, event: BaseEvent) -> None:
        payload_bytes = event.model_dump_json().encode("utf-8") if hasattr(event, "model_dump_json") else event.json().encode("utf-8")
        self.published_events.append({
            "routing_key": routing_key,
            "event": event,
            "body": payload_bytes,
        })

        # Deliver to all matching bound queues
        for consumer in self.consumers:
            matched = False
            for pattern in consumer["routing_keys"]:
                if pattern == routing_key or pattern == "#":
                    matched = True
                    break
                # Handle simple wildcard e.g. order.* or payment.*
                if pattern.endswith(".*") and routing_key.startswith(pattern[:-2]):
                    matched = True
                    break

            if matched:
                msg = MockIncomingMessage(routing_key=routing_key, body=payload_bytes)
                # Dispatch asynchronously
                await consumer["callback"](msg)


class TestDistributedSagaE2E(unittest.IsolatedAsyncioTestCase):
    """Module 6 End-to-End Choreography Saga Verification."""

    async def asyncSetUp(self):
        # 1. Initialize databases with fallback layers
        await init_product_db()
        await init_order_db()
        await init_payment_db()

        # 2. Reset notification store
        NotificationStore.clear()

        # 3. Create simulated RabbitMQ broker
        self.broker = MockMessageBroker()

        # 4. Instantiate all service consumers
        self.product_consumer = ProductEventConsumer(self.broker)
        self.order_consumer = OrderEventConsumer(self.broker)
        self.payment_consumer = PaymentEventConsumer(self.broker)
        self.notification_consumer = NotificationConsumer(self.broker)

        # 5. Start listening on message queues
        await self.product_consumer.start()
        await self.order_consumer.start()
        await self.payment_consumer.start()
        await self.notification_consumer.start()

    async def asyncTearDown(self):
        await close_order_db()
        await close_payment_db()

    async def test_case_1_happy_path_saga(self):
        """Test Case 1: Happy Path.
        Order Created -> Stock Reserved -> Payment Succeeded -> Order CONFIRMED.
        """
        user_id = "customer_alice"

        # Step 1: Create a product with initial stock = 10
        product = await ProductRepository.create({
            "name": "Wireless Noise-Canceling Headphones",
            "description": "Premium audio gear",
            "price": 150.00,
            "stock_quantity": 10,
        })
        product_id = product["id"]

        # Step 2: Create an order for 2 units
        order = await OrderRepository.create_order(
            user_id=user_id,
            items_data=[{
                "product_id": product_id,
                "quantity": 2,
                "unit_price": 150.00,
            }],
        )
        self.assertEqual(order.status, OrderStatus.PENDING.value)
        self.assertEqual(order.total_price, 300.00)

        # Step 3: Publish order.created event (initiates Saga)
        order_created_event = OrderCreatedEvent(
            order_id=order.id,
            user_id=user_id,
            items=[OrderItem(product_id=product_id, quantity=2, unit_price=150.00)],
            total_amount=300.00,
        )
        await self.broker.publish(RoutingKeys.ORDER_CREATED, order_created_event)

        # Step 4: Verify stock state
        updated_product = await ProductRepository.get_by_id(product_id)
        self.assertEqual(updated_product["stock_quantity"], 8)
        self.assertEqual(updated_product["reserved_quantity"], 2)

        # Step 5: Verify Order transition to CONFIRMED
        confirmed_order = await OrderRepository.get_order(order.id)
        self.assertEqual(confirmed_order.status, OrderStatus.CONFIRMED.value)

        # Step 6: Verify Payment record
        payment_tx = await PaymentRepository.get_by_order_id(order.id)
        self.assertIsNotNone(payment_tx)
        self.assertEqual(payment_tx.status, PaymentStatus.SUCCESS.value)
        self.assertEqual(payment_tx.amount, 300.00)

        # Step 7: Verify Notifications dispatched
        notifications = NotificationStore.list(order_id=order.id)
        dispatched_types = [n["event_type"] for n in notifications]
        self.assertIn("order.created", dispatched_types)
        self.assertIn("payment.succeeded", dispatched_types)
        self.assertIn("order.confirmed", dispatched_types)

    async def test_case_2_insufficient_stock_path(self):
        """Test Case 2: Insufficient Stock Path.
        Order quantity exceeds stock -> Inventory fails -> Order CANCELLED -> No payment.
        """
        user_id = "customer_bob"

        # Step 1: Create product with only 3 units in stock
        product = await ProductRepository.create({
            "name": "Mechanical Keyboard",
            "price": 100.00,
            "stock_quantity": 3,
        })
        product_id = product["id"]

        # Step 2: Customer orders 10 units (insufficient)
        order = await OrderRepository.create_order(
            user_id=user_id,
            items_data=[{
                "product_id": product_id,
                "quantity": 10,
                "unit_price": 100.00,
            }],
        )

        # Step 3: Publish order.created
        order_created_event = OrderCreatedEvent(
            order_id=order.id,
            user_id=user_id,
            items=[OrderItem(product_id=product_id, quantity=10, unit_price=100.00)],
            total_amount=1000.00,
        )
        await self.broker.publish(RoutingKeys.ORDER_CREATED, order_created_event)

        # Step 4: Verify stock remains untouched (stock=3, reserved=0)
        product_after = await ProductRepository.get_by_id(product_id)
        self.assertEqual(product_after["stock_quantity"], 3)
        self.assertEqual(product_after["reserved_quantity"], 0)

        # Step 5: Verify Order transitioned to CANCELLED
        cancelled_order = await OrderRepository.get_order(order.id)
        self.assertEqual(cancelled_order.status, OrderStatus.CANCELLED.value)

        # Step 6: Verify NO payment transaction was created
        payment_tx = await PaymentRepository.get_by_order_id(order.id)
        self.assertIsNone(payment_tx)

        # Step 7: Verify failure notification
        notifications = NotificationStore.list(order_id=order.id)
        dispatched_types = [n["event_type"] for n in notifications]
        self.assertIn("inventory.failed", dispatched_types)
        self.assertIn("order.cancelled", dispatched_types)

    async def test_case_3_payment_failure_and_rollback_compensating_saga(self):
        """Test Case 3: Compensating Transaction Path.
        Stock Reserved -> Payment Fails -> Order CANCELLED -> Reserved Stock Released.
        """
        user_id = "customer_charlie"

        # Step 1: Product with 5 units
        product = await ProductRepository.create({
            "name": "Ergonomic Mouse",
            "price": 50.00,
            "stock_quantity": 5,
        })
        product_id = product["id"]

        # Step 2: Order for 2 units
        order = await OrderRepository.create_order(
            user_id=user_id,
            items_data=[{
                "product_id": product_id,
                "quantity": 2,
                "unit_price": 50.00,
            }],
        )

        # Step 3: Trigger order.created to reserve stock
        items = [OrderItem(product_id=product_id, quantity=2, unit_price=50.00)]
        order_created_event = OrderCreatedEvent(
            order_id=order.id,
            user_id=user_id,
            items=items,
            total_amount=100.00,
        )
        await self.broker.publish(RoutingKeys.ORDER_CREATED, order_created_event)

        # Verify stock was temporarily reserved
        mid_product = await ProductRepository.get_by_id(product_id)
        self.assertEqual(mid_product["stock_quantity"], 3)
        self.assertEqual(mid_product["reserved_quantity"], 2)

        # Step 4: Simulate payment failure event
        payment_fail_event = PaymentFailedEvent(
            order_id=order.id,
            user_id=user_id,
            amount=100.00,
            reason="Insufficient card funds",
        )
        await self.broker.publish(RoutingKeys.PAYMENT_FAILED, payment_fail_event)

        # Step 5: Verify Order status transitioned to CANCELLED
        order_after = await OrderRepository.get_order(order.id)
        self.assertEqual(order_after.status, OrderStatus.CANCELLED.value)

        # Step 6: Verify compensating action (stock restored back to 5, reserved=0)
        final_product = await ProductRepository.get_by_id(product_id)
        self.assertEqual(final_product["stock_quantity"], 5)
        self.assertEqual(final_product["reserved_quantity"], 0)

        # Step 7: Verify notification logged
        notifications = NotificationStore.list(order_id=order.id)
        dispatched_types = [n["event_type"] for n in notifications]
        self.assertIn("payment.failed", dispatched_types)
        self.assertIn("order.cancelled", dispatched_types)

    async def test_case_4_idempotent_payment_processing(self):
        """Test Case 4: Idempotency guarantee.
        Duplicate inventory.reserved events do not charge customer twice.
        """
        user_id = "customer_david"
        order_id = "order_idempotent_test_123"
        items = [OrderItem(product_id="prod_idemp", quantity=1, unit_price=45.00)]

        event = InventoryReservedEvent(order_id=order_id, items=items)

        # Dispatch event first time
        msg1 = MockIncomingMessage(
            routing_key=RoutingKeys.INVENTORY_RESERVED,
            body=event.model_dump_json().encode("utf-8"),
        )
        await self.payment_consumer.handle_message(msg1)

        # Record count of payment transactions
        tx1 = await PaymentRepository.get_by_order_id(order_id)
        self.assertIsNotNone(tx1)

        # Redeliver duplicate event
        msg2 = MockIncomingMessage(
            routing_key=RoutingKeys.INVENTORY_RESERVED,
            body=event.model_dump_json().encode("utf-8"),
        )
        await self.payment_consumer.handle_message(msg2)

        # Verify only one transaction was created
        all_txs = await PaymentRepository.list_transactions(limit=100)
        matching = [t for t in all_txs if t.order_id == order_id]
        self.assertEqual(len(matching), 1)


if __name__ == "__main__":
    unittest.main()
