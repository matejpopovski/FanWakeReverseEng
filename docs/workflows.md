# Workflows (FanWake observed → rebuild)

## W1 Inbound fan message (autopilot)
Observed: fan writes → (away delay if fan was idle) → pacing wait → AI draft (1–2 bubbles) → approval mode
decides: auto-send / threshold (fan spend ≥ X → review) / review-first. Escalation conditions stop the chat and
queue for the operator; nudges let it continue and add a heads-up. Memory and "next move" update after.
Rebuild: same pipeline, but **default approval = review-first**, auto-send requires live mode + global
kill-switch off + per-fan allowance + explicit operator opt-in.

## W2 Operator reviews a draft
Observed: Review page lists pending drafts; archive has Recover/Delete. Rebuild: approve (optionally edit),
reject (with reason), regenerate; approved drafts go to the send queue with idempotency key; archive with recover.

## W3 Re-engagement
Observed: silent fans (≥ silence threshold, within activity window, contactable) get up to N attempts on a day
schedule; reply → "Awakened"; no reply after last attempt → "Completed"; send error → "Failed"; not contactable →
"Unreachable"; optional repeat cycle for fans who previously replied; daily cap; sending hours.
Rebuild: same state machine; drafts go to review by default.

## W4 PPV pitch
Observed: engine picks an eligible template (active, gates pass, not owned, cooldown) when the approach allows,
writes a teaser (or fixed teaser), attaches vault media + optional free preview, sends as pay-to-view.
Rebuild: AI may *suggest* a template; it is attached to the draft as an offer; nothing is priced/sent without review.

## W5 Scheduled check-in
Observed: engine plans a follow-up with time; before sending it re-reads the chat and cancels if stale.
Rebuild: same, limited per fan per week; operator can cancel.

## W6 Persona editing
Observed: structured persona fields build the system prompt automatically; custom prompt overrides.
Rebuild: same, with prompt versioning (every save creates a new version; drafts reference the version used).

## W7 Fanvue connection
Observed: OAuth connect, reconnect/refresh, disconnect, scope list.
Rebuild: OAuth + PKCE against official endpoints; mock mode needs no connection.
