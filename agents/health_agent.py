"""
agents/health_agent.py

Health Agent — nutrition-aware restaurant and dish selector.
Connects to the swiggyFood MCP server via a ReAct inner agent, runs a
multi-step search-and-filter pipeline, and hands exactly 3 curated
high-protein picks back to the Supervisor.

Inner agent loop:
    search_restaurants → filter veg + 4.0 stars → get_restaurant_menu
        → filter protein / no-mushrooms → rank top 3 → hand off

Integration with supervisor.py:
    Replace the call_health_agent stub with:
        from agents.health_agent import health_agent_node
        graph.add_node("health_agent", health_agent_node)
    Update the CLI to use asyncio:
        import asyncio
        result = asyncio.run(swiggy_graph.ainvoke({"messages": [...]}, config=config))
"""

import os
import re
import traceback
import uuid
from typing import Literal

import agents.schema_fix  # noqa: F401 — patches Gemini schema validator for integer enums

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from agents.supervisor import State, _content_text


# ──────────────────────────────────────────────────────────────────────────────
# MCP Connection helpers
# ──────────────────────────────────────────────────────────────────────────────

_SESSION_TOKEN = os.getenv("SWIGGY_SESSION_TOKEN", "")


def _mcp_headers() -> dict[str, str]:
    """Build headers required by the Anthropic MCP proxy.

    The proxy needs:
      - Authorization: Bearer <claude.ai OAuth token>
      - X-Mcp-Client-Session-Id: <any UUID, unique per session>
    """
    headers: dict[str, str] = {}
    if _SESSION_TOKEN:
        headers["Authorization"] = f"Bearer {_SESSION_TOKEN}"
    headers["X-Mcp-Client-Session-Id"] = str(uuid.uuid4())
    return headers


