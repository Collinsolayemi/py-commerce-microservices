"""Tests for Module 12: Persistent Cart & Wishlist Service."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import jwt
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
COMMON_ROOT = ROOT / "common"
if str(COMMON_ROOT) not in sys.path:
    sys.path.insert(0, str(COMMON_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.config import RoutingKeys
from common.rabbitmq import RabbitMQClient
from common.security import JWT_ALGORITHM, JWT_SECRET_KEY
from services.cart_service.app.consumer import CartConsumer
from services.cart_service.app.main import app
from services.cart_service.app.models import cart_repo


def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


class TestCartService(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        cart_repo.clear()

    def tearDown(self) -> None:
        cart_repo.clear()

    def test_requires_authentication(self) -> None:
        with TestClient(app) as client:
            self.assertEqual(client.get("/cart").status_code, 401)
            self.assertEqual(client.get("/wishlist").status_code, 401)

    def test_cart_crud_totals_and_customer_isolation(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}
        bob_headers = {"Authorization": f"Bearer {make_token('bob')}"}

        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "healthy")

            # Add 2 lamps at $89.00 and 1 tote at $48.00
            r1 = client.post(
                "/cart/items",
                json={
                    "product_id": "prod-lamp",
                    "name": "Milo table lamp",
                    "unit_price": 89.0,
                    "quantity": 2,
                },
                headers=alice_headers,
            )
            self.assertEqual(r1.status_code, 201)
            self.assertEqual(r1.json()["total_amount"], 178.0)

            r2 = client.post(
                "/cart/items",
                json={
                    "product_id": "prod-tote",
                    "name": "The everyday tote",
                    "unit_price": 48.0,
                    "quantity": 1,
                },
                headers=alice_headers,
            )
            self.assertEqual(r2.status_code, 201)
            self.assertEqual(r2.json()["item_count"], 3)
            self.assertEqual(r2.json()["total_amount"], 226.0)

            # Bob's cart is isolated and empty
            bob_cart = client.get("/cart", headers=bob_headers).json()
            self.assertEqual(bob_cart["item_count"], 0)

            # Update lamp quantity to 1 -> $89 + $48 = $137
            patched = client.patch(
                "/cart/items/prod-lamp",
                json={"quantity": 1},
                headers=alice_headers,
            )
            self.assertEqual(patched.status_code, 200)
            self.assertEqual(patched.json()["total_amount"], 137.0)

            # Update quantity to 0 removes item -> $48
            zeroed = client.patch(
                "/cart/items/prod-lamp",
                json={"quantity": 0},
                headers=alice_headers,
            )
            self.assertEqual(zeroed.status_code, 200)
            self.assertEqual(zeroed.json()["item_count"], 1)
            self.assertEqual(zeroed.json()["total_amount"], 48.0)

            # Remove nonexistent item -> 404
            missing = client.delete("/cart/items/nonexistent", headers=alice_headers)
            self.assertEqual(missing.status_code, 404)

            # Clear cart
            cleared = client.delete("/cart", headers=alice_headers)
            self.assertEqual(cleared.status_code, 200)
            self.assertEqual(cleared.json()["item_count"], 0)

    def test_wishlist_add_idempotent_list_and_remove(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}

        with TestClient(app) as client:
            w1 = client.post(
                "/wishlist/prod-chair",
                json={"name": "Sunday lounge chair", "unit_price": 249.0},
                headers=alice_headers,
            )
            self.assertEqual(w1.status_code, 201)

            # Adding again is idempotent
            w2 = client.post("/wishlist/prod-chair", headers=alice_headers)
            self.assertEqual(w2.status_code, 201)

            listed = client.get("/wishlist", headers=alice_headers).json()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["product_id"], "prod-chair")

            deleted = client.delete("/wishlist/prod-chair", headers=alice_headers)
            self.assertEqual(deleted.status_code, 204)
            self.assertEqual(client.get("/wishlist", headers=alice_headers).json(), [])

    async def test_order_created_event_clears_customer_cart(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}
        with TestClient(app) as client:
            client.post(
                "/cart/items",
                json={
                    "product_id": "prod-watch",
                    "name": "Tempo everyday watch",
                    "unit_price": 159.0,
                    "quantity": 1,
                },
                headers=alice_headers,
            )

        mock_broker = AsyncMock(spec=RabbitMQClient)
        consumer = CartConsumer(mock_broker)
        order_payload = {
            "order_id": "ord-900",
            "user_id": "alice",
            "items": [{"product_id": "prod-watch", "quantity": 1, "unit_price": 159.0}],
            "total_amount": 159.0,
        }
        await consumer.handle_event(order_payload, RoutingKeys.ORDER_CREATED)
        # Re-delivery is a no-op
        await consumer.handle_event(order_payload, RoutingKeys.ORDER_CREATED)

        self.assertEqual(cart_repo.get_cart("alice").item_count, 0)
        self.assertEqual(mock_broker.publish.await_count, 1)


if __name__ == "__main__":
    unittest.main()
