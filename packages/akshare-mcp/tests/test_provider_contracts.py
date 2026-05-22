from __future__ import annotations

import asyncio
from types import SimpleNamespace
from datetime import date

import pandas as pd

from akshare_mcp.provider_contracts.adapters import (
    fetch_equity_historical,
    fetch_equity_quote,
    fetch_stock_info,
    fetch_trading_calendar,
)
from akshare_mcp.provider_contracts.fetcher import ProviderFetcher, ProviderRegistryMap
from akshare_mcp.provider_contracts.generate_reference import build_reference_bundle
from akshare_mcp.provider_contracts.models import EquityHistoricalQuery, EquityQuoteQuery, StockInfoQuery, TradingCalendarQuery
from akshare_mcp.provider_contracts.result import AIASKFinancialResult
from akshare_mcp.tools import basic_data as basic_data_module
from akshare_mcp.tools import finance as finance_module
from akshare_mcp.tools import fund_flow as fund_flow_module
from akshare_mcp.tools import fund_flow_market as fund_flow_market_module
from akshare_mcp.tools import fund_flow_north as fund_flow_north_module
from akshare_mcp.tools import fund_flow_sector as fund_flow_sector_module
from akshare_mcp.tools import macro as macro_module
from akshare_mcp.tools import market_blocks as market_blocks_module
from akshare_mcp.tools import options as options_module
from akshare_mcp.tools.tool_catalog import get_tool_contract


TARGET_PROVIDER_CONTRACT_TOOLS = (
    "get_financials",
    "get_stock_info",
    "get_north_fund",
    "get_sector_fund_flow",
    "get_concept_fund_flow",
    "get_dragon_tiger",
    "get_margin_data",
    "get_margin_ranking",
    "get_block_trades",
    "get_north_fund_holding",
    "get_north_fund_top",
    "get_stock_fund_flow",
    "get_market_blocks",
    "get_block_stocks",
    "get_macro_indicator",
    "get_option_chain",
)

PLATFORM_PROVIDER_CONTRACT_TOOLS = (
    "calculate_technical_indicators",
    "check_candlestick_patterns",
    "get_available_patterns",
    "run_simple_backtest",
    "run_batch_backtest",
    "backtest_factor",
    "run_factor_group_backtest",
    "get_valuation_metrics",
    "dcf_valuation",
    "ddm_valuation",
    "relative_valuation",
    "get_historical_valuation",
    "scenario_dcf_valuation",
    "optimize_portfolio",
    "analyze_portfolio_risk",
    "stress_test_portfolio",
    "analyze_portfolio_risk_barra",
    "get_investment_analysis",
    "get_unified_decision_summary",
    "get_unified_decision_details",
    "get_unified_decision",
    "get_research_summary",
    "search_research_db",
    "get_stock_news",
    "get_market_news",
    "get_stock_notices",
    "get_stock_research",
    "get_research_reports",
    "get_profit_forecast",
    "get_analyst_ranking",
    "analyze_stock_sentiment",
    "calculate_fear_greed_index",
    "get_market_sentiment_context",
    "get_stock_text_signals",
    "check_all_alerts",
    "get_ipo_info",
    "get_cb_info",
    "get_stock_capital",
    "get_tdx_extended_data",
)


class FakeProvider:
    def get_realtime_quote(self, code: str) -> dict:
        return {
            "code": code,
            "name": "Demo",
            "price": 10.5,
            "change": 0.2,
            "changePercent": 1.94,
            "source": "tdx_local",
            "source_chain": ["tqcenter", "tdx_local"],
            "fallback_used": True,
            "fallback_reason": "tqcenter_empty",
            "time": "2026-05-20T10:30:00+08:00",
        }

    def get_kline(self, code: str, period: str = "daily", limit: int = 100) -> list[dict]:
        return [
            {"date": "2026-05-19", "open": 10.0, "close": 10.2, "high": 10.4, "low": 9.9, "volume": 1000, "source": "tdx_local"},
            {"date": "2026-05-20", "open": 10.2, "close": 10.5, "high": 10.6, "low": 10.1, "volume": 1200, "source": "tdx_local"},
        ][:limit]

    def get_stock_info(self, code: str) -> dict:
        return {
            "code": code,
            "name": "Demo",
            "industry": "Testing",
            "listDate": "20200101",
            "source": "tushare_pro",
        }

    def get_trading_dates(self, market: str = "SH", start_time: str = "", end_time: str = "", count: int = -1) -> dict:
        return {
            "success": True,
            "data": ["20260518", "20260519", "20260520"][-count if count > 0 else 0 :],
            "source": "tdx_local",
            "backend_requested": "tushare_pro",
            "backend_used": "tdx_local",
            "fallback_used": True,
            "fallback_reason": "tushare_skipped_for_tdx",
        }


