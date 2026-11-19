"""Fanvue webhook signature verification (HMAC-SHA256 over "<t>.<raw body>")."""

from __future__ import annotations

import hashlib
import hmac
import time

TOLERANCE_SECONDS = 300


def sign(secret: str, timestamp: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, header: str | None, body: bytes, now: float | None = None) -> bool:
    """Header format: ``t=<unix>,v0=<hex>[,<hex>...]`` (multiple v0 values during secret rotation)."""
    if not secret or not header:
        return False
    ts: int | None = None
    sigs: list[str] = []
    current = None
    for part in header.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            current = k
            if k == "t":
                try:
                    ts = int(v)
                except ValueError:
                    return False
            elif k == "v0":
                sigs.append(v)
        elif current == "v0" and part:
            sigs.append(part)
    if ts is None or not sigs:
        return False
    if abs((now if now is not None else time.time()) - ts) > TOLERANCE_SECONDS:
        return False
    expected = sign(secret, ts, body)
    return any(hmac.compare_digest(expected, s) for s in sigs)
