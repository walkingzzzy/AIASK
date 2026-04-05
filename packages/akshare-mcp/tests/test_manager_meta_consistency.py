import pytest

import akshare_mcp.tools.fund_flow as fund_flow_mod
import akshare_mcp.tools.market.limit_up as limit_up_tool_mod
import akshare_mcp.tools.macro as macro_tool_mod
import akshare_mcp.tools.managers.event_manager as event_manager_mod
import akshare_mcp.tools.managers.fundamental_analysis_manager as fundamental_manager_mod
import akshare_mcp.tools.managers.industry_chain_manager as industry_chain_manager_mod
import akshare_mcp.tools.managers.limit_up_manager as limit_up_manager_mod
import akshare_mcp.tools.managers.macro_manager as macro_manager_mod
import akshare_mcp.tools.managers.market_insight_manager as market_insight_manager_mod
import akshare_mcp.tools.managers.backtest_manager as backtest_manager_mod
import akshare_mcp.tools.managers.portfolio_manager as portfolio_manager_mod
import akshare_mcp.tools.managers.risk_manager as risk_manager_mod
import akshare_mcp.tools.managers.insight_manager as insight_manager_mod
import akshare_mcp.tools.managers.performance_manager as performance_manager_mod
import akshare_mcp.tools.managers.sector_manager as sector_manager_mod
import akshare_mcp.tools.managers.sentiment_manager as sentiment_manager_mod
import akshare_mcp.tools.managers.trading_data_manager as trading_data_manager_mod
import akshare_mcp.tools.managers.user_manager as user_manager_mod


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


class _FundamentalDB:
    async def get_financials(self, code, limit=4):
        return [
            {
                "code": code,
                "revenue": 1000000000,
                "n_income": 240000000,
                "basic_eps": 12.3,
                "roe": 18.6,
                "debt_ratio": 28.4,
                "gross_margin": 52.1,
                "revenue_growth": 9.8,
                "profit_growth": 11.2,
            }
        ]

    async def get_stock_info(self, code):
        return None


class _SentimentDB:
    async def get_klines(self, code, limit=20):
        return [
            {"open": 10.0, "close": 10.5, "volume": 1000},
            {"open": 10.5, "close": 10.7, "volume": 1100},
            {"open": 10.7, "close": 10.6, "volume": 950},
            {"open": 10.6, "close": 10.9, "volume": 1200},
            {"open": 10.9, "close": 11.1, "volume": 1300},
            {"open": 11.1, "close": 11.3, "volume": 1250},
        ]


class _EmptyFetchConn:
    async def fetch(self, query, *args):
        return []


class _TradingDB:
    def __init__(self):
        self.conn = _EmptyFetchConn()

    def acquire(self):
        return _Acquire(self.conn)

    async def get_klines(self, code, limit=1):
        return []


class _UserConn:
    def __init__(self):
        self.users = {
            "default": {
                "id": "default",
                "username": "demo",
                "email": "demo@example.com",
                "settings": {"theme": "light"},
                "created_at": "2026-03-18",
            }
        }

    async def fetchrow(self, query, *args):
        user_id = args[0]
        user = self.users.get(user_id)
        if not user:
            return None
        if "SELECT settings FROM users" in query:
            return {"settings": user.get("settings")}
        return dict(user)

    async def fetch(self, query, *args):
        limit = int(args[0]) if args else 50
        values = [dict(item) for item in self.users.values()]
        return values[:limit]

    async def execute(self, query, *args):
        settings_json, user_id = args
        user = self.users.get(user_id)
        if user is not None:
            import json

            user["settings"] = json.loads(settings_json)


class _UserDB:
    def __init__(self):
        self.conn = _UserConn()

    def acquire(self):
        return _Acquire(self.conn)


class _SectorConn:
    async def fetch(self, query, *args):
        if "FROM market_blocks" in query:
            block_type = args[0]
            return [
                {"block_code": "BK001", "block_name": "白酒", "block_type": block_type},
                {"block_code": "BK002", "block_name": "半导体", "block_type": block_type},
            ]
        return []


class _SectorDB:
    def __init__(self):
        self.conn = _SectorConn()

    def acquire(self):
        return _Acquire(self.conn)


class _BacktestConn:
    def __init__(self):
        self.rows = []

    async def execute(self, query, *args):
        self.rows.append((str(query), args))
        return "OK"


