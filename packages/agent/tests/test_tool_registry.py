from __future__ import annotations

import asyncio
import json

from aiask_agent.intents import ActionIntentStore
from aiask_agent.mcp_client import MCPAggregator
from aiask_agent.tool_registry import build_default_tool_registry


def test_registry_exposes_only_aiask_financial_allowlist(tmp_path) -> None:
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))
    names = set(registry.names())
    assert {
        "agent_tool_catalog",
        "agent_analyze_stock",
        "agent_governance_check",
        "agent_data_validation",
        "agent_quant_data_gate",
        "agent_factor_validation",
        "agent_backtest_suite",
        "agent_portfolio_risk",
        "agent_quant_research_run",
        "agent_market_temperature_snapshot",
        "agent_market_temperature_cache_readiness",
        "agent_market_temperature_cache_history",
        "agent_market_temperature_industry_history",
        "agent_market_temperature_industry_constituents",
        "agent_market_temperature_forward_validation",
        "agent_factory_status",
        "agent_factory_runs",
        "agent_strategy_review_snapshot",
        "agent_trade_prediction_status",
        "agent_trade_prediction_outcomes",
        "agent_trade_prediction_matrix",
        "agent_stock_radar_status",
        "agent_stock_radar_candidates",
        "agent_stock_radar_digest",
        "agent_action_intent_create",
        "agent_action_intent_get",
    } <= names
    blocked = ("terminal", "file", "browser", "code", "strategy_manager", "available_tools", "get_tool_contract")
    assert not any(any(token in name for token in blocked) for name in names)

    catalog = asyncio.run(registry.call_tool("agent_tool_catalog", {}))
    assert catalog["success"] is True
    text = str(catalog["data"]).lower()
    assert "available_tools" not in text
    assert "get_tool_contract" not in text
    assert "strategy_manager" not in text
    assert catalog["meta"]["trace_id"]
    assert catalog["meta"]["source_chain"]
    assert catalog["meta"]["side_effect"]["level"] == "read_only"


def test_registry_catalog_exposes_formal_tool_contract_annotations(tmp_path) -> None:
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    catalog = asyncio.run(registry.call_tool("agent_tool_catalog", {}))

    assert catalog["success"] is True
    tools = catalog["data"]["tools"]
    assert tools
    for item in tools:
        annotations = item["annotations"]
        assert set(annotations) >= {
            "readOnlyHint",
            "destructiveHint",
            "idempotentHint",
            "openWorldHint",
            "requiresApproval",
            "tradeRisk",
        }
        assert item["outputSchema"]["required"] == ["success", "data", "error", "meta"]
        assert item["output_schema"] == item["outputSchema"]
        assert item["contract_version"] == "aiask_tool_contract_v2"

    by_name = {item["name"]: item for item in tools}
    quote = by_name["agent_stock_live_quote"]
    assert quote["annotations"]["readOnlyHint"] is True
    assert quote["annotations"]["destructiveHint"] is False
    assert quote["annotations"]["openWorldHint"] is True
    quote_data = quote["outputSchema"]["properties"]["data"]["properties"]
    assert {"code", "price", "provider", "data_timestamp", "source_chain"} <= set(quote_data)

    news_data = by_name["agent_stock_news_digest"]["outputSchema"]["properties"]["data"]["properties"]
    assert {"items", "news", "sources", "source_chain"} <= set(news_data)

    market_data = by_name["agent_market_temperature_snapshot"]["outputSchema"]["properties"]["data"]["properties"]
    assert {"market", "industries", "quality", "source_chain"} <= set(market_data)

    risk_data = by_name["agent_portfolio_risk"]["outputSchema"]["properties"]["data"]["properties"]
    assert {"portfolio_risk", "risk_metrics", "stress", "source_chain"} <= set(risk_data)

    intent_create = by_name["agent_action_intent_create"]
    assert intent_create["annotations"]["readOnlyHint"] is False
    assert intent_create["annotations"]["requiresApproval"] is True
    assert intent_create["annotations"]["idempotentHint"] is False
    intent_data = intent_create["outputSchema"]["properties"]["data"]["properties"]
    assert {"intent", "intent_id", "status", "side_effect"} <= set(intent_data)

    registry_item = registry.get("agent_action_intent_create")
    assert registry_item is not None
    assert registry_item.metadata["annotations"] == intent_create["annotations"]
    assert registry_item.metadata["outputSchema"] == intent_create["outputSchema"]


