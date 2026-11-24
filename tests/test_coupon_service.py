"""Tests for Module 11: Promotions & Coupons Service."""

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
from services.coupon_service.app.consumer import CouponConsumer
from services.coupon_service.app.main import app
from services.coupon_service.app.models import RedemptionStatus, coupon_repo


def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


class TestCouponService(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        coupon_repo.clear()

    def tearDown(self) -> None:
        coupon_repo.clear()

    def test_create_validate_and_percentage_cap(self) -> None:
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "healthy")

            # Percentage > 100 is rejected
            bad_pct = client.post(
                "/coupons",
                json={
                    "code": "TOO_MUCH",
                    "discount_type": "PERCENTAGE",
                    "discount_value": 150,
                },
            )
            self.assertEqual(bad_pct.status_code, 422)

            # Create 20% off coupon with $50 minimum and $30 max discount cap
            created = client.post(
                "/coupons",
                json={
                    "code": "welcome20",
                    "description": "20% off orders $50+",
                    "discount_type": "PERCENTAGE",
                    "discount_value": 20,
                    "min_order_amount": 50.0,
                    "max_discount_amount": 30.0,
                },
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["code"], "WELCOME20")

            # Duplicate code rejected
            dup = client.post(
                "/coupons",
                json={
                    "code": "WELCOME20",
                    "discount_type": "FIXED_AMOUNT",
                    "discount_value": 10,
                },
            )
            self.assertEqual(dup.status_code, 409)

            # Below min_order_amount -> valid=False
            too_small = client.post(
                "/coupons/validate",
                json={"code": "welcome20", "order_amount": 40.0},
            )
            self.assertEqual(too_small.status_code, 200)
            self.assertFalse(too_small.json()["valid"])

            # $100 order -> 20% = $20 discount, final $80
            q1 = client.post(
                "/coupons/validate",
                json={"code": "welcome20", "order_amount": 100.0},
            ).json()
            self.assertTrue(q1["valid"])
            self.assertEqual(q1["discount_amount"], 20.0)
            self.assertEqual(q1["final_amount"], 80.0)

            # $250 order -> 20% = $50, capped at $30 -> final $220
            q2 = client.post(
                "/coupons/validate",
                json={"code": "welcome20", "order_amount": 250.0},
            ).json()
            self.assertTrue(q2["valid"])
            self.assertEqual(q2["discount_amount"], 30.0)
            self.assertEqual(q2["final_amount"], 220.0)

    def test_authenticated_redemption_idempotency_limits_and_ownership(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}
        bob_headers = {"Authorization": f"Bearer {make_token('bob')}"}

        with TestClient(app) as client:
            client.post(
                "/coupons",
                json={
                    "code": "SAVE15",
                    "discount_type": "FIXED_AMOUNT",
                    "discount_value": 15.0,
                    "max_uses": 1,
                    "per_user_limit": 1,
                },
            )

            # Unauthenticated redeem returns 401
            unauth = client.post(
                "/coupons/SAVE15/redeem",
                json={"order_id": "ord-1", "order_amount": 50.0},
            )
            self.assertEqual(unauth.status_code, 401)

            # Alice redeems SAVE15 on ord-1
            r1 = client.post(
                "/coupons/SAVE15/redeem",
                json={"order_id": "ord-1", "order_amount": 50.0},
                headers=alice_headers,
            )
            self.assertEqual(r1.status_code, 201)
            self.assertEqual(r1.json()["discount_amount"], 15.0)
            self.assertEqual(r1.json()["final_amount"], 35.0)

            # Idempotent retry for same order_id returns 200 without failing max_uses
            r1_retry = client.post(
                "/coupons/SAVE15/redeem",
                json={"order_id": "ord-1", "order_amount": 50.0},
                headers=alice_headers,
            )
            self.assertEqual(r1_retry.status_code, 200)
            self.assertEqual(
                r1_retry.json()["redemption_id"], r1.json()["redemption_id"]
            )
            self.assertEqual(client.get("/coupons/SAVE15").json()["used_count"], 1)

            # Bob cannot redeem SAVE15 because max_uses=1 is exhausted
            bob_redeem = client.post(
                "/coupons/SAVE15/redeem",
                json={"order_id": "ord-2", "order_amount": 50.0},
                headers=bob_headers,
            )
            self.assertEqual(bob_redeem.status_code, 409)

            # Alice can read her redemption; Bob gets 404 (ownership isolation)
            own_fetch = client.get(
                "/coupons/redemptions/ord-1", headers=alice_headers
            )
            self.assertEqual(own_fetch.status_code, 200)

            other_fetch = client.get(
                "/coupons/redemptions/ord-1", headers=bob_headers
            )
            self.assertEqual(other_fetch.status_code, 404)

    def test_expired_and_deactivated_coupons_rejected(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        with TestClient(app) as client:
            client.post(
                "/coupons",
                json={
                    "code": "OLD10",
                    "discount_type": "FIXED_AMOUNT",
                    "discount_value": 10.0,
                    "expires_at": past,
                },
            )
            expired_res = client.post(
                "/coupons/OLD10/redeem",
                json={"order_id": "ord-exp", "order_amount": 40.0},
                headers=alice_headers,
            )
            self.assertEqual(expired_res.status_code, 409)
            self.assertIn("expired", expired_res.json()["detail"].lower())

            client.post(
                "/coupons",
                json={
                    "code": "FLASH5",
                    "discount_type": "FIXED_AMOUNT",
                    "discount_value": 5.0,
                },
            )
            deact = client.post("/coupons/FLASH5/deactivate")
            self.assertEqual(deact.status_code, 200)
            self.assertFalse(deact.json()["active"])

            inactive_res = client.post(
                "/coupons/FLASH5/redeem",
                json={"order_id": "ord-inact", "order_amount": 40.0},
                headers=alice_headers,
            )
            self.assertEqual(inactive_res.status_code, 409)

    async def test_order_cancelled_event_releases_coupon_quota_idempotently(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}
        with TestClient(app) as client:
            client.post(
                "/coupons",
                json={
                    "code": "VIP25",
                    "discount_type": "FIXED_AMOUNT",
                    "discount_value": 25.0,
                    "max_uses": 1,
                    "per_user_limit": 1,
                },
            )
            res = client.post(
                "/coupons/VIP25/redeem",
                json={"order_id": "ord-500", "order_amount": 100.0},
                headers=alice_headers,
            )
            self.assertEqual(res.status_code, 201)
            self.assertEqual(coupon_repo.get("VIP25").used_count, 1)

        mock_broker = AsyncMock(spec=RabbitMQClient)
        consumer = CouponConsumer(mock_broker)

        cancel_payload = {
            "order_id": "ord-500",
            "user_id": "alice",
            "reason": "Payment declined",
        }
        await consumer.handle_event(cancel_payload, RoutingKeys.ORDER_CANCELLED)
        # Re-delivering the same cancellation must be idempotent
        await consumer.handle_event(cancel_payload, RoutingKeys.ORDER_CANCELLED)

        redemption = coupon_repo.get_redemption_by_order("ord-500")
        self.assertIsNotNone(redemption)
        self.assertEqual(redemption.status, RedemptionStatus.RELEASED)
        self.assertEqual(coupon_repo.get("VIP25").used_count, 0)
        self.assertEqual(mock_broker.publish.await_count, 1)

        # Alice can now redeem VIP25 on a new order
        with TestClient(app) as client:
            re_redeem = client.post(
                "/coupons/VIP25/redeem",
                json={"order_id": "ord-501", "order_amount": 100.0},
                headers=alice_headers,
            )
            self.assertEqual(re_redeem.status_code, 201)
            self.assertEqual(coupon_repo.get("VIP25").used_count, 1)


if __name__ == "__main__":
    unittest.main()

