"""Deterministic first-pass classifier for inbound fan messages.

Fast, explainable, testable. Categories drive escalation (stop + human) vs nudge (continue + heads-up).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ESCALATE = "escalate"
NUDGE = "nudge"

# (category, action, patterns). Patterns are matched case-insensitively on word boundaries where sensible.
_RULES: list[tuple[str, str, list[str]]] = [
    ("minor_risk", ESCALATE, [r"\b(i'?m|i am|im) (1[0-7])\b(?!\s*(k\b|cm|inch|in\b|min|hours?|days?|ft|%|'|\"))",
                              r"\b(1[0-7]) ?(yo|y/o|years? old)\b", r"\bunder ?age\b", r"\bminor\b",
                              r"\bhigh ?school(er)?\b", r"\bmiddle school\b"]),
    ("self_harm", ESCALATE, [r"\bkill (myself|my self)\b", r"\bsuicid", r"\bend it all\b",
                             r"\bself[- ]?harm\b", r"\bdon'?t want to live\b"]),
    ("ai_question", ESCALATE, [r"\bare you (an? )?(ai|bot|robot|chat ?bot|real|human|a real person)\b",
                               r"\b(is this|am i talking to) (an? )?(ai|bot|real person|chat ?bot|human)\b",
                               r"\bchat ?gpt\b", r"\bare you even real\b", r"\bai (generated|reply|replies)\b",
                               r"\bis (this|that) (really )?you\b"]),
    ("stop_request", ESCALATE, [r"^\s*stop\s*$", r"\bstop (messaging|texting) me\b", r"\bleave me alone\b",
                                r"\bunsubscribe\b", r"\bdon'?t (message|text) me\b"]),
    ("off_platform_payment", ESCALATE, [r"\b(telegram|whats ?app|snap(chat)?|kik|signal|cash ?app|venmo|"
                                        r"pay ?pal|zelle|crypto|bitcoin|btc|onlyfans|instagram dm)\b",
                                        r"\b(pay|send) you (outside|off)\b", r"\boff[- ]?platform\b"]),
    ("meetup", ESCALATE, [r"\bmeet (up|irl|in person|you)\b", r"\bin real life\b", r"\birl\b",
                          r"\bcome (over|to my place)\b", r"\b(your|ur) address\b", r"\bhotel room\b",
                          r"\bgo on a date\b"]),
    ("complaint", ESCALATE, [r"\brefund\b", r"\bscam(med)?\b", r"\bripped off\b", r"\bchargeback\b",
                             r"\breport(ing)? you\b", r"\bwaste of money\b", r"\bnot what (i|you) (paid|promised)\b"]),
    ("custom_request", NUDGE, [r"\bcustom (video|vid|pic|photo|content|request)\b", r"\bpersonali[sz]ed\b",
                               r"\bmake (me )?a video\b", r"\bsay my name\b"]),
    ("purchase_intent", NUDGE, [r"\bhow much\b", r"\bprice\b", r"\bwhat do you (have|sell)\b",
                                r"\bbuy\b", r"\bunlock\b", r"\bppv\b", r"\bmenu\b"]),
]
_COMPILED = [(c, a, [re.compile(p, re.IGNORECASE) for p in pats]) for c, a, pats in _RULES]


@dataclass
class Classification:
    categories: list[str] = field(default_factory=list)
    escalate: list[str] = field(default_factory=list)
    nudge: list[str] = field(default_factory=list)
    matched: dict[str, str] = field(default_factory=dict)

    @property
    def primary(self) -> str:
        if self.escalate:
            return self.escalate[0]
        if self.nudge:
            return self.nudge[0]
        return "conversation"

    def as_dict(self) -> dict[str, object]:
        return {"primary": self.primary, "categories": self.categories, "escalate": self.escalate,
                "nudge": self.nudge, "matched": self.matched}


def classify(text: str, extra_escalation: list[str] | None = None,
             extra_nudge: list[str] | None = None, tip_cents: int | None = None) -> Classification:
    out = Classification()
    t = text or ""
    for cat, action, pats in _COMPILED:
        for p in pats:
            m = p.search(t)
            if m:
                out.categories.append(cat)
                (out.escalate if action == ESCALATE else out.nudge).append(cat)
                out.matched[cat] = m.group(0)
                break
    low = t.lower()
    for kw in extra_escalation or []:
        if kw and kw.lower() in low and "operator_keyword" not in out.escalate:
            out.categories.append("operator_keyword")
            out.escalate.append("operator_keyword")
            out.matched["operator_keyword"] = kw
    for kw in extra_nudge or []:
        if kw and kw.lower() in low and "operator_nudge" not in out.nudge:
            out.categories.append("operator_nudge")
            out.nudge.append("operator_nudge")
            out.matched["operator_nudge"] = kw
    if tip_cents and tip_cents >= 2000:
        out.categories.append("big_tip")
        out.nudge.append("big_tip")
    return out


ESCALATION_TEXT = {
    "minor_risk": "Fan may be under 18. Automation stopped; verify and handle manually.",
    "self_harm": "Fan mentioned self-harm. Automation stopped; respond with care and point to local help resources.",
    "ai_question": "Fan sincerely asked whether they are talking to AI or a real person. Answer honestly yourself.",
    "stop_request": "Fan asked to stop receiving messages. Automation stopped for this fan.",
    "off_platform_payment": "Fan mentioned off-platform payment or contact. Fanvue policy forbids this; reply yourself.",
    "meetup": "Fan is asking to meet in person. Not allowed via automation; reply yourself.",
    "complaint": "Fan is unhappy (refund/scam/report). Needs a human decision.",
    "operator_keyword": "Matched one of your escalation keywords.",
}
NUDGE_TEXT = {
    "custom_request": "Fan asked for custom content.",
    "purchase_intent": "Fan is showing purchase intent.",
    "operator_nudge": "Matched one of your nudge keywords.",
    "big_tip": "Fan sent a big tip.",
}
