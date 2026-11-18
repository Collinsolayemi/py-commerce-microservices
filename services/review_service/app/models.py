"""Domain models and in-memory repository for Product Reviews & Ratings Service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Review(BaseModel):
    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str
    user_id: str
    rating: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=120)
    comment: str = Field(default="", max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str = Field(..., min_length=1, max_length=120)
    comment: str = Field(default="", max_length=1000)


class UpdateReviewRequest(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ProductReviewSummary(BaseModel):
    product_id: str
    average_rating: float
    total_reviews: int
    rating_breakdown: Dict[int, int]
    reviews: List[Review]


class ReviewRepository:
    """In-memory review store enforcing one review per (user_id, product_id)."""

    def __init__(self) -> None:
        self._reviews: Dict[str, Review] = {}

    def create(
        self,
        product_id: str,
        user_id: str,
        rating: int,
        title: str,
        comment: str = "",
    ) -> Review:
        for existing in self._reviews.values():
            if existing.product_id == product_id and existing.user_id == user_id:
                raise ValueError("You have already reviewed this product")

        review = Review(
            product_id=product_id,
            user_id=user_id,
            rating=rating,
            title=title.strip(),
            comment=comment.strip(),
        )
        self._reviews[review.review_id] = review
        return review

    def get(self, review_id: str) -> Optional[Review]:
        return self._reviews.get(review_id)

    def summarize_product(self, product_id: str) -> ProductReviewSummary:
        items = sorted(
            (r for r in self._reviews.values() if r.product_id == product_id),
            key=lambda r: r.created_at,
            reverse=True,
        )
        breakdown: Dict[int, int] = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        for r in items:
            breakdown[r.rating] = breakdown.get(r.rating, 0) + 1

        total = len(items)
        avg = round(sum(r.rating for r in items) / total, 2) if total > 0 else 0.0
        return ProductReviewSummary(
            product_id=product_id,
            average_rating=avg,
            total_reviews=total,
            rating_breakdown=breakdown,
            reviews=items,
        )

    def update(
        self,
        review_id: str,
        user_id: str,
        rating: Optional[int] = None,
        title: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Review:
        review = self._reviews.get(review_id)
        if review is None:
            raise KeyError(review_id)
        if review.user_id != user_id:
            raise PermissionError("You can only edit your own review")

        if rating is not None:
            review.rating = rating
        if title is not None:
            review.title = title.strip()
        if comment is not None:
            review.comment = comment.strip()
        review.updated_at = datetime.now(timezone.utc)
        return review

    def delete(self, review_id: str, user_id: str) -> None:
        review = self._reviews.get(review_id)
        if review is None:
            raise KeyError(review_id)
        if review.user_id != user_id:
            raise PermissionError("You can only delete your own review")
        del self._reviews[review_id]

    def clear(self) -> None:
        self._reviews.clear()


review_repo = ReviewRepository()

