"""
agents/deal_agent.py

Deal Agent — coupon hunter and card-offer optimizer.
Connects to swiggyFood MCP, fetches every available coupon AND card/payment
offer for the selected restaurant in one call, identifies the HDFC Swiggy
Credit Card and SBI Cashback Credit Card offers specifically, computes the
optimal coupon + card combination, and hands the full deal breakdown back
to the Supervisor with an updated cart_summary.

NOTE — on 'get_payment_offers':
    There is no separate get_payment_offers tool on the swiggyFood MCP server.
    Card / bank offers are returned inside fetch_food_coupons under the
    'payment_offers' section of the response. This agent uses that single tool.

Inner agent workflow:
    get_addresses (auto-select Viman Nagar address)
        → fetch_food_coupons(restaurantId, addressId)
        → parse best_coupons + payment_offers sections
        → compute coupon_saving, HDFC saving, SBI saving
        → pick highest-value stackable combo
        → output DEAL_BREAKDOWN

Integration with supervisor.py:
    Replace the call_deal_agent stub with:
        from agents.deal_agent import deal_agent_node
        graph.add_node("deal_agent", deal_agent_node)
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


# ─────────────────────────────────────────────────────────────────────────────
# MCP Connection helpers
# ─────────────────────────────────────────────────────────────────────────────

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

from agents.supervisor import _build_llm  # noqa: E402

_llm = _build_llm()

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — injected as the inner ReAct agent's fixed context
# ─────────────────────────────────────────────────────────────────────────────

_DEAL_SYSTEM = SystemMessage(content="""\
You are the Deal Agent for Sambhav Mehta's Swiggy Bot.
Your sole job: find the maximum discount on the current order.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SAVED CARDS — CHECK THESE ONLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. HDFC Swiggy Credit Card
  2. SBI Cashback Credit Card

━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP-BY-STEP WORKFLOW
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1 — Call get_addresses.
           Do NOT wait for user confirmation — automatically pick the address
           that matches "Viman Nagar, Pune". Note its addressId.

Step 2 — Call fetch_food_coupons using:
             restaurantId  = the ID provided in the task (or find it via
                             search_restaurants if the task gives only a name)
             addressId     = the addressId from Step 1
           The response has THREE sections — process ALL of them:
             • best_coupons   → standard promo codes (discount_pct or flat_discount)
             • more_offers    → secondary promotions
             • payment_offers → bank / card cashback (HDFC, SBI, etc.)

Step 3 — Identify:
           BEST COUPON  → the code that produces the highest net rupee saving.
                          saving = min(MRP × discount_pct / 100, max_discount)
                                OR the flat_discount amount — whichever applies.
           HDFC OFFER   → the "HDFC Swiggy Credit Card" entry in payment_offers.
           SBI OFFER    → the "SBI Cashback Credit Card" entry in payment_offers.

Step 4 — Compute all combinations (use the MRP from the task context):
           coupon_saving    = from Step 3
           post_coupon      = MRP − coupon_saving
           hdfc_cashback    = min(post_coupon × hdfc_pct / 100, hdfc_max_cashback)
           sbi_cashback     = min(post_coupon × sbi_pct / 100, sbi_max_cashback)

           combo_with_hdfc  = coupon_saving + hdfc_cashback
           combo_with_sbi   = coupon_saving + sbi_cashback

           STACKING RULE: one coupon + one card offer is ALWAYS stackable on Swiggy.
                          Two coupons or two card offers are NEVER stackable.

Step 5 — Pick the combo that results in the LOWEST payable amount.
           payable = MRP − best_total_discount
           If no coupons and no card offers exist, payable = MRP.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
End your final response with EXACTLY this block and nothing after it:

DEAL_BREAKDOWN:
MRP: ₹[amount]
Best Coupon: [CODE or NONE] | [description or N/A] | Saves ₹[amount]
HDFC Swiggy Card: [description or N/A] | Cashback ₹[amount]
SBI Cashback Card: [description or N/A] | Cashback ₹[amount]
Best Combo: [COUPON_CODE + HDFC Swiggy Card / COUPON_CODE + SBI Cashback Card / best single option]
Total Discount: ₹[amount]
PAYABLE: ₹[amount]
""")


# ─────────────────────────────────────────────────────────────────────────────
# Deal Agent Node
# ─────────────────────────────────────────────────────────────────────────────

async def deal_agent_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Called by the Supervisor once a food choice is locked in.

    Lifecycle:
    1. Reads cart_summary (restaurant_id, total_mrp) and fills any gaps by
       parsing the Health Agent's HEALTH_RECOMMENDATIONS from message history.
    2. Opens a live connection to swiggyFood MCP.
    3. Inner ReAct agent calls get_addresses → fetch_food_coupons, processes
       all three offer sections (best_coupons, more_offers, payment_offers),
       finds HDFC + SBI card offers specifically, and computes savings.
    4. Parses the DEAL_BREAKDOWN block and enriches cart_summary with every
       discount field so the Supervisor has exact numbers for user confirmation.
    5. Returns Command(goto="supervisor").
    """
    task = HumanMessage(content=_build_context(state))

    try:
        # v0.2+ API: no context manager — call get_tools() directly.
        client = MultiServerMCPClient(_MCP_CONFIG)
        tools = await client.get_tools()

        inner_agent = create_react_agent(
            model=_llm,
            tools=tools,
            prompt=_DEAL_SYSTEM,
        )

        result = await inner_agent.ainvoke({"messages": [task]})

        deal_text = _extract_deal_breakdown(result["messages"])
        updated_cart = _parse_cart_update(deal_text, state.get("cart_summary") or {})

        reply_text = (
            "Deal Agent locked in the best offer. Full breakdown:\n\n"
            f"{deal_text}\n\n"
            "Back to Supervisor — waiting on your final approval."
        )

    except Exception as exc:  # noqa: BLE001
        print(f"\n[Deal Agent ERROR] {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        reply_text = (
            f"Deal Agent error — {type(exc).__name__}: {exc}\n"
            "Supervisor: present best available info to the user."
        )
        updated_cart = state.get("cart_summary") or {}

    return Command(
        goto="supervisor",
        update={
            "messages": [AIMessage(content=reply_text)],
            "next_agent": "supervisor",
            "cart_summary": updated_cart,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Context builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_context(state: State) -> str:
    """
    Compose the task string for the inner agent.

    Priority order for each field:
      1. cart_summary (populated by Health Agent if it stored the data)
      2. Parsed from the HEALTH_RECOMMENDATIONS block in message history
      3. Generic fallback instruction to discover via MCP tools
    """
    cart = state.get("cart_summary") or {}
    restaurant_id   = cart.get("restaurant_id", "")
    restaurant_name = cart.get("restaurant_name", "")
    mrp             = cart.get("total_mrp", 0)

    # Fill gaps from Health Agent's structured recommendation
    health = _extract_health_rec(state)
    if not restaurant_name:
        restaurant_name = health.get("restaurant", "")
    if not mrp:
        mrp = health.get("price", 0)

    lines = ["Find the best deal for this Swiggy food order."]

    if restaurant_id:
        lines.append(f"Restaurant ID: {restaurant_id}")
    elif restaurant_name:
        lines.append(
            f"Restaurant name: '{restaurant_name}' — use search_restaurants "
            "to resolve its ID if fetch_food_coupons requires it."
        )
    else:
        lines.append(
            "Restaurant not yet identified — search Viman Nagar, Pune to find it."
        )

    lines.append(f"Order MRP: ₹{mrp}" if mrp else "Order MRP: use the price from the menu.")
    lines.append("Delivery location: Viman Nagar, Pune.")
    lines.append(
        "Specifically find HDFC Swiggy Credit Card and SBI Cashback Credit Card "
        "entries in the payment_offers section of the fetch_food_coupons response."
    )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_health_rec(state: State) -> dict:
    """
    Scan message history in reverse for a HEALTH_RECOMMENDATIONS block.
    Returns the first entry's restaurant name and price, or an empty dict.
    """
    for msg in reversed(state["messages"]):
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        block = re.search(r"HEALTH_RECOMMENDATIONS:(.+?)(?=\n\n|\Z)", content, re.DOTALL)
        if not block:
            continue
        # Format: 1. [Restaurant] | [Dish] | ₹[Price] | [reason]
        first = re.search(
            r"1\.\s*(.+?)\s*\|\s*.+?\s*\|\s*₹(\d+)",
            block.group(1),
        )
        if first:
            return {
                "restaurant": first.group(1).strip(),
                "price":      int(first.group(2)),
            }
    return {}


def _extract_deal_breakdown(messages: list) -> str:
    """
    Walk the inner agent's message list in reverse, return the first
    DEAL_BREAKDOWN block found.
    Falls back to raw last-AIMessage content so the Supervisor always
    receives something actionable rather than silence.
    """
    fallback = ""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = _content_text(msg.content)
        match = re.search(r"(DEAL_BREAKDOWN:.+)", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        if content.strip() and not fallback:
            fallback = content.strip()
    return fallback or "No deal breakdown produced — MCP server may be unavailable."


def _parse_cart_update(breakdown: str, cart: dict) -> dict:
    """
    Extract every numeric and text field from DEAL_BREAKDOWN and merge
    into cart_summary. All pre-existing keys (items, restaurant_id, etc.)
    are preserved via dict unpacking.

    New / updated keys written to cart_summary:
        total_mrp, coupon_code, coupon_saving,
        hdfc_cashback, sbi_cashback,
        best_combo, total_discount, payable
    """

    def _rupees(pattern: str) -> int:
        m = re.search(pattern, breakdown, re.IGNORECASE)
        return int(m.group(1).replace(",", "")) if m else 0

    def _text(pattern: str) -> str:
        m = re.search(pattern, breakdown, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    mrp            = _rupees(r"MRP:\s*₹([\d,]+)")
    total_discount = _rupees(r"Total Discount:\s*₹([\d,]+)")
    payable        = _rupees(r"PAYABLE:\s*₹([\d,]+)")
    coupon_saving  = _rupees(r"Best Coupon:.*?Saves\s*₹([\d,]+)")
    hdfc_cashback  = _rupees(r"HDFC Swiggy Card:.*?Cashback\s*₹([\d,]+)")
    sbi_cashback   = _rupees(r"SBI Cashback Card:.*?Cashback\s*₹([\d,]+)")

    coupon_match = re.search(r"Best Coupon:\s*(\w+)\s*\|", breakdown, re.IGNORECASE)
    coupon_code = coupon_match.group(1) if coupon_match else ""
    if coupon_code.upper() == "NONE":
        coupon_code = ""

    best_combo = _text(r"Best Combo:\s*(.+)")

    # Derive payable from the other two fields if the LLM omitted it
    if mrp and total_discount and not payable:
        payable = mrp - total_discount

    return {
        **cart,                                         # preserve existing cart keys
        "total_mrp":      mrp or cart.get("total_mrp", 0),
        "coupon_code":    coupon_code,
        "coupon_saving":  coupon_saving,
        "hdfc_cashback":  hdfc_cashback,
        "sbi_cashback":   sbi_cashback,
        "best_combo":     best_combo,
        "total_discount": total_discount,
        "payable":        payable,
    }
