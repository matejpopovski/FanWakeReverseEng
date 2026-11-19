# AI system design

## Pipeline for one inbound fan message
1. **Trigger**: new inbound message stored by sync (or simulated in mock mode) → `generate_reply` job scheduled
   at `now + pacing delay` (+ away delay if the fan had been idle; postponed to the end of quiet hours).
   A newer inbound message for the same fan reschedules (debounce) and a newer draft *replaces* an older pending one.
2. **Pre-checks** (no LLM): autopilot enabled globally and for the fan, kill switch off, fan not escalated/paused,
   fan contactable, daily AI budget not exceeded.
3. **Classification** (`ai/classifier.py`): deterministic keyword/regex layer first (fast, testable), optional
   LLM layer later. Categories: `smalltalk`, `flirt`, `content_request`, `purchase_intent`, `custom_request`,
   `complaint`, `ai_question`, `off_platform_payment`, `meetup`, `minor_risk`, `self_harm`, `stop_request`.
   Escalating categories (stop + queue for operator): `ai_question` (sincere), `complaint` (strong),
   `off_platform_payment`, `meetup`, `minor_risk`, `self_harm`, `stop_request`, plus operator-defined
   escalation keywords. Nudge categories (continue + heads-up): `custom_request`, `purchase_intent`, big tips.
4. **Rules engine** (`services/rules.py`): evaluate the operator's custom rules over the fan's live metrics
   (same 16 metrics FanWake exposes, computed locally) → actions `hold_pitch`, `note`, `slow_down`,
   `speed_up`, `nudge`. Conflict resolution: notes concatenate, any hold wins, longest slow-down wins,
   slow beats speed.
5. **Context assembly** (`ai/prompt.py`):
   - System prompt = persona block (auto-generated from structured persona, or custom) + approach preset +
     conversation rules + **non-overridable safety block** + output format spec.
   - Fan block = display name, status, spend, purchases, tags, operator notes, memory (`[ABOUT] [BUYING]
     [DYNAMIC] [NOW]`), custom per-fan approach, rule notes, local time for creator.
   - PPV block (only if pitching allowed): eligible templates after gates, ownership, message + hour cooldowns,
     minimum gap since the fan's last offer, and holds; each item carries its track record (sales/offers). If nothing
     is eligible the prompt states why (e.g. "last offer was 3h ago").
   - Fan content history by tag ("bought before: premium x2; offered but not bought: tease x1").
   - History = last N messages (default 30) as alternating turns, oldest first. Never invented details.
6. **Generation**: provider adapter returns JSON `{messages: [..1-2 strings], ppv_template_id|null,
   memory_update|null, next_move, checkin: {text, at}|null, nudge|null}`. Prompt versions are stored
   (`prompt_versions` table, hash of rendered system prompt) and referenced by each draft.
7. **Post-generation guardrails** (`ai/guardrails.py`) — any hit → draft becomes `blocked` with reason and
   goes to review: claims to be human / denies AI, off-platform payment/contact (telegram, whatsapp, cashapp,
   paypal, snap, "meet"), age/minor references, length limits, empty output, repeated identical message,
   pitching a template not in the eligible list, price below Fanvue minimum.
8. **Approval routing**: approval mode `review` (default) | `threshold` (fan spend ≥ X → review) | `auto`.
   Per-fan override `inherit|manual|auto`. Auto only possible if `live_sending_enabled` (live) or mock mode.
9. **Send** (`send_draft` job): idempotency key per draft bubble, rate-limited, typing indicator optional,
   bubble 2 sent a few seconds after bubble 1, PPV sent as pay-to-view (`price`, `mediaUuids`).
10. **Learning**: memory update merged into fan memory (sections kept, ≤3000 chars); `next_move` stored;
    check-in scheduled (max per fan per week); usage (tokens, cost) logged.

## Honesty policy (non-overridable)
Inserted into every system prompt and enforced by guardrails:
- Never claim to be a human, never deny that AI assists with messages.
- If a fan sincerely asks whether they talk to AI/a real person → escalate to operator; no auto answer.
- No off-platform payments or contact, no meeting arrangements, no minors, no pressure tactics
  (false scarcity, guilt, threats of leaving), respect "stop".
- Use only facts present in persona, memory or history; never invent fan details.

## Personas & prompts
Structured persona → deterministic prompt text (`ai/persona_prompt.py`). Custom prompt allowed but the safety
block is always appended after it. Each change creates a `prompt_versions` row.

## Providers
`MockProvider` (deterministic template-based replies, used in tests and mock mode), `AnthropicProvider`
(Messages API via httpx), `OpenAIProvider` (chat completions, any compatible base URL). Configured model,
max tokens, temperature, per-1M-token prices for cost tracking.

## Evaluation
`backend/tests/ai/` contains prompt regression fixtures (inputs → expected classification, guardrail verdicts,
prompt snapshot sections). Mock provider makes the whole pipeline deterministic in CI.
