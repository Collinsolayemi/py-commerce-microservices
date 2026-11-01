"""Shared JWT security and token verification helpers across all microservices."""

import os
from typing import Optional, Dict, Any
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-ecommerce-jwt-key-2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

security_scheme = HTTPBearer(auto_error=False)


def verify_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify a JWT token.
    Raises HTTPException(401) if invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please authenticate again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> str:
    """
    FastAPI dependency to extract and verify the user_id (sub) from the Bearer token.
    Enforces authentication.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject or user identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(user_id)


def get_optional_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Optional[str]:
    """
    FastAPI dependency to optionally extract user_id if Bearer token is provided.
    Does not enforce authentication for anonymous-friendly endpoints.
    """
    if not credentials:
        return None
    try:
        payload = verify_token(credentials.credentials)
        user_id = payload.get("sub") or payload.get("user_id")
        return str(user_id) if user_id else None
    except HTTPException:
        return None
