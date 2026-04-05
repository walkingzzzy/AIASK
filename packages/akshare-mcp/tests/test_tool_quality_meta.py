from datetime import date, datetime, timedelta

import pandas as pd
import pytest

import akshare_mcp.storage as storage_mod
import akshare_mcp.tools.backtest as backtest_mod
import akshare_mcp.tools.basic_data as basic_data_mod
import akshare_mcp.tools.finance as finance_mod
import akshare_mcp.tools.fund_flow_market as fund_flow_market_mod
import akshare_mcp.tools.macro as macro_tool_mod
import akshare_mcp.tools.market.kline as kline_mod
import akshare_mcp.tools.market.limit_up as limit_up_mod
import akshare_mcp.tools.market.quote as quote_mod
import akshare_mcp.tools.search as search_mod
import akshare_mcp.tools.valuation as valuation_mod


class _DummyLimiter:
    def acquire(self):
        return True


class _FinanceDB:
    async def get_financials(self, code, limit=1):
        raise RuntimeError("db unavailable")


class _KlineDB:
    async def get_klines(self, code, **kwargs):
        raise RuntimeError("db unavailable")


class _PartialFundKlineDB:
    async def get_klines(self, code, **kwargs):
        return [
            {
                "date": date.today().isoformat(),
                "open": 2.95,
                "close": 3.01,
                "high": 3.03,
                "low": 2.94,
                "volume": 123456,
                "amount": 789012.0,
                "turnover": None,
                "change_pct": None,
                "source": "timescaledb",
            }
        ]


class _DummyMCP:
    def tool(self, **_kwargs):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn
        return _decorator


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ValuationStockInfoDB:
    async def get_stock_info(self, code):
        return {
            "code": code,
            "name": "贵州茅台",
            "pe_ratio": 21.8,
            "pb_ratio": 6.4,
            "market_cap": 1234.0,
        }


class _SearchConn:
    async def fetch(self, query, *args):
        return []


class _SearchDB:
    def acquire(self):
        return _Acquire(_SearchConn())


class _BacktestToolDB:
    def __init__(self):
        self.rows = [
            {
                "date": f"2025-02-{(idx % 28) + 1:02d}",
                "open": 10.0 + idx * 0.1,
                "close": 10.2 + idx * 0.1,
                "high": 10.4 + idx * 0.1,
                "low": 9.8 + idx * 0.1,
                "volume": 10000 + idx * 50,
            }
            for idx in range(80)
        ]

    async def get_klines(self, code, start_date=None, end_date=None):
        return list(self.rows)