class _BacktestDB:
    def __init__(self):
        self.conn = _BacktestConn()
        self.klines = [
            {
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "open": 10 + i * 0.1,
                "high": 10.5 + i * 0.1,
                "low": 9.5 + i * 0.1,
                "close": 10 + i * 0.1,
                "volume": 100000 + i * 100,
            }
            for i in range(60)
        ]

    async def get_klines(self, code, limit=250):
        return self.klines[: int(limit)]

    async def save_klines(self, code, klines):
        return None

    def acquire(self):
        return _Acquire(self.conn)


class _PerformanceConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        return self.row


class _PerformanceDB:
    def __init__(self, row):
        self.conn = _PerformanceConn(row)

    def acquire(self):
        return _Acquire(self.conn)


def _assert_manager_meta(result: dict, expected_prefix: str):
    assert result["success"] is True
    assert "meta" in result
    meta = result["meta"]
    assert meta["trace_id"].startswith(expected_prefix)
    assert isinstance(meta["latency_ms"], int)
    assert meta["latency_ms"] >= 0
    assert isinstance(meta["source_chain"], list)
    assert meta["source_chain"]


@pytest.mark.asyncio
async def test_fundamental_manager_should_attach_meta_for_json_kwargs(monkeypatch):
    mcp = _DummyMCP()
    fundamental_manager_mod.register_fundamental_analysis_manager(mcp)
    monkeypatch.setattr(fundamental_manager_mod, "get_db", lambda: _FundamentalDB())

    result = await mcp.fundamental_analysis_manager(
        action="analyze",
        kwargs='{"stock_code":"600519"}',
    )

    _assert_manager_meta(result, "fundamental_analysis_manager:analyze:")
    assert result["data"]["code"] == "600519"
    assert result["data"]["metrics"]["roe"] == pytest.approx(18.6)
    assert result["meta"]["source_chain"] == ["fundamental_analysis_manager", "db.get_financials"]


