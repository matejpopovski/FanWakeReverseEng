"""Synchronise fans and messages from Fanvue (mock or live) into the local database."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue import get_client
from app.fanvue.base import ChatSummary, FanvueClient, FanvueError, RemoteMessage
from app.fanvue.oauth import get_connection
from app.models import Draft, Fan, Message
from app.services import engine, jobs, purchases

FRESH_WINDOW = timedelta(hours=24)  # only react to inbound messages this recent


@dataclass
class SyncReport:
    fans_seen: int = 0
    fans_created: int = 0
    messages_added: int = 0
    inbound_triggers: int = 0
    errors: list[str] = field(default_factory=list)


def _upsert_fan(db: Session, chat: ChatSummary) -> tuple[Fan, bool]:
    fan = db.scalar(select(Fan).where(Fan.fanvue_uuid == chat.fan.uuid))
    created = False
    if fan is None:
        fan = Fan(fanvue_uuid=chat.fan.uuid, handle=chat.fan.handle, display_name=chat.fan.display_name,
                  avatar_url=chat.fan.avatar_url)
        db.add(fan)
        db.flush()
        created = True
    else:
        fan.handle = chat.fan.handle or fan.handle
        fan.display_name = chat.fan.display_name or fan.display_name
        fan.avatar_url = chat.fan.avatar_url or fan.avatar_url
    fan.unread_count = chat.unread_count
    return fan, created


def refresh_insight(db: Session, client: FanvueClient, fan: Fan) -> None:
    try:
        ins = client.get_fan_insight(fan.fanvue_uuid)
    except FanvueError:
        return
    fan.status = ins.status
    before = fan.total_spent_cents
    # keep locally-observed tips; total spend comes from Fanvue
    fan.total_spent_cents = max(ins.spent_cents, fan.tip_total_cents)
    fan.last_purchase_at = ins.last_purchase_at or fan.last_purchase_at
    if fan.total_spent_cents > before and before >= 0:
        # spend went up: check whether any offered PPV was unlocked
        purchases.detect_for_fan(db, client, fan, force=True)


def _ingest(db: Session, fan: Fan, remote: list[RemoteMessage], backfill: bool,
            report: SyncReport) -> None:
    known = set(db.scalars(select(Message.fanvue_uuid).where(Message.fan_id == fan.id,
                                                             Message.fanvue_uuid.is_not(None))))
    new = [m for m in sorted(remote, key=lambda m: m.sent_at) if m.uuid not in known]
    newest_inbound: tuple[Message, datetime | None] | None = None
    prev_inbound = fan.last_inbound_at
    for rm in new:
        msg = Message(fan_id=fan.id, fanvue_uuid=rm.uuid, direction="in" if rm.sender == "fan" else "out",
                      text=rm.text, sent_at=rm.sent_at, media_uuids=rm.media_uuids, price_cents=rm.price_cents,
                      message_type=rm.message_type, tip_cents=rm.tip_cents,
                      origin="fan" if rm.sender == "fan" else "operator")
        db.add(msg)
        db.flush()
        report.messages_added += 1
        if fan.first_contact_at is None or rm.sent_at < fan.first_contact_at:
            fan.first_contact_at = rm.sent_at
        if msg.direction == "in":
            if rm.tip_cents:
                fan.tips_count += 1
                fan.tip_total_cents += rm.tip_cents
                fan.max_tip_cents = max(fan.max_tip_cents, rm.tip_cents)
                fan.last_tip_at = rm.sent_at
            newest_inbound = (msg, prev_inbound)
            prev_inbound = rm.sent_at
            fan.last_inbound_at = max(fan.last_inbound_at or rm.sent_at, rm.sent_at)
        else:
            fan.last_outbound_at = max(fan.last_outbound_at or rm.sent_at, rm.sent_at)
            # the creator answered on Fanvue directly -> pending AI reply is obsolete
            for d in db.scalars(select(Draft).where(Draft.fan_id == fan.id, Draft.status == "pending",
                                                    Draft.kind == "reply")):
                d.status = "replaced"
                d.reject_reason = "answered outside the app"
    if new:
        fan.last_synced_message_uuid = new[-1].uuid
    if backfill or newest_inbound is None:
        return
    msg, prev = newest_inbound
    last_dir = db.scalar(select(Message.direction).where(Message.fan_id == fan.id)
                         .order_by(Message.sent_at.desc(), Message.id.desc()))
    if last_dir == "in" and utcnow() - msg.sent_at <= FRESH_WINDOW:
        engine.on_inbound(db, fan, msg, prev_inbound_at=prev)
        report.inbound_triggers += 1


def sync(db: Session, client: FanvueClient | None = None, max_pages: int = 20,
         refresh_all_insights: bool = False) -> SyncReport:
    client = client or get_client(db)
    report = SyncReport()
    cursor: str | None = None
    for _ in range(max_pages):
        try:
            chats, cursor = client.list_chats(cursor)
        except FanvueError as exc:
            report.errors.append(str(exc))
            break
        for chat in chats:
            report.fans_seen += 1
            fan, created = _upsert_fan(db, chat)
            if created:
                report.fans_created += 1
            latest_local = db.scalar(select(Message.sent_at).where(Message.fan_id == fan.id)
                                     .order_by(Message.sent_at.desc()))
            changed = created or (chat.last_message_at and (latest_local is None
                                                            or chat.last_message_at > latest_local))
            if changed:
                try:
                    remote = client.get_messages(fan.fanvue_uuid, limit=50)
                except FanvueError as exc:
                    report.errors.append(f"{fan.id}: {exc}")
                    continue
                _ingest(db, fan, remote, backfill=created, report=report)
            if changed or created or refresh_all_insights:
                refresh_insight(db, client, fan)
            db.commit()
        if not cursor:
            break
    conn = get_connection(db)
    conn.last_sync_at = utcnow()
    conn.last_error = "; ".join(report.errors)[:1000] or None
    jobs.audit(db, "worker", "sync.completed", detail_fans=report.fans_seen, added=report.messages_added,
               triggers=report.inbound_triggers, errors=len(report.errors))
    db.commit()
    return report
