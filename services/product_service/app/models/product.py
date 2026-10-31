"""Data models for Products and Inventory."""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=150, example="Wireless Mechanical Keyboard")
    description: Optional[str] = Field(None, example="RGB backlit mechanical keyboard with hot-swappable switches")
    price: float = Field(..., gt=0.0, example=99.99)
    stock_quantity: int = Field(..., ge=0, example=50)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(None, gt=0.0)
    stock_quantity: Optional[int] = Field(None, ge=0)


class StockAdjustment(BaseModel):
    delta: int = Field(..., description="Positive to add stock, negative to subtract stock", example=10)


class ProductResponse(ProductBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reserved_quantity: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        from_attributes = True

