from __future__ import annotations

import sys
from datetime import date

import akshare
import pandas as pd
import pytest

import akshare_mcp.storage as storage_mod
import akshare_mcp.tools.data_sync as data_sync_mod
import akshare_mcp.tools.finance as finance_mod
import akshare_mcp.tools.fund_flow_north as north_mod
import akshare_mcp.tools.market.kline as kline_mod
import akshare_mcp.tools.market_blocks as market_blocks_mod
import akshare_mcp.tools.news.research as research_mod
import akshare_mcp.tools.valuation as valuation_mod
import akshare_mcp.tools.vector as vector_mod
from akshare_mcp.storage.timescaledb.financials import FinancialsMixin


class _DummyMCP:
    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


class _DummyLimiter:
    def acquire(self):
        return None


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FinanceDB:
    def __init__(self, rows):
        self._rows = rows

    async def get_financials(self, code, limit=4):
        return list(self._rows)


def test_get_cache_stats_returns_success_envelope(monkeypatch):
    mcp = _DummyMCP()
    data_sync_mod.register(mcp)

    monkeypatch.setattr(
        data_sync_mod.cache,
        "get_stats",
        lambda: {
            "file_count": 3,
            "total_size_mb": 1.25,
            "hit_rate": 0.9,
            "cache_dir": "/tmp/cache",
        },
    )
    monkeypatch.setattr(data_sync_mod, "CACHE_TTL", {"quote": 60})

    result = mcp.get_cache_stats()

    assert result["success"] is True
    assert result["error"] is None
    assert result["data"]["file_count"] == 3
    assert result["data"]["ttl_config"] == {"quote": 60}
    assert result["file_count"] == 3


def test_kline_quality_meta_uses_latest_row_for_asof_and_missing_fields():
    rows = [
        {
            "date": "2026-03-17",
            "open": 10.0,
            "close": 10.5,
            "high": 10.8,
            "low": 9.9,
            "volume": 1000,
            "amount": 2000.0,
            "turnover": None,
            "change_pct": None,
            "source": "timescaledb",
        },
        {
            "date": "2026-03-11",
            "open": 9.8,
            "close": 10.0,
            "high": 10.1,
            "low": 9.7,
            "volume": 900,
            "amount": 1800.0,
            "turnover": 1.2,
            "change_pct": 1.1,
            "source": "timescaledb",
        },
    ]

    result = kline_mod._ok_kline_response(rows, source_chain=["db.get_klines"])

    assert result["success"] is True
    assert result["asof_time"].startswith("2026-03-17")
    assert result["missing_fields"] == ["turnover", "change_pct"]


def test_get_north_fund_prefers_recent_partial_snapshot(monkeypatch):
    today = date.today().isoformat()

    monkeypatch.setattr(north_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(north_mod, "_NORTH_FUND_FAST_MODE", False)
    monkeypatch.setattr(north_mod, "_north_fund_from_db", lambda days: [])
    monkeypatch.setattr(north_mod, "_north_fund_from_tushare", lambda days: [])
    monkeypatch.setattr(north_mod, "_north_fund_from_hkex", lambda days: [])
    monkeypatch.setattr(
        north_mod,
        "_north_fund_from_akshare",
        lambda days: [
            {
                "date": "2024-09-27",
                "shConnect": 52_000_000_000.0,
                "szConnect": 52_000_000_000.0,
                "total": 104_000_000_000.0,
                "shCumulative": None,
                "szCumulative": None,
                "cumulative": None,
            }
        ],
    )
    monkeypatch.setattr(
        north_mod,
        "_north_fund_from_em_summary",
        lambda days: [
            {
                "date": today,
                "shConnect": 0.0,
                "szConnect": 0.0,
                "total": 0.0,
                "shCumulative": 0.0,
                "szCumulative": 0.0,
                "cumulative": 0.0,
            }
        ],
    )

    result = north_mod.get_north_fund.__wrapped__(10)

    assert result["success"] is True
    assert result["data"]["source"] == "em_summary_partial"
    assert result["data"]["partial"] is True
    assert result["data"]["stale"] is False
    assert result["data"]["items"][0]["date"] == today


def test_search_research_keyword_only_falls_back_to_candidate_stocks(monkeypatch):
    class _FakePro:
        def report_rc(self, **kwargs):
            return pd.DataFrame(columns=["ts_code", "report_title", "org_name", "author_name", "report_date", "rating"])

        def stock_basic(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "ts_code": "002594.SZ",
                        "symbol": "002594",
                        "name": "比亚迪",
                        "industry": "汽车整车",
                    }
                ]
            )

    monkeypatch.setattr(research_mod.data_source, "get_tushare_pro", lambda: _FakePro())
    monkeypatch.setattr(
        research_mod,
        "_fetch_eastmoney_research",
        lambda code, limit: [
            {
                "title": "比亚迪深度跟踪报告",
                "institution": "某券商",
                "rating": "买入",
                "date": "2026-03-18",
            }
        ]
        if code == "002594"
        else [],
    )

    result = research_mod.search_research.__wrapped__(keyword="新能源汽车", stock_code="", days=30)

    assert result["success"] is True
    assert result["data"]["total"] == 1
    assert result["data"]["reports"][0]["stockCode"] == "002594"
    assert result["data"]["reports"][0]["title"] == "比亚迪深度跟踪报告"


