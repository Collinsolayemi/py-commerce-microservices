"""REST endpoints for Promotions & Coupons Service."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from common.config import RoutingKeys
from common.events import BaseEvent, CouponCreatedEvent, CouponRedeemedEvent
from common.rabbitmq import RabbitMQClient
from common.security import get_current_user_id, get_optional_user_id
from services.coupon_service.app.models import (
    Coupon,
    CouponQuoteResponse,
    CouponRedemption,
    CreateCouponRequest,
    RedeemCouponRequest,
    ValidateCouponRequest,
    coupon_repo,
)

router = APIRouter(prefix="/coupons", tags=["Coupons"])


async def _publish_if_connected(request: Request, routing_key: str, event: BaseEvent) -> None:
    client: Optional[RabbitMQClient] = getattr(request.app.state, "rabbitmq_client", None)
    if client is not None and client.exchange is not None:
        await client.publish(routing_key=routing_key, event=event)


@router.get("", response_model=List[Coupon])
async def list_coupons(active_only: bool = Query(default=False)):
    return coupon_repo.list_all(active_only=active_only)


@router.post("", response_model=Coupon, status_code=status.HTTP_201_CREATED)
async def create_coupon(payload: CreateCouponRequest, request: Request):
    try:
        coupon = coupon_repo.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await _publish_if_connected(
        request,
        RoutingKeys.COUPON_CREATED,
        CouponCreatedEvent(
            coupon_id=coupon.coupon_id,
            code=coupon.code,
            discount_type=coupon.discount_type.value,
            discount_value=coupon.discount_value,
        ),
    )
    return coupon


@router.post("/validate", response_model=CouponQuoteResponse)
async def validate_coupon(
    payload: ValidateCouponRequest,
    user_id: Optional[str] = Depends(get_optional_user_id),
):
    return coupon_repo.quote(
        code=payload.code,
        order_amount=payload.order_amount,
        user_id=user_id,
    )


@router.get("/redemptions/{order_id}", response_model=CouponRedemption)
async def get_order_redemption(
    order_id: str,
    user_id: str = Depends(get_current_user_id),
):
    redemption = coupon_repo.get_redemption_by_order(order_id)
    if redemption is None or redemption.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon redemption not found",
        )
    return redemption


@router.get("/{code}", response_model=Coupon)
async def get_coupon(code: str):
    coupon = coupon_repo.get(code)
    if coupon is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon code not found",
        )
    return coupon


@router.post(
    "/{code}/redeem",
    response_model=CouponRedemption,
    status_code=status.HTTP_201_CREATED,
)
async def redeem_coupon(
    code: str,
    payload: RedeemCouponRequest,
    request: Request,
    response: Response,
    user_id: str = Depends(get_current_user_id),
):
    try:
        redemption, created = coupon_repo.redeem(
            code=code,
            order_id=payload.order_id,
            user_id=user_id,
            order_amount=payload.order_amount,
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon code not found",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if created:
        await _publish_if_connected(
            request,
            RoutingKeys.COUPON_REDEEMED,
            CouponRedeemedEvent(
                redemption_id=redemption.redemption_id,
                coupon_id=redemption.coupon_id,
                code=redemption.code,
                order_id=redemption.order_id,
                user_id=redemption.user_id,
                discount_amount=redemption.discount_amount,
                final_amount=redemption.final_amount,
            ),
        )
    else:
        response.status_code = status.HTTP_200_OK

    return redemption


@router.post("/{code}/deactivate", response_model=Coupon)
async def deactivate_coupon(code: str):
    try:
        return coupon_repo.deactivate(code)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coupon code not found",
        )

