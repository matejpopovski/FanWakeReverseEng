"""Re-engagement: find quiet fans and draft outreach messages on a schedule.

State machine per fan: none → active (attempt n) → awakened (fan replied) | completed (no reply after last
attempt) | failed (send error) | unreachable (not contactable). Completed/awakened fans can re-enter after
`repeat_every_days` if they had replied at some point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Draft, Fan, Message
from app.services import engine, jobs, timing
from app.settings_store import EngineSettings, ReengageSettings, load

FINAL_GRACE = timedelta(days=7)


@dataclass
class ScanReport:
    candidates: int = 0
    drafted: int = 0
    completed: int = 0
    skipped: list[str] = field(default_factory=list)


def quiet_since(fan: Fan) -> datetime | None:
    return fan.last_inbound_at or fan.first_contact_at or fan.created_at


def due_at(fan: Fan, s: ReengageSettings, attempt_index: int) -> datetime | None:
    base = fan.reengage_cycle_started_at or quiet_since(fan)
    if base is None:
        return None
    days = s.schedule_days[attempt_index] if attempt_index < len(s.schedule_days) else s.schedule_days[-1]
    offset = timedelta(days=days)
    if attempt_index == 0:
        offset = max(offset, timedelta(hours=s.silence_hours))
    return base + offset


def eligible(db: Session, fan: Fan, s: ReengageSettings, now: datetime) -> tuple[bool, str]:
    if not fan.reengage_enabled:
        return False, "disabled for fan"
    if fan.escalated:
        return False, "escalated"
    if fan.status == "not_contactable":
        return False, "not contactable"
    has_inbound = fan.last_inbound_at is not None
    if not has_inbound and not s.include_no_history:
        return False, "no chat history"
    qs = quiet_since(fan)
    if qs is None or now - qs < timedelta(hours=s.silence_hours):
        return False, "not quiet long enough"
    if s.active_within_days is not None and has_inbound and now - qs > timedelta(days=s.active_within_days):
        return False, "inactive beyond window"
    last_out = fan.last_outbound_at
    if last_out and fan.last_inbound_at and last_out > fan.last_inbound_at and fan.reengage_state == "none":
        # we already spoke last outside of re-engagement; count silence from our last message
        if now - last_out < timedelta(hours=s.silence_hours):
            return False, "recent outbound"
    return True, "ok"


def drafts_today(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Draft).where(
        Draft.kind == "reengage", Draft.created_at >= utcnow() - timedelta(days=1))) or 0


def scan(db: Session, now: datetime | None = None, limit: int | None = None) -> ScanReport:
    s = load(db, ReengageSettings)
    eng = load(db, EngineSettings)
    now = now or utcnow()
    rep = ScanReport()
    if not s.enabled:
        rep.skipped.append("re-engagement disabled")
        return rep
    if s.sending_hours_enabled and not timing.in_window(now, eng.timezone, s.send_from_hour, s.send_to_hour):
        rep.skipped.append("outside sending hours")
        return rep
    budget = max(s.daily_cap - drafts_today(db), 0)
    if limit is not None:
        budget = min(budget, limit)

    # 1) transitions for fans already in a cycle
    for fan in db.scalars(select(Fan).where(Fan.reengage_state.in_(("completed", "awakened")))):
        if s.repeat_every_days is None or fan.last_inbound_at is None:
            continue
        ended = fan.reengage_last_sent_at or fan.awakened_at
        if ended and now - ended >= timedelta(days=s.repeat_every_days):
            fan.reengage_state = "none"
            fan.reengage_attempts = 0
            fan.reengage_cycle_started_at = None

    candidates = list(db.scalars(select(Fan).where(Fan.reengage_state.in_(("none", "active")))
                                 .order_by(Fan.total_spent_cents.desc(), Fan.id)))
    for fan in candidates:
        if fan.reengage_state == "active":
            if fan.reengage_attempts >= s.attempts:
                if fan.reengage_last_sent_at and now - fan.reengage_last_sent_at >= FINAL_GRACE:
                    fan.reengage_state = "completed"
                    rep.completed += 1
                continue
            pending = db.scalar(select(Draft.id).where(Draft.fan_id == fan.id, Draft.kind == "reengage",
                                                       Draft.status.in_(("pending", "approved", "sending"))))
            if pending:
                continue
            due = due_at(fan, s, fan.reengage_attempts)
            if due is None or due > now:
                continue
        else:
            ok, why = eligible(db, fan, s, now)
            if not ok:
                continue
        rep.candidates += 1
        if budget <= 0:
            rep.skipped.append("daily cap reached")
            break
        if fan.reengage_state == "none":
            fan.reengage_state = "active"
            fan.reengage_attempts = 0
            fan.reengage_cycle_started_at = quiet_since(fan)
        draft = engine.create_draft(db, fan, "reengage", approval_mode=s.approval_mode,
                                    threshold_cents=s.threshold_spend_cents)
        if draft is None:
            continue
        if s.teaser_media_uuids:
            used = set()
            for m in db.scalars(select(Message.media_uuids).where(Message.fan_id == fan.id,
                                                                  Message.origin == "ai_reengage")):
                used.update(m or [])
            fresh = [u for u in s.teaser_media_uuids if u not in used]
            if fresh:
                draft.media_uuids = [fresh[0]]
        fan.reengage_attempts += 1
        fan.reengage_next_at = due_at(fan, s, fan.reengage_attempts) if fan.reengage_attempts < s.attempts else None
        budget -= 1
        rep.drafted += 1
        db.commit()
    jobs.audit(db, "worker", "reengage.scan", candidates=rep.candidates, drafted=rep.drafted,
               completed=rep.completed)
    db.commit()
    return rep


def preview(db: Session, now: datetime | None = None, limit: int = 50) -> list[dict[str, object]]:
    s = load(db, ReengageSettings)
    now = now or utcnow()
    out = []
    for fan in db.scalars(select(Fan).where(Fan.reengage_state == "none").order_by(Fan.total_spent_cents.desc())):
        ok, why = eligible(db, fan, s, now)
        if ok:
            out.append({"fan_id": fan.id, "display_name": fan.display_name, "handle": fan.handle,
                        "quiet_since": quiet_since(fan), "spent": fan.total_spent_cents / 100})
        if len(out) >= limit:
            break
    return out
