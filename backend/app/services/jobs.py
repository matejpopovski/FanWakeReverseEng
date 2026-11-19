"""DB-backed job queue with idempotency, retries and backoff."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import AuditLog, Job

STALE_LOCK = timedelta(minutes=10)


def audit(db: Session, actor: str, action: str, entity: str | None = None, entity_id: Any = None,
          **detail: Any) -> None:
    db.add(AuditLog(actor=actor, action=action, entity=entity,
                    entity_id=None if entity_id is None else str(entity_id), detail=detail))


def enqueue(db: Session, kind: str, payload: dict[str, Any] | None = None, run_at: datetime | None = None,
            idempotency_key: str | None = None) -> Job | None:
    """Insert a job. Returns None if a job with the same idempotency key already exists."""
    if idempotency_key:
        existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing is not None:
            return None
    job = Job(kind=kind, payload=payload or {}, run_at=run_at or utcnow(), idempotency_key=idempotency_key)
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return None
    return job


def cancel_jobs(db: Session, kind: str, **match: Any) -> int:
    n = 0
    for job in db.scalars(select(Job).where(Job.kind == kind, Job.status == "queued")):
        if all(job.payload.get(k) == v for k, v in match.items()):
            job.status = "cancelled"
            n += 1
    return n


def claim_due(db: Session, limit: int = 10) -> list[Job]:
    """Atomically claim due jobs (works on SQLite and Postgres)."""
    now = utcnow()
    # recover stale locks
    db.execute(update(Job).where(Job.status == "running", Job.locked_at < now - STALE_LOCK)
               .values(status="queued", locked_at=None))
    ids = list(db.scalars(select(Job.id).where(Job.status == "queued", Job.run_at <= now)
                          .order_by(Job.run_at, Job.id).limit(limit)))
    claimed: list[Job] = []
    for jid in ids:
        res = db.execute(update(Job).where(Job.id == jid, Job.status == "queued")
                         .values(status="running", locked_at=now, attempts=Job.attempts + 1))
        if res.rowcount == 1:  # type: ignore[attr-defined]
            job = db.get(Job, jid)
            if job:
                claimed.append(job)
    db.commit()
    return claimed


def finish(db: Session, job: Job) -> None:
    job.status = "done"
    job.locked_at = None
    job.last_error = None


def fail(db: Session, job: Job, error: str, max_attempts: int, retry: bool = True) -> None:
    job.last_error = error[:2000]
    job.locked_at = None
    if retry and job.attempts < max_attempts:
        job.status = "queued"
        job.run_at = utcnow() + timedelta(seconds=min(30 * 2 ** (job.attempts - 1), 3600))
    else:
        job.status = "dead"
