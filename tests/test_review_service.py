"""Tests for Module 10: Product Reviews & Ratings Service."""

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

from common.security import JWT_ALGORITHM, JWT_SECRET_KEY
from services.review_service.app.main import app
from services.review_service.app.models import review_repo


def make_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


class TestReviewService(unittest.TestCase):
    def setUp(self) -> None:
        review_repo.clear()

    def tearDown(self) -> None:
        review_repo.clear()

    def test_requires_authentication_for_mutations(self) -> None:
        with TestClient(app) as client:
            res = client.post(
                "/reviews/prod-1",
                json={"rating": 5, "title": "Great", "comment": "Love it"},
            )
            self.assertEqual(res.status_code, 401)

    def test_create_summarize_update_and_delete_review(self) -> None:
        alice_headers = {"Authorization": f"Bearer {make_token('alice')}"}
        bob_headers = {"Authorization": f"Bearer {make_token('bob')}"}

        with TestClient(app) as client:
            # Alice creates 5-star review
            r1 = client.post(
                "/reviews/prod-1",
                json={"rating": 5, "title": "Superb", "comment": "Very comfortable"},
                headers=alice_headers,
            )
            self.assertEqual(r1.status_code, 201)
            review_id = r1.json()["review_id"]

            # Duplicate review by Alice on same product is rejected
            dup = client.post(
                "/reviews/prod-1",
                json={"rating": 4, "title": "Again", "comment": ""},
                headers=alice_headers,
            )
            self.assertEqual(dup.status_code, 409)

            # Bob creates 3-star review
            r2 = client.post(
                "/reviews/prod-1",
                json={"rating": 3, "title": "Okay", "comment": "Decent"},
                headers=bob_headers,
            )
            self.assertEqual(r2.status_code, 201)

            # Summary reflects both reviews: avg (5+3)/2 = 4.0
            summary = client.get("/reviews/prod-1")
            self.assertEqual(summary.status_code, 200)
            body = summary.json()
            self.assertEqual(body["total_reviews"], 2)
            self.assertEqual(body["average_rating"], 4.0)
            self.assertEqual(body["rating_breakdown"]["5"], 1)
            self.assertEqual(body["rating_breakdown"]["3"], 1)

            # Bob cannot edit or delete Alice's review
            forbidden_patch = client.patch(
                f"/reviews/{review_id}",
                json={"rating": 1},
                headers=bob_headers,
            )
            self.assertEqual(forbidden_patch.status_code, 403)

            forbidden_del = client.delete(f"/reviews/{review_id}", headers=bob_headers)
            self.assertEqual(forbidden_del.status_code, 403)

            # Alice updates her review
            updated = client.patch(
                f"/reviews/{review_id}",
                json={"rating": 4, "title": "Updated"},
                headers=alice_headers,
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["rating"], 4)

            # Alice deletes her review
            deleted = client.delete(f"/reviews/{review_id}", headers=alice_headers)
            self.assertEqual(deleted.status_code, 204)

            summary_after = client.get("/reviews/prod-1").json()
            self.assertEqual(summary_after["total_reviews"], 1)
            self.assertEqual(summary_after["average_rating"], 3.0)


if __name__ == "__main__":
    unittest.main()
