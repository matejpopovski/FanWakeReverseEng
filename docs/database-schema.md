# Database schema

Source of truth: `backend/app/models.py`; migrations in `backend/alembic/versions/` (`0001_initial_schema`).
SQLite by default (WAL, foreign keys on), PostgreSQL via `DATABASE_URL`. Timestamps are naive UTC. Money is integer cents.

| Table | Purpose | Key columns |
|---|---|---|
| `settings` | Typed JSON settings documents | `key` (engine, reengage, safety, persona), `value` |
| `prompt_versions` | Every distinct rendered system prompt | `kind`, `content_hash` (unique per kind), `content` |
| `fanvue_connection` | Singleton OAuth state | `status`, `handle`, `access_token_enc`, `refresh_token_enc` (Fernet), `expires_at`, `needs_reconnect`, `last_sync_at` |
| `oauth_states` | PKCE verifier per pending authorize | `state` (PK), `code_verifier`, 15 min TTL |
| `fans` | CRM record per Fanvue user | `fanvue_uuid` (unique), status, spend metrics, activity timestamps, per-fan overrides (`autopilot_enabled`, `review_mode`, `reengage_enabled`, `ppv_enabled`, `pacing_override_min`, `custom_approach`), `notes`, `tags`, `memory`, `next_move`, escalation state, re-engagement state machine fields |
| `messages` | Local copy of conversation | `fan_id`, `fanvue_uuid` (unique, dedup key), `direction`, `text`, `sent_at`, `media_uuids`, `price_cents`, `tip_cents`, `origin` (fan/operator/ai_reply/ai_reengage/ai_checkin), `draft_id` |
| `drafts` | AI or operator messages awaiting/after sending | `kind` (reply/reengage/checkin/manual), `status` (pending/approved/sending/sent/rejected/replaced/expired/failed), `bubbles`, offer (`ppv_template_id`, `price_cents`, `media_uuids`), `guardrail_flags`, `rule_actions`, `prompt_version_id`, provider/model/tokens/cost, `route_reason`, `approved_by`, `sent_bubbles` (resume point) |
| `alerts` | Escalations, nudges, system notices | `kind`, `category`, `message`, `status` (open/handled) |
| `checkins` | Planned AI follow-ups | `intent`, `scheduled_at`, `status` (planned/drafted/cancelled/skipped), `draft_id` |
| `ppv_tags` | Labels with AI-facing meaning | `name` (unique), `description` |
| `ppv_templates` | Offerable paid content | description, when_to_pitch, teaser, `media_uuids`, preview, `price_cents`, `tag_ids`, gates, `first_purchase_only`, `tip_reward_cents`, `active` |
| `ppv_offers` | Pitch/purchase ledger per fan × template | `status` (pitched/purchased), `source` (ai/manual/webhook/tip_reward), `amount_cents`, timestamps |
| `custom_rules` | Rules engine definitions | `conditions` JSON, `action`, `note`, `factor`, `enabled`, `position` |
| `jobs` | Durable job queue | `kind`, `payload`, `run_at`, `status`, `attempts`, `last_error`, `idempotency_key` (unique), `locked_at` |
| `audit_log` | Who did what | `actor`, `action`, `entity`, `entity_id`, `detail` (ids and short facts only) |
| `ai_usage` | Per-call token/cost/latency | `provider`, `model`, `purpose`, tokens, `cost_usd`, `ok`, `error`, `draft_id` |
| `webhook_events` | Delivery dedup | `id` (event id), `type`, `processed` |
| `mock_fans`, `mock_messages`, `mock_media` | The simulated "remote Fanvue" used in mock mode only | synthetic data |

Relationships: `fans 1─* messages/drafts/alerts/checkins/ppv_offers` (cascade delete), `drafts *─1 ppv_templates` (set null),
`drafts *─1 prompt_versions`. `drafts.trigger_message_id` is a soft reference (no FK) to avoid a messages↔drafts FK cycle.
