from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from akshare_mcp.storage.timescaledb.strategy_crud import StrategyCrudMixin
from akshare_mcp.tools import sentiment as sentiment_mod


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _FakeDb:
    def __init__(self):
        self.get_klines = AsyncMock(
            return_value=[
                {"date": f"2026-03-{idx + 1:02d}", "close": float(3000 + idx), "volume": 1000 + idx}
                for idx in range(60)
            ]
        )
        self.get_limit_up_stats = AsyncMock(
            return_value={"advance_count": 3200, "decline_count": 1800, "limit_up_count": 80, "limit_down_count": 10}
        )
        self.get_recent_north_fund_summary = AsyncMock(
            return_value={
                "sample_count": 5,
                "total_net": 123.45,
                "source": "north_fund_flow",
                "stale": False,
                "stale_age_days": 2,
                "latest_trade_date": "2026-03-20",
                "series": [
                    {"trade_date": "2026-03-20", "north_money": 50.0},
                    {"trade_date": "2026-03-19", "north_money": 40.0},
                    {"trade_date": "2026-03-18", "north_money": 33.45},
                    {"trade_date": "2026-03-17", "north_money": 20.0},
                    {"trade_date": "2026-03-16", "north_money": 10.0},
                ],
            }
        )
        self.get_recent_margin_summary = AsyncMock(
            return_value={
                "sample_count": 6,
                "margin_balance_latest": 1000.0,
                "margin_buy_latest": 200.0,
                "margin_balance_change_5d": 6.78,
                "recent_rows": [{"trade_date": "2026-03-20", "marginBalance": 1000.0}],
                "source": "margin_market_flow",
                "stale": False,
                "stale_age_days": 2,
                "latest_trade_date": "2026-03-20",
            }
        )


class _ConnWrapper:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "FROM margin_market_flow" in normalized:
            return list(self._rows.get("market", []))
        if "FROM margin_detail" in normalized:
            return list(self._rows.get("detail", []))
        raise AssertionError(f"unexpected query: {normalized}")


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _MarginSummaryDb(StrategyCrudMixin):
    def __init__(self, rows):
        self._conn = _ConnWrapper(rows)

    def acquire(self):
        return _AcquireCtx(self._conn)


@pytest.mark.asyncio
async def test_get_market_sentiment_context_prefers_db_summaries(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(sentiment_mod, "get_db", lambda: db)
    monkeypatch.setattr(
        sentiment_mod.sentiment_analyzer,
        "calculate_fear_greed_index",
        lambda index_klines=None, breadth_data=None: {
            "index": 61,
            "level": "greed",
            "components": {"breadth": 0.66},
        },
    )

    from akshare_mcp.tools import fund_flow as fund_flow_mod

    monkeypatch.setattr(fund_flow_mod, "get_north_fund", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("north fallback should not run")))
    monkeypatch.setattr(fund_flow_mod, "get_margin_data", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("margin fallback should not run")))
    monkeypatch.setattr(
        fund_flow_mod,
        "get_sector_fund_flow",
        lambda top_n=10: {
            "success": True,
            "data": [
                {"name": "半导体", "mainNetInflow": 30.0},
                {"name": "消费", "mainNetInflow": 10.0},
                {"name": "煤炭", "mainNetInflow": -8.0},
            ],
        },
    )

    mcp = _DummyMCP()
    sentiment_mod.register(mcp)
    result = await mcp.get_market_sentiment_context()

    assert result["success"] is True
    data = result["data"]
    assert data["northbound_flow_3d"] == 123.45
    assert data["northbound_context"]["source"] == "north_fund_flow"
    assert data["margin_balance_change_5d"] == 6.78
    assert data["margin_context"]["source"] == "margin_market_flow"
    assert data["source_chain"][1] == "db.get_recent_north_fund_summary"
    assert data["source_chain"][2] == "db.get_recent_margin_summary"


@pytest.mark.asyncio
async def test_get_recent_margin_summary_uses_market_table_rows():
    db = _MarginSummaryDb(
        {
            "market": [
                {
                    "trade_date": sentiment_mod.date(2026, 3, 20),
                    "exchange_id": "SSE",
                    "rzye": 100.0,
                    "rzmre": 20.0,
                    "rzche": 10.0,
                    "rqye": 5.0,
                    "rqmcl": 1.0,
                    "rqyl": 2.0,
                    "rzrqye": 105.0,
                },
                {
                    "trade_date": sentiment_mod.date(2026, 3, 20),
                    "exchange_id": "SZSE",
                    "rzye": 40.0,
                    "rzmre": 8.0,
                    "rzche": 4.0,
                    "rqye": 2.0,
                    "rqmcl": 0.5,
                    "rqyl": 1.0,
                    "rzrqye": 42.0,
                },
                {
                    "trade_date": sentiment_mod.date(2026, 3, 13),
                    "exchange_id": "SSE",
                    "rzye": 100.0,
                    "rzmre": 15.0,
                    "rzche": 8.0,
                    "rqye": 3.0,
                    "rqmcl": 0.2,
                    "rqyl": 0.8,
                    "rzrqye": 103.0,
                },
            ],
            "detail": [],
        }
    )

    result = await db.get_recent_margin_summary(days=10, sample_limit=10, change_lookback_days=1)

    assert result is not None
    assert result["source"] == "margin_market_flow"
    assert result["margin_balance_latest"] == 140.0
    assert result["margin_buy_latest"] == 28.0
    assert result["margin_balance_change_5d"] == 40.0


@pytest.mark.asyncio
async def test_get_recent_margin_summary_falls_back_to_detail_aggregate():
    db = _MarginSummaryDb(
        {
            "market": [],
            "detail": [
                {
                    "trade_date": sentiment_mod.date(2026, 3, 20),
                    "rzye": 120.0,
                    "rzmre": 18.0,
                    "rzche": 8.0,
                    "rqye": 4.0,
                    "rqmcl": 1.0,
                    "rqyl": 2.0,
                    "rzrqye": 124.0,
                },
                {
                    "trade_date": sentiment_mod.date(2026, 3, 13),
                    "rzye": 100.0,
                    "rzmre": 12.0,
                    "rzche": 7.0,
                    "rqye": 3.0,
                    "rqmcl": 0.5,
                    "rqyl": 1.0,
                    "rzrqye": 103.0,
                },
            ],
        }
    )

    result = await db.get_recent_margin_summary(days=10, sample_limit=10, change_lookback_days=1)

    assert result is not None
    assert result["source"] == "margin_detail_aggregate"
    assert result["margin_balance_latest"] == 120.0
    assert result["margin_balance_change_5d"] == 20.0
