# Fanvue integration design

## Client abstraction
`app/fanvue/base.py` defines `FanvueClient` (get_me, list_chats, get_messages, get_fan_insight, send_message,
list_media, typing) and DTOs. Two implementations:
- `MockFanvueClient` (`app/fanvue/mock.py`) — backed by `mock_*` tables; validates like the real API
  (min price 300 cents, not-contactable error, text-or-media required).
- `LiveFanvueClient` (`app/fanvue/live.py`) — official `/v1` endpoints only, `X-Fanvue-API-Version: 2025-06-26`,
  Bearer token from `oauth.access_token()`, one transparent refresh on 401, client-side limiter (150 req/min,
  4 concurrent), retries on 429/5xx honouring `Retry-After`, typed errors (`NotContactable`, `NeedsReconnect`).
`get_client(db)` picks by `FANVUE_MODE`.

## OAuth (app/fanvue/oauth.py)
Authorization code + PKCE S256, `state` ≥32 chars stored with the verifier (15 min TTL), `client_secret_basic`
at `https://auth.fanvue.com/oauth2/token`, `offline_access` for refresh tokens. Rotation is serialised with a
lock and the new refresh token is committed before use; `invalid_grant` sets `needs_reconnect`.
Callback `/api/fanvue/oauth/callback` requires the operator session.

## Sync (app/services/sync.py)
Polling every `FANVUE_POLL_SECONDS` (default 60): page through `GET /v1/chats`; for chats whose `lastMessageAt`
is newer than the newest local message, fetch the latest 50 messages, insert unseen ones (dedup by message uuid),
refresh fan insights. New fans are back-filled silently. A new inbound message (≤24 h old, still unanswered)
triggers the reply engine. Outbound messages not created by the app (creator replied on Fanvue) supersede
pending AI replies.

## Webhooks (optional)
`POST /api/webhooks/fanvue`: verification probe → 200; HMAC-SHA256 check (`t=..,v0=..`, ±300 s, rotation-aware);
dedup by event id; `creator.message.*` and `creator.payment.succeeded` enqueue an immediate sync (single code path).
Requires a public HTTPS tunnel; polling remains the default.

## Sending
`send_draft` job → gates (live sending enabled in live mode, kill switch for auto, per-fan daily cap,
contactable) → bubbles sent in order with `sent_bubbles` persisted after each, so a retry never double-sends →
offer attached to the last bubble as pay-to-view (`price`, `mediaUuids`, `mediaPreviewUuid`) → `ppv_offers` row.

## Not available through the official API (handled differently)
- Per-message "was this PPV unlocked" flag: not in the message schema → `app/services/purchases.py` checks
  `GET /v1/media/{uuid}?purchasedBy={fanUuid}` (`purchasedByFan`) for every open offer's media when the fan's spend
  increases and in a 30-minute sweep (offers ≤30 days old); manual "Mark sold" covers the rest. Mock mode stores
  unlocks in `mock_purchases` and goes through the same detection path.
- Platform "AI reply" features (CHAT_TEXT_* message types) are Fanvue-internal and unused.
