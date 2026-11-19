"""Mock Fanvue backend: a fully local stand-in for the official API.

It stores synthetic fans/messages in the `mock_*` tables so the real sync, drafting and sending code paths run
unchanged. Nothing here talks to the network.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue.base import (
    ChatSummary,
    FanInsight,
    FanvueError,
    Me,
    NotContactable,
    RemoteFan,
    RemoteMedia,
    RemoteMessage,
)
from app.models import MockFan, MockMedia, MockMessage

MOCK_CREATOR = Me(uuid="mock-creator-0001", handle="demo_creator", display_name="Demo Creator")


class MockFanvueClient:
    mode = "mock"

    def __init__(self, db: Session, fail_sends: bool = False):
        self.db = db
        self.fail_sends = fail_sends

    # -- helpers used by the simulator -------------------------------------------------------------------
    def _next_seq(self) -> int:
        return int(self.db.scalar(select(func.coalesce(func.max(MockMessage.seq), 0))) or 0) + 1

    def add_fan_message(self, fan_uuid: str, text: str, tip_cents: int | None = None,
                        at: datetime | None = None) -> MockMessage:
        if self.db.get(MockFan, fan_uuid) is None:
            raise FanvueError("unknown mock fan", 404)
        msg = MockMessage(uuid=str(uuid.uuid4()), fan_uuid=fan_uuid, sender="fan", text=text,
                          sent_at=at or utcnow(), seq=self._next_seq(), tip_cents=tip_cents,
                          message_type="TIP" if tip_cents else "SINGLE_RECIPIENT")
        self.db.add(msg)
        if tip_cents:
            fan = self.db.get(MockFan, fan_uuid)
            assert fan
            fan.spent_cents += tip_cents
            fan.max_payment_cents = max(fan.max_payment_cents, tip_cents)
            fan.last_purchase_at = msg.sent_at
        self.db.flush()
        return msg

    def record_purchase(self, fan_uuid: str, amount_cents: int) -> None:
        fan = self.db.get(MockFan, fan_uuid)
        if fan is None:
            raise FanvueError("unknown mock fan", 404)
        fan.spent_cents += amount_cents
        fan.max_payment_cents = max(fan.max_payment_cents, amount_cents)
        fan.last_purchase_at = utcnow()
        self.db.flush()

    # -- FanvueClient protocol -------------------------------------------------------------------------
    def get_me(self) -> Me:
        return MOCK_CREATOR

    def list_chats(self, cursor: str | None = None, size: int = 50) -> tuple[list[ChatSummary], str | None]:
        offset = int(cursor or 0)
        last = (select(MockMessage.fan_uuid, func.max(MockMessage.sent_at).label("last"))
                .group_by(MockMessage.fan_uuid).subquery())
        rows = self.db.execute(
            select(MockFan, last.c.last).join(last, last.c.fan_uuid == MockFan.uuid, isouter=True)
            .order_by(last.c.last.desc().nullslast(), MockFan.uuid).offset(offset).limit(size)
        ).all()
        out = [ChatSummary(fan=RemoteFan(f.uuid, f.handle, f.display_name), last_message_at=ts) for f, ts in rows]
        return out, (str(offset + size) if len(rows) == size else None)

    def get_messages(self, fan_uuid: str, limit: int = 50,
                     sent_before: datetime | None = None) -> list[RemoteMessage]:
        q = select(MockMessage).where(MockMessage.fan_uuid == fan_uuid)
        if sent_before:
            q = q.where(MockMessage.sent_at < sent_before)
        rows = self.db.scalars(q.order_by(MockMessage.sent_at.desc(), MockMessage.seq.desc()).limit(limit))
        return [RemoteMessage(uuid=m.uuid, fan_uuid=m.fan_uuid, sender=m.sender, text=m.text, sent_at=m.sent_at,
                              price_cents=m.price_cents, media_uuids=list(m.media_uuids or []),
                              message_type=m.message_type, tip_cents=m.tip_cents) for m in rows]

    def get_fan_insight(self, fan_uuid: str) -> FanInsight:
        f = self.db.get(MockFan, fan_uuid)
        if f is None:
            raise FanvueError("unknown mock fan", 404)
        return FanInsight(status=f.status, spent_cents=f.spent_cents, max_payment_cents=f.max_payment_cents,
                          last_purchase_at=f.last_purchase_at)

    def send_message(self, fan_uuid: str, text: str | None, media_uuids: list[str] | None = None,
                     price_cents: int | None = None, preview_media_uuid: str | None = None) -> str:
        if self.fail_sends:
            raise FanvueError("simulated send failure", 503, retryable=True)
        f = self.db.get(MockFan, fan_uuid)
        if f is None:
            raise FanvueError("unknown mock fan", 404)
        if f.status == "not_contactable":
            raise NotContactable("fan is not contactable", 400)
        if price_cents is not None and 0 < price_cents < 300:
            raise FanvueError("price must be at least 300 cents", 400)
        if not (text or media_uuids):
            raise FanvueError("message needs text or media", 400)
        media = list(media_uuids or [])
        if preview_media_uuid:
            media = [preview_media_uuid, *media]
        msg = MockMessage(uuid=str(uuid.uuid4()), fan_uuid=fan_uuid, sender="creator", text=text or "",
                          price_cents=price_cents, media_uuids=media, sent_at=utcnow(), seq=self._next_seq())
        self.db.add(msg)
        self.db.flush()
        return msg.uuid

    def list_media(self, cursor: str | None = None) -> tuple[list[RemoteMedia], str | None]:
        rows = self.db.scalars(select(MockMedia).order_by(MockMedia.name))
        return [RemoteMedia(uuid=m.uuid, name=m.name, media_type=m.media_type,
                            url=f"/api/mock/media/{m.uuid}.svg") for m in rows], None

    def typing(self, fan_uuid: str) -> None:
        return None
