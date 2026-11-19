# Final feature matrix & FanWake comparison

Status: **WORKING-MOCK** = fully functional and tested against the mock Fanvue backend; **LIVE-READY** = implemented
against the official API, untested without credentials; **PARTIAL**; **NOT BUILT**; **N/A**.

| Feature | FanWake (observed) | Wakeful implementation | Evidence | Status | Known differences / defects |
|---|---|---|---|---|---|
| Fanvue OAuth connect / reconnect / disconnect | Connect page, scope list | PKCE S256, client_secret_basic, encrypted tokens, rotation lock, needs-reconnect | `test_oauth_*` | LIVE-READY | Not run against real Fanvue |
| Chat & fan sync | "N fans synced" | Polling + optional signed webhooks, dedup, insights refresh | `test_initial_sync_*`, `test_webhook_*`, live client contract | WORKING-MOCK / LIVE-READY | 50 msgs/chat import |
| Overview dashboard | KPIs, perf chart, PPV perf, top fans, log | KPIs, activity chart 7/30/90/All, revenue/offers/conversion, AI cost, top fans, top templates, recent sends | API + e2e | WORKING-MOCK | No monthly quota (N/A) |
| Fan list, segments, search, per-fan autopilot | Yes | Same + escalated/unreachable segments, sort, load more | `test_dashboard_status_and_fans` | WORKING-MOCK | |
| Fan drawer: tags, notes, heads-up | Yes | Yes | API + e2e | WORKING-MOCK | |
| Fan content (owned / offered / offerable, mark sold) | Yes | Yes (ledger in `ppv_offers`) | `test_ppv_*` | WORKING-MOCK | No thumbnails of owned media |
| Fan engine overrides + custom approach | Yes | Yes | API tests | WORKING-MOCK | |
| AI memory (sectioned, editable) | Yes | Yes, `[ABOUT] [BUYING] [DYNAMIC] [NOW]`, 3000 chars | e2e memory test | WORKING-MOCK | Mock AI memory updates are simplistic |
| Next move / planned check-ins | Yes | Yes, weekly cap, skip-if-moved-on, cancel | `test_checkins_*` | WORKING-MOCK | |
| Inbox / thread view / manual compose | Not present | Yes | API + e2e | WORKING-MOCK | New |
| Review queue (approve/edit/reject/archive/recover/delete) | Yes (500 cap) | Yes + regenerate, send-without-offer, guardrail flags, cost per draft | `test_approve_edit_and_send`, `test_draft_reject_recover_delete`, e2e | WORKING-MOCK | |
| Multi-bubble replies | Main + follow-up | 1–3 bubbles, resumable sending | `test_send_retry_is_idempotent` | WORKING-MOCK | |
| Approval modes (auto / threshold / review) + per-fan pin | Yes (auto default) | Yes (review default) | `test_auto_mode_*`, `test_inbound_review_mode_*` | WORKING-MOCK | Safer default |
| Reply pacing, away delay, offline hours | Yes | Yes | `test_pacing_windows`, `test_away_delay_and_quiet_hours` | WORKING-MOCK | |
| Approach presets + custom prompt + conversation rules | 7 presets | 7 original presets + extra instructions + rules text | prompt tests | WORKING-MOCK | Wording original |
| Escalations & nudges | Yes | Yes + built-in policy categories | classifier fixtures, `test_escalation_*`, e2e | WORKING-MOCK | Regex classifier |
| Custom rules engine (16 metrics, 5 actions, placeholders) | Yes (10 on Pro) | Yes (20 max) | `test_rules_*` | WORKING-MOCK | |
| PPV library, tags with meanings, gates, tip reward, cooldown | Yes | Yes | `test_ppv_*`, e2e | WORKING-MOCK | Folders not built (tags only) |
| PPV offer sending (pay-to-view, preview) | Yes | Yes via `POST /v1/chats/{uuid}/message` | `test_ppv_draft_send_records_offer` | WORKING-MOCK / LIVE-READY | |
| Automatic purchase detection | Inferred | `media purchasedBy` lookup on spend increase + 30-min sweep; "Check now" per fan | `tests/test_sales.py` | WORKING-MOCK / LIVE-READY | 30-day lookback |
| Sales learning (item track record, fan buying profile by tag) | Not observed | Added to every prompt | `test_prompt_includes_track_record_*` | WORKING-MOCK | Needs real LLM to matter |
| Time-based re-offer cooldown + minimum gap between offers | Message-count cooldown only | Both message and hour cooldowns; min gap (default 12h); no new offer while one is in flight | `test_time_cooldown_*`, `test_min_gap_*`, `test_in_flight_*` | WORKING-MOCK | |
| Re-engagement (attempts, schedule, silence, repeat, window, hours, cap, approaches, teaser media) | Yes | Yes | `test_reengage_*` | WORKING-MOCK | |
| Persona (identity, tone, behaviours, style, Q&A, examples, custom prompt) | Yes | Yes + prompt preview + versions | persona tests | WORKING-MOCK | 12 languages listed (any works via text) |
| AI providers, token & cost tracking, prompt versioning | Hidden | Mock / Anthropic / OpenAI-compatible; per-call usage; versions per draft | provider contract tests | WORKING-MOCK / LIVE-READY | Real LLM untested |
| Kill switch, live-sending switch, caps, audit log | Not observed | Yes | `test_kill_switch_*`, `test_live_mode_blocks_*`, e2e | WORKING-MOCK | New |
| Privacy: forget fan, export, retention | Not observed | Yes | `test_forget_fan_and_export` | WORKING-MOCK | New |
| Telegram / email notifications | Telegram (optional) | — | — | NOT BUILT | |
| Billing, plans, top-ups, referral | Yes | — | — | N/A | Single operator |
| Multi-model switcher | Yes | — | — | NOT BUILT | Single creator |
| PPV folders | Yes | — | — | NOT BUILT | Tags cover grouping |
