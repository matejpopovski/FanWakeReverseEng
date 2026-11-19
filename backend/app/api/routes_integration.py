"""Fanvue connection, sync, vault media, mock simulator, webhooks, logs, export."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.config import get_settings
from app.db import get_db, utcnow
from app.fanvue import get_client, oauth
from app.fanvue.base import FanvueError
from app.fanvue.mock import MockFanvueClient
from app.fanvue.webhooks import verify_signature
from app.models import AiUsage, AuditLog, Draft, Fan, Job, Message, MockFan, MockMedia, PpvOffer, WebhookEvent
from app.security import SESSION_COOKIE, check_session, require_operator
from app.services import jobs, sync

router = APIRouter(prefix="/api", dependencies=[Depends(require_operator)])
public = APIRouter(prefix="/api")


# ------------------------------------------------------------------------------------------------ Fanvue
@router.get("/fanvue/connection")
def connection(db: Session = Depends(get_db)) -> dict[str, Any]:
    s = get_settings()
    c = oauth.get_connection(db)
    db.commit()
    return {"mode": s.fanvue_mode, "status": c.status if s.fanvue_mode == "live" else "mock",
            "handle": c.handle, "display_name": c.display_name, "scopes": (c.scopes or s.fanvue_scopes).split(),
            "needs_reconnect": c.needs_reconnect, "expires_at": c.expires_at, "last_sync_at": c.last_sync_at,
            "last_error": c.last_error, "client_configured": bool(s.fanvue_client_id and s.fanvue_client_secret),
            "redirect_uri": s.fanvue_redirect_uri, "webhook_url": f"{s.public_base_url}/api/webhooks/fanvue",
            "webhook_secret_configured": bool(s.fanvue_webhook_secret)}


@router.post("/fanvue/connect")
def connect(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        url = oauth.build_authorize_url(db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return {"authorize_url": url}


@public.get("/fanvue/oauth/callback")
def oauth_callback(request: Request, state: str = "", code: str = "", error: str = "",
                   db: Session = Depends(get_db)) -> RedirectResponse:
    if not check_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(401, "Sign in to the app first, then connect Fanvue")
    if error:
        return RedirectResponse(f"/connect?error={error[:64]}")
    try:
        oauth.exchange_code(db, state, code)
        db.commit()
        me = get_client(db).get_me()
        c = oauth.get_connection(db)
        c.creator_uuid, c.handle, c.display_name = me.uuid, me.handle, me.display_name
        jobs.audit(db, "operator", "fanvue.connected", handle=me.handle)
        jobs.enqueue(db, "sync_fanvue", {}, idempotency_key=f"sync-after-connect-{utcnow():%Y%m%d%H%M%S}")
        db.commit()
    except (ValueError, FanvueError) as exc:
        db.rollback()
        return RedirectResponse(f"/connect?error={str(exc)[:120]}")
    return RedirectResponse("/connect?connected=1")


@router.post("/fanvue/disconnect")
def disconnect(db: Session = Depends(get_db)) -> dict[str, bool]:
    oauth.disconnect(db)
    jobs.audit(db, "operator", "fanvue.disconnected")
    db.commit()
    return {"ok": True}


@router.post("/fanvue/sync")
def sync_now(db: Session = Depends(get_db)) -> dict[str, Any]:
    rep = sync.sync(db, refresh_all_insights=True)
    return rep.__dict__


@router.get("/fanvue/media")
def media(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        items, cursor = get_client(db).list_media()
    except FanvueError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"items": [m.__dict__ for m in items], "next_cursor": cursor}


@public.get("/mock/media/{uuid}.svg")
def mock_media_svg(uuid: str, db: Session = Depends(get_db)) -> Response:
    m = db.get(MockMedia, uuid)
    if m is None:
        raise HTTPException(404)
    label = m.name.replace("&", "&amp;").replace("<", "&lt;")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="200"><rect width="160" height="200" '
           f'rx="12" fill="{m.color}"/><text x="80" y="104" font-family="sans-serif" font-size="14" fill="#fff" '
           f'text-anchor="middle">{label}</text><text x="80" y="124" font-family="sans-serif" font-size="11" '
           f'fill="#fff" text-anchor="middle" opacity=".8">{m.media_type}</text></svg>')
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


# ------------------------------------------------------------------------------------------------ mock simulator
class SimulateIn(BaseModel):
    fan_id: int
    text: str = Field(min_length=1, max_length=2000)
    tip: float | None = Field(default=None, ge=0, le=1000)
    sync_now: bool = True


def _require_mock() -> None:
    if get_settings().fanvue_mode != "mock":
        raise HTTPException(400, "The simulator is only available in mock mode")


@router.post("/mock/simulate-message")
def simulate_message(body: SimulateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_mock()
    fan = db.get(Fan, body.fan_id)
    if fan is None:
        raise HTTPException(404, "fan not found")
    client = MockFanvueClient(db)
    client.add_fan_message(fan.fanvue_uuid, body.text, tip_cents=int(body.tip * 100) if body.tip else None)
    db.commit()
    rep = sync.sync(db, client) if body.sync_now else None
    return {"ok": True, "sync": rep.__dict__ if rep else None}


class PurchaseIn(BaseModel):
    fan_id: int
    template_id: int


@router.post("/mock/simulate-purchase")
def simulate_purchase(body: PurchaseIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Mock-mode stand-in for a `creator.payment.succeeded` webhook on a pitched PPV."""
    _require_mock()
    fan = db.get(Fan, body.fan_id)
    if fan is None:
        raise HTTPException(404, "fan not found")
    offer = db.scalar(select(PpvOffer).where(PpvOffer.fan_id == fan.id, PpvOffer.template_id == body.template_id,
                                             PpvOffer.status == "pitched").order_by(PpvOffer.id.desc()))
    if offer is None:
        raise HTTPException(409, "no open offer for this template")
    from app.models import PpvTemplate

    tpl = db.get(PpvTemplate, body.template_id)
    amount = tpl.price_cents if tpl else 0
    offer.status, offer.purchased_at, offer.amount_cents = "purchased", utcnow(), amount
    fan.ppv_purchases += 1
    fan.total_spent_cents += amount
    fan.last_purchase_at = offer.purchased_at
    MockFanvueClient(db).record_purchase(fan.fanvue_uuid, amount)
    jobs.audit(db, "system", "ppv.purchased", "fan", fan.id, template_id=body.template_id, source="mock")
    db.commit()
    return {"ok": True}


