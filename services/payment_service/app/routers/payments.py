"""Payment processing and transaction HTTP endpoints."""

import json
import logging
import random
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Query, Header

from common.config import RoutingKeys
from common.events import PaymentSucceededEvent, PaymentFailedEvent
from services.payment_service.app.core.broker import get_rabbitmq_client
from services.payment_service.app.core.config import PAYMENT_SUCCESS_RATE
from services.payment_service.app.database import PaymentRepository
from services.payment_service.app.models.payment import (
    PaymentRequest,
    PaymentResponse,
    PaymentStatus,
    IdempotencyStatus,
)

logger = logging.getLogger("payment_service.routers.payments")
router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def process_payment(
    payload: PaymentRequest,
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    """
    Process a payment directly with idempotency check.
    """
    idempotency_key = payload.idempotency_key or x_idempotency_key or f"manual_pay_{payload.order_id}"

    # Check existing idempotency record
    existing_record = await PaymentRepository.get_idempotency_record(idempotency_key)
    if existing_record and existing_record.status == IdempotencyStatus.COMPLETED.value:
        existing_txn = await PaymentRepository.get_by_order_id(payload.order_id)
        if existing_txn:
            return existing_txn

    await PaymentRepository.save_idempotency_key(idempotency_key, IdempotencyStatus.PROCESSING)

    # Simulate authorization
    is_success = random.random() < PAYMENT_SUCCESS_RATE
    broker = get_rabbitmq_client()

    if is_success:
        transaction = await PaymentRepository.create_transaction(
            order_id=payload.order_id,
            user_id=payload.user_id,
            amount=payload.amount,
            status=PaymentStatus.SUCCESS,
        )
        await PaymentRepository.update_idempotency_result(
            key=idempotency_key,
            status=IdempotencyStatus.COMPLETED,
            response_payload=json.dumps({"transaction_id": transaction.id, "status": "SUCCESS"}),
        )

        if broker:
            try:
                await broker.publish(
                    RoutingKeys.PAYMENT_SUCCEEDED,
                    PaymentSucceededEvent(
                        payment_id=transaction.id,
                        order_id=payload.order_id,
                        user_id=payload.user_id,
                        amount=payload.amount,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish PaymentSucceededEvent: {exc}")

        return transaction

    else:
        reason = "Direct payment declined: Card authorization failed"
        transaction = await PaymentRepository.create_transaction(
            order_id=payload.order_id,
            user_id=payload.user_id,
            amount=payload.amount,
            status=PaymentStatus.FAILED,
            reason=reason,
        )
        await PaymentRepository.update_idempotency_result(
            key=idempotency_key,
            status=IdempotencyStatus.FAILED,
            response_payload=json.dumps({"transaction_id": transaction.id, "status": "FAILED"}),
        )

        if broker:
            try:
                await broker.publish(
                    RoutingKeys.PAYMENT_FAILED,
                    PaymentFailedEvent(
                        order_id=payload.order_id,
                        user_id=payload.user_id,
                        amount=payload.amount,
                        reason=reason,
                    ),
                )
            except Exception as exc:
                logger.warning(f"Could not publish PaymentFailedEvent: {exc}")

        return transaction


@router.get("", response_model=List[PaymentResponse])
async def list_payments(
    user_id: Optional[str] = Query(None, description="Filter by customer ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Retrieve transaction history with pagination and user filter."""
    return await PaymentRepository.list_transactions(user_id=user_id, skip=skip, limit=limit)


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str):
    """Fetch details of a single transaction by ID."""
    payment = await PaymentRepository.get_by_id(payment_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment transaction with ID '{payment_id}' not found.",
        )
    return payment


@router.get("/order/{order_id}", response_model=PaymentResponse)
async def get_payment_for_order(order_id: str):
    """Fetch payment transaction associated with an order ID."""
    payment = await PaymentRepository.get_by_order_id(order_id)
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No payment transaction found for order '{order_id}'.",
        )
    return payment
