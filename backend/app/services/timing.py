"""Human-like timing: pacing windows, away delay, quiet hours."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

PACING: dict[str, tuple[int, int, int]] = {
    # (usual_min_s, usual_max_s, occasional_max_s)
    "fast": (5, 45, 45),
    "natural": (15, 180, 300),
    "relaxed": (60, 420, 600),
}


def pacing_delay(pacing: str, override_min: int | None = None, factor: float = 1.0,
                 rng: random.Random | None = None) -> float:
    r = rng or random
    if override_min:
        target = min(override_min, 30) * 60
        base = r.uniform(target * 0.7, target * 1.3)
    else:
        lo, hi, occ = PACING.get(pacing, PACING["natural"])
        base = r.uniform(hi, occ) if r.random() < 0.1 else r.uniform(lo, hi)
    return max(1.0, base * factor)


def away_delay(prev_inbound: datetime | None, now: datetime, after_min: int, wait_min: int, wait_max: int,
               rng: random.Random | None = None) -> float:
    """Seconds to wait because the fan returned after being idle (simulates 'she just noticed')."""
    if prev_inbound is None or now - prev_inbound < timedelta(minutes=after_min):
        return 0.0
    r = rng or random
    return r.uniform(wait_min * 60, max(wait_min, wait_max) * 60)


def _local(dt_utc: datetime, tz: str) -> datetime:
    return dt_utc.replace(tzinfo=UTC).astimezone(ZoneInfo(tz))


def in_window(dt_utc: datetime, tz: str, start_hour: int, end_hour: int) -> bool:
    """True if local hour is inside [start, end). Handles windows crossing midnight. start==end -> never."""
    h = _local(dt_utc, tz).hour
    if start_hour == end_hour:
        return False
    if start_hour < end_hour:
        return start_hour <= h < end_hour
    return h >= start_hour or h < end_hour


def next_window_end(dt_utc: datetime, tz: str, end_hour: int) -> datetime:
    loc = _local(dt_utc, tz)
    end = loc.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    if end <= loc:
        end += timedelta(days=1)
    return end.astimezone(UTC).replace(tzinfo=None)


def apply_quiet_hours(send_at: datetime, enabled: bool, tz: str, q_from: int, q_to: int,
                      rng: random.Random | None = None) -> datetime:
    if not enabled or not in_window(send_at, tz, q_from, q_to):
        return send_at
    r = rng or random
    return next_window_end(send_at, tz, q_to) + timedelta(seconds=r.uniform(0, 30 * 60))


def local_now_str(tz: str, now: datetime) -> str:
    return _local(now, tz).strftime("%A %H:%M")
