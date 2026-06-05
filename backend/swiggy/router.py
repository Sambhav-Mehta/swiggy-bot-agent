"""
backend/swiggy/router.py

Endpoints for connecting a user's OWN Swiggy account (Phase 2, Option D).

Because the Anthropic MCP proxy does not expose a third-party OAuth flow,
"connecting" means the user supplies their own claude.ai OAuth token + their
own Swiggy Food MCP server URL (obtained from claude.ai → Connected apps).
We validate the credentials by listing tools, then store them encrypted.

If a user never connects, the bot falls back to the shared env credentials —
so this whole feature is optional.
"""

import uuid

from fastapi import APIRouter, HTTPException, Depends

from backend.auth.middleware import get_current_user
from backend.db.models import SwiggyConnectIn, SwiggyStatusOut
from backend.db.crud import (
    upsert_swiggy_connection, get_swiggy_connection, delete_swiggy_connection,
)
from agents.mcp_config import build_food_mcp_config

router = APIRouter(prefix="/api/swiggy", tags=["swiggy"])


async def _validate_credentials(token: str, url: str) -> int:
    """
    Verify the token + URL actually work by listing MCP tools.
    Returns the tool count on success; raises HTTPException on failure.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient

    cfg = build_food_mcp_config(token=token, url=url)
    try:
        client = MultiServerMCPClient(cfg)
        tools = await client.get_tools()
        return len(tools)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400,
            detail=f"Could not connect to Swiggy with those credentials: {exc}",
        )


@router.post("/connect")
async def connect_swiggy(body: SwiggyConnectIn, user=Depends(get_current_user)):
    """Validate + store the user's own Swiggy MCP credentials."""
    tool_count = await _validate_credentials(body.session_token, body.mcp_server_url)
    upsert_swiggy_connection(user["id"], body.session_token, body.mcp_server_url)
    return {"connected": True, "tools_available": tool_count}


@router.get("/status", response_model=SwiggyStatusOut)
def swiggy_status(user=Depends(get_current_user)):
    """Whether the user has connected their own Swiggy account."""
    conn = get_swiggy_connection(user["id"])
    if not conn:
        return SwiggyStatusOut(connected=False)
    return SwiggyStatusOut(
        connected=True,
        mcp_server_url=conn.get("mcp_server_url"),
        connected_at=conn.get("connected_at"),
    )


@router.delete("/disconnect", status_code=204)
def disconnect_swiggy(user=Depends(get_current_user)):
    """Remove the user's Swiggy connection — bot reverts to shared default."""
    delete_swiggy_connection(user["id"])
