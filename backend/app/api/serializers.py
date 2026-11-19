"""ORM → JSON-able dict helpers (kept explicit so API shapes are stable and documented)."""

from __future__ import annotations

from typing import Any

from app.models import Alert, Checkin, CustomRule, Draft, Fan, Message, PpvTag, PpvTemplate

VIP_CENTS = 5000


def fan_summary(f: Fan) -> dict[str, Any]:
    return {
        "id": f.id, "fanvue_uuid": f.fanvue_uuid, "handle": f.handle, "display_name": f.display_name,
        "avatar_url": f.avatar_url, "status": f.status, "vip": f.total_spent_cents >= VIP_CENTS,
        "total_spent": f.total_spent_cents / 100, "last_inbound_at": f.last_inbound_at,
        "last_outbound_at": f.last_outbound_at, "unread_count": f.unread_count,
        "autopilot_enabled": f.autopilot_enabled, "reengage_state": f.reengage_state,
        "reengage_attempts": f.reengage_attempts, "escalated": f.escalated, "tags": f.tags or [],
    }


def fan_detail(f: Fan) -> dict[str, Any]:
    d = fan_summary(f)
    d.update({
        "review_mode": f.review_mode, "reengage_enabled": f.reengage_enabled, "ppv_enabled": f.ppv_enabled,
        "pacing_override_min": f.pacing_override_min, "custom_approach": f.custom_approach, "notes": f.notes,
        "memory": f.memory, "next_move": f.next_move, "escalation_reason": f.escalation_reason,
        "ppv_purchases": f.ppv_purchases, "tips_count": f.tips_count, "tip_total": f.tip_total_cents / 100,
        "first_contact_at": f.first_contact_at, "awakened_at": f.awakened_at,
        "reengage_next_at": f.reengage_next_at, "reengage_last_sent_at": f.reengage_last_sent_at,
        "escalation_count": f.escalation_count,
    })
    return d


def message(m: Message) -> dict[str, Any]:
    return {"id": m.id, "fan_id": m.fan_id, "direction": m.direction, "text": m.text, "sent_at": m.sent_at,
            "media_uuids": m.media_uuids or [], "price": m.price_cents / 100 if m.price_cents else None,
            "tip": m.tip_cents / 100 if m.tip_cents else None, "origin": m.origin, "draft_id": m.draft_id,
            "message_type": m.message_type}


def draft(d: Draft, fan: Fan | None = None) -> dict[str, Any]:
    out = {"id": d.id, "fan_id": d.fan_id, "kind": d.kind, "status": d.status, "bubbles": d.bubbles,
           "ppv_template_id": d.ppv_template_id, "price": d.price_cents / 100 if d.price_cents else None,
           "media_uuids": d.media_uuids or [], "guardrail_flags": d.guardrail_flags or [],
           "rule_actions": d.rule_actions or {}, "route_reason": d.route_reason, "reject_reason": d.reject_reason,
           "edited": d.edited, "approved_by": d.approved_by, "provider": d.provider, "model": d.model,
           "tokens_in": d.tokens_in, "tokens_out": d.tokens_out, "cost_usd": d.cost_usd,
           "prompt_version_id": d.prompt_version_id, "created_at": d.created_at, "sent_at": d.sent_at,
           "error": d.error, "sent_bubbles": d.sent_bubbles}
    if fan is not None:
        out["fan"] = {"id": fan.id, "display_name": fan.display_name, "handle": fan.handle, "status": fan.status,
                      "total_spent": fan.total_spent_cents / 100}
    return out


def alert(a: Alert) -> dict[str, Any]:
    return {"id": a.id, "fan_id": a.fan_id, "kind": a.kind, "category": a.category, "message": a.message,
            "status": a.status, "created_at": a.created_at, "handled_at": a.handled_at,
            "fan_name": a.fan.display_name if a.fan else None}


def checkin(c: Checkin) -> dict[str, Any]:
    return {"id": c.id, "fan_id": c.fan_id, "intent": c.intent, "scheduled_at": c.scheduled_at,
            "status": c.status, "draft_id": c.draft_id, "fan_name": c.fan.display_name if c.fan else None}


def template(t: PpvTemplate, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": t.id, "name": t.name, "description": t.description, "when_to_pitch": t.when_to_pitch,
            "teaser": t.teaser, "media_uuids": t.media_uuids or [], "preview_media_uuid": t.preview_media_uuid,
            "price": t.price_cents / 100, "tag_ids": t.tag_ids or [],
            "gate_min_spent": None if t.gate_min_spent_cents is None else t.gate_min_spent_cents / 100,
            "gate_max_spent": None if t.gate_max_spent_cents is None else t.gate_max_spent_cents / 100,
            "gate_min_purchases": t.gate_min_purchases, "first_purchase_only": t.first_purchase_only,
            "tip_reward": None if t.tip_reward_cents is None else t.tip_reward_cents / 100, "active": t.active,
            "stats": stats or {}}


def tag(t: PpvTag) -> dict[str, Any]:
    return {"id": t.id, "name": t.name, "description": t.description}


def rule(r: CustomRule) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "enabled": r.enabled, "conditions": r.conditions, "action": r.action,
            "note": r.note, "factor": r.factor, "position": r.position}
