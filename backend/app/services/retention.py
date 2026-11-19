"""Data retention and per-fan erasure."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import AiUsage, AuditLog, Job, Message
from app.services import jobs


def purge_old(db: Session) -> dict[str, int]:
    days = get_settings().retention_days_messages
    cutoff = utcnow() - timedelta(days=days)
    r1 = db.execute(delete(Message).where(Message.sent_at < cutoff)).rowcount  # type: ignore[attr-defined]
    r2 = db.execute(delete(Job).where(Job.status.in_(("done", "cancelled")),
                                      Job.updated_at < utcnow() - timedelta(days=14))).rowcount  # type: ignore[attr-defined]
    r3 = db.execute(delete(AiUsage).where(AiUsage.at < cutoff)).rowcount  # type: ignore[attr-defined]
    r4 = db.execute(delete(AuditLog).where(AuditLog.at < cutoff)).rowcount  # type: ignore[attr-defined]
    jobs.audit(db, "worker", "retention.purge", messages=r1, jobs=r2, usage=r3, audit=r4)
    return {"messages": r1, "jobs": r2, "ai_usage": r3, "audit": r4}
