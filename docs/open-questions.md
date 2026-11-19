# Open questions

1. FanWake runtime timing (pacing distribution, offline backlog spread) — only UI copy seen. Rebuild uses its own documented distributions.
2. How FanWake detects PPV unlocks (vault sync vs payment webhooks) — UNVERIFIED. Rebuild uses `creator.payment.succeeded` + manual marks.
3. Model switcher behaviour with multiple creators — UNVERIFIED (single account). Rebuild is single-creator but schema keeps `creator_id`.
4. Telegram approve/reject flow — not exercised.
5. Fanvue access-token lifetime and refresh grace window — not documented.
6. Does Matej want webhooks (requires a public tunnel such as Cloudflare Tunnel/ngrok) or polling only? Default: polling every 60 s within rate limits.
7. Which AI provider/model for live use? Default adapter list: mock, Anthropic, OpenAI-compatible. Needs an API key in `.env`.
