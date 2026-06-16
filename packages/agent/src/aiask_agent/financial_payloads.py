from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .ai_payloads import ai_status_payload_for_runtime
from .audited_tool_calls import audited_runtime_tool_call
from .broker_readonly import (
    BrokerSyncContext,
    broker_readiness,
    latest_broker_payload,
    normalize_provider,
    run_behavior_analytics,
    sync_broker_readonly,
)
from .financial_readiness import financial_system_readiness
from .mcp_client import MCPAggregator
from .request_context import request_context_payload, tool_payload_with_request_context
from .route_auth import control_token_configured, hermes_full_enabled
from .runtime import AgentRuntime


ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


FINANCIAL_MANAGER_GROUPS: tuple[dict[str, str], ...] = (
    {"id": "overview", "label": "Overview", "description": "Readiness, manager coverage, and recent operating context."},
    {"id": "market-research", "label": "Market & Research", "description": "Stock analysis, research, sector, sentiment, technical, options, and trading-data reads."},
    {"id": "portfolio-watchlist", "label": "Portfolio & Watchlist", "description": "Portfolio, holdings, and watchlist reads plus intent-only mutations."},
    {"id": "risk-performance", "label": "Risk & Performance", "description": "Portfolio risk, VaR, exposure, stress, attribution, and benchmark comparison."},
    {"id": "quant-backtest", "label": "Quant & Backtest", "description": "Quant research, data gates, and backtest suite operations."},
    {"id": "paper-execution", "label": "Paper & Execution Planning", "description": "Paper trading and execution plan reads plus intent-only task changes."},
    {"id": "broker-readonly", "label": "Broker Read-only", "description": "THS/QMT account, position, order, and deal queries without live order placement."},
)

