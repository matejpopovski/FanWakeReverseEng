"""Automatic PPV purchase detection through the official Fanvue API.

Fanvue's message objects do not say whether a paid message was unlocked, but
``GET /v1/media/{uuid}?purchasedBy={fanUuid}`` returns ``purchasedByFan``. For every template that was offered to a
fan and is not yet recorded as bought, we check the template's main media; if the fan owns all of it, the offer is
marked purchased (source ``detected``) so the item is never offered again and sales stats stay accurate.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue.base import FanvueClient, FanvueError
from app.models import Fan, PpvOffer, PpvTemplate
from app.services import jobs

LOOKBACK = timedelta(days=30)  # only check offers made in the last 30 days
RECHECK_AFTER = timedelta(hours=1)


def detect_for_fan(db: Session, client: FanvueClient, fan: Fan, force: bool = False) -> int:
    """Returns the number of newly detected purchases."""
    now = utcnow()
    if not force and fan.purchases_checked_at and now - fan.purchases_checked_at < RECHECK_AFTER:
        return 0
    open_offers = list(db.scalars(select(PpvOffer).where(
        PpvOffer.fan_id == fan.id, PpvOffer.status == "pitched", PpvOffer.pitched_at >= now - LOOKBACK)
        .order_by(PpvOffer.pitched_at.desc())))
    fan.purchases_checked_at = now
    found = 0
    seen_templates: set[int] = set()
    for offer in open_offers:
        if offer.template_id in seen_templates:
            continue
        seen_templates.add(offer.template_id)
        tpl = db.get(PpvTemplate, offer.template_id)
        if tpl is None or not tpl.media_uuids:
            continue
        try:
            owned = all(client.media_purchased_by(fan.fanvue_uuid, m) for m in tpl.media_uuids[:3])
        except FanvueError:
            continue
        if not owned:
            continue
        offer.status = "purchased"
        offer.source = "detected"
        offer.purchased_at = now
        offer.amount_cents = tpl.price_cents
        fan.ppv_purchases += 1
        fan.last_purchase_at = now
        found += 1
        jobs.audit(db, "system", "ppv.purchase_detected", "fan", fan.id, template_id=tpl.id)
    return found


def detect_recent(db: Session, client: FanvueClient, limit: int = 50) -> int:
    """Periodic sweep: fans with open offers from the last 30 days."""
    fan_ids = list(db.scalars(select(PpvOffer.fan_id).where(
        PpvOffer.status == "pitched", PpvOffer.pitched_at >= utcnow() - LOOKBACK).distinct().limit(limit)))
    total = 0
    for fid in fan_ids:
        fan = db.get(Fan, fid)
        if fan is not None:
            total += detect_for_fan(db, client, fan)
            db.commit()
    return total
