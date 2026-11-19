"""SQLAlchemy ORM models. See docs/database-schema.md for the narrative description."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# --------------------------------------------------------------------------- configuration


class Setting(Base):
    """Key/value store for typed settings documents (engine, reengage, safety, ...)."""

    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # persona | reply_system | reengage_system
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("kind", "content_hash", name="uq_prompt_kind_hash"),)


class FanvueConnection(Base):
    __tablename__ = "fanvue_connection"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(32), default="disconnected")  # disconnected|connected|error
    creator_uuid: Mapped[str | None] = mapped_column(String(64))
    handle: Mapped[str | None] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(256))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    scopes: Mapped[str | None] = mapped_column(Text)
    needs_reconnect: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class OAuthState(Base):
    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    code_verifier: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --------------------------------------------------------------------------- fans & messages


class Fan(TimestampMixin, Base):
    __tablename__ = "fans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fanvue_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    handle: Mapped[str] = mapped_column(String(128), default="")
    display_name: Mapped[str] = mapped_column(String(256), default="")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="follower")  # subscriber|follower|expired|not_contactable

    # spend metrics (cents)
    total_spent_cents: Mapped[int] = mapped_column(Integer, default=0)
    ppv_purchases: Mapped[int] = mapped_column(Integer, default=0)
    tips_count: Mapped[int] = mapped_column(Integer, default=0)
    tip_total_cents: Mapped[int] = mapped_column(Integer, default=0)
    max_tip_cents: Mapped[int] = mapped_column(Integer, default=0)
    last_tip_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime)

    # activity
    first_contact_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    last_synced_message_uuid: Mapped[str | None] = mapped_column(String(64))
    purchases_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    # per-fan engine overrides
    autopilot_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    review_mode: Mapped[str] = mapped_column(String(16), default="inherit")  # inherit|manual|auto
    reengage_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    ppv_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    pacing_override_min: Mapped[int | None] = mapped_column(Integer)
    custom_approach: Mapped[str] = mapped_column(Text, default="")

    # CRM
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory: Mapped[str] = mapped_column(Text, default="")
    next_move: Mapped[str] = mapped_column(Text, default="")

    # state
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    reengage_state: Mapped[str] = mapped_column(String(16), default="none")
    # none|active|completed|failed|unreachable|awakened
    reengage_attempts: Mapped[int] = mapped_column(Integer, default=0)
    reengage_next_at: Mapped[datetime | None] = mapped_column(DateTime)
    reengage_cycle_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    reengage_last_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    awakened_at: Mapped[datetime | None] = mapped_column(DateTime)
    escalation_count: Mapped[int] = mapped_column(Integer, default=0)

    messages: Mapped[list[Message]] = relationship(back_populates="fan", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fan_id: Mapped[int] = mapped_column(ForeignKey("fans.id", ondelete="CASCADE"), index=True)
    fanvue_uuid: Mapped[str | None] = mapped_column(String(64), unique=True)
    direction: Mapped[str] = mapped_column(String(8))  # in|out
    text: Mapped[str] = mapped_column(Text, default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    media_uuids: Mapped[list[str]] = mapped_column(JSON, default=list)
    price_cents: Mapped[int | None] = mapped_column(Integer)
    message_type: Mapped[str | None] = mapped_column(String(48))
    origin: Mapped[str] = mapped_column(String(24), default="fan")
    # fan|operator|ai_reply|ai_reengage|ai_checkin|platform
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    tip_cents: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    fan: Mapped[Fan] = relationship(back_populates="messages")
    __table_args__ = (Index("ix_messages_fan_sent", "fan_id", "sent_at"),)


# --------------------------------------------------------------------------- AI drafts & alerts


class Draft(TimestampMixin, Base):
    __tablename__ = "drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fan_id: Mapped[int] = mapped_column(ForeignKey("fans.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="reply")  # reply|reengage|checkin|manual
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending|approved|sending|sent|rejected|replaced|expired|failed|blocked
    bubbles: Mapped[list[str]] = mapped_column(JSON, default=list)
    ppv_template_id: Mapped[int | None] = mapped_column(ForeignKey("ppv_templates.id", ondelete="SET NULL"))
    price_cents: Mapped[int | None] = mapped_column(Integer)
    media_uuids: Mapped[list[str]] = mapped_column(JSON, default=list)
    classification: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    guardrail_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    rule_actions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_versions.id"))
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    route_reason: Mapped[str | None] = mapped_column(Text)  # why it needs review / auto
    reject_reason: Mapped[str | None] = mapped_column(Text)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(32))  # operator|auto
    scheduled_send_at: Mapped[datetime | None] = mapped_column(DateTime)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)
    trigger_message_id: Mapped[int | None] = mapped_column(Integer)  # soft ref (avoids FK cycle)
    sent_bubbles: Mapped[int] = mapped_column(Integer, default=0)

    fan: Mapped[Fan] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fan_id: Mapped[int | None] = mapped_column(ForeignKey("fans.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # escalation|nudge|system
    category: Mapped[str] = mapped_column(String(48), default="")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|handled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime)

    fan: Mapped[Fan | None] = relationship()


class Checkin(Base):
    __tablename__ = "checkins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fan_id: Mapped[int] = mapped_column(ForeignKey("fans.id", ondelete="CASCADE"), index=True)
    intent: Mapped[str] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="planned")  # planned|drafted|cancelled|skipped
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    fan: Mapped[Fan] = relationship()


# --------------------------------------------------------------------------- PPV


class PpvTag(Base):
    __tablename__ = "ppv_tags"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(48), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")


class PpvTemplate(TimestampMixin, Base):
    __tablename__ = "ppv_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    when_to_pitch: Mapped[str] = mapped_column(Text, default="")
    teaser: Mapped[str] = mapped_column(Text, default="")
    media_uuids: Mapped[list[str]] = mapped_column(JSON, default=list)
    preview_media_uuid: Mapped[str | None] = mapped_column(String(64))
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    tag_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    gate_min_spent_cents: Mapped[int | None] = mapped_column(Integer)
    gate_max_spent_cents: Mapped[int | None] = mapped_column(Integer)
    gate_min_purchases: Mapped[int | None] = mapped_column(Integer)
    first_purchase_only: Mapped[bool] = mapped_column(Boolean, default=False)
    tip_reward_cents: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PpvOffer(Base):
    """A template pitched to / purchased by a fan."""

    __tablename__ = "ppv_offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fan_id: Mapped[int] = mapped_column(ForeignKey("fans.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("ppv_templates.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="pitched")  # pitched|purchased
    source: Mapped[str] = mapped_column(String(16), default="ai")  # ai|manual|webhook
    amount_cents: Mapped[int | None] = mapped_column(Integer)
    pitched_at: Mapped[datetime | None] = mapped_column(DateTime)
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CustomRule(TimestampMixin, Base):
    __tablename__ = "custom_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # [{metric, op, value}]
    action: Mapped[str] = mapped_column(String(16))  # hold_pitch|note|slow_down|speed_up|nudge
    note: Mapped[str] = mapped_column(Text, default="")
    factor: Mapped[float] = mapped_column(Float, default=2.0)
    position: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- infrastructure


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    run_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # queued|running|done|failed|dead|cancelled
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(32))  # operator|system|ai|worker
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str | None] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AiUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(32))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text)
    draft_id: Mapped[int | None] = mapped_column(Integer)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    type: Mapped[str] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------- mock Fanvue backend


class MockFan(Base):
    """Synthetic 'remote' Fanvue fans used by MockFanvueClient (never real people)."""

    __tablename__ = "mock_fans"
    uuid: Mapped[str] = mapped_column(String(64), primary_key=True)
    handle: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(32), default="follower")
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)
    max_payment_cents: Mapped[int] = mapped_column(Integer, default=0)
    last_purchase_at: Mapped[datetime | None] = mapped_column(DateTime)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MockMessage(Base):
    __tablename__ = "mock_messages"
    uuid: Mapped[str] = mapped_column(String(64), primary_key=True)
    fan_uuid: Mapped[str] = mapped_column(ForeignKey("mock_fans.uuid", ondelete="CASCADE"), index=True)
    sender: Mapped[str] = mapped_column(String(16))  # fan|creator
    text: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int | None] = mapped_column(Integer)
    media_uuids: Mapped[list[str]] = mapped_column(JSON, default=list)
    message_type: Mapped[str] = mapped_column(String(48), default="SINGLE_RECIPIENT")
    tip_cents: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, index=True)


class MockMedia(Base):
    __tablename__ = "mock_media"
    uuid: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    media_type: Mapped[str] = mapped_column(String(16), default="image")
    color: Mapped[str] = mapped_column(String(16), default="#888888")


class MockPurchase(Base):
    """Media unlocked by a mock fan (stands in for Fanvue's purchasedByFan flag)."""

    __tablename__ = "mock_purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fan_uuid: Mapped[str] = mapped_column(ForeignKey("mock_fans.uuid", ondelete="CASCADE"), index=True)
    media_uuid: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("fan_uuid", "media_uuid", name="uq_mock_purchase"),)
