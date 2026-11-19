"""Live Fanvue client using only the official public API (https://api.fanvue.com/docs).

Endpoints used (all /v1, header X-Fanvue-API-Version):
  GET  /v1/users/me                         read:self
  GET  /v1/chats                            read:chat
  GET  /v1/chats/{userUuid}/messages        read:chat
  POST /v1/chats/{userUuid}/message         write:chat
  POST /v1/chats/{userUuid}/typing          write:chat
  GET  /v1/insights/fans/{userUuid}         read:insights + read:fan
  GET  /v1/media                            read:media
  GET  /v1/media/{uuid}?purchasedBy=        read:media   (purchase detection)
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings
from app.fanvue.base import (
    ChatSummary,
    FanInsight,
    FanvueError,
    Me,
    NeedsReconnect,
    NotContactable,
    RemoteFan,
    RemoteMedia,
    RemoteMessage,
)


def parse_ts(v: str | None) -> datetime | None:
    if not v:
        return None
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def to_cents(v: Any) -> int:
    """Fanvue amounts are integer minor units (cents)."""
    try:
        return int(round(float(v or 0)))
    except (TypeError, ValueError):
        return 0


class RateLimiter:
    """Client-side limiter: stays under Fanvue's 200 req/60 s budget with headroom; 4 concurrent max."""

    def __init__(self, per_minute: int = 150, concurrency: int = 4):
        self.per_minute = per_minute
        self.calls: deque[float] = deque()
        self.lock = threading.Lock()
        self.sem = threading.BoundedSemaphore(concurrency)

    def acquire(self) -> None:
        self.sem.acquire()
        while True:
            with self.lock:
                now = time.monotonic()
                while self.calls and now - self.calls[0] > 60:
                    self.calls.popleft()
                if len(self.calls) < self.per_minute:
                    self.calls.append(now)
                    return
                wait = 60 - (now - self.calls[0])
            time.sleep(max(wait, 0.05))

    def release(self) -> None:
        self.sem.release()


_limiter = RateLimiter()


