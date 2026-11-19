"""Unit + prompt-regression tests for classifier, guardrails, prompts, rules, timing, providers."""

from __future__ import annotations

import json
import random
from datetime import datetime

import httpx
import pytest

from app.ai import classifier, guardrails
from app.ai.prompts import SAFETY_BLOCK, persona_prompt
from app.ai.providers import (
    AnthropicProvider,
    ChatTurn,
    GenerationRequest,
    MockProvider,
    OpenAIProvider,
    ProviderError,
    _merge_turns,
    parse_json_reply,
)
from app.models import CustomRule
from app.services import rules, timing
from app.settings_store import Persona

# ---------------------------------------------------------------- classifier regression fixtures
ESCALATE_CASES = [
    ("are you a bot?", "ai_question"),
    ("Is this an AI replying??", "ai_question"),
    ("am i talking to a real person", "ai_question"),
    ("can i pay you on telegram instead", "off_platform_payment"),
    ("send me your cashapp", "off_platform_payment"),
    ("we should meet up irl", "meetup"),
    ("i'm 16 btw", "minor_risk"),
    ("im 17 years old", "minor_risk"),
    ("stop messaging me", "stop_request"),
    ("this is a scam, I want a refund", "complaint"),
    ("sometimes i want to kill myself", "self_harm"),
]
SAFE_CASES = [
    "hey how was your day", "i'm 18 minutes away from home lol", "im 15 min late sorry",
    "loved your post", "goodnight!", "what's your favourite food?",
]


@pytest.mark.parametrize(("text", "cat"), ESCALATE_CASES)
def test_classifier_escalates(text: str, cat: str) -> None:
    c = classifier.classify(text)
    assert cat in c.escalate, (text, c.as_dict())


@pytest.mark.parametrize("text", SAFE_CASES)
def test_classifier_safe(text: str) -> None:
    assert classifier.classify(text).escalate == []


def test_classifier_nudges_and_operator_keywords() -> None:
    c = classifier.classify("can you make me a custom video? how much", extra_escalation=["lawyer"])
    assert "custom_request" in c.nudge and "purchase_intent" in c.nudge and not c.escalate
    assert "operator_keyword" in classifier.classify("my lawyer says hi", extra_escalation=["lawyer"]).escalate
    assert "big_tip" in classifier.classify("here you go", tip_cents=5000).nudge


# ---------------------------------------------------------------- guardrails
@pytest.mark.parametrize(("bubble", "flag"), [
    ("no i'm a real person, promise", "claims_human_or_denies_ai"),
    ("i'm not a bot silly", "claims_human_or_denies_ai"),
    ("add me on telegram babe", "off_platform_contact"),
    ("we could meet up irl sometime", "meetup"),
    ("only 2 spots left, last chance!", "pressure_tactic"),
])
def test_guardrails_flag(bubble: str, flag: str) -> None:
    assert flag in guardrails.check_bubbles([bubble])


def test_guardrails_clean_and_structural() -> None:
    assert guardrails.check_bubbles(["haha that's so sweet", "what are you up to?"]) == []
    assert guardrails.check_bubbles([]) == ["empty_output"]
    assert "repeats_recent_message" in guardrails.check_bubbles(["hey"], recent_outbound=["Hey"])
    assert "too_long" in guardrails.check_bubbles(["x" * 1200])
    assert guardrails.check_offer(5, {1, 2}, 999) == ["ineligible_ppv_template"]
    assert guardrails.check_offer(1, {1}, 150) == ["price_below_fanvue_minimum"]


# ---------------------------------------------------------------- prompts
def test_persona_prompt_snapshot_sections() -> None:
    p = Persona(ai_name="Mia", age=25, location="Oslo", traits="witty", tone="playful",
                qa=[{"q": "where are you from?", "a": "norway!"}], examples=["lol same"])
    text = persona_prompt(p)
    for needle in ("Mia", "age 25", "Oslo", "witty", "Tone: fun", "Q: where are you from?", "- lol same"):
        assert needle in text
    assert persona_prompt(Persona(custom_system_prompt="CUSTOM")) == "CUSTOM"


def test_safety_block_is_honest() -> None:
    assert "Never claim to be human" in SAFETY_BLOCK
    assert "never deny" in SAFETY_BLOCK
    assert "outside Fanvue" in SAFETY_BLOCK


# ---------------------------------------------------------------- rules
def _rule(**kw: object) -> CustomRule:
    base = {"id": 1, "name": "r", "enabled": True, "position": 0, "note": "", "factor": 2.0,
            "conditions": [{"metric": "total_spent", "op": "gte", "value": 10}], "action": "note"}
    base.update(kw)
    return CustomRule(**base)


