"""SQLAlchemy and Pydantic models for Payment Service and Idempotency tracking."""

from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Float, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class IdempotencyStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ==========================================
# SQLAlchemy ORM Models
# ==========================================

class PaymentTransactionModel(Base):
    """Stores completed and attempted payment transactions."""
    __tablename__ = "payment_transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default=PaymentStatus.PENDING.value, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IdempotencyKeyModel(Base):
    """Guarantees distributed exactly-once payment processing semantics."""
    __tablename__ = "idempotency_keys"

    key = Column(String(128), primary_key=True)
    status = Column(String(20), default=IdempotencyStatus.PROCESSING.value, nullable=False)
    response_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ==========================================
# Pydantic Schemas
# ==========================================

class PaymentRequest(BaseModel):
    order_id: str = Field(..., description="Target order identifier")
    user_id: str = Field(..., description="Customer identifier")
    amount: float = Field(..., gt=0.0, description="Payment amount must be greater than zero")
    idempotency_key: Optional[str] = Field(None, description="Optional client idempotency token")


class PaymentResponse(BaseModel):
    id: str
    order_id: str
    user_id: str
    amount: float
    status: str
    reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

