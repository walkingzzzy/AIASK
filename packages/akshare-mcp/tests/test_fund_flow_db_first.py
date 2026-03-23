from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from akshare_mcp.core.cache_manager import clear_cache
from akshare_mcp.storage.timescaledb.strategy_crud import StrategyCrudMixin
from akshare_mcp.tools import fund_flow as flow_mod
from akshare_mcp.tools import fund_flow_market as market_mod
from akshare_mcp.tools import fund_flow_north as north_mod


class _ConnWrapper:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, *args):
        normalized = " ".join(str(query).split())
        if "FROM margin_market_flow" in normalized:
            return list(self._rows.get("market", []))
        if "FROM margin_detail" in normalized and "GROUP BY trade_date" in normalized:
            return list(self._rows.get("detail_agg", []))
        if "FROM margin_detail" in normalized and "ts_code = $2" in normalized:
            ts_code = args[1]
            return [row for row in self._rows.get("detail", []) if row.get("ts_code") == ts_code]
        if "FROM margin_detail" in normalized and "WHERE trade_date = $1" in normalized:
            target_date = args[0]
            rows = [row for row in self._rows.get("detail", []) if row.get("trade_date") == target_date]
            if "ORDER BY rzmre DESC" in normalized:
                rows = sorted(rows, key=lambda row: (float(row.get("rzmre") or 0.0), str(row.get("ts_code") or "")), reverse=True)
            elif "ORDER BY rqmcl DESC" in normalized:
                rows = sorted(rows, key=lambda row: (float(row.get("rqmcl") or 0.0), str(row.get("ts_code") or "")), reverse=True)
            else:
                rows = sorted(rows, key=lambda row: (float(row.get("rzrqye") or 0.0), str(row.get("ts_code") or "")), reverse=True)
            return rows
        if "FROM margin_detail" in normalized:
            return list(self._rows.get("detail", []))
        raise AssertionError(f"unexpected query: {normalized}")

    async def fetchval(self, query, *args):
        normalized = " ".join(str(query).split())
        if "SELECT MAX(trade_date) FROM margin_detail" in normalized:
            end_date = args[0]
            values = [row.get("trade_date") for row in self._rows.get("detail", []) if row.get("trade_date") and row.get("trade_date") <= end_date]
            return max(values) if values else None
        raise AssertionError(f"unexpected fetchval query: {normalized}")


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FundFlowDb(StrategyCrudMixin):
    def __init__(self, rows):
        self._conn = _ConnWrapper(rows)

    def acquire(self):
        return _AcquireCtx(self._conn)


@pytest.mark.asyncio
async def test_get_margin_market_history_uses_market_table_rows():
    db = _FundFlowDb(
        {
            "market": [
                {
                    "trade_date": date(2026, 3, 20),
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
                    "trade_date": date(2026, 3, 20),
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
                    "trade_date": date(2026, 3, 19),
                    "exchange_id": "SSE",
                    "rzye": 120.0,
                    "rzmre": 18.0,
                    "rzche": 9.0,
                    "rqye": 4.0,
                    "rqmcl": 0.8,
                    "rqyl": 1.5,
                    "rzrqye": 124.0,
                },
            ],
            "detail_agg": [],
            "detail": [],
        }
    )

    rows = await db.get_margin_market_history(days=2, end_date="2026-03-22")

    assert len(rows) == 2
    assert rows[0]["source"] == "margin_market_flow"
    assert rows[0]["marginBalance"] == 140.0
    assert rows[0]["marginBuy"] == 28.0


@pytest.mark.asyncio
async def test_get_margin_detail_latest_filters_ts_code():
    db = _FundFlowDb(
        {
            "market": [],
            "detail_agg": [],
            "detail": [
                {
                    "trade_date": date(2026, 3, 20),
                    "ts_code": "600519.SH",
                    "rzye": 120.0,
                    "rqye": 4.0,
                    "rzmre": 18.0,
                    "rqyl": 2.0,
                    "rzche": 8.0,
                    "rqchl": 1.0,
                    "rqmcl": 1.2,
                    "rzrqye": 124.0,
                },
                {
                    "trade_date": date(2026, 3, 20),
                    "ts_code": "000001.SZ",
                    "rzye": 90.0,
                    "rqye": 3.0,
                    "rzmre": 10.0,
                    "rqyl": 1.0,
                    "rzche": 5.0,
                    "rqchl": 0.5,
                    "rqmcl": 0.8,
                    "rzrqye": 93.0,
                },
            ],
        }
    )

    rows = await db.get_margin_detail_latest(limit=10, ts_code="600519", end_date="2026-03-22")

    assert len(rows) == 1
    assert rows[0]["ts_code"] == "600519.SH"
    assert rows[0]["code"] == "600519"
    assert rows[0]["source"] == "margin_detail"


