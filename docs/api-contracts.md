# API contracts

Base: `http://127.0.0.1:8000`. JSON in/out. Auth: HttpOnly session cookie from `POST /api/auth/login`.
Every non-GET call under `/api/*` (except login, logout, OAuth callback and the webhook) must send
`X-Requested-With: wakeful`. Errors: `{"detail": "..."}` or a FastAPI validation array (`422`).
Interactive schema: `/api/docs` (dev). Money in responses is dollars (float); in the DB it is integer cents.

Key payloads
- `PATCH /api/fans/{id}`: any of `autopilot_enabled, review_mode (inherit|manual|auto), reengage_enabled, ppv_enabled, pacing_override_min (0-30), custom_approach (≤1000), notes, tags[], memory (≤3000), escalated(false clears)`.
- `POST /api/drafts/{id}/approve`: `{bubbles?: string[≤3], drop_offer?: bool}` → enqueues `send_draft` (idempotency key `send-draft-{id}`).
- `POST /api/drafts/{id}/reject`: `{reason?}`. `POST /api/drafts/{id}/recover`. `DELETE /api/drafts/{id}` (not for sent/in-flight).
- `POST /api/fans/{id}/generate`: `{kind: reply|reengage}` → always a pending draft. `POST /api/fans/{id}/compose`: `{text}` → approved manual draft.
- `PUT /api/settings/{engine|reengage|safety|persona}`: partial document, validated (see `backend/app/settings_store.py`).
- `POST /api/rules`: `{name, enabled, conditions:[{metric, op: gte|lte, value}], action: hold_pitch|note|slow_down|speed_up|nudge, note ≤200, factor}`.
- `POST /api/ppv/templates`: `{name, description, media_uuids[≥1], price (0 or ≥3), tag_ids, gate_min_spent, gate_max_spent, gate_min_purchases, first_purchase_only, tip_reward, when_to_pitch, teaser, preview_media_uuid, active}`.
- `POST /api/webhooks/fanvue`: raw Fanvue envelope; verified with `X-Fanvue-Signature`; verification probe answered 200.

## Route table (generated from the OpenAPI schema)

| Method | Path | Handler |
|---|---|---|
| GET | `/api/alerts` | List Alerts |
| POST | `/api/alerts/handle-all` | Handle All |
| POST | `/api/alerts/{alert_id}/handle` | Handle Alert |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/session` | Session Ok |
| GET | `/api/checkins` | List Checkins |
| POST | `/api/checkins/{cid}/cancel` | Cancel Checkin |
| GET | `/api/conversations` | Conversations |
| GET | `/api/conversations/{fan_id}/messages` | Conversation Messages |
| GET | `/api/dashboard` | Dashboard |
| GET | `/api/drafts` | List Drafts |
| DELETE | `/api/drafts/{draft_id}` | Delete Draft |
| POST | `/api/drafts/{draft_id}/approve` | Approve |
| POST | `/api/drafts/{draft_id}/recover` | Recover |
| POST | `/api/drafts/{draft_id}/reject` | Reject |
| GET | `/api/export` | Export |
| GET | `/api/fans` | List Fans |
| POST | `/api/fans/bulk-autopilot` | Bulk Autopilot |
| GET | `/api/fans/{fan_id}` | Get Fan |
| PATCH | `/api/fans/{fan_id}` | Patch Fan |
| POST | `/api/fans/{fan_id}/compose` | Compose |
| DELETE | `/api/fans/{fan_id}/data` | Forget Fan |
| POST | `/api/fans/{fan_id}/generate` | Generate For Fan |
| POST | `/api/fans/{fan_id}/ppv-sales` | Mark Sold |
| POST | `/api/fanvue/connect` | Connect |
| GET | `/api/fanvue/connection` | Connection |
| POST | `/api/fanvue/disconnect` | Disconnect |
| GET | `/api/fanvue/media` | Media |
| GET | `/api/fanvue/oauth/callback` | Oauth Callback |
| POST | `/api/fanvue/sync` | Sync Now |
| GET | `/api/health` | Health |
| GET | `/api/logs/audit` | Audit Log |
| GET | `/api/logs/jobs` | Job Log |
| POST | `/api/logs/jobs/{job_id}/retry` | Retry Job |
| GET | `/api/logs/usage` | Usage Log |
| GET | `/api/mock/fans` | Mock Fans |
| GET | `/api/mock/media/{uuid}.svg` | Mock Media Svg |
| POST | `/api/mock/simulate-message` | Simulate Message |
| POST | `/api/mock/simulate-purchase` | Simulate Purchase |
| GET | `/api/persona/preview` | Persona Preview |
| GET | `/api/ppv/tags` | List Tags |
| POST | `/api/ppv/tags` | Create Tag |
| PUT | `/api/ppv/tags/{tid}` | Update Tag |
| DELETE | `/api/ppv/tags/{tid}` | Delete Tag |
| GET | `/api/ppv/templates` | List Templates |
| POST | `/api/ppv/templates` | Create Template |
| PUT | `/api/ppv/templates/{tid}` | Update Template |
| DELETE | `/api/ppv/templates/{tid}` | Delete Template |
| POST | `/api/ppv/templates/{tid}/toggle` | Toggle Template |
| GET | `/api/prompt-versions/{vid}` | Prompt Version |
| GET | `/api/reengage/preview` | Reengage Preview |
| POST | `/api/reengage/run` | Reengage Run |
| GET | `/api/rules` | List Rules |
| POST | `/api/rules` | Create Rule |
| PUT | `/api/rules/{rid}` | Update Rule |
| DELETE | `/api/rules/{rid}` | Delete Rule |
| GET | `/api/settings/{key}` | Get Settings Doc |
| PUT | `/api/settings/{key}` | Put Settings Doc |
| GET | `/api/status` | Status |
| POST | `/api/webhooks/fanvue` | Fanvue Webhook |