@pytest.mark.asyncio
async def test_get_financials_quality_meta_exposes_fallback_chain(monkeypatch):
    today = date.today().isoformat()
    cached_entries = []

    monkeypatch.setattr(finance_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(finance_mod.cache, "get", lambda key, ttl_seconds: None)
    monkeypatch.setattr(finance_mod.cache, "set", lambda key, value: cached_entries.append((key, value)))
    monkeypatch.setattr(storage_mod, "get_db", lambda: _FinanceDB())
    monkeypatch.setattr(
        finance_mod,
        "_get_financials_tushare",
        lambda code: {
            "code": code,
            "reportDate": today,
            "revenue": 100.0,
            "netProfit": 10.0,
            "roe": 12.5,
            "debtRatio": 35.0,
            "source": "tushare_pro",
        },
    )
    monkeypatch.setattr(finance_mod, "_get_financials_akshare", lambda code: None)
    monkeypatch.setattr(finance_mod, "baostock_client", None)

    result = await finance_mod.get_financials.__wrapped__("600519")

    assert result["success"] is True
    assert result["source"] == "tushare_pro"
    assert result["backend_requested"] == "db.get_financials"
    assert result["backend_used"] == "tushare_pro"
    assert result["source_chain"] == ["db.get_financials", "tushare_pro"]
    assert result["fallback_chain"] == ["db.get_financials", "tushare_pro"]
    assert result["fallback_used"] is True
    assert result["quality_flags"] == ["fallback"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["db.get_financials failed: db unavailable"]

    assert cached_entries
    _, cached_payload = cached_entries[0]
    assert cached_payload["source_chain"] == ["db.get_financials", "tushare_pro"]
    assert cached_payload["fallback_reason"] == ["db.get_financials failed: db unavailable"]
    assert cached_payload["payload"]["source"] == "tushare_pro"


@pytest.mark.asyncio
async def test_get_financials_normalizes_aliases_and_zero_values(monkeypatch):
    today = date.today().isoformat()

    monkeypatch.setattr(finance_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(finance_mod.cache, "get", lambda key, ttl_seconds: None)
    monkeypatch.setattr(finance_mod.cache, "set", lambda key, value: None)
    monkeypatch.setattr(storage_mod, "get_db", lambda: _FinanceDB())
    monkeypatch.setattr(
        finance_mod,
        "_get_financials_tushare",
        lambda code: {
            "code": code,
            "report_date": today,
            "revenue": 0,
            "net_profit": 0,
            "roe": None,
            "debt_ratio": 0,
            "source": "tushare_pro",
        },
    )
    monkeypatch.setattr(finance_mod, "_get_financials_akshare", lambda code: None)
    monkeypatch.setattr(finance_mod, "baostock_client", None)

    result = await finance_mod.get_financials.__wrapped__("600519")

    assert result["success"] is True
    assert result["data"]["reportDate"] == today
    assert result["data"]["report_date"] == today
    assert result["data"]["netProfit"] == 0.0
    assert result["data"]["net_profit"] == 0.0
    assert result["data"]["debtRatio"] == 0.0
    assert result["data"]["debt_ratio"] == 0.0
    assert result["data"]["data_quality"]["field_state"]["netProfit"] == "present_zero"
    assert result["data"]["data_quality"]["field_state"]["debtRatio"] == "present_zero"
    assert result["data"]["data_quality"]["field_state"]["roe"] == "null"
    assert "roe" in result["missing_fields"]
    assert "partial" in result["quality_flags"]


@pytest.mark.asyncio
async def test_get_kline_quality_meta_tracks_db_to_datasource_fallback(monkeypatch):
    today = date.today().isoformat()

    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(kline_mod, "get_db", lambda: _KlineDB())
    monkeypatch.setattr(
        kline_mod.data_source,
        "get_kline",
        lambda code, period, limit: [
            {
                "date": today,
                "open": 10.0,
                "close": 10.5,
                "high": 10.8,
                "low": 9.9,
                "volume": 1000,
                "amount": 2000.0,
                "turnover": 1.2,
                "change_pct": 3.1,
                "source": "data_source",
            }
        ],
    )

    async def _noop_save(code, rows):
        return None

    monkeypatch.setattr(kline_mod, "_async_save_klines_to_db", _noop_save)

    result = await kline_mod.get_kline.__wrapped__("600519", "daily", 5)

    assert result["success"] is True
    assert result["source"] == "data_source"
    assert result["backend_requested"] == "db.get_klines"
    assert result["backend_used"] == "data_source"
    assert result["source_chain"] == ["db.get_klines", "data_source.get_kline"]
    assert result["fallback_used"] is True
    assert "fallback" in result["quality_flags"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["db.get_klines failed: db unavailable"]


@pytest.mark.asyncio
async def test_get_kline_accepts_partial_db_rows_for_fund_code(monkeypatch):
    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(kline_mod, "get_db", lambda: _PartialFundKlineDB())

    def _should_not_run(*args, **kwargs):
        raise AssertionError("fund-like partial DB rows should return before external fallbacks")

    monkeypatch.setattr(kline_mod.data_source, "get_kline", _should_not_run)

    result = await kline_mod.get_kline.__wrapped__("510050", "daily", 5)

    assert result["success"] is True
    assert result["source"] == "timescaledb"
    assert result["backend_requested"] == "db.get_klines"
    assert result["backend_used"] == "timescaledb"
    assert result["source_chain"] == ["db.get_klines"]
    assert result["fallback_used"] is False
    assert "partial" in result["quality_flags"]
    assert "degraded" in result["quality_flags"]
    assert result["missing_fields"] == ["turnover", "change_pct"]
    assert result["data"][0]["close"] == 3.01


def test_get_minute_kline_quality_meta_marks_fallback_source_chain(monkeypatch):
    now = datetime.now().replace(microsecond=0).isoformat(sep=" ")

    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(
        kline_mod,
        "_get_minute_kline_from_akshare",
        lambda code, minutes, limit: [
            {
                "date": now,
                "open": 10.0,
                "close": 10.2,
                "high": 10.3,
                "low": 9.9,
                "volume": 100,
                "amount": 1000.0,
                "turnover": 0.6,
                "change_pct": 1.5,
                "source": "akshare_minute",
            }
        ],
    )
    monkeypatch.setattr(kline_mod, "_get_minute_kline_from_sina", lambda code, minutes, limit: [])

    result = kline_mod.get_minute_kline.__wrapped__("600519", "5m", 10)

    assert result["success"] is True
    assert result["source"] == "akshare_minute"
    assert result["backend_requested"] == "data_source.get_kline"
    assert result["backend_used"] == "akshare_minute"
    assert result["source_chain"] == ["data_source.get_kline", "akshare.stock_zh_a_hist_min_em"]
    assert result["fallback_used"] is True
    assert result["quality_flags"] == ["fallback"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["data_source.get_kline returned non_intraday rows"]


@pytest.mark.asyncio
async def test_get_kline_data_quality_meta_keeps_full_attempt_chain(monkeypatch):
    today = date.today()
    start_date = (today - timedelta(days=1)).isoformat()
    end_date = today.isoformat()

    monkeypatch.setattr(kline_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(kline_mod, "get_db", lambda: _KlineDB())

    def _boom_datasource(code, period, limit):
        raise RuntimeError("ds unavailable")

    monkeypatch.setattr(kline_mod.data_source, "get_kline", _boom_datasource)

    class _DummyAk:
        @staticmethod
        def stock_zh_a_hist(symbol, period, start_date=None, end_date=None, adjust="qfq"):
            return pd.DataFrame(
                [
                    {
                        "日期": end_date[:4] + "-" + end_date[4:6] + "-" + end_date[6:8],
                        "开盘": 10.0,
                        "收盘": 10.6,
                        "最高": 10.8,
                        "最低": 9.8,
                        "成交量": 5000,
                        "成交额": 30000.0,
                        "换手率": 1.1,
                        "涨跌幅": 2.3,
                    }
                ]
            )

    async def _noop_save(code, rows):
        return None

    monkeypatch.setattr(kline_mod, "ak", _DummyAk())
    monkeypatch.setattr(kline_mod, "_async_save_klines_to_db", _noop_save)

    result = await kline_mod.get_kline_data(
        "600519",
        period="daily",
        start_date=start_date,
        end_date=end_date,
        limit=30,
    )

    assert result["success"] is True
    assert result["source"] == "akshare"
    assert result["backend_requested"] == "db.get_klines"
    assert result["backend_used"] == "akshare"
    assert result["source_chain"] == [
        "db.get_klines",
        "data_source.get_kline",
        "akshare.stock_zh_a_hist",
    ]
    assert result["fallback_used"] is True
    assert "fallback" in result["quality_flags"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == [
        "db.get_klines failed: db unavailable",
        "data_source.get_kline failed: ds unavailable",
    ]


@pytest.mark.asyncio
async def test_get_valuation_metrics_filters_non_positive_db_values(monkeypatch):
    class _ValuationConn:
        async def fetchrow(self, query, code):
            return {
                "code": code,
                "stock_name": "贵州茅台",
                "pe_ratio": 0.0,
                "pb_ratio": -1.0,
                "market_cap": 1234.0,
            }

    class _ValuationDB(_ValuationStockInfoDB):
        def acquire(self):
            return _Acquire(_ValuationConn())

    mcp = _DummyMCP()
    valuation_mod.register(mcp)
    monkeypatch.setattr(valuation_mod, "get_db", lambda: _ValuationDB())

    result = await mcp.get_valuation_metrics("600519")

    assert result["success"] is True
    assert result["data"]["pe_ratio"] == 21.8
    assert result["data"]["pb_ratio"] == 6.4
    assert result["data"]["market_cap"] == 1234.0
    assert result["data"]["data_quality"]["source_chain"] == [
        "db.stocks",
        "db.get_stock_info",
    ]
    assert result["data"]["data_quality"]["fallback_used"] is True
    assert result["data"]["data_quality"]["invalid_metrics"]["pe_ratio"][0]["reason"] == "non_positive"
    assert result["data"]["data_quality"]["invalid_metrics"]["pb_ratio"][0]["reason"] == "non_positive"


def test_get_macro_indicator_returns_read_only_meta_envelope(monkeypatch):
    class _TsPro:
        def cpi(self):
            return pd.DataFrame(
                [
                    {"month": "202601", "nt_val": 0.8, "nt_yoy": 0.8, "nt_mom": 0.1},
                    {"month": "202602", "nt_val": 1.2, "nt_yoy": 1.2, "nt_mom": 0.2},
                ]
            )

    monkeypatch.setattr(macro_tool_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(macro_tool_mod.data_source, "get_tushare_pro", lambda: _TsPro())

    result = macro_tool_mod.get_macro_indicator.__wrapped__("cpi", limit=2)

    assert result["success"] is True
    assert result["data"]["indicator"] == "cpi"
    assert len(result["data"]["records"]) == 2
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["source_chain"] == ["macro.get_indicator", "tushare_pro.cpi"]
    assert result["meta"]["quality"]["backend_used"] == "tushare_pro.cpi"
    assert result["meta"]["degraded"] is False


@pytest.mark.asyncio
async def test_get_stock_capital_tool_meta_marks_finance_fallback(monkeypatch):
    mcp = _DummyMCP()
    basic_data_mod.register(mcp)

    monkeypatch.setattr(
        basic_data_mod.data_source,
        "get_gb_info",
        lambda stock_code, date_list, count: {
            "success": False,
            "message": "gb unavailable",
            "source": "none",
            "backend_requested": "tushare_pro",
            "backend_used": "none",
            "fallback_used": False,
            "quality_flags": ["fallback"],
        },
    )
    monkeypatch.setattr(
        finance_mod,
        "get_stock_info",
        lambda code: {
            "success": True,
            "data": {"totalShares": 1000, "floatShares": 600},
        },
    )

    result = await mcp.get_stock_capital("600519")

    assert result["success"] is True
    assert result["data"]["source"] == "get_stock_info_fallback"
    assert result["meta"]["degraded"] is True
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["source_chain"] == [
        "basic_data.get_stock_capital",
        "market_data.tushare_pro",
        "finance.get_stock_info",
    ]
    assert result["meta"]["quality"]["fallback_used"] is True
    assert result["meta"]["quality"]["backend_used"] == "get_stock_info_fallback"
    assert result["data"]["capital_data"][0]["ltgb"] == 600.0


@pytest.mark.asyncio
async def test_run_simple_backtest_tool_exposes_pit_and_execution_reality(monkeypatch):
    mcp = _DummyMCP()
    backtest_mod.register(mcp)

    monkeypatch.setattr(backtest_mod, "get_db", lambda: _BacktestToolDB())
    monkeypatch.setattr(
        backtest_mod.backtest_engine,
        "run_backtest",
        lambda code, klines, strategy, params: {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy,
                "total_return": 0.18,
                "sharpe_ratio": 1.42,
            },
        },
    )

    result = await mcp.run_simple_backtest(
        "600519",
        strategy="ma_cross",
        start_date="2025-01-01",
        end_date="2025-03-31",
        short_period=5,
        long_period=20,
        as_of="2025-03-31",
    )

    assert result["success"] is True
    assert result["data"]["execution_reality"]["fill_model"] == "close_price"
    assert result["data"]["execution_reality"]["cost_model_mode"] == "backtest"
    assert result["meta"]["pit"]["event_time"] == "2025-03-31"
    assert result["meta"]["pit"]["event_time_window"] == {"start": "2025-01-01", "end": "2025-03-31"}
    assert result["meta"]["pit"]["feature_time_window"] == {"lookback_bars": 20}
    assert result["meta"]["pit"]["pit_passed"] is True


@pytest.mark.asyncio
async def test_run_batch_backtest_tool_exposes_pit_and_execution_reality(monkeypatch):
    mcp = _DummyMCP()
    backtest_mod.register(mcp)

    monkeypatch.setattr(backtest_mod, "get_db", lambda: _BacktestToolDB())
    monkeypatch.setattr(
        backtest_mod.backtest_engine,
        "run_backtest",
        lambda code, klines, strategy, params: {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy,
                "total_return": 0.08,
                "sharpe_ratio": 0.96,
            },
        },
    )
    monkeypatch.setattr(backtest_mod, "RAY_AVAILABLE", False)

    result = await mcp.run_batch_backtest(
        ["600519", "000858"],
        use_parallel=False,
        start_date="2025-01-01",
        end_date="2025-03-31",
        short_period=10,
        long_period=30,
        as_of="2025-03-31",
    )

    assert result["success"] is True
    assert result["data"]["execution_reality"]["total_cost_bps"] == pytest.approx(3.0)
    assert result["data"]["pit"]["feature_time_window"] == {"lookback_bars": 30}
    assert result["meta"]["pit"]["event_time_window"] == {"start": "2025-01-01", "end": "2025-03-31"}
    assert result["meta"]["quality"]["execution_mode"] == "local_sequential"


def test_get_limit_up_stocks_quality_metadata_distinguishes_missing_vs_derived(monkeypatch):
    monkeypatch.setattr(limit_up_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())

    def _fake_tushare(api_name, params=None, fields=""):
        if api_name == "stk_limit":
            return pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "trade_date": "20260318", "up_limit": 11.0},
                ]
            )
        if api_name == "daily":
            return pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "trade_date": "20260318", "close": 11.0, "pct_chg": 10.0, "vol": 12345},
                ]
            )
        if api_name == "daily_basic":
            return pd.DataFrame(
                [
                    {"ts_code": "000001.SZ", "turnover_rate": 1.8, "total_mv": 2200},
                ]
            )
        if api_name == "stock_basic" and fields == "ts_code,name":
            return pd.DataFrame([{"ts_code": "000001.SZ", "name": "平安银行"}])
        if api_name == "stock_basic" and fields == "ts_code,industry":
            return pd.DataFrame([{"ts_code": "000001.SZ", "industry": "银行"}])
        return pd.DataFrame()

    def _fake_fill_continuous(results, current_date):
        for item in results:
            limit_up_mod._mark_limit_up_field(item, "continuousDays", 2)

    monkeypatch.setattr(limit_up_mod, "_tushare_http_call", _fake_tushare)
    monkeypatch.setattr(limit_up_mod, "_fill_continuous_days", _fake_fill_continuous)
    monkeypatch.setattr(limit_up_mod, "_get_limit_up_stocks_from_akshare", lambda date: [])

    result = limit_up_mod.get_limit_up_stocks.__wrapped__("2026-03-18")

    assert result["success"] is True
    assert result["source"] == "tushare_combo"
    assert result["data_quality"]["derived_field_counts"]["name"] == 1
    assert result["data_quality"]["derived_field_counts"]["continuousDays"] == 1
    assert result["data_quality"]["missing_field_counts"]["openTimes"] == 1
    assert result["data"][0]["dataQuality"]["derived_fields"] == [
        "continuousDays",
        "industry",
        "marketCap",
        "name",
        "turnoverRate",
    ]
    assert "openTimes" in result["data"][0]["dataQuality"]["missing_fields"]
    assert result["data"][0]["openTimes"] is None