def test_rules_conflict_resolution() -> None:
    m = {"total_spent": 50.0, "rejected_pitch_streak": 3.0}
    out = rules.evaluate([
        _rule(id=1, action="hold_pitch", note="streak {rejected_pitch_streak}"),
        _rule(id=2, action="note", note="spent ${total_spent}"),
        _rule(id=3, action="slow_down", factor=2),
        _rule(id=4, action="slow_down", factor=3),
        _rule(id=5, action="speed_up", factor=2),
        _rule(id=6, action="nudge", note="vip"),
        _rule(id=7, action="note", note="never", conditions=[{"metric": "total_spent", "op": "lte", "value": 1}]),
        _rule(id=8, action="note", note="disabled", enabled=False),
    ], m)
    assert out.hold_pitch
    assert out.notes == ["streak 3", "spent $50"]
    assert out.pace_factor == 3  # longest slow-down wins and beats speed-up
    assert out.nudges == ["vip"]
    assert out.matched_rule_ids == [1, 2, 3, 4, 5, 6]


def test_rules_speed_up_only_and_validation() -> None:
    assert rules.evaluate([_rule(action="speed_up", factor=2)], {"total_spent": 20}).pace_factor == 0.5
    with pytest.raises(ValueError):
        rules.validate_rule([{"metric": "nope", "op": "gte", "value": 1}], "note")
    with pytest.raises(ValueError):
        rules.validate_rule([], "note")
    with pytest.raises(ValueError):
        rules.validate_rule([{"metric": "total_spent", "op": "gte", "value": 1}], "explode")


# ---------------------------------------------------------------- timing
def test_pacing_windows() -> None:
    rng = random.Random(1)
    for _ in range(200):
        assert 5 <= timing.pacing_delay("fast", rng=rng) <= 45
        assert 15 <= timing.pacing_delay("natural", rng=rng) <= 300
    d = timing.pacing_delay("natural", override_min=10, rng=rng)
    assert 420 <= d <= 780
    assert timing.pacing_delay("fast", factor=3, rng=random.Random(2)) >= 15


def test_away_delay_and_quiet_hours() -> None:
    now = datetime(2026, 1, 1, 12, 0)
    assert timing.away_delay(datetime(2026, 1, 1, 11, 50), now, 30, 5, 20) == 0
    d = timing.away_delay(datetime(2026, 1, 1, 9, 0), now, 30, 5, 20, rng=random.Random(3))
    assert 300 <= d <= 1200
    # 03:00 UTC = 03:00 London in winter -> inside 02-09 quiet window -> pushed to >= 09:00
    at = timing.apply_quiet_hours(datetime(2026, 1, 1, 3, 0), True, "Europe/London", 2, 9, rng=random.Random(4))
    assert datetime(2026, 1, 1, 9, 0) <= at <= datetime(2026, 1, 1, 9, 30)
    assert timing.in_window(datetime(2026, 1, 1, 23, 0), "UTC", 22, 6)
    assert not timing.in_window(datetime(2026, 1, 1, 12, 0), "UTC", 22, 6)
    assert not timing.in_window(datetime(2026, 1, 1, 12, 0), "UTC", 5, 5)


# ---------------------------------------------------------------- providers
def test_parse_json_reply_tolerant() -> None:
    assert parse_json_reply('```json\n{"messages": "hi"}\n```')["messages"] == ["hi"]
    assert parse_json_reply('Sure! {"messages": ["a", " ", "b"]}')["messages"] == ["a", "b"]
    with pytest.raises(ProviderError):
        parse_json_reply("no json here")


def test_merge_turns_alternates() -> None:
    out = _merge_turns([ChatTurn("assistant", "a"), ChatTurn("user", "b"), ChatTurn("user", "c")])
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[-1]["content"] == "b\nc"


def test_mock_provider_deterministic() -> None:
    req = GenerationRequest(system="s", turns=[ChatTurn("user", "show me more pics?")],
                            context={"fan_id": 1, "eligible_ppv": [{"id": 9}]})
    a, b = MockProvider().generate(req), MockProvider().generate(req)
    assert a.text == b.text
    data = json.loads(a.text)
    assert data["ppv_template_id"] == 9 and 1 <= len(data["messages"]) <= 3


def test_anthropic_provider_http_contract() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        seen["key"] = req.headers["x-api-key"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"messages":["hi"]}'}],
                                         "usage": {"input_tokens": 100, "output_tokens": 20}})

    p = AnthropicProvider("k", "claude-test", transport=httpx.MockTransport(handler))
    res = p.generate(GenerationRequest(system="SYS", turns=[ChatTurn("user", "hey")]))
    assert seen["url"].endswith("/v1/messages") and seen["key"] == "k"
    assert seen["body"]["system"] == "SYS" and seen["body"]["messages"][0]["role"] == "user"
    assert res.tokens_in == 100 and res.cost_usd > 0


def test_openai_provider_errors() -> None:
    p = OpenAIProvider("k", "m", "https://x/v1", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ProviderError):
        p.generate(GenerationRequest(system="s", turns=[]))
    with pytest.raises(ProviderError):
        AnthropicProvider("", "m")
