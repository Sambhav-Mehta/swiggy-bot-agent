# Swiggy Bot

A multi-agent AI food-ordering assistant for Swiggy. Users chat in natural
language (Hinglish, with a deliberately blunt "Seedhe Maut" personality) and a
team of specialist LLM agents finds food matching their dietary profile, hunts
for the best coupon + card-offer combination, and assembles the order — all
through a streaming chat UI.

Ordering currently runs in **simulation mode**: the cart is built and priced for
real via the Swiggy connector, but the final `place_food_order` call is not
made. The bot shows a "SIMULATION COMPLETE" confirmation instead.

---

## What it does

- **Health-aware food search** — finds restaurants near the user, filters
  strictly to vegetarian, 4.0★+, no mushrooms, and ranks dishes by protein, then
  returns three recommendations.
- **Deal optimization** — fetches every available coupon and card offer
  (e.g. HDFC Swiggy, SBI Cashback), computes the best stackable combination, and
  reports the lowest payable amount.
- **Cart assembly** — builds the cart, applies the chosen coupon, and gracefully
  handles coupon failures (e.g. "not eligible") by offering to proceed without it.
- **Per-user profiles** — each account stores its own dietary rules, budget,
  delivery addresses, and order history.

---

## Architecture

```
Browser (React + Vite + Tailwind, React Router)
   │  JWT in localStorage  ·  SSE for chat
   ▼
FastAPI backend (backend/api.py)
   /api/auth/*      register · login · me        (Supabase Auth)
   /api/profile     · /api/addresses             (per-user profile)
   /api/orders      · /api/sessions              (history)
   /api/swiggy/*    connect · status · disconnect
   /api/chat        SSE stream of the agent run
   ▼
LangGraph pipeline (agents/)
   supervisor → health_agent → deal_agent → order_agent → supervisor (loop)
   ▼
MCP client (langchain-mcp-adapters)
   ▼
Anthropic MCP proxy ──► Swiggy Food connector
   +
Supabase (PostgreSQL + Auth)
```

### The agent loop

The core is a **supervisor-orchestrated graph** (`agents/supervisor.py`) built
with LangGraph. A shared `State` carries the conversation (`messages`, append-only),
`user_persona`, `cart_summary`, and the per-user Swiggy credentials.

1. Every run enters at `load_persona`, then hands to the **supervisor**.
2. The **supervisor** is the only LLM that talks to the user. It injects the
   persona into its system prompt, reads the full conversation, and ends each
   reply with a JSON routing block: `{"next": "health_agent | deal_agent | order_agent | END"}`.
3. Each **specialist** node (`health_agent`, `deal_agent`, `order_agent`) opens an
   MCP client, spins up an inner **ReAct agent** (`create_react_agent`) armed with
   the Swiggy tools, lets it autonomously call those tools, extracts a structured
   result block, and returns control to the supervisor.
4. The supervisor loops until it routes to `END`. A typical flow is:
   *food request → health_agent → deal_agent → present 3 options → user picks →
   order_agent → payment prompt → SIMULATION COMPLETE*.