def test_get_block_trades_backfills_name_and_marks_quality(monkeypatch):
    monkeypatch.setattr(fund_flow_market_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(
        fund_flow_market_mod,
        "_fetch_eastmoney_datacenter",
        lambda params: [
            {
                "TRADE_DATE": "2026-03-18 00:00:00",
                "SECURITY_CODE": "600519",
                "SECUCODE": "600519.SH",
                "SECURITY_NAME_ABBR": "",
                "DEAL_PRICE": "1500.5",
                "DEAL_VOLUME": "1000",
                "DEAL_AMT": "1500500",
                "PREMIUM_RATIO": "1.2",
                "BUYER_NAME": "机构专用",
                "SELLER_NAME": "营业部A",
            }
        ],
    )
    monkeypatch.setattr(fund_flow_market_mod, "_get_cached_name_map", lambda: {"600519": "贵州茅台"})
    monkeypatch.setattr(fund_flow_market_mod.data_source, "get_tushare_pro", lambda: None)

    result = fund_flow_market_mod.get_block_trades("2026-03-18", "600519", 10)

    assert result["success"] is True
    assert result["source"] == "eastmoney_block_trade"
    assert result["data"][0]["name"] == "贵州茅台"
    assert result["data"][0]["dataQuality"]["derived_fields"] == ["name"]
    assert result["data_quality"]["name_backfilled_count"] == 1
    assert result["data_quality"]["missing_name_count"] == 0
    assert result["source_chain"] == ["eastmoney.block_trades"]


def test_get_realtime_quote_quality_meta_tracks_fallback_chain(monkeypatch):
    monkeypatch.setattr(quote_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(quote_mod.data_source, "get_realtime_quote", lambda code: (_ for _ in ()).throw(RuntimeError("ds unavailable")))
    monkeypatch.setattr(
        quote_mod,
        "_get_realtime_quote_akshare",
        lambda code: {
            "code": code,
            "name": "贵州茅台",
            "price": 1500.0,
            "change": 10.0,
            "changePercent": 0.67,
            "open": 1490.0,
            "high": 1510.0,
            "low": 1485.0,
            "preClose": 1490.0,
            "volume": 1000,
            "amount": 1500000.0,
            "source": "akshare",
        },
    )
    monkeypatch.setattr(quote_mod, "_get_quote_sina", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_quote_tencent", lambda code: None)
    monkeypatch.setattr(quote_mod, "_save_quote_nonblocking", lambda payload: None)

    result = quote_mod.get_realtime_quote.__wrapped__("600519")

    assert result["success"] is True
    assert result["source"] == "akshare"
    assert result["backend_requested"] == "data_source"
    assert result["backend_used"] == "akshare"
    assert result["source_chain"] == ["data_source", "akshare"]
    assert result["fallback_used"] is True
    assert "fallback" in result["quality_flags"]
    assert result["missing_fields"] == []
    assert result["fallback_reason"] == ["data_source失败: ds unavailable"]


def test_get_realtime_quote_quality_meta_marks_failed_chain(monkeypatch):
    monkeypatch.setattr(quote_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(quote_mod.data_source, "get_realtime_quote", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_realtime_quote_akshare", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_quote_sina", lambda code: None)
    monkeypatch.setattr(quote_mod, "_get_quote_tencent", lambda code: None)

    result = quote_mod.get_realtime_quote.__wrapped__("600519")

    assert result["success"] is False
    assert result["source"] == "none"
    assert result["backend_requested"] == "data_source"
    assert result["backend_used"] == "none"
    assert result["source_chain"] == ["data_source", "akshare", "sina", "tencent"]
    assert result["fallback_used"] is True
    assert "failed" in result["quality_flags"]
    assert result["fallback_reason"] == ["所有上游源均返回空数据"]


def test_get_realtime_quote_backfills_prev_close_and_timestamp(monkeypatch):
    monkeypatch.setattr(quote_mod, "get_limiter", lambda *args, **kwargs: _DummyLimiter())
    monkeypatch.setattr(
        quote_mod.data_source,
        "get_realtime_quote",
        lambda code: {
            "code": code,
            "name": "贵州茅台",
            "price": 1500.0,
            "open": 1498.0,
            "high": 1508.0,
            "low": 1492.0,
            "volume": 1000,
            "amount": 1500000.0,
            "source": "data_source",
        },
    )
    monkeypatch.setattr(quote_mod, "_get_daily_snapshot", lambda code: {"prev_close": 1490.0})
    monkeypatch.setattr(quote_mod, "_save_quote_nonblocking", lambda payload: None)
    monkeypatch.setattr(quote_mod, "_current_data_timestamp", lambda: "2026-03-21T10:15:30+08:00")

    result = quote_mod.get_realtime_quote.__wrapped__("600519")

    assert result["success"] is True
    data = result["data"]
    assert data["preClose"] == 1490.0
    assert data["change"] == 10.0
    assert round(data["changePercent"], 4) == round((10.0 / 1490.0) * 100, 4)
    assert data["data_timestamp"] == "2026-03-21T10:15:30+08:00"


@pytest.mark.asyncio
async def test_search_stocks_meta_marks_tushare_fallback(monkeypatch):
    class _SimpleDF:
        empty = False

        def iterrows(self):
            yield 0, {"ts_code": "600519.SH", "symbol": "600519", "name": "贵州茅台", "industry": "白酒"}

    class _FakePro:
        def stock_basic(self, **kwargs):
            return _SimpleDF()

    mcp = _DummyMCP()
    search_mod.register(mcp)
    monkeypatch.setattr(search_mod, "get_db", lambda: _SearchDB())
    monkeypatch.setattr(search_mod.data_source, "get_tushare_pro", lambda: _FakePro())

    result = await mcp.search_stocks(keyword="白酒", limit=5)

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["quality"]["fallback_used"] is True
    assert result["meta"]["degraded"] is True
    assert result["meta"]["source_chain"] == ["search.search_stocks", "db.search_stocks", "tushare_pro.stock_basic"]
