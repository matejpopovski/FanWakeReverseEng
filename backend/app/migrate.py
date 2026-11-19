"""Run Alembic migrations programmatically (used at startup and in tests)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command

BACKEND = Path(__file__).resolve().parents[1]


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    if url:
        cfg.attributes["url"] = url
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)
