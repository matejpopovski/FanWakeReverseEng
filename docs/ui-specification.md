# UI specification (rebuild), derived from observed FanWake UX

Design language observed: light warm-grey canvas, dark sidebar, single orange accent, white rounded cards,
pill badges (green = subscriber, grey = follower, orange = VIP), toggles in accent colour, long single-column
settings forms with one sticky Save, right-side drawer for entity detail. The rebuild uses its own visual design
(dark-neutral sidebar, indigo accent) and component code; only information architecture is reused.

## Pages
| Route | Purpose | Key components |
|---|---|---|
| `/` Overview | KPIs, mode banner (MOCK/LIVE, kill-switch), activity chart, top fans, recent log | StatCard, BarChart, LogList |
| `/inbox` | Conversation list + thread view + compose/draft panel (**new vs FanWake**) | ChatList, Thread, DraftEditor |
| `/fans` | Searchable, filterable fan table, per-fan autopilot toggle | DataTable, FanDrawer (Overview/Content/Engine/Activity) |
| `/review` | Pending drafts (approve/edit/reject/regenerate), escalations, nudges, scheduled check-ins, archive | DraftCard, AlertList |
| `/autopilot` | Engine settings: enabled, approval mode, threshold, pacing, away delay, quiet hours, approach, rules text, escalation/nudge triggers, custom rules, PPV pitching | SettingsForm, RuleBuilder |
| `/ppv` | Tags, templates CRUD with gates and stats | TemplateForm, TemplateCard |
| `/re-engage` | Re-engagement settings + candidate preview + run-now (drafts only) | SettingsForm, CandidateTable |
| `/persona` | Persona fields, prompt preview, versions | PersonaForm, PromptPreview |
| `/connect` | Mode switch, Fanvue OAuth status, sync now, webhook info | — |
| `/logs` | Audit + job + AI usage logs (tokens, cost) | LogTable |
| `/settings` | AI provider, model, safety switches, data retention, export/backup | — |

## States
Every list has loading, empty and error states; every form validates client-side and shows server errors;
destructive actions use an inline confirm (no browser `confirm()`).
