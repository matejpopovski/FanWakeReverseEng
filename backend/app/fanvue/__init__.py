"""Fanvue integration: factory selecting the mock or live client."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.fanvue.base import FanvueClient
from app.fanvue.mock import MockFanvueClient


def get_client(db: Session) -> FanvueClient:
    if get_settings().fanvue_mode == "live":
        from app.fanvue import oauth
        from app.fanvue.live import LiveFanvueClient

        return LiveFanvueClient(token_provider=lambda: oauth.access_token(db),
                                on_unauthorized=lambda: oauth.refresh(db))
    return MockFanvueClient(db)
