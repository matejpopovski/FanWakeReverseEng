# Decisions (ADR log)

| # | Date | Decision | Why |
|---|------|----------|-----|
| D1 | 2026-11-19 | Independent implementation; FanWake used only as UX/behaviour reference. No FanWake endpoints, code or prompt text are reused. | Legal/ethical; prompt requirement. |
| D2 | 2026-11-19 | Backend: Python 3.13 + FastAPI + SQLAlchemy 2 + Alembic. | Strong typing via Pydantic, real migrations, fast tests; uv available. |
| D3 | 2026-11-19 | Database: SQLite by default (file in `data/`), PostgreSQL supported through `DATABASE_URL`. | Docker daemon not running and no local Postgres; single operator load is tiny. |
| D4 | 2026-11-19 | Background work: DB-backed job queue + in-process asyncio worker (no Redis). | Fewer moving parts; jobs survive restarts; idempotency keys in DB. |
| D5 | 2026-11-19 | Frontend: Vite + React + TypeScript + Tailwind + React Router + TanStack Query. | Pure SPA served by FastAPI in production; no SSR needed for a local tool. |
| D6 | 2026-11-19 | Fanvue integration behind a `FanvueClient` interface with `MockFanvueClient` and `LiveFanvueClient`. Mode is a single setting; live requires OAuth tokens. | Clear mock/live separation. |
| D7 | 2026-11-19 | Default approval = review-first. Auto-send only when live sending is explicitly enabled, kill-switch off, and quiet hours/rate limits pass. | Prompt safety rules; Fanvue policy §4.3.2. |
| D8 | 2026-11-19 | AI honesty guardrail is non-optional: a sincere "are you AI / a real person?" escalates; drafts that deny AI involvement or claim to be human are blocked by a post-generation check. | Fanvue policy §4.3.2; differs from FanWake default. |
| D9 | 2026-11-19 | Off-platform payment and in-person meeting requests escalate (stop) rather than nudge; drafts proposing them are blocked. | Fanvue policy §5.2. |
| D10 | 2026-11-19 | Sync by polling (`/v1/chats` + per-chat messages) with optional webhook endpoint (HMAC verified) for when a tunnel exists. | Laptop has no public URL. |
| D11 | 2026-11-19 | Tokens encrypted at rest with Fernet key from env; operator login via password hash in env + HttpOnly session cookie; server binds 127.0.0.1. | Policy §10; single operator. |
| D12 | 2026-11-19 | AI providers: `mock` (deterministic, offline), `anthropic`, `openai` (compatible). Token + cost tracked per call. | Testability and choice. |
