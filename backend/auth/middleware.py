"""
backend/auth/middleware.py

FastAPI dependency: `get_current_user`
Validates the Supabase JWT sent in the Authorization header and returns
the decoded user payload.  Raise 401 on any failure.
"""

import os
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

_scheme = HTTPBearer(auto_error=False)


def _get_jwt_secret() -> str:
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET env var is not set")
    return secret


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_scheme),
) -> dict:
    """
    Decode and validate the Supabase JWT.
    Returns the full decoded payload (includes `sub` = user UUID, `email`, etc.).
    Raises HTTP 401 if the token is missing, expired, or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=["HS256"],
            options={"verify_aud": False},  # Supabase doesn't always include aud
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    return {"id": user_id, "email": payload.get("email", "")}


# Convenience alias for routes that don't need the full payload
CurrentUser = Depends(get_current_user)
