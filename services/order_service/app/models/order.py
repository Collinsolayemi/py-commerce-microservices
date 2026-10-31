"""SQLAlchemy and Pydantic models for Order Service."""

from __future__ import annotations
import enum
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


# ==========================================
# SQLAlchemy ORM Models
# ==========================================

class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=False, index=True)
    total_price = Column(Float, nullable=False, default=0.0)
    status = Column(String(20), default=OrderStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = relationship("OrderItemModel", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(100), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)

    order = relationship("OrderModel", back_populates="items")


# ==========================================
# Pydantic Schemas
# ==========================================

class OrderItemCreate(BaseModel):
    product_id: str = Field(..., description="Target product identifier")
    quantity: int = Field(..., gt=0, description="Quantity must be greater than zero")
    unit_price: float = Field(..., ge=0.0, description="Price per unit at time of purchase")


class OrderCreate(BaseModel):
    user_id: str = Field(..., description="ID of the purchasing customer")
    items: List[OrderItemCreate] = Field(..., min_items=1, description="List of items in order")


class OrderItemResponse(BaseModel):
    id: str
    product_id: str
    quantity: int
    price: float

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: str
    user_id: str
    total_price: float
    status: str
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True

