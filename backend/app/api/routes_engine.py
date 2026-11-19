"""Drafts/review, settings, persona, rules, PPV, re-engagement."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.prompts import SAFETY_BLOCK, persona_prompt
from app.ai.providers import ProviderError
from app.api import serializers as ser
from app.api.routes_core import template_stats
from app.db import get_db, utcnow
from app.models import CustomRule, Draft, Fan, PpvOffer, PpvTag, PpvTemplate, PromptVersion
from app.security import require_operator
from app.services import engine, jobs, reengage
from app.services.rules import ACTIONS, MAX_RULES, validate_rule
from app.settings_store import DOCS, Persona, load, save

router = APIRouter(prefix="/api", dependencies=[Depends(require_operator)])


# ------------------------------------------------------------------------------------------------ drafts
@router.get("/drafts")
def list_drafts(status: str = "pending", kind: str | None = None, fan_id: int | None = None,
                limit: int = Query(100, le=500), db: Session = Depends(get_db)) -> dict[str, Any]:
    stmt = select(Draft)
    if status == "archive":
        stmt = stmt.where(Draft.status.in_(("rejected", "replaced", "expired", "failed")))
    elif status == "sent":
        stmt = stmt.where(Draft.status == "sent")
    elif status != "all":
        stmt = stmt.where(Draft.status == status)
    if kind:
        stmt = stmt.where(Draft.kind == kind)
    if fan_id:
        stmt = stmt.where(Draft.fan_id == fan_id)
    order = Draft.sent_at.desc() if status == "sent" else Draft.created_at.desc()
    rows = db.scalars(stmt.order_by(order, Draft.id.desc()).limit(limit))
    return {"items": [ser.draft(d, d.fan) for d in rows]}


class ApproveIn(BaseModel):
    bubbles: list[str] | None = Field(default=None, max_length=3)
    drop_offer: bool = False


@router.post("/drafts/{draft_id}/approve")
def approve(draft_id: int, body: ApproveIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _draft(db, draft_id)
    if d.status != "pending":
        raise HTTPException(409, f"draft is {d.status}")
    if body.bubbles is not None:
        bubbles = [b.strip() for b in body.bubbles if b.strip()]
        if not bubbles:
            raise HTTPException(422, "at least one non-empty message is required")
        if bubbles != d.bubbles:
            d.bubbles = bubbles
            d.edited = True
    if body.drop_offer:
        d.ppv_template_id = None
        d.price_cents = None
        d.media_uuids = []
    d.status = "approved"
    d.approved_by = "operator"
    jobs.audit(db, "operator", "draft.approved", "draft", d.id, edited=d.edited)
    jobs.enqueue(db, "send_draft", {"draft_id": d.id}, idempotency_key=f"send-draft-{d.id}")
    db.commit()
    return ser.draft(d, d.fan)


class RejectIn(BaseModel):
    reason: str = Field(default="", max_length=500)


@router.post("/drafts/{draft_id}/reject")
def reject(draft_id: int, body: RejectIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _draft(db, draft_id)
    if d.status not in ("pending", "approved"):
        raise HTTPException(409, f"draft is {d.status}")
    d.status = "rejected"
    d.reject_reason = body.reason or None
    jobs.cancel_jobs(db, "send_draft", draft_id=d.id)
    jobs.audit(db, "operator", "draft.rejected", "draft", d.id, reason=body.reason[:100])
    db.commit()
    return ser.draft(d, d.fan)


@router.post("/drafts/{draft_id}/recover")
def recover(draft_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    d = _draft(db, draft_id)
    if d.status not in ("rejected", "replaced", "expired", "failed"):
        raise HTTPException(409, f"draft is {d.status}")
    engine.supersede_pending(db, d.fan_id, d.kind)
    # a failed draft keeps sent_bubbles so already-delivered bubbles are never re-sent
    d.status = "pending"
    d.approved_by = None
    d.error = None
    d.created_at = utcnow()
    jobs.audit(db, "operator", "draft.recovered", "draft", d.id)
    db.commit()
    return ser.draft(d, d.fan)


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    d = _draft(db, draft_id)
    if d.status in ("approved", "sending", "sent"):
        raise HTTPException(409, "sent or in-flight drafts cannot be deleted")
    db.delete(d)
    db.commit()
    return {"ok": True}


class GenerateIn(BaseModel):
    kind: str = Field(default="reply", pattern="^(reply|reengage)$")


@router.post("/fans/{fan_id}/generate")
def generate_for_fan(fan_id: int, body: GenerateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Operator asks for an AI suggestion now. Always lands in review (never auto-sent)."""
    fan = db.get(Fan, fan_id)
    if fan is None:
        raise HTTPException(404, "fan not found")
    try:
        d = engine.create_draft(db, fan, body.kind, force_review=True)
    except ProviderError as exc:
        db.commit()
        raise HTTPException(502, f"AI provider error: {exc}") from exc
    db.commit()
    if d is None:
        raise HTTPException(409, "No draft created (fan escalated, budget or queue limit). See alerts.")
    return ser.draft(d, fan)


class ComposeIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@router.post("/fans/{fan_id}/compose")
def compose(fan_id: int, body: ComposeIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Operator-written message: stored as an approved manual draft and sent by the worker."""
    fan = db.get(Fan, fan_id)
    if fan is None:
        raise HTTPException(404, "fan not found")
    d = Draft(fan_id=fan.id, kind="manual", status="approved", bubbles=[body.text.strip()],
              approved_by="operator", route_reason="written by operator")
    db.add(d)
    db.flush()
    engine.supersede_pending(db, fan.id, "reply")
    jobs.enqueue(db, "send_draft", {"draft_id": d.id}, idempotency_key=f"send-draft-{d.id}")
    jobs.audit(db, "operator", "message.composed", "draft", d.id, fan_id=fan.id)
    db.commit()
    return ser.draft(d, fan)


def _draft(db: Session, draft_id: int) -> Draft:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "draft not found")
    return d


# ------------------------------------------------------------------------------------------------ settings
@router.get("/settings/{key}")
def get_settings_doc(key: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    if key not in DOCS:
        raise HTTPException(404, "unknown settings document")
    return load(db, DOCS[key]).model_dump(mode="json")


@router.put("/settings/{key}")
def put_settings_doc(key: str, body: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    if key not in DOCS:
        raise HTTPException(404, "unknown settings document")
    current = load(db, DOCS[key]).model_dump()
    current.update(body)
    try:
        doc = DOCS[key].model_validate(current)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc
    save(db, doc)
    if key == "persona":
        assert isinstance(doc, Persona)
        engine.store_prompt_version(db, "persona", persona_prompt(doc))
    changed = sorted(k for k in body if k in current)
    jobs.audit(db, "operator", f"settings.{key}.updated", fields=changed)
    db.commit()
    return doc.model_dump(mode="json")


@router.get("/persona/preview")
def persona_preview(db: Session = Depends(get_db)) -> dict[str, Any]:
    p = load(db, Persona)
    return {"persona_prompt": persona_prompt(p), "safety_block": SAFETY_BLOCK,
            "versions": [{"id": v.id, "created_at": v.created_at, "hash": v.content_hash[:10]}
                         for v in db.scalars(select(PromptVersion).where(PromptVersion.kind == "persona")
                                             .order_by(PromptVersion.id.desc()).limit(20))]}


@router.get("/prompt-versions/{vid}")
def prompt_version(vid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    v = db.get(PromptVersion, vid)
    if v is None:
        raise HTTPException(404, "not found")
    return {"id": v.id, "kind": v.kind, "content": v.content, "created_at": v.created_at}


# ------------------------------------------------------------------------------------------------ rules
class RuleIn(BaseModel):
    name: str = Field(default="", max_length=128)
    enabled: bool = False
    conditions: list[dict[str, Any]]
    action: str
    note: str = Field(default="", max_length=200)
    factor: float = Field(default=2.0, gt=0, le=10)


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.metrics import METRICS

    return {"items": [ser.rule(r) for r in db.scalars(select(CustomRule).order_by(CustomRule.position))],
            "metrics": METRICS, "actions": ACTIONS, "max": MAX_RULES}


@router.post("/rules")
def create_rule(body: RuleIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if (db.scalar(select(func.count()).select_from(CustomRule)) or 0) >= MAX_RULES:
        raise HTTPException(409, f"maximum {MAX_RULES} rules")
    _validate(body)
    pos = (db.scalar(select(func.max(CustomRule.position))) or 0) + 1
    r = CustomRule(**body.model_dump(), position=pos)
    db.add(r)
    db.commit()
    return ser.rule(r)


@router.put("/rules/{rid}")
def update_rule(rid: int, body: RuleIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(CustomRule, rid)
    if r is None:
        raise HTTPException(404, "rule not found")
    _validate(body)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return ser.rule(r)


@router.delete("/rules/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    r = db.get(CustomRule, rid)
    if r is None:
        raise HTTPException(404, "rule not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


def _validate(body: RuleIn) -> None:
    try:
        validate_rule(body.conditions, body.action)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# ------------------------------------------------------------------------------------------------ PPV
class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    description: str = Field(default="", max_length=300)


@router.get("/ppv/tags")
def list_tags(db: Session = Depends(get_db)) -> dict[str, Any]:
    counts: dict[int, int] = {}
    for t in db.scalars(select(PpvTemplate)):
        for i in t.tag_ids or []:
            counts[i] = counts.get(i, 0) + 1
    return {"items": [{**ser.tag(t), "count": counts.get(t.id, 0)}
                      for t in db.scalars(select(PpvTag).order_by(PpvTag.name))]}


@router.post("/ppv/tags")
def create_tag(body: TagIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.scalar(select(PpvTag).where(func.lower(PpvTag.name) == body.name.lower())):
        raise HTTPException(409, "tag already exists")
    t = PpvTag(name=body.name.strip(), description=body.description.strip())
    db.add(t)
    db.commit()
    return ser.tag(t)


@router.put("/ppv/tags/{tid}")
def update_tag(tid: int, body: TagIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(PpvTag, tid)
    if t is None:
        raise HTTPException(404, "tag not found")
    t.name, t.description = body.name.strip(), body.description.strip()
    db.commit()
    return ser.tag(t)


@router.delete("/ppv/tags/{tid}")
def delete_tag(tid: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    t = db.get(PpvTag, tid)
    if t is None:
        raise HTTPException(404, "tag not found")
    for tpl in db.scalars(select(PpvTemplate)):
        if tid in (tpl.tag_ids or []):
            tpl.tag_ids = [i for i in tpl.tag_ids if i != tid]
    db.delete(t)
    db.commit()
    return {"ok": True}


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    when_to_pitch: str = Field(default="", max_length=1000)
    teaser: str = Field(default="", max_length=1000)
    media_uuids: list[str] = Field(min_length=1, max_length=50)
    preview_media_uuid: str | None = None
    price: float = Field(default=0, ge=0, le=500)
    tag_ids: list[int] = Field(default_factory=list)
    gate_min_spent: float | None = Field(default=None, ge=0)
    gate_max_spent: float | None = Field(default=None, ge=0)
    gate_min_purchases: int | None = Field(default=None, ge=0)
    first_purchase_only: bool = False
    tip_reward: float | None = Field(default=None, ge=0)
    active: bool = True


def _apply_template(t: PpvTemplate, b: TemplateIn) -> None:
    price_cents = int(round(b.price * 100))
    if 0 < price_cents < 300:
        raise HTTPException(422, "Fanvue's minimum price for paid content is $3.00 (or 0 for free)")
    if b.gate_min_spent is not None and b.gate_max_spent is not None and b.gate_min_spent > b.gate_max_spent:
        raise HTTPException(422, "min spend gate is above max spend gate")
    t.name, t.description, t.when_to_pitch, t.teaser = b.name, b.description, b.when_to_pitch, b.teaser
    t.media_uuids, t.preview_media_uuid, t.price_cents, t.tag_ids = b.media_uuids, b.preview_media_uuid, \
        price_cents, b.tag_ids
    t.gate_min_spent_cents = None if b.gate_min_spent is None else int(round(b.gate_min_spent * 100))
    t.gate_max_spent_cents = None if b.gate_max_spent is None else int(round(b.gate_max_spent * 100))
    t.gate_min_purchases, t.first_purchase_only, t.active = b.gate_min_purchases, b.first_purchase_only, b.active
    t.tip_reward_cents = None if b.tip_reward is None else int(round(b.tip_reward * 100))


@router.get("/ppv/templates")
def list_templates(db: Session = Depends(get_db)) -> dict[str, Any]:
    stats = template_stats(db)
    return {"items": [ser.template(t, stats.get(t.id)) for t in
                      db.scalars(select(PpvTemplate).order_by(PpvTemplate.created_at.desc(), PpvTemplate.id.desc()))]}


@router.post("/ppv/templates")
def create_template(body: TemplateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = PpvTemplate()
    _apply_template(t, body)
    db.add(t)
    db.flush()
    jobs.audit(db, "operator", "ppv.template.created", "ppv_template", t.id)
    db.commit()
    return ser.template(t)


@router.put("/ppv/templates/{tid}")
def update_template(tid: int, body: TemplateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(PpvTemplate, tid)
    if t is None:
        raise HTTPException(404, "template not found")
    _apply_template(t, body)
    db.commit()
    return ser.template(t)


@router.post("/ppv/templates/{tid}/toggle")
def toggle_template(tid: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(PpvTemplate, tid)
    if t is None:
        raise HTTPException(404, "template not found")
    t.active = not t.active
    db.commit()
    return ser.template(t)


@router.delete("/ppv/templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    t = db.get(PpvTemplate, tid)
    if t is None:
        raise HTTPException(404, "template not found")
    db.delete(t)
    db.commit()
    return {"ok": True}


class MarkSoldIn(BaseModel):
    template_id: int
    amount: float | None = Field(default=None, ge=0)


@router.post("/fans/{fan_id}/ppv-sales")
def mark_sold(fan_id: int, body: MarkSoldIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Record a sale manually (e.g. bought before the app existed) so it is never offered again."""
    fan = db.get(Fan, fan_id)
    t = db.get(PpvTemplate, body.template_id)
    if fan is None or t is None:
        raise HTTPException(404, "fan or template not found")
    amount = int(round((body.amount if body.amount is not None else t.price_cents / 100) * 100))
    existing = db.scalar(select(PpvOffer).where(PpvOffer.fan_id == fan.id, PpvOffer.template_id == t.id,
                                                PpvOffer.status == "pitched").order_by(PpvOffer.id.desc()))
    o = existing or PpvOffer(fan_id=fan.id, template_id=t.id, source="manual")
    o.status, o.purchased_at, o.amount_cents = "purchased", utcnow(), amount
    if existing is None:
        db.add(o)
    fan.ppv_purchases += 1
    fan.last_purchase_at = o.purchased_at
    jobs.audit(db, "operator", "ppv.marked_sold", "fan", fan.id, template_id=t.id)
    db.commit()
    return {"ok": True, "offer_id": o.id}


# ------------------------------------------------------------------------------------------------ re-engagement
@router.get("/reengage/preview")
def reengage_preview(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": reengage.preview(db), "drafted_today": reengage.drafts_today(db)}


@router.post("/reengage/run")
def reengage_run(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)) -> dict[str, Any]:
    rep = reengage.scan(db, limit=limit)
    db.commit()
    return {"candidates": rep.candidates, "drafted": rep.drafted, "completed": rep.completed,
            "skipped": rep.skipped}
