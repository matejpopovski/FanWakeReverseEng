"""Scheduled AI check-ins: drafted when due, skipped if the conversation moved on."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Checkin, Fan
from app.services import engine
from app.settings_store import EngineSettings, load


def process_due(db: Session) -> int:
    eng = load(db, EngineSettings)
    n = 0
    for c in db.scalars(select(Checkin).where(Checkin.status == "planned", Checkin.scheduled_at <= utcnow())):
        fan = db.get(Fan, c.fan_id)
        if fan is None or not eng.enabled or not eng.checkins_enabled or fan.escalated or not fan.autopilot_enabled:
            c.status = "skipped"
            continue
        # moment passed: the fan wrote again after the check-in was planned
        if fan.last_inbound_at and fan.last_inbound_at > c.created_at:
            c.status = "skipped"
            continue
        draft = engine.create_draft(db, fan, "checkin", extra=c.intent)
        c.status = "drafted" if draft else "skipped"
        c.draft_id = draft.id if draft else None
        n += 1
        db.commit()
    db.commit()
    return n
