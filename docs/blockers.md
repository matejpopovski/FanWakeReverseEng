# Blockers

| # | Blocker | Impact | Workaround / needed from Matej |
|---|---------|--------|-------------------------------|
| B1 | No Fanvue OAuth app credentials (client id/secret) | Live mode cannot connect | Create an app in the Fanvue developer area (needs KYC'd creator account), redirect URI `http://localhost:8000/api/fanvue/oauth/callback`, paste into `.env`. Mock mode works without it. |
| B2 | No AI provider API key | Live AI drafts unavailable | Add `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` to `.env`. Mock provider works offline. |
| B3 | No public HTTPS URL for webhooks | Real-time events unavailable | Polling sync (default) or run a tunnel and register the webhook. |
| B4 | Docker daemon not running | Docker Compose not testable here | Compose file provided; SQLite path used locally. |
| B5 | Live sending/automation | Never enabled without Matej's explicit approval in the thread | Ships disabled. |
