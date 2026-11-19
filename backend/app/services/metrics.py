"""Per-fan live metrics used by the rules engine, prompt context and analytics."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Alert, Draft, Fan, Message, PpvOffer

METRICS: dict[str, str] = {
    "hours_since_last_spend": "Hours since last spend",
    "rejected_pitch_streak": "Offers ignored since last spend",
    "pitches_since_last_purchase": "Offers since last PPV purchase",
    "total_spent": "Total spent ($)",
    "ppv_purchases": "PPV purchases (count)",
    "tips_count": "Tips (count)",
    "tip_total": "Total tipped ($)",
    "max_tip": "Biggest single tip ($)",
    "hours_since_last_tip": "Hours since last tip",
    "avg_purchase": "Avg purchase ($)",
    "replies_sent_total": "Replies sent all time",
    "session_message_count": "Messages this session (resets after 6h idle)",
    "exchanges_loaded": "Conversation depth (loaded)",
    "days_since_first_contact": "Days since first contact",
    "days_since_last_active": "Days since last active",
    "escalation_count": "Past escalations (count)",
}

NEVER = 99999.0


def _hours(since: datetime | None, now: datetime) -> float:
    return NEVER if since is None else round((now - since).total_seconds() / 3600, 1)


def fan_metrics(db: Session, fan: Fan, now: datetime | None = None) -> dict[str, float]:
    now = now or utcnow()
    last_spend = max([d for d in (fan.last_purchase_at, fan.last_tip_at) if d], default=None)
    offers = list(db.scalars(select(PpvOffer).where(PpvOffer.fan_id == fan.id)
                             .order_by(PpvOffer.created_at.desc()).limit(50)))
    streak = 0
    for o in offers:
        if o.status == "purchased" or (last_spend and o.pitched_at and o.pitched_at < last_spend):
            break
        streak += 1
    pitches_since_purchase = 0
    for o in offers:
        if o.status == "purchased":
            break
        pitches_since_purchase += 1
    replies_sent = db.scalar(select(func.count()).select_from(Message)
                             .where(Message.fan_id == fan.id, Message.direction == "out")) or 0
    total_msgs = db.scalar(select(func.count()).select_from(Message).where(Message.fan_id == fan.id)) or 0
    # session = messages since the last gap of >= 6h
    recent = list(db.scalars(select(Message.sent_at).where(Message.fan_id == fan.id)
                             .order_by(Message.sent_at.desc()).limit(200)))
    session = 0
    prev = now
    for ts in recent:
        if prev - ts >= timedelta(hours=6):
            break
        session += 1
        prev = ts
    purchases = fan.ppv_purchases
    spent_ppv = max(fan.total_spent_cents - fan.tip_total_cents, 0)
    return {
        "hours_since_last_spend": _hours(last_spend, now),
        "rejected_pitch_streak": float(streak),
        "pitches_since_last_purchase": float(pitches_since_purchase),
        "total_spent": round(fan.total_spent_cents / 100, 2),
        "ppv_purchases": float(purchases),
        "tips_count": float(fan.tips_count),
        "tip_total": round(fan.tip_total_cents / 100, 2),
        "max_tip": round(fan.max_tip_cents / 100, 2),
        "hours_since_last_tip": _hours(fan.last_tip_at, now),
        "avg_purchase": round(spent_ppv / purchases / 100, 2) if purchases else 0.0,
        "replies_sent_total": float(replies_sent),
        "session_message_count": float(session),
        "exchanges_loaded": float(total_msgs),
        "days_since_first_contact": round(_hours(fan.first_contact_at, now) / 24, 1)
        if fan.first_contact_at else NEVER,
        "days_since_last_active": round(_hours(fan.last_inbound_at, now) / 24, 1) if fan.last_inbound_at else NEVER,
        "escalation_count": float(fan.escalation_count),
    }


def pending_counts(db: Session) -> dict[str, int]:
    return {
        "pending_drafts": db.scalar(select(func.count()).select_from(Draft).where(Draft.status == "pending")) or 0,
        "open_alerts": db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open")) or 0,
    }
