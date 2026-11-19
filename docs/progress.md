# Progress log

## 2026-11-19
- **Environment**: macOS 27.2 arm64; Node 20.20 / npm 10.8; Python 3.13.3; uv 0.13.6; git 2.54; gh 2.87; Docker CLI 29.1 (daemon not running); no local Postgres/Redis; Google Chrome installed; Playwright 1.65 via npx; Claude in Chrome extension connected (authenticated FanWake tab).
- Repo was empty (`main`, no commits). Working on branch `claude/project-thread-qdue2b`.
- Phase 1 exploration complete: Overview, Fans (+drawer 4 tabs), Review (+archive), Autopilot (all collapsibles), PPV (+template form, cancelled), Re-engage, Persona, Connect, Account, Billing. Only read-only interactions; nothing saved or sent.
- Fanvue official API + usage policy researched; OpenAPI path list saved.
- Phase 2 design docs written (architecture, schema, contracts, AI design, integration, security, plan).
- Phase 3/4 built: FastAPI backend (SQLite + Alembic, job worker, mock + live Fanvue clients, OAuth PKCE, AI engine with guardrails, rules, PPV, re-engagement, check-ins) and React SPA (11 pages).
- Phase 5: 77 backend tests, 7 frontend unit tests, 7 Playwright e2e tests passing; ruff, mypy, tsc clean. Manually exercised in the browser: login, autopilot enable, simulated fan message, draft with PPV offer, approve and send.
- Bugs found and fixed during manual testing: activity chart bars had zero height; Inbox crashed because an effect returned the Promise from Chrome's scrollIntoView; e2e race on template count; sent list did not auto-refresh.
- Phase 6 docs: README, setup, configuration, testing, deployment, limitations, final feature matrix.
- 2026-11-19 (evening): login made optional (off) at Matej's request. Sales upgrades built: automatic purchase detection (media purchasedBy), sales track record + fan buying profile in prompts, hour-based re-offer cooldown and minimum gap between offers (migration 0002). 89 backend tests, 7 e2e passing.
