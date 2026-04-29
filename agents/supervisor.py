"""
agents/supervisor.py

Master Supervisor Agent — the central orchestrator for the Swiggy Bot.
Loads the user persona, interprets every request through that lens, and
routes work between the Health Agent (nutritional filtering) and the
Deal Agent (coupons / card offers). Conversation + cart state persist
across sessions via LangGraph's MemorySaver checkpointer.

Hand-off logic at a glance
──────────────────────────
  START
    │
    ▼
  load_persona ──► supervisor
                       │
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
   health_agent    deal_agent        END
         │             │
         └──────┬───────┘
                ▼
           supervisor  (loops until END)
"""

import asyncio
import os
import re
import json
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command


# ──────────────────────────────────────────────────────────────────────────────
# 1. Shared State
# ──────────────────────────────────────────────────────────────────────────────

class State(TypedDict):
    # Full conversation history — add_messages reducer appends, never replaces.
    messages: Annotated[list[BaseMessage], add_messages]

    # Parsed contents of persona/profile.md, loaded once per session.
    user_persona: dict

    # Tracks which specialist will act next (informational, used for debugging).
    next_agent: str

    # Accumulates cart items across multiple agent turns.
    # Schema: {"items": [...], "total_mrp": 0, "discount": 0, "payable": 0}
    cart_summary: dict


# ──────────────────────────────────────────────────────────────────────────────
# 2. Persona Loader
# ──────────────────────────────────────────────────────────────────────────────

_PROFILE_PATH = Path(__file__).parent.parent / "persona" / "profile.md"


def load_persona(state: State) -> dict:
    """
    Reads persona/profile.md and injects structured data into state.
    Runs every invocation but is a no-op after the first successful load
    (MemorySaver preserves user_persona across sessions).
    """
    if state.get("user_persona"):
        return {}  # already loaded — let MemorySaver carry it forward

    try:
        raw = _PROFILE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = "No persona file found."

    def _extract(pattern: str) -> str:
        m = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""

    persona = {
        "raw": raw,
        "name":         _extract(r"User Persona:\s*\[(.+?)\]"),
        "location":     _extract(r"\*\*Location:\*\*\s*(.+)"),
        "diet_goals":   _extract(r"\*\*Dietary Goals:\*\*\s*(.+)"),
        "restrictions": _extract(r"\*\*Restrictions:\*\*\s*(.+)"),
        "preferences":  _extract(r"\*\*Preferences:\*\*\s*(.+)"),
        "budget_wkday": _extract(r"Weekdays:\s*(.+)"),
        "budget_wknd":  _extract(r"Weekends:\s*(.+)"),
    }

    return {"user_persona": persona, "cart_summary": {"items": [], "total_mrp": 0, "discount": 0, "payable": 0}}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Supervisor Node
# ──────────────────────────────────────────────────────────────────────────────

_MODEL = os.getenv("SWIGGY_BOT_MODEL", "claude-sonnet-4-6")

_llm = ChatAnthropic(model=_MODEL, temperature=0.4)

_SUPERVISOR_SYSTEM = """\
You are the Swiggy Bot Supervisor — the sharp, no-nonsense central brain \
of this ordering system. Your vibe? Pure Seedhe Maut energy: fast, direct, \
zero fluff, confident swagger. Get things done, say exactly what needs to be \
said, and keep it real with the user at all times.

You are operating for: {name}
Here is everything you know about them:
{persona_raw}

──────────────────────────────────────────────────────────────────
ABSOLUTE RULES — break any of these and the whole system fails:
1. VEGETARIAN ONLY. Never suggest, mention, or allow non-veg food.
2. NO MUSHROOMS. Not even a garnish.
3. Restaurants must be rated 4.0 stars or higher. No exceptions.
4. Always check for the best coupon / card offer before any order is final.
5. Weekday meals: stay under ₹500. Weekend fine-dining via Dineout: up to ₹1500+.
6. High-protein, low-sugar choices must be prioritised when filtering food.
──────────────────────────────────────────────────────────────────

YOUR WORKFLOW:
• When the user wants food → route to Health Agent first for nutritional filtering.
• Once food is selected → route to Deal Agent to find and apply the best offer.
• After the deal is confirmed by the user → finalize and route to END.
• You can loop: Health Agent → you → Deal Agent → you → END.

ROUTING OUTPUT — you MUST end every response with this exact JSON block:
```json
{{"next": "<health_agent | deal_agent | END>"}}
```

Routing logic:
- "health_agent" : user wants food recommendations / the menu needs dietary filtering
- "deal_agent"   : food choice is locked, now hunt for the best discount / card offer
- "END"          : order placed, or user explicitly ends the session

Keep responses tight and punchy. Ek dum solid — let's go.
"""


