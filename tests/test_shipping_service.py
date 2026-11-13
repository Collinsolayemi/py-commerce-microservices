"""Tests for Module 9: Shipping & Fulfillment Service."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
COMMON_ROOT = ROOT / "common"
if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import RoutingKeys
from common.rabbitmq import RabbitMQClient
from services.shipping_service.app.consumer import ShippingConsumer
from services.shipping_service.app.main import app
from services.shipping_service.app.models import ShipmentStatus, shipment_repo


class TestShippingService(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        shipment_repo.clear()

    def tearDown(self) -> None:
        shipment_repo.clear()

    async def test_order_confirmed_event_creates_shipment_idempotently(self) -> None:
        mock_broker = AsyncMock(spec=RabbitMQClient)
        consumer = ShippingConsumer(mock_broker)

        payload = {"order_id": "ord-101", "user_id": "usr-1"}
        await consumer.handle_event(payload, RoutingKeys.ORDER_CONFIRMED)
        await consumer.handle_event(payload, RoutingKeys.ORDER_CONFIRMED)

        shipment = shipment_repo.get_by_order("ord-101")
        self.assertIsNotNone(shipment)
        self.assertEqual(shipment.status, ShipmentStatus.PENDING_DISPATCH)
        self.assertTrue(shipment.tracking_number.startswith("TRK-"))
        self.assertEqual(mock_broker.publish.await_count, 1)

    async def test_order_cancelled_event_cancels_pending_shipment(self) -> None:
        consumer = ShippingConsumer(None)
        await consumer.handle_event(
            {"order_id": "ord-102", "user_id": "usr-2"},
            RoutingKeys.ORDER_CONFIRMED,
        )
        await consumer.handle_event(
            {"order_id": "ord-102", "user_id": "usr-2", "reason": "Payment failed"},
            RoutingKeys.ORDER_CANCELLED,
        )

        shipment = shipment_repo.get_by_order("ord-102")
        self.assertIsNotNone(shipment)
        self.assertEqual(shipment.status, ShipmentStatus.CANCELLED)

    def test_rest_lifecycle_dispatch_and_deliver(self) -> None:
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "healthy")

            created = client.post(
                "/shipments",
                json={"order_id": "ord-201", "user_id": "usr-9", "carrier": "DHL Express"},
            )
            self.assertEqual(created.status_code, 201)
            body = created.json()
            self.assertEqual(body["status"], "PENDING_DISPATCH")
            self.assertEqual(body["carrier"], "DHL Express")

            # Cannot deliver before dispatch
            early_deliver = client.post("/shipments/ord-201/deliver")
            self.assertEqual(early_deliver.status_code, 409)

            dispatched = client.post("/shipments/ord-201/dispatch")
            self.assertEqual(dispatched.status_code, 200)
            self.assertEqual(dispatched.json()["status"], "IN_TRANSIT")

            delivered = client.post("/shipments/ord-201/deliver")
            self.assertEqual(delivered.status_code, 200)
            self.assertEqual(delivered.json()["status"], "DELIVERED")

            # Cannot cancel after delivery
            late_cancel = client.post("/shipments/ord-201/cancel")
            self.assertEqual(late_cancel.status_code, 409)

            fetched = client.get("/shipments/ord-201")
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["status"], "DELIVERED")

            missing = client.get("/shipments/nonexistent-order")
            self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()

