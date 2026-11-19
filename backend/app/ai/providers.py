"""LLM provider adapters with token/cost accounting.

- MockProvider: deterministic, offline; builds a plausible reply from the structured context. Used in mock mode
  and tests so the full pipeline is reproducible.
- AnthropicProvider: Messages API (https://api.anthropic.com/v1/messages).
- OpenAIProvider: Chat Completions on any OpenAI-compatible base URL.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import get_settings


@dataclass
class ChatTurn:
    role: str  # user (fan) | assistant (creator)
    content: str


@dataclass
class GenerationRequest:
    system: str
    turns: list[ChatTurn]
    purpose: str = "reply"  # reply | reengage | checkin
    context: dict[str, Any] = field(default_factory=dict)  # structured hints (used by MockProvider)


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0

    @property
    def cost_usd(self) -> float:
        s = get_settings()
        if self.provider == "mock":
            return 0.0
        return round(self.tokens_in / 1e6 * s.ai_price_input_per_mtok
                     + self.tokens_out / 1e6 * s.ai_price_output_per_mtok, 6)


class ProviderError(Exception):
    pass


class Provider(Protocol):
    name: str
    model: str

    def generate(self, req: GenerationRequest) -> GenerationResult: ...


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider:
    name = "mock"
    model = "mock-1"

    OPENERS = ["hey you", "hii", "omg hi", "heyy"]
    SMALLTALK = [
        "that actually made me smile, tell me more?",
        "haha okay you have my attention now",
        "honestly same. what are you up to tonight?",
        "i like that. what made you think of it?",
    ]
    REENGAGE = [
        "hey stranger, been a while. how have you been?",
        "was just thinking about our last chat, how did everything go?",
        "hiii, missed talking to you. what's new with you?",
    ]

    def _pick(self, options: list[str], seed: str) -> str:
        h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        return options[h % len(options)]

    def generate(self, req: GenerationRequest) -> GenerationResult:
        ctx = req.context
        last = next((t.content for t in reversed(req.turns) if t.role == "user"), "")
        seed = f"{ctx.get('fan_id')}:{last}:{len(req.turns)}"
        out: dict[str, Any] = {"messages": [], "ppv_template_id": None, "escalate": None, "nudge": None,
                               "memory_update": None, "next_move": "keep the conversation natural",
                               "checkin": None}
        if req.purpose == "reengage":
            out["messages"] = [self._pick(self.REENGAGE, seed)]
            out["next_move"] = "wait for the fan to reply"
        elif req.purpose == "checkin":
            out["messages"] = [f"hey, how did it go? {ctx.get('checkin_intent', '')}".strip()]
        else:
            low = last.lower()
            name = ctx.get("fan_name") or ""
            first = self._pick(self.OPENERS, seed) + (f" {name.split()[0].lower()}" if name else "")
            if any(w in low for w in ("goodnight", "good night", "gn", "going to bed")):
                out["messages"] = ["sleep well, talk tomorrow?"]
                out["checkin"] = {"in_hours": 10, "intent": "ask how they slept"}
            elif "?" in last:
                out["messages"] = [f"{first}, good question", self._pick(self.SMALLTALK, seed + "q")]
            else:
                out["messages"] = [self._pick(self.SMALLTALK, seed)]
            eligible = ctx.get("eligible_ppv") or []
            if eligible and any(w in low for w in ("pic", "video", "content", "see more", "show me", "unlock")):
                out["ppv_template_id"] = eligible[0]["id"]
                out["messages"].append("i have something you might like, want me to send it?")
            words = [w for w in last.split() if len(w) > 3][:6]
            if words:
                prev = ctx.get("memory") or ""
                out["memory_update"] = (prev + "\n" if prev else "[ABOUT]\n") + f"[NOW] talked about: {' '.join(words)}"
        text = json.dumps(out)
        prompt_len = len(req.system) + sum(len(t.content) for t in req.turns)
        return GenerationResult(text=text, provider=self.name, model=self.model,
                                tokens_in=prompt_len // 4, tokens_out=len(text) // 4)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self._http = httpx.Client(base_url="https://api.anthropic.com", timeout=60.0, transport=transport,
                                  headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                                           "content-type": "application/json"})

    def generate(self, req: GenerationRequest) -> GenerationResult:
        s = get_settings()
        messages = _merge_turns(req.turns)
        t0 = time.monotonic()
        resp = self._http.post("/v1/messages", json={
            "model": self.model, "max_tokens": s.ai_max_tokens, "temperature": s.ai_temperature,
            "system": req.system, "messages": messages})
        if resp.status_code >= 400:
            raise ProviderError(f"anthropic {resp.status_code}: {resp.text[:200]}")
        d = resp.json()
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        u = d.get("usage") or {}
        return GenerationResult(text=text, provider=self.name, model=self.model,
                                tokens_in=int(u.get("input_tokens") or _estimate_tokens(req.system)),
                                tokens_out=int(u.get("output_tokens") or _estimate_tokens(text)),
                                latency_ms=int((time.monotonic() - t0) * 1000))


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str, transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        self.model = model
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=60.0, transport=transport,
                                  headers={"Authorization": f"Bearer {api_key}"})

    def generate(self, req: GenerationRequest) -> GenerationResult:
        s = get_settings()
        msgs = [{"role": "system", "content": req.system}] + _merge_turns(req.turns)
        t0 = time.monotonic()
        resp = self._http.post("/chat/completions", json={
            "model": self.model, "max_tokens": s.ai_max_tokens, "temperature": s.ai_temperature,
            "messages": msgs, "response_format": {"type": "json_object"}})
        if resp.status_code >= 400:
            raise ProviderError(f"openai {resp.status_code}: {resp.text[:200]}")
        d = resp.json()
        text = d["choices"][0]["message"]["content"] or ""
        u = d.get("usage") or {}
        return GenerationResult(text=text, provider=self.name, model=self.model,
                                tokens_in=int(u.get("prompt_tokens") or 0),
                                tokens_out=int(u.get("completion_tokens") or 0),
                                latency_ms=int((time.monotonic() - t0) * 1000))


def _merge_turns(turns: list[ChatTurn]) -> list[dict[str, str]]:
    """Providers require alternating roles starting with user; merge consecutive same-role turns."""
    out: list[dict[str, str]] = []
    for t in turns:
        if out and out[-1]["role"] == t.role:
            out[-1]["content"] += "\n" + t.content
        else:
            out.append({"role": t.role, "content": t.content})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(conversation start)"})
    if out[-1]["role"] != "user":
        out.append({"role": "user", "content": "(no new fan message; write the outreach message now)"})
    return out


def get_provider() -> Provider:
    s = get_settings()
    if s.ai_provider == "anthropic":
        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model)
    if s.ai_provider == "openai":
        return OpenAIProvider(s.openai_api_key, s.openai_model, s.openai_base_url)
    return MockProvider()


def parse_json_reply(text: str) -> dict[str, Any]:
    """Extract the first JSON object from model output (tolerates code fences / prose)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("{"):]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ProviderError("model output contained no JSON object")
    try:
        data = json.loads(t[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ProviderError(f"invalid JSON from model: {exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("model JSON is not an object")
    msgs = data.get("messages")
    if isinstance(msgs, str):
        data["messages"] = [msgs]
    elif not isinstance(msgs, list):
        data["messages"] = []
    data["messages"] = [str(m).strip() for m in data["messages"] if str(m).strip()]
    return data
