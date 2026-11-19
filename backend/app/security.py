"""Operator authentication, session cookies and token encryption."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from app.config import get_settings

SESSION_COOKIE = "wakeful_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "wakeful"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str) -> bool:
    s = get_settings()
    if s.admin_password_hash:
        try:
            return bcrypt.checkpw(password.encode(), s.admin_password_hash.encode())
        except ValueError:
            return False
    if s.admin_password:
        return hmac.compare_digest(password.encode(), s.admin_password.encode())
    return False


def _signer() -> TimestampSigner:
    return TimestampSigner(get_settings().secret_key, salt="wakeful-session")


def issue_session() -> str:
    return _signer().sign(secrets.token_urlsafe(16)).decode()


def check_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        _signer().unsign(token, max_age=SESSION_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


def require_operator(request: Request) -> None:
    """FastAPI dependency: valid session + CSRF header on unsafe methods."""
    if not check_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF header")


@lru_cache
def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        # Derive a stable dev key from SECRET_KEY so tokens survive restarts in dev.
        digest = hashlib.sha256(("fernet:" + get_settings().secret_key).encode()).digest()
        key = base64.urlsafe_b64encode(digest).decode()
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotated
        raise ValueError("Cannot decrypt stored token (encryption key changed?)") from exc