class LiveFanvueClient:
    mode = "live"

    def __init__(self, token_provider: Callable[[], str], transport: httpx.BaseTransport | None = None,
                 on_unauthorized: Callable[[], str] | None = None, max_retries: int = 3):
        s = get_settings()
        self._token_provider = token_provider
        self._on_unauthorized = on_unauthorized
        self._max_retries = max_retries
        self._http = httpx.Client(base_url=s.fanvue_api_base, timeout=20.0, transport=transport,
                                  headers={"X-Fanvue-API-Version": s.fanvue_api_version,
                                           "Accept": "application/json"})

    # -- transport ---------------------------------------------------------------------------------------
    def _request(self, method: str, path: str, **kw: Any) -> Any:
        token = self._token_provider()
        refreshed = False
        for attempt in range(self._max_retries + 1):
            _limiter.acquire()
            try:
                resp = self._http.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kw)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise FanvueError(f"network error: {exc.__class__.__name__}", retryable=True) from exc
                time.sleep(min(2 ** attempt, 10))
                continue
            finally:
                _limiter.release()
            if resp.status_code == 401 and not refreshed and self._on_unauthorized:
                token = self._on_unauthorized()
                refreshed = True
                continue
            if resp.status_code == 401:
                raise NeedsReconnect("Fanvue rejected the access token", 401)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= self._max_retries:
                    raise FanvueError(f"Fanvue {resp.status_code}", resp.status_code, retryable=True)
                retry_after = float(resp.headers.get("Retry-After") or min(2 ** attempt, 30))
                time.sleep(min(retry_after, 60))
                continue
            if resp.status_code >= 400:
                detail = _safe_error(resp)
                if resp.status_code == 400 and "contact" in detail.lower():
                    raise NotContactable(detail, 400)
                raise FanvueError(f"Fanvue {resp.status_code}: {detail}", resp.status_code)
            return resp.json() if resp.content else None
        raise FanvueError("retries exhausted", retryable=True)  # pragma: no cover

    # -- protocol ----------------------------------------------------------------------------------------
    def get_me(self) -> Me:
        d = self._request("GET", "/v1/users/me")
        return Me(uuid=d["uuid"], handle=d.get("handle", ""), display_name=d.get("displayName", ""))

    def list_chats(self, cursor: str | None = None, size: int = 50) -> tuple[list[ChatSummary], str | None]:
        params: dict[str, Any] = {"size": size, "sortBy": "most_recent_messages"}
        if cursor:
            params["cursor"] = cursor
        d = self._request("GET", "/v1/chats", params=params)
        out = []
        for c in d.get("data", []):
            u = c.get("user") or {}
            if c.get("isCreator"):
                continue  # creator-to-creator chats are out of scope
            out.append(ChatSummary(
                fan=RemoteFan(uuid=u["uuid"], handle=u.get("handle", ""), display_name=u.get("displayName", ""),
                              avatar_url=u.get("avatarUrl")),
                last_message_at=parse_ts(c.get("lastMessageAt")),
                unread_count=int(c.get("unreadMessagesCount") or 0)))
        return out, d.get("nextCursor")

    def get_messages(self, fan_uuid: str, limit: int = 50,
                     sent_before: datetime | None = None) -> list[RemoteMessage]:
        params: dict[str, Any] = {"limit": min(limit, 50), "markAsRead": "false"}
        if sent_before:
            params["sentBefore"] = sent_before.isoformat() + "Z"
        d = self._request("GET", f"/v1/chats/{fan_uuid}/messages", params=params)
        out = []
        for m in d.get("data", []):
            sender = (m.get("sender") or {}).get("uuid")
            out.append(RemoteMessage(
                uuid=m["uuid"], fan_uuid=fan_uuid, sender="fan" if sender == fan_uuid else "creator",
                text=m.get("text") or "", sent_at=parse_ts(m.get("sentAt")) or datetime.min,
                message_type=m.get("type")))
        return out

    def get_fan_insight(self, fan_uuid: str) -> FanInsight:
        d = self._request("GET", f"/v1/insights/fans/{fan_uuid}")
        sp = d.get("spending") or {}
        return FanInsight(status=d.get("status", "follower"),
                          spent_cents=to_cents((sp.get("total") or {}).get("gross")),
                          max_payment_cents=to_cents((sp.get("maxSinglePayment") or {}).get("gross")),
                          last_purchase_at=parse_ts(sp.get("lastPurchaseAt")))

    def send_message(self, fan_uuid: str, text: str | None, media_uuids: list[str] | None = None,
                     price_cents: int | None = None, preview_media_uuid: str | None = None) -> str:
        body: dict[str, Any] = {"text": text}
        if media_uuids:
            body["mediaUuids"] = media_uuids
        if price_cents:
            if price_cents < 300:
                raise FanvueError("Fanvue minimum price is 300 cents", 400)
            body["price"] = price_cents
        if preview_media_uuid:
            body["mediaPreviewUuid"] = preview_media_uuid
        d = self._request("POST", f"/v1/chats/{fan_uuid}/message", json=body)
        return d["messageUuid"]

    def list_media(self, cursor: str | None = None) -> tuple[list[RemoteMedia], str | None]:
        params: dict[str, Any] = {"size": 50}
        if cursor:
            params["cursor"] = cursor
        d = self._request("GET", "/v1/media", params=params)
        out = []
        for m in d.get("data", []):
            thumb = next((v.get("url") for v in m.get("variants") or [] if v.get("variantType") == "thumbnail"),
                         m.get("url"))
            out.append(RemoteMedia(uuid=m["uuid"], name=m.get("name") or m.get("caption") or m["uuid"][:8],
                                   media_type=m.get("mediaType", "image"), url=thumb))
        return out, d.get("nextCursor")

    def media_purchased_by(self, fan_uuid: str, media_uuid: str) -> bool:
        """GET /v1/media/{uuid}?purchasedBy={fan} -> purchasedByFan (read:media)."""
        d = self._request("GET", f"/v1/media/{media_uuid}", params={"purchasedBy": fan_uuid})
        return bool((d or {}).get("purchasedByFan"))

    def typing(self, fan_uuid: str) -> None:
        try:
            self._request("POST", f"/v1/chats/{fan_uuid}/typing")
        except FanvueError:
            pass


def _safe_error(resp: httpx.Response) -> str:
    try:
        d = resp.json()
        return str(d.get("message") or d.get("error") or "")[:300]
    except ValueError:
        return resp.text[:300]
