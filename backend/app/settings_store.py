"""Typed settings documents persisted in the `settings` table."""

from __future__ import annotations

from typing import Literal, TypeVar

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.models import Setting

ApprovalMode = Literal["review", "threshold", "auto"]
Approach = Literal[
    "adaptive", "balanced", "warm_then_pitch", "smart_revenue", "build_desire", "revenue_focused", "engagement_only"
]


class EngineSettings(BaseModel):
    """Autopilot (reply engine) settings."""

    enabled: bool = False
    approval_mode: ApprovalMode = "review"
    threshold_spend_cents: int = Field(default=10000, ge=0)
    pacing: Literal["fast", "natural", "relaxed"] = "natural"
    away_after_min: int = Field(default=30, ge=1, le=1440)
    away_wait_min: int = Field(default=5, ge=0, le=240)
    away_wait_max: int = Field(default=20, ge=0, le=240)
    quiet_hours_enabled: bool = False
    quiet_from_hour: int = Field(default=2, ge=0, le=23)
    quiet_to_hour: int = Field(default=9, ge=0, le=23)
    timezone: str = "America/Chicago"
    checkins_enabled: bool = True
    checkins_per_week: int = Field(default=2, ge=0, le=14)
    checkin_guidance: str = Field(
        default=(
            "Plan a check-in only when the conversation itself created a concrete reason to follow up later "
            "(a goodnight, an event the fan mentioned). Keep it short and specific to that moment."
        ),
        max_length=400,
    )
    approach: Approach = "balanced"
    custom_prompt: str = Field(default="", max_length=5000)
    conversation_rules: str = Field(default="", max_length=5000)
    escalation_keywords: list[str] = Field(default_factory=list)
    nudge_keywords: list[str] = Field(default_factory=lambda: ["custom video", "custom content", "dick rating"])
    ppv_enabled: bool = True
    repitch_cooldown_msgs: int | None = 25  # None = never re-pitch unpurchased
    repitch_cooldown_hours: int | None = Field(default=72, ge=0, le=24 * 60)  # also require this much time
    min_hours_between_offers: int = Field(default=12, ge=0, le=24 * 14)  # any offer to the same fan; 0 = off
    max_bubbles: int = Field(default=2, ge=1, le=3)
    expire_pending_after_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("away_wait_max")
    @classmethod
    def _max_ge_min(cls, v: int, info) -> int:  # type: ignore[no-untyped-def]
        lo = info.data.get("away_wait_min", 0)
        return max(v, lo)


class ReengageSettings(BaseModel):
    enabled: bool = False
    approval_mode: ApprovalMode = "review"
    threshold_spend_cents: int = Field(default=10000, ge=0)
    attempts: int = Field(default=3, ge=1, le=4)
    schedule_days: list[int] = Field(default_factory=lambda: [2, 9, 21])
    silence_hours: int = Field(default=48, ge=12, le=24 * 14)
    repeat_every_days: int | None = 30  # None = never repeat cycle
    active_within_days: int | None = 90  # None = no limit
    include_no_history: bool = False
    sending_hours_enabled: bool = False
    send_from_hour: int = Field(default=10, ge=0, le=23)
    send_to_hour: int = Field(default=22, ge=0, le=23)
    daily_cap: int = Field(default=50, ge=0, le=500)
    approach: Literal["natural", "curiosity", "warm_tease", "direct"] = "natural"
    custom_prompt: str = Field(default="", max_length=3000)
    teaser_media_uuids: list[str] = Field(default_factory=list)


class SafetySettings(BaseModel):
    automation_paused: bool = False  # global kill switch
    live_sending_enabled: bool = False  # must be explicitly turned on by the operator for live mode
    max_sends_per_fan_per_day: int = Field(default=60, ge=1, le=500)
    max_ai_calls_per_day: int = Field(default=2000, ge=1)
    pending_queue_cap: int = Field(default=500, ge=1)
    share_notes_with_ai: bool = True
    share_memory_with_ai: bool = True


class Persona(BaseModel):
    ai_name: str = Field(default="", max_length=64)
    language: str = "English"
    tone: Literal["warm", "flirty", "playful", "sensual", "direct"] = "warm"
    age: int | None = Field(default=None, ge=18, le=99)
    location: str = Field(default="", max_length=128)
    timezone: str = "America/Chicago"
    occupation: str = Field(default="", max_length=128)
    traits: str = Field(default="", max_length=256)
    bio: str = Field(default="", max_length=1200)
    behaviours: list[str] = Field(default_factory=list, max_length=8)
    emoji_frequency: Literal["zero", "rare", "moderate", "frequent"] = "rare"
    message_length: Literal["auto", "very_short", "short", "medium", "long"] = "auto"
    energy: Literal["low", "casual", "enthusiastic"] = "casual"
    casing: Literal["lowercase", "mixed", "proper"] = "mixed"
    preferred_emojis: str = Field(default="", max_length=64)
    allow_other_emojis: bool = True
    qa: list[dict[str, str]] = Field(default_factory=list, max_length=5)  # [{q, a}]
    examples: list[str] = Field(default_factory=list, max_length=8)
    custom_system_prompt: str = Field(default="", max_length=6000)


DOCS: dict[str, type[BaseModel]] = {
    "engine": EngineSettings,
    "reengage": ReengageSettings,
    "safety": SafetySettings,
    "persona": Persona,
}

T = TypeVar("T", bound=BaseModel)


def load(db: Session, model: type[T]) -> T:
    key = next(k for k, v in DOCS.items() if v is model)
    row = db.get(Setting, key)
    if row is None:
        return model()
    return model.model_validate(row.value)


def save(db: Session, doc: BaseModel) -> None:
    key = next(k for k, v in DOCS.items() if v is type(doc))
    row = db.get(Setting, key)
    data = doc.model_dump(mode="json")
    if row is None:
        db.add(Setting(key=key, value=data))
    else:
        row.value = data
    db.flush()