State persists per session via LangGraph's `MemorySaver`, keyed by a `thread_id`
(the browser's session UUID).

### MCP and the Swiggy connector

The bot does not call any Swiggy API directly. It reaches Swiggy through the
**Model Context Protocol (MCP)**, via the **Anthropic MCP proxy**
(`mcp-proxy.anthropic.com`), which exposes the Swiggy Food connector's ~14 tools
(`search_restaurants`, `get_restaurant_menu`, `fetch_food_coupons`,
`apply_food_coupon`, `update_food_cart`, `place_food_order`, …).

- `agents/mcp_config.py` centralizes the connection. `build_food_mcp_config(token, url)`
  produces a `MultiServerMCPClient` config using `streamable_http` transport, a
  `Bearer` token, and a unique `X-Mcp-Client-Session-Id` per call.
- `config_from_state(state)` uses the user's own Swiggy credentials when they've
  connected an account, and otherwise falls back to the shared `SWIGGY_SESSION_TOKEN`
  / `SWIGGY_FOOD_MCP_URL` environment variables.
- Two compatibility shims keep the Gemini + MCP combination working:
  - `agents/schema_fix.py` stringifies integer `enum` values in tool schemas
    (Swiggy's `vegFilter: [0, 1]` would otherwise fail Gemini's validator).
  - The order agent wraps tools in `ToolNode(tools, handle_tool_errors=True)` so a
    `ToolException` (e.g. an ineligible coupon) becomes a message the LLM can act
    on instead of crashing the run.

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (`StateGraph`, `Command` routing, `MemorySaver`) |
| LLM | Google Gemini (`langchain-google-genai`) with a model fallback chain |
| Inner agents | `create_react_agent` + MCP tools (`langchain-mcp-adapters`) |
| Backend | FastAPI + Uvicorn (SSE streaming) |
| Auth & DB | Supabase (Auth + PostgreSQL) |
| Frontend | React 19, Vite, Tailwind CSS, React Router, Axios |
| Deployment | Render (multi-stage Dockerfile) |

---

## Running locally

### Prerequisites

- Python 3.11+
- Node.js 20+
- A Supabase project (free tier is fine)
- A Google Gemini API key
- Access to a Swiggy Food MCP server URL + token (see *Known limitations*)

### 1. Configure environment

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Required variables:

```
GOOGLE_API_KEY=...
SWIGGY_BOT_MODELS=gemini-1.5-flash,gemini-2.0-flash,gemini-2.5-flash
SWIGGY_FOOD_MCP_URL=https://mcp-proxy.anthropic.com/v1/mcp/<your_mcpsrv_id>
SWIGGY_SESSION_TOKEN=sk-ant-oat01-...
SWIGGY_ADDRESS_ID=<fallback_address_id>
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
ENCRYPTION_KEY=<fernet_key>   # python -m backend.swiggy.crypto
```

### 2. Set up the database

In the Supabase SQL editor, create the tables: `user_profiles`,
`user_addresses`, `swiggy_connections`, `chat_sessions`, `order_history`
(with row-level security policies scoped to `auth.uid()`). Disable email
confirmation in Auth settings for local development.

### 3. Backend

```bash
python -m venv venv
venv\Scripts\activate           # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn backend.api:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev        # serves on http://localhost:5173, proxies /api to :8000
```

Open `http://localhost:5173`, register an account, complete onboarding, and chat.

### CLI smoke test

To exercise the agent graph without the web stack:

```bash
python run.py
```

This uses the sample persona in `persona/profile.md` and skips auth entirely.

---

## Known limitations

- **The Swiggy connection is personal-session based, not multi-tenant.** The
  Anthropic MCP proxy is tied to a single claude.ai account. The shared
  `SWIGGY_SESSION_TOKEN` authenticates as that one account, so by default every
  user's searches and orders run through the owner's Swiggy session. Users *can*
  connect their own account, but only by manually pasting their own claude.ai
  token and MCP URL (Settings → Connect Swiggy) — there is no real third-party
  OAuth, so this is impractical for genuine public multi-tenant use. App-level
  auth (login, profiles, history) is properly multi-user via Supabase; the Swiggy
  *ordering* layer is not.
- **The server-side Swiggy session expires periodically**, returning `401` from
  the MCP proxy. Reconnect Swiggy in claude.ai to refresh it — rotating the token
  alone does not fix it.
- **Ordering is simulation-only.** `place_food_order` is never called; the bot
  stops at a priced, confirmed preview.
- **Session state is in-memory.** LangGraph uses `MemorySaver`, so conversation
  and cart state are lost when the backend restarts. A persistent checkpointer
  (e.g. Postgres) would be needed for production.
- **Gemini free-tier rate limits apply.** Put a high-quota model first in
  `SWIGGY_BOT_MODELS` (e.g. `gemini-1.5-flash`) to avoid quick `429`s.
- **Secrets are environment-driven.** Never commit `.env`; per-user Swiggy tokens
  are encrypted at rest with `ENCRYPTION_KEY` (Fernet).
