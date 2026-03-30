from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from akshare_mcp.core.validators import validate_kline, validate_kline_list
from akshare_mcp.storage.timescaledb.kline import KlineMixin


class _Conn:
    def __init__(self):
        self.rows = None

    async def executemany(self, _query, rows):
        self.rows = list(rows)


class _KlineDb(KlineMixin):
    def __init__(self):
        self.conn = _Conn()

    @asynccontextmanager
    async def acquire(self):
        yield self.conn


def test_validate_kline_rejects_inconsistent_ohlc() -> None:
    with pytest.raises(ValueError, match="最高价不能低于开盘价、收盘价或最低价"):
        validate_kline(
            {
                "date": "2026-03-01",
                "code": "600519",
                "open": 10.0,
                "close": 11.0,
                "high": 9.5,
                "low": 9.0,
                "volume": 1000,
            }
        )


def test_validate_kline_list_skips_invalid_rows() -> None:
    rows = validate_kline_list(
        [
            {
                "date": "2026-03-01",
                "code": "600519",
                "open": 10.0,
                "close": 11.0,
                "high": 9.5,
                "low": 9.0,
                "volume": 1000,
            },
            {
                "date": "2026-03-02",
                "code": "600519",
                "open": 10.0,
                "close": 11.0,
                "high": 12.0,
                "low": 9.0,
                "volume": 1000,
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-03-02"


@pytest.mark.asyncio
async def test_save_klines_skips_invalid_rows_before_persisting() -> None:
    db = _KlineDb()

    saved = await db.save_klines(
        "600519",
        [
            {
                "date": "2026-03-01",
                "open": 10.0,
                "close": 11.0,
                "high": 9.5,
                "low": 9.0,
                "volume": 1000,
            },
            {
                "date": "2026-03-02",
                "open": 10.0,
                "close": 11.0,
                "high": 12.0,
                "low": 9.0,
                "volume": 1000,
            },
        ],
    )

    assert saved == 1
    assert db.conn.rows is not None
    assert len(db.conn.rows) == 1
    assert db.conn.rows[0][1] == "600519"
