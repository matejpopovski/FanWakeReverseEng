from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.update({
    "APP_ENV": "test", "ADMIN_PASSWORD": "test-password", "ADMIN_PASSWORD_HASH": "", "FANVUE_MODE": "mock",
    "AI_PROVIDER": "mock", "SECRET_KEY": "test-secret", "WORKER_ENABLED": "false",
    "FANVUE_WEBHOOK_SECRET": "whsec_test", "FANVUE_CLIENT_ID": "cid", "FANVUE_CLIENT_SECRET": "csecret",
})

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import db as dbmod  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.migrate import upgrade  # noqa: E402


@pytest.fixture()
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture()
def db(db_url: str) -> Iterator[Session]:
    get_settings.cache_clear()
    os.environ["DATABASE_URL"] = db_url
    os.environ["FANVUE_MODE"] = "mock"
    get_settings.cache_clear()
    upgrade(db_url)
    dbmod.init_engine(db_url)
    s = dbmod.SessionLocal()
    try:
        yield s
    finally:
        s.close()
        dbmod.get_engine().dispose()


@pytest.fixture()
def seeded(db: Session) -> Session:
    from app.seed import seed_defaults, seed_mock
    from app.services import sync

    seed_defaults(db)
    seed_mock(db, fans=12)
    db.commit()
    sync.sync(db)
    return db


@pytest.fixture()
def client(seeded: Session) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as c:
        r = c.post("/api/auth/login", json={"password": "test-password"})
        assert r.status_code == 200
        c.headers.update({"X-Requested-With": "wakeful"})
        yield c


def enable_engine(db: Session, **kw: object) -> None:
    from app.settings_store import EngineSettings, load, save

    e = load(db, EngineSettings)
    e.enabled = True
    for k, v in kw.items():
        setattr(e, k, v)
    save(db, e)
    db.commit()