def test_provider_contract_adapters_normalize_first_batch_models():
    provider = FakeProvider()

    quote = fetch_equity_quote(EquityQuoteQuery(code="600519"), provider=provider)
    assert quote.success is True
    assert quote.model == "EquityQuote"
    assert quote.data["code"] == "600519"
    assert quote.meta.provider_used == "tdx_local"
    assert quote.meta.fallback_used is True

    historical = fetch_equity_historical(EquityHistoricalQuery(code="600519", limit=2), provider=provider)
    assert historical.success is True
    assert historical.data["rows"][-1]["date"] == "2026-05-20"
    assert historical.meta.data_timestamp == "2026-05-20"

    info = fetch_stock_info(StockInfoQuery(code="600519"), provider=provider)
    assert info.success is True
    assert info.data["name"] == "Demo"
    assert info.meta.provider_used == "tushare_pro"

    calendar = fetch_trading_calendar(TradingCalendarQuery(count=2), provider=provider)
    assert calendar.success is True
    assert calendar.data["count"] == 2
    assert calendar.meta.provider_used == "tdx_local"


def test_first_batch_tool_catalog_contracts_are_explicit_provider_contracts():
    for tool_name in ("get_realtime_quote", "get_kline", "get_kline_data", "get_stock_info", "get_trading_dates"):
        contract = get_tool_contract(tool_name)
        assert contract is not None
        assert contract["contract_version"] == "ai_tool_contract_v1"
        assert contract["contract_source"] == "akshare_mcp.tool_catalog"
        assert contract.get("inferred_from_runtime") is None
        assert contract["input_schema"]["type"] == "object"
        assert contract["source_policy"]["priority"]
        assert contract["freshness"]["expectation"]


def test_high_frequency_tool_catalog_contracts_are_explicit_provider_contracts():
    expected_models = {
        "get_financials": "FinancialMetrics",
        "get_stock_info": "StockInfo",
        "get_north_fund": "NorthFundFlow",
        "get_sector_fund_flow": "SectorFundFlow",
        "get_concept_fund_flow": "ConceptFundFlow",
        "get_dragon_tiger": "DragonTiger",
        "get_margin_data": "MarginData",
        "get_margin_ranking": "MarginRanking",
        "get_block_trades": "BlockTrades",
        "get_north_fund_holding": "NorthFundHolding",
        "get_north_fund_top": "NorthFundTop",
        "get_stock_fund_flow": "StockFundFlow",
        "get_market_blocks": "MarketBlocks",
        "get_block_stocks": "BlockStocks",
        "get_macro_indicator": "MacroIndicator",
        "get_option_chain": "OptionChain",
    }

    for tool_name in TARGET_PROVIDER_CONTRACT_TOOLS:
        contract = get_tool_contract(tool_name)
        assert contract is not None
        assert contract["contract_version"] == "ai_tool_contract_v1"
        assert contract["contract_source"] == "akshare_mcp.tool_catalog"
        assert contract.get("inferred_from_runtime") is None
        assert contract["standard_model"] == expected_models[tool_name]
        assert contract["input_schema"]["type"] == "object"
        assert contract["output_schema"]["properties"]["meta"]["properties"]["provider_contract"]
        assert contract["source_policy"]["priority"]
        assert contract["freshness"]["expectation"]
        assert contract["examples"]


def test_platform_provider_contracts_have_generated_metadata():
    for tool_name in PLATFORM_PROVIDER_CONTRACT_TOOLS:
        contract = get_tool_contract(tool_name)
        assert contract is not None
        assert contract["contract_source"] == "akshare_mcp.tool_catalog"
        assert contract.get("inferred_from_runtime") is None
        assert contract["standard_model"]
        assert contract["provider_choices"]
        assert contract["provider_status"]["providers"]
        assert contract["quality_gate"]["mode"] == "report_only"
        assert contract["form_schema"]["type"] == "object"
        assert contract["input_schema"]["type"] == "object"


