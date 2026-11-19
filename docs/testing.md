# Testing

| Suite | Command | What it covers | Result (2026-11-19) |
|---|---|---|---|
| Backend unit + integration | `make test-backend` | classifier/guardrail regression fixtures, prompt sections, rules engine conflicts, timing windows, provider HTTP contracts, JSON parsing; sync/backfill/idempotency, review & auto modes, debounce/replace, kill switch, live-sending gate, escalations, guardrail routing, PPV gates/cooldown/ownership, resumable sends, not-contactable, job retry/dead-letter, worker tick, re-engagement state machine, check-ins, expiry; API auth/CSRF, every router, validation errors, export/forget; webhook signatures + dedup; OAuth PKCE + refresh rotation + invalid_grant; live Fanvue client request/response mapping; migrations up/down/up | **77 passed** |
| Frontend unit | `make test-frontend` | API client (CSRF header, error mapping, 401 event), UI helpers | **7 passed** |
| Browser e2e (Playwright, system Chrome) | `make e2e` | login failure/success, dashboard, simulate fan message → draft → edit → approve → sent, AI-question escalation, kill switch, PPV validation + create, memory persistence across reload | **7 passed** |
| Static checks | `make lint` | ruff (incl. bandit-style S rules), mypy, tsc | clean |

The e2e suite starts its own server on port 8765 with a throwaway SQLite database, mock Fanvue and mock AI.

## AI regression testing
`backend/tests/test_ai_units.py` holds fixtures of fan messages with expected escalation categories, safe messages
that must not escalate, and draft texts that guardrails must flag. Add a case whenever a real draft surprises you.
With `AI_PROVIDER=mock` the full pipeline is deterministic.

## Not covered by automated tests
- Real Fanvue API calls (no credentials available) — the live client is tested against the documented contract with
  a mock transport.
- Real LLM output quality — provider adapters are contract-tested; quality needs manual review with your persona.
- PostgreSQL — schema is portable SQLAlchemy/Alembic; only SQLite was exercised here.
