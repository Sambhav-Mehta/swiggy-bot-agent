"""
backend/profile/router.py

User profile and address management endpoints.
All routes are protected — require a valid JWT.
"""

from fastapi import APIRouter, HTTPException, Depends

from backend.auth.middleware import get_current_user
from backend.db.crud import (
    get_user_profile, upsert_user_profile,
    get_addresses, add_address, delete_address,
)
from backend.db.models import UserProfileIn, AddressIn

router = APIRouter(prefix="/api", tags=["profile"])


# ── Profile ──────────────────────────────────────────────────────────────────

@router.get("/profile")
def read_profile(user=Depends(get_current_user)):
    profile = get_user_profile(user["id"])
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


@router.put("/profile")
def update_profile(body: UserProfileIn, user=Depends(get_current_user)):
    updated = upsert_user_profile(user["id"], body)
    return updated


# ── Addresses ─────────────────────────────────────────────────────────────────

@router.get("/addresses")
def list_addresses(user=Depends(get_current_user)):
    return get_addresses(user["id"])


@router.post("/addresses", status_code=201)
def create_address(body: AddressIn, user=Depends(get_current_user)):
    return add_address(user["id"], body)


@router.delete("/addresses/{address_id}", status_code=204)
def remove_address(address_id: str, user=Depends(get_current_user)):
    delete_address(user["id"], address_id)