def test_provider_fetcher_lifecycle_preserves_data_shape_and_adds_quality_meta():
    contract = get_tool_contract("get_valuation_metrics")
    assert contract is not None
    fetcher = ProviderFetcher(
        contract,
        executor=lambda args: {
            "success": True,
            "data": {"code": args["code"], "pe_ratio": 12.3},
            "error": None,
            "source": "db.stocks",
            "meta": {"source_chain": ["db.stocks"], "quality": {"status": "available"}},
        },
    )

    missing = asyncio.run(fetcher.execute({}))
    assert missing.success is False
    assert missing.meta["quality_gate"]["failed_checks"] == ["required_arguments"]

    result = asyncio.run(fetcher.execute({"code": "600519"}))
    assert result.success is True
    assert result.data == {"code": "600519", "pe_ratio": 12.3}
    assert result.meta["provider_contract"]["standard_model"] == "ValuationMetrics"
    assert result.meta["quality_gate"]["status"] == "passed"
    assert result.meta["provider_status"]["providers"]


def test_provider_registry_reference_generation_is_read_only():
    registry_map = ProviderRegistryMap()
    report = registry_map.coverage_report(known_tools=list(PLATFORM_PROVIDER_CONTRACT_TOOLS))
    assert report["runtime_inference_fallback"] is False
    assert report["coverage"] == 1.0

    bundle = build_reference_bundle()
    assert bundle["tool_reference"]
    assert bundle["provider_capabilities"]
    assert bundle["coverage_report"]["explicit_contract_count"] >= len(TARGET_PROVIDER_CONTRACT_TOOLS)


def test_aiask_financial_result_wraps_existing_envelope_without_changing_data():
    original = {
        "success": True,
        "data": {"code": "600519", "price": 10.5},
        "error": None,
        "meta": {"quality": {"status": "available"}, "side_effect": {"level": "read_only"}},
    }
    wrapped = AIASKFinancialResult.from_tool_result(original, standard_data={"code": "600519"})
    assert wrapped.data == original["data"]
    assert wrapped.standard_data == {"code": "600519"}
    assert wrapped.to_tool_envelope()["data"] == original["data"]


def _assert_provider_meta(result: dict, tool_name: str, standard_model: str) -> None:
    assert result["meta"]["provider_contract"]["tool"] == tool_name
    assert result["meta"]["provider_contract"]["standard_model"] == standard_model
    assert result["meta"]["contract_meta"]["standard_model"] == standard_model
    assert result["meta"]["contract_meta"]["contract_source"] == "akshare_mcp.tool_catalog"
    assert result["meta"]["quality_gate"]["mode"] == "report_only"


def test_stock_info_tool_response_includes_provider_contract_meta(monkeypatch):
    monkeypatch.setattr(finance_module.data_source, "get_tushare_pro", lambda: None)
    monkeypatch.setattr(
        finance_module,
        "_call_with_retry",
        lambda _fn: pd.DataFrame(
            [
                {"item": "股票简称", "value": "Demo"},
                {"item": "行业", "value": "Testing"},
                {"item": "上市日期", "value": "20200101"},
            ]
        ),
    )

    result = finance_module.get_stock_info.__wrapped__(code="600519")

    assert result["success"] is True
    assert result["data"]["code"] == "600519"
    assert result["meta"]["argument_contract"]["canonical_tool"] == "get_stock_info"
    contract = result["meta"]["provider_contract"]
    assert contract["standard_model"] == "StockInfo"
    assert contract["tool"] == "get_stock_info"
    assert contract["provider_used"] == "akshare.stock_individual_info_em"
    assert result["meta"]["contract_meta"]["standard_model"] == "StockInfo"


def test_trading_dates_tool_response_includes_provider_contract_meta(monkeypatch):
    captured = {}

    class FakeMcp:
        def tool(self):
            def _register(fn):
                captured[fn.__name__] = fn
                return fn

            return _register

    basic_data_module.register(FakeMcp())
    monkeypatch.setattr(
        basic_data_module.data_source,
        "get_trading_dates",
        lambda **_kwargs: {
            "success": True,
            "data": ["20260518", "20260519", "20260520"],
            "source": "tdx_local",
            "backend_requested": "tqcenter",
            "backend_used": "tdx_local",
            "fallback_used": True,
        },
    )

    result = asyncio.run(captured["get_trading_dates"](count=3))

    assert result["success"] is True
    assert result["data"]["dates"] == ["20260518", "20260519", "20260520"]
    contract = result["meta"]["provider_contract"]
    assert contract["standard_model"] == "TradingCalendar"
    assert contract["tool"] == "get_trading_dates"
    assert contract["provider_requested"] == "market_data.tqcenter"
    assert contract["provider_used"] == "market_data.tdx_local"
    assert result["meta"]["contract_meta"]["standard_model"] == "TradingCalendar"


