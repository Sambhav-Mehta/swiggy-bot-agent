# Swiggy Bot — Progress Tracker

> Last updated: 2026-06-06 | Living document — update before clearing context.

---

## 1. Agenda / Vision

A **multi-agent AI food-ordering bot** for Swiggy, exposed as a **public multi-user web product**. Any user can:
- Register / log in
- Fill a health & food persona (fitness goal, veg/non-veg, restrictions, budget)
- Connect their own Swiggy account (Phase 2)
- Chat naturally to find high-protein meals, auto-apply best coupons + card offers
- Place **real orders** with **native Swiggy payment** (Phase 3)

The bot has a "Seedhe Maut" (Hindi/Hinglish, hip-hop) personality.

---

## 2. Architecture (current)

```
Browser (React + Vite + Tailwind + React Router)
  /login  /register  /onboarding/*  /chat  /settings
        │ JWT in localStorage, axios interceptor adds Bearer header
        ▼
FastAPI Backend (backend/api.py)
  /api/auth/*      → register, login, me, logout       (Supabase Auth)
  /api/profile     → GET/PUT user profile
  /api/addresses   → GET/POST/DELETE addresses
  /api/orders      → GET/POST order history
  /api/sessions    → chat session tracking
  /api/chat        → SSE streaming (JWT-protected, persona from DB)
        ▼
LangGraph Pipeline (agents/)
  supervisor → health_agent → deal_agent → order_agent
        │ MultiServerMCPClient (currently SHARED env token)
        ▼
Anthropic MCP Proxy → Swiggy Food / Dineout / Instamart
        +
Supabase (PostgreSQL + Auth)
  user_profiles, user_addresses, swiggy_connections,
  chat_sessions, order_history
```

---

## 3. Tech Stack & Key Decisions

| Layer | Choice | Notes |
|---|---|---|
| LLM | Google Gemini | `SWIGGY_BOT_MODELS` env = fallback chain. **Put `gemini-1.5-flash` FIRST** (1,500 req/day free); `gemini-2.5-flash` only 25/day |
| Orchestration | LangGraph 1.x | `StateGraph` + `Command` routing + `MemorySaver` checkpointer |
| Inner agents | `create_react_agent` | NOTE: `handle_tool_errors` NOT a valid kwarg here — use `ToolNode(tools, handle_tool_errors=True)` then pass as `tools=` |
| Auth | Supabase Auth | JWT validated via `sb.auth.get_user(token)` — NOT python-jose (avoids HS256/RS256 algorithm mismatch) |
| DB | Supabase Postgres | RLS enabled, `auth.uid() = user_id` policies |
| DB access | `supabase-py` SDK | Service-role key for admin writes, anon key for auth + token validation |
| Frontend | React 19 + Vite 8 + Tailwind v4 | `@tailwindcss/vite` plugin |
| Routing | React Router v6 | |
| HTTP | axios | Interceptor injects JWT from localStorage |
| Markdown | react-markdown | For ORDER_SUMMARY / DEAL_BREAKDOWN blocks |
| Deploy | Render (free tier) | Dockerfile multi-stage (Node builds React → Python serves). Railway abandoned (free trial exhausted) |

### Naming conventions
- Backend: snake_case modules, sub-package per domain (`auth/`, `db/`, `profile/`, `orders/`, `swiggy/`)
- Each backend sub-package has `__init__.py` + `router.py`
- Frontend: PascalCase components, `use*` hooks, `*Context.jsx` contexts, `pages/` for routes
- DB persona dict keys: `raw, name, location, diet_goals, restrictions, preferences, budget_wkday, budget_wknd, address_id`

---

## 4. Phase 1 — COMPLETE ✅

**Goal:** Any user can register, fill profile, and chat. (Shared Swiggy account, simulated orders.)

### Backend — done
- `backend/db/connection.py` — Supabase client singletons (service + anon)
- `backend/db/models.py` — Pydantic models (RegisterRequest, LoginRequest, AuthResponse, UserProfileIn/Out, AddressIn/Out, OrderIn/Out)
- `backend/db/crud.py` — all DB ops + `profile_to_persona_dict()` (converts DB row → supervisor persona dict)
- `backend/auth/router.py` — `/api/auth/register|login|me|logout`
- `backend/auth/middleware.py` — `get_current_user` via `sb.auth.get_user(token)`
- `backend/profile/router.py` — profile + addresses CRUD
- `backend/orders/router.py` — orders + sessions
- `backend/api.py` — all routers mounted, `/api/chat` JWT-protected, persona loaded from DB (not request body), serves React `dist/` via `StaticFiles(html=True)`
- `backend/models.py` — `ChatRequest` slimmed (message + session_id only; no persona)