@pytest.mark.asyncio
async def test_semantic_stock_search_demotes_st_concept_noise(monkeypatch):
    class _Conn:
        async def fetch(self, query, *args):
            if "WHERE code = ANY($1::text[])" in query:
                return [
                    {"code": "600519", "market_cap": 100.0, "pe_ratio": 30.0, "pb_ratio": 8.0},
                    {"code": "600381", "market_cap": 5.0, "pe_ratio": 10.0, "pb_ratio": 1.2},
                ]
            return []

    class _DB:
        def acquire(self):
            return _Acquire(_Conn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

        def head(self, count):
            return _Frame(self._rows[:count])

    def _stock_sector_detail(sector):
        if sector == "new_whitewine":
            return _Frame(
                [
                    {"code": "600381", "name": "*ST春天"},
                    {"code": "600519", "name": "贵州茅台"},
                ]
            )
        return _Frame([])

    monkeypatch.setattr(vector_mod, "get_db", lambda: _DB())
    monkeypatch.setattr(
        akshare,
        "stock_sector_spot",
        lambda: _Frame([{"板块": "白酒概念", "label": "new_whitewine"}]),
        raising=False,
    )
    monkeypatch.setattr(akshare, "stock_board_industry_name_ths", lambda: _Frame([]), raising=False)
    monkeypatch.setattr(akshare, "stock_sector_detail", _stock_sector_detail, raising=False)
    monkeypatch.setitem(sys.modules, "akshare", akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query="白酒", limit=5)

    assert result["success"] is True
    codes = [item["code"] for item in result["data"]["results"]]
    assert codes[0] == "600519"
    if "600381" in codes:
        assert codes.index("600381") > 0


@pytest.mark.asyncio
async def test_semantic_stock_search_suppresses_concept_constituent_stdout(monkeypatch, capsys):
    class _Conn:
        async def fetch(self, query, *args):
            return []

    class _DB:
        def acquire(self):
            return _Acquire(_Conn())

    class _Frame:
        def __init__(self, rows):
            self._rows = rows
            self.empty = not rows

        def iterrows(self):
            for idx, row in enumerate(self._rows):
                yield idx, row

    def _noisy_concept_rows(block_code, block_name):
        print("concept constituent progress should not reach stdout")
        return [{"stock_code": "600519", "stock_name": "贵州茅台"}]

    monkeypatch.setattr(vector_mod, "get_db", lambda: _DB())
    monkeypatch.setattr(akshare, "stock_sector_spot", lambda: _Frame([]), raising=False)
    monkeypatch.setattr(akshare, "stock_board_industry_name_ths", lambda: _Frame([]), raising=False)
    monkeypatch.setattr(
        akshare,
        "stock_board_concept_name_ths",
        lambda: _Frame([{"name": "白酒概念", "code": "301496"}]),
        raising=False,
    )
    monkeypatch.setattr(market_blocks_mod, "_fetch_concept_stocks_from_ths", _noisy_concept_rows)
    monkeypatch.setitem(sys.modules, "akshare", akshare)

    mcp = _DummyMCP()
    vector_mod.register(mcp)

    result = await mcp.semantic_stock_search(query="白酒", limit=5)
    captured = capsys.readouterr()

    assert result["success"] is True
    assert result["data"]["results"][0]["code"] == "600519"
    assert captured.out == ""


@pytest.mark.asyncio
async def test_get_financials_merges_db_tushare_and_akshare_layers(monkeypatch):
    today = date.today().isoformat()
    cached_entries = []

    monkeypatch.setattr(finance_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(finance_mod.cache, "get", lambda key, ttl_seconds: None)
    monkeypatch.setattr(finance_mod.cache, "set", lambda key, value: cached_entries.append((key, value)))
    monkeypatch.setattr(
        storage_mod,
        "get_db",
        lambda: _FinanceDB(
            [
                {
                    "code": "600519",
                    "report_date": today,
                    "revenue": 100.0,
                    "net_profit": 10.0,
                    "revenue_growth": 8.5,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        finance_mod,
        "_get_financials_tushare",
        lambda code: {
            "code": code,
            "reportDate": today,
            "roe": 12.5,
            "source": "tushare_pro",
        },
    )
    monkeypatch.setattr(
        finance_mod,
        "_get_financials_akshare",
        lambda code: {
            "code": code,
            "reportDate": today,
            "debtRatio": 35.0,
            "eps": 1.5,
            "currentRatio": 2.0,
            "bvps": 4.2,
            "source": "akshare_ths",
        },
    )
    monkeypatch.setattr(finance_mod, "baostock_client", None)

    result = await finance_mod.get_financials.__wrapped__("600519")

    assert result["success"] is True
    assert result["source"] == "akshare_ths"
    assert result["source_chain"] == ["db.get_financials", "tushare_pro", "akshare_financials"]
    assert result["data"]["revenue"] == 100.0
    assert result["data"]["netProfit"] == 10.0
    assert result["data"]["roe"] == 12.5
    assert result["data"]["debtRatio"] == 35.0
    assert result["data"]["eps"] == 1.5
    assert result["data"]["currentRatio"] == 2.0
    assert result["data"]["bvps"] == 4.2
    assert result["data"]["revenueGrowth"] == 8.5
    assert "tushare_pro incomplete" in " | ".join(result.get("fallback_reason") or [])
    assert cached_entries


def test_get_financials_tushare_prefers_more_complete_recent_row(monkeypatch):
    class _FakePro:
        def fina_indicator(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "end_date": "20250930",
                        "roe": None,
                        "debt_to_assets": None,
                        "current_ratio": None,
                        "eps": None,
                        "grossprofit_margin": None,
                        "netprofit_margin": None,
                        "tr_yoy": None,
                        "netprofit_yoy": None,
                    },
                    {
                        "end_date": "20250630",
                        "roe": 7.8,
                        "debt_to_assets": 91.2,
                        "current_ratio": 0.95,
                        "eps": 1.23,
                        "grossprofit_margin": 42.0,
                        "netprofit_margin": 18.0,
                        "tr_yoy": 4.5,
                        "netprofit_yoy": 6.1,
                    },
                ]
            )

        def income(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "end_date": "20250930",
                        "total_revenue": None,
                        "operate_profit": None,
                        "n_income": None,
                    },
                    {
                        "end_date": "20250630",
                        "total_revenue": 1000.0,
                        "operate_profit": 120.0,
                        "n_income": 88.0,
                    },
                ]
            )

        def balancesheet(self, **kwargs):
            return pd.DataFrame(
                [
                    {
                        "end_date": "20250630",
                        "total_assets": 10000.0,
                        "total_liab": 9120.0,
                        "total_cur_assets": 1900.0,
                        "total_cur_liab": 2000.0,
                    }
                ]
            )

    monkeypatch.setattr(finance_mod.data_source, "get_tushare_pro", lambda: _FakePro())

    result = finance_mod._get_financials_tushare("000001")

    assert result["reportDate"] == "20250630"
    assert result["revenue"] == 1000.0
    assert result["netProfit"] == 88.0
    assert result["roe"] == 7.8
    assert result["debtRatio"] == 91.2
    assert result["currentRatio"] == 0.95
    assert result["eps"] == 1.23
    assert result["revenueGrowth"] == 4.5
    assert result["profitGrowth"] == 6.1


@pytest.mark.asyncio
async def test_relative_valuation_handles_percentage_debt_ratio_units(monkeypatch):
    class _ValuationConn:
        async def fetch(self, query, *args):
            if "WHERE industry = $1 AND code != $2" in query:
                return [
                    {"code": "P1"},
                    {"code": "P2"},
                    {"code": "P3"},
                    {"code": "P4"},
                    {"code": "P5"},
                ]
            return []

    class _ValuationDB:
        def __init__(self):
            self.stock_info = {
                "TGT": {"name": "目标公司", "industry": "白酒", "market_cap": 100.0, "pe_ratio": 20.0, "pb_ratio": 3.0},
                "P1": {"name": "同业1", "market_cap": 95.0, "pe_ratio": 15.0, "pb_ratio": 2.0},
                "P2": {"name": "同业2", "market_cap": 98.0, "pe_ratio": 16.0, "pb_ratio": 2.1},
                "P3": {"name": "同业3", "market_cap": 102.0, "pe_ratio": 17.0, "pb_ratio": 2.2},
                "P4": {"name": "同业4", "market_cap": 105.0, "pe_ratio": 18.0, "pb_ratio": 2.3},
                "P5": {"name": "同业5", "market_cap": 110.0, "pe_ratio": 19.0, "pb_ratio": 2.4},
            }
            self.financials = {
                "TGT": [{"roe": 20.0, "debtRatio": 40.0, "revenueGrowth": 12.0, "operatingCashFlow": 120.0, "netProfit": 100.0}],
                "P1": [{"roe": 18.0, "debt_ratio": 35.0, "revenue_growth": 11.0, "operating_cash_flow": 130.0, "net_profit": 100.0}],
                "P2": [{"roe": 19.0, "debt_ratio": 36.0, "revenue_growth": 12.0, "operating_cash_flow": 125.0, "net_profit": 100.0}],
                "P3": [{"roe": 17.0, "debtRatio": 38.0, "revenueGrowth": 13.0, "operatingCashFlow": 140.0, "netProfit": 100.0}],
                "P4": [{"roe": 21.0, "debt_ratio": 39.0, "revenue_growth": 14.0, "operating_cash_flow": 150.0, "net_profit": 100.0}],
                "P5": [{"roe": 20.0, "debt_ratio": 41.0, "revenue_growth": 10.0, "operating_cash_flow": 135.0, "net_profit": 100.0}],
            }

        def acquire(self):
            return _Acquire(_ValuationConn())

        async def get_stock_info(self, code):
            return self.stock_info.get(code)

        async def get_financials(self, code, limit=1):
            rows = self.financials.get(code, [])
            return rows[:limit]

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _ValuationDB())

    result = await mcp.relative_valuation("TGT")

    assert result["success"] is True
    assert result["data"]["peer_count"] == 5
    assert result["data"]["peer_pool_build"]["after_quality_filter"] == 5
    assert result["data"]["peer_pool_build"]["quality_filter_relaxed"] is False
    assert result["data"]["peer_pool_build"]["quality_thresholds"]["debt_ratio_max"] == pytest.approx(65.0)