def test_market_temperature_agent_facade_is_read_only(monkeypatch, tmp_path) -> None:
    async def fake_snapshot(**kwargs):
        return {
            "success": True,
            "data": {
                "market": {"temperature": 66.6},
                "quality": {"status": "healthy"},
                "arguments": kwargs,
            },
            "error": None,
            "meta": {"side_effect": {"level": "read_only"}, "source_chain": ["fake.market_temperature"]},
        }

    monkeypatch.setattr(
        "aiask_agent.adapters.akshare.load_registered_tool",
        lambda module_name, function_name: fake_snapshot,
    )
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    result = asyncio.run(
        registry.call_tool(
            "agent_market_temperature_snapshot",
            {"limit": 2, "top_n": 1, "use_cache": False},
        )
    )

    assert result["success"] is True
    assert result["data"]["market"]["temperature"] == 66.6
    assert result["data"]["arguments"]["limit"] == 2
    assert result["data"]["arguments"]["use_cache"] is False
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["toolset"] == "finance_safe"
    assert registry.get("agent_market_temperature_snapshot").parameters["properties"]["use_cache"]["default"] is True


def test_market_temperature_cache_readiness_agent_facade_is_read_only(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    async def fake_readiness(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "data": {
                "ready": True,
                "status": "fresh",
                "read_only": True,
                "as_of": kwargs.get("as_of"),
                "max_stale_days": kwargs.get("max_stale_days"),
                "blockers": [],
            },
            "error": None,
            "meta": {"side_effect": {"level": "read_only"}, "source_chain": ["fake.db_freshness"]},
        }

    def fake_loader(module_name, function_name):
        assert module_name == "akshare_mcp.tools.db_freshness"
        assert function_name == "check_market_temperature_cache_readiness"
        return fake_readiness

    monkeypatch.setattr("aiask_agent.adapters.akshare.load_registered_tool", fake_loader)
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    result = asyncio.run(
        registry.call_tool(
            "agent_market_temperature_cache_readiness",
            {"as_of": "2026-06-08", "max_stale_days": 2},
        )
    )

    assert result["success"] is True
    assert result["data"]["ready"] is True
    assert result["data"]["status"] == "fresh"
    assert result["data"]["as_of"] == "2026-06-08"
    assert captured == {"as_of": "2026-06-08", "max_stale_days": 2}
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["toolset"] == "finance_safe"
    schema = registry.get("agent_market_temperature_cache_readiness").parameters
    assert schema["properties"]["max_stale_days"]["default"] == 1


def test_market_temperature_cache_history_agent_facade_is_read_only(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    async def fake_history(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "data": {
                "items": [
                    {
                        "as_of": "2026-06-08",
                        "market_temperature": 55.5,
                        "market_state": "neutral",
                        "stock_count": 300,
                        "industry_count": 5,
                        "quality_status": "healthy",
                        "warnings": [],
                    }
                ],
                "count": 1,
                "limit": kwargs.get("limit"),
                "include_snapshot": kwargs.get("include_snapshot"),
            },
            "error": None,
            "meta": {"side_effect": {"level": "read_only"}, "source_chain": ["fake.market_temperature"]},
        }

    def fake_loader(module_name, function_name):
        assert module_name == "akshare_mcp.tools.market_temperature"
        assert function_name == "list_market_temperature_snapshot_cache"
        return fake_history

    monkeypatch.setattr("aiask_agent.adapters.akshare.load_registered_tool", fake_loader)
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    result = asyncio.run(
        registry.call_tool(
            "agent_market_temperature_cache_history",
            {"limit": 5, "include_snapshot": False},
        )
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["items"][0]["as_of"] == "2026-06-08"
    assert captured == {"limit": 5, "include_snapshot": False}
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["toolset"] == "finance_safe"
    schema = registry.get("agent_market_temperature_cache_history").parameters
    assert schema["properties"]["limit"]["default"] == 30
    assert schema["properties"]["include_snapshot"]["default"] is False


def test_market_temperature_industry_history_agent_facade_is_read_only(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    async def fake_history(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "data": {
                "items": [
                    {
                        "as_of": "2026-06-08",
                        "name": "bank",
                        "temperature": 60.0,
                        "market_temperature": 55.5,
                        "quality_status": "healthy",
                    }
                ],
                "count": 1,
                "industry": kwargs.get("industry"),
                "match_mode": kwargs.get("match_mode"),
            },
            "error": None,
            "meta": {"side_effect": {"level": "read_only"}, "source_chain": ["fake.market_temperature"]},
        }

    def fake_loader(module_name, function_name):
        assert module_name == "akshare_mcp.tools.market_temperature"
        assert function_name == "list_market_temperature_industry_history"
        return fake_history

    monkeypatch.setattr("aiask_agent.adapters.akshare.load_registered_tool", fake_loader)
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    result = asyncio.run(
        registry.call_tool(
            "agent_market_temperature_industry_history",
            {"industry": "bank", "limit": 5, "top_n": 3, "match_mode": "exact"},
        )
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["items"][0]["temperature"] == 60.0
    assert captured == {"industry": "bank", "limit": 5, "top_n": 3, "match_mode": "exact"}
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["toolset"] == "finance_safe"
    schema = registry.get("agent_market_temperature_industry_history").parameters
    assert schema["properties"]["limit"]["default"] == 120
    assert schema["properties"]["top_n"]["maximum"] == 50


def test_market_temperature_industry_constituents_agent_facade_is_read_only(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    async def fake_constituents(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "data": {
                "items": [
                    {
                        "code": "000001",
                        "name": "Ping An Bank",
                        "industry": "bank",
                        "market_cap": 3120.8,
                    }
                ],
                "count": 1,
                "industry": kwargs.get("industry"),
                "match_mode": kwargs.get("match_mode"),
            },
            "error": None,
            "meta": {"side_effect": {"level": "read_only"}, "source_chain": ["fake.market_temperature"]},
        }

    def fake_loader(module_name, function_name):
        assert module_name == "akshare_mcp.tools.market_temperature"
        assert function_name == "list_market_temperature_industry_constituents"
        return fake_constituents

    monkeypatch.setattr("aiask_agent.adapters.akshare.load_registered_tool", fake_loader)
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    result = asyncio.run(
        registry.call_tool(
            "agent_market_temperature_industry_constituents",
            {"industry": "bank", "limit": 5, "offset": 1, "match_mode": "contains"},
        )
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["items"][0]["code"] == "000001"
    assert captured == {"industry": "bank", "limit": 5, "offset": 1, "match_mode": "contains"}
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["toolset"] == "finance_safe"
    schema = registry.get("agent_market_temperature_industry_constituents").parameters
    assert schema["required"] == ["industry"]
    assert schema["properties"]["limit"]["maximum"] == 1000
    assert schema["properties"]["match_mode"]["default"] == "contains"


def test_market_temperature_forward_validation_agent_facade_is_read_only(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    async def fake_forward_validation(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "data": {
                "matrix": {"warm": {"1d": {"sample_n": 3, "hit_rate": 0.67}}},
                "horizons": kwargs.get("horizons"),
                "target_field": kwargs.get("target_field"),
            },
            "error": None,
            "meta": {"side_effect": {"level": "read_only"}, "source_chain": ["fake.market_temperature"]},
        }

    def fake_loader(module_name, function_name):
        assert module_name == "akshare_mcp.tools.market_temperature"
        assert function_name == "get_market_temperature_forward_validation"
        return fake_forward_validation

    monkeypatch.setattr("aiask_agent.adapters.akshare.load_registered_tool", fake_loader)
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))

    result = asyncio.run(
        registry.call_tool(
            "agent_market_temperature_forward_validation",
            {"limit": 30, "horizons": [1, 3], "target_field": "benchmark_return", "benchmark_code": "000300"},
        )
    )

    assert result["success"] is True
    assert result["data"]["matrix"]["warm"]["1d"]["sample_n"] == 3
    assert captured == {"limit": 30, "horizons": [1, 3], "target_field": "benchmark_return", "benchmark_code": "000300"}
    assert result["meta"]["side_effect"]["level"] == "read_only"
    assert result["meta"]["toolset"] == "finance_safe"
    schema = registry.get("agent_market_temperature_forward_validation").parameters
    assert schema["properties"]["limit"]["maximum"] == 365
    assert schema["properties"]["target_field"]["default"] == "weighted_pct_change"
    assert "benchmark_return" in schema["properties"]["target_field"]["enum"]
    assert schema["properties"]["benchmark_code"]["default"] == "000300"


def test_mcp_contract_metadata_flows_into_agent_registry_without_raw_leaks(tmp_path) -> None:
    input_schema = {
        "type": "object",
        "properties": {"code": {"type": "string"}},
        "required": ["code"],
    }
    output_schema = {
        "type": "object",
        "properties": {"data": {"type": "object"}},
    }
    config_path = tmp_path / "mcp_servers.json"
    config_path.write_text(
        json.dumps(
            {
                "servers": [
                    {
                        "name": "akshare-demo",
                        "domain": "financial",
                        "command": "python",
                        "tools": [
                            {
                                "name": "get_realtime_quote",
                                "description": "quote tool",
                                "parameters": input_schema,
                                "input_schema": input_schema,
                                "output_schema": output_schema,
                                "freshness": {"expectation": "intraday_or_latest_quote_snapshot"},
                                "source_policy": {"priority": ["tdx_local", "akshare"]},
                                "examples": [{"arguments": {"code": "600519"}}],
                                "contract_version": "ai_tool_contract_v1",
                                "contract_source": "akshare_mcp.tool_catalog",
                                "standard_model": "EquityQuote",
                                "provider_choices": [{"rank": 1, "source": "tdx_local", "provider": "tdx_local"}],
                                "provider_status": {"providers": [{"provider": "tdx_local", "available": True}]},
                                "quality_gate": {"mode": "report_only", "status": "passed"},
                                "reconciliation": {"enabled": True, "mode": "sampled_report_only"},
                                "form_schema": input_schema,
                                "side_effect": {"level": "read_only"},
                            },
                            {
                                "name": "get_macro_indicator",
                                "description": "macro tool",
                                "parameters": {"type": "object", "properties": {"indicator": {"type": "string"}}, "required": ["indicator"]},
                                "input_schema": {"type": "object", "properties": {"indicator": {"type": "string"}}, "required": ["indicator"]},
                                "output_schema": output_schema,
                                "freshness": {"expectation": "latest_published_macro_indicator_snapshot"},
                                "source_policy": {"priority": ["tushare_pro.macro", "akshare.macro"]},
                                "examples": [{"arguments": {"indicator": "cpi"}}],
                                "contract_version": "ai_tool_contract_v1",
                                "contract_source": "akshare_mcp.tool_catalog",
                                "side_effect": {"level": "read_only"},
                            },
                            {
                                "name": "get_stock_fund_flow",
                                "description": "fund flow tool",
                                "parameters": input_schema,
                                "input_schema": input_schema,
                                "output_schema": output_schema,
                                "freshness": {"expectation": "intraday_or_latest_trading_day_fund_flow_snapshot"},
                                "source_policy": {"priority": ["db.stock_fund_flow", "tqcenter.more_info", "tushare.moneyflow"]},
                                "examples": [{"arguments": {"code": "600519"}}],
                                "contract_version": "ai_tool_contract_v1",
                                "contract_source": "akshare_mcp.tool_catalog",
                                "side_effect": {"level": "read_only"},
                            },
                            {
                                "name": "get_option_chain",
                                "description": "option chain tool",
                                "parameters": {"type": "object", "properties": {"underlying": {"type": "string"}}, "required": ["underlying"]},
                                "input_schema": {"type": "object", "properties": {"underlying": {"type": "string"}}, "required": ["underlying"]},
                                "output_schema": output_schema,
                                "freshness": {"expectation": "near_real_time_option_chain_snapshot"},
                                "source_policy": {"priority": ["akshare.option_sse_list_sina", "akshare.option_sse_codes_sina"]},
                                "examples": [{"arguments": {"underlying": "510050"}}],
                                "contract_version": "ai_tool_contract_v1",
                                "contract_source": "akshare_mcp.tool_catalog",
                                "side_effect": {"level": "read_only"},
                            },
                            {"name": "available_tools", "description": "legacy catalog"},
                            {"name": "get_tool_contract", "description": "legacy contract lookup"},
                            {"name": "strategy_manager", "description": "direct strategy manager"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    aggregator = MCPAggregator(config_path)
    tools = aggregator.financial_tools()
    assert [item["wrapped_name"] for item in tools] == [
        "agent_mcp_akshare_demo_get_realtime_quote",
        "agent_mcp_akshare_demo_get_macro_indicator",
        "agent_mcp_akshare_demo_get_stock_fund_flow",
        "agent_mcp_akshare_demo_get_option_chain",
    ]
    assert tools[0]["parameters"]["required"] == ["code"]
    assert tools[0]["input_schema"]["required"] == ["code"]
    assert tools[0]["contract_source"] == "akshare_mcp.tool_catalog"

    registry = build_default_tool_registry(
        ActionIntentStore(tmp_path / "intents.sqlite3"),
        mcp_aggregator=aggregator,
    )
    wrapped = registry.get("agent_mcp_akshare_demo_get_realtime_quote")
    assert wrapped is not None
    assert wrapped.parameters["required"] == wrapped.metadata["input_schema"]["required"]
    assert wrapped.metadata["output_schema"] == output_schema
    assert wrapped.metadata["outputSchema"] == output_schema
    assert wrapped.metadata["annotations"]["readOnlyHint"] is True
    assert wrapped.metadata["annotations"]["openWorldHint"] is True
    assert wrapped.metadata["annotations"]["requiresApproval"] is False
    assert wrapped.metadata["freshness"]["expectation"] == "intraday_or_latest_quote_snapshot"
    assert wrapped.metadata["source_policy"]["priority"] == ["tdx_local", "akshare"]
    assert wrapped.metadata["contract_version"] == "ai_tool_contract_v1"
    assert wrapped.metadata["standard_model"] == "EquityQuote"
    assert wrapped.metadata["provider_choices"][0]["provider"] == "tdx_local"
    assert wrapped.metadata["provider_status"]["providers"][0]["available"] is True
    assert wrapped.metadata["quality_gate"]["mode"] == "report_only"
    assert wrapped.metadata["reconciliation"]["enabled"] is True
    assert wrapped.metadata["form_schema"]["required"] == ["code"]
    catalog_item = next(item for item in registry.catalog if item["name"] == wrapped.name)
    assert catalog_item["contract_source"] == "akshare_mcp.tool_catalog"
    assert catalog_item["annotations"] == wrapped.metadata["annotations"]
    assert catalog_item["outputSchema"] == output_schema

    macro_wrapped = registry.get("agent_mcp_akshare_demo_get_macro_indicator")
    fund_wrapped = registry.get("agent_mcp_akshare_demo_get_stock_fund_flow")
    option_wrapped = registry.get("agent_mcp_akshare_demo_get_option_chain")
    assert macro_wrapped is not None
    assert fund_wrapped is not None
    assert option_wrapped is not None
    assert macro_wrapped.metadata["freshness"]["expectation"] == "latest_published_macro_indicator_snapshot"
    assert fund_wrapped.metadata["source_policy"]["priority"][0] == "db.stock_fund_flow"
    assert option_wrapped.metadata["source_policy"]["priority"][0] == "akshare.option_sse_list_sina"

    names = set(registry.names())
    assert names.isdisjoint({"available_tools", "get_tool_contract", "strategy_manager"})
    assert not any(name.startswith("agent_mcp_akshare_demo_available_tools") for name in names)


def test_intent_tools_create_and_get_enveloped_results(tmp_path) -> None:
    registry = build_default_tool_registry(ActionIntentStore(tmp_path / "intents.sqlite3"))
    created = asyncio.run(registry.call_tool(
        "agent_action_intent_create",
        {
            "action": "strategy_manager.factory_run_once",
            "params": {"execution_mode": "dry_run"},
            "user_id": "u1",
            "rationale": "test",
        },
    ))
    assert created["success"] is True
    assert created["meta"]["trace_id"]
    assert created["meta"]["source_chain"]
    assert created["meta"]["side_effect"]["confirmation_required"] is True
    intent_id = created["data"]["intent"]["intent_id"]

    fetched = asyncio.run(registry.call_tool("agent_action_intent_get", {"intent_id": intent_id}))
    assert fetched["success"] is True
    assert fetched["data"]["intent"]["status"] == "awaiting_confirmation"
