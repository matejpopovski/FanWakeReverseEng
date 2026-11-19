# Behavioural findings (FanWake)

Format: finding — evidence — status.

## Reply engine
- Replies are timed to look human: pacing presets 5–45 s / 15 s–3 min (≤5 min) / 1–7 min (≤10 min) — UI copy — VERIFIED (copy), INFERRED (runtime).
- "Away delay": after N minutes of fan silence, the next reply waits a random min–max minutes; shown as a cancellable timer — UI + live strip — VERIFIED.
- Offline hours: no replies inside window; backlog spread across ~30 min after — UI copy — INFERRED runtime.
- Drafts can contain a main bubble plus a follow-up bubble sent seconds later — review archive — VERIFIED.
- A new draft for a fan *replaces* an older pending one (status "Replaced") — review archive — VERIFIED.
- Draft statuses observed: pending, sent, rejected, replaced, expired, failed; archive supports Recover (back to queue) and Delete — VERIFIED.
- Pending queue hard cap 500 — VERIFIED (counter).
- Escalation runs in every approval mode and holds the conversation for the operator — UI copy — INFERRED.
- Nudges ("heads up") are short third-person observations stored per fan and acknowledged with "Got it" — VERIFIED.

## Memory
- Per-fan memory is a single editable text blob (≤3000 chars) with fixed section headers `[ABOUT]`, `[BUYING]`, `[DYNAMIC]`, `[NOW]`, auto-updated by the engine — VERIFIED.
- "AI approach" per fan stores a *next move* and an optional *planned check-in* — VERIFIED.

## Rules engine
- 16 fan metrics, numeric ≥/≤ conditions, AND-combined, actions hold-pitch / note / slow / speed / nudge, conflict resolution: notes concatenate, any hold wins, longest slow-down wins, slow beats speed — UI copy — VERIFIED (copy).
- Notes support `{placeholder}` substitution of the same metrics — VERIFIED.

## PPV
- Engine tracks pitched vs purchased per fan and never re-pitches purchased templates; unpurchased re-pitch after cooldown (off/25/50 msgs) — UI copy — INFERRED runtime.
- Availability gates (spend range, min PPV count, first-purchase-only) hard-filter eligibility; tags alone do not — UI copy — VERIFIED.
- Tip-reward: tips in last 24 h not yet "spent" become credit that can unlock a template free — UI copy — INFERRED.
- Paid price minimum $3.00 (matches Fanvue API `price` min 300 cents) — VERIFIED (both sides).

## Re-engagement
- State per fan: — / Attempt N / Completed / Failed / Unreachable — fans table — VERIFIED.
- Up to 4 attempts on a day schedule; Completed = sequence ended with no reply; Unreachable = Fanvue reports not contactable (INFERRED from API `not_contactable`).
- "Awakened" = fan replied to a re-engagement message — KPI copy — VERIFIED.

## Policy-relevant observation
- FanWake's default conversation rules tell the AI to neither confirm nor deny AI involvement and to deflect, escalating on direct accusation. Fanvue's API policy §4.3.2 says apps must not make fans believe they are talking to a live person and must not deny being AI when sincerely asked. **The rebuild deliberately differs**: sincere "are you AI/real?" questions are escalated to the operator *and* any AI-drafted answer must not deny AI involvement (see `ai-system-design.md`).
- Several observed nudges concern off-platform payment and in-person meetings; both are prohibited categories in Fanvue's API policy. The rebuild escalates (stops) on these instead of only nudging.
