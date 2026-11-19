# Implementation plan (as executed)

1. Workspace, config, DB + migrations, job queue — done.
2. Mock Fanvue backend + seed data; live client + OAuth — done (live untested without credentials).
3. Sync service; inbox/fans API — done.
4. Persona + prompt builder + providers (mock/Anthropic/OpenAI) — done.
5. Reply engine: classifier, rules, PPV eligibility, guardrails, routing, memory, check-ins — done.
6. Review queue: approve/edit/reject/regenerate/recover/delete; sender with idempotent resume — done.
7. Re-engagement state machine + scan + preview — done.
8. Analytics dashboard, logs (audit/jobs/AI usage), export, retention, CLI (backup/pause/keys) — done.
9. React SPA for all of the above — done.
10. Tests: unit, integration, API, migration, live-client contract, OAuth, webhook, Playwright e2e — done.
11. Next (not started): Telegram/email notifications, LLM-based classifier second pass, webhook auto-registration,
    vault media sync cache, multi-creator support.
