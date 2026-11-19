"""PPV eligibility: which templates may be offered to a given fan right now."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
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


def on_cooldown(db: Session, fan: Fan, template_id: int, cooldown_msgs: int | None,
                cooldown_hours: int | None = None, now: datetime | None = None) -> bool:
    """An unpurchased template may be re-offered only after BOTH the message and the time cooldown."""
    last = db.scalar(select(func.max(PpvOffer.pitched_at)).where(
        PpvOffer.fan_id == fan.id, PpvOffer.template_id == template_id, PpvOffer.status == "pitched"))
    if last is None:
        return False
    if cooldown_msgs is None:
        return True  # never re-pitch unpurchased templates
    if cooldown_hours and (now or utcnow()) - last < timedelta(hours=cooldown_hours):
        return True
    since = db.scalar(select(func.count()).select_from(Message)
                      .where(Message.fan_id == fan.id, Message.sent_at > last)) or 0
    return since < cooldown_msgs


def offer_gap_reason(db: Session, fan: Fan, min_gap_hours: int, now: datetime | None = None) -> str | None:
    """Why no offer may be made right now (minimum gap between any two offers to the same fan), or None."""
    from app.models import Draft

    # approved/sending offers are on their way; a pending reply draft doesn't count because a new reply replaces it
    in_flight = db.scalar(select(Draft.id).where(
        Draft.fan_id == fan.id, Draft.ppv_template_id.is_not(None),
        or_(Draft.status.in_(("approved", "sending")), (Draft.status == "pending") & (Draft.kind != "reply"))))
    if in_flight:
        return "an offer for this fan is already waiting to be sent"
    if not min_gap_hours:
        return None
    last = db.scalar(select(func.max(PpvOffer.pitched_at)).where(PpvOffer.fan_id == fan.id))
    if last is None:
        return None
    elapsed = (now or utcnow()) - last
    if elapsed < timedelta(hours=min_gap_hours):
        return f"last offer was {elapsed.total_seconds() / 3600:.1f}h ago (minimum gap {min_gap_hours}h)"
    return None


def tip_credit_cents(db: Session, fan: Fan, now: datetime | None = None) -> int:
    now = now or utcnow()
    tips = db.scalar(select(func.coalesce(func.sum(Message.tip_cents), 0)).where(
        Message.fan_id == fan.id, Message.tip_cents.is_not(None), Message.sent_at >= now - timedelta(hours=24))) or 0
    used = db.scalar(select(func.coalesce(func.sum(PpvOffer.amount_cents), 0)).where(
        PpvOffer.fan_id == fan.id, PpvOffer.source == "tip_reward",
        PpvOffer.created_at >= now - timedelta(hours=24))) or 0
    return max(int(tips) - int(used), 0)


def eligible_templates(db: Session, fan: Fan, cooldown_msgs: int | None, cooldown_hours: int | None = None,
                       min_gap_hours: int = 0) -> list[PpvTemplate]:
    if offer_gap_reason(db, fan, min_gap_hours):
        return []
    owned = owned_template_ids(db, fan.id)
    out = []
    for t in db.scalars(select(PpvTemplate).where(PpvTemplate.active.is_(True)).order_by(PpvTemplate.id)):
        if t.id in owned or gate_reason(t, fan) or on_cooldown(db, fan, t.id, cooldown_msgs, cooldown_hours):
            continue
        out.append(t)
    return out


def template_performance(db: Session) -> dict[int, dict[str, float]]:
    """Offers, sales and conversion per template across all fans."""
    out: dict[int, dict[str, float]] = {}
    for tid, status, n in db.execute(select(PpvOffer.template_id, PpvOffer.status, func.count())
                                     .group_by(PpvOffer.template_id, PpvOffer.status)).all():
        s = out.setdefault(tid, {"offers": 0, "sales": 0})
        s["offers"] += n
        if status == "purchased":
            s["sales"] += n
    for s in out.values():
        s["conversion_pct"] = round(s["sales"] / s["offers"] * 100) if s["offers"] else 0
    return out


def fan_buying_profile(db: Session, fan: Fan) -> str:
    """Short, factual summary of what kinds of content this fan bought or passed on (by tag)."""
    tags = {t.id: t.name for t in db.scalars(select(PpvTag))}
    bought: dict[str, int] = {}
    passed: dict[str, int] = {}
    offers = db.scalars(select(PpvOffer).where(PpvOffer.fan_id == fan.id))
    tpl_tags = {t.id: t.tag_ids or [] for t in db.scalars(select(PpvTemplate))}
    for o in offers:
        target = bought if o.status == "purchased" else passed
        for tid in tpl_tags.get(o.template_id, []) or [-1]:
            name = tags.get(tid, "untagged")
            target[name] = target.get(name, 0) + 1
    if not bought and not passed:
        return ""
    fmt = lambda d: ", ".join(f"{k} x{v}" for k, v in sorted(d.items(), key=lambda kv: -kv[1]))  # noqa: E731
    parts = []
    if bought:
        parts.append(f"bought before: {fmt(bought)}")
    if passed:
        parts.append(f"offered but not bought: {fmt(passed)}")
    return "; ".join(parts)


def describe_for_prompt(db: Session, templates: list[PpvTemplate], fan: Fan) -> list[dict[str, object]]:
    tags = {t.id: t for t in db.scalars(select(PpvTag))}
    credit = tip_credit_cents(db, fan)
    perf = template_performance(db)
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
        p = perf.get(t.id)
        if p and p["offers"] >= 3:
            item["track_record"] = f"{int(p['sales'])}/{int(p['offers'])} offers bought ({int(p['conversion_pct'])}%)"
        else:
            item["track_record"] = "new, little data yet"
        out.append(item)
    return out
