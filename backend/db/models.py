"""
backend/db/models.py

Pydantic response/request models for DB-backed resources.
These mirror the Supabase table schema.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, EmailStr


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    name: Optional[str] = None
    onboarding_done: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# User Profile
# ─────────────────────────────────────────────────────────────────────────────

class UserProfileIn(BaseModel):
    name: str
    phone: Optional[str] = None
    city: str
    fitness_goal: Optional[str] = None       # 'muscle_gain' | 'weight_loss' | 'maintenance'
    diet_type: str = "veg"                   # 'veg' | 'non_veg' | 'both'
    restrictions: Optional[List[str]] = []   # ['no_mushrooms', 'no_onion']
    cuisine_prefs: Optional[List[str]] = []  # ['north_indian', 'south_indian']
    budget_wkday: Optional[int] = None       # rupees
    budget_wknd: Optional[int] = None
    saved_cards: Optional[List[str]] = []    # ['hdfc_swiggy', 'sbi_cashback']
    default_address_id: Optional[str] = None
    onboarding_done: bool = False


class UserProfileOut(UserProfileIn):
    user_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Addresses
# ─────────────────────────────────────────────────────────────────────────────

class AddressIn(BaseModel):
    label: str = "Home"
    full_address: str
    city: Optional[str] = None
    pincode: Optional[str] = None
    is_default: bool = False
    swiggy_addr_id: Optional[str] = None


class AddressOut(AddressIn):
    id: str
    user_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────────────────────────────────────

class OrderIn(BaseModel):
    session_id: Optional[str] = None
    swiggy_order_id: Optional[str] = None
    restaurant_name: Optional[str] = None
    dish_name: Optional[str] = None
    amount_paid: Optional[int] = None
    coupon_used: Optional[str] = None
    payment_method: Optional[str] = None
    status: str = "placed"
    delivery_address: Optional[str] = None


class OrderOut(OrderIn):
    id: str
    user_id: str
    created_at: str


# ─────────────────────────────────────────────────────────────────────────────
# Swiggy connection (Phase 2)
# ─────────────────────────────────────────────────────────────────────────────

class SwiggyConnectIn(BaseModel):
    session_token: str                     # user's claude.ai OAuth token
    mcp_server_url: str                     # user's Swiggy Food MCP proxy URL


class SwiggyStatusOut(BaseModel):
    connected: bool
    mcp_server_url: Optional[str] = None
    connected_at: Optional[str] = None
