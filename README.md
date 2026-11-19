# Wakeful — private AI-assisted Fanvue inbox

A single-operator, locally run alternative to FanWake, built independently from observed behaviour and the
**official Fanvue API**. It syncs your Fanvue chats, drafts replies and re-engagement messages in your persona,
and puts everything through a review queue before it reaches a fan.

> Ships in **mock mode** (fictional fans, nothing leaves your machine) with **review-first** approval and
> **live sending disabled**. Going live is three deliberate steps; see [docs/configuration.md](docs/configuration.md).

## Quick start (mock mode)

```bash
make setup          # uv sync + npm install + creates .env from .env.example
make keys           # paste SECRET_KEY / TOKEN_ENCRYPTION_KEY into .env
make start          # builds the UI and serves everything on http://localhost:8000
```

There is no login by default (local only; set `ADMIN_PASSWORD` if you want one). Then: Autopilot → enable → Save; Inbox → "Simulate fan message"; Review → edit/approve.
For development with hot reload use `make dev` (API :8000 + Vite :5173).

## What it does
- **Inbox & CRM**: conversations, fan profiles, tags, notes, editable AI memory, spend/purchase history, segments.
- **AI drafting**: persona-driven replies (1–3 bubbles), approach presets, conversation rules, custom rules over
  16 live fan metrics, PPV suggestions with gates/cooldowns/ownership tracking, scheduled check-ins.
- **Safety**: review-first default, global kill switch, live-sending master switch, quiet hours, per-fan caps,
  escalations (AI-identity questions, off-platform payment, meetups, possible minors, self-harm, stop requests,
  complaints), post-generation guardrails (never claims to be human), full audit log.
- **Re-engagement**: quiet-fan detection, multi-attempt schedule, awakened/completed/failed/unreachable states.
- **Ops**: durable job queue with retries, AI token/cost tracking, prompt versioning, JSON export, backups, retention.

## Docs
Setup [docs/setup.md](docs/setup.md) · Configuration [docs/configuration.md](docs/configuration.md) ·
Testing [docs/testing.md](docs/testing.md) · Deployment & backups [docs/deployment.md](docs/deployment.md) ·
Limitations [docs/limitations.md](docs/limitations.md) · Feature matrix [docs/final-feature-matrix.md](docs/final-feature-matrix.md) ·
Architecture [docs/architecture.md](docs/architecture.md) · FanWake research [docs/feature-inventory.md](docs/feature-inventory.md)