@router.get("/mock/fans")
def mock_fans(db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_mock()
    return {"items": [{"uuid": f.uuid, "display_name": f.display_name, "status": f.status}
                      for f in db.scalars(select(MockFan).order_by(MockFan.display_name))]}


# ------------------------------------------------------------------------------------------------ webhooks
@public.post("/webhooks/fanvue")
async def fanvue_webhook(request: Request, db: Session = Depends(get_db)) -> Response:
    raw = await request.body()
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return Response(status_code=400)
    if payload.get("type") == "fanvue.webhook.verification":
        return Response(status_code=200)  # unsigned reachability probe
    secret = get_settings().fanvue_webhook_secret
    if not verify_signature(secret, request.headers.get("X-Fanvue-Signature"), raw):
        return Response(status_code=401)
    event_id = str(payload.get("id") or "")
    if not event_id or db.get(WebhookEvent, event_id) is not None:
        return Response(status_code=200)  # duplicate delivery
    db.add(WebhookEvent(id=event_id, type=str(payload.get("type", ""))[:64]))
    etype = payload.get("type", "")
    data = payload.get("data") or {}
    if etype in ("creator.message.received", "creator.message.sent"):
        # message bodies are fetched by the regular sync (single code path); just trigger it now
        jobs.enqueue(db, "sync_fanvue", {}, idempotency_key=f"sync-webhook-{event_id}")
    elif etype == "creator.payment.succeeded":
        jobs.audit(db, "system", "webhook.payment", detail_keys=sorted(data.keys())[:20])
        jobs.enqueue(db, "sync_fanvue", {}, idempotency_key=f"sync-webhook-{event_id}")
    db.commit()
    return Response(status_code=200)


# ------------------------------------------------------------------------------------------------ logs & export
@router.get("/logs/audit")
def audit_log(limit: int = Query(200, le=1000), action: str | None = None,
              db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    return {"items": [{"id": a.id, "at": a.at, "actor": a.actor, "action": a.action, "entity": a.entity,
                       "entity_id": a.entity_id, "detail": a.detail}
                      for a in db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit))]}


@router.get("/logs/jobs")
def job_log(status: str | None = None, limit: int = Query(200, le=1000),
            db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    return {"items": [{"id": j.id, "kind": j.kind, "status": j.status, "attempts": j.attempts, "run_at": j.run_at,
                       "last_error": j.last_error, "payload": j.payload, "updated_at": j.updated_at}
                      for j in db.scalars(stmt.order_by(Job.id.desc()).limit(limit))]}


@router.post("/logs/jobs/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    j = db.get(Job, job_id)
    if j is None or j.status not in ("dead", "failed"):
        raise HTTPException(409, "only dead/failed jobs can be retried")
    j.status, j.run_at, j.attempts = "queued", utcnow(), 0
    db.commit()
    return {"ok": True}


@router.get("/logs/usage")
def usage_log(limit: int = Query(200, le=1000), db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": [{"id": u.id, "at": u.at, "provider": u.provider, "model": u.model, "purpose": u.purpose,
                       "tokens_in": u.tokens_in, "tokens_out": u.tokens_out, "cost_usd": u.cost_usd,
                       "latency_ms": u.latency_ms, "ok": u.ok, "error": u.error, "draft_id": u.draft_id}
                      for u in db.scalars(select(AiUsage).order_by(AiUsage.id.desc()).limit(limit))]}


@router.get("/export")
def export(db: Session = Depends(get_db)) -> Response:
    """Full JSON export of local CRM data (no tokens or secrets)."""
    data = {
        "exported_at": utcnow().isoformat(),
        "fans": [ser.fan_detail(f) for f in db.scalars(select(Fan))],
        "messages": [ser.message(m) for m in db.scalars(select(Message))],
        "drafts": [ser.draft(d) for d in db.scalars(select(Draft))],
    }
    body = json.dumps(data, default=str, ensure_ascii=False)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="wakeful-export.json"'})