### Frontend — done
- `frontend/src/contexts/AuthContext.jsx` — JWT storage, axios instance + interceptor, login/register/logout/refreshProfile
- `frontend/src/pages/LoginPage.jsx`, `RegisterPage.jsx`
- Onboarding wizard (Step1 personal, Step2 fitness, Step3 address) — *built per plan*
- `frontend/src/components/ChatWindow.jsx` — uses `useAuth()`, Settings + New Chat buttons (no longer takes persona prop)
- `App.jsx` — React Router + protected routes
- `useChat.js` — auth header, no persona in request

### Agents — done
- `agents/schema_fix.py` — **CRITICAL PATCH**: monkey-patches `langchain_google_genai._function_utils._dict_to_genai_schema` to stringify integer enum values. Swiggy's `vegFilter` param has `enum: [0,1]` (ints) which Gemini rejects. Imported at top of all 3 agent files.
- `health_agent.py` / `order_agent.py` — dynamic system prompts (per-user name + addressId from state)

### DB — done
- All 5 tables created in Supabase via SQL editor, RLS enabled with per-user policies.

### Verified working
- Register → row appears in Supabase `auth.users` + `user_profiles` ✅
- Login → JWT issued ✅
- Address save → works after switching JWT validation to `sb.auth.get_user()` ✅
- Chat → bot responds, uses DB persona ✅ (hit Gemini free-tier 429 — resolved by reordering models)

### Gotchas resolved in Phase 1
1. `email_validator` missing → `pip install pydantic[email]` (added to requirements)
2. JWT "alg not allowed" → switched from python-jose manual decode to Supabase SDK validation
3. Gemini integer-enum crash → `schema_fix.py` monkeypatch
4. Supabase email confirmation ON by default → must turn OFF in Auth settings for dev
5. PowerShell doesn't support `&&` → use `;` or separate commands
6. Gemini 429 → reorder `SWIGGY_BOT_MODELS` to put `gemini-1.5-flash` first

---

## 5. Phase 2 — Per-User Swiggy Credentials (COMPLETE ✅, Option D)

**Decision made:** True per-user OAuth via the Anthropic MCP proxy is **NOT possible**
for a public app — the proxy is single-tenant (tied to the developer's claude.ai
account). So we chose **Option D**: build full per-user infrastructure, default
everyone to the shared env token, and let power users optionally paste their own
claude.ai Swiggy token + MCP URL.

