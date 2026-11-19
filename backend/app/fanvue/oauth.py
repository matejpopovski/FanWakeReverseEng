"""Fanvue OAuth 2.0 authorization-code + PKCE (S256) flow and token storage with rotation."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.fanvue.base import NeedsReconnect
from app.models import FanvueConnection, OAuthState
from app.security import decrypt, encrypt

STATE_TTL = timedelta(minutes=15)
_refresh_lock = threading.Lock()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def get_connection(db: Session) -> FanvueConnection:
    conn = db.get(FanvueConnection, 1)
    if conn is None:
        conn = FanvueConnection(id=1)
        db.add(conn)
        db.flush()
    return conn


def build_authorize_url(db: Session) -> str:
    s = get_settings()
    if not (s.fanvue_client_id and s.fanvue_client_secret):
        raise ValueError("FANVUE_CLIENT_ID / FANVUE_CLIENT_SECRET are not configured in .env")
    db.execute(delete(OAuthState).where(OAuthState.created_at < utcnow() - STATE_TTL))
    state = secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    db.add(OAuthState(state=state, code_verifier=verifier))
    db.flush()
    q = urlencode({
        "client_id": s.fanvue_client_id, "redirect_uri": s.fanvue_redirect_uri, "response_type": "code",
        "scope": s.fanvue_scopes, "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    return f"{s.fanvue_auth_base}/oauth2/auth?{q}"


def _token_request(data: dict[str, str], transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    s = get_settings()
    with httpx.Client(timeout=20.0, transport=transport) as c:
        resp = c.post(f"{s.fanvue_auth_base}/oauth2/token", data=data,
                      auth=(s.fanvue_client_id, s.fanvue_client_secret))  # client_secret_basic
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", "")
        except ValueError:
            err = ""
        if err == "invalid_grant":
            raise NeedsReconnect("Fanvue refresh/authorization grant is invalid; reconnect required", 400)
        raise ValueError(f"token endpoint returned {resp.status_code} {err}")
    return resp.json()


def _store_tokens(conn: FanvueConnection, tok: dict[str, Any]) -> None:
    conn.access_token_enc = encrypt(tok["access_token"])
    if tok.get("refresh_token"):
        conn.refresh_token_enc = encrypt(tok["refresh_token"])
    conn.expires_at = utcnow() + timedelta(seconds=int(tok.get("expires_in") or 3600))
    if tok.get("scope"):
        conn.scopes = tok["scope"]
    conn.needs_reconnect = False
    conn.status = "connected"
    conn.last_error = None


def exchange_code(db: Session, state: str, code: str, transport: httpx.BaseTransport | None = None) -> None:
    st = db.get(OAuthState, state)
    if st is None or st.created_at < utcnow() - STATE_TTL:
        raise ValueError("Invalid or expired OAuth state")
    verifier = st.code_verifier
    db.delete(st)
    tok = _token_request({"grant_type": "authorization_code", "code": code,
                          "redirect_uri": get_settings().fanvue_redirect_uri, "code_verifier": verifier},
                         transport)
    _store_tokens(get_connection(db), tok)
    db.flush()


def access_token(db: Session, transport: httpx.BaseTransport | None = None) -> str:
    conn = get_connection(db)
    if not conn.access_token_enc:
        raise NeedsReconnect("Fanvue is not connected")
    if conn.expires_at and conn.expires_at - timedelta(seconds=60) <= utcnow():
        return refresh(db, transport)
    return decrypt(conn.access_token_enc)


def refresh(db: Session, transport: httpx.BaseTransport | None = None) -> str:
    """Rotate the refresh token. Serialised so a single-use refresh token is never sent twice."""
    with _refresh_lock:
        conn = get_connection(db)
        db.refresh(conn)
        if conn.expires_at and conn.expires_at - timedelta(seconds=60) > utcnow() and conn.access_token_enc:
            return decrypt(conn.access_token_enc)  # someone else refreshed meanwhile
        if not conn.refresh_token_enc:
            conn.needs_reconnect = True
            db.commit()
            raise NeedsReconnect("No refresh token stored")
        try:
            tok = _token_request({"grant_type": "refresh_token",
                                  "refresh_token": decrypt(conn.refresh_token_enc)}, transport)
        except NeedsReconnect:
            conn.needs_reconnect = True
            conn.status = "error"
            conn.last_error = "Refresh token rejected; reconnect Fanvue"
            db.commit()
            raise
        _store_tokens(conn, tok)
        db.commit()  # persist the rotated refresh token immediately
        return tok["access_token"]


def disconnect(db: Session) -> None:
    conn = get_connection(db)
    conn.access_token_enc = conn.refresh_token_enc = None
    conn.expires_at = None
    conn.status = "disconnected"
    conn.needs_reconnect = False
    db.flush()
