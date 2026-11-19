"""Fanvue client protocol and transport-neutral DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class FanvueError(Exception):
    def __init__(self, message: str, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class NotContactable(FanvueError):
    pass


class NeedsReconnect(FanvueError):
    pass


@dataclass
class RemoteFan:
    uuid: str
    handle: str
    display_name: str
    avatar_url: str | None = None


@dataclass
class ChatSummary:
    fan: RemoteFan
    last_message_at: datetime | None
    unread_count: int = 0


@dataclass
class RemoteMessage:
    uuid: str
    fan_uuid: str
    sender: str  # fan | creator
    text: str
    sent_at: datetime
    price_cents: int | None = None
    media_uuids: list[str] = field(default_factory=list)
    message_type: str | None = None
    tip_cents: int | None = None


@dataclass
class FanInsight:
    status: str  # subscriber|expired|follower|not_contactable
    spent_cents: int = 0
    max_payment_cents: int = 0
    last_purchase_at: datetime | None = None


@dataclass
class RemoteMedia:
    uuid: str
    name: str
    media_type: str
    url: str | None = None


@dataclass
class Me:
    uuid: str
    handle: str
    display_name: str


class FanvueClient(Protocol):
    mode: str

    def get_me(self) -> Me: ...

    def list_chats(self, cursor: str | None = None, size: int = 50) -> tuple[list[ChatSummary], str | None]: ...

    def get_messages(self, fan_uuid: str, limit: int = 50,
                     sent_before: datetime | None = None) -> list[RemoteMessage]: ...

    def get_fan_insight(self, fan_uuid: str) -> FanInsight: ...

    def send_message(self, fan_uuid: str, text: str | None, media_uuids: list[str] | None = None,
                     price_cents: int | None = None, preview_media_uuid: str | None = None) -> str: ...

    def list_media(self, cursor: str | None = None) -> tuple[list[RemoteMedia], str | None]: ...

    def typing(self, fan_uuid: str) -> None: ...
