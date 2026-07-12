"""A-share matching pure rules (no DB / no asyncio loop).

Host MatchingEngine should re-export these for limit ratio + session checks
so policy does not drift across packages.
"""

from __future__ import annotations

from datetime import datetime, time


MORNING_OPEN = time(9, 30)
MORNING_CLOSE = time(11, 30)
AFTERNOON_OPEN = time(13, 0)
AFTERNOON_CLOSE = time(15, 0)
SCAN_INTERVAL_SECONDS = 30


def is_trading_time(now: datetime) -> bool:
    """Whether *now* falls in A-share continuous auction sessions (weekdays)."""
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (MORNING_OPEN <= t <= MORNING_CLOSE) or (AFTERNOON_OPEN <= t <= AFTERNOON_CLOSE)


def get_limit_ratio(code: str) -> float:
    """Price-limit ratio: ChiNext/STAR 20%, otherwise 10%."""
    c = str(code).strip()
    for prefix in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if c.startswith(prefix):
            c = c[len(prefix) :]
            break
    if c.startswith("300") or c.startswith("301") or c.startswith("688"):
        return 0.20
    return 0.10


__all__ = [
    "AFTERNOON_CLOSE",
    "AFTERNOON_OPEN",
    "MORNING_CLOSE",
    "MORNING_OPEN",
    "SCAN_INTERVAL_SECONDS",
    "get_limit_ratio",
    "is_trading_time",
]
