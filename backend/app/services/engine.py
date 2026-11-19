"""Reply engine: inbound handling, draft generation, approval routing, learning."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import classifier, guardrails
from app.ai.prompts import APPROACHES, OUTPUT_SPEC, REENGAGE_APPROACHES, SAFETY_BLOCK, persona_prompt
from app.ai.providers import (
    ChatTurn,
    GenerationRequest,
    GenerationResult,
    ProviderError,
    get_provider,
    parse_json_reply,
)
from app.config import get_settings
from app.db import utcnow
from app.models import AiUsage, Alert, Checkin, CustomRule, Draft, Fan, Message, PromptVersion
from app.services import jobs, ppv, rules, timing
from app.services.metrics import fan_metrics
from app.settings_store import EngineSettings, Persona, ReengageSettings, SafetySettings, load

MEMORY_MAX = 3000
TERMINAL = ("sent", "rejected", "replaced", "expired", "failed")


# ----------------------------------------------------------------------------------------------- helpers


def add_alert(db: Session, fan: Fan | None, kind: str, category: str, message: str) -> Alert:
    # de-duplicate identical open alerts
    existing = db.scalar(select(Alert).where(Alert.fan_id == (fan.id if fan else None), Alert.kind == kind,
                                             Alert.category == category, Alert.status == "open"))
    if existing and existing.message == message:
        return existing
    a = Alert(fan_id=fan.id if fan else None, kind=kind, category=category, message=message[:1000])
    db.add(a)
    db.flush()
    return a


def escalate(db: Session, fan: Fan, category: str, detail: str = "") -> None:
    msg = classifier.ESCALATION_TEXT.get(category, "Needs your attention.")
    if detail:
        msg += f" ({detail})"
    if not fan.escalated:
        fan.escalation_count += 1
    fan.escalated = True
    fan.escalation_reason = category
    add_alert(db, fan, "escalation", category, msg)
    jobs.cancel_jobs(db, "generate_reply", fan_id=fan.id)
    for d in db.scalars(select(Draft).where(Draft.fan_id == fan.id, Draft.status == "approved",
                                            Draft.approved_by == "auto")):
        d.status = "pending"
        d.approved_by = None
        d.route_reason = f"held: fan escalated ({category})"
    jobs.audit(db, "system", "fan.escalated", "fan", fan.id, category=category)


def daily_ai_calls(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AiUsage)
                     .where(AiUsage.at >= utcnow() - timedelta(days=1))) or 0


def sends_today(db: Session, fan_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Message).where(
        Message.fan_id == fan_id, Message.direction == "out",
        Message.origin.in_(("ai_reply", "ai_reengage", "ai_checkin")),
        Message.sent_at >= utcnow() - timedelta(days=1))) or 0


def auto_send_allowed(db: Session, fan: Fan) -> tuple[bool, str]:
    safety = load(db, SafetySettings)
    if safety.automation_paused:
        return False, "automation paused (kill switch)"
    if get_settings().fanvue_mode == "live" and not safety.live_sending_enabled:
        return False, "live sending is disabled"
    if fan.escalated:
        return False, "fan escalated"
    if sends_today(db, fan.id) >= safety.max_sends_per_fan_per_day:
        return False, "per-fan daily send cap reached"
    return True, "ok"


def route(db: Session, fan: Fan, approval_mode: str, threshold_cents: int,
          flags: list[str]) -> tuple[str, str]:
    """Returns ('auto'|'review', reason)."""
    if flags:
        return "review", "guardrail: " + ", ".join(flags)
    if fan.review_mode == "manual":
        return "review", "fan pinned to manual review"
    if fan.review_mode == "auto":
        mode = "auto"
    else:
        mode = approval_mode
    if mode == "review":
        return "review", "review-first mode"
    if mode == "threshold" and fan.total_spent_cents >= threshold_cents:
        return "review", f"fan spend ≥ ${threshold_cents / 100:.0f} threshold"
    ok, why = auto_send_allowed(db, fan)
    return ("auto", "auto mode") if ok else ("review", why)


def store_prompt_version(db: Session, kind: str, content: str) -> PromptVersion:
    h = hashlib.sha256(content.encode()).hexdigest()
    pv = db.scalar(select(PromptVersion).where(PromptVersion.kind == kind, PromptVersion.content_hash == h))
    if pv is None:
        pv = PromptVersion(kind=kind, content_hash=h, content=content)
        db.add(pv)
        db.flush()
    return pv


def history_turns(db: Session, fan: Fan, limit: int) -> list[ChatTurn]:
    msgs = list(db.scalars(select(Message).where(Message.fan_id == fan.id)
                           .order_by(Message.sent_at.desc(), Message.id.desc()).limit(limit)))
    turns = []
    for m in reversed(msgs):
        text = m.text or ""
        if m.tip_cents:
            text = f"[tipped ${m.tip_cents / 100:.2f}] {text}".strip()
        if m.price_cents and m.direction == "out":
            text = f"{text} [paid content offered at ${m.price_cents / 100:.2f}]".strip()
        if m.media_uuids and not m.price_cents:
            text = f"{text} [media attached]".strip()
        if not text:
            continue
        turns.append(ChatTurn(role="user" if m.direction == "in" else "assistant", content=text))
    return turns


def fan_block(db: Session, fan: Fan, metrics: dict[str, float], safety: SafetySettings,
              rule_notes: list[str], now_str: str) -> str:
    lines = [f"FAN: {fan.display_name or fan.handle} (@{fan.handle}), status: {fan.status}.",
             f"Spent so far: ${metrics['total_spent']:.2f}; PPV purchases: {int(metrics['ppv_purchases'])}; "
             f"tips: {int(metrics['tips_count'])}.",
             f"Creator's local time now: {now_str}."]
    if fan.tags:
        lines.append("Tags: " + ", ".join(fan.tags))
    if safety.share_notes_with_ai and fan.notes.strip():
        lines.append("Operator notes: " + fan.notes.strip())
    if safety.share_memory_with_ai and fan.memory.strip():
        lines.append("FAN MEMORY (facts learned earlier):\n" + fan.memory.strip())
    if fan.custom_approach.strip():
        lines.append("Special approach for this fan: " + fan.custom_approach.strip())
    if fan.next_move.strip():
        lines.append("Planned next move: " + fan.next_move.strip())
    profile = ppv.fan_buying_profile(db, fan)
    if profile:
        lines.append("Content history (by tag): " + profile + ". Prefer what they bought; avoid what they passed on.")
    for n in rule_notes:
        lines.append("Rule: " + n)
    return "\n".join(lines)


def build_request(db: Session, fan: Fan, purpose: str, extra: str = "") -> tuple[GenerationRequest, dict[str, Any]]:
    s = get_settings()
    eng = load(db, EngineSettings)
    persona = load(db, Persona)
    safety = load(db, SafetySettings)
    re_s = load(db, ReengageSettings)
    metrics = fan_metrics(db, fan)
    outcome = rules.evaluate(list(db.scalars(select(CustomRule))), metrics)
    allow_ppv = (purpose == "reply" and eng.ppv_enabled and fan.ppv_enabled and not outcome.hold_pitch
                 and eng.approach != "engagement_only")
    gap_reason = ppv.offer_gap_reason(db, fan, eng.min_hours_between_offers) if allow_ppv else None
    eligible = ppv.eligible_templates(db, fan, eng.repitch_cooldown_msgs, eng.repitch_cooldown_hours,
                                      eng.min_hours_between_offers) if allow_ppv else []
    eligible_desc = ppv.describe_for_prompt(db, eligible, fan)

    parts = [persona_prompt(persona)]
    if purpose == "reengage":
        parts.append("TASK: The fan has been quiet. Write ONE short outreach message to restart the conversation. "
                     + REENGAGE_APPROACHES[re_s.approach])
        if re_s.custom_prompt.strip():
            parts.append(re_s.custom_prompt.strip())
    elif purpose == "checkin":
        parts.append("TASK: Write ONE short follow-up message the creator planned earlier. Intent: " + extra)
    else:
        parts.append("TASK: Reply to the fan's latest message(s). Use 1 to "
                     f"{eng.max_bubbles} short chat bubbles. APPROACH: " + APPROACHES[eng.approach])
        if eng.custom_prompt.strip():
            parts.append(eng.custom_prompt.strip())
    if eng.conversation_rules.strip():
        parts.append("CONVERSATION RULES:\n" + eng.conversation_rules.strip())
    if eng.checkins_enabled and purpose == "reply":
        parts.append("CHECK-INS: " + eng.checkin_guidance)
    parts.append(fan_block(db, fan, metrics, safety, outcome.notes,
                           timing.local_now_str(persona.timezone or eng.timezone, utcnow())))
    if eligible_desc:
        parts.append("ELIGIBLE PPV (offer at most one, only if it fits naturally):\n"
                     + json.dumps(eligible_desc, ensure_ascii=False))
    else:
        why = f" ({gap_reason})" if gap_reason else ""
        parts.append(f"ELIGIBLE PPV: none{why}. Do not offer paid content.")
    parts.append(SAFETY_BLOCK)
    parts.append(OUTPUT_SPEC)
    system = "\n\n".join(parts)
    turns = history_turns(db, fan, s.ai_history_messages)
    ctx = {"fan_id": fan.id, "fan_name": fan.display_name, "memory": fan.memory,
           "eligible_ppv": [{"id": t.id} for t in eligible], "checkin_intent": extra}
    meta = {"metrics": metrics, "rules": outcome.as_dict(), "eligible_ids": {t.id for t in eligible},
            "templates": {t.id: t for t in eligible}}
    return GenerationRequest(system=system, turns=turns, purpose=purpose, context=ctx), meta


def call_model(db: Session, req: GenerationRequest) -> tuple[dict[str, Any], GenerationResult]:
    provider = get_provider()
    try:
        res = provider.generate(req)
    except ProviderError as exc:
        db.add(AiUsage(provider=provider.name, model=provider.model, purpose=req.purpose, ok=False,
                       error=str(exc)[:500]))
        raise
    usage = AiUsage(provider=res.provider, model=res.model, purpose=req.purpose, tokens_in=res.tokens_in,
                    tokens_out=res.tokens_out, cost_usd=res.cost_usd, latency_ms=res.latency_ms)
    db.add(usage)
    try:
        data = parse_json_reply(res.text)
    except ProviderError as exc:
        usage.ok = False
        usage.error = str(exc)[:500]
        raise
    return data, res


# ----------------------------------------------------------------------------------------------- inbound


def on_inbound(db: Session, fan: Fan, msg: Message, prev_inbound_at=None) -> None:  # type: ignore[no-untyped-def]
    """Called by sync for each *new* inbound fan message (not during initial backfill)."""
    eng = load(db, EngineSettings)
    if fan.reengage_state == "active":
        fan.reengage_state = "awakened"
        fan.awakened_at = msg.sent_at
        fan.reengage_next_at = None
        jobs.audit(db, "system", "fan.awakened", "fan", fan.id)
    # any pending re-engagement/check-in drafts are now stale
    for d in db.scalars(select(Draft).where(Draft.fan_id == fan.id, Draft.status == "pending",
                                            Draft.kind.in_(("reengage", "checkin")))):
        d.status = "replaced"
        d.reject_reason = "fan replied"

    cls = classifier.classify(msg.text, eng.escalation_keywords, eng.nudge_keywords, msg.tip_cents)
    if cls.escalate:
        escalate(db, fan, cls.escalate[0], cls.matched.get(cls.escalate[0], ""))
        return
    for n in cls.nudge:
        add_alert(db, fan, "nudge", n, classifier.NUDGE_TEXT.get(n, n))

    if not (eng.enabled and fan.autopilot_enabled) or fan.escalated:
        return
    now = utcnow()
    mode, _ = route(db, fan, eng.approval_mode, eng.threshold_spend_cents, [])
    delay = 0.0
    if mode == "auto":
        metrics = fan_metrics(db, fan)
        outcome = rules.evaluate(list(db.scalars(select(CustomRule))), metrics)
        delay = timing.pacing_delay(eng.pacing, fan.pacing_override_min, outcome.pace_factor)
        delay += timing.away_delay(prev_inbound_at, now, eng.away_after_min, eng.away_wait_min, eng.away_wait_max)
    run_at = now + timedelta(seconds=delay)
    run_at = timing.apply_quiet_hours(run_at, eng.quiet_hours_enabled, eng.timezone, eng.quiet_from_hour,
                                      eng.quiet_to_hour) if mode == "auto" else run_at
    jobs.cancel_jobs(db, "generate_reply", fan_id=fan.id)  # debounce: newest message wins
    jobs.enqueue(db, "generate_reply", {"fan_id": fan.id, "trigger_message_id": msg.id}, run_at=run_at)


# ----------------------------------------------------------------------------------------------- drafting


def supersede_pending(db: Session, fan_id: int, kind: str, keep_id: int | None = None) -> None:
    for d in db.scalars(select(Draft).where(Draft.fan_id == fan_id, Draft.kind == kind,
                                            Draft.status == "pending")):
        if d.id != keep_id:
            d.status = "replaced"


def create_draft(db: Session, fan: Fan, purpose: str, extra: str = "", trigger_message_id: int | None = None,
                 approval_mode: str | None = None, threshold_cents: int | None = None,
                 force_review: bool = False) -> Draft | None:
    eng = load(db, EngineSettings)
    safety = load(db, SafetySettings)
    if daily_ai_calls(db) >= safety.max_ai_calls_per_day:
        add_alert(db, None, "system", "ai_budget", "Daily AI call budget reached; drafting paused until tomorrow.")
        return None
    pending = db.scalar(select(func.count()).select_from(Draft).where(Draft.status == "pending")) or 0
    if pending >= safety.pending_queue_cap:
        add_alert(db, None, "system", "queue_full", "Pending review queue is full; new drafts are not created.")
        return None

    req, meta = build_request(db, fan, purpose, extra)
    pv = store_prompt_version(db, f"{purpose}_system", req.system)
    data, res = call_model(db, req)

    kind = {"reply": "reply", "reengage": "reengage", "checkin": "checkin"}[purpose]
    if data.get("escalate") and purpose == "reply":
        cat = str(data["escalate"])
        escalate(db, fan, cat if cat in classifier.ESCALATION_TEXT else "operator_keyword",
                 "flagged by AI")
        return None
    bubbles = data["messages"][: eng.max_bubbles if purpose == "reply" else 1]
    tpl_id = data.get("ppv_template_id")
    try:
        tpl_id = int(tpl_id) if tpl_id is not None else None
    except (TypeError, ValueError):
        tpl_id = -1
    recent_out = [m.text for m in db.scalars(select(Message).where(Message.fan_id == fan.id,
                                                                   Message.direction == "out")
                                             .order_by(Message.sent_at.desc()).limit(10))]
    flags = guardrails.check_bubbles(bubbles, recent_out, max_bubbles=3)
    tpl = meta["templates"].get(tpl_id) if tpl_id else None
    price = None
    media: list[str] = []
    if tpl_id is not None:
        flags += guardrails.check_offer(tpl_id, meta["eligible_ids"], tpl.price_cents if tpl else None)
        if tpl:
            free = bool(tpl.tip_reward_cents and ppv.tip_credit_cents(db, fan) >= tpl.tip_reward_cents)
            price = None if free or tpl.price_cents == 0 else tpl.price_cents
            media = list(tpl.media_uuids or [])
            if tpl.teaser.strip():
                bubbles = [*bubbles[:-1], tpl.teaser.strip()] if bubbles else [tpl.teaser.strip()]

    if force_review:
        mode, why = "review", "manual generation"
    else:
        mode, why = route(db, fan, approval_mode or eng.approval_mode,
                          eng.threshold_spend_cents if threshold_cents is None else threshold_cents, flags)
    draft = Draft(fan_id=fan.id, kind=kind, status="pending", bubbles=bubbles,
                  ppv_template_id=tpl.id if tpl else None, price_cents=price, media_uuids=media,
                  classification={}, guardrail_flags=flags, rule_actions=meta["rules"],
                  prompt_version_id=pv.id, provider=res.provider, model=res.model, tokens_in=res.tokens_in,
                  tokens_out=res.tokens_out, cost_usd=res.cost_usd, route_reason=why,
                  trigger_message_id=trigger_message_id)
    db.add(draft)
    db.flush()
    supersede_pending(db, fan.id, kind, keep_id=draft.id)
    db.query(AiUsage).filter(AiUsage.draft_id.is_(None), AiUsage.at >= utcnow() - timedelta(minutes=1)) \
        .update({"draft_id": draft.id})

    # learning
    if purpose == "reply":
        mem = data.get("memory_update")
        if isinstance(mem, str) and mem.strip():
            fan.memory = mem.strip()[:MEMORY_MAX]
        nm = data.get("next_move")
        if isinstance(nm, str):
            fan.next_move = nm.strip()[:500]
        if isinstance(data.get("nudge"), str) and data["nudge"].strip():
            add_alert(db, fan, "nudge", "ai_nudge", data["nudge"].strip())
        for n in meta["rules"]["nudges"]:
            add_alert(db, fan, "nudge", "rule", n)
        ci = data.get("checkin")
        if eng.checkins_enabled and isinstance(ci, dict) and ci.get("intent"):
            plan_checkin(db, fan, str(ci["intent"]), float(ci.get("in_hours") or 12), eng.checkins_per_week)

    jobs.audit(db, "ai", "draft.created", "draft", draft.id, fan_id=fan.id, kind=kind, route=mode, flags=flags)
    if mode == "auto" and not flags:
        draft.status = "approved"
        draft.approved_by = "auto"
        jobs.enqueue(db, "send_draft", {"draft_id": draft.id}, idempotency_key=f"send-draft-{draft.id}")
    return draft


def plan_checkin(db: Session, fan: Fan, intent: str, in_hours: float, per_week: int) -> Checkin | None:
    if per_week > 0:
        n = db.scalar(select(func.count()).select_from(Checkin).where(
            Checkin.fan_id == fan.id, Checkin.created_at >= utcnow() - timedelta(days=7))) or 0
        if n >= per_week:
            return None
    for c in db.scalars(select(Checkin).where(Checkin.fan_id == fan.id, Checkin.status == "planned")):
        c.status = "cancelled"
    hours = min(max(in_hours, 2.0), 72.0)
    c = Checkin(fan_id=fan.id, intent=intent[:400], scheduled_at=utcnow() + timedelta(hours=hours))
    db.add(c)
    db.flush()
    return c


def generate_reply_job(db: Session, fan_id: int, trigger_message_id: int | None) -> Draft | None:
    fan = db.get(Fan, fan_id)
    if fan is None:
        return None
    eng = load(db, EngineSettings)
    if not (eng.enabled and fan.autopilot_enabled) or fan.escalated or fan.status == "not_contactable":
        return None
    last = db.scalar(select(Message).where(Message.fan_id == fan.id).order_by(Message.sent_at.desc(),
                                                                             Message.id.desc()))
    if last is None or last.direction != "in":
        return None  # already answered (e.g. operator replied on Fanvue)
    return create_draft(db, fan, "reply", trigger_message_id=trigger_message_id)


def expire_drafts(db: Session) -> int:
    eng = load(db, EngineSettings)
    cutoff = utcnow() - timedelta(hours=eng.expire_pending_after_hours)
    n = 0
    for d in db.scalars(select(Draft).where(Draft.status == "pending", Draft.created_at < cutoff)):
        d.status = "expired"
        n += 1
    return n
