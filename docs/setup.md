# Setup

Requirements: Python 3.13 + [uv](https://docs.astral.sh/uv/), Node 20+, macOS/Linux. Docker optional.

1. `make setup` — installs backend (`backend/.venv`) and frontend (`frontend/node_modules`), creates `.env`.
2. `make keys` — prints `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY`; paste them into `.env`.
3. Login is optional. With `ADMIN_PASSWORD` and `ADMIN_PASSWORD_HASH` both empty (the default) there is no login
   screen and the app only listens on 127.0.0.1. To require a password, set `ADMIN_PASSWORD=...` or put the output of
   `make hash-password` in `ADMIN_PASSWORD_HASH`.
4. `make start` (single process on http://localhost:8000) or `make dev` (hot reload, UI on http://localhost:5173).

On start the app runs migrations (`alembic upgrade head`), writes default settings, and in mock mode seeds 30
fictional fans and a demo PPV library, then syncs them. `make migrate` / `make seed` do the same manually.

### Using mock mode
- Inbox → bottom bar "Simulate fan message" pretends the selected fan wrote something.
- `POST /api/mock/simulate-purchase {fan_id, template_id}` marks an offered template as bought.
- Everything (sync, drafting, guardrails, sending, re-engagement) runs through the same code as live mode.

### Operating the review queue
Review shows pending drafts with: why they need review, guardrail flags, rule notes, attached offer, tokens/cost.
Approve (optionally edit), send without the offer, regenerate, or reject with a reason. Rejected/replaced/expired/
failed drafts are kept in the archive (Recover / Delete). Escalations stop automation for that fan until you clear
it on the fan profile. The red **Pause all automation** button in the header is the emergency stop
(`make pause` does the same from a terminal).
