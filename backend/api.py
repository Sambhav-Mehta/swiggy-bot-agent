"""
backend/api.py

FastAPI server — exposes the LangGraph Swiggy Bot pipeline as an SSE streaming
endpoint so any frontend can drive a real-time multi-user chat experience.

Endpoints
─────────
POST /api/chat   Stream bot response as Server-Sent Events
GET  /api/health Liveness check

Session model
─────────────
Each browser generates a UUID (stored in localStorage) and sends it as
`session_id` on every request.  That UUID becomes the LangGraph `thread_id`,
so MemorySaver preserves the full conversation + cart state across turns.
A "New Chat" button in the UI just generates a fresh UUID.

Persona injection
─────────────────
`load_persona()` in supervisor.py already skips the file-read if
`user_persona` is pre-populated in the initial state.  We build the dict here
from the Pydantic `Persona` model and inject it on every request.  On
subsequent turns within the same session LangGraph's checkpointer carries it
forward automatically.
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage

from agents.supervisor import swiggy_graph, _content_text
from backend.models import ChatRequest, Persona

app = FastAPI(title="Swiggy Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_ROUTING_RE = re.compile(r'\s*```json[\s\S]*?```|\{\s*"next"\s*:\s*"\w+"\s*\}', re.DOTALL)

_AGENT_LABELS = {
    "health_agent": "🥗 Health Agent — searching restaurants…",
    "deal_agent":   "💰 Deal Agent — scanning coupons & card offers…",
    "order_agent":  "🛒 Order Agent — building your cart…",
}


def _persona_to_dict(p: Persona) -> dict:
    """Convert the Pydantic Persona into the dict format supervisor.py expects."""
    raw = (
        f"# User Persona: [{p.name}]\n"
        f"- **Location:** {p.location}\n"
        f"- **Dietary Goals:** {p.diet_goals or 'Balanced, healthy'}\n"
        f"- **Restrictions:** {p.restrictions or 'None specified'}\n"
        f"- **Preferences:** {p.preferences or 'Not specified'}\n"
        f"- **Budget Logic:**\n"
        f"  - Weekdays: {p.budget_wkday or 'Under ₹500/meal'}\n"
        f"  - Weekends: {p.budget_wknd or 'Open to fine dining'}\n"
        f"- **Rule #1:** Never suggest a restaurant with less than 4.0 stars.\n"
        f"- **Rule #2:** Always check for the best available offer and apply it automatically.\n"
        f"- **Rule #3:** Always check for the best available card offers.\n"
    )
    return {
        "raw":          raw,
        "name":         p.name,
        "location":     p.location,
        "diet_goals":   p.diet_goals,
        "restrictions": p.restrictions,
        "preferences":  p.preferences,
        "budget_wkday": p.budget_wkday,
        "budget_wknd":  p.budget_wknd,
        "address_id":   p.address_id or os.getenv("SWIGGY_ADDRESS_ID", ""),
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
async def chat(request: ChatRequest):
    persona_dict = _persona_to_dict(request.persona)
    config = {
        "configurable": {"thread_id": request.session_id},
        "recursion_limit": 12,
    }
    initial_state = {
        "messages":    [HumanMessage(content=request.message)],
        "user_persona": persona_dict,
    }

    async def event_stream():
        try:
            emitted_agents: set[str] = set()

            async for event in swiggy_graph.astream_events(
                initial_state, config, version="v2"
            ):
                kind = event["event"]
                name = event.get("name", "")
                # langgraph_node in metadata is the reliable way to know which
                # graph node is currently executing in LangGraph v2 events.
                node = event.get("metadata", {}).get("langgraph_node", "")

                # ── specialist agent entered → show thinking badge once ──────
                if kind == "on_chain_start" and name in _AGENT_LABELS:
                    if name not in emitted_agents:
                        emitted_agents.add(name)
                        yield _sse({"type": "thinking", "agent": name,
                                    "label": _AGENT_LABELS[name]})

                # ── supervisor LLM tokens → stream character by character ────
                # Filter by langgraph_node so inner ReAct agent tokens (from
                # health/deal/order) are never leaked to the user.
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

    # Note: do NOT add Access-Control-Allow-Origin here — CORSMiddleware
    # already adds it. Duplicate headers cause browsers to reject the stream.
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",   # prevent nginx from buffering SSE
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Serve built React app (production)
# FastAPI serves frontend/dist/* so only one Railway service is needed.
# ─────────────────────────────────────────────────────────────────────────────

_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _DIST.exists():
    from starlette.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Return index.html for all non-API routes (SPA client-side routing)."""
        return FileResponse(str(_DIST / "index.html"))