def _no_ssl_factory(
    headers: dict | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """httpx factory: SSL verification disabled (corporate firewall) + MCP defaults."""
    return httpx.AsyncClient(
        headers=headers or {},
        timeout=timeout or httpx.Timeout(30.0, read=300.0),
        auth=auth,
        verify=True,
        follow_redirects=True,
    )


_MCP_CONFIG = {
    "swiggyFood": {
        "url": os.getenv("SWIGGY_FOOD_MCP_URL", ""),  # set SWIGGY_FOOD_MCP_URL in .env
        "transport": "streamable_http",
        "headers": _mcp_headers(),
        "httpx_client_factory": _no_ssl_factory,
    }
}


# ──────────────────────────────────────────────────────────────────────────────
# LLM — imported fallback builder from supervisor keeps config in one place
# ──────────────────────────────────────────────────────────────────────────────

from agents.supervisor import _build_llm  # noqa: E402

_llm = _build_llm()

# ──────────────────────────────────────────────────────────────────────────────
# System Prompt for the inner ReAct agent
# All dietary, rating, and location rules are encoded here so the inner
# agent never needs to be told twice.
# ──────────────────────────────────────────────────────────────────────────────

_ADDRESS_ID = os.getenv("SWIGGY_ADDRESS_ID", "")  # set SWIGGY_ADDRESS_ID in .env


def _build_health_system(name: str, address_id: str) -> SystemMessage:
    """Build the inner-agent system prompt with per-user name and address ID."""
    return SystemMessage(content=f"""\
You are the Health Agent for {name}'s Swiggy Bot.
Your sole job: find exactly 3 vegetarian, high-protein dishes near the user's location.

CRITICAL RULE: Every tool call MUST include addressId="{address_id}".
The API will reject every call without it. Do NOT omit it.

NON-NEGOTIABLE DIETARY RULES:
1. VEGETARIAN ONLY — no meat, fish, eggs, or meat-based gravies.
2. NO MUSHROOMS — not in the dish, not as a topping, not in any sauce.
3. Only restaurants rated 4.0 or higher.
4. HIGH-PROTEIN priority: Paneer Tikka, Soya Chaap, Dal Makhani, Rajma,
   Chhole, Tofu dishes, Paneer Bhurji. Rank by protein density.
5. LOW-SUGAR preference: skip desserts, sweet lassi, or sugary mains.

STEP-BY-STEP WORKFLOW:
Step 1 → Call search_restaurants(addressId="{address_id}", query="high protein veg")
Step 2 → Discard any restaurant with rating < 4.0. Keep the top 3 by rating.
Step 3 → For each restaurant call get_restaurant_menu(addressId="{address_id}", restaurantId=<id>).
Step 4 → From each menu pick the single best high-protein veg dish (no mushrooms).
Step 5 → Rank: protein content > rating > price (lower better).

MANDATORY OUTPUT FORMAT — end with EXACTLY this block:

HEALTH_RECOMMENDATIONS:
1. [Restaurant Name] | [restaurantId] | [Dish Name] | [itemId] | Rs.[Price] | [Why: protein source]
2. [Restaurant Name] | [restaurantId] | [Dish Name] | [itemId] | Rs.[Price] | [Why: protein source]
3. [Restaurant Name] | [restaurantId] | [Dish Name] | [itemId] | Rs.[Price] | [Why: protein source]
""")


# ──────────────────────────────────────────────────────────────────────────────
# Health Agent Node
# ──────────────────────────────────────────────────────────────────────────────

async def health_agent_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Called by the Supervisor whenever the user wants food recommendations.

    Lifecycle:
    1. Extracts the user's latest request from shared state.
    2. Opens a live connection to the swiggyFood MCP server.
    3. Spins up a ReAct inner agent armed with MCP tools + dietary rules.
    4. Inner agent autonomously calls search_restaurants → get_restaurant_menu,
       filters results, and produces a structured shortlist.
    5. Parses the HEALTH_RECOMMENDATIONS block and packages it as an AIMessage.
    6. Returns Command(goto="supervisor") so the Supervisor can show the user
       the picks and decide whether to send them to the Deal Agent next.
    """
    persona     = state.get("user_persona") or {}
    name        = persona.get("name", "the user")
    address_id  = persona.get("address_id") or _ADDRESS_ID or ""
    location    = persona.get("location", "their area")

    user_request = _latest_human_message(state)

    task = HumanMessage(content=(
        f"User request: '{user_request}'\n\n"
        f"Search for the best high-protein vegetarian dishes available right now "
        f"near {location}. Apply all dietary and rating rules from your "
        "instructions and return exactly 3 recommendations in the required format."
    ))

    try:
        client = MultiServerMCPClient(_MCP_CONFIG)
        tools = await client.get_tools()

        inner_agent = create_react_agent(
            model=_llm,
            tools=tools,
            prompt=_build_health_system(name, address_id),
        )

        result = await inner_agent.ainvoke({"messages": [task]})

        recommendations = _extract_recommendations(result["messages"])
        reply_text = (
            "Health Agent done. Top 3 high-protein veg picks from Viman Nagar:\n\n"
            f"{recommendations}\n\n"
            "Handing back to Supervisor — they'll lock in the best deal next."
        )

    except Exception as exc:  # noqa: BLE001
        print(f"\n[Health Agent ERROR] {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        reply_text = (
            f"Health Agent error — {type(exc).__name__}: {exc}\n"
            "Supervisor: proceed with whatever data is available."
        )

    return Command(
        goto="supervisor",
        update={
            "messages": [AIMessage(content=reply_text)],
            "next_agent": "supervisor",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _latest_human_message(state: State) -> str:
    """Return the content of the most recent HumanMessage in the conversation."""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


def _extract_recommendations(messages: list) -> str:
    """
    Walk the inner agent's message list in reverse and return the first
    HEALTH_RECOMMENDATIONS block found.

    Falls back to the raw last AIMessage content if the block is absent
    (e.g., the LLM hit a tool error and explained it in prose).
    """
    fallback = ""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        match = re.search(r"(HEALTH_RECOMMENDATIONS:.+)", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        if content.strip() and not fallback:
            fallback = content.strip()
    return fallback or "No recommendations found — the menu data may be unavailable."
