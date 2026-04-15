from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from akshare_mcp.storage.timescaledb.kline import KlineMixin


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.last_query = None
        self.last_params = None

    async def fetch(self, query, *params):
        self.last_query = query
        self.last_params = params
        return self.rows


class _FakeDB(KlineMixin):
    def __init__(self, rows):
        self._conn = _FakeConn(rows)

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


@pytest.mark.asyncio
async def test_get_klines_limit_returns_latest_rows_but_keeps_ascending_order():
    rows = [
        {
            "time": datetime(2026, 3, 19, tzinfo=timezone.utc),
            "code": "600519",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "amount": 100500.0,
            "turnover": 1.2,
            "change_pct": 0.5,
        },
        {
            "time": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "code": "600519",
            "open": 101.0,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1200,
            "amount": 121800.0,
            "turnover": 1.4,
            "change_pct": 1.0,
        },
    ]
    db = _FakeDB(rows)

    data = await db.get_klines("600519", limit=2)

    assert "ORDER BY time DESC" in db._conn.last_query
    assert "ORDER BY time ASC" in db._conn.last_query
    assert [row["date"] for row in data] == ["2026-03-19", "2026-03-20"]


@pytest.mark.asyncio
async def test_get_klines_uses_inclusive_date_bounds_in_market_timezone():
    rows = [
        {
            "time": datetime(2026, 4, 13, 7, 0, tzinfo=timezone.utc),
            "code": "600519",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "amount": 100500.0,
            "turnover": 1.2,
            "change_pct": 0.5,
        },
    ]
    db = _FakeDB(rows)

    data = await db.get_klines("600519", start_date="2026-04-13", end_date="2026-04-13")

    assert "time >=" in db._conn.last_query
    assert "time <" in db._conn.last_query
    assert db._conn.last_params[1].strftime("%Y-%m-%d %H:%M:%S%z") == "2026-04-13 00:00:00+0800"
    assert db._conn.last_params[2].strftime("%Y-%m-%d %H:%M:%S%z") == "2026-04-14 00:00:00+0800"
    assert [row["date"] for row in data] == ["2026-04-13"]
