"""
agents/order_agent.py

Order Agent — cart builder and pre-checkout dry-run.
Uses the addressId, restaurantId, and itemId captured by health/deal agents
to assemble the cart and show the final order preview.
Does NOT call place_food_order (simulate mode).
"""

import os
import re
import traceback
import uuid
from typing import Literal

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from langgraph.prebuilt.tool_node import ToolNode
from agents.supervisor import State, _build_llm, _content_text


# ─────────────────────────────────────────────────────────────────────────────
# MCP helpers
# ─────────────────────────────────────────────────────────────────────────────

_SESSION_TOKEN = os.getenv("SWIGGY_SESSION_TOKEN", "")
_ADDRESS_ID    = os.getenv("SWIGGY_ADDRESS_ID", "")  # set SWIGGY_ADDRESS_ID in .env


def _mcp_headers() -> dict[str, str]:
    h: dict[str, str] = {}
    if _SESSION_TOKEN:
        h["Authorization"] = f"Bearer {_SESSION_TOKEN}"
    h["X-Mcp-Client-Session-Id"] = str(uuid.uuid4())
    return h


def _no_ssl_factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(
        headers=headers or {},
        timeout=timeout or httpx.Timeout(30.0, read=300.0),
        auth=auth, verify=True, follow_redirects=True,
    )


_MCP_CONFIG = {
    "swiggyFood": {
        "url": os.getenv("SWIGGY_FOOD_MCP_URL", ""),  # set SWIGGY_FOOD_MCP_URL in .env
        "transport": "streamable_http",
        "headers": _mcp_headers(),
        "httpx_client_factory": _no_ssl_factory,
    }
}

_llm = _build_llm()

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────────────────────

_ORDER_SYSTEM = SystemMessage(content=f"""\
You are the Order Agent for Sambhav's Swiggy Bot.
Your job: assemble the cart and produce an order preview. Do NOT call place_food_order.

CRITICAL: Pass addressId="{_ADDRESS_ID}" to EVERY tool call or it will fail.

STEP-BY-STEP WORKFLOW:
Step 1 → Call flush_food_cart(addressId="{_ADDRESS_ID}") to clear stale items.

Step 2 → If restaurantId and itemId are provided in the task, skip this step.
          Otherwise call search_restaurants(addressId="{_ADDRESS_ID}", query=<restaurant name>)
          then search_menu(addressId="{_ADDRESS_ID}", restaurantId=<id>, query=<dish name>)
          to resolve the IDs.

Step 3 → Call update_food_cart(addressId="{_ADDRESS_ID}", restaurantId=<id>,
          items=[{{"itemId": <id>, "quantity": 1}}])

Step 4 → COUPON HANDLING (very important):
          - If the task says "SKIP COUPON" → skip this step entirely.
          - If a coupon code is provided, call
            apply_food_coupon(addressId="{_ADDRESS_ID}", couponCode=<code>)
          - If apply_food_coupon returns ANY error (expired, not found, invalid):
            * Do NOT retry or use a different coupon.
            * Stop immediately and output COUPON_FAILED block (see format below).
            * Do NOT output ORDER_SUMMARY.

Step 5 → Call get_food_cart(addressId="{_ADDRESS_ID}") to read the final cart.

Step 6 → Output ORDER_SUMMARY block. Do NOT call place_food_order.

━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — use exactly ONE of these two blocks:
━━━━━━━━━━━━━━━━━━━━

If coupon failed:

COUPON_FAILED:
Coupon  : [code]
Reason  : [error message from the tool — e.g. "Coupon does not exist", "expired"]
Cart    : [dish name] from [restaurant] — Rs.[MRP]
Message : Coupon could not be applied. Shall I proceed without it?

If cart built successfully (no coupon, or coupon applied):

ORDER_SUMMARY:
Restaurant   : [name]
Dish         : [item name]
Address      : Viman Nagar, Pune
MRP          : Rs.[amount]
Coupon       : [code or NONE]
Discount     : Rs.[amount]
PAYABLE      : Rs.[amount]
Est. Delivery: [X mins]
Status       : DRY-RUN COMPLETE — not placed yet
""")


