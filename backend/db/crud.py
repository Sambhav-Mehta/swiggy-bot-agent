"""
backend/db/crud.py

All Supabase database operations.
Every function takes an explicit `user_id` so there is never ambiguity
about which user's data is being read or written.
"""

from __future__ import annotations
from typing import Optional

from backend.db.connection import get_supabase_client
from backend.db.models import UserProfileIn, AddressIn, OrderIn
from backend.swiggy.crypto import encrypt, decrypt


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

def get_user_profile(user_id: str) -> Optional[dict]:
    """Return the user's profile row, or None if not yet created."""
    sb = get_supabase_client()
    res = sb.table("user_profiles").select("*").eq("user_id", user_id).maybe_single().execute()
    return res.data


def upsert_user_profile(user_id: str, profile: UserProfileIn) -> dict:
    """Create or update the user's profile."""
    sb = get_supabase_client()
    data = profile.model_dump()
    data["user_id"] = user_id
    res = (
        sb.table("user_profiles")
        .upsert(data, on_conflict="user_id")
        .execute()
    )
    return res.data[0]


def profile_to_persona_dict(profile: dict) -> dict:
    """
    Convert a DB profile row into the persona dict that supervisor.py expects.
    Mirrors what _persona_to_dict() in api.py used to do from the request body.
    """
    if not profile:
        return {}

    restrictions = ", ".join(profile.get("restrictions") or []) or "None"
    cuisine = ", ".join(profile.get("cuisine_prefs") or []) or "Not specified"
    cards    = ", ".join(profile.get("saved_cards") or []) or "None saved"

    raw = (
        f"# User Persona: [{profile.get('name', 'User')}]\n"
        f"- **Location:** {profile.get('city', '')}\n"
        f"- **Dietary Goals:** {profile.get('fitness_goal') or 'Healthy eating'}\n"
        f"- **Restrictions:** {restrictions}\n"
        f"- **Diet Type:** {profile.get('diet_type', 'veg')}\n"
        f"- **Preferences:** {cuisine}\n"
        f"- **Budget Logic:**\n"
        f"  - Weekdays: Under ₹{profile.get('budget_wkday') or 500}/meal\n"
        f"  - Weekends: Up to ₹{profile.get('budget_wknd') or 1500}+\n"
        f"- **Saved Cards:** {cards}\n"
        f"- **Rule #1:** Never suggest a restaurant with less than 4.0 stars.\n"
        f"- **Rule #2:** Always check for the best available offer.\n"
        f"- **Rule #3:** Suggest card offers based on saved cards.\n"
    )

    return {
        "raw":          raw,
        "name":         profile.get("name", "User"),
        "location":     profile.get("city", ""),
        "diet_goals":   profile.get("fitness_goal") or "",
        "restrictions": restrictions,
        "preferences":  cuisine,
        "budget_wkday": f"Under ₹{profile.get('budget_wkday') or 500}/meal",
        "budget_wknd":  f"Up to ₹{profile.get('budget_wknd') or 1500}+",
        "address_id":   profile.get("default_address_id") or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Addresses
# ─────────────────────────────────────────────────────────────────────────────

def get_addresses(user_id: str) -> list[dict]:
    sb = get_supabase_client()
    res = sb.table("user_addresses").select("*").eq("user_id", user_id).execute()
    return res.data or []


def add_address(user_id: str, address: AddressIn) -> dict:
    sb = get_supabase_client()
    data = address.model_dump()
    data["user_id"] = user_id

    # If this is the user's first address or marked default, unset others
    if address.is_default:
        sb.table("user_addresses").update({"is_default": False}).eq("user_id", user_id).execute()

    res = sb.table("user_addresses").insert(data).execute()
    addr = res.data[0]

    # If it's the default, also update user_profiles.default_address_id
    if address.is_default:
        sb.table("user_profiles").update(
            {"default_address_id": addr["swiggy_addr_id"] or addr["id"]}
        ).eq("user_id", user_id).execute()

    return addr


def delete_address(user_id: str, address_id: str) -> None:
    sb = get_supabase_client()
    sb.table("user_addresses").delete().eq("id", address_id).eq("user_id", user_id).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Orders
# ─────────────────────────────────────────────────────────────────────────────

def save_order(user_id: str, order: OrderIn) -> dict:
    sb = get_supabase_client()
    data = order.model_dump()
    data["user_id"] = user_id
    res = sb.table("order_history").insert(data).execute()
    return res.data[0]


def get_orders(user_id: str, limit: int = 20) -> list[dict]:
    sb = get_supabase_client()
    res = (
        sb.table("order_history")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# Chat sessions
# ─────────────────────────────────────────────────────────────────────────────

def upsert_chat_session(user_id: str, thread_id: str, title: str = "") -> dict:
    sb = get_supabase_client()
    res = (
        sb.table("chat_sessions")
        .upsert(
            {"user_id": user_id, "thread_id": thread_id, "title": title,
             "last_msg_at": "now()"},
            on_conflict="thread_id",
        )
        .execute()
    )
    return res.data[0] if res.data else {}


def get_chat_sessions(user_id: str) -> list[dict]:
    sb = get_supabase_client()
    res = (
        sb.table("chat_sessions")
        .select("*")
        .eq("user_id", user_id)
        .order("last_msg_at", desc=True)
        .limit(20)
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# Swiggy connections (Phase 2 — per-user MCP tokens)
# Tokens are encrypted at rest via backend.swiggy.crypto.
# ─────────────────────────────────────────────────────────────────────────────

def upsert_swiggy_connection(user_id: str, session_token: str, mcp_server_url: str) -> dict:
    """Store (encrypted) the user's own Swiggy MCP token + URL."""
    sb = get_supabase_client()
    res = (
        sb.table("swiggy_connections")
        .upsert(
            {
                "user_id": user_id,
                "session_token": encrypt(session_token),
                "mcp_server_url": mcp_server_url,
                "connected_at": "now()",
            },
            on_conflict="user_id",
        )
        .execute()
    )
    return res.data[0] if res.data else {}


def get_swiggy_connection(user_id: str) -> Optional[dict]:
    """
    Return the user's decrypted Swiggy connection, or None if not connected.
    Shape: {"session_token": <plain>, "mcp_server_url": <url>, "connected_at": ...}
    """
    sb = get_supabase_client()
    res = (
        sb.table("swiggy_connections")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        return None
    row = res.data
    row["session_token"] = decrypt(row.get("session_token", ""))
    return row


def delete_swiggy_connection(user_id: str) -> None:
    sb = get_supabase_client()
    sb.table("swiggy_connections").delete().eq("user_id", user_id).execute()
