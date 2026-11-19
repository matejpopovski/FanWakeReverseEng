# Fanvue API feasibility

Sources (read 2026-11-19): https://api.fanvue.com/docs (scopes, authentication, rate limits, webhooks,
event catalogue, creator message events), the OpenAPI spec `https://api.fanvue.com/docs/openapi-v1.json`
(full path list saved in `docs/fanvue-openapi-paths.txt`), and the API Access & Usage Policy
https://legal.fanvue.com/api-policy.

## Access model — CONFIRMED
- OAuth 2.0 authorization code + **PKCE (S256) mandatory**; confidential client, `client_secret_basic` only.
  - Authorize: `https://auth.fanvue.com/oauth2/auth` · Token: `https://auth.fanvue.com/oauth2/token`
  - Request `offline_access` to get a refresh token. Refresh tokens are **single-use and rotate**; reusing one after the grace window kills the chain (user must re-authorize).
  - Redirect URIs must match exactly; `http://localhost` is allowed → a local app works.
  - Creating an app requires a Fanvue creator account with KYC done (developer area). **Matej must create the app and paste client id/secret into `.env`.**
- Base URL `https://api.fanvue.com`, versioned paths `/v1/...`, header `X-Fanvue-API-Version: 2025-06-26`.
- Rate limit: 200 points / 60 s per user per client; 6 concurrent; `429` with `Retry-After`. Polling chats is the main 429 cause → use webhooks or `POST /v1/chats/messages/batch` with `sinceMessageUuid`.

## Scopes the rebuild needs
`openid offline_access read:self read:chat write:chat read:fan read:insights read:media read:creator`
(`write:media` only if uploading; not needed initially.)

## Capability matrix

| Capability | Endpoint(s) | Status |
|---|---|---|
| Who am I | `GET /v1/users/me` | CONFIRMED |
| List chats (cursor, filter unread, search) | `GET /v1/chats` | CONFIRMED |
| Read messages of a chat | `GET /v1/chats/{userUuid}/messages` (`sentBefore`, `limit`, `markAsRead`) | CONFIRMED |
| Delta sync many chats | `POST /v1/chats/messages/batch` (≤50 chats, `sinceMessageUuid`) | CONFIRMED |
| Send text / media / pay-to-view message | `POST /v1/chats/{userUuid}/message` body `{text, mediaUuids, mediaPreviewUuid, price(cents, ≥300), templateUuid, gif}` → `201 {messageUuid}`; not-contactable fan → 400 | CONFIRMED |
| Typing indicator | `POST /v1/chats/{userUuid}/typing` | CONFIRMED |
| Fan notes (native) | `GET/PUT /v1/chats/{userUuid}/notes` | CONFIRMED |
| Subscribers / followers | `GET /v1/subscribers`, `GET /v1/followers` (cursor) | CONFIRMED |
| Per-fan spend & status | `GET /v1/insights/fans/{userUuid}` → `status (subscriber/expired/follower/not_contactable)`, `spending.total`, `lastPurchaseAt`, `maxSinglePayment` | CONFIRMED |
| Bulk fan insights | `POST /v1/insights/fans/batch` (≤100) | CONFIRMED |
| Earnings / top spenders | `GET /v1/insights/earnings`, `/earnings/summary`, `/top-spenders` | CONFIRMED |
| Vault media | `GET /v1/media`, `GET /v1/vault/folders…` | CONFIRMED |
| Mass messages | `POST /v1/chats/mass-messages` (Idempotency-Key) | CONFIRMED — not used (re-engagement is per-fan) |
| Webhooks (message received/sent, payment succeeded, subscription events) | subscription via developer area or `POST /v1/webhooks/subscriptions`; HMAC-SHA256 `X-Fanvue-Signature: t=..,v0=..` over `"<t>.<raw body>"`, 300 s tolerance | CONFIRMED |
| Which PPV a fan unlocked | Message objects in the list endpoint do not expose purchase state in the spec; `GET /v1/media?purchasedBy=` and `creator.payment.succeeded` webhook exist | PARTIAL — rebuild records sales from payment webhooks + manual "mark sold" |
| Webhooks to a laptop | Need a public HTTPS URL (tunnel) | BLOCKED for pure-local; **polling fallback** implemented |

## Policy constraints that shape the design (API policy, paraphrased)
- §4.2 Everything the app sends is the creator's own content and responsibility.
- §4.3.2 AI chat only with creator authorisation; creator must be able to **review, pause and switch off** AI messaging at any time; must **not make fans believe they talk to a live person**; must **not deny being AI** when sincerely asked.
- §4.3.1 AI-generated media must carry a clear AI disclosure.
- §5.2 Prohibited: unsolicited bulk messaging, filter/limit evasion, off-platform payment solicitation, arranging in-person meetings, data resale, training AI on API content without authorisation.
- §7/§10 Keep secrets server-side, encrypt tokens at rest, never log credentials or personal data, retain data only as long as needed.

These are implemented as hard guardrails (see `security.md`, `ai-system-design.md`).

## Unknowns
- Access-token lifetime (only `expires_in` at runtime), refresh grace window length.
- Whether a specific message's PPV was unlocked is queryable directly (spec suggests not).
- Webhook retry schedule / auto-disable rules (page not read).
