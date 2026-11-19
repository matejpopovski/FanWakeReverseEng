"""Purchase detection, sales learning in prompts, time cooldowns and offer gaps."""

from __future__ import annotations

from datetime import timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue.mock import MockFanvueClient
from app.models import Draft, Fan, Message, PpvOffer, PpvTag, PpvTemplate
from app.services import engine, ppv, purchases, sync
from app.settings_store import EngineSettings, load
from tests.conftest import enable_engine


def _fan(db: Session) -> Fan:
    return db.scalar(select(Fan).where(Fan.status != "not_contactable").order_by(Fan.id))


def _tpl(db: Session, name: str = "Gym session clip") -> PpvTemplate:
    return db.scalar(select(PpvTemplate).where(PpvTemplate.name == name))


def _pitch(db: Session, fan: Fan, tpl: PpvTemplate, hours_ago: float = 1) -> PpvOffer:
    o = PpvOffer(fan_id=fan.id, template_id=tpl.id, status="pitched", pitched_at=utcnow() - timedelta(hours=hours_ago))
    db.add(o)
    db.commit()
    return o


def test_detects_unlocked_offer(seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    offer = _pitch(seeded, fan, tpl)
    client = MockFanvueClient(seeded)
    assert purchases.detect_for_fan(seeded, client, fan, force=True) == 0  # not bought yet
    client.unlock_media(fan.fanvue_uuid, tpl.media_uuids, tpl.price_cents)
    seeded.commit()
    before = fan.ppv_purchases
    assert purchases.detect_for_fan(seeded, client, fan, force=True) == 1
    seeded.commit()
    assert offer.status == "purchased" and offer.source == "detected" and offer.amount_cents == tpl.price_cents
    assert fan.ppv_purchases == before + 1
    assert tpl.id in ppv.owned_template_ids(seeded, fan.id)  # never offered again
    assert purchases.detect_for_fan(seeded, client, fan) == 0  # throttled re-check


def test_partial_unlock_is_not_a_purchase(seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    _pitch(seeded, fan, tpl)
    client = MockFanvueClient(seeded)
    client.unlock_media(fan.fanvue_uuid, tpl.media_uuids[:1], 0)
    seeded.commit()
    assert purchases.detect_for_fan(seeded, client, fan, force=True) == 0


def test_spend_increase_triggers_detection_in_sync(seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    offer = _pitch(seeded, fan, tpl)
    client = MockFanvueClient(seeded)
    client.unlock_media(fan.fanvue_uuid, tpl.media_uuids, tpl.price_cents)
    seeded.commit()
    sync.refresh_insight(seeded, client, fan)
    assert offer.status == "purchased"


def test_periodic_sweep(seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    _pitch(seeded, fan, tpl)
    old = _pitch(seeded, fan, _tpl(seeded, "Evening photoshoot"), hours_ago=24 * 40)  # outside lookback
    client = MockFanvueClient(seeded)
    client.unlock_media(fan.fanvue_uuid, tpl.media_uuids + _tpl(seeded, "Evening photoshoot").media_uuids, 0)
    seeded.commit()
    assert purchases.detect_recent(seeded, client) == 1
    assert old.status == "pitched"


def test_live_client_purchase_lookup_contract() -> None:
    from app.fanvue.live import LiveFanvueClient

    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"uuid": "m1", "purchasedByFan": True})

    c = LiveFanvueClient(token_provider=lambda: "T", transport=httpx.MockTransport(handler))
    assert c.media_purchased_by("fan-1", "m1") is True
    assert seen[0].url.path == "/v1/media/m1" and seen[0].url.params["purchasedBy"] == "fan-1"


def test_time_cooldown_requires_both_messages_and_hours(seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    _pitch(seeded, fan, tpl, hours_ago=10)
    for i in range(30):  # plenty of messages since the offer
        seeded.add(Message(fan_id=fan.id, direction="in", text=f"m{i}", sent_at=utcnow() - timedelta(minutes=30 - i)))
    seeded.commit()
    assert not ppv.on_cooldown(seeded, fan, tpl.id, 25)  # message cooldown alone: passed
    assert ppv.on_cooldown(seeded, fan, tpl.id, 25, cooldown_hours=72)  # but only 10h have passed
    assert not ppv.on_cooldown(seeded, fan, tpl.id, 25, cooldown_hours=8)


def test_min_gap_between_offers_blocks_everything(seeded: Session) -> None:
    fan = _fan(seeded)
    fan.total_spent_cents = 0
    seeded.commit()
    assert ppv.eligible_templates(seeded, fan, 25, 72, 12)
    _pitch(seeded, fan, _tpl(seeded), hours_ago=3)
    assert ppv.eligible_templates(seeded, fan, 25, 72, 12) == []
    assert "minimum gap 12h" in (ppv.offer_gap_reason(seeded, fan, 12) or "")
    assert ppv.eligible_templates(seeded, fan, 25, 72, 0)  # gap off -> other templates allowed again


def test_in_flight_offer_blocks_new_offers(seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    seeded.add(Draft(fan_id=fan.id, kind="reengage", status="approved", bubbles=["x"], ppv_template_id=tpl.id))
    seeded.commit()
    assert "already waiting" in (ppv.offer_gap_reason(seeded, fan, 0) or "")
    assert ppv.eligible_templates(seeded, fan, 25) == []


def test_prompt_includes_track_record_buying_profile_and_gap_reason(seeded: Session) -> None:
    enable_engine(seeded)
    fan = _fan(seeded)
    fan.total_spent_cents = 2000
    other = seeded.scalar(select(Fan).where(Fan.id != fan.id))
    gym, evening = _tpl(seeded), _tpl(seeded, "Evening photoshoot")
    for i in range(4):  # gym: 4 offers, 3 sales across fans
        seeded.add(PpvOffer(fan_id=other.id, template_id=gym.id, status="purchased" if i else "pitched",
                            pitched_at=utcnow() - timedelta(days=5)))
    seeded.add(PpvOffer(fan_id=fan.id, template_id=evening.id, status="purchased", pitched_at=utcnow() - timedelta(days=9)))
    seeded.commit()
    for _ in range(5):
        seeded.add(Message(fan_id=fan.id, direction="in", text="hi", sent_at=utcnow() - timedelta(days=1)))
    seeded.commit()
    req, meta = engine.build_request(seeded, fan, "reply")
    assert '"track_record": "3/4 offers bought (75%)"' in req.system
    best = seeded.scalar(select(PpvTag).where(PpvTag.name == "best seller"))
    assert f"bought before: {best.name} x1" in req.system
    _pitch(seeded, fan, gym, hours_ago=1)
    req2, _ = engine.build_request(seeded, fan, "reply")
    assert "ELIGIBLE PPV: none (last offer was" in req2.system


def test_settings_and_api_exposure(client: TestClient, seeded: Session) -> None:
    e = client.put("/api/settings/engine", json={"repitch_cooldown_hours": 48, "min_hours_between_offers": 6}).json()
    assert e["repitch_cooldown_hours"] == 48 and e["min_hours_between_offers"] == 6
    assert client.put("/api/settings/engine", json={"min_hours_between_offers": -1}).status_code == 422
    fan = _fan(seeded)
    d = client.get(f"/api/fans/{fan.id}").json()["content"]
    assert "offer_block_reason" in d and "buying_profile" in d
    assert client.post(f"/api/fans/{fan.id}/detect-purchases").json() == {"detected": 0}


def test_simulated_purchase_goes_through_detection(client: TestClient, seeded: Session) -> None:
    fan, tpl = _fan(seeded), _tpl(seeded)
    _pitch(seeded, fan, tpl)
    r = client.post("/api/mock/simulate-purchase", json={"fan_id": fan.id, "template_id": tpl.id})
    assert r.json() == {"ok": True, "detected": True}
    assert load(seeded, EngineSettings).min_hours_between_offers == 12  # default
