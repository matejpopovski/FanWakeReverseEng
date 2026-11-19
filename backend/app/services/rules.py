"""Custom rules engine: conditions over fan metrics -> actions.

Conflict resolution (documented in the UI): all notes are injected, any hold applies, the longest slow-down
wins, and slowing down beats speeding up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models import CustomRule
from app.services.metrics import METRICS

ACTIONS = ("hold_pitch", "note", "slow_down", "speed_up", "nudge")
OPS = ("gte", "lte")
MAX_RULES = 20
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass
class RuleOutcome:
    hold_pitch: bool = False
    notes: list[str] = field(default_factory=list)
    pace_factor: float = 1.0
    nudges: list[str] = field(default_factory=list)
    matched_rule_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"hold_pitch": self.hold_pitch, "notes": self.notes, "pace_factor": self.pace_factor,
                "nudges": self.nudges, "matched_rule_ids": self.matched_rule_ids}


def validate_rule(conditions: list[dict[str, Any]], action: str) -> None:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action}")
    if not conditions:
        raise ValueError("a rule needs at least one condition")
    for c in conditions:
        if c.get("metric") not in METRICS:
            raise ValueError(f"unknown metric {c.get('metric')}")
        if c.get("op") not in OPS:
            raise ValueError(f"unknown operator {c.get('op')}")
        if not isinstance(c.get("value"), int | float):
            raise ValueError("condition value must be a number")


def render_note(note: str, metrics: dict[str, float]) -> str:
    def sub(m: re.Match[str]) -> str:
        v = metrics.get(m.group(1))
        if v is None:
            return m.group(0)
        return str(int(v)) if float(v).is_integer() else f"{v:.2f}"

    return _PLACEHOLDER.sub(sub, note)


def matches(rule: CustomRule, metrics: dict[str, float]) -> bool:
    for c in rule.conditions:
        v = metrics.get(c["metric"])
        if v is None:
            return False
        if c["op"] == "gte" and not v >= c["value"]:
            return False
        if c["op"] == "lte" and not v <= c["value"]:
            return False
    return True


def evaluate(rules: list[CustomRule], metrics: dict[str, float]) -> RuleOutcome:
    out = RuleOutcome()
    slow: list[float] = []
    fast: list[float] = []
    for r in sorted(rules, key=lambda r: r.position):
        if not r.enabled or not matches(r, metrics):
            continue
        out.matched_rule_ids.append(r.id)
        note = render_note(r.note, metrics) if r.note else ""
        if r.action == "hold_pitch":
            out.hold_pitch = True
            if note:
                out.notes.append(note)
        elif r.action == "note" and note:
            out.notes.append(note)
        elif r.action == "slow_down":
            slow.append(max(r.factor, 1.0))
        elif r.action == "speed_up":
            fast.append(min(max(r.factor, 0.1), 1.0) if r.factor <= 1 else 1 / r.factor)
        elif r.action == "nudge":
            out.nudges.append(note or (r.name or "custom rule matched"))
    if slow:
        out.pace_factor = max(slow)
    elif fast:
        out.pace_factor = min(fast)
    return out


DEFAULT_RULES: list[dict[str, Any]] = [
    {"name": "Stop offering after repeated passes", "action": "hold_pitch",
     "conditions": [{"metric": "rejected_pitch_streak", "op": "gte", "value": 3}],
     "note": "The fan passed on the last {rejected_pitch_streak} offers. Do not offer paid content until they ask; "
             "just talk."},
    {"name": "Repeat buyer price anchor", "action": "note",
     "conditions": [{"metric": "ppv_purchases", "op": "gte", "value": 2}],
     "note": "Repeat buyer; typical unlock is about ${avg_purchase}. Treat as a rough anchor only."},
    {"name": "New fan: connection first", "action": "hold_pitch",
     "conditions": [{"metric": "exchanges_loaded", "op": "lte", "value": 4}],
     "note": "Brand-new conversation: focus on getting to know the fan, no offers yet."},
    {"name": "Big spender heads-up", "action": "nudge",
     "conditions": [{"metric": "total_spent", "op": "gte", "value": 200}],
     "note": "High-value fan (${total_spent} spent) is chatting."},
]
