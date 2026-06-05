"""
agents/mcp_config.py

Centralised builder for the Swiggy Food MCP connection config.

Per-user support (Phase 2):
    Each agent receives the user's Swiggy token + MCP URL through the graph
    State (injected by the backend from the swiggy_connections table).  When
    a user has connected their own Swiggy account, their token is used; when
    they have not, we fall back to the shared SWIGGY_SESSION_TOKEN env var.

This keeps all header / SSL / transport details in ONE place so the three
specialist agents (health, deal, order) never duplicate the logic.
"""

import os
import uuid

import httpx

# Shared/default credentials from the environment (the developer's account).
_ENV_TOKEN = os.getenv("SWIGGY_SESSION_TOKEN", "")
_ENV_URL   = os.getenv("SWIGGY_FOOD_MCP_URL", "")


def _no_ssl_factory(
    headers: dict | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """httpx factory with sane MCP timeouts + redirect following."""
    return httpx.AsyncClient(
        headers=headers or {},
        timeout=timeout or httpx.Timeout(30.0, read=300.0),
        auth=auth,
        verify=True,
        follow_redirects=True,
    )


def build_food_mcp_config(token: str = "", url: str = "") -> dict:
    """
    Return a MultiServerMCPClient config dict for the Swiggy Food server.

    Args:
        token: the user's Swiggy session token (from DB). Falls back to env.
        url:   the user's MCP server URL (from DB). Falls back to env.

    Both args are passed through the graph State.  Empty values mean
    "use the shared default" — so existing single-user behaviour is unchanged.
    """
    effective_token = token or _ENV_TOKEN
    effective_url   = url or _ENV_URL

    headers: dict[str, str] = {}
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"
    headers["X-Mcp-Client-Session-Id"] = str(uuid.uuid4())

    return {
        "swiggyFood": {
            "url": effective_url,
            "transport": "streamable_http",
            "headers": headers,
            "httpx_client_factory": _no_ssl_factory,
        }
    }


def config_from_state(state: dict) -> dict:
    """Convenience: build the MCP config from a graph State dict."""
    return build_food_mcp_config(
        token=state.get("swiggy_token", "") or "",
        url=state.get("swiggy_mcp_url", "") or "",
    )
