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
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from agents.supervisor import State


# ──────────────────────────────────────────────────────────────────────────────
# MCP Connection — mirrors the swiggyFood entry in .vscode/mcp.json
# ──────────────────────────────────────────────────────────────────────────────

_MCP_CONFIG = {
    "swiggyFood": {
        "url": os.getenv("SWIGGY_FOOD_MCP_URL", "https://mcp.swiggy.com/food"),
        # streamable_http is the modern MCP HTTP transport (replaces SSE).
        # If the server only supports SSE, change this to "sse".
        "transport": "streamable_http",
    }
}


# ──────────────────────────────────────────────────────────────────────────────
# LLM
# ──────────────────────────────────────────────────────────────────────────────

_MODEL = os.getenv("SWIGGY_BOT_MODEL", "claude-sonnet-4-6")

# Lower temperature → more deterministic tool use and consistent filtering.
_llm = ChatAnthropic(model=_MODEL, temperature=0.2)


# ──────────────────────────────────────────────────────────────────────────────
# System Prompt for the inner ReAct agent
# All dietary, rating, and location rules are encoded here so the inner
# agent never needs to be told twice.
# ──────────────────────────────────────────────────────────────────────────────

_HEALTH_SYSTEM = SystemMessage(content="""\
You are the Health Agent for Sambhav Mehta's Swiggy Bot.
Your sole job: find exactly 3 vegetarian, high-protein dishes from Viman Nagar, Pune.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NON-NEGOTIABLE DIETARY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. VEGETARIAN ONLY — absolutely no meat, fish, eggs, or meat-based gravies.
2. NO MUSHROOMS — not in the dish, not as a topping, not in any sauce.
3. Only restaurants rated 4.0 ★ or higher. Filter out anything below.
4. HIGH-PROTEIN priority: Paneer Tikka, Soya Chaap, Dal Makhani, Rajma,
   Chhole, Tofu dishes, Paneer Bhurji, etc. Rank by protein density.
5. LOW-SUGAR preference: skip desserts, sweet lassi, or sugary mains.
6. Location: Viman Nagar, Pune — only pull restaurants in this area.

━━━━━━━━━━━━━━━━━━━
STEP-BY-STEP WORKFLOW
━━━━━━━━━━━━━━━━━━━
Step 1 → Call search_restaurants with location = "Viman Nagar, Pune".
          Request vegetarian filter if the tool supports it.
Step 2 → Discard any restaurant with rating < 4.0. Keep the top 3 by rating.
Step 3 → For each kept restaurant, call get_restaurant_menu (or search_menu)
          to retrieve available dishes.
Step 4 → From each menu, identify high-protein vegetarian dishes.
          Immediately discard anything containing mushrooms.
Step 5 → Pick the single best dish from each restaurant (3 dishes total).
          Rank by: protein content > rating > price (lower is better).

━━━━━━━━━━━━━━━━━━━━
MANDATORY OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━
End your final response with EXACTLY this block and nothing after it:

HEALTH_RECOMMENDATIONS:
1. [Restaurant Name] | [Dish Name] | ₹[Price] | [Why it fits: protein source, macros]
2. [Restaurant Name] | [Dish Name] | ₹[Price] | [Why it fits: protein source, macros]
3. [Restaurant Name] | [Dish Name] | ₹[Price] | [Why it fits: protein source, macros]
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
    # Pull the most recent human message as the task context for the inner agent
    user_request = _latest_human_message(state)

    task = HumanMessage(content=(
        f"User request: '{user_request}'\n\n"
        "Search for the best high-protein vegetarian dishes available right now "
        "in Viman Nagar, Pune. Apply all dietary and rating rules from your "
        "instructions and return exactly 3 recommendations in the required format."
    ))

    try:
        async with MultiServerMCPClient(_MCP_CONFIG) as mcp:
            tools = mcp.get_tools()

            # Inner ReAct agent: reasons over MCP tools step by step until it
            # reaches a final answer. The dietary system prompt is injected via
            # the `prompt` parameter so it's the very first context the LLM sees.
            inner_agent = create_react_agent(
                model=_llm,
                tools=tools,
                prompt=_HEALTH_SYSTEM,
            )

            result = await inner_agent.ainvoke({"messages": [task]})

        recommendations = _extract_recommendations(result["messages"])
        reply_text = (
            "Health Agent done. Top 3 high-protein veg picks from Viman Nagar:\n\n"
            f"{recommendations}\n\n"
            "Handing back to Supervisor — they'll lock in the best deal next."
        )

    except Exception as exc:  # noqa: BLE001
        # Graceful degradation: surface the error to the Supervisor so it can
        # inform the user rather than silently hanging.
        reply_text = (
            f"[Health Agent] Could not reach swiggyFood MCP server: {exc}\n"
            "Please check connectivity or try again."
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
        content = str(msg.content)
        match = re.search(r"(HEALTH_RECOMMENDATIONS:.+)", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        if content.strip() and not fallback:
            fallback = content.strip()
    return fallback or "No recommendations found — the menu data may be unavailable."
