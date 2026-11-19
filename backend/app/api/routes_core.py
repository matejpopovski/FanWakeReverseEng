"""Auth, health, dashboard, fans, conversations, alerts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.config import get_settings
from app.db import get_db, utcnow
from app.fanvue.oauth import get_connection
from app.models import AiUsage, Alert, Checkin, Draft, Fan, Message, PpvOffer, PpvTemplate
from app.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    auth_enabled,
    issue_session,
    require_operator,
    verify_password,
)
from app.services import jobs, ppv
from app.services.metrics import fan_metrics
from app.settings_store import EngineSettings, ReengageSettings, SafetySettings, load

public = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_operator)])


# ------------------------------------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    password: str


@public.post("/auth/login")
def login(body: LoginIn, response: Response) -> dict[str, bool]:
    if not auth_enabled():
        return {"ok": True}
    if not verify_password(body.password):
        raise HTTPException(401, "Wrong password")
    response.set_cookie(SESSION_COOKIE, issue_session(), max_age=SESSION_MAX_AGE, httponly=True,
                        samesite="strict", secure=get_settings().public_base_url.startswith("https"))
    return {"ok": True}


@public.post("/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@public.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    db.execute(select(1))
    s = get_settings()
    return {"ok": True, "mode": s.fanvue_mode, "ai_provider": s.ai_provider}


# ------------------------------------------------------------------------------------------------ status
@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_settings()
    safety = load(db, SafetySettings)
    eng = load(db, EngineSettings)
    re_s = load(db, ReengageSettings)
    conn = get_connection(db)
    return {
        "mode": s.fanvue_mode, "ai_provider": s.ai_provider,
        "ai_model": {"mock": "mock-1", "anthropic": s.anthropic_model, "openai": s.openai_model}[s.ai_provider],
        "automation_paused": safety.automation_paused, "live_sending_enabled": safety.live_sending_enabled,
        "autopilot_enabled": eng.enabled, "autopilot_mode": eng.approval_mode,
        "reengage_enabled": re_s.enabled, "reengage_mode": re_s.approval_mode,
        "connection": {"status": conn.status if s.fanvue_mode == "live" else "mock",
                       "handle": conn.handle, "needs_reconnect": conn.needs_reconnect,
                       "last_sync_at": conn.last_sync_at, "last_error": conn.last_error},
        "pending_drafts": db.scalar(select(func.count()).select_from(Draft).where(Draft.status == "pending")),
        "open_alerts": db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open")),
    }


# ------------------------------------------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard(days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db)) -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(days=days)
    total = db.scalar(select(func.count()).select_from(Fan)) or 0
    kpis = {
        "total_fans": total,
        "subscribers": db.scalar(select(func.count()).select_from(Fan).where(Fan.status == "subscriber")) or 0,
        "in_reengagement": db.scalar(select(func.count()).select_from(Fan).where(Fan.reengage_state == "active")) or 0,
        "awakened": db.scalar(select(func.count()).select_from(Fan).where(Fan.reengage_state == "awakened")) or 0,
        "pending_review": db.scalar(select(func.count()).select_from(Draft).where(Draft.status == "pending")) or 0,
        "scheduled": db.scalar(select(func.count()).select_from(Checkin).where(Checkin.status == "planned")) or 0,
        "escalated": db.scalar(select(func.count()).select_from(Fan).where(Fan.escalated.is_(True))) or 0,
    }
    ai_out = Message.origin.in_(("ai_reply", "ai_reengage", "ai_checkin"))
    day = func.date(Message.sent_at)
    rows = db.execute(select(day, func.sum(case((ai_out, 1), else_=0)), func.sum(case((Message.direction == "in", 1),
                                                                                    else_=0)))
                      .where(Message.sent_at >= since).group_by(day).order_by(day)).all()
    rev_rows = db.execute(select(func.date(PpvOffer.purchased_at), func.sum(PpvOffer.amount_cents))
                          .where(PpvOffer.status == "purchased", PpvOffer.purchased_at >= since)
                          .group_by(func.date(PpvOffer.purchased_at))).all()
    rev = {str(d): (c or 0) / 100 for d, c in rev_rows}
    series = [{"date": str(d), "ai_sent": int(a or 0), "inbound": int(i or 0), "revenue": rev.get(str(d), 0)}
              for d, a, i in rows]
    pitches = db.scalar(select(func.count()).select_from(PpvOffer).where(PpvOffer.pitched_at >= since)) or 0
    sales = db.scalar(select(func.count()).select_from(PpvOffer).where(PpvOffer.status == "purchased",
                                                                     PpvOffer.purchased_at >= since)) or 0
    revenue = sum(rev.values())
    ai_msgs = db.scalar(select(func.count()).select_from(Message).where(ai_out, Message.sent_at >= since)) or 0
    usage = db.execute(select(func.coalesce(func.sum(AiUsage.tokens_in), 0), func.coalesce(func.sum(AiUsage.tokens_out), 0),
                              func.coalesce(func.sum(AiUsage.cost_usd), 0.0), func.count())
                       .where(AiUsage.at >= since)).one()
    top_spend = [ser.fan_summary(f) for f in db.scalars(select(Fan).order_by(Fan.total_spent_cents.desc()).limit(5))]
    msg_count = func.count(Message.id)
    top_msgs = [{"fan": ser.fan_summary(f), "messages": n} for f, n in db.execute(
        select(Fan, msg_count).join(Message, Message.fan_id == Fan.id).group_by(Fan.id)
        .order_by(msg_count.desc()).limit(5)).all()]
    tpl_stats = template_stats(db)
    top_templates = sorted(tpl_stats.items(), key=lambda kv: kv[1]["revenue"], reverse=True)[:3]
    names = {t.id: t.name for t in db.scalars(select(PpvTemplate))}
    return {
        "kpis": kpis, "series": series,
        "totals": {"ai_messages": ai_msgs, "revenue": revenue, "pitches": pitches, "sales": sales,
                   "conversion": round(sales / pitches * 100, 1) if pitches else 0.0},
        "ai_usage": {"tokens_in": usage[0], "tokens_out": usage[1], "cost_usd": round(float(usage[2]), 4),
                     "calls": usage[3]},
        "top_fans_by_spend": top_spend, "top_fans_by_messages": top_msgs,
        "top_templates": [{"id": k, "name": names.get(k, "?"), **v} for k, v in top_templates],
        "recent": [ser.draft(d, d.fan) for d in db.scalars(select(Draft).where(Draft.status == "sent")
                                                            .order_by(Draft.sent_at.desc()).limit(8))],
    }


def template_stats(db: Session) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for tid, status, n, amt in db.execute(select(PpvOffer.template_id, PpvOffer.status, func.count(),
                                                 func.coalesce(func.sum(PpvOffer.amount_cents), 0))
                                          .group_by(PpvOffer.template_id, PpvOffer.status)).all():
        s = out.setdefault(tid, {"pitches": 0, "sales": 0, "revenue": 0.0})
        if status == "purchased":
            s["sales"] += n
            s["revenue"] += (amt or 0) / 100
        s["pitches"] += n
    for s in out.values():
        s["conversion"] = round(s["sales"] / s["pitches"] * 100, 1) if s["pitches"] else 0.0
    return out


# ------------------------------------------------------------------------------------------------ fans
SEGMENTS: dict[str, Any] = {
    "all": None, "subscribers": Fan.status == "subscriber", "expired": Fan.status == "expired",
    "followers": Fan.status == "follower", "in_reengagement": Fan.reengage_state == "active",
    "awakened": Fan.reengage_state == "awakened", "autopilot_on": Fan.autopilot_enabled.is_(True),
    "vip": Fan.total_spent_cents >= ser.VIP_CENTS, "escalated": Fan.escalated.is_(True),
    "unreachable": Fan.status == "not_contactable",
}


@router.get("/fans")
def list_fans(q: str = "", segment: str = "all", sort: str = "last_active", offset: int = 0,
              limit: int = Query(100, le=500), db: Session = Depends(get_db)) -> dict[str, Any]:
    if segment not in SEGMENTS:
        raise HTTPException(400, "unknown segment")
    stmt = select(Fan)
    cond = SEGMENTS[segment]
    if cond is not None:
        stmt = stmt.where(cond)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Fan.display_name).like(like), func.lower(Fan.handle).like(like)))
    order: Any = {"last_active": Fan.last_inbound_at.desc().nullslast(), "spend": Fan.total_spent_cents.desc(),
             "name": func.lower(Fan.display_name)}.get(sort, Fan.last_inbound_at.desc().nullslast())
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(order, Fan.id).offset(offset).limit(limit))
    return {"total": total, "items": [ser.fan_summary(f) for f in rows]}


@router.get("/fans/{fan_id}")
def get_fan(fan_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    fan = _fan(db, fan_id)
    d = ser.fan_detail(fan)
    d["metrics"] = fan_metrics(db, fan)
    eng = load(db, EngineSettings)
    owned = ppv.owned_template_ids(db, fan.id)
    pitched = set(db.scalars(select(PpvOffer.template_id).where(PpvOffer.fan_id == fan.id)))
    eligible = ppv.eligible_templates(db, fan, eng.repitch_cooldown_msgs)
    d["content"] = {
        "owned_template_ids": sorted(owned), "pitched_template_ids": sorted(pitched - owned),
        "eligible_template_ids": [t.id for t in eligible],
        "offers": [{"id": o.id, "template_id": o.template_id, "status": o.status, "source": o.source,
                    "pitched_at": o.pitched_at, "purchased_at": o.purchased_at,
                    "amount": (o.amount_cents or 0) / 100}
                   for o in db.scalars(select(PpvOffer).where(PpvOffer.fan_id == fan.id)
                                       .order_by(PpvOffer.created_at.desc()))],
    }
    d["alerts"] = [ser.alert(a) for a in db.scalars(select(Alert).where(Alert.fan_id == fan.id)
                                                    .order_by(Alert.created_at.desc()).limit(20))]
    d["checkins"] = [ser.checkin(c) for c in db.scalars(select(Checkin).where(Checkin.fan_id == fan.id)
                                                        .order_by(Checkin.scheduled_at.desc()).limit(10))]
    d["reengage_messages"] = [ser.message(m) for m in db.scalars(
        select(Message).where(Message.fan_id == fan.id, Message.origin == "ai_reengage")
        .order_by(Message.sent_at))]
    return d


class FanPatch(BaseModel):
    autopilot_enabled: bool | None = None
    review_mode: str | None = Field(default=None, pattern="^(inherit|manual|auto)$")
    reengage_enabled: bool | None = None
    ppv_enabled: bool | None = None
    pacing_override_min: int | None = Field(default=None, ge=0, le=30)
    custom_approach: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = None
    memory: str | None = Field(default=None, max_length=3000)
    escalated: bool | None = None


@router.patch("/fans/{fan_id}")
def patch_fan(fan_id: int, body: FanPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    fan = _fan(db, fan_id)
    data = body.model_dump(exclude_unset=True)
    if "pacing_override_min" in data and data["pacing_override_min"] == 0:
        data["pacing_override_min"] = None
    if "tags" in data and data["tags"] is not None:
        data["tags"] = sorted({t.strip()[:32] for t in data["tags"] if t.strip()})[:20]
    if data.get("escalated") is False:
        fan.escalation_reason = None
        for a in db.scalars(select(Alert).where(Alert.fan_id == fan.id, Alert.kind == "escalation",
                                                Alert.status == "open")):
            a.status = "handled"
            a.handled_at = utcnow()
    for k, v in data.items():
        setattr(fan, k, v)
    jobs.audit(db, "operator", "fan.updated", "fan", fan.id, fields=sorted(data))
    db.commit()
    return ser.fan_detail(fan)


@router.post("/fans/bulk-autopilot")
def bulk_autopilot(enabled: bool, segment: str = "all", db: Session = Depends(get_db)) -> dict[str, int]:
    stmt = select(Fan)
    cond = SEGMENTS.get(segment)
    if cond is not None:
        stmt = stmt.where(cond)
    n = 0
    for f in db.scalars(stmt):
        f.autopilot_enabled = enabled
        n += 1
    jobs.audit(db, "operator", "fan.bulk_autopilot", segment=segment, enabled=enabled, count=n)
    db.commit()
    return {"updated": n}


@router.delete("/fans/{fan_id}/data")
def forget_fan(fan_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    """Erase local data for a fan (messages, drafts, memory, notes). Fanvue data is untouched."""
    fan = _fan(db, fan_id)
    for model in (Message, Draft, Alert, Checkin, PpvOffer):
        db.query(model).filter(model.fan_id == fan.id).delete()  # type: ignore[attr-defined]
    fan.memory = fan.notes = fan.next_move = fan.custom_approach = ""
    fan.tags = []
    fan.last_synced_message_uuid = None
    jobs.audit(db, "operator", "fan.forgotten", "fan", fan.id)
    db.commit()
    return {"ok": True}


def _fan(db: Session, fan_id: int) -> Fan:
    fan = db.get(Fan, fan_id)
    if fan is None:
        raise HTTPException(404, "fan not found")
    return fan


# ------------------------------------------------------------------------------------------------ conversations
@router.get("/conversations")
def conversations(q: str = "", filter: str = "all", limit: int = Query(50, le=200), offset: int = 0,
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    last_at = func.max(Message.sent_at).label("last_at")
    sub = select(Message.fan_id, last_at).group_by(Message.fan_id).subquery()
    stmt = select(Fan, sub.c.last_at).join(sub, sub.c.fan_id == Fan.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Fan.display_name).like(like), func.lower(Fan.handle).like(like)))
    if filter == "needs_reply":
        stmt = stmt.where(Fan.last_inbound_at.is_not(None),
                          or_(Fan.last_outbound_at.is_(None), Fan.last_inbound_at > Fan.last_outbound_at))
    elif filter == "escalated":
        stmt = stmt.where(Fan.escalated.is_(True))
    rows = db.execute(stmt.order_by(sub.c.last_at.desc()).offset(offset).limit(limit)).all()
    pending = dict(db.execute(select(Draft.fan_id, func.count()).where(Draft.status == "pending")
                              .group_by(Draft.fan_id)).all())
    items = []
    for f, ts in rows:
        last = db.scalar(select(Message).where(Message.fan_id == f.id).order_by(Message.sent_at.desc(),
                                                                              Message.id.desc()))
        items.append({"fan": ser.fan_summary(f), "last_at": ts,
                      "last_message": ser.message(last) if last else None,
                      "pending_drafts": pending.get(f.id, 0)})
    return {"items": items}


@router.get("/conversations/{fan_id}/messages")
def conversation_messages(fan_id: int, before_id: int | None = None, limit: int = Query(50, le=200),
                          db: Session = Depends(get_db)) -> dict[str, Any]:
    _fan(db, fan_id)
    stmt = select(Message).where(Message.fan_id == fan_id)
    if before_id:
        stmt = stmt.where(Message.id < before_id)
    rows = list(db.scalars(stmt.order_by(Message.sent_at.desc(), Message.id.desc()).limit(limit)))
    return {"items": [ser.message(m) for m in reversed(rows)], "has_more": len(rows) == limit}


# ------------------------------------------------------------------------------------------------ alerts
@router.get("/alerts")
def list_alerts(status: str = "open", kind: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Alert)
    if status != "all":
        stmt = stmt.where(Alert.status == status)
    if kind:
        stmt = stmt.where(Alert.kind == kind)
    return {"items": [ser.alert(a) for a in db.scalars(stmt.order_by(Alert.created_at.desc()).limit(200))]}


@router.post("/alerts/{alert_id}/handle")
def handle_alert(alert_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Alert, alert_id)
    if a is None:
        raise HTTPException(404, "alert not found")
    a.status = "handled"
    a.handled_at = utcnow()
    db.commit()
    return ser.alert(a)


@router.post("/alerts/handle-all")
def handle_all(kind: str = "nudge", db: Session = Depends(get_db)) -> dict[str, int]:
    n = 0
    for a in db.scalars(select(Alert).where(Alert.status == "open", Alert.kind == kind)):
        a.status = "handled"
        a.handled_at = utcnow()
        n += 1
    db.commit()
    return {"handled": n}


@router.get("/checkins")
def list_checkins(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": [ser.checkin(c) for c in db.scalars(select(Checkin).where(Checkin.status == "planned")
                                                         .order_by(Checkin.scheduled_at))]}


@router.post("/checkins/{cid}/cancel")
def cancel_checkin(cid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    c = db.get(Checkin, cid)
    if c is None:
        raise HTTPException(404, "check-in not found")
    c.status = "cancelled"
    jobs.audit(db, "operator", "checkin.cancelled", "checkin", cid)
    db.commit()
    return ser.checkin(c)


@router.get("/auth/session")
def session_ok() -> dict[str, bool]:
    return {"ok": True, "auth_enabled": auth_enabled()}

