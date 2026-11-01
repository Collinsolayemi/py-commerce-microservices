"""User authentication and profile management HTTP endpoints."""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from services.user_service.app.database import UserRepository
from services.user_service.app.models.user import (
    UserModel,
    UserRegister,
    UserLogin,
    TokenResponse,
    UserResponse,
)
from services.user_service.app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)

logger = logging.getLogger("user_service.routers.users")
router = APIRouter(prefix="/users", tags=["Users"])

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> UserModel:
    """Dependency to retrieve and authenticate the user from the JWT Bearer token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account no longer exists.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account.",
        )

    return user


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserRegister):
    """Register a new customer account."""
    existing_user = await UserRepository.get_by_email(payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    hashed_pw = hash_password(payload.password)
    user = await UserRepository.create_user(
        email=payload.email,
        hashed_password=hashed_pw,
        full_name=payload.full_name,
    )
    logger.info(f"Successfully registered new user: {user.id} ({user.email})")
    return user


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLogin):
    """Authenticate credentials and generate a JWT Bearer access token."""
    user = await UserRepository.get_by_email(payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact support.",
        )

    token_data = {
        "sub": user.id,
        "email": user.email,
        "full_name": user.full_name,
    }
    access_token = create_access_token(data=token_data)
    logger.info(f"User logged in successfully: {user.id}")

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: UserModel = Depends(get_current_user)):
    """Retrieve the authenticated user's profile."""
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(user_id: str):
    """Retrieve public profile for a specific user ID."""
    user = await UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Max results per page"),
):
    """List registered user accounts with pagination."""
    return await UserRepository.list_users(skip=skip, limit=limit)

