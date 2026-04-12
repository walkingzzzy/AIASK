from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import pytest

from akshare_mcp.storage.timescaledb.signal_tracking import SignalTrackingMixin


class _FakeConn:
    def __init__(self):
        self.last_fetch_query = None
        self.last_fetch_params = None
        self.last_fetchrow_query = None
        self.last_fetchrow_params = None

    async def fetchrow(self, query, *params):
        self.last_fetchrow_query = query
        self.last_fetchrow_params = params
        if "COUNT(*) AS total_signals" in query:
            return {"total_signals": 12, "latest_signal_date": date(2026, 4, 2)}
        return None

    async def fetch(self, query, *params):
        self.last_fetch_query = query
        self.last_fetch_params = params
        if "JOIN signal_forward_returns" in query:
            return [
                {"signal_id": 101, "signal_date": date(2026, 4, 2), "signal": 1, "forward_days": 1, "actual_return": 0.03},
                {"signal_id": 101, "signal_date": date(2026, 4, 2), "signal": 1, "forward_days": 5, "actual_return": 0.07},
                {"signal_id": 102, "signal_date": date(2026, 4, 1), "signal": -1, "forward_days": 1, "actual_return": -0.02},
            ]
        return [
            {
                "id": 1,
                "strategy_id": "sid",
                "signal_date": date(2026, 4, 1),
                "code": "600519",
                "signal": 1,
            }
        ]


class _FakeDB(SignalTrackingMixin):
    def __init__(self):
        self._conn = _FakeConn()

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


@pytest.mark.asyncio
async def test_get_signal_stats_separates_raw_signal_count_from_forward_return_coverage():
    db = _FakeDB()

    stats = await db.get_signal_stats("sid")

    assert stats["total_signals"] == 12
    assert stats["raw_signal_count"] == 12
    assert stats["signals_with_forward_returns_count"] == 2
    assert stats["observed_forward_return_count"] == 3
    assert stats["hit_rate"][1] == 1.0
    assert stats["hit_rate"][5] == 1.0
    assert stats["sample_count"][1] == 2
    assert stats["effective_n"][5] == 1
    assert stats["hit_rate_lcb"][1] < stats["hit_rate"][1]
    assert stats["skill_lcb"][1] < stats["hit_rate_lcb"][1]
    assert stats["recent_hit_rate"][1] == 1.0
    assert stats["hit_rate_lcb_method"] == "wilson_ess_approx"
    assert stats["effective_n_method"] == "overlap_adjusted_ess_v1"


@pytest.mark.asyncio
async def test_get_pending_forward_returns_uses_explicit_limit():
    db = _FakeDB()

    await db.get_pending_forward_returns(5, limit=1234)

    assert "LIMIT $5" in db._conn.last_fetch_query
    assert db._conn.last_fetch_params[1] == 5
    assert db._conn.last_fetch_params[4] == 1234
