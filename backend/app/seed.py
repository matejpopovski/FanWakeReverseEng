"""Synthetic demo data for mock mode. All people and messages here are fictional."""

from __future__ import annotations

import random
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.fanvue.mock import MockFanvueClient
from app.models import CustomRule, MockFan, MockMedia, MockMessage, PpvTag, PpvTemplate
from app.services import rules as rules_svc
from app.settings_store import EngineSettings, Persona, ReengageSettings, SafetySettings, load, save

FIRST = ["Alex", "Sam", "Jordan", "Chris", "Taylor", "Morgan", "Jamie", "Riley", "Casey", "Drew", "Robin",
         "Quinn", "Avery", "Parker", "Reese", "Skyler", "Hayden", "Rowan", "Elliot", "Kai"]
LAST = ["Harbor", "Pine", "Stone", "Brook", "Vale", "Frost", "Reed", "Lark", "Moss", "Wren"]
FAN_LINES = [
    "hey how's your day going?", "you looked amazing in your last post", "what are you up to tonight?",
    "just got off work, so tired lol", "do you like hiking?", "i've been thinking about you",
    "what's your favourite movie?", "good morning beautiful", "haha you're funny",
    "any new content coming soon?", "how was the gym today?", "goodnight, talk tomorrow",
]
CREATOR_LINES = [
    "hey you, it's been a busy one but better now", "aww thank you, that made my day",
    "just relaxing with some music, you?", "go rest, you earned it",
    "i love hiking when the weather is nice", "haha i try", "morning! coffee first though",
]
COLORS = ["#f97316", "#8b5cf6", "#06b6d4", "#22c55e", "#ef4444", "#eab308", "#ec4899", "#14b8a6"]


def seed_mock(db: Session, fans: int = 30, rng_seed: int = 7) -> dict[str, int]:
    """Idempotent: does nothing if mock fans already exist."""
    if db.scalar(select(MockFan).limit(1)) is not None:
        return {"fans": 0}
    rng = random.Random(rng_seed)
    now = utcnow()
    media = []
    for i in range(12):
        m = MockMedia(uuid=str(uuid.UUID(int=rng.getrandbits(128))), name=f"Vault item {i + 1}",
                      media_type="video" if i % 4 == 0 else "image", color=COLORS[i % len(COLORS)])
        db.add(m)
        media.append(m)
    seq = 0
    for i in range(fans):
        name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 3) % len(LAST)]}"
        status = rng.choices(["subscriber", "follower", "expired", "not_contactable"], [5, 8, 2, 1])[0]
        spent = rng.choice([0, 0, 0, 500, 1299, 2500, 4999, 12000, 30000]) if status != "follower" or rng.random() < .3 else 0
        f = MockFan(uuid=str(uuid.UUID(int=rng.getrandbits(128))), handle=name.lower().replace(" ", "_"),
                    display_name=name, status=status, spent_cents=spent, max_payment_cents=min(spent, 4999),
                    last_purchase_at=now - timedelta(days=rng.randint(1, 60)) if spent else None,
                    registered_at=now - timedelta(days=rng.randint(30, 400)))
        db.add(f)
        last_active_days = rng.choice([0, 0, 1, 2, 3, 5, 8, 15, 30, 45, 70, 120])
        n_msgs = rng.randint(0, 14) if i else 6
        t = now - timedelta(days=last_active_days, hours=rng.randint(1, 20)) - timedelta(minutes=n_msgs * 7)
        for k in range(n_msgs):
            seq += 1
            fan_turn = k % 2 == 0
            db.add(MockMessage(uuid=str(uuid.UUID(int=rng.getrandbits(128))), fan_uuid=f.uuid,
                               sender="fan" if fan_turn else "creator",
                               text=rng.choice(FAN_LINES if fan_turn else CREATOR_LINES),
                               sent_at=t + timedelta(minutes=k * 7), seq=seq))
    db.flush()
    _seed_ppv(db, media)
    return {"fans": fans, "media": len(media)}


def _seed_ppv(db: Session, media: list[MockMedia]) -> None:
    if db.scalar(select(PpvTag).limit(1)) is not None:
        return
    tags = {
        "entry level": "Cheap first unlock, good icebreaker for fans who never bought.",
        "best seller": "Converts well; a safe pick when the moment fits.",
        "premium": "High price; only for proven buyers or when the fan asks for more.",
        "follow-up": "Natural next unlock after a related purchase.",
        "tease": "Suggestive, not explicit; fine to offer early.",
    }
    tag_rows = {}
    for n, d in tags.items():
        t = PpvTag(name=n, description=d)
        db.add(t)
        tag_rows[n] = t
    db.flush()
    templates = [
        ("Beach day set", "Sunny beach photo set, 8 photos in a summer outfit.", 699, ["entry level", "tease"], True),
        ("Gym session clip", "Short video from a workout session, playful and sporty.", 1299, ["best seller"], False),
        ("Evening photoshoot", "Dressed-up evening photoshoot, 12 photos, moody lighting.", 1999, ["best seller"], False),
        ("Behind the scenes", "Casual behind-the-scenes clip from a shoot day.", 999, ["follow-up"], False),
        ("Premium bundle", "Large bundle: 3 videos and 20 photos from this month.", 4999, ["premium"], False),
        ("Free hello pic", "A free selfie to say hi to new fans.", 0, ["tease"], False),
    ]
    for i, (name, desc, price, tnames, first_only) in enumerate(templates):
        tpl = PpvTemplate(name=name, description=desc, price_cents=price,
                          media_uuids=[media[(i * 2) % len(media)].uuid, media[(i * 2 + 1) % len(media)].uuid],
                          preview_media_uuid=media[(i + 5) % len(media)].uuid if price else None,
                          tag_ids=[tag_rows[t].id for t in tnames], first_purchase_only=first_only,
                          gate_min_purchases=2 if "premium" in tnames else None)
        db.add(tpl)


def seed_defaults(db: Session) -> None:
    """Default settings and rules (safe values)."""
    from app.models import Setting

    if db.get(Setting, "persona") is None:
        save(db, Persona(ai_name="Demo Creator", age=27, location="Lisbon, Portugal", timezone="Europe/Lisbon",
                         occupation="photographer and content creator",
                         traits="curious, warm, a bit sarcastic, loves travel",
                         bio="Shoots travel and lifestyle content, spends weekends hiking and trying new cafes.",
                         behaviours=["Mentions her own day", "Remembers details fans share"], tone="flirty",
                         examples=["haha stop, you're making me blush", "ok but tell me more about that"]))
    for doc in (EngineSettings, ReengageSettings, SafetySettings):
        if db.get(Setting, {EngineSettings: "engine", ReengageSettings: "reengage",
                            SafetySettings: "safety"}[doc]) is None:
            save(db, load(db, doc))
    if db.scalar(select(CustomRule).limit(1)) is None:
        for i, r in enumerate(rules_svc.DEFAULT_RULES):
            db.add(CustomRule(name=r["name"], action=r["action"], conditions=r["conditions"], note=r["note"],
                              enabled=False, position=i))
    db.flush()


def simulate_inbound(db: Session, fan_uuid: str, text: str, tip_cents: int | None = None) -> str:
    return MockFanvueClient(db).add_fan_message(fan_uuid, text, tip_cents=tip_cents).uuid
