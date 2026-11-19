# Configuration

All configuration is environment variables (`.env`, see `.env.example`). Runtime behaviour (autopilot, re-engagement,
safety, persona) is edited in the UI and stored in the `settings` table.

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | dev placeholder | Signs session cookies. Required in practice. |
| `TOKEN_ENCRYPTION_KEY` | derived from SECRET_KEY | Fernet key encrypting Fanvue tokens at rest. |
| `ADMIN_PASSWORD` / `ADMIN_PASSWORD_HASH` | — | Operator login (hash preferred). |
| `DATABASE_URL` | `sqlite:///data/wakeful.db` | Or `postgresql+psycopg://…` (install with `uv sync --extra postgres`). |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Used for the OAuth redirect URI and webhook URL. |
| `FANVUE_MODE` | `mock` | `mock` or `live`. |
| `FANVUE_CLIENT_ID` / `FANVUE_CLIENT_SECRET` | — | Your Fanvue developer app credentials. |
| `FANVUE_WEBHOOK_SECRET` | — | Signing secret if you register a webhook. |
| `FANVUE_POLL_SECONDS` | 60 | Sync interval (min 15). |
| `AI_PROVIDER` | `mock` | `mock`, `anthropic` or `openai` (any OpenAI-compatible endpoint via `OPENAI_BASE_URL`). |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | —, `claude-sonnet-5-5` | |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | | |
| `AI_PRICE_INPUT_PER_MTOK`, `AI_PRICE_OUTPUT_PER_MTOK` | 3, 15 | USD per million tokens for cost tracking; set to your model's prices. |
| `AI_MAX_TOKENS`, `AI_TEMPERATURE`, `AI_HISTORY_MESSAGES` | 600, 0.8, 30 | Generation limits / context size. |
| `WORKER_ENABLED` | true | Run the background worker inside the API process. |
| `RETENTION_DAYS_MESSAGES` | 365 | Daily purge of older messages, usage and audit rows. |

## Connecting your real Fanvue account (live mode)
1. In the Fanvue developer area (requires a KYC-verified creator account) create an app with redirect URI
   `http://localhost:8000/api/fanvue/oauth/callback` and scopes
   `openid offline_access read:self read:chat write:chat read:fan read:insights read:media read:creator`.
2. Put the client id/secret in `.env`, set `FANVUE_MODE=live`, restart.
3. Connect page → **Connect Fanvue** → approve on Fanvue. The first sync imports chats without replying to anything.
4. Reading works immediately. **Sending stays blocked** until you switch on Settings → "Allow sending to real fans".
   Keep Autopilot on *Review first* until you trust the drafts.

## Enabling features
- Autopilot: Autopilot page → Enable → choose approval mode → Save.
- Re-engagement: Re-engage page → Enable (drafts go to Review unless you choose otherwise). "Draft now" runs a scan.
- Custom rules: Autopilot → Custom rules (all ship disabled).
- PPV: PPV library page; the AI only offers active templates that pass each fan's gates.
