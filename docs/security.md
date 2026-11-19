# Security, privacy and safety

## Authentication
- Single operator. `ADMIN_PASSWORD_HASH` (bcrypt via `python -m app.cli hash-password`) or, for first run only,
  `ADMIN_PASSWORD` in `.env`. Login sets an HttpOnly, SameSite=Strict, signed session cookie (`SECRET_KEY`).
- All `/api/*` routes except `/api/auth/login`, `/api/health`, `/api/fanvue/oauth/callback` (state-checked)
  and `/api/webhooks/fanvue` (HMAC-checked) require the session.
- State-changing requests require the `X-Requested-With: wakeful` header (simple CSRF defence with SameSite).
- Server binds `127.0.0.1` by default.

## Secrets
- Never committed; `.env` is git-ignored; `.env.example` has placeholders only.
- Fanvue access/refresh tokens encrypted at rest with Fernet (`TOKEN_ENCRYPTION_KEY`).
- Logs never contain tokens, cookies or full message bodies (audit log stores ids and short summaries).

## Fanvue integration
- Official OAuth 2.0 + PKCE only; `state` ≥32 random chars bound to the session; exact redirect URI.
- Refresh-token rotation handled atomically (single in-flight refresh, persisted before use).
- Webhooks: HMAC-SHA256 verification, ±300 s timestamp tolerance, constant-time compare, event-id dedup.
- Client-side rate limiter: ≤150 req/min, ≤4 concurrent, honours `Retry-After`.

## Messaging safety defaults
- Approval mode `review`; `live_sending_enabled=false`; global kill switch (`automation_paused`) one click away
  in the header; quiet hours; per-fan daily send cap; re-engagement daily cap; pending queue cap (500).
- Nothing is ever sent from mock mode to Fanvue. Live sends are blocked unless all gates pass; every send is
  audit-logged with draft id, prompt version, approver (`operator` or `auto`).
- Honesty and content guardrails as in `ai-system-design.md`.

## Privacy / retention
- Data stays in the local database. `RETENTION_DAYS_MESSAGES` (default 365) purge job; per-fan "forget" deletes
  messages, memory, notes and drafts for that fan. Export (JSON) and backup (`make backup`) commands.
- AI provider receives only the context needed for a reply; operator can disable sending notes/memory.
