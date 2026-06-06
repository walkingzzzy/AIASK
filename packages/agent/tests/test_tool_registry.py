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
        "agent_factory_status",
        "agent_factory_runs",
        "agent_strategy_review_snapshot",
        "agent_trade_prediction_status",
        "agent_trade_prediction_outcomes",
        "agent_trade_prediction_matrix",
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