# ─────────────────────────────────────────────────────────────────────────────
# Order Agent Node
# ─────────────────────────────────────────────────────────────────────────────

async def order_agent_node(state: State) -> Command[Literal["supervisor"]]:
    task_text = _build_task(state)
    task = HumanMessage(content=task_text)
    print(f"\n[Order Agent] Task:\n{task_text}\n", flush=True)

    try:
        client = MultiServerMCPClient(_MCP_CONFIG)
        tools = await client.get_tools()
        print(f"[Order Agent] Tools available: {[t.name for t in tools]}", flush=True)

        # create_react_agent doesn't accept handle_tool_errors directly in this
        # version. Build a ToolNode with handle_tool_errors=True and pass it
        # as the tools argument. This converts ToolException (thrown by MCP
        # tools on API errors like "Coupon not eligible") into a ToolMessage
        # so the LLM sees the error and outputs COUPON_FAILED instead of crashing.
        tool_node = ToolNode(tools, handle_tool_errors=True)
        inner_agent = create_react_agent(
            model=_llm,
            tools=tool_node,
            prompt=_ORDER_SYSTEM,
        )
        result = await inner_agent.ainvoke({"messages": [task]})

        raw = _extract_order_summary(result["messages"])
        if raw.startswith("COUPON_FAILED"):
            reply_text = f"Order Agent — coupon issue detected:\n\n{raw}"
        else:
            reply_text = (
                "Order Agent dry-run complete. Here's your order preview:\n\n"
                f"{raw}\n\n"
                "Handing back to Supervisor."
            )

    except Exception as exc:
        exc_str = _flatten_exc(exc)
        if _is_coupon_error(exc_str):
            coupon_match = re.search(r"Coupon code:\s*(\w+)", task_text)
            coupon_code = coupon_match.group(1) if coupon_match else "UNKNOWN"
            reason = exc_str.split("\n")[0].strip()
            reply_text = (
                "Order Agent — coupon issue detected:\n\n"
                "COUPON_FAILED:\n"
                f"Coupon  : {coupon_code}\n"
                f"Reason  : {reason}\n"
                "Message : Coupon nahi laga. Bina coupon ke order karna chahoge?"
            )
        else:
            print(f"\n[Order Agent ERROR] {type(exc).__name__}: {exc}", flush=True)
            traceback.print_exc()
            reply_text = (
                f"Order Agent error — {type(exc).__name__}: {exc}\n"
                "Supervisor: inform the user the cart could not be built."
            )

    return Command(
        goto="supervisor",
        update={"messages": [AIMessage(content=reply_text)], "next_agent": "supervisor"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_task(state: State) -> str:
    """Build the task string from cart_summary or message history."""
    cart = state.get("cart_summary") or {}
    lines = ["Build the cart for this order:"]

    restaurant_id   = cart.get("restaurant_id", "")
    restaurant_name = cart.get("restaurant_name", "")
    item_id         = cart.get("item_id", "")
    item_name       = cart.get("item_name", "")
    coupon_code     = cart.get("coupon_code", "")

    # Parse from HEALTH_RECOMMENDATIONS if cart is sparse
    if not item_name or not restaurant_name:
        parsed = _parse_health_rec(state)
        restaurant_id   = restaurant_id   or parsed.get("restaurant_id", "")
        restaurant_name = restaurant_name or parsed.get("restaurant_name", "")
        item_id         = item_id         or parsed.get("item_id", "")
        item_name       = item_name       or parsed.get("item_name", "")

    # Parse coupon — but skip if it already failed on a previous run
    if not coupon_code:
        coupon_code = _parse_coupon(state)
    coupon_previously_failed = _coupon_failed_in_history(state)

    if restaurant_id:
        lines.append(f"Restaurant ID: {restaurant_id} ({restaurant_name})")
    else:
        lines.append(f"Restaurant: {restaurant_name or 'unknown — search by name'}")

    if item_id:
        lines.append(f"Item ID: {item_id} ({item_name})")
    else:
        lines.append(f"Dish: {item_name or 'unknown — use search_menu to find it'}")

    if coupon_previously_failed:
        lines.append("SKIP COUPON — coupon already failed on previous attempt, user confirmed to proceed without it")
    elif coupon_code:
        lines.append(f"Coupon code: {coupon_code}")

    lines.append(f"Address ID: {_ADDRESS_ID} (Viman Nagar, Pune — use for every tool call)")
    return "\n".join(lines)


def _coupon_failed_in_history(state: State) -> bool:
    """Return True if any message in history indicates a coupon failure.

    Checks for both the structured COUPON_FAILED block AND raw error strings
    from the generic exception handler (which fires when the error keyword
    wasn't in _COUPON_ERROR_KEYWORDS on a previous run).
    """
    for msg in state["messages"]:
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        if "COUPON_FAILED" in content:
            return True
        if _is_coupon_error(content):
            return True
    return False


def _flatten_exc(exc: Exception) -> str:
    """Flatten ExceptionGroup or plain exception into a single string."""
    if isinstance(exc, ExceptionGroup):
        parts = [_flatten_exc(e) for e in exc.exceptions]
        return " | ".join(parts)
    return str(exc)


_COUPON_ERROR_KEYWORDS = (
    "coupon does not exist",
    "coupon expired",
    "coupon not valid",
    "invalid coupon",
    "coupon not found",
    "coupon not applicable",
    "coupon not available",
    "no such coupon",
    "not eligible",
    "coupon is not eligible",
    "not applicable to",
    "cannot be applied",
    "coupon cannot",
)


def _is_coupon_error(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _COUPON_ERROR_KEYWORDS)


def _parse_health_rec(state: State) -> dict:
    """Extract the CHOSEN option's restaurantId, itemId, names from HEALTH_RECOMMENDATIONS."""
    # Find which option the user picked (look for a supervisor message asking to confirm
    # and the subsequent user message with the choice)
    chosen_idx = 1  # default to option 1
    for msg in state["messages"]:
        if hasattr(msg, "type") and msg.type == "human":
            content = str(msg.content).lower()
            for n in ("1", "2", "3", "one", "two", "three", "first", "second", "third"):
                if n in content:
                    chosen_idx = {"1": 1, "one": 1, "first": 1,
                                  "2": 2, "two": 2, "second": 2,
                                  "3": 3, "three": 3, "third": 3}.get(n, 1)
                    break

    # Find the health rec block and extract the chosen line
    for msg in reversed(state["messages"]):
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        block_match = re.search(r"HEALTH_RECOMMENDATIONS:(.*)", content, re.DOTALL)
        if not block_match:
            continue
        block = block_match.group(1)
        # New format: Restaurant | restaurantId | Dish | itemId | Rs.Price | Why
        line_pattern = rf"{chosen_idx}\.\s*(.+?)\s*\|\s*(\S+)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|\s*(?:Rs\.|₹)(\d+)"
        m = re.search(line_pattern, block)
        if m:
            return {
                "restaurant_name": m.group(1).strip(),
                "restaurant_id":   m.group(2).strip(),
                "item_name":       m.group(3).strip(),
                "item_id":         m.group(4).strip(),
                "price":           int(m.group(5)),
            }
        # Fallback: old format without IDs
        m2 = re.search(rf"{chosen_idx}\.\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(?:Rs\.|₹)(\d+)", block)
        if m2:
            return {"restaurant_name": m2.group(1).strip(), "item_name": m2.group(2).strip()}
    return {}


def _parse_coupon(state: State) -> str:
    for msg in reversed(state["messages"]):
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        m = re.search(r"Best Coupon:\s*(\w+)\s*\|", content, re.IGNORECASE)
        if m and m.group(1).upper() != "NONE":
            return m.group(1)
    return ""


def _extract_order_summary(messages: list) -> str:
    """Return ORDER_SUMMARY or COUPON_FAILED block from the agent's final message."""
    fallback = ""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        # Check for ORDER_SUMMARY first
        m = re.search(r"(ORDER_SUMMARY:.+)", content, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Then check for COUPON_FAILED
        m2 = re.search(r"(COUPON_FAILED:.+)", content, re.DOTALL)
        if m2:
            return m2.group(1).strip()
        if content.strip() and not fallback:
            fallback = content.strip()
    return fallback or "Order summary unavailable."
