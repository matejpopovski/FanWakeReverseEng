"""Integration tests over the real DB + mock Fanvue: sync, drafting, review, sending, safety gates."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue.mock import MockFanvueClient
from app.models import Alert, Checkin, Draft, Fan, Job, Message, MockFan, MockMessage, PpvOffer, PpvTemplate
from app.services import checkins, engine, jobs, reengage, sender, sync
from app.settings_store import ReengageSettings, SafetySettings, load, save
from app.worker import run_job
from tests.conftest import enable_engine


def contactable_fan(db: Session) -> Fan:
    return db.scalar(select(Fan).where(Fan.status != "not_contactable").order_by(Fan.id))


def say(db: Session, fan: Fan, text: str, tip: int | None = None) -> None:
    MockFanvueClient(db).add_fan_message(fan.fanvue_uuid, text, tip_cents=tip)
    db.commit()
    sync.sync(db)


def run_queued(db: Session, kind: str) -> int:
    n = 0
    for j in list(db.scalars(select(Job).where(Job.kind == kind, Job.status == "queued"))):
        j.status, j.attempts = "running", j.attempts + 1
        db.commit()
        run_job(db, j)
        n += 1
    return n


def test_initial_sync_backfills_without_triggering(seeded: Session) -> None:
    assert seeded.scalar(select(func.count()).select_from(Fan)) == 12
    remote = seeded.scalar(select(func.count()).select_from(MockMessage))
    assert seeded.scalar(select(func.count()).select_from(Message)) == remote
    assert seeded.scalar(select(func.count()).select_from(Job).where(Job.kind == "generate_reply")) == 0
    # second sync is a no-op (idempotent)
    rep = sync.sync(seeded)
    assert rep.messages_added == 0 and rep.fans_created == 0


def test_inbound_review_mode_creates_pending_draft(seeded: Session) -> None:
    enable_engine(seeded)
    fan = contactable_fan(seeded)
    say(seeded, fan, "hey how is your day going?")
    job = seeded.scalar(select(Job).where(Job.kind == "generate_reply", Job.status == "queued"))
    assert job and job.payload["fan_id"] == fan.id
    assert job.run_at <= utcnow() + timedelta(seconds=1)  # review mode: no artificial delay
    run_queued(seeded, "generate_reply")
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id))
    assert d.status == "pending" and d.bubbles and d.route_reason == "review-first mode"
    assert d.prompt_version_id and d.provider == "mock"
    assert seeded.scalar(select(func.count()).select_from(Job).where(Job.kind == "send_draft")) == 0


def test_debounce_and_replace(seeded: Session) -> None:
    enable_engine(seeded)
    fan = contactable_fan(seeded)
    say(seeded, fan, "hello?")
    say(seeded, fan, "you there?")
    queued = list(seeded.scalars(select(Job).where(Job.kind == "generate_reply", Job.status == "queued")))
    assert len(queued) == 1  # older job cancelled
    run_queued(seeded, "generate_reply")
    say(seeded, fan, "one more thing")
    run_queued(seeded, "generate_reply")
    statuses = sorted(d.status for d in seeded.scalars(select(Draft).where(Draft.fan_id == fan.id)))
    assert statuses == ["pending", "replaced"]


def test_approve_edit_and_send(seeded: Session, client) -> None:  # type: ignore[no-untyped-def]
    enable_engine(seeded)
    fan = contactable_fan(seeded)
    say(seeded, fan, "what are you doing tonight")
    run_queued(seeded, "generate_reply")
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id, Draft.status == "pending"))
    r = client.post(f"/api/drafts/{d.id}/approve", json={"bubbles": ["edited reply", "  "]})
    assert r.status_code == 200 and r.json()["edited"] is True
    seeded.expire_all()
    assert run_queued(seeded, "send_draft") == 1
    seeded.expire_all()
    d = seeded.get(Draft, d.id)
    assert d.status == "sent" and d.bubbles == ["edited reply"] and d.approved_by == "operator"
    remote = seeded.scalar(select(MockMessage).where(MockMessage.fan_uuid == fan.fanvue_uuid,
                                                     MockMessage.sender == "creator")
                           .order_by(MockMessage.seq.desc()))
    assert remote.text == "edited reply"
    # resync must not duplicate the sent message
    sync.sync(seeded)
    assert seeded.scalar(select(func.count()).select_from(Message).where(Message.text == "edited reply")) == 1
    # approving again is rejected
    assert client.post(f"/api/drafts/{d.id}/approve", json={}).status_code == 409


def test_auto_mode_sends_with_pacing(seeded: Session) -> None:
    enable_engine(seeded, approval_mode="auto")
    fan = contactable_fan(seeded)
    say(seeded, fan, "hey")
    job = seeded.scalar(select(Job).where(Job.kind == "generate_reply", Job.status == "queued"))
    assert job.run_at > utcnow()  # human-like delay
    run_queued(seeded, "generate_reply")
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id))
    assert d.status == "approved" and d.approved_by == "auto"
    run_queued(seeded, "send_draft")
    seeded.expire_all()
    assert seeded.get(Draft, d.id).status == "sent"


def test_kill_switch_holds_auto_drafts(seeded: Session) -> None:
    enable_engine(seeded, approval_mode="auto")
    fan = contactable_fan(seeded)
    say(seeded, fan, "hey")
    run_queued(seeded, "generate_reply")
    s = load(seeded, SafetySettings)
    s.automation_paused = True
    save(seeded, s)
    seeded.commit()
    run_queued(seeded, "send_draft")
    seeded.expire_all()
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id))
    assert d.status == "pending" and "kill switch" in d.route_reason


def test_live_mode_blocks_sending_unless_enabled(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    fan = contactable_fan(seeded)
    d = Draft(fan_id=fan.id, kind="manual", status="approved", bubbles=["hi"], approved_by="operator")
    seeded.add(d)
    seeded.commit()
    monkeypatch.setattr(get_settings(), "fanvue_mode", "live")
    with pytest.raises(sender.SendBlocked):
        sender.send_draft(seeded, d.id, client=MockFanvueClient(seeded))
    seeded.expire_all()
    assert seeded.get(Draft, d.id).status == "pending"
    assert seeded.scalar(select(func.count()).select_from(MockMessage).where(MockMessage.text == "hi")) == 0


@pytest.mark.parametrize(("text", "cat"), [("are you a bot?", "ai_question"),
                                           ("pay you on telegram?", "off_platform_payment")])
def test_escalation_stops_automation(seeded: Session, text: str, cat: str) -> None:
    enable_engine(seeded, approval_mode="auto")
    fan = contactable_fan(seeded)
    say(seeded, fan, text)
    seeded.expire_all()
    fan = seeded.get(Fan, fan.id)
    assert fan.escalated and fan.escalation_reason == cat
    assert seeded.scalar(select(Alert).where(Alert.fan_id == fan.id, Alert.kind == "escalation"))
    assert seeded.scalar(select(func.count()).select_from(Job).where(Job.kind == "generate_reply",
                                                                   Job.status == "queued")) == 0


def test_guardrail_flag_forces_review(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from app.ai import providers

    enable_engine(seeded, approval_mode="auto")
    fan = contactable_fan(seeded)

    def fake(self, req):  # type: ignore[no-untyped-def]
        return providers.GenerationResult(text=json.dumps({"messages": ["lol i'm a real person"]}),
                                          provider="mock", model="m")

    monkeypatch.setattr(providers.MockProvider, "generate", fake)
    d = engine.create_draft(seeded, fan, "reply")
    assert d.status == "pending" and "claims_human_or_denies_ai" in d.guardrail_flags


def test_ai_flagged_escalation(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from app.ai import providers

    fan = contactable_fan(seeded)
    monkeypatch.setattr(providers.MockProvider, "generate", lambda self, req: providers.GenerationResult(
        text=json.dumps({"messages": [], "escalate": "complaint"}), provider="mock", model="m"))
    assert engine.create_draft(seeded, fan, "reply") is None
    assert seeded.get(Fan, fan.id).escalated


def test_ppv_offer_gates_cooldown_and_purchase(seeded: Session) -> None:
    from app.services import ppv

    fan = contactable_fan(seeded)
    fan.total_spent_cents, fan.ppv_purchases = 0, 0
    seeded.commit()
    names = {t.name for t in ppv.eligible_templates(seeded, fan, 25)}
    assert "Premium bundle" not in names  # gate_min_purchases=2
    assert "Beach day set" in names  # first purchase only + new fan
    fan.total_spent_cents = 1000
    assert "Beach day set" not in {t.name for t in ppv.eligible_templates(seeded, fan, 25)}
    tpl = seeded.scalar(select(PpvTemplate).where(PpvTemplate.name == "Gym session clip"))
    seeded.add(PpvOffer(fan_id=fan.id, template_id=tpl.id, status="pitched", pitched_at=utcnow()))
    seeded.commit()
    assert tpl.id not in {t.id for t in ppv.eligible_templates(seeded, fan, 25)}  # cooldown
    assert tpl.id not in {t.id for t in ppv.eligible_templates(seeded, fan, None)}  # never re-pitch
    off = seeded.scalar(select(PpvOffer).where(PpvOffer.template_id == tpl.id))
    off.status = "purchased"
    seeded.commit()
    assert tpl.id in ppv.owned_template_ids(seeded, fan.id)


def test_ppv_draft_send_records_offer(seeded: Session) -> None:
    enable_engine(seeded)
    fan = contactable_fan(seeded)
    fan.total_spent_cents = 0
    seeded.commit()
    for _ in range(3):  # get past the 'new fan' depth
        say(seeded, fan, "chatting")
    say(seeded, fan, "can i see more pics?")
    run_queued(seeded, "generate_reply")
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id, Draft.status == "pending"))
    assert d.ppv_template_id is not None
    d.status, d.approved_by = "approved", "operator"
    seeded.commit()
    sender.send_draft(seeded, d.id, bubble_gap_s=0)
    off = seeded.scalar(select(PpvOffer).where(PpvOffer.draft_id == d.id))
    assert off and off.status == "pitched"
    last = seeded.scalar(select(MockMessage).where(MockMessage.fan_uuid == fan.fanvue_uuid)
                         .order_by(MockMessage.seq.desc()))
    tpl = seeded.get(PpvTemplate, d.ppv_template_id)
    assert last.price_cents == (tpl.price_cents or None) and last.media_uuids


def test_send_retry_is_idempotent(seeded: Session) -> None:
    fan = contactable_fan(seeded)
    d = Draft(fan_id=fan.id, kind="manual", status="approved", bubbles=["one", "two"], approved_by="operator")
    seeded.add(d)
    seeded.commit()
    flaky = MockFanvueClient(seeded)
    calls = {"n": 0}
    orig = flaky.send_message

    def send(*a, **kw):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 2:
            from app.fanvue.base import FanvueError

            raise FanvueError("boom", 503, retryable=True)
        return orig(*a, **kw)

    flaky.send_message = send  # type: ignore[method-assign]
    from app.fanvue.base import FanvueError

    with pytest.raises(FanvueError):
        sender.send_draft(seeded, d.id, client=flaky, bubble_gap_s=0)
    seeded.expire_all()
    assert seeded.get(Draft, d.id).sent_bubbles == 1
    sender.send_draft(seeded, d.id, client=flaky, bubble_gap_s=0)
    texts = [m.text for m in seeded.scalars(select(MockMessage).where(MockMessage.fan_uuid == fan.fanvue_uuid,
                                                                     MockMessage.sender == "creator")
                                            .order_by(MockMessage.seq.desc()).limit(2))]
    assert texts == ["two", "one"]  # exactly once each
    assert sender.send_draft(seeded, d.id).status == "sent"  # idempotent


def test_not_contactable_marks_fan(seeded: Session) -> None:
    fan = contactable_fan(seeded)
    seeded.get(MockFan, fan.fanvue_uuid).status = "not_contactable"
    d = Draft(fan_id=fan.id, kind="reengage", status="approved", bubbles=["hi"], approved_by="operator")
    seeded.add(d)
    seeded.commit()
    sender.send_draft(seeded, d.id)
    seeded.expire_all()
    f = seeded.get(Fan, fan.id)
    assert seeded.get(Draft, d.id).status == "failed" and f.status == "not_contactable"
    assert f.reengage_state == "unreachable"


def test_job_queue_retry_backoff_and_idempotency(seeded: Session) -> None:
    j = jobs.enqueue(seeded, "nope", {}, idempotency_key="k1")
    assert jobs.enqueue(seeded, "nope", {}, idempotency_key="k1") is None
    seeded.commit()
    claimed = jobs.claim_due(seeded)
    assert [c.id for c in claimed] == [j.id]
    assert jobs.claim_due(seeded) == []  # already running
    jobs.fail(seeded, j, "err", max_attempts=2)
    assert j.status == "queued" and j.run_at > utcnow()
    j.attempts = 2
    jobs.fail(seeded, j, "err", max_attempts=2)
    assert j.status == "dead"


def test_reengage_state_machine(seeded: Session) -> None:
    s = load(seeded, ReengageSettings)
    s.enabled, s.attempts, s.schedule_days, s.silence_hours, s.active_within_days = True, 2, [2, 5], 48, None
    save(seeded, s)
    fan = contactable_fan(seeded)
    for other in seeded.scalars(select(Fan).where(Fan.id != fan.id)):
        other.reengage_enabled = False
    fan.last_inbound_at = utcnow() - timedelta(days=3)
    fan.last_outbound_at = utcnow() - timedelta(days=3, hours=1)
    seeded.commit()
    rep = reengage.scan(seeded)
    assert rep.drafted == 1
    seeded.expire_all()
    f = seeded.get(Fan, fan.id)
    assert f.reengage_state == "active" and f.reengage_attempts == 1
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id, Draft.kind == "reengage"))
    assert d.status == "pending"  # review-first default
    # not due again yet
    assert reengage.scan(seeded).drafted == 0
    # send attempt 1, then advance time past day 5
    d.status, d.approved_by = "approved", "operator"
    seeded.commit()
    sender.send_draft(seeded, d.id)
    assert reengage.scan(seeded, now=utcnow() + timedelta(days=3)).drafted == 1
    seeded.expire_all()
    f = seeded.get(Fan, fan.id)
    assert f.reengage_attempts == 2
    d2 = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id, Draft.kind == "reengage",
                                           Draft.status == "pending"))
    d2.status, d2.approved_by = "approved", "operator"
    seeded.commit()
    sender.send_draft(seeded, d2.id)
    # fan replies -> awakened
    say(seeded, f, "omg hi, sorry was busy")
    seeded.expire_all()
    assert seeded.get(Fan, fan.id).reengage_state == "awakened"


def test_reengage_completes_without_reply(seeded: Session) -> None:
    fan = contactable_fan(seeded)
    fan.reengage_state, fan.reengage_attempts = "active", 3
    fan.reengage_last_sent_at = utcnow() - timedelta(days=8)
    s = load(seeded, ReengageSettings)
    s.enabled = True
    save(seeded, s)
    seeded.commit()
    assert reengage.scan(seeded).completed >= 1
    assert seeded.get(Fan, fan.id).reengage_state == "completed"


def test_checkins_skip_when_fan_wrote_again(seeded: Session) -> None:
    enable_engine(seeded)
    fan = contactable_fan(seeded)
    c1 = engine.plan_checkin(seeded, fan, "ask about the exam", 2, 5)
    c1.scheduled_at = utcnow() - timedelta(minutes=1)
    c1.created_at = utcnow() - timedelta(hours=3)
    seeded.commit()
    fan.last_inbound_at = utcnow()
    seeded.commit()
    checkins.process_due(seeded)
    assert seeded.get(Checkin, c1.id).status == "skipped"
    c2 = engine.plan_checkin(seeded, fan, "ask how the trip went", 2, 5)
    c2.scheduled_at = utcnow() - timedelta(minutes=1)
    seeded.commit()
    checkins.process_due(seeded)
    seeded.expire_all()
    c2 = seeded.get(Checkin, c2.id)
    assert c2.status == "drafted"
    assert seeded.get(Draft, c2.draft_id).kind == "checkin"


def test_checkin_weekly_limit(seeded: Session) -> None:
    fan = contactable_fan(seeded)
    assert engine.plan_checkin(seeded, fan, "a", 5, 1) is not None
    assert engine.plan_checkin(seeded, fan, "b", 5, 1) is None


def test_operator_reply_on_fanvue_supersedes_pending(seeded: Session) -> None:
    enable_engine(seeded)
    fan = contactable_fan(seeded)
    say(seeded, fan, "hi there")
    run_queued(seeded, "generate_reply")
    MockFanvueClient(seeded).send_message(fan.fanvue_uuid, "answered from phone")
    seeded.commit()
    sync.sync(seeded)
    d = seeded.scalar(select(Draft).where(Draft.fan_id == fan.id))
    assert d.status == "replaced"


def test_expire_drafts(seeded: Session) -> None:
    fan = contactable_fan(seeded)
    d = Draft(fan_id=fan.id, kind="reply", status="pending", bubbles=["x"],
              created_at=utcnow() - timedelta(hours=48))
    seeded.add(d)
    seeded.commit()
    assert engine.expire_drafts(seeded) == 1


def test_worker_retries_then_dead_letters(seeded: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import worker
    from app.fanvue.base import FanvueError

    def boom(db, p):  # type: ignore[no-untyped-def]
        raise FanvueError("upstream 503", 503, retryable=True)

    monkeypatch.setitem(worker.HANDLERS, "sync_fanvue", boom)
    j = jobs.enqueue(seeded, "sync_fanvue", {})
    seeded.commit()
    for _ in range(6):
        j = seeded.get(Job, j.id)
        if j.status == "dead":
            break
        j.status, j.attempts, j.run_at = "running", j.attempts + 1, utcnow()
        seeded.commit()
        run_job(seeded, j)
    seeded.expire_all()
    j = seeded.get(Job, j.id)
    assert j.status == "dead" and "503" in j.last_error


def test_worker_tick_processes_due_jobs(seeded: Session) -> None:
    from app import worker

    enable_engine(seeded)
    fan = contactable_fan(seeded)
    say(seeded, fan, "tick test")
    processed = worker.tick(periodic=False)
    assert processed >= 1
    seeded.expire_all()
    assert seeded.scalar(select(Draft).where(Draft.fan_id == fan.id, Draft.status == "pending"))
