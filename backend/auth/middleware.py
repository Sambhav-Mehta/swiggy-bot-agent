"""
backend/auth/middleware.py

FastAPI dependency: `get_current_user`

Uses Supabase's own auth.get_user(token) to validate the JWT instead of
manually decoding it with python-jose.  This works regardless of whether
the Supabase project uses HS256 or RS256 — no need to manage the JWT
secret or algorithm in our code.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.db.connection import get_supabase_anon_client

_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_scheme),
) -> dict:
    """
    Validate the Bearer token via Supabase and return the user payload.
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
        sb = get_supabase_anon_client()
        response = sb.auth.get_user(token)
        user = response.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"id": user.id, "email": user.email or ""}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


CurrentUser = Depends(get_current_user)