@pytest.mark.asyncio
async def test_macro_manager_should_attach_meta_for_multi_indicator_kwargs_json(monkeypatch):
    mcp = _DummyMCP()
    macro_manager_mod.register_macro_manager(mcp)
    monkeypatch.setattr(macro_manager_mod, "get_db", lambda: object())
    monkeypatch.setattr(
        macro_tool_mod,
        "get_macro_indicator",
        lambda indicator, limit=5: {"success": False, "data": []},
    )

    result = await mcp.macro_manager(
        action="get_indicators",
        kwargs='{"indicators":["cpi","pmi"],"limit":3}',
    )

    _assert_manager_meta(result, "macro_manager:get_indicators:")
    assert result["data"]["requested_indicators"] == ["cpi", "pmi"]
    assert set(result["data"]["data"].keys()) == {"cpi", "pmi"}
    assert "macro_manager.fallback_indicators" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_sentiment_manager_should_attach_meta_for_stock_sentiment_json_kwargs(monkeypatch):
    mcp = _DummyMCP()
    sentiment_manager_mod.register_sentiment_manager(mcp)
    monkeypatch.setattr(sentiment_manager_mod, "get_db", lambda: _SentimentDB())

    result = await mcp.sentiment_manager(
        action="stock_sentiment",
        kwargs='{"stock_code":"600519"}',
    )

    _assert_manager_meta(result, "sentiment_manager:stock_sentiment:")
    assert result["data"]["code"] == "600519"
    assert result["data"]["indicators"]["up_days"] >= 1
    assert "db.get_klines" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_trading_data_manager_should_attach_meta_while_preserving_quality_payload(monkeypatch):
    mcp = _DummyMCP()
    trading_data_manager_mod.register_trading_data_manager(mcp)
    monkeypatch.setattr(trading_data_manager_mod, "get_db", lambda: _TradingDB())
    monkeypatch.setattr(
        fund_flow_mod,
        "get_block_trades",
        lambda date="", stock_code="", limit=500: {
            "success": True,
            "data": [
                {
                    "date": "2026-03-18",
                    "code": "600519",
                    "name": "贵州茅台",
                    "price": 1500.5,
                    "amount": 1500500.0,
                }
            ],
            "data_quality": {"name_backfilled_count": 1},
            "source_chain": ["eastmoney.block_trades"],
            "fallback_reason": ["db block_trades empty"],
            "degraded": False,
        },
    )

    result = await mcp.trading_data_manager(
        action="block_trades",
        kwargs='{"stock_code":"600519","limit":10,"date":"2026-03-18"}',
    )

    _assert_manager_meta(result, "trading_data_manager:block_trades:")
    assert result["data"]["code"] == "600519"
    assert result["data"]["data_quality"]["name_backfilled_count"] == 1
    assert result["data"]["source_chain"] == ["eastmoney.block_trades"]
    assert "eastmoney.block_trades" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_market_insight_manager_should_attach_meta_for_sector_analysis(monkeypatch):
    mcp = _DummyMCP()
    market_insight_manager_mod.register_market_insight_manager(mcp)
    monkeypatch.setattr(
        fund_flow_mod,
        "get_sector_fund_flow",
        lambda top_n=10: {
            "success": True,
            "data": [
                {"name": "白酒", "mainNetInflow": 12.5},
                {"name": "半导体", "mainNetInflow": 9.6},
                {"name": "银行", "mainNetInflow": -1.5},
            ],
        },
    )
    monkeypatch.setattr(
        fund_flow_mod,
        "get_concept_fund_flow",
        lambda top_n=5: {
            "success": True,
            "data": [
                {"name": "AI应用", "mainNetInflow": 8.2},
                {"name": "白酒概念", "mainNetInflow": 3.1},
            ],
        },
    )

    result = await mcp.market_insight_manager(
        action="sector_analysis",
        kwargs='{"sector":"白酒"}',
    )

    _assert_manager_meta(result, "market_insight_manager:sector_analysis:")
    assert result["data"]["requestedSector"] == "白酒"
    assert result["data"]["matchedCount"] >= 1
    assert "fund_flow.get_sector_fund_flow" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_market_insight_manager_market_trend_should_use_quote_fallback(monkeypatch):
    mcp = _DummyMCP()
    market_insight_manager_mod.register_market_insight_manager(mcp)

    monkeypatch.setattr(
        "akshare_mcp.tools.market.quote.get_index_quote",
        lambda index_code: {
            "success": True,
            "data": {
                "price": 3300.0,
                "changePercent": 2.17,
                "open": 3240.0,
                "high": 3312.0,
                "low": 3210.0,
                "preClose": 3230.0,
            },
        },
    )

    async def _fake_get_index_kline(**kwargs):
        return {"success": False, "error": "network unavailable"}

    monkeypatch.setattr("akshare_mcp.tools.market.kline.get_index_kline", _fake_get_index_kline)

    result = await mcp.market_insight_manager(action="market_trend", kwargs="{}")

    _assert_manager_meta(result, "market_insight_manager:market_trend:")
    assert result["data"]["analysisMode"] == "quote_fallback"
    assert result["data"]["trend"] == "bullish"
    assert result["data"]["strength"] == "strong"
    assert result["data"]["keyLevels"]["support"] == 3210.0
    assert result["data"]["keyLevels"]["resistance"] == 3312.0
    assert result["data"]["movingAverages"]["ma5"] == 3300.0
    assert result["data"]["movingAverages"]["ma20"] == 3230.0
    assert "market_trend.quote_fallback" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_limit_up_manager_should_attach_meta_while_preserving_quality_payload(monkeypatch):
    mcp = _DummyMCP()
    limit_up_manager_mod.register_limit_up_manager(mcp)
    monkeypatch.setattr(
        limit_up_tool_mod,
        "get_limit_up_statistics",
        lambda date="": {
            "success": True,
            "data": {
                "totalLimitUp": 12,
                "failedBoard": 3,
                "successRate": 75.0,
            },
            "data_quality": {"missing_field_counts": {"openTimes": 2}},
            "source_chain": ["tushare.stk_limit", "tushare.daily"],
            "fallback_reason": ["openTimes unavailable from source"],
            "degraded": True,
        },
    )

    result = await mcp.limit_up_manager(
        action="statistics",
        kwargs='{"date":"2026-03-18"}',
    )

    _assert_manager_meta(result, "limit_up_manager:statistics:")
    assert result["data"]["total_limit_up"] == 12
    assert result["data"]["data_quality"]["missing_field_counts"]["openTimes"] == 2
    assert result["data"]["source_chain"] == ["tushare.stk_limit", "tushare.daily"]
    assert "tushare.stk_limit" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_user_manager_should_attach_meta_and_merge_preferences(monkeypatch):
    mcp = _DummyMCP()
    user_manager_mod.register_user_manager(mcp)
    fake_db = _UserDB()
    monkeypatch.setattr(user_manager_mod, "get_db", lambda: fake_db)

    result = await mcp.user_manager(
        action="update_preferences",
        kwargs='{"user_id":"default","preferences":{"risk_level":"balanced"}}',
    )

    _assert_manager_meta(result, "user_manager:update_preferences:")
    assert result["data"]["updated"] is True
    assert result["data"]["preferences"]["theme"] == "light"
    assert result["data"]["preferences"]["risk_level"] == "balanced"
    assert result["meta"]["source_chain"] == ["user_manager", "db.users"]