def test_financials_tool_response_includes_provider_contract_meta(monkeypatch):
    monkeypatch.setattr(finance_module.cache, "get", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(finance_module.cache, "set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(finance_module, "resolve_existing_security_code_sync", lambda code=None, **_kwargs: (code, {}, None))
    from akshare_mcp import storage as storage_module

    monkeypatch.setattr(storage_module, "get_db", lambda: (_ for _ in ()).throw(RuntimeError("skip db")))
    monkeypatch.setattr(
        finance_module,
        "_get_financials_tdx",
        lambda code: {
            "code": code,
            "reportDate": "2026-Q1",
            "revenue": 100.0,
            "netProfit": 20.0,
            "roe": 15.0,
            "debtRatio": 30.0,
            "source": "tqcenter",
        },
    )

    result = asyncio.run(finance_module.get_financials.__wrapped__(code="600519"))

    assert result["success"] is True
    _assert_provider_meta(result, "get_financials", "FinancialMetrics")
    assert result["meta"]["provider_contract"]["provider_used"] == "tqcenter"


def test_stock_fund_flow_tool_response_includes_provider_contract_meta(monkeypatch):
    monkeypatch.setattr(fund_flow_module, "resolve_existing_security_code_sync", lambda code=None, **_kwargs: (code, {}, None))
    monkeypatch.setattr(fund_flow_module, "_run_storage_call_sync", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(
        fund_flow_module.data_source,
        "get_more_info",
        lambda _code: {"Name": "Demo", "Zjl_HB": 1.0, "Zjl": 2.0},
    )

    result = fund_flow_module.get_stock_fund_flow(code="600519")

    assert result["success"] is True
    _assert_provider_meta(result, "get_stock_fund_flow", "StockFundFlow")
    assert result["meta"]["provider_contract"]["provider_used"] == "tqcenter.more_info"


def test_north_fund_tools_response_include_provider_contract_meta(monkeypatch):
    today = date.today().strftime("%Y-%m-%d")
    monkeypatch.setattr(
        fund_flow_north_module,
        "_north_fund_from_db",
        lambda _days: [{"date": today, "shConnect": 1.0, "szConnect": 2.0, "total": 3.0}],
    )
    monkeypatch.setattr(fund_flow_north_module, "_north_fund_from_tushare", lambda _days: [])
    monkeypatch.setattr(fund_flow_north_module, "_north_fund_from_hkex", lambda _days: [])
    monkeypatch.setattr(fund_flow_north_module, "_north_fund_from_eastmoney_direct", lambda _days: [])
    north = fund_flow_north_module.get_north_fund.__wrapped__(days=1)
    _assert_provider_meta(north, "get_north_fund", "NorthFundFlow")

    monkeypatch.setattr(fund_flow_north_module, "resolve_existing_security_code_sync", lambda stock_code=None, **_kwargs: (stock_code, {}, None))
    monkeypatch.setattr(
        fund_flow_north_module,
        "_run_storage_call_sync",
        lambda *_args, **_kwargs: ({"shares": 100.0, "ratio": 1.2, "change": 5.0, "trade_date": today, "source": "tqcenter.gpjy.GP06"}, None),
    )
    holding = fund_flow_north_module.get_north_fund_holding("600519")
    _assert_provider_meta(holding, "get_north_fund_holding", "NorthFundHolding")

    monkeypatch.setattr(
        fund_flow_north_module,
        "_fetch_eastmoney_datacenter",
        lambda _params: [{"SECURITY_CODE": "600519", "SECURITY_NAME": "Demo", "HOLD_SHARES": 100, "HOLD_SHARES_RATIO": 1.2, "HOLD_MARKET_CAP": 500}],
    )
    top = fund_flow_north_module.get_north_fund_top(top_n=1)
    _assert_provider_meta(top, "get_north_fund_top", "NorthFundTop")


def test_sector_and_concept_fund_flow_response_include_provider_contract_meta(monkeypatch):
    fund_flow_sector_module._sector_flow_cache["data"] = None
    fund_flow_sector_module._sector_flow_cache["ts"] = 0
    monkeypatch.setattr(fund_flow_sector_module, "_load_sector_flow_cache", lambda: None)
    monkeypatch.setattr(
        fund_flow_sector_module,
        "_fetch_sector_flow_from_db",
        lambda _top_n: [{"name": "Food", "mainNetInflow": 100.0, "source": "db.market_blocks"}],
    )
    sector = fund_flow_sector_module.get_sector_fund_flow.__wrapped__(top_n=1)
    _assert_provider_meta(sector, "get_sector_fund_flow", "SectorFundFlow")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"data": {"diff": [{"f14": "AI", "f3": 120, "f62": 1000, "f66": 200, "f184": 3.2}]}}

    monkeypatch.setattr(fund_flow_sector_module.requests, "get", lambda *_args, **_kwargs: FakeResponse())
    concept = fund_flow_sector_module.get_concept_fund_flow.__wrapped__(top_n=1)
    _assert_provider_meta(concept, "get_concept_fund_flow", "ConceptFundFlow")


def test_market_flow_tools_response_include_provider_contract_meta(monkeypatch):
    monkeypatch.setattr(fund_flow_market_module, "get_latest_trading_date", lambda: "20260520")
    monkeypatch.setattr(
        fund_flow_market_module,
        "ak",
        SimpleNamespace(
            stock_lhb_detail_daily_sina=lambda date: pd.DataFrame(
                [{"股票代码": "600519", "股票名称": "Demo", "收盘价": 10.0, "对应值": 1.0, "指标": "test"}]
            ),
            stock_lhb_detail_em=lambda start_date, end_date: pd.DataFrame(),
        ),
    )
    dragon = fund_flow_market_module.get_dragon_tiger(date="2026-05-20")
    _assert_provider_meta(dragon, "get_dragon_tiger", "DragonTiger")

    monkeypatch.setattr(
        fund_flow_market_module,
        "_margin_rows_from_db",
        lambda **_kwargs: [{"date": "2026-05-20", "code": "600519", "marginBalance": 1.0, "source": "margin_detail"}],
    )
    margin = fund_flow_market_module.get_margin_data(stock_code="600519", days=1)
    _assert_provider_meta(margin, "get_margin_data", "MarginData")

    monkeypatch.setattr(
        fund_flow_market_module,
        "_margin_ranking_from_db",
        lambda **_kwargs: [{"date": "2026-05-20", "code": "600519", "totalBalance": 1.0, "source": "margin_detail_ranking"}],
    )
    ranking = fund_flow_market_module.get_margin_ranking(top_n=1)
    _assert_provider_meta(ranking, "get_margin_ranking", "MarginRanking")

    monkeypatch.setattr(
        fund_flow_market_module,
        "_fetch_eastmoney_datacenter",
        lambda _params: [{"TRADE_DATE": "2026-05-20", "SECURITY_CODE": "600519", "SECURITY_NAME_ABBR": "Demo", "DEAL_PRICE": 10, "DEAL_VOLUME": 100, "DEAL_AMT": 1000}],
    )
    monkeypatch.setattr(fund_flow_market_module, "_get_security_meta_map", lambda _codes: {"600519": {"name": "Demo", "industry": "Food"}})
    block_trades = fund_flow_market_module.get_block_trades(stock_code="600519", limit=1)
    _assert_provider_meta(block_trades, "get_block_trades", "BlockTrades")


def test_macro_option_and_block_tools_response_include_provider_contract_meta(monkeypatch):
    monkeypatch.setattr(
        macro_module,
        "_try_tushare_macro",
        lambda indicator, limit: (
            {"indicator": indicator, "records": [{"period": "2026-04", "value": 1.0, "publishDate": "2026-04"}]},
            "tushare_pro.cpi",
        ),
    )
    macro = macro_module.get_macro_indicator.__wrapped__(indicator="cpi", limit=1)
    _assert_provider_meta(macro, "get_macro_indicator", "MacroIndicator")

    monkeypatch.setattr(
        options_module,
        "ak",
        SimpleNamespace(
            option_sse_list_sina=lambda symbol: ["202606"],
            option_sse_codes_sina=lambda **_kwargs: pd.DataFrame(),
            option_sse_underlying_spot_price_sina=lambda symbol: pd.DataFrame(),
        ),
    )
    option_chain = options_module.get_option_chain.__wrapped__(underlying="510050", limit=1)
    _assert_provider_meta(option_chain, "get_option_chain", "OptionChain")

    async def _fake_blocks(_block_type, _limit):
        return [{"block_code": "880001", "block_name": "Demo", "block_type": "industry", "source": "db"}]

    monkeypatch.setattr(market_blocks_module, "_fetch_from_db", _fake_blocks)
    market_blocks = asyncio.run(market_blocks_module.get_market_blocks(block_type="industry", limit=1))
    _assert_provider_meta(market_blocks, "get_market_blocks", "MarketBlocks")

    from akshare_mcp import data_source as data_source_module

    monkeypatch.setattr(
        data_source_module.data_source,
        "get_stock_list_in_sector",
        lambda *_args: [{"Code": "600519.SH", "Name": "Demo"}],
    )
    block_stocks = asyncio.run(market_blocks_module.get_block_stocks("880001"))
    _assert_provider_meta(block_stocks, "get_block_stocks", "BlockStocks")
