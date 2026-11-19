# Observed network behaviour (FanWake)

Captured with the Chrome extension's network reader during read-only browsing. Cookies, tokens and
API keys were **not** captured or recorded. Fan UUIDs are omitted.

## Stack (INFERRED from traffic)
- Next.js App Router frontend on `fanwake.app` (page navigations use `GET /<route>?model=…&_rsc=<id>`).
- Supabase (PostgREST) backend queried **directly from the browser** with the user's session (RLS-protected).
  Tables visible from query strings:
  - `creators` (`id, plan, referral_code, is_active, fanvue_creator_id, fanvue_handle, created_at`)
  - `creator_tokens` (`needs_reconnect`, filtered by `creator_id`) — tokens themselves are not selected client-side.
  - `creator_settings` (`followup_enabled`, …)
  - `fans` (`fan_id, display_name`, filtered by `creator_id`)
- Some data goes through Next API routes, e.g. `GET /api/activity?fan_id=<uuid>&limit=3` (fan message log).

## Sequencing
- Overview loads creators → token health (`needs_reconnect`) → settings flags → fan display names for the live strip.
- Fan drawer message log is lazy (only on "Load messages"), page size 3, "Load more".
- Review page shows "Loading drafts…" then renders (client fetch).

## Relevance to the rebuild
The rebuild does **not** call any FanWake endpoint. Only the *shape* of the domain (creator → settings,
tokens health flag, fans, activity log) informed our own schema. Fanvue access goes through the official
Fanvue API only (see `fanvue-api-feasibility.md`).
