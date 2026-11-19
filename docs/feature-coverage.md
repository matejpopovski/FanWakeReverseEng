# Feature coverage matrix

Columns: FanWake status (from exploration) → rebuild status. Rebuild statuses: PLANNED, MOCK-WORKING (fully functional against mock Fanvue), LIVE-READY (implemented against official API, untested without credentials), LIVE-VERIFIED, OMITTED.
See `final-feature-matrix.md` for the end-of-project state.

| Feature | FanWake | Rebuild |
|---|---|---|
| Overview KPIs + chart | VERIFIED | WORKING-MOCK |
| Fan list / filters / search | VERIFIED | WORKING-MOCK |
| Fan drawer (notes, tags, content, engine overrides, memory, activity) | VERIFIED | WORKING-MOCK |
| Inbox / thread view | NOT IN FANWAKE | WORKING-MOCK |
| Review queue + archive | VERIFIED | WORKING-MOCK |
| Autopilot settings | VERIFIED | WORKING-MOCK |
| Custom rules engine | VERIFIED | WORKING-MOCK |
| Escalations / nudges | VERIFIED | WORKING-MOCK |
| Scheduled check-ins | VERIFIED | WORKING-MOCK |
| Persona + prompt | VERIFIED | WORKING-MOCK |
| PPV library + gates | VERIFIED | WORKING-MOCK |
| Re-engagement | VERIFIED | WORKING-MOCK |
| Fanvue OAuth connect | VERIFIED | LIVE-READY (untested without credentials) |
| Telegram notifications | UNVERIFIED | NOT BUILT |
| Billing / plans / referral | VERIFIED | OMITTED (N/A) |
