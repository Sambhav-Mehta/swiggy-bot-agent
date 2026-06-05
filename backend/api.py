"""
backend/api.py

FastAPI application root.
- Mounts auth, profile, orders sub-routers
- /api/chat is now JWT-protected; persona is loaded from Supabase, not the request body
- Serves built React SPA for all non-/api routes
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage

from agents.supervisor import swiggy_graph, _content_text
from backend.models import ChatRequest
from backend.db.crud import (
    get_user_profile, profile_to_persona_dict, upsert_chat_session,
    get_swiggy_connection,
)
from backend.auth.middleware import get_current_user
from backend.auth.router import router as auth_router
from backend.profile.router import router as profile_router
from backend.orders.router import router as orders_router
from backend.swiggy.router import router as swiggy_router

app = FastAPI(title="Swiggy Bot API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register sub-routers
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(orders_router)
app.include_router(swiggy_router)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_ROUTING_RE = re.compile(r'\s*```json[\s\S]*?```|\{\s*"next"\s*:\s*"\w+"\s*\}', re.DOTALL)

_AGENT_LABELS = {
    "health_agent": "🥗 Health Agent — searching restaurants…",
    "deal_agent":   "💰 Deal Agent — scanning coupons & card offers…",
    "order_agent":  "🛒 Order Agent — building your cart…",
}


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(request: ChatRequest, user=Depends(get_current_user)):
    """
    JWT-protected chat endpoint.
    Persona is loaded from Supabase (not sent by the client) so users
    cannot spoof another user's dietary rules or budget.
    """
    profile = get_user_profile(user["id"])
    if not profile:
        raise HTTPException(
            status_code=400,
            detail="Profile not found. Complete onboarding first.",
        )

    persona_dict = profile_to_persona_dict(profile)

    # Per-user Swiggy credentials (Phase 2). If the user connected their own
    # account, inject their token/URL so agents use it. Otherwise leave empty
    # and agents fall back to the shared SWIGGY_SESSION_TOKEN env var.
    swiggy_token = ""
    swiggy_mcp_url = ""
    try:
        conn = get_swiggy_connection(user["id"])
        if conn:
            swiggy_token   = conn.get("session_token", "") or ""
            swiggy_mcp_url = conn.get("mcp_server_url", "") or ""
    except Exception:
        pass  # fall back to shared default

    config = {
        "configurable": {"thread_id": request.session_id},
        "recursion_limit": 12,
    }
    initial_state = {
        "messages":      [HumanMessage(content=request.message)],
        "user_persona":  persona_dict,
        "swiggy_token":  swiggy_token,
        "swiggy_mcp_url": swiggy_mcp_url,
    }

    # Track the session in DB (upsert is idempotent)
    try:
        upsert_chat_session(user["id"], request.session_id)
    except Exception:
        pass  # non-critical

    async def event_stream():
        try:
            emitted_agents: set[str] = set()

            async for event in swiggy_graph.astream_events(
                initial_state, config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")
                node = event.get("metadata", {}).get("langgraph_node", "")

                if kind == "on_chain_start" and name in _AGENT_LABELS:
                    if name not in emitted_agents:
                        emitted_agents.add(name)
                        yield _sse({"type": "thinking", "agent": name,
                                    "label": _AGENT_LABELS[name]})

                elif kind == "on_chat_model_stream" and node == "supervisor":
                    chunk = event["data"].get("chunk")
                    if chunk:
                        text = _content_text(chunk.content)
                        text = _ROUTING_RE.sub("", text).strip()
                        if text:
                            yield _sse({"type": "text", "text": text})

            yield _sse({"type": "done"})

        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "text": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Serve built React SPA
# ─────────────────────────────────────────────────────────────────────────────

_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _DIST.exists():
    # Mount entire dist directory — html=True serves index.html for /
    # API routes registered above take precedence (they're checked first).
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="spa")
