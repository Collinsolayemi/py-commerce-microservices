"""SQLAlchemy and Pydantic models for User Service and Authentication."""

from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


# ==========================================
# SQLAlchemy ORM Models
# ==========================================

class UserModel(Base):
    """User account model for customer identity and authentication."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ==========================================
# Pydantic Schemas
# ==========================================

class UserRegister(BaseModel):
    """User registration payload."""
    email: EmailStr = Field(..., description="Valid unique email address")
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    full_name: str = Field(..., min_length=1, max_length=255, description="Customer's full name")


class UserLogin(BaseModel):
    """User authentication login payload."""
    email: EmailStr = Field(..., description="Account email address")
    password: str = Field(..., description="Account password")


class TokenResponse(BaseModel):
    """JWT bearer token response."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


class UserResponse(BaseModel):
    """Public user profile response."""
    id: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

