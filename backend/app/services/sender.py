"""Sending approved drafts through the Fanvue client, idempotently and with all safety gates."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.fanvue import get_client
from app.fanvue.base import FanvueClient, FanvueError, NeedsReconnect, NotContactable
from app.models import Draft, Fan, Message, PpvOffer
from app.services import jobs
from app.services.engine import add_alert, auto_send_allowed
from app.settings_store import SafetySettings, load

ORIGIN = {"reply": "ai_reply", "reengage": "ai_reengage", "checkin": "ai_checkin", "manual": "operator"}


class SendBlocked(Exception):
    pass


def check_gates(db: Session, draft: Draft, fan: Fan) -> None:
    safety = load(db, SafetySettings)
    if get_settings().fanvue_mode == "live" and not safety.live_sending_enabled:
        raise SendBlocked("Live sending is disabled in Settings → Safety. Nothing was sent.")
    if draft.approved_by == "auto":
        ok, why = auto_send_allowed(db, fan)
        if not ok:
            raise SendBlocked(why)
    if fan.status == "not_contactable":
        raise SendBlocked("fan is not contactable")


def send_draft(db: Session, draft_id: int, client: FanvueClient | None = None, bubble_gap_s: float = 2.0) -> Draft:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise ValueError("draft not found")
    if draft.status == "sent":
        return draft  # idempotent
    if draft.status not in ("approved", "sending"):
        raise SendBlocked(f"draft is {draft.status}, not approved")
    fan = db.get(Fan, draft.fan_id)
    assert fan is not None
    try:
        check_gates(db, draft, fan)
    except SendBlocked as exc:
        draft.status = "pending"
        draft.route_reason = f"held: {exc}"
        draft.approved_by = None
        jobs.audit(db, "worker", "draft.send_held", "draft", draft.id, reason=str(exc))
        db.commit()
        raise

    client = client or get_client(db)
    draft.status = "sending"
    db.commit()
    origin = ORIGIN.get(draft.kind, "ai_reply")
    try:
        for i in range(draft.sent_bubbles, len(draft.bubbles)):
            last = i == len(draft.bubbles) - 1
            attach = last and (draft.media_uuids or draft.price_cents)
            tpl_preview = None
            if attach and draft.ppv_template_id:
                from app.models import PpvTemplate

                tpl = db.get(PpvTemplate, draft.ppv_template_id)
                tpl_preview = tpl.preview_media_uuid if tpl else None
            if i > 0 and bubble_gap_s:
                time.sleep(bubble_gap_s)
            uuid = client.send_message(fan.fanvue_uuid, draft.bubbles[i],
                                       media_uuids=draft.media_uuids if attach else None,
                                       price_cents=draft.price_cents if attach else None,
                                       preview_media_uuid=tpl_preview)
            now = utcnow()
            db.add(Message(fan_id=fan.id, fanvue_uuid=uuid, direction="out", text=draft.bubbles[i], sent_at=now,
                           media_uuids=list(draft.media_uuids) if attach else [],
                           price_cents=draft.price_cents if attach else None, origin=origin, draft_id=draft.id))
            draft.sent_bubbles = i + 1
            fan.last_outbound_at = now
            db.commit()  # persist progress per bubble -> retries never double-send
    except NotContactable as exc:
        draft.status = "failed"
        draft.error = str(exc)
        fan.status = "not_contactable"
        if draft.kind == "reengage":
            fan.reengage_state = "unreachable"
        jobs.audit(db, "worker", "draft.failed", "draft", draft.id, error="not_contactable")
        db.commit()
        return draft
    except NeedsReconnect as exc:
        draft.status = "approved"
        draft.error = str(exc)
        add_alert(db, None, "system", "fanvue_auth", "Fanvue connection needs to be re-authorised.")
        db.commit()
        raise
    except FanvueError as exc:
        draft.error = str(exc)
        if exc.retryable:
            draft.status = "approved"
            db.commit()
            raise
        draft.status = "failed"
        if draft.kind == "reengage":
            fan.reengage_state = "failed"
        jobs.audit(db, "worker", "draft.failed", "draft", draft.id, error=str(exc)[:200])
        db.commit()
        return draft

    draft.status = "sent"
    draft.sent_at = utcnow()
    draft.error = None
    if draft.ppv_template_id:
        db.add(PpvOffer(fan_id=fan.id, template_id=draft.ppv_template_id, draft_id=draft.id, status="pitched",
                        source="ai", pitched_at=draft.sent_at,
                        amount_cents=None if draft.price_cents else 0))
    if draft.kind == "reengage":
        fan.reengage_last_sent_at = draft.sent_at
    jobs.audit(db, "worker", "draft.sent", "draft", draft.id, fan_id=fan.id, approved_by=draft.approved_by,
               bubbles=len(draft.bubbles), ppv=draft.ppv_template_id)
    db.commit()
    return draft