@pytest.mark.asyncio
async def test_ddm_valuation_falls_back_to_finance_eps_when_db_eps_missing(monkeypatch):
    class _DDMConn:
        async def fetchrow(self, query, *args):
            return {"eps": 0.0}

    class _DDMDB:
        def acquire(self):
            return _Acquire(_DDMConn())

        async def _financials_code_column(self, conn):
            return "code"

    async def _fake_get_financials(code):
        return {
            "success": True,
            "data": {
                "code": code,
                "reportDate": "2025-09-30",
                "eps": 2.0,
                "source": "tushare_pro",
            },
        }

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _DDMDB())
    monkeypatch.setattr(finance_mod, "get_financials", _fake_get_financials)

    result = await mcp.ddm_valuation("600519")

    assert result["success"] is True
    assert result["data"]["current_dividend"] == pytest.approx(0.6)
    assert result["data"]["source_chain"] == ["db.financials", "finance.get_financials"]
    assert "DB eps 缺失或非正值" in result["data"]["fallback_reason"]


@pytest.mark.asyncio
async def test_timescaledb_financials_handles_legacy_schema_without_new_columns():
    class _LegacyConn:
        def __init__(self):
            self.select_query = ""

        async def fetch(self, query, *args):
            if "information_schema.columns" in query:
                return [
                    {"column_name": "stock_code"},
                    {"column_name": "report_date"},
                    {"column_name": "revenue"},
                    {"column_name": "net_profit"},
                    {"column_name": "roe"},
                    {"column_name": "debt_ratio"},
                ]

            self.select_query = query
            return [
                {
                    "stock_code": "600519",
                    "report_date": pd.Timestamp("2025-09-30"),
                    "revenue": 0.0,
                    "net_profit": 10.0,
                    "gross_margin": None,
                    "net_margin": None,
                    "debt_ratio": 0.0,
                    "current_ratio": None,
                    "eps": None,
                    "roe": 0.0,
                    "bvps": None,
                    "roa": None,
                    "revenue_growth": None,
                    "profit_growth": None,
                }
            ]

    class _LegacyFinancialDB(FinancialsMixin):
        def __init__(self, conn):
            self._conn = conn

        def acquire(self):
            return _Acquire(self._conn)

    conn = _LegacyConn()
    db = _LegacyFinancialDB(conn)

    rows = await db.get_financials("600519", limit=1)

    assert "NULL AS gross_margin" in conn.select_query
    assert rows[0]["revenue"] == 0.0
    assert rows[0]["roe"] == 0.0
    assert rows[0]["debt_ratio"] == 0.0
    assert rows[0]["gross_margin"] is None
