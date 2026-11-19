"""Post-generation guardrails. Any flag blocks auto-sending; the draft goes to the operator."""

from __future__ import annotations

import re

_HUMAN_CLAIMS = [
    r"\b(i'?m|i am|im) (not )?(an? )?(ai|bot|robot)\b",
    r"\b(i'?m|i am|im) (a )?(real|human|real person|real girl|real woman|real guy)\b",
    r"\bnot an? (ai|bot|robot)\b", r"\bdefinitely real\b", r"\b100% real\b", r"\bit'?s really me\b",
    r"\bno bots? here\b", r"\bthis is (really )?me typing\b",
]
_OFF_PLATFORM = [
    r"\b(telegram|whats ?app|snap(chat)?|kik|signal|cash ?app|venmo|pay ?pal|zelle|crypto|bitcoin)\b",
    r"\b(my|add me on) (insta|ig|instagram)\b", r"\bemail me\b", r"\b(my|text my) (number|phone)\b",
]
_MEETUP = [r"\bmeet (up|irl|in person)\b", r"\b(my|your) (place|address|hotel)\b", r"\bsee you in person\b"]
_MINORS = [r"\b(1[0-7]) ?(yo|years? old)\b", r"\bschool ?girl\b", r"\bteen(ager)?\b", r"\bunderage\b"]
_PRESSURE = [r"\bonly \d+ (left|spots?)\b", r"\blast chance\b", r"\bexpires in \d+ (min|minutes|hours?)\b",
             r"\bif you (really )?(loved|cared about) me you('d| would)\b", r"\bi'?ll (leave|block) you\b"]

_GROUPS = {
    "claims_human_or_denies_ai": _HUMAN_CLAIMS,
    "off_platform_contact": _OFF_PLATFORM,
    "meetup": _MEETUP,
    "minor_reference": _MINORS,
    "pressure_tactic": _PRESSURE,
}
_COMPILED = {k: [re.compile(p, re.IGNORECASE) for p in v] for k, v in _GROUPS.items()}

MAX_BUBBLE_CHARS = 1000


def check_bubbles(bubbles: list[str], recent_outbound: list[str] | None = None,
                  max_bubbles: int = 3) -> list[str]:
    flags: list[str] = []
    if not bubbles or not any(b.strip() for b in bubbles):
        return ["empty_output"]
    if len(bubbles) > max_bubbles:
        flags.append("too_many_bubbles")
    joined = "\n".join(bubbles)
    for name, pats in _COMPILED.items():
        if any(p.search(joined) for p in pats):
            flags.append(name)
    if any(len(b) > MAX_BUBBLE_CHARS for b in bubbles):
        flags.append("too_long")
    recent = {r.strip().lower() for r in (recent_outbound or []) if r.strip()}
    if any(b.strip().lower() in recent for b in bubbles):
        flags.append("repeats_recent_message")
    return flags


def check_offer(template_id: int | None, eligible_ids: set[int], price_cents: int | None) -> list[str]:
    flags: list[str] = []
    if template_id is not None and template_id not in eligible_ids:
        flags.append("ineligible_ppv_template")
    if price_cents is not None and 0 < price_cents < 300:
        flags.append("price_below_fanvue_minimum")
    return flags
