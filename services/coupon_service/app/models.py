"""Domain models and in-memory repository for Promotions & Coupons Service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, model_validator


def _normalize_code(code: str) -> str:
    return code.strip().upper()


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DiscountType(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class RedemptionStatus(str, Enum):
    REDEEMED = "REDEEMED"
    RELEASED = "RELEASED"


class Coupon(BaseModel):
    coupon_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    description: str = ""
    discount_type: DiscountType
    discount_value: float = Field(gt=0.0)
    min_order_amount: float = Field(default=0.0, ge=0.0)
    max_discount_amount: Optional[float] = Field(default=None, gt=0.0)
    max_uses: Optional[int] = Field(default=None, gt=0)
    per_user_limit: int = Field(default=1, gt=0)
    used_count: int = Field(default=0, ge=0)
    active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CreateCouponRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(default="", max_length=240)
    discount_type: DiscountType
    discount_value: float = Field(..., gt=0.0)
    min_order_amount: float = Field(default=0.0, ge=0.0)
    max_discount_amount: Optional[float] = Field(default=None, gt=0.0)
    max_uses: Optional[int] = Field(default=None, gt=0)
    per_user_limit: int = Field(default=1, gt=0)
    expires_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_percentage_bounds(self) -> "CreateCouponRequest":
        if self.discount_type == DiscountType.PERCENTAGE and self.discount_value > 100.0:
            raise ValueError("Percentage discount cannot exceed 100")
        return self


class ValidateCouponRequest(BaseModel):
    code: str = Field(..., min_length=1)
    order_amount: float = Field(..., gt=0.0)


class CouponQuoteResponse(BaseModel):
    code: str
    valid: bool
    order_amount: float
    discount_amount: float
    final_amount: float
    reason: Optional[str] = None


class RedeemCouponRequest(BaseModel):
    order_id: str = Field(..., min_length=1)
    order_amount: float = Field(..., gt=0.0)


class CouponRedemption(BaseModel):
    redemption_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    coupon_id: str
    code: str
    order_id: str
    user_id: str
    order_amount: float
    discount_amount: float
    final_amount: float
    status: RedemptionStatus = RedemptionStatus.REDEEMED
    redeemed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: Optional[datetime] = None


class CouponRepository:
    """In-memory promotional code and order-indexed redemption store."""

    def __init__(self) -> None:
        self._coupons: Dict[str, Coupon] = {}
        self._redemptions_by_order: Dict[str, CouponRedemption] = {}

    def create(self, payload: CreateCouponRequest) -> Coupon:
        code = _normalize_code(payload.code)
        if code in self._coupons:
            raise ValueError(f"Coupon '{code}' already exists")

        coupon = Coupon(
            code=code,
            description=payload.description.strip(),
            discount_type=payload.discount_type,
            discount_value=payload.discount_value,
            min_order_amount=payload.min_order_amount,
            max_discount_amount=payload.max_discount_amount,
            max_uses=payload.max_uses,
            per_user_limit=payload.per_user_limit,
            expires_at=_as_utc(payload.expires_at) if payload.expires_at else None,
        )
        self._coupons[code] = coupon
        return coupon

    def get(self, code: str) -> Optional[Coupon]:
        return self._coupons.get(_normalize_code(code))

    def list_all(self, active_only: bool = False) -> List[Coupon]:
        items = list(self._coupons.values())
        if active_only:
            now = datetime.now(timezone.utc)
            items = [
                c
                for c in items
                if c.active
                and (c.expires_at is None or _as_utc(c.expires_at) > now)
                and (c.max_uses is None or c.used_count < c.max_uses)
            ]
        return sorted(items, key=lambda c: c.created_at, reverse=True)

    def deactivate(self, code: str) -> Coupon:
        coupon = self.get(code)
        if coupon is None:
            raise KeyError(code)
        coupon.active = False
        return coupon

    def _compute_discount(self, coupon: Coupon, order_amount: float) -> float:
        if coupon.discount_type == DiscountType.PERCENTAGE:
            raw_discount = order_amount * (coupon.discount_value / 100.0)
            if coupon.max_discount_amount is not None:
                raw_discount = min(raw_discount, coupon.max_discount_amount)
        else:
            raw_discount = coupon.discount_value

        return round(min(raw_discount, order_amount), 2)

    def _active_user_redemptions(self, code: str, user_id: str) -> int:
        return sum(
            1
            for r in self._redemptions_by_order.values()
            if r.code == code
            and r.user_id == user_id
            and r.status == RedemptionStatus.REDEEMED
        )

    def quote(
        self, code: str, order_amount: float, user_id: Optional[str] = None
    ) -> CouponQuoteResponse:
        normalized = _normalize_code(code)
        rounded_order = round(order_amount, 2)
        coupon = self._coupons.get(normalized)

        def invalid(reason: str) -> CouponQuoteResponse:
            return CouponQuoteResponse(
                code=normalized,
                valid=False,
                order_amount=rounded_order,
                discount_amount=0.0,
                final_amount=rounded_order,
                reason=reason,
            )

        if coupon is None:
            return invalid("Coupon code not found")
        if not coupon.active:
            return invalid("Coupon is inactive")
        if coupon.expires_at is not None and _as_utc(coupon.expires_at) <= datetime.now(timezone.utc):
            return invalid("Coupon has expired")
        if order_amount < coupon.min_order_amount:
            return invalid(
                f"Minimum order amount of ${coupon.min_order_amount:.2f} required"
            )
        if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
            return invalid("Coupon redemption limit reached")
        if user_id and self._active_user_redemptions(normalized, user_id) >= coupon.per_user_limit:
            return invalid("Per-customer redemption limit reached for this coupon")

        discount = self._compute_discount(coupon, order_amount)
        final_amount = round(max(0.0, order_amount - discount), 2)
        return CouponQuoteResponse(
            code=normalized,
            valid=True,
            order_amount=rounded_order,
            discount_amount=discount,
            final_amount=final_amount,
        )

    def redeem(
        self, code: str, order_id: str, user_id: str, order_amount: float
    ) -> Tuple[CouponRedemption, bool]:
        normalized = _normalize_code(code)
        coupon = self._coupons.get(normalized)
        if coupon is None:
            raise KeyError(normalized)

        existing = self._redemptions_by_order.get(order_id)
        if existing is not None and existing.status == RedemptionStatus.REDEEMED:
            if existing.code == normalized and existing.user_id == user_id:
                return existing, False
            raise ValueError(f"Order '{order_id}' already has an active coupon redemption")

        quote = self.quote(normalized, order_amount, user_id=user_id)
        if not quote.valid:
            raise ValueError(quote.reason or "Coupon is not valid for this order")

        redemption = CouponRedemption(
            coupon_id=coupon.coupon_id,
            code=normalized,
            order_id=order_id,
            user_id=user_id,
            order_amount=quote.order_amount,
            discount_amount=quote.discount_amount,
            final_amount=quote.final_amount,
        )
        coupon.used_count += 1
        self._redemptions_by_order[order_id] = redemption
        return redemption, True

    def get_redemption_by_order(self, order_id: str) -> Optional[CouponRedemption]:
        return self._redemptions_by_order.get(order_id)

    def release_by_order(self, order_id: str) -> Optional[CouponRedemption]:
        redemption = self._redemptions_by_order.get(order_id)
        if redemption is None or redemption.status != RedemptionStatus.REDEEMED:
            return None

        redemption.status = RedemptionStatus.RELEASED
        redemption.released_at = datetime.now(timezone.utc)
        coupon = self._coupons.get(redemption.code)
        if coupon is not None and coupon.used_count > 0:
            coupon.used_count -= 1
        return redemption

    def clear(self) -> None:
        self._coupons.clear()
        self._redemptions_by_order.clear()


coupon_repo = CouponRepository()

