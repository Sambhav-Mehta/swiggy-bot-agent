"""
backend/auth/router.py

Authentication endpoints using Supabase Auth.
Supabase handles password hashing, email confirmation, and JWT issuance.
We just proxy the calls and return the access token + basic profile.
"""

from fastapi import APIRouter, HTTPException, status, Depends

from backend.db.connection import get_supabase_anon_client
from backend.db.models import RegisterRequest, LoginRequest, AuthResponse
from backend.db.crud import get_user_profile, upsert_user_profile, profile_to_persona_dict
from backend.db.models import UserProfileIn
from backend.auth.middleware import get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    """
    Create a new Supabase user account.
    Also bootstraps an empty user_profiles row so downstream checks don't fail.
    """
    sb = get_supabase_anon_client()
    try:
        res = sb.auth.sign_up({"email": req.email, "password": req.password})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if res.user is None:
        raise HTTPException(status_code=400, detail="Registration failed — check email/password")

    user_id = res.user.id

    # Seed the profile with just the name so onboarding can detect it's incomplete
    upsert_user_profile(user_id, UserProfileIn(
        name=req.name,
        city="",           # filled during onboarding
        onboarding_done=False,
    ))

    token = res.session.access_token if res.session else ""
    return AuthResponse(
        access_token=token,
        user_id=user_id,
        email=req.email,
        name=req.name,
        onboarding_done=False,
    )


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    """Sign in with email + password; return JWT + profile state."""
    sb = get_supabase_anon_client()
    try:
        res = sb.auth.sign_in_with_password({"email": req.email, "password": req.password})
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if res.user is None or res.session is None:
        raise HTTPException(status_code=401, detail="Login failed")

    user_id = res.user.id
    profile = get_user_profile(user_id)

    return AuthResponse(
        access_token=res.session.access_token,
        user_id=user_id,
        email=res.user.email or "",
        name=profile.get("name") if profile else None,
        onboarding_done=profile.get("onboarding_done", False) if profile else False,
    )


@router.get("/me")
def me(user=Depends(get_current_user)):
    """Return the authenticated user's profile + onboarding state."""
    profile = get_user_profile(user["id"])
    return {
        "user_id": user["id"],
        "email":   user["email"],
        "profile": profile,
        "onboarding_done": profile.get("onboarding_done", False) if profile else False,
    }


@router.post("/logout")
def logout():
    """
    JWT-based auth is stateless on the backend.
    The frontend simply deletes the token from localStorage.
    This endpoint exists only for symmetry / future server-side session invalidation.
    """
    return {"message": "Logged out"}