@pytest.mark.asyncio
async def test_get_margin_ranking_uses_latest_trade_date_and_sorts():
    db = _FundFlowDb(
        {
            "market": [],
            "detail_agg": [],
            "detail": [
                {
                    "trade_date": date(2026, 3, 20),
                    "ts_code": "600519.SH",
                    "rzye": 120.0,
                    "rqye": 4.0,
                    "rzmre": 18.0,
                    "rqyl": 2.0,
                    "rzche": 8.0,
                    "rqchl": 1.0,
                    "rqmcl": 1.2,
                    "rzrqye": 124.0,
                },
                {
                    "trade_date": date(2026, 3, 20),
                    "ts_code": "000001.SZ",
                    "rzye": 90.0,
                    "rqye": 3.0,
                    "rzmre": 25.0,
                    "rqyl": 1.0,
                    "rzche": 5.0,
                    "rqchl": 0.5,
                    "rqmcl": 0.8,
                    "rzrqye": 93.0,
                },
                {
                    "trade_date": date(2026, 3, 19),
                    "ts_code": "300750.SZ",
                    "rzye": 300.0,
                    "rqye": 2.0,
                    "rzmre": 100.0,
                    "rqyl": 1.0,
                    "rzche": 20.0,
                    "rqchl": 0.5,
                    "rqmcl": 0.6,
                    "rzrqye": 302.0,
                },
            ],
        }
    )

    rows = await db.get_margin_ranking(top_n=2, sort_by="buy", end_date="2026-03-22")

    assert len(rows) == 2
    assert rows[0]["trade_date"] == date(2026, 3, 20)
    assert rows[0]["code"] == "000001"
    assert rows[0]["source"] == "margin_detail_ranking"


def test_get_north_fund_prefers_db_source(monkeypatch):
    clear_cache()
    today = north_mod.date.today()
    monkeypatch.setattr(
        north_mod,
        "_north_fund_from_db",
        lambda days: [
            {
                "date": (today).strftime("%Y-%m-%d"),
                "shConnect": 100.0,
                "szConnect": 120.0,
                "total": 220.0,
                "shCumulative": 100.0,
                "szCumulative": 120.0,
                "cumulative": 220.0,
            },
            {
                "date": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
                "shConnect": 90.0,
                "szConnect": 110.0,
                "total": 200.0,
                "shCumulative": 190.0,
                "szCumulative": 230.0,
                "cumulative": 420.0,
            },
        ],
    )
    monkeypatch.setattr(north_mod, "_north_fund_from_tushare", lambda days: (_ for _ in ()).throw(AssertionError("tushare should not run")))
    monkeypatch.setattr(north_mod, "_north_fund_from_hkex", lambda days: (_ for _ in ()).throw(AssertionError("hkex should not run")))
    monkeypatch.setattr(north_mod, "_north_fund_from_akshare", lambda days: (_ for _ in ()).throw(AssertionError("akshare should not run")))
    monkeypatch.setattr(north_mod, "_north_fund_from_em_summary", lambda days: (_ for _ in ()).throw(AssertionError("em_summary should not run")))

    result = north_mod.get_north_fund(2)

    assert result["success"] is True
    assert result["data"]["source"] == "north_fund_flow"
    assert len(result["data"]["items"]) == 2
    clear_cache()