def supervisor_node(state: State) -> Command[Literal["health_agent", "deal_agent", "__end__"]]:
    """
    Core LLM node. Reads the full conversation + persona, decides the next
    action, and returns a Command that moves the graph to the right specialist
    or terminates the session.

    The supervisor always appends its reply to messages before routing, so
    the specialist receiving control sees the full updated context.
    """
    persona = state.get("user_persona") or {}
    system_prompt = _SUPERVISOR_SYSTEM.format(
        name=persona.get("name", "the user"),
        persona_raw=persona.get("raw", "No persona loaded."),
    )

    response = _llm.invoke(
        [SystemMessage(content=system_prompt)] + state["messages"]
    )

    next_node = _parse_routing(str(response.content))

    return Command(
        goto=next_node if next_node != "END" else END,
        update={
            "messages": [response],
            "next_agent": next_node,
        },
    )


def _parse_routing(content: str) -> str:
    """
    Extract the supervisor's routing decision from its JSON block.
    Falls back to END if the block is missing or malformed, so the
    graph never hangs in an indeterminate state.
    """
    match = re.search(
        r"```json\s*\{[^}]*\"next\"\s*:\s*\"(\w+)\"[^}]*\}\s*```",
        content,
        re.DOTALL,
    )
    if match:
        decision = match.group(1).lower()
        if decision in ("health_agent", "deal_agent"):
            return decision
    return "END"


# ──────────────────────────────────────────────────────────────────────────────
# 4. Specialist Stubs
#    Real implementations live in agents/health_agent.py and agents/deal_agent.py.
#    These stubs keep the graph runnable while those files are being built.
#    Each stub always hands control back to the supervisor with a status message.
# ──────────────────────────────────────────────────────────────────────────────

def call_health_agent(state: State) -> Command[Literal["supervisor"]]:
    """
    Stub: Health Agent placeholder.

    Will be replaced by the real agent that:
      - Calls search_restaurants / get_restaurant_menu via MCP
      - Filters by vegetarian, 4.0+ stars, no mushrooms
      - Ranks dishes by protein content, flags high-sugar items
      - Returns a curated shortlist with macros to the Supervisor
    """
    stub_reply = AIMessage(content=(
        "[Health Agent] Running dietary filters — veg-only, 4.0+ stars, "
        "no mushrooms, high-protein priority. Shortlisted options are on "
        "their way back to Supervisor."
    ))
    return Command(
        goto="supervisor",
        update={"messages": [stub_reply], "next_agent": "supervisor"},
    )


def call_deal_agent(state: State) -> Command[Literal["supervisor"]]:
    """
    Stub: Deal Agent placeholder.

    Will be replaced by the real agent that:
      - Calls fetch_food_coupons / apply_food_coupon via MCP
      - Checks card-linked offers against the user's saved cards
      - Selects the highest-value discount automatically
      - Updates cart_summary with the final payable amount
      - Returns the deal breakdown to the Supervisor for user confirmation
    """
    stub_reply = AIMessage(content=(
        "[Deal Agent] Scanning all active coupons and card offers. "
        "Best discount incoming — Supervisor gets the full breakdown next."
    ))
    return Command(
        goto="supervisor",
        update={"messages": [stub_reply], "next_agent": "supervisor"},
    )


# ──────────────────────────────────────────────────────────────────────────────
# 5. Graph Construction
# ──────────────────────────────────────────────────────────────────────────────

def build_graph():
    """
    Wires all nodes into a StateGraph and compiles it with MemorySaver so
    that conversation history, the loaded persona, and the cart persist
    across separate chat sessions (keyed by thread_id in config).
    """
    graph = StateGraph(State)

    # Lazy import avoids the circular reference:
    # health_agent.py imports State from this module, so we can't import it
    # at the top level — deferring to build_graph() breaks the cycle cleanly.
    # Lazy imports break the circular reference: both agents import State from
    # this module, so top-level imports in both directions would deadlock.
    from agents.health_agent import health_agent_node  # noqa: PLC0415
    from agents.deal_agent import deal_agent_node      # noqa: PLC0415

    # Register nodes
    graph.add_node("load_persona", load_persona)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("health_agent", health_agent_node)  # real implementation
    graph.add_node("deal_agent", deal_agent_node)      # real implementation

    # Static edges: entry point always loads persona, then hands to supervisor.
    # Specialist → supervisor routing is declared via Command return types above.
    graph.add_edge(START, "load_persona")
    graph.add_edge("load_persona", "supervisor")

    return graph.compile(checkpointer=MemorySaver())


# Module-level singleton — import this from other files.
swiggy_graph = build_graph()


# ──────────────────────────────────────────────────────────────────────────────
# 6. CLI Runner  (local smoke-test only)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uuid

    # A stable thread_id = a persistent session; a new uuid = a fresh one.
    thread_id = os.getenv("SWIGGY_THREAD_ID", str(uuid.uuid4()))
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n🎤  Swiggy Bot live  |  thread: {thread_id}")
    print("    Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBot: Chal bhai, later. ✌️")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Bot: Chal bhai, later. ✌️")
            break

        # ainvoke is required because health_agent_node is async (MCP client).
        result = asyncio.run(
            swiggy_graph.ainvoke(
                {"messages": [HumanMessage(content=user_input)]},
                config=config,
            )
        )

        # Print the last supervisor reply (skip internal agent status lines).
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and not msg.content.startswith("["):
                print(f"\nBot: {msg.content}\n")
                break