**How "connect your own Swiggy" works (the answer to the user's recurring question):**
There is no automatic/OAuth way. A user who wants their OWN account must:
1. Open claude.ai → Settings → Connectors → connect Swiggy Food
2. Copy their MCP server URL (`mcpsrv_...`) + access token (`sk-ant-oat01-...`)
3. Paste both into Settings → "Connect My Swiggy" in our app
We validate by listing tools, then store encrypted. If they never connect, the
shared demo account is used automatically. This is documented inline in the UI.

### What was built
- `agents/mcp_config.py` — **centralised** MCP config builder. `build_food_mcp_config(token, url)` + `config_from_state(state)`. Falls back to env when state values are empty. Replaced the duplicated `_MCP_CONFIG` / `_mcp_headers` / `_no_ssl_factory` blocks in all 3 agents.
- `agents/supervisor.py` — `State` gained `swiggy_token` + `swiggy_mcp_url` fields.
- `health_agent.py` / `deal_agent.py` / `order_agent.py` — now call `config_from_state(state)` instead of module-level `_MCP_CONFIG`. Removed dead imports (`uuid`, `httpx`, per-agent helpers).
- `backend/swiggy/crypto.py` — Fernet encrypt/decrypt for tokens at rest. No key set → plaintext passthrough (dev). `python -m backend.swiggy.crypto` mints a key.
- `backend/swiggy/router.py` — `POST /api/swiggy/connect` (validates via tool list, stores encrypted), `GET /api/swiggy/status`, `DELETE /api/swiggy/disconnect`.
- `backend/db/crud.py` — `upsert_swiggy_connection`, `get_swiggy_connection` (decrypts), `delete_swiggy_connection`.
- `backend/db/models.py` — `SwiggyConnectIn`, `SwiggyStatusOut`.
- `backend/api.py` — mounts swiggy router; `/api/chat` reads the user's connection from DB and injects `swiggy_token` + `swiggy_mcp_url` into initial_state (falls back to "" → shared env).
- `frontend/src/pages/SettingsPage.jsx` — "Swiggy Account" section: status pill, collapsible connect form with inline how-to instructions, verify+connect, disconnect.
- `.env` + `.env.example` — `ENCRYPTION_KEY` (Fernet). Real key is in `.env` already.

### Verified
- Agents compile, graph builds, `config_from_state({})` → env fallback, `config_from_state({token,url})` → per-user values ✅
- Encryption roundtrip with real key ✅
- Full backend imports ✅
- Frontend builds (244 modules) ✅

### NOT yet done in Phase 2
- **DB table:** `swiggy_connections` table must exist in Supabase. It was in the original Phase 1 SQL — **verify it exists** (Table Editor). If not, create it (schema in section 3 of the plan / DB schema).
- **Address sync on connect** (call `get_addresses` after connect to populate `user_addresses`) — deferred, optional nice-to-have.
- **Not tested end-to-end live** — needs the table confirmed + a manual connect test.

### Phase 2 gotcha
- `backend/db/crud.py` now imports `backend.swiggy.crypto` → `backend.swiggy` must be a package (`__init__.py` exists ✅). No circular import because `agents/mcp_config.py` is standalone (only imports os/uuid/httpx).

---

## 6. Environment Variables (.env)

```
GOOGLE_API_KEY=...
SWIGGY_BOT_MODELS=gemini-1.5-flash,gemini-1.5-flash-8b,gemini-2.0-flash,gemini-2.5-flash  # 1.5-flash FIRST
SWIGGY_ADDRESS_ID=339175103          # fallback default (Viman Nagar)
SWIGGY_FOOD_MCP_URL=https://mcp-proxy.anthropic.com/v1/mcp/mcpsrv_01USRnNY7F3XZXVs95w8xAyo
SWIGGY_SESSION_TOKEN=sk-ant-oat01-...  # SHARED token, refreshed from ~/.claude/.credentials.json
SUPABASE_URL=https://tdiivvfvwvvxuvlpxfdk.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_KEY=eyJ...
# SUPABASE_JWT_SECRET — no longer needed (SDK validates)
GITHUB_TOKEN=ghp_...
GITHUB_REPO=Sambhav-Mehta/swiggy-bot-agent
# Phase 2 (not yet): ENCRYPTION_KEY, APP_URL
```

### RECURRING MCP ISSUE (every session)
`SWIGGY_SESSION_TOKEN` 401s happen when the **server-side Swiggy MCP session expires** (not the token). Fix: reconnect Swiggy on claude.ai → Settings → Integrations. Token itself rarely changes; grab latest from `~/.claude/.credentials.json` → `claudeAiOauth.accessToken` if needed.

---

## 7. Phases 3 & 4 (not started)

- **Phase 3:** Real ordering — remove "do NOT call place_food_order" from order_agent; add payment-method routing (UPI/Card/COD); save to `order_history`.
- **Phase 4:** Order tracking agent, `/orders` history page, rate limiting (slowapi), PostgresSaver (replace MemorySaver), remove all hardcoded "Viman Nagar".

---

## 8. Deployment State
- **GitHub:** `Sambhav-Mehta/swiggy-bot-agent` (private), `main` branch
- **Live:** Render — `https://swiggy-bot-agent.onrender.com` (Dockerfile build). Spins down after 15 min idle (free tier).
- **TODO before next deploy:** Add `SUPABASE_*` + reordered `SWIGGY_BOT_MODELS` env vars to Render dashboard; commit + push Phase 1 work (may not be pushed yet — verify `git status`).
- Plan file: `C:\Users\sambh\.claude\plans\ethereal-hopping-bear.md`
