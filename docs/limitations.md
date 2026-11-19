# Limitations

## Live vs mock
- **Live Fanvue integration is implemented but not verified against the real API**: no OAuth app credentials were
  available. All live calls follow the official docs/OpenAPI spec and are contract-tested with a mock transport.
  Expect small field-mapping fixes on first real connection (e.g. message `sender` detection, spend fields).
- **Real LLM providers are implemented but not exercised** (no API key). Mock AI produces plausible but simple text.

## API-imposed
- Fanvue's message schema has no "this PPV was unlocked" flag → purchases are tracked from manual "Mark sold",
  payment-webhook-triggered syncs and Fanvue spend totals; per-template revenue in live mode may be incomplete.
- Webhooks need a public HTTPS URL; default is polling (60 s), so reply timing is ≥ poll interval.
- Rate limit 200 req/min: very large chat lists sync gradually (20 pages × 50 chats per run).
- Message history import is the latest 50 messages per chat.

## Deliberate differences from FanWake
- Never denies being AI; sincere AI questions escalate (Fanvue API policy §4.3.2). FanWake deflects by default.
- Off-platform payment and meetup requests escalate instead of nudging.
- Review-first is the default; live sending has a separate master switch.
- No billing/plans/quotas/referrals (single operator) — replaced by AI cost tracking and daily caps.
- No Telegram approvals (not implemented yet); alerts are in-app only (no email).
- Adds a full Inbox/thread view and manual compose, which FanWake lacks.

## Other
- Classifier is keyword/regex based: it can miss paraphrases and over-trigger on some phrases; review escalations.
- Single creator account (schema keeps it simple; multi-model switching not implemented).
- Vault media is fetched live when editing templates (no local cache).
- PostgreSQL and Docker paths were not run here.
