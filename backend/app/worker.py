"""Background worker: periodic scheduling + job execution with retries.

Run inside the API process (default) or standalone: ``python -m app.worker``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.fanvue.base import FanvueError, NeedsReconnect
from app.models import Job
from app.services import checkins, engine, jobs, reengage, sender, sync
from app.services.retention import purge_old

log = logging.getLogger("wakeful.worker")

PERIODIC: list[tuple[str, int]] = [  # (kind, every_seconds)
    ("sync_fanvue", 0),  # replaced by settings.fanvue_poll_seconds
    ("reengage_scan", 15 * 60),
    ("checkins_due", 60),
    ("expire_drafts", 60 * 60),
    ("retention", 24 * 60 * 60),
    ("detect_purchases", 30 * 60),
]


def _h_sync(db: Session, p: dict[str, Any]) -> None:
    sync.sync(db)


def _h_generate(db: Session, p: dict[str, Any]) -> None:
    engine.generate_reply_job(db, int(p["fan_id"]), p.get("trigger_message_id"))


def _h_send(db: Session, p: dict[str, Any]) -> None:
    sender.send_draft(db, int(p["draft_id"]))


def _h_reengage(db: Session, p: dict[str, Any]) -> None:
    reengage.scan(db)


def _h_checkins(db: Session, p: dict[str, Any]) -> None:
    checkins.process_due(db)


def _h_expire(db: Session, p: dict[str, Any]) -> None:
    engine.expire_drafts(db)


def _h_retention(db: Session, p: dict[str, Any]) -> None:
    purge_old(db)


def _h_purchases(db: Session, p: dict[str, Any]) -> None:
    from app.fanvue import get_client
    from app.services import purchases

    purchases.detect_recent(db, get_client(db))


HANDLERS: dict[str, Callable[[Session, dict[str, Any]], None]] = {
    "sync_fanvue": _h_sync,
    "generate_reply": _h_generate,
    "send_draft": _h_send,
    "reengage_scan": _h_reengage,
    "checkins_due": _h_checkins,
    "expire_drafts": _h_expire,
    "retention": _h_retention,
    "detect_purchases": _h_purchases,
}


def schedule_periodic(db: Session, now_ts: float | None = None) -> None:
    now_ts = now_ts or time.time()
    for kind, every in PERIODIC:
        if kind == "sync_fanvue":
            every = max(get_settings().fanvue_poll_seconds, 15)
        bucket = int(now_ts // every)
        jobs.enqueue(db, kind, {}, idempotency_key=f"periodic-{kind}-{bucket}")
    db.commit()


def run_job(db: Session, job: Job) -> None:
    handler = HANDLERS.get(job.kind)
    if handler is None:
        jobs.fail(db, job, f"no handler for {job.kind}", 0, retry=False)
        db.commit()
        return
    try:
        handler(db, job.payload or {})
        db.refresh(job)
        jobs.finish(db, job)
    except sender.SendBlocked as exc:
        db.rollback()
        job = db.get(Job, job.id) or job
        jobs.fail(db, job, f"blocked: {exc}", 0, retry=False)
    except NeedsReconnect as exc:
        db.rollback()
        job = db.get(Job, job.id) or job
        jobs.fail(db, job, str(exc), 0, retry=False)
    except FanvueError as exc:
        db.rollback()
        job = db.get(Job, job.id) or job
        jobs.fail(db, job, str(exc), get_settings().job_max_attempts, retry=exc.retryable)
    except Exception as exc:  # noqa: BLE001 - worker must survive any handler error
        log.exception("job %s failed", job.id)
        db.rollback()
        job = db.get(Job, job.id) or job
        jobs.fail(db, job, f"{exc.__class__.__name__}: {exc}", get_settings().job_max_attempts)
    db.commit()


def tick(periodic: bool = True) -> int:
    """One worker iteration (sync code, run in a thread). Returns number of jobs processed."""
    db = SessionLocal()
    try:
        if periodic:
            schedule_periodic(db)
        claimed = jobs.claim_due(db, limit=10)
        for job in claimed:
            run_job(db, job)
        return len(claimed)
    finally:
        db.close()


async def run_forever(stop: asyncio.Event) -> None:
    interval = get_settings().worker_poll_seconds
    log.info("worker started at %s", utcnow())
    while not stop.is_set():
        try:
            n = await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001
            log.exception("worker tick failed")
            n = 0
        if n == 0:
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever(asyncio.Event()))
