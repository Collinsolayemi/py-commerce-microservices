"""REST endpoints for Product Reviews & Ratings Service."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from common.config import RoutingKeys
from common.events import BaseEvent, ReviewCreatedEvent
from common.rabbitmq import RabbitMQClient
from common.security import get_current_user_id
from services.review_service.app.models import (
    CreateReviewRequest,
    ProductReviewSummary,
    Review,
    UpdateReviewRequest,
    review_repo,
)

router = APIRouter(prefix="/reviews", tags=["Reviews"])


async def _publish_if_connected(request: Request, routing_key: str, event: BaseEvent) -> None:
    client: Optional[RabbitMQClient] = getattr(request.app.state, "rabbitmq_client", None)
    if client is not None and client.exchange is not None:
        await client.publish(routing_key=routing_key, event=event)


@router.get("/{product_id}", response_model=ProductReviewSummary)
async def get_product_reviews(product_id: str):
    return review_repo.summarize_product(product_id)


@router.post("/{product_id}", response_model=Review, status_code=status.HTTP_201_CREATED)
async def create_review(
    product_id: str,
    payload: CreateReviewRequest,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    try:
        review = review_repo.create(
            product_id=product_id,
            user_id=user_id,
            rating=payload.rating,
            title=payload.title,
            comment=payload.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await _publish_if_connected(
        request,
        RoutingKeys.REVIEW_CREATED,
        ReviewCreatedEvent(
            review_id=review.review_id,
            product_id=review.product_id,
            user_id=review.user_id,
            rating=review.rating,
        ),
    )
    return review


@router.patch("/{review_id}", response_model=Review)
async def update_review(
    review_id: str,
    payload: UpdateReviewRequest,
    user_id: str = Depends(get_current_user_id),
):
    try:
        return review_repo.update(
            review_id=review_id,
            user_id=user_id,
            rating=payload.rating,
            title=payload.title,
            comment=payload.comment,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review(
    review_id: str,
    user_id: str = Depends(get_current_user_id),
):
    try:
        review_repo.delete(review_id=review_id, user_id=user_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
