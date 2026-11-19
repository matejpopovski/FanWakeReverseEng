# Architecture

Private, single-operator, local-first application ("Wakeful" working name).

```
┌────────────── browser (127.0.0.1) ──────────────┐
│ React SPA (Vite, TS, Tailwind, TanStack Query)  │
└───────────────┬─────────────────────────────────┘
                │ JSON /api/*  (HttpOnly session cookie)
┌───────────────▼─────────────────────────────────────────────────────────┐
│ FastAPI app (backend/app)                                               │
│  api/        routers: auth, dashboard, fans, conversations, drafts,     │
│              settings, persona, ppv, reengage, fanvue, logs, webhooks   │
│  services/   sync, drafting, review, sender, reengage, checkins,        │
│              rules, memory, analytics, audit                            │
│  ai/         prompt builder, providers (mock/anthropic/openai),         │
│              guardrails, classifier, cost tracking                      │
│  fanvue/     FanvueClient protocol → MockFanvueClient | LiveFanvueClient │
│              oauth (PKCE), webhook signature verify, rate limiter        │
│  worker/     asyncio loop: claims due jobs from `jobs` table            │
│  db/         SQLAlchemy models, session; alembic/ migrations            │
└───────────────┬───────────────────────────────┬─────────────────────────┘
                │ SQLAlchemy                    │ HTTPS (official API only)
        ┌───────▼────────┐              ┌──────▼──────────────────┐
        │ SQLite / Postgres│             │ api.fanvue.com /v1      │
        └────────────────┘              │ auth.fanvue.com oauth2  │
                                        └─────────────────────────┘
```

## Process model
One `uvicorn` process runs API + worker (worker started in lifespan; can be disabled with `WORKER_ENABLED=false`
and run separately via `python -m app.worker`). Jobs are rows with `run_at`, `status`, `attempts`,
`idempotency_key`; claimed with an atomic UPDATE; retried with exponential backoff; dead-lettered after N attempts.

Job kinds: `sync_fanvue`, `generate_reply`, `send_draft`, `reengage_scan`, `send_checkin`, `memory_update`,
`expire_drafts`.

## Modes
- `FANVUE_MODE=mock` (default): `MockFanvueClient` backed by the local `mock_*` tables, seeded with synthetic fans.
  A "simulate fan message" tool creates inbound messages so the full pipeline can be exercised.
- `FANVUE_MODE=live`: `LiveFanvueClient` with OAuth tokens. Reading/sync works once connected. **Sending is
  additionally gated** by the `live_sending_enabled` setting (default false) and the global kill switch.

## Frontend routes
`/login`, `/` overview, `/inbox`, `/inbox/:fanId`, `/fans`, `/review`, `/autopilot`, `/ppv`, `/re-engage`,
`/persona`, `/connect`, `/logs`, `/settings`.

## Deployment
Local: `make dev` (uvicorn --reload + vite dev server with proxy). Production-like: `make build` builds the SPA
into `backend/app/static` and FastAPI serves it. Docker Compose file provided (app + optional Postgres).
