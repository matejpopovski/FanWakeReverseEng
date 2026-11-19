# Deployment, operations and backups

This is a private tool. Keep it bound to `127.0.0.1` (default) or behind your own VPN/reverse proxy with TLS.

## Local (recommended)
`make start` → http://localhost:8000. For always-on use, run it under `launchd`/`systemd` or a terminal multiplexer.

## Docker
`docker compose up -d --build` runs the app + PostgreSQL 17, port bound to localhost. Uses `.env`.
(Not executed in this environment because the Docker daemon was not running.)

## Webhooks (optional)
Expose `/api/webhooks/fanvue` via an HTTPS tunnel (e.g. Cloudflare Tunnel), register it in the Fanvue developer
area for `creator.message.received`, `creator.message.sent`, `creator.payment.succeeded`, and set
`FANVUE_WEBHOOK_SECRET`. Set `PUBLIC_BASE_URL` to the tunnel URL only if OAuth also goes through it.

## Backups
- SQLite: `make backup` → consistent online copy in `backups/wakeful-YYYYMMDD-HHMMSS.db`. Restore by stopping the
  app and copying the file to `data/wakeful.db`.
- PostgreSQL: `docker compose exec db pg_dump -U wakeful wakeful > backup.sql`.
- `.env` holds your keys; back it up separately and securely. Losing `TOKEN_ENCRYPTION_KEY` only means reconnecting Fanvue.

## Monitoring
Logs page: audit trail, job queue (retry dead jobs), AI usage/cost. Overview shows escalations and pending drafts.
`GET /api/health` for uptime checks.
