"""PPV eligibility: which templates may be offered to a given fan right now."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Fan, Message, PpvOffer, PpvTag, PpvTemplate


def gate_reason(t: PpvTemplate, fan: Fan) -> str | None:
    """Return why the template is gated for this fan, or None if the gates pass."""
    if not t.active:
        return "inactive"
    if t.gate_min_spent_cents is not None and fan.total_spent_cents < t.gate_min_spent_cents:
        return "below min spend"
    if t.gate_max_spent_cents is not None and fan.total_spent_cents > t.gate_max_spent_cents:
        return "above max spend"
    if t.gate_min_purchases is not None and fan.ppv_purchases < t.gate_min_purchases:
        return "not enough purchases"
    if t.first_purchase_only and (fan.ppv_purchases > 0 or fan.total_spent_cents > 0):
        return "first purchase only"
    return None


def owned_template_ids(db: Session, fan_id: int) -> set[int]:
    return set(db.scalars(select(PpvOffer.template_id).where(PpvOffer.fan_id == fan_id,
                                                             PpvOffer.status == "purchased")))


def on_cooldown(db: Session, fan: Fan, template_id: int, cooldown_msgs: int | None) -> bool:
    last = db.scalar(select(func.max(PpvOffer.pitched_at)).where(
        PpvOffer.fan_id == fan.id, PpvOffer.template_id == template_id, PpvOffer.status == "pitched"))
    if last is None:
        return False
    if cooldown_msgs is None:
        return True  # never re-pitch unpurchased templates
    since = db.scalar(select(func.count()).select_from(Message)
                      .where(Message.fan_id == fan.id, Message.sent_at > last)) or 0
    return since < cooldown_msgs


def tip_credit_cents(db: Session, fan: Fan, now: datetime | None = None) -> int:
    now = now or utcnow()
    tips = db.scalar(select(func.coalesce(func.sum(Message.tip_cents), 0)).where(
        Message.fan_id == fan.id, Message.tip_cents.is_not(None), Message.sent_at >= now - timedelta(hours=24))) or 0
    used = db.scalar(select(func.coalesce(func.sum(PpvOffer.amount_cents), 0)).where(
        PpvOffer.fan_id == fan.id, PpvOffer.source == "tip_reward",
        PpvOffer.created_at >= now - timedelta(hours=24))) or 0
    return max(int(tips) - int(used), 0)


def eligible_templates(db: Session, fan: Fan, cooldown_msgs: int | None) -> list[PpvTemplate]:
    owned = owned_template_ids(db, fan.id)
    out = []
    for t in db.scalars(select(PpvTemplate).where(PpvTemplate.active.is_(True)).order_by(PpvTemplate.id)):
        if t.id in owned or gate_reason(t, fan) or on_cooldown(db, fan, t.id, cooldown_msgs):
            continue
        out.append(t)
    return out


def describe_for_prompt(db: Session, templates: list[PpvTemplate], fan: Fan) -> list[dict[str, object]]:
    tags = {t.id: t for t in db.scalars(select(PpvTag))}
    credit = tip_credit_cents(db, fan)
    out = []
    for t in templates:
        item: dict[str, object] = {
            "id": t.id, "description": t.description, "price_usd": round(t.price_cents / 100, 2),
            "tags": [f"{tags[i].name}: {tags[i].description}" if tags[i].description else tags[i].name
                     for i in t.tag_ids if i in tags],
        }
        if t.when_to_pitch:
            item["when_to_offer"] = t.when_to_pitch
        if t.teaser:
            item["fixed_teaser"] = t.teaser
        if t.tip_reward_cents and credit >= t.tip_reward_cents:
            item["free_as_tip_reward"] = True
        out.append(item)
    return out