@pytest.mark.asyncio
async def test_industry_chain_manager_should_attach_meta_for_keyword_related_stocks(monkeypatch):
    mcp = _DummyMCP()
    industry_chain_manager_mod.register_industry_chain_manager(mcp)
    monkeypatch.setattr(industry_chain_manager_mod, "get_db", lambda: object())

    result = await mcp.industry_chain_manager(
        action="related_stocks",
        kwargs='{"keyword":"半导体"}',
    )

    _assert_manager_meta(result, "industry_chain_manager:related_stocks:")
    assert result["data"]["industry"] == "半导体"
    assert result["data"]["count"] >= 1
    assert any(item["stage"] == "midstream" for item in result["data"]["related_stocks"])
    assert result["meta"]["source_chain"] == ["industry_chain_manager", "preset.industry_chains"]


@pytest.mark.asyncio
async def test_sector_manager_should_attach_meta_for_list_sectors(monkeypatch):
    mcp = _DummyMCP()
    sector_manager_mod.register_sector_manager(mcp)
    monkeypatch.setattr(sector_manager_mod, "get_db", lambda: _SectorDB())

    result = await mcp.sector_manager(
        action="list_sectors",
        kwargs='{"block_type":"industry"}',
    )

    _assert_manager_meta(result, "sector_manager:list_sectors:")
    assert result["data"]["count"] == 2
    assert result["data"]["sectors"][0]["block_code"] == "BK001"
    assert "db.market_blocks" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_risk_manager_should_attach_meta_for_codes_weights_input(monkeypatch):
    mcp = _DummyMCP()
    risk_manager_mod.register_risk_manager(mcp)
    monkeypatch.setattr(risk_manager_mod, "get_db", lambda: object())

    async def _fake_klines(db, code, limit):
        return (
            [
                {"close": 10.0, "volume": 1000, "amount": 10000, "date": "2026-03-14"},
                {"close": 10.2, "volume": 1100, "amount": 11220, "date": "2026-03-15"},
                {"close": 10.5, "volume": 1050, "amount": 11025, "date": "2026-03-16"},
                {"close": 10.4, "volume": 980, "amount": 10192, "date": "2026-03-17"},
                {"close": 10.8, "volume": 1200, "amount": 12960, "date": "2026-03-18"},
            ],
            ["db.get_klines"],
        )

    async def _fake_stock_info(db, code):
        return ({"industry": "白酒", "stock_name": "测试股票"}, ["db.get_stock_info"])

    async def _fake_financials(db, code):
        return ([{"roe": 18.0, "pe_ratio": 20.0, "pb_ratio": 4.0, "debt_ratio": 25.0}], ["db.get_financials"])

    monkeypatch.setattr(risk_manager_mod, "_get_klines_with_fallback", _fake_klines)
    monkeypatch.setattr(risk_manager_mod, "_get_stock_info_with_fallback", _fake_stock_info)
    monkeypatch.setattr(risk_manager_mod, "_get_financials_with_fallback", _fake_financials)

    result = await mcp.risk_manager(
        action="risk_exposure",
        kwargs='{"codes":["600519","000858"],"weights":[0.5,0.5],"portfolio_value":500000}',
    )

    _assert_manager_meta(result, "risk_manager:risk_exposure:")
    assert result["data"]["input_mode"] == "codes_weights"
    assert "input.codes_weights" in result["meta"]["source_chain"]
    assert "db.get_klines" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_backtest_manager_should_attach_meta_for_run(monkeypatch):
    mcp = _DummyMCP()
    backtest_manager_mod.register_backtest_manager(mcp)
    fake_db = _BacktestDB()
    monkeypatch.setattr(backtest_manager_mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(backtest_manager_mod, "register_artifact", lambda artifact: None)

    import akshare_mcp.services.backtest as backtest_service_mod

    monkeypatch.setattr(
        backtest_service_mod.backtest_engine,
        "run_backtest",
        lambda **kwargs: {
            "success": True,
            "data": {
                "final_capital": 108000.0,
                "total_return": 0.08,
                "annual_return": 0.12,
                "max_drawdown": 0.06,
                "sharpe_ratio": 1.1,
            },
        },
    )

    result = await mcp.backtest_manager(
        action="run",
        kwargs='{"code":"600519","strategy":"ma_cross","artifact_id":"art_meta_001","limit":60}',
    )

    _assert_manager_meta(result, "backtest_manager:run:")
    assert result["data"]["artifact_id"] == "art_meta_001"
    assert result["data"]["result"]["final_capital"] == 108000.0
    assert "db.get_klines" in result["meta"]["source_chain"]
    assert "services.backtest.backtest_engine" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_backtest_manager_should_sort_window_and_persist_extended_metrics(monkeypatch):
    mcp = _DummyMCP()
    backtest_manager_mod.register_backtest_manager(mcp)

    class _WindowBacktestConn:
        def __init__(self):
            self.rows = []

        async def execute(self, query, *args):
            self.rows.append((str(query), args))
            return "OK"

    class _WindowBacktestDB:
        def __init__(self):
            self.conn = _WindowBacktestConn()
            self.klines = [
                {
                    "date": f"2025-03-{day:02d}",
                    "open": 10.0 + day,
                    "high": 10.5 + day,
                    "low": 9.5 + day,
                    "close": 10.2 + day,
                    "volume": 100000 + day,
                }
                for day in range(31, 0, -1)
            ] + [
                {
                    "date": f"2025-02-{day:02d}",
                    "open": 20.0 + day,
                    "high": 20.5 + day,
                    "low": 19.5 + day,
                    "close": 20.2 + day,
                    "volume": 200000 + day,
                }
                for day in range(28, 0, -1)
            ] + [
                {
                    "date": f"2025-01-{day:02d}",
                    "open": 30.0 + day,
                    "high": 30.5 + day,
                    "low": 29.5 + day,
                    "close": 30.2 + day,
                    "volume": 300000 + day,
                }
                for day in range(31, 0, -1)
            ]

        async def get_klines(self, code, start_date=None, end_date=None, limit=None):
            return list(self.klines)

        async def save_klines(self, code, klines):
            return None

        def acquire(self):
            return _Acquire(self.conn)

    fake_db = _WindowBacktestDB()
    monkeypatch.setattr(backtest_manager_mod, "get_db", lambda: fake_db)
    monkeypatch.setattr(backtest_manager_mod, "register_artifact", lambda artifact: None)

    import akshare_mcp.services.backtest as backtest_service_mod

    captured = {}

    def _fake_run_backtest(**kwargs):
        captured["first_date"] = kwargs["klines"][0]["date"]
        captured["last_date"] = kwargs["klines"][-1]["date"]
        return {
            "success": True,
            "data": {
                "final_capital": 108000.0,
                "total_return": 0.08,
                "annual_return": 0.12,
                "max_drawdown": 0.06,
                "sharpe_ratio": 1.1,
                "sortino_ratio": 1.35,
                "trades_count": 9,
                "win_rate": 0.55,
            },
        }

    monkeypatch.setattr(backtest_service_mod.backtest_engine, "run_backtest", _fake_run_backtest)

    result = await mcp.backtest_manager(
        action="run",
        kwargs='{"code":"600519","strategy":"ma_cross","start_date":"2025-01-10","end_date":"2025-03-05"}',
    )

    _assert_manager_meta(result, "backtest_manager:run:")
    assert captured["first_date"] == "2025-01-10"
    assert captured["last_date"] == "2025-03-05"
    query, args = fake_db.conn.rows[0]
    assert "annual_return" in query
    assert "sortino_ratio" in query
    assert "win_rate" in query
    assert "trades_count" in query
    assert args[4].isoformat() == "2025-01-10"
    assert args[5].isoformat() == "2025-03-05"
    assert args[9] == 0.12
    assert args[12] == 1.35
    assert args[13] == 0.55
    assert args[14] == 9
    assert "db.backtest_results" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_performance_manager_should_attach_meta_for_backtest_metrics(monkeypatch):
    mcp = _DummyMCP()
    performance_manager_mod.register_performance_manager(mcp)
    fake_row = {
        "id": "bt_meta_001",
        "code": "600519",
        "strategy": "ma_cross",
        "params": '{"artifact_id": "art_perf_meta_001"}',
        "start_date": "2025-01-01",
        "end_date": "2025-02-01",
        "created_at": "2025-02-02",
        "initial_capital": 100000.0,
        "final_capital": 110000.0,
        "total_return": 0.10,
        "annual_return": 0.18,
        "max_drawdown": 0.05,
        "sharpe_ratio": 1.2,
        "sortino_ratio": 1.4,
        "win_rate": 0.6,
        "trades_count": 12,
    }
    monkeypatch.setattr(performance_manager_mod, "get_db", lambda: _PerformanceDB(fake_row))

    result = await mcp.performance_manager(action="backtest_metrics", kwargs='{"backtest_id":"bt_meta_001"}')

    _assert_manager_meta(result, "performance_manager:backtest_metrics:")
    assert result["data"]["artifact_id"] == "art_perf_meta_001"
    assert result["data"]["trades_count"] == 12
    assert result["meta"]["source_chain"] == ["performance_manager", "db.backtest_results"]


@pytest.mark.asyncio
async def test_event_manager_should_attach_meta_for_content_fallback(monkeypatch):
    mcp = _DummyMCP()
    event_manager_mod.register_event_manager(mcp)

    class _EventConn:
        async def fetch(self, query, *args):
            return []

    class _EventDB:
        def acquire(self):
            return _Acquire(_EventConn())

    monkeypatch.setattr(event_manager_mod, "get_db", lambda: _EventDB())
    monkeypatch.setattr(
        event_manager_mod,
        "get_stock_news",
        lambda code, limit=10: {
            "success": True,
            "data": [{"title": "新闻事件", "date": "2026-03-03", "source": "新闻源"}],
        },
    )
    monkeypatch.setattr(
        event_manager_mod,
        "get_stock_notices",
        lambda **kwargs: {
            "success": True,
            "data": {"events": [{"title": "公告事件", "date": "2026-03-02", "source": "公告"}]},
        },
    )
    monkeypatch.setattr(
        event_manager_mod,
        "get_stock_research",
        lambda code, limit=10: {
            "success": True,
            "data": {"reports": [{"title": "研报事件", "date": "2026-03-01", "institution": "机构A"}]},
        },
    )
    monkeypatch.setattr(event_manager_mod, "get_research_reports", lambda **kwargs: {"success": True, "data": []})

    result = await mcp.event_manager(
        action="get_by_code",
        kwargs='{"stock_code":"300750","limit":10}',
    )

    _assert_manager_meta(result, "event_manager:get_by_code:")
    assert result["data"]["source"] == "aggregated_content"
    assert result["data"]["fallback_used"] is True
    assert result["data"]["count"] == 3
    assert "db.events" in result["data"]["source_chain"]
    assert "news.get_stock_news" in result["meta"]["source_chain"]


@pytest.mark.asyncio
async def test_portfolio_manager_should_attach_meta_for_structured_create(monkeypatch):
    mcp = _DummyMCP()
    portfolio_manager_mod.register_portfolio_manager(mcp)

    class _PortfolioCreateConn:
        async def fetchval(self, query, *args):
            return 501

    class _PortfolioCreateDB:
        def acquire(self):
            return _Acquire(_PortfolioCreateConn())

    monkeypatch.setattr(portfolio_manager_mod, "get_db", lambda: _PortfolioCreateDB())

    result = await mcp.portfolio_manager(
        action="create",
        params={
            "name": "元数据组合",
            "user_id": "u_meta",
            "initial_capital": 320000,
            "metadata": {"benchmark": "000300"},
        },
    )

    _assert_manager_meta(result, "portfolio_manager:create:")
    assert result["data"]["portfolio_id"] == 501
    assert result["data"]["metadata"]["benchmark"] == "000300"
    assert result["meta"]["source_chain"] == ["portfolio_manager", "db.portfolios"]


@pytest.mark.asyncio
async def test_insight_manager_should_attach_meta_for_generate_report(tmp_path):
    mcp = _DummyMCP()
    insight_manager_mod.register_insight_manager(mcp)

    result = await mcp.insight_manager(
        action="generate_report",
        kwargs='{"report_type":"weekly","output_dir":"'
        + str(tmp_path).replace("\\", "/")
        + '","data_window":"2026-01-01~2026-02-01","next_actions":["rebalance"]}',
    )

    _assert_manager_meta(result, "insight_manager:generate_report:")
    assert result["data"]["report_type"] == "weekly"
    assert "markdown" in result["data"]["artifacts"]
    assert "filesystem.write_report_artifacts" in result["meta"]["source_chain"]