def test_get_margin_data_prefers_db_rows(monkeypatch):
    monkeypatch.setattr(
        market_mod,
        "_margin_rows_from_db",
        lambda stock_code="", days=30: [
            {
                "date": "2026-03-20",
                "code": "600519" if stock_code else "",
                "name": "贵州茅台" if stock_code else "",
                "marginBalance": 120.0,
                "marginBuy": 18.0,
                "marginRepay": 8.0,
                "shortBalance": 4.0,
                "shortSell": 1.2,
                "shortRepay": 1.0,
                "totalBalance": 124.0,
                "source": "margin_detail" if stock_code else "margin_market_flow",
            }
        ],
    )
    monkeypatch.setattr(market_mod, "_fetch_eastmoney_datacenter", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("eastmoney should not run")))
    if market_mod.ak is not None:
        monkeypatch.setattr(market_mod.ak, "stock_margin_account_info", lambda: (_ for _ in ()).throw(AssertionError("akshare summary should not run")))
        monkeypatch.setattr(market_mod.ak, "stock_margin_sse", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("akshare sse should not run")))

    market_result = market_mod.get_margin_data(days=3)
    stock_result = market_mod.get_margin_data(stock_code="600519", days=3)

    assert market_result["success"] is True
    assert market_result["data"][0]["source"] == "margin_market_flow"
    assert stock_result["success"] is True
    assert stock_result["data"][0]["source"] == "margin_detail"
    assert stock_result["data"][0]["code"] == "600519"


def test_get_margin_ranking_prefers_db_rows(monkeypatch):
    monkeypatch.setattr(
        market_mod,
        "_margin_ranking_from_db",
        lambda top_n=20, sort_by="balance": [
            {
                "date": "2026-03-20",
                "code": "600519",
                "name": "贵州茅台",
                "marginBalance": 120.0,
                "marginBuy": 18.0,
                "shortSell": 1.2,
                "totalBalance": 124.0,
                "source": "margin_detail_ranking",
            }
        ],
    )
    monkeypatch.setattr(market_mod, "_fetch_eastmoney_datacenter", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("eastmoney should not run")))

    result = market_mod.get_margin_ranking(top_n=5, sort_by="buy")

    assert result["success"] is True
    assert result["data"][0]["source"] == "margin_detail_ranking"
    assert result["data"][0]["code"] == "600519"


def test_get_stock_fund_flow_prefers_db_snapshot(monkeypatch):
    monkeypatch.setattr(flow_mod, "_run_storage_call_sync", lambda callback, timeout=8.0: ({"code": "600519", "mainNetInflow": 123.4, "source": "stock_fund_flow"}, ["db.stock_fund_flow"]))
    monkeypatch.setattr(flow_mod, "_get_stock_fund_flow_from_tushare", lambda code: (_ for _ in ()).throw(AssertionError("tushare should not run")))
    monkeypatch.setattr(flow_mod.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("eastmoney should not run")))

    result = flow_mod.get_stock_fund_flow("600519")

    assert result["success"] is True
    assert result["data"]["source"] == "stock_fund_flow"
    assert result["data"]["mainNetInflow"] == 123.4


def test_get_stock_fund_flow_falls_back_to_tushare_moneyflow(monkeypatch):
    monkeypatch.setattr(flow_mod, "_run_storage_call_sync", lambda callback, timeout=8.0: ({}, []))

    class _FakePro:
        @staticmethod
        def moneyflow(**kwargs):
            assert kwargs["ts_code"] == "600519.SH"
            return pd.DataFrame(
                [
                    {
                        "trade_date": "20260320",
                        "buy_sm_amount": 10.0,
                        "sell_sm_amount": 14.0,
                        "buy_md_amount": 30.0,
                        "sell_md_amount": 25.0,
                        "buy_lg_amount": 80.0,
                        "sell_lg_amount": 50.0,
                        "buy_elg_amount": 120.0,
                        "sell_elg_amount": 100.0,
                    }
                ]
            )

    monkeypatch.setattr(flow_mod.data_source, "get_tushare_pro", lambda: _FakePro())
    monkeypatch.setattr(flow_mod.requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("eastmoney should not run")))

    result = flow_mod.get_stock_fund_flow("600519", prefer_db=False)

    assert result["success"] is True
    assert result["data"]["source"] == "tushare.moneyflow"
    assert result["data"]["tradeDate"] == "2026-03-20"
    assert result["data"]["superLargeNetInflow"] == 20.0
    assert result["data"]["largeNetInflow"] == 30.0
    assert result["data"]["middleNetInflow"] == 5.0
    assert result["data"]["smallNetInflow"] == -4.0
    assert result["data"]["mainNetInflow"] == 50.0
