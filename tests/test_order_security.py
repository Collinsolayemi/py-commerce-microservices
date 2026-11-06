"""Module 7 HTTP regression tests using real SQLite persistence and signed JWTs."""

import sys
from pathlib import Path
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))

import httpx
import jwt
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from common.security import JWT_SECRET_KEY, JWT_ALGORITHM
from services.order_service.app.models.order import Base, OrderStatus
from services.order_service.app import database
from services.order_service.app.routers.orders import router


class TestOrderSecurity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.factory_patch = patch.object(database, "_session_factory", async_sessionmaker(self.engine, expire_on_commit=False))
        self.factory_patch.start()
        self.broker = AsyncMock()
        self.broker_patch = patch("services.order_service.app.routers.orders.get_rabbitmq_client", return_value=self.broker)
        self.broker_patch.start()
        app = FastAPI()
        app.include_router(router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.order = await database.OrderRepository.create_order("alice", [
            {"product_id": "product-1", "quantity": 2, "unit_price": 12.50},
        ])

    async def asyncTearDown(self):
        await self.client.aclose()
        self.broker_patch.stop()
        self.factory_patch.stop()
        await self.engine.dispose()

    def headers(self, subject="alice", **claims):
        payload = {"sub": subject, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}
        payload.update(claims)
        return {"Authorization": "Bearer " + jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)}

    def payload(self, **extra):
        return {"items": [{"product_id": "product-2", "quantity": 1, "unit_price": 5}], **extra}

    async def test_accepts_token_issued_by_user_service(self):
        from services.user_service.app.core.security import create_access_token
        token = create_access_token({"sub": "alice", "email": "alice@example.com"})
        response = await self.client.get("/orders", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["user_id"], "alice")

    async def test_all_order_routes_require_authentication(self):
        for method, path, kwargs in [
            ("GET", "/orders", {}),
            ("GET", f"/orders/{self.order.id}", {}),
            ("POST", "/orders", {"json": self.payload()}),
            ("POST", f"/orders/{self.order.id}/cancel", {}),
        ]:
            with self.subTest(path=path, method=method):
                response = await self.client.request(method, path, **kwargs)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.broker.publish.assert_not_awaited()

    async def test_rejects_invalid_expired_and_incomplete_tokens(self):
        now = datetime.now(timezone.utc)
        tokens = [
            "not-a-jwt",
            jwt.encode({"sub": "alice", "exp": now + timedelta(minutes=5)}, "wrong-signing-key-for-negative-test-only-12345", algorithm=JWT_ALGORITHM),
            jwt.encode({"sub": "alice", "exp": now - timedelta(seconds=1)}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
            jwt.encode({"sub": "alice"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
            jwt.encode({"user_id": "alice", "exp": now + timedelta(minutes=5)}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
            jwt.encode({"sub": " ", "exp": now + timedelta(minutes=5)}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM),
        ]
        for token in tokens:
            with self.subTest(token=token[:12]):
                response = await self.client.get("/orders", headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers["www-authenticate"], "Bearer")

    async def test_creation_uses_token_subject_and_publishes_that_identity(self):
        response = await self.client.post("/orders", json=self.payload(), headers=self.headers())
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user_id"], "alice")
        event = self.broker.publish.await_args.args[1]
        self.assertEqual(event.user_id, "alice")
        self.assertEqual(str(event.order_id), response.json()["id"])

    async def test_legacy_matching_user_id_is_accepted(self):
        response = await self.client.post("/orders", json=self.payload(user_id="alice"), headers=self.headers())
        self.assertEqual(response.status_code, 201, response.text)

    async def test_cannot_spoof_creation_customer(self):
        response = await self.client.post("/orders", json=self.payload(user_id="bob"), headers=self.headers())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(await database.OrderRepository.list_orders()), 1)
        self.broker.publish.assert_not_awaited()

    async def test_list_is_scoped_to_customer_and_preserves_pagination(self):
        await database.OrderRepository.create_order("bob", [{"product_id": "p", "quantity": 1, "unit_price": 1}])
        response = await self.client.get("/orders", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [self.order.id])
        response = await self.client.get("/orders?skip=1&limit=1", headers=self.headers())
        self.assertEqual(response.json(), [])
        response = await self.client.get("/orders?user_id=alice", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        response = await self.client.get("/orders?user_id=bob", headers=self.headers())
        self.assertEqual(response.status_code, 403)
        response = await self.client.get("/orders?user_id=", headers=self.headers())
        self.assertEqual(response.status_code, 403)

    async def test_owner_can_read_and_cancel(self):
        response = await self.client.get(f"/orders/{self.order.id}", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        response = await self.client.post(f"/orders/{self.order.id}/cancel", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "CANCELLED")
        self.broker.publish.assert_awaited_once()
        # Repeated cancellation remains idempotent.
        response = await self.client.post(f"/orders/{self.order.id}/cancel", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.broker.publish.assert_awaited_once()

    async def test_other_customer_cannot_read_or_cancel(self):
        for path in [self.order.id, "missing-order"]:
            response = await self.client.get(f"/orders/{path}", headers=self.headers("bob"))
            self.assertEqual(response.status_code, 404)
            response = await self.client.post(f"/orders/{path}/cancel", headers=self.headers("bob"))
            self.assertEqual(response.status_code, 404)
        order = await database.OrderRepository.get_order(self.order.id)
        self.assertEqual(order.status, OrderStatus.PENDING.value)
        self.broker.publish.assert_not_awaited()

    async def test_owner_still_cannot_cancel_confirmed_order(self):
        await database.OrderRepository.update_status(self.order.id, OrderStatus.CONFIRMED)
        response = await self.client.post(f"/orders/{self.order.id}/cancel", headers=self.headers())
        self.assertEqual(response.status_code, 400)
        self.broker.publish.assert_not_awaited()

    async def test_invalid_order_payload_is_rejected(self):
        response = await self.client.post("/orders", json={"items": []}, headers=self.headers())
        self.assertEqual(response.status_code, 422)
        self.broker.publish.assert_not_awaited()