FINANCIAL_MANAGER_ACTIONS: tuple[dict[str, Any], ...] = (
    {"capability_id": "stock-analysis", "action_id": "analyze_stock", "group": "market-research", "label": "Analyze stock", "mode": "read_only", "tool": "agent_analyze_stock", "default_params": {"code": "600519", "include_decision": False}},
    {"capability_id": "research", "action_id": "reports", "group": "market-research", "label": "Research reports", "mode": "read_only", "mcp_tool": "research_manager", "mcp_action": "get_reports", "default_params": {"code": "600519", "limit": 5}},
    {"capability_id": "sector", "action_id": "sector_performance", "group": "market-research", "label": "Sector performance", "mode": "read_only", "mcp_tool": "sector_manager", "mcp_action": "sector_performance", "default_params": {"limit": 10}},
    {"capability_id": "sentiment", "action_id": "market_sentiment", "group": "market-research", "label": "Market sentiment", "mode": "read_only", "mcp_tool": "sentiment_manager", "mcp_action": "market_sentiment", "default_params": {}},
    {"capability_id": "technical", "action_id": "calculate", "group": "market-research", "label": "Technical indicators", "mode": "read_only", "mcp_tool": "technical_analysis_manager", "mcp_action": "calculate", "default_params": {"code": "600519", "indicators": ["ma", "rsi"]}},
    {"capability_id": "options", "action_id": "calculate_greeks", "group": "market-research", "label": "Option Greeks", "mode": "read_only", "mcp_tool": "options_manager", "mcp_action": "calculate_greeks", "default_params": {}},
    {"capability_id": "trading-data", "action_id": "dragon_tiger", "group": "market-research", "label": "Dragon tiger list", "mode": "read_only", "mcp_tool": "trading_data_manager", "mcp_action": "dragon_tiger", "default_params": {"limit": 20}},
    {"capability_id": "screener", "action_id": "screen", "group": "market-research", "label": "Stock screener", "mode": "read_only", "mcp_tool": "screener_manager", "mcp_action": "screen", "default_params": {"limit": 20}},
    {"capability_id": "portfolio", "action_id": "risk", "group": "risk-performance", "label": "Portfolio risk", "mode": "read_only", "tool": "agent_portfolio_risk", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "portfolio", "action_id": "list", "group": "portfolio-watchlist", "label": "Portfolio list", "mode": "read_only", "mcp_tool": "portfolio_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "portfolio", "action_id": "get_holdings", "group": "portfolio-watchlist", "label": "Portfolio holdings", "mode": "read_only", "mcp_tool": "portfolio_manager", "mcp_action": "get_holdings", "default_params": {"portfolio_id": 1}},
    {"capability_id": "portfolio", "action_id": "create", "group": "portfolio-watchlist", "label": "Create portfolio intent", "mode": "stateful_intent", "intent_action": "portfolio_manager.create", "default_params": {"name": "Desktop portfolio"}},
    {"capability_id": "portfolio", "action_id": "add_holding", "group": "portfolio-watchlist", "label": "Add holding intent", "mode": "stateful_intent", "intent_action": "portfolio_manager.add_holding", "default_params": {"portfolio_id": 1, "code": "600519", "shares": 100, "cost_price": 1800}},
    {"capability_id": "watchlist", "action_id": "list", "group": "portfolio-watchlist", "label": "Watchlist groups", "mode": "read_only", "mcp_tool": "watchlist_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "watchlist", "action_id": "add", "group": "portfolio-watchlist", "label": "Add watchlist stock intent", "mode": "stateful_intent", "intent_action": "watchlist_manager.add", "default_params": {"group": "default", "code": "600519"}},
    {"capability_id": "watchlist", "action_id": "remove", "group": "portfolio-watchlist", "label": "Remove watchlist stock intent", "mode": "stateful_intent", "intent_action": "watchlist_manager.remove", "default_params": {"group": "default", "code": "600519"}},
    {"capability_id": "risk", "action_id": "var", "group": "risk-performance", "label": "Risk VaR", "mode": "read_only", "mcp_tool": "risk_manager", "mcp_action": "var", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "risk", "action_id": "exposure", "group": "risk-performance", "label": "Risk exposure", "mode": "read_only", "mcp_tool": "risk_manager", "mcp_action": "exposure", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "performance", "action_id": "calculate_metrics", "group": "risk-performance", "label": "Performance metrics", "mode": "read_only", "mcp_tool": "performance_manager", "mcp_action": "calculate_metrics", "default_params": {"portfolio_id": 1}},
    {"capability_id": "decision", "action_id": "portfolio_advice", "group": "risk-performance", "label": "Portfolio advice", "mode": "read_only", "mcp_tool": "decision_manager", "mcp_action": "portfolio_advice", "default_params": {"codes": ["600519", "000001"], "weights": [0.5, 0.5]}},
    {"capability_id": "quant", "action_id": "data_gate", "group": "quant-backtest", "label": "Quant data gate", "mode": "read_only", "tool": "agent_quant_data_gate", "default_params": {"codes": ["600519", "000001"], "max_stale_days": 5}},
    {"capability_id": "quant", "action_id": "research_run", "group": "quant-backtest", "label": "Quant research run", "mode": "read_only", "tool": "agent_quant_research_run", "default_params": {"universe": ["600519", "000001"], "factors": ["momentum"], "benchmark": "000300"}},
    {"capability_id": "backtest", "action_id": "suite", "group": "quant-backtest", "label": "Backtest suite", "mode": "read_only", "tool": "agent_backtest_suite", "default_params": {"codes": ["600519", "000001"], "strategy": "ma_cross"}},
    {"capability_id": "backtest", "action_id": "list", "group": "quant-backtest", "label": "Saved backtests", "mode": "read_only", "mcp_tool": "backtest_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "paper", "action_id": "status", "group": "paper-execution", "label": "Paper trading status", "mode": "read_only", "mcp_tool": "paper_trading_manager", "mcp_action": "summary", "default_params": {}},
    {"capability_id": "paper", "action_id": "orders", "group": "paper-execution", "label": "Paper orders", "mode": "read_only", "mcp_tool": "paper_trading_manager", "mcp_action": "orders", "default_params": {"limit": 20}},
    {"capability_id": "paper", "action_id": "submit_order", "group": "paper-execution", "label": "Paper order intent", "mode": "stateful_intent", "intent_action": "paper_trading_manager.submit_order", "default_params": {"code": "600519", "side": "buy", "quantity": 100, "dry_run": True}},
    {"capability_id": "execution", "action_id": "plan", "group": "paper-execution", "label": "Execution tasks", "mode": "read_only", "mcp_tool": "execution_manager", "mcp_action": "list", "default_params": {}},
    {"capability_id": "execution", "action_id": "create_plan", "group": "paper-execution", "label": "Create execution plan intent", "mode": "stateful_intent", "intent_action": "execution_manager.create_plan", "default_params": {"code": "600519", "side": "buy", "quantity": 1000, "dry_run": True}},
    {"capability_id": "broker-ths", "action_id": "balance", "group": "broker-readonly", "label": "THS balance", "mode": "read_only", "mcp_tool": "ths_query_balance", "default_params": {}},
    {"capability_id": "broker-ths", "action_id": "positions", "group": "broker-readonly", "label": "THS positions", "mode": "read_only", "mcp_tool": "ths_query_position", "default_params": {}},
    {"capability_id": "broker-ths", "action_id": "orders", "group": "broker-readonly", "label": "THS orders", "mode": "read_only", "mcp_tool": "ths_query_orders", "default_params": {}},
    {"capability_id": "broker-ths", "action_id": "deals", "group": "broker-readonly", "label": "THS deals", "mode": "read_only", "mcp_tool": "ths_query_deals", "default_params": {}},
    {"capability_id": "broker-qmt", "action_id": "account", "group": "broker-readonly", "label": "QMT account", "mode": "read_only", "mcp_tool": "qmt_query_account", "default_params": {}},
    {"capability_id": "broker-qmt", "action_id": "positions", "group": "broker-readonly", "label": "QMT positions", "mode": "read_only", "mcp_tool": "qmt_query_position", "default_params": {}},
    {"capability_id": "broker-qmt", "action_id": "orders", "group": "broker-readonly", "label": "QMT orders", "mode": "read_only", "mcp_tool": "qmt_query_orders", "default_params": {}},
    {"capability_id": "broker-live", "action_id": "place_order", "group": "broker-readonly", "label": "Live place order", "mode": "blocked", "blocked_reason": "Live broker order placement is disabled in Financial Manager V1."},
    {"capability_id": "broker-live", "action_id": "cancel_order", "group": "broker-readonly", "label": "Live cancel order", "mode": "blocked", "blocked_reason": "Live broker cancellation is disabled in Financial Manager V1."},
)

FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE: dict[str, dict[str, Any]] = {
    "watchlist_manager.add": {"execution_mode": "confirmed_execute"},
    "watchlist_manager.remove": {"execution_mode": "confirmed_execute"},
    "portfolio_manager.create": {"execution_mode": "confirmed_execute"},
    "portfolio_manager.add_holding": {"execution_mode": "confirmed_execute"},
    "execution_manager.create_plan": {
        "execution_mode": "confirmed_execute_dry_run_only",
        "dry_run_required": True,
    },
    "paper_trading_manager.submit_order": {
        "execution_mode": "confirmed_execute_dry_run_only",
        "dry_run_required": True,
    },
}

FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS: tuple[str, ...] = tuple(
    action_name
    for action_name, policy in FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.items()
    if bool(policy.get("dry_run_required"))
)


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "archived"}
    return bool(value)


def _financial_action_key(capability_id: str, action_id: str) -> str:
    return f"{str(capability_id or '').strip()}::{str(action_id or '').strip()}"


def _financial_action_map() -> dict[str, dict[str, Any]]:
    return {
        _financial_action_key(str(item.get("capability_id") or ""), str(item.get("action_id") or "")): dict(item)
        for item in FINANCIAL_MANAGER_ACTIONS
    }


def _financial_execution_mode(action: dict[str, Any]) -> str:
    mode = str(action.get("mode") or "read_only")
    if mode == "blocked":
        return "blocked"
    if mode == "read_only":
        return "read_only"
    intent_action = str(action.get("intent_action") or "").strip()
    if intent_action and intent_action in FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE:
        return str(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE[intent_action]["execution_mode"])
    return "intent_only"


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("secret", "token", "api_key", "apikey", "password", "credential")):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def _wrapped_mcp_lookup(runtime: AgentRuntime) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for name in runtime.tool_registry.names():
        if not name.startswith("agent_mcp_"):
            continue
        tool = runtime.tool_registry.get(name)
        metadata = dict(getattr(tool, "metadata", {}) or {}) if tool else {}
        side_effect = metadata.get("side_effect") if isinstance(metadata.get("side_effect"), dict) else {}
        target = str(side_effect.get("target") or "")
        for candidate in {name, target, target.split(".")[0]}:
            if candidate:
                lookup.setdefault(candidate, {"wrapped_name": name, "metadata": metadata})
        lowered = name.lower()
        for action in FINANCIAL_MANAGER_ACTIONS:
            raw_tool = str(action.get("mcp_tool") or "").lower()
            if raw_tool and lowered.endswith(raw_tool):
                lookup.setdefault(str(action.get("mcp_tool")), {"wrapped_name": name, "metadata": metadata})
    return lookup


def _financial_mcp_availability_detail(
    runtime: AgentRuntime,
    action: dict[str, Any],
    mcp_lookup: dict[str, dict[str, Any]],
    *,
    mcp_tools: list[dict[str, Any]] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    required = str(action.get("mcp_tool") or "").strip()
    if not required:
        return {}
    names = set(runtime.tool_registry.names())
    match = mcp_lookup.get(required)
    tools = list(mcp_tools or MCPAggregator().tools_summary(include_all=True))
    servers = list(mcp_servers or MCPAggregator().servers_summary(include_all=True))
    matching_tools = [
        {
            "server": item.get("server"),
            "name": item.get("name"),
            "wrapped_name": item.get("wrapped_name"),
            "domain": item.get("domain"),
        }
        for item in tools
        if str(item.get("name") or "") == required or str(item.get("wrapped_name") or "") == required
    ]
    financial_servers = [
        {
            "name": item.get("name"),
            "domain": item.get("domain"),
            "transport": item.get("transport"),
            "tools_count": len(list(item.get("tools") or [])),
        }
        for item in servers
        if str(item.get("domain") or "").lower() == "financial"
    ]
    reason_code = "agent_mcp_wrapped_tool_ready"
    if not match:
        if matching_tools:
            reason_code = "mcp_tool_discovered_but_agent_registry_not_refreshed"
        elif not financial_servers:
            reason_code = "no_financial_mcp_server_registered"
        else:
            reason_code = "mcp_tool_not_discovered"
    wrapped_name = str((match or {}).get("wrapped_name") or "")
    return {
        "required_mcp_tool": required,
        "required_mcp_action": action.get("mcp_action"),
        "reason_code": reason_code,
        "agent_registry_has_wrapped_tool": bool(wrapped_name and wrapped_name in names),
        "wrapped_tool": wrapped_name or None,
        "matching_configured_tools": matching_tools,
        "financial_servers": financial_servers,
    }


def _financial_tool_availability_detail(runtime: AgentRuntime, action: dict[str, Any]) -> dict[str, Any]:
    required = str(action.get("tool") or "").strip()
    if not required:
        return {}
    names = set(runtime.tool_registry.names())
    return {
        "required_tool": required,
        "reason_code": "agent_tool_ready" if required in names else "agent_tool_missing",
        "agent_registry_has_tool": required in names,
    }


def financial_catalog_payload_for_runtime(runtime: AgentRuntime) -> dict[str, Any]:
    names = set(runtime.tool_registry.names())
    mcp_lookup = _wrapped_mcp_lookup(runtime)
    mcp = MCPAggregator()
    mcp_tools = mcp.tools_summary(include_all=True)
    mcp_servers = mcp.servers_summary(include_all=True)
    actions: list[dict[str, Any]] = []
    for raw in FINANCIAL_MANAGER_ACTIONS:
        item = dict(raw)
        mode = str(item.get("mode") or "read_only")
        item["execution_mode"] = _financial_execution_mode(item)
        item["available"] = False
        item["status"] = "unavailable"
        item["side_effect"] = {
            "level": "read_only" if mode == "read_only" else "stateful" if mode == "stateful_intent" else "trade_risk",
            "target": item.get("intent_action") or item.get("tool") or item.get("mcp_tool") or item.get("action_id"),
            "confirmation_required": mode != "read_only",
            "idempotent": mode == "read_only",
        }
        if mode == "blocked":
            item["status"] = "blocked"
            item["availability"] = {"reason_code": "blocked", "blocked_reason": item.get("blocked_reason")}
        elif item.get("tool"):
            item["available"] = str(item["tool"]) in names
            item["status"] = "ready" if item["available"] else "missing_tool"
            item["availability"] = _financial_tool_availability_detail(runtime, item)
        elif item.get("mcp_tool"):
            mcp = mcp_lookup.get(str(item["mcp_tool"]))
            item["available"] = bool(mcp)
            item["status"] = "ready" if mcp else "missing_mcp_tool"
            item["availability"] = _financial_mcp_availability_detail(
                runtime,
                item,
                mcp_lookup,
                mcp_tools=mcp_tools,
                mcp_servers=mcp_servers,
            )
            if mcp:
                item["wrapped_tool"] = mcp.get("wrapped_name")
        elif item.get("intent_action"):
            item["available"] = "agent_action_intent_create" in names
            item["status"] = "intent_ready" if item["available"] else "missing_intent_tool"
            item["availability"] = {
                "required_tool": "agent_action_intent_create",
                "reason_code": "action_intent_ready" if item["available"] else "action_intent_tool_missing",
                "agent_registry_has_tool": item["available"],
            }
        actions.append(item)
    summary: dict[str, int] = {}
    for item in actions:
        status = str(item.get("status") or "unknown")
        summary[status] = summary.get(status, 0) + 1
    return {
        "object": "aiask.desktop.financial_manager.catalog",
        "groups": list(FINANCIAL_MANAGER_GROUPS),
        "actions": actions,
        "summary": summary,
        "safety": {
            "mode": "read_only_plus_intents",
            "live_trading_enabled": False,
            "stateful_execution": "allowlisted_confirmed_actions",
            "confirmed_action_scope": list(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.keys()),
            "dry_run_only_actions": list(FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS),
            "secrets_redacted": True,
        },
        "stateful_execution": "allowlisted_confirmed_actions",
        "confirmed_action_scope": list(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.keys()),
        "dry_run_only_actions": list(FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS),
        "secrets_redacted": True,
    }


async def financial_status_payload_for_runtime(runtime: AgentRuntime) -> dict[str, Any]:
    catalog = financial_catalog_payload_for_runtime(runtime)
    readiness = await financial_system_readiness(
        runtime,
        full_runtime=None,
        full_mode_enabled=hermes_full_enabled(),
        control_token_configured=control_token_configured(),
        ai_status=ai_status_payload_for_runtime(runtime),
    )
    mcp = MCPAggregator()
    return {
        "object": "aiask.desktop.financial_manager.status",
        "status": readiness.get("status") or "unknown",
        "readiness": _redact_secrets(readiness),
        "catalog_summary": catalog.get("summary") or {},
        "mcp": {
            "registration": _redact_secrets(mcp.registration_diagnostics()),
            "servers": _redact_secrets(mcp.servers_summary(include_all=False)),
        },
        "stateful_execution": "allowlisted_confirmed_actions",
        "confirmed_action_scope": list(FINANCIAL_MANAGER_CONFIRMED_ACTION_SCOPE.keys()),
        "dry_run_only_actions": list(FINANCIAL_MANAGER_DRY_RUN_ONLY_ACTIONS),
        "broker": {
            "live_trading_enabled": False,
            "read_only_surfaces": ["ths_query_position", "ths_query_orders", "ths_query_deals", "qmt_query_account", "qmt_query_position", "qmt_query_orders"],
            "blocked_actions": ["ths_place_order", "ths_cancel_order", "qmt_place_order", "qmt_cancel_order"],
        },
        "recent_intents": [],
        "secrets_redacted": True,
    }


def _manager_arguments(action: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    mcp_action = str(action.get("mcp_action") or "").strip()
    if not mcp_action:
        return dict(params)
    return {"action": mcp_action, "params": dict(params), **dict(params)}


async def financial_query_payload_for_runtime(
    runtime: AgentRuntime,
    payload: dict[str, Any],
    *,
    tool_caller: ToolCaller | None = None,
) -> dict[str, Any]:
    action = _financial_action_map().get(_financial_action_key(str(payload.get("capability_id") or ""), str(payload.get("action_id") or "")))
    if not action:
        return {"object": "aiask.desktop.financial_manager.query", "success": False, "data": None, "error": "financial manager action is not registered", "error_code": "FINANCIAL_ACTION_NOT_FOUND", "secrets_redacted": True}
    if action.get("mode") == "blocked":
        return {"object": "aiask.desktop.financial_manager.query", "success": False, "data": {"action": action, "reason": action.get("blocked_reason")}, "error": str(action.get("blocked_reason") or "action is blocked"), "error_code": "FINANCIAL_ACTION_BLOCKED", "secrets_redacted": True}
    if action.get("mode") != "read_only":
        return {"object": "aiask.desktop.financial_manager.query", "success": False, "data": {"action": action, "required_endpoint": "/v1/desktop/financial-manager/intent"}, "error": "stateful financial actions must be created as ActionIntent", "error_code": "FINANCIAL_ACTION_REQUIRES_INTENT", "secrets_redacted": True}
    params = dict(action.get("default_params") or {})
    params.update(dict(payload.get("params") or {}))
    tool_name = str(action.get("tool") or "")
    if not tool_name and action.get("mcp_tool"):
        mcp_lookup = _wrapped_mcp_lookup(runtime)
        match = mcp_lookup.get(str(action.get("mcp_tool")))
        tool_name = str((match or {}).get("wrapped_name") or "")
        params = _manager_arguments(action, params)
    if not tool_name:
        availability = (
            _financial_mcp_availability_detail(runtime, action, _wrapped_mcp_lookup(runtime))
            if action.get("mcp_tool")
            else _financial_tool_availability_detail(runtime, action)
        )
        return {
            "object": "aiask.desktop.financial_manager.query",
            "success": False,
            "data": {"action": action, "availability": _redact_secrets(availability)},
            "error": "financial manager tool is not available",
            "error_code": "FINANCIAL_TOOL_UNAVAILABLE",
            "secrets_redacted": True,
        }
    tool_payload = tool_payload_with_request_context(params, payload)
    if tool_caller:
        result = await tool_caller(tool_name, tool_payload)
    else:
        tool = runtime.tool_registry.get(tool_name)
        result = await audited_runtime_tool_call(
            runtime,
            tool_name,
            tool_payload,
            metadata=dict(getattr(tool, "metadata", {}) or {}) if tool else {},
            source_chain=["aiask_agent.server", "financial_manager.query"],
        )
    return {
        "object": "aiask.desktop.financial_manager.query",
        "capability_id": action.get("capability_id"),
        "action_id": action.get("action_id"),
        "tool": tool_name,
        "success": bool(result.get("success")),
        "data": _redact_secrets(result.get("data")),
        "error": result.get("error"),
        "error_code": result.get("error_code"),
        "meta": _redact_secrets(result.get("meta")),
        "secrets_redacted": True,
    }


def _broker_request_context(payload: dict[str, Any] | None, *, headers: Any | None = None) -> BrokerSyncContext:
    context = request_context_payload(payload, headers=headers)
    return BrokerSyncContext(
        user_id=str(context.get("user_id") or "local"),
        session_id=context.get("session_id"),
        run_id=context.get("run_id"),
        trace_id=context.get("trace_id"),
        source=str(context.get("source") or "desktop"),
    )


def broker_readiness_payload_for_runtime(runtime: AgentRuntime) -> dict[str, Any]:
    return broker_readiness(runtime.session_store)


def broker_accounts_payload_for_runtime(runtime: AgentRuntime, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload or {})
    return latest_broker_payload(
        runtime.session_store,
        user_id=str(body.get("user_id") or "").strip() or None,
        provider=str(body.get("provider") or "").strip() or None,
    )


async def broker_sync_payload_for_runtime(
    runtime: AgentRuntime,
    payload: dict[str, Any],
    *,
    headers: Any | None = None,
    tool_caller: ToolCaller | None = None,
) -> dict[str, Any]:
    provider = normalize_provider(payload.get("provider"))
    context = _broker_request_context(payload, headers=headers)

    async def call_financial_query(_path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await financial_query_payload_for_runtime(runtime, body, tool_caller=tool_caller)

    result = await sync_broker_readonly(
        runtime.session_store,
        provider=provider,
        context=context,
        tool_caller=call_financial_query,
        consent=_truthy(payload.get("consent") or payload.get("consent_granted")),
    )
    runtime.session_store.record_activity_event(
        {
            "user_id": context.user_id,
            "session_id": context.session_id,
            "run_id": context.run_id,
            "trace_id": context.trace_id,
            "page_key": "broker-readonly",
            "route": "/v1/desktop/broker/sync",
            "event_type": "broker_readonly_sync",
            "target_type": "broker",
            "target_id": provider,
            "payload": {
                "success": result.get("success"),
                "error_code": result.get("error_code"),
                "read_only": True,
            },
            "source": context.source,
        }
    )
    return result


def broker_analytics_payload_for_runtime(runtime: AgentRuntime, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload or {})
    user_id = str(body.get("user_id") or "").strip() or None
    provider = str(body.get("provider") or "").strip() or None
    broker_profile_id = str(body.get("broker_profile_id") or "").strip() or None
    analytics = run_behavior_analytics(
        runtime.session_store,
        broker_profile_id=broker_profile_id,
        user_id=user_id,
        provider=provider,
        period_start=str(body.get("period_start") or "").strip() or None,
        period_end=str(body.get("period_end") or "").strip() or None,
    )
    return {
        "object": "aiask.desktop.broker_readonly.analytics",
        "success": True,
        "data": {"analytics": analytics},
        "error": None,
        "read_only": True,
        "live_trading_enabled": False,
        "secrets_redacted": True,
        "source_chain": ["aiask_agent.broker_readonly"],
    }


async def financial_intent_payload_for_runtime(
    runtime: AgentRuntime,
    payload: dict[str, Any],
    *,
    tool_caller: ToolCaller | None = None,
) -> dict[str, Any]:
    action = _financial_action_map().get(_financial_action_key(str(payload.get("capability_id") or ""), str(payload.get("action_id") or "")))
    if not action:
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": None, "error": "financial manager action is not registered", "error_code": "FINANCIAL_ACTION_NOT_FOUND", "secrets_redacted": True}
    if action.get("mode") == "blocked":
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": {"action": action, "reason": action.get("blocked_reason")}, "error": str(action.get("blocked_reason") or "action is blocked"), "error_code": "FINANCIAL_ACTION_BLOCKED", "secrets_redacted": True}
    if action.get("mode") != "stateful_intent":
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": {"action": action}, "error": "read-only financial actions do not create intents", "error_code": "FINANCIAL_ACTION_READ_ONLY", "secrets_redacted": True}
    params = dict(action.get("default_params") or {})
    params.update(dict(payload.get("params") or {}))
    intent_payload = tool_payload_with_request_context(
        {
            "action": str(action.get("intent_action") or ""),
            "params": params,
            "rationale": payload.get("rationale") or f"Financial Manager V1 intent for {action.get('label') or action.get('action_id')}",
            "user_id": payload.get("user_id"),
        },
        payload,
    )
    if tool_caller:
        result = await tool_caller("agent_action_intent_create", intent_payload)
    else:
        tool = runtime.tool_registry.get("agent_action_intent_create")
        result = await audited_runtime_tool_call(
            runtime,
            "agent_action_intent_create",
            intent_payload,
            metadata=dict(getattr(tool, "metadata", {}) or {}) if tool else {},
            source_chain=["aiask_agent.server", "financial_manager.intent"],
        )
    return {
        "object": "aiask.desktop.financial_manager.intent",
        "capability_id": action.get("capability_id"),
        "action_id": action.get("action_id"),
        "success": bool(result.get("success")),
        "data": _redact_secrets(result.get("data")),
        "error": result.get("error"),
        "error_code": result.get("error_code"),
        "meta": _redact_secrets(result.get("meta")),
        "secrets_redacted": True,
    }
