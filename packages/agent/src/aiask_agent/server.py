from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, AsyncIterator, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .approvals import ApprovalStore
from .acp import ACPManager
from .ai_payloads import (
    ai_config_payload_for_runtime as _ai_config_payload_for_runtime,
    ai_models_payload_for_runtime as _ai_models_payload_for_runtime,
    ai_smoke_payload_for_runtime as _ai_smoke_payload_for_runtime,
    ai_status_payload_for_runtime as _ai_status_payload_for_runtime,
    save_ai_config_for_runtime as _save_ai_config_for_runtime,
)
from .audited_tool_calls import audited_runtime_tool_call
from .broker_readonly import (
    BrokerSyncContext,
    broker_readiness,
    latest_broker_payload,
    normalize_provider,
    run_behavior_analytics,
    sync_broker_readonly,
)
from .capabilities import HERMES_BASELINE, HERMES_BASELINE_VERSION, HERMES_RELEASE_TAG, parity_summary
from .desktop_payloads import (
    agent_endpoint as _agent_endpoint,
    desktop_data_status_payload_for_runtime as _desktop_data_status_payload_for_runtime,
    desktop_data_sync_plan_payload_for_runtime as _desktop_data_sync_plan_payload_for_runtime,
    desktop_settings_status_payload_for_runtime as _desktop_settings_status_payload_builder,
    local_profile_payload,
    save_local_profile,
)
from .desktop_capabilities_payloads import (
    desktop_capabilities_payload_for_runtime as _desktop_capabilities_payload_for_runtime,
)
from .env_config import load_project_env
from .gateway import ADAPTERS, DeliveryRouter, GatewayChannelDirectoryStore, GatewayConfigStore, GatewayMessageStore, GatewayRuntime, adapter_for, normalize_platform
from .financial_readiness import financial_system_readiness
from .hermes_payloads import (
    financial_readiness_payload_for_runtime as _financial_readiness_payload_for_runtime,
    hermes_readiness_payload_for_runtime as _hermes_readiness_payload_for_runtime,
    hermes_status_payload_for_runtime as _hermes_status_payload_for_runtime,
    parity_live_evidence as _parity_live_evidence,
    redact_required_env as _redact_required_env,
)
from .json_utils import dumps_json_bytes
from .learning_loop import LearningLoop
from .intents import ActionIntentStore, IntentExecutor
from .mcp_client import MCPAggregator
from .memory_providers import MemoryProviderManager
from .model_providers import ModelProviderRegistry, ProviderUsageStore
from .plugin_runtime import NativePluginManager
from .process_registry import ProcessRegistry
from .quant_research import QuantResearchStore
from .request_context import (
    request_context_payload as _request_context_payload,
    request_user_id_from_payload as _request_user_id_from_payload,
    tool_payload_with_request_context as _tool_payload_with_request_context,
)
from .response_payloads import (
    chat_completion_payload as _chat_completion_payload,
    messages_from_responses_payload as _messages_from_responses_payload,
    responses_payload as _responses_payload,
)
from .rl_atropos import RLAtroposManager
from .run_payloads import (
    _artifact_content_payload,
    _desktop_runs_payload,
    _handoff_queue_payload,
    _normalize_run_event,
    _run_trace_eval_payload,
    _session_resume_context_payload,
    _session_summary_payload,
    _workbench_summary_payload,
)
from .security import SecurityScanner
from .runtime import AgentRuntime
from .route_auth import (
    RouteAuthorizer,
    control_token_configured as _control_token_configured,
    extract_bearer_token as _extract_bearer_token,
    hermes_full_enabled as _hermes_full_enabled,
    is_loopback as _is_loopback,
    mode_error_status as _mode_error_status,
)
from .routes.ai import create_ai_router
from .routes.approvals import create_approvals_router
from .routes.connectors import create_connectors_router
from .routes.desktop_data import create_desktop_data_router
from .routes.desktop_finance import create_desktop_finance_router
from .routes.desktop_runs import create_desktop_runs_router
from .routes.desktop_user import create_desktop_user_router
from .routes.desktop_workbench import create_desktop_workbench_router
from .routes.full_controls import create_full_controls_router
from .routes.gateway import create_gateway_router
from .routes.health import create_health_router
from .routes.hermes import create_hermes_router
from .routes.hermes_status import create_hermes_status_router
from .routes.intents import create_intents_router
from .routes.jobs import create_jobs_router
from .routes.learning_rl import create_learning_rl_router
from .routes.mcp import create_mcp_router
from .routes.plugins_skills import create_plugins_skills_router
from .routes.responses import create_responses_router
from .routes.run_control import create_run_control_router
from .routes.run_history import create_run_history_router
from .routes.tools import create_tools_router
from .routes.tools_catalog import build_tool_catalog_payload
from .routes.webhooks import create_webhooks_router
from .session_store import AgentSessionStore
from .skill_packs import SkillPackManager
from .stock_data_sources import list_stock_data_sources, save_stock_data_source, test_stock_data_source
from .native_capabilities import SkillStore
from .terminal_backends import list_backends, sessions as terminal_backend_sessions
from .tui import status as tui_status_payload
from .tool_registry import SAFE_TOOL_CATALOG, build_default_tool_registry
from .tool_risk import metadata_is_read_only
from .tools.policy import GENERAL_FULL_TOOLSET, ToolPolicy, ToolPolicyEngine
from .webhooks import WebhookStore
from .adapters import quant as quant_adapter
from .adapters.desktop_ops import factor_factory_status


ToolCaller = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _load_local_env_file() -> None:
    """Load a repo-local .env for CLI/dev launches without overriding the process env."""
    load_project_env()


def _json_dumps(payload: Any) -> bytes:
    return dumps_json_bytes(payload, ensure_ascii=False, sort_keys=True)


def _query_bool(query: dict[str, list[str]], key: str, *, default: bool = False) -> bool:
    values = query.get(key)
    if not values:
        return default
    value = str(values[-1] or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "archived"}
    return bool(value)


def _exception_messages(exc: BaseException) -> list[str]:
    messages = [str(exc)] if str(exc) else [exc.__class__.__name__]
    nested = getattr(exc, "exceptions", None)
    if isinstance(nested, (list, tuple)):
        for item in nested:
            if isinstance(item, BaseException):
                messages.extend(_exception_messages(item))
            else:
                messages.append(str(item))
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, BaseException):
        messages.extend(_exception_messages(cause))
    return [message for index, message in enumerate(messages) if message and message not in messages[:index]]


def _classify_mcp_error(exc: BaseException) -> tuple[str, str]:
    messages = _exception_messages(exc)
    detail = "; ".join(messages)
    lowered = detail.lower()
    if (
        "401" in lowered
        or "unauthorized" in lowered
        or "authentication required" in lowered
        or "invalid_token" in lowered
        or "bearer token env" in lowered
    ):
        return "MCP_DISCOVERY_AUTH_REQUIRED", detail
    if "oauth" in lowered:
        return "MCP_DISCOVERY_OAUTH_REQUIRED", detail
    if "connection" in lowered or "connect" in lowered or "refused" in lowered:
        return "MCP_DISCOVERY_CONNECTION_FAILED", detail
    return "MCP_DISCOVERY_FAILED", detail


def _mcp_action_error_payload(*, action: str, server_name: str, exc: BaseException) -> dict[str, Any]:
    error_code, detail = _classify_mcp_error(exc)
    auth: dict[str, Any] = {}
    if server_name:
        try:
            auth = MCPAggregator().auth_readiness(server_name)
        except Exception:
            auth = {}
    return {
        "object": f"mcp.{action}",
        "success": False,
        "data": {
            "server": server_name or None,
            "configured": False,
            "status": "failed",
            "detail": detail,
            **auth,
        },
        "error": detail,
        "error_code": error_code,
    }


def _plugin_tools(plugin: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in list(plugin.get("tools") or []) if isinstance(item, dict) and item.get("name")]


def _plugin_self_test_payload(plugin: dict[str, Any], name: str) -> dict[str, Any]:
    tools = _plugin_tools(plugin)
    commands = [dict(item) for item in list(plugin.get("commands") or []) if isinstance(item, dict) and item.get("name")]
    return {
        "object": "plugin.tool_test",
        "success": True,
        "data": {
            "plugin": str(plugin.get("name") or name),
            "test_type": "manifest",
            "enabled": bool(plugin.get("enabled")),
            "manifest_valid": True,
            "tools_count": len(tools),
            "commands_count": len(commands),
            "hooks_count": len(list(plugin.get("hooks") or [])),
            "available_tools": [str(item.get("name") or "") for item in tools],
            "available_commands": [str(item.get("name") or "") for item in commands],
            "note": "plugin manifest is readable; no executable tool runner is required for this self-test",
        },
        "error": None,
    }


def _redacted_env_name(name: Any) -> str:
    text = str(name or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in ("secret", "token", "password", "credential")):
        return "[redacted-env-name]"
    return text


def _redact_sensitive_terms(text: str) -> str:
    redacted = str(text)
    replacements = {
        "secret": "sensitive",
        "token": "sensitive",
        "api_key": "sensitive",
        "apikey": "sensitive",
        "password": "sensitive",
        "credential": "sensitive",
        "credentials": "sensitive",
    }
    for needle, replacement in replacements.items():
        redacted = re.sub(re.escape(needle), replacement, redacted, flags=re.IGNORECASE)
    return redacted


def _redact_required_env(payload: Any, *, redact_sensitive_names: bool = False) -> Any:
    """Keep diagnostic env names visible, with an optional strict mode for public health payloads."""
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            if key in {"required_env", "live_env", "required_env_groups", "required_env_names", "missing_env", "auth_env_vars", "missing_auth_env_vars"} and isinstance(value, list):
                names = [str(item) for item in value if str(item).strip()]
                redacted[key] = [_redacted_env_name(item) for item in names] if redact_sensitive_names else names
            else:
                redacted[key] = _redact_required_env(value, redact_sensitive_names=redact_sensitive_names)
        return redacted
    if isinstance(payload, list):
        return [_redact_required_env(item, redact_sensitive_names=redact_sensitive_names) for item in payload]
    if redact_sensitive_names and isinstance(payload, str):
        return _redact_sensitive_terms(payload)
    return payload


def _parity_live_evidence(parity: dict[str, Any]) -> dict[str, Any]:
    checked_at = int(time.time())
    rows: list[dict[str, Any]] = []
    required_env_groups: set[str] = set()
    required_env_names: set[str] = set()
    sections = (
        ("capability", parity.get("matrix") or []),
        ("tool", parity.get("hermes_tool_mapping") or []),
        ("gateway_platform", parity.get("gateway_platform_mapping") or []),
        ("feature", parity.get("feature_mapping") or []),
    )
    delta_items: list[dict[str, Any]] = []
    for delta_name in ("v014_delta", "v016_delta"):
        delta = parity.get(delta_name)
        if not isinstance(delta, dict):
            continue
        for bucket in ("implemented", "partial", "missing", "excluded_by_design"):
            delta_items.extend(item for item in list(delta.get(bucket) or []) if isinstance(item, dict))
    if delta_items:
        sections = (*sections, ("delta", delta_items))
    for kind, items in sections:
        for item in list(items or []):
            if not isinstance(item, dict):
                continue
            required_env = [str(name) for name in list(item.get("required_env") or []) if str(name).strip()]
            live_status = str(item.get("live_status") or "unknown")
            if required_env:
                for group in required_env:
                    required_env_groups.add(group)
                    for name in group.split("|"):
                        if name.strip():
                            required_env_names.add(name.strip())
            if not required_env and live_status == "not_required":
                continue
            label = item.get("reference") or item.get("hermes_tool") or item.get("platform") or item.get("feature") or "item"
            rows.append(
                {
                    "kind": kind,
                    "name": str(label),
                    "area": item.get("area"),
                    "code_status": item.get("code_status"),
                    "mock_status": item.get("mock_status"),
                    "live_status": live_status,
                    "required_env": required_env,
                    "safe_to_smoke": live_status in {"not_required", "ready", "skipped_missing_credentials"},
                    "last_checked_at": checked_at,
                }
            )
    return {
        "object": "aiask.hermes_live_evidence",
        "baseline": parity.get("baseline"),
        "baseline_version": parity.get("baseline_version"),
        "baseline_release_tag": parity.get("baseline_release_tag"),
        "code_status": parity.get("code_status"),
        "core_code_status": parity.get("core_code_status"),
        "mock_status": parity.get("mock_status"),
        "live_status": parity.get("live_status"),
        "strict_status": parity.get("strict_status"),
        "live_unverified_count": parity.get("live_unverified_count"),
        "required_env_groups": sorted(required_env_groups),
        "required_env_names": sorted(required_env_names),
        "items": rows,
        "last_checked_at": checked_at,
    }


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid JSON request body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("JSON request body must be an object")
    return parsed


def _header_token(handler: BaseHTTPRequestHandler, *names: str) -> str | None:
    for name in names:
        value = _extract_bearer_token(handler.headers.get(name))
        if value:
            return value
    return _extract_bearer_token(handler.headers.get("Authorization"))


async def _audited_runtime_tool_call(
    selected: AgentRuntime,
    tool_name: str,
    payload: dict[str, Any],
    *,
    headers: Any | None = None,
    metadata: dict[str, Any] | None = None,
    source_chain: list[str] | None = None,
) -> dict[str, Any]:
    return await audited_runtime_tool_call(
        selected,
        tool_name,
        payload,
        request_context_payload=_request_context_payload,
        headers=headers,
        metadata=metadata,
        source_chain=source_chain,
    )


def _cors_origins() -> set[str]:
    configured = str(os.getenv("AIASK_AGENT_CORS_ORIGINS", "")).strip()
    defaults = {
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
    }
    values = defaults if not configured else set()
    for item in configured.split(","):
        origin = item.strip().rstrip("/")
        if origin and origin != "*":
            values.add(origin)
    return values


def _is_read_only_desktop_tool(name: str) -> bool:
    if name == "agent_tool_catalog":
        return True
    for item in SAFE_TOOL_CATALOG:
        if item.get("name") == name:
            return item.get("side_effect") == "read_only"
    return False


def _metadata_allows_read_only_desktop_call(metadata: dict[str, Any], tool_name: str) -> bool:
    return metadata_is_read_only(metadata, target=tool_name)


def _build_runtime_and_executor() -> tuple[AgentRuntime, IntentExecutor]:
    session_store = AgentSessionStore()
    intent_store = ActionIntentStore()
    registry = build_default_tool_registry(intent_store, session_store=session_store)
    return AgentRuntime(session_store=session_store, tool_registry=registry), IntentExecutor(intent_store)


def _desktop_settings_status_payload_for_runtime(
    runtime: AgentRuntime,
    *,
    endpoint: str | None = None,
    control_authorized: bool = False,
    control_reason: str | None = None,
) -> dict[str, Any]:
    return _desktop_settings_status_payload_builder(
        runtime,
        ai_status_payload=_ai_status_payload_for_runtime,
        endpoint=endpoint,
        control_authorized=control_authorized,
        control_reason=control_reason,
    )


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


def _financial_catalog_payload(runtime: AgentRuntime) -> dict[str, Any]:
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


async def _financial_status_payload(runtime: AgentRuntime) -> dict[str, Any]:
    catalog = _financial_catalog_payload(runtime)
    readiness = await financial_system_readiness(
        runtime,
        full_runtime=None,
        full_mode_enabled=_hermes_full_enabled(),
        control_token_configured=_control_token_configured(),
        ai_status=_ai_status_payload_for_runtime(runtime),
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


async def _financial_query_payload(runtime: AgentRuntime, payload: dict[str, Any], *, tool_caller: ToolCaller | None = None) -> dict[str, Any]:
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
    tool_payload = _tool_payload_with_request_context(params, payload)
    if tool_caller:
        result = await tool_caller(tool_name, tool_payload)
    else:
        tool = runtime.tool_registry.get(tool_name)
        result = await _audited_runtime_tool_call(
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
    context = _request_context_payload(payload, headers=headers)
    return BrokerSyncContext(
        user_id=str(context.get("user_id") or "local"),
        session_id=context.get("session_id"),
        run_id=context.get("run_id"),
        trace_id=context.get("trace_id"),
        source=str(context.get("source") or "desktop"),
    )


def _broker_readiness_payload(runtime: AgentRuntime) -> dict[str, Any]:
    return broker_readiness(runtime.session_store)


def _broker_accounts_payload(runtime: AgentRuntime, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = dict(payload or {})
    return latest_broker_payload(
        runtime.session_store,
        user_id=str(body.get("user_id") or "").strip() or None,
        provider=str(body.get("provider") or "").strip() or None,
    )


async def _broker_sync_payload(
    runtime: AgentRuntime,
    payload: dict[str, Any],
    *,
    headers: Any | None = None,
    tool_caller: ToolCaller | None = None,
) -> dict[str, Any]:
    provider = normalize_provider(payload.get("provider"))
    context = _broker_request_context(payload, headers=headers)

    async def call_financial_query(_path: str, body: dict[str, Any]) -> dict[str, Any]:
        return await _financial_query_payload(runtime, body, tool_caller=tool_caller)

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


def _broker_analytics_payload(runtime: AgentRuntime, payload: dict[str, Any] | None = None) -> dict[str, Any]:
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


async def _financial_intent_payload(runtime: AgentRuntime, payload: dict[str, Any], *, tool_caller: ToolCaller | None = None) -> dict[str, Any]:
    action = _financial_action_map().get(_financial_action_key(str(payload.get("capability_id") or ""), str(payload.get("action_id") or "")))
    if not action:
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": None, "error": "financial manager action is not registered", "error_code": "FINANCIAL_ACTION_NOT_FOUND", "secrets_redacted": True}
    if action.get("mode") == "blocked":
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": {"action": action, "reason": action.get("blocked_reason")}, "error": str(action.get("blocked_reason") or "action is blocked"), "error_code": "FINANCIAL_ACTION_BLOCKED", "secrets_redacted": True}
    if action.get("mode") != "stateful_intent":
        return {"object": "aiask.desktop.financial_manager.intent", "success": False, "data": {"action": action}, "error": "read-only financial actions do not create intents", "error_code": "FINANCIAL_ACTION_READ_ONLY", "secrets_redacted": True}
    params = dict(action.get("default_params") or {})
    params.update(dict(payload.get("params") or {}))
    intent_payload = _tool_payload_with_request_context(
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
        result = await _audited_runtime_tool_call(
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


def create_app(
    *,
    runtime: AgentRuntime | None = None,
    intent_executor: IntentExecutor | None = None,
) -> FastAPI:
    load_project_env()
    if runtime is None:
        runtime, default_executor = _build_runtime_and_executor()
        intent_executor = intent_executor or default_executor
    if intent_executor is None:
        intent_executor = IntentExecutor(ActionIntentStore())
    full_runtime: AgentRuntime | None = None
    quant_store = QuantResearchStore(runtime.session_store.path)

    def _control_snapshot() -> tuple[bool, str | None]:
        expected = (
            str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
            or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
        )
        if not expected:
            return False, "control token is not configured"
        return False, "control token required"

    def _desktop_settings_status_payload() -> dict[str, Any]:
        control_ok, control_reason = _control_snapshot()
        return _desktop_settings_status_payload_for_runtime(
            runtime,
            endpoint=_agent_endpoint(),
            control_authorized=control_ok,
            control_reason=control_reason,
        )

    async def _desktop_data_status_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_status_payload_for_runtime(runtime, arguments)

    async def _desktop_data_sync_plan_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_sync_plan_payload_for_runtime(runtime, arguments)

    def build_full_runtime() -> AgentRuntime:
        nonlocal full_runtime
        if full_runtime is not None:
            return full_runtime
        policy = ToolPolicy(
            toolset=GENERAL_FULL_TOOLSET,
            general_tools_enabled=True,
            workspace_roots=runtime.tool_registry.policy_engine.policy.workspace_roots,
        )
        full_runtime = AgentRuntime(
            model_client=runtime.model_client,
            session_store=runtime.session_store,
            tool_registry=build_default_tool_registry(
                session_store=runtime.session_store,
                policy_engine=ToolPolicyEngine(policy),
            ),
            model=runtime.model,
            max_iterations=runtime.max_iterations,
            model_timeout_seconds=runtime.model_timeout_seconds,
            tool_timeout_seconds=runtime.tool_timeout_seconds,
            retry_attempts=runtime.retry_attempts,
        )
        return full_runtime

    authorizer = RouteAuthorizer(
        runtime=runtime,
        build_full_runtime=build_full_runtime,
        request_user_id_from_payload=_request_user_id_from_payload,
    )
    api_authorized = authorizer.api_authorized
    control_authorized = authorizer.control_authorized
    full_authorized = authorizer.full_authorized
    select_runtime = authorizer.select_runtime
    require_api = authorizer.require_api
    require_control = authorizer.require_control
    require_full = authorizer.require_full
    require_user_scope = authorizer.require_user_scope

    def event_batch_from_payload(payload: dict[str, Any], request: Request) -> list[dict[str, Any]]:
        context = _request_context_payload(payload, headers=request.headers)
        raw_events = payload.get("events")
        events = raw_events if isinstance(raw_events, list) else [payload]
        normalized: list[dict[str, Any]] = []
        for item in list(events or [])[:200]:
            if not isinstance(item, dict):
                continue
            event = {**context, **dict(item)}
            event.setdefault("user_id", context["user_id"])
            event.setdefault("session_id", context["session_id"])
            event.setdefault("run_id", context["run_id"])
            event.setdefault("trace_id", context["trace_id"])
            event.setdefault("source", context["source"])
            normalized.append(event)
        return normalized

    async def audited_tool_call(
        selected: AgentRuntime,
        tool_name: str,
        payload: dict[str, Any],
        *,
        request: Request,
        metadata: dict[str, Any] | None = None,
        source_chain: list[str] | None = None,
    ) -> dict[str, Any]:
        return await _audited_runtime_tool_call(
            selected,
            tool_name,
            dict(payload or {}),
            headers=request.headers,
            metadata=metadata,
            source_chain=source_chain,
        )

    async def audited_desktop_tool_call(
        tool_name: str,
        payload: dict[str, Any],
        *,
        request: Request,
        source_chain: list[str],
    ) -> dict[str, Any]:
        tool = runtime.tool_registry.get(tool_name)
        metadata = dict(getattr(tool, "metadata", {}) or {}) if tool else {}
        return await _audited_runtime_tool_call(
            runtime,
            tool_name,
            dict(payload or {}),
            headers=request.headers,
            metadata=metadata,
            source_chain=source_chain,
        )

    def tool_catalog_payload(selected: AgentRuntime, *, implementation: str | None = None) -> dict[str, Any]:
        return build_tool_catalog_payload(selected, implementation=implementation)

    async def full_tool_call(request: Request, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        full = require_full(request)
        tool = full.tool_registry.get(tool_name)
        result = await _audited_runtime_tool_call(
            full,
            tool_name,
            dict(arguments or {}),
            headers=request.headers,
            metadata=dict(getattr(tool, "metadata", {}) or {}) if tool else {},
            source_chain=["aiask_agent.server", "full_tool_call"],
        )
        if not result.get("success"):
            raise HTTPException(400, detail=result.get("error") or "tool failed")
        return result

    def full_surface_status() -> dict[str, Any]:
        gateway = GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path))
        learning = LearningLoop(session_store=runtime.session_store, state_path=runtime.session_store.path)
        rl = RLAtroposManager(runtime.session_store.path)
        mcp = MCPAggregator()
        skills = SkillStore()
        return {
            "full_scope": "hermes_full_runtime",
            "platform_gateway": gateway.status(),
            "terminal_backends": list_backends(),
            "learning_loop": learning.status(),
            "rl_training": rl.current_config(),
            "tui": tui_status_payload(),
            "providers": ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path)).status(),
            "memory": MemoryProviderManager(path=runtime.session_store.path).status(),
            "acp": ACPManager(mcp=mcp).status(),
            "security": SecurityScanner(policy=runtime.tool_registry.policy_engine.policy).status(),
            "skill_packs": SkillPackManager(skill_store=skills).status(),
        }

    def hermes_readiness_payload() -> dict[str, Any]:
        gateway = GatewayRuntime(messages=GatewayMessageStore(runtime.session_store.path))
        rl = RLAtroposManager(runtime.session_store.path)
        terminal_items = list_backends()
        plugin_manager = NativePluginManager()
        plugins = plugin_manager.list()
        mcp = MCPAggregator()
        provider_registry = ModelProviderRegistry(usage_store=ProviderUsageStore(runtime.session_store.path))
        memory_manager = MemoryProviderManager(path=runtime.session_store.path)
        acp_manager = ACPManager(mcp=mcp)
        security = SecurityScanner(policy=runtime.tool_registry.policy_engine.policy)
        skill_packs = SkillPackManager(skill_store=SkillStore())
        selected_names = build_full_runtime().tool_registry.names() if _hermes_full_enabled() else runtime.tool_registry.names()
        parity = parity_summary(selected_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys())
        dependency = {
            "docker": bool(shutil.which("docker") or importlib.util.find_spec("docker")),
            "ssh": bool(shutil.which("ssh") or importlib.util.find_spec("asyncssh")),
            "apptainer_or_singularity": bool(shutil.which("apptainer") or shutil.which("singularity")),
            "modal": bool(shutil.which("modal") or importlib.util.find_spec("modal") or os.getenv("AIASK_MODAL_TERMINAL_COMMAND")),
            "daytona": bool(shutil.which("daytona") or importlib.util.find_spec("daytona") or os.getenv("AIASK_DAYTONA_TERMINAL_COMMAND")),
            "textual": bool(importlib.util.find_spec("textual")),
            "atroposlib": bool(importlib.util.find_spec("atroposlib")),
            "tinker_atropos": bool(importlib.util.find_spec("tinker_atropos")),
        }
        credentials = {
            "homeassistant": bool(os.getenv("HASS_URL") and os.getenv("HASS_TOKEN")),
            "rl": bool(os.getenv("TINKER_API_KEY") and os.getenv("WANDB_API_KEY")),
            "feishu": bool((os.getenv("FEISHU_APP_ID") and os.getenv("FEISHU_APP_SECRET")) or os.getenv("FEISHU_BOT_WEBHOOK")),
            "discord": bool(os.getenv("DISCORD_BOT_TOKEN")),
            "gateway_webhook": bool(os.getenv("AIASK_GATEWAY_WEBHOOK_URL") or os.getenv("AIASK_GATEWAY_WEBHOOK_SECRET")),
        }
        live_evidence = _parity_live_evidence(parity)
        return {
            "object": "aiask.hermes_readiness",
            "implementation": "aiask_native",
            "embedded_vendor_runtime": False,
            "parity_baseline": parity.get("baseline"),
            "baseline_version": parity.get("baseline_version"),
            "baseline_release_tag": parity.get("baseline_release_tag"),
            "dependencies": dependency,
            "credentials": credentials,
            "live_evidence": live_evidence,
            "live_readiness": live_evidence,
            "terminal_backends": terminal_items,
            "gateway": gateway.status(),
            "mcp": mcp.registration_diagnostics(),
            "providers": provider_registry.status(),
            "memory": memory_manager.status(),
            "acp": acp_manager.readiness(),
            "security": security.status(),
            "skill_packs": skill_packs.status(),
            "rl": rl.readiness(),
            "plugins": {
                "count": len(plugins),
                "enabled_count": sum(1 for item in plugins if item.get("enabled")),
                "readiness": plugin_manager.readiness(),
                "runners": [
                    {
                        "name": item.get("name"),
                        "enabled": item.get("enabled"),
                        "runner": item.get("runner"),
                        "tools": [tool.get("name") for tool in list(item.get("tools") or []) if isinstance(tool, dict)],
                        "commands": [command.get("name") for command in list(item.get("commands") or []) if isinstance(command, dict)],
                    }
                    for item in plugins
                ],
            },
            "feature_mapping": parity.get("feature_mapping", []),
            "missing_features": parity.get("missing_features", []),
            "implemented_features_count": parity.get("implemented_features_count", 0),
            "network": {
                "live_tests_enabled": bool(os.getenv("AIASK_RUN_LIVE_HERMES_TESTS")),
                "proxy_configured": bool(os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")),
            },
            "permissions": {
                "control_token_configured": bool(os.getenv("AIASK_AGENT_CONTROL_TOKEN") or os.getenv("AIASK_LOCAL_CONTROL_TOKEN")),
                "workspace_roots": list(runtime.tool_registry.policy_engine.policy.workspace_roots),
            },
        }

    def ai_status_payload() -> dict[str, Any]:
        return _ai_status_payload_for_runtime(runtime)

    async def ai_smoke_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _ai_smoke_payload_for_runtime(runtime, payload)

    async def ai_models_payload() -> dict[str, Any]:
        return await _ai_models_payload_for_runtime(runtime)

    def ai_config_payload() -> dict[str, Any]:
        return _ai_config_payload_for_runtime(runtime)

    async def ai_config_save_payload(payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _save_ai_config_for_runtime(runtime, payload)

    def workbench_summary_payload(
        *,
        user_id: str | None = None,
        session_limit: int = 8,
        run_limit: int = 8,
    ) -> dict[str, Any]:
        return _workbench_summary_payload(
            runtime,
            intent_store=intent_executor.store,
            user_id=user_id,
            session_limit=session_limit,
            run_limit=run_limit,
        )

    def desktop_runs_payload(
        *,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        return _desktop_runs_payload(runtime, session_id=session_id, status=status, limit=limit)

    def search_payload(
        *,
        query: str = "",
        q: str = "",
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 20,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        return {
            "object": "list",
            "include_archived": bool(include_archived),
            "data": runtime.session_store.search(
                query=query or q,
                session_id=session_id,
                user_id=user_id,
                limit=limit,
                include_archived=bool(include_archived),
            ),
        }

    def run_trace_eval_payload(run_id: str) -> dict[str, Any]:
        return _run_trace_eval_payload(runtime, run_id)

    def artifact_content_payload(artifact_id: str, *, max_bytes: int = 262144) -> dict[str, Any]:
        return _artifact_content_payload(runtime.session_store, artifact_id, max_bytes=max_bytes)

    def hermes_status_payload() -> dict[str, Any]:
        selected_names = build_full_runtime().tool_registry.names() if _hermes_full_enabled() else runtime.tool_registry.names()
        return {
            "object": "aiask.hermes_status",
            "implementation": "aiask_native",
            "baseline": HERMES_BASELINE,
            "baseline_version": HERMES_BASELINE_VERSION,
            "baseline_release_tag": HERMES_RELEASE_TAG,
            "embedded_vendor_runtime": False,
            "full_mode_enabled": _hermes_full_enabled(),
            "full_mode_active": full_runtime is not None,
            "evaluated_toolset": GENERAL_FULL_TOOLSET if _hermes_full_enabled() else runtime.tool_registry.policy_engine.toolset,
            "parity": parity_summary(selected_names, env=dict(os.environ), gateway_adapters=ADAPTERS.keys()),
            **full_surface_status(),
        }

    async def financial_readiness_payload() -> dict[str, Any]:
        return await financial_system_readiness(
            runtime,
            full_runtime=build_full_runtime() if _hermes_full_enabled() else full_runtime,
            full_mode_enabled=_hermes_full_enabled(),
            control_token_configured=bool(
                str(os.getenv("AIASK_AGENT_CONTROL_TOKEN", "")).strip()
                or str(os.getenv("AIASK_LOCAL_CONTROL_TOKEN", "")).strip()
            ),
            ai_status=ai_status_payload(),
        )

    def hermes_toolsets_payload() -> dict[str, Any]:
        return {
            "object": "list",
            "active": "finance_safe",
            "data": [
                {"name": "finance_safe", "implementation": "aiask_native", "default": True},
                {"name": "hermes_full", "implementation": "aiask_native", "enabled": _hermes_full_enabled(), "toolset": GENERAL_FULL_TOOLSET},
            ],
        }

    def hermes_config_payload(full: AgentRuntime) -> dict[str, Any]:
        return {
            "object": "aiask.hermes_config",
            "home": os.getenv("AIASK_AGENT_HOME", ""),
            "toolset": full.tool_registry.policy_engine.toolset,
            "workspace_roots": list(full.tool_registry.policy_engine.policy.workspace_roots),
            "secrets_redacted": True,
        }

    def hermes_sessions_payload(
        *,
        user_id: str | None = None,
        limit: int = 100,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        return {
            "object": "list",
            "implementation": "aiask_native",
            "include_archived": bool(include_archived),
            "data": _session_summary_payload(
                runtime,
                intent_store=intent_executor.store,
                user_id=user_id,
                limit=limit,
                include_archived=include_archived,
            ),
        }

    def hermes_handoffs_payload(
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        include_completed: bool = False,
    ) -> dict[str, Any]:
        return _handoff_queue_payload(
            runtime,
            user_id=user_id,
            session_id=session_id,
            status=status,
            limit=limit,
            include_completed=include_completed,
        )

    def hermes_resume_context_payload(session_id: str) -> dict[str, Any]:
        return _session_resume_context_payload(runtime, session_id, intent_store=intent_executor.store)

    def desktop_settings_status_payload(request: Request | None = None) -> dict[str, Any]:
        control_ok = False
        control_reason = None
        if request is not None:
            control_ok, control_reason = control_authorized(request)
        return _desktop_settings_status_payload_for_runtime(
            runtime,
            endpoint=_agent_endpoint(),
            control_authorized=control_ok,
            control_reason=control_reason,
        )

    async def desktop_data_status_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_status_payload_for_runtime(runtime, arguments)

    async def desktop_data_sync_plan_payload(arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return await _desktop_data_sync_plan_payload_for_runtime(runtime, arguments)

    async def desktop_capabilities_payload(request: Request) -> dict[str, Any]:
        return await _desktop_capabilities_payload_for_runtime(
            runtime,
            request,
            build_full_runtime=build_full_runtime,
            current_full_runtime=lambda: full_runtime,
            full_authorized=full_authorized,
            control_authorized=control_authorized,
            hermes_full_enabled=_hermes_full_enabled,
            hermes_readiness_payload=hermes_readiness_payload,
            quant_store=quant_store,
            ai_status_payload=ai_status_payload,
        )
    async def sse_events(events: list[dict[str, Any]]) -> AsyncIterator[bytes]:
        for raw_event in events:
            event = _normalize_run_event(raw_event)
            if event.get("id") is not None:
                yield f"id: {event['id']}\n".encode("utf-8")
            if event.get("event"):
                yield f"event: {event['event']}\n".encode("utf-8")
            yield b"data: "
            yield _json_dumps(event)
            yield b"\n\n"

    async def chat_completion_sse(result: Any, *, model: str) -> AsyncIterator[bytes]:
        created = int(time.time())
        chunks = [
            {
                "id": result.response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            },
            {
                "id": result.response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": result.content}, "finish_reason": None}],
                "aiask": {"session_id": result.session_id, "run_id": result.run_id},
            },
            {
                "id": result.response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
        ]
        for chunk in chunks:
            yield b"data: "
            yield _json_dumps(chunk)
            yield b"\n\n"
        yield b"data: [DONE]\n\n"

    async def response_sse(result: Any, *, model: str) -> AsyncIterator[bytes]:
        events = [
            {"event": "response.created", "data": {"id": result.response_id, "status": "in_progress", "model": model}},
            {"event": "response.output_text.delta", "data": {"id": result.response_id, "delta": result.content}},
            {"event": "response.completed", "data": {"id": result.response_id, "status": result.status, "run_id": result.run_id}},
        ]
        for event in events:
            yield f"event: {event['event']}\n".encode("utf-8")
            yield b"data: "
            yield _json_dumps(event["data"])
            yield b"\n\n"
        yield b"data: [DONE]\n\n"

    _daemon = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        nonlocal _daemon
        # Start Gateway Daemon if enabled
        if os.getenv("AIASK_GATEWAY_DAEMON_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
            from .gateway_daemon import GatewayDaemon
            try:
                _daemon = GatewayDaemon(
                    runtime=runtime,
                    config=GatewayConfigStore(),
                    router=DeliveryRouter(),
                    messages=GatewayMessageStore(),
                )
                await _daemon.start()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Gateway daemon start failed: %s", exc)
                _daemon = None

        try:
            yield
        finally:
            if _daemon is not None:
                await _daemon.stop()
            if full_runtime is not None:
                await full_runtime.aclose()
            await runtime.aclose()

    app = FastAPI(title="AIASK Agent", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(_cors_origins()),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-AIASK-Agent-Token",
            "X-AIASK-Agent-Control-Token",
            "X-AIASK-Local-Control-Token",
            "X-AIASK-Session-Id",
            "X-AIASK-User-Id",
            "X-AIASK-Run-Id",
            "X-AIASK-Trace-Id",
        ],
    )

    app.include_router(
        create_health_router(
            runtime=runtime,
            build_full_runtime=build_full_runtime,
            hermes_full_enabled=_hermes_full_enabled,
            full_runtime_active=lambda: full_runtime is not None,
            require_api=require_api,
            tool_catalog_payload=tool_catalog_payload,
            desktop_capabilities_payload=desktop_capabilities_payload,
            redact_required_env=_redact_required_env,
            parity_live_evidence=_parity_live_evidence,
        )
    )

    app.include_router(
        create_desktop_data_router(
            require_api=require_api,
            control_authorized=control_authorized,
            desktop_settings_status_payload=desktop_settings_status_payload,
            desktop_data_status_payload=desktop_data_status_payload,
            desktop_data_sync_plan_payload=desktop_data_sync_plan_payload,
        )
    )

    app.include_router(
        create_desktop_user_router(
            runtime=runtime,
            require_api=require_api,
            require_control=require_control,
            require_user_scope=require_user_scope,
            local_profile_payload=local_profile_payload,
            save_local_profile=save_local_profile,
            event_batch_from_payload=event_batch_from_payload,
            request_context_payload=_request_context_payload,
            truthy=_truthy,
        )
    )

    app.include_router(
        create_desktop_finance_router(
            require_api=require_api,
            control_authorized=control_authorized,
            require_user_scope=require_user_scope,
            factor_factory_status=factor_factory_status,
            audited_desktop_tool_call=audited_desktop_tool_call,
            quant_presets=quant_adapter.quant_presets,
            quant_store=quant_store,
            financial_catalog_payload=lambda: _financial_catalog_payload(runtime),
            financial_status_payload=lambda: _financial_status_payload(runtime),
            financial_query_payload=lambda payload, **kwargs: _financial_query_payload(runtime, payload, **kwargs),
            financial_intent_payload=lambda payload, **kwargs: _financial_intent_payload(runtime, payload, **kwargs),
            broker_readiness_payload=lambda: _broker_readiness_payload(runtime),
            broker_sync_payload=lambda payload, **kwargs: _broker_sync_payload(runtime, payload, **kwargs),
            broker_accounts_payload=lambda payload: _broker_accounts_payload(runtime, payload),
            broker_analytics_payload=lambda payload: _broker_analytics_payload(runtime, payload),
            session_store=runtime.session_store,
            normalize_provider=normalize_provider,
        )
    )

    app.include_router(
        create_desktop_workbench_router(
            require_api=require_api,
            workbench_summary_payload=workbench_summary_payload,
        )
    )

    app.include_router(
        create_ai_router(
            require_api=require_api,
            require_control=require_control,
            ai_status_payload=ai_status_payload,
            ai_config_payload=ai_config_payload,
            ai_config_save_payload=ai_config_save_payload,
            ai_smoke_payload=ai_smoke_payload,
            ai_models_payload=ai_models_payload,
        )
    )

    app.include_router(
        create_desktop_runs_router(
            require_api=require_api,
            desktop_runs_payload=desktop_runs_payload,
        )
    )

    app.include_router(
        create_responses_router(
            require_api=require_api,
            select_runtime=select_runtime,
            messages_from_responses_payload=_messages_from_responses_payload,
            responses_payload=_responses_payload,
            response_sse=response_sse,
            chat_completion_payload=_chat_completion_payload,
            chat_completion_sse=chat_completion_sse,
            get_response=runtime.session_store.get_response,
            delete_response=runtime.session_store.delete_response,
            search_payload=search_payload,
        )
    )

    app.include_router(
        create_run_history_router(
            require_api=require_api,
            session_store=runtime.session_store,
            sse_events=sse_events,
            normalize_run_event=_normalize_run_event,
            run_trace_eval_payload=run_trace_eval_payload,
            artifact_content_payload=artifact_content_payload,
        )
    )

    app.include_router(
        create_run_control_router(
            require_api=require_api,
            require_full=require_full,
            session_store=runtime.session_store,
            truthy=_truthy,
        )
    )

    app.include_router(
        create_intents_router(
            require_api=require_api,
            control_authorized=control_authorized,
            intent_store=intent_executor.store,
            intent_executor=intent_executor,
            audited_desktop_tool_call=audited_desktop_tool_call,
        )
    )

    app.include_router(
        create_approvals_router(
            require_full=require_full,
            approval_store_factory=lambda: ApprovalStore(runtime.session_store.path),
        )
    )

    app.include_router(
        create_jobs_router(
            require_api=require_api,
            job_store=runtime.job_store,
            scheduler=runtime.scheduler,
        )
    )

    app.include_router(
        create_tools_router(
            runtime=runtime,
            require_api=require_api,
            require_full=require_full,
            audited_tool_call=audited_tool_call,
            metadata_allows_read_only_desktop_call=_metadata_allows_read_only_desktop_call,
            is_read_only_desktop_tool=_is_read_only_desktop_tool,
        )
    )

    app.include_router(
        create_hermes_status_router(
            require_api=require_api,
            hermes_status_payload=hermes_status_payload,
            hermes_readiness_payload=hermes_readiness_payload,
            financial_readiness_payload=financial_readiness_payload,
        )
    )

    app.include_router(
        create_hermes_router(
            require_api=require_api,
            require_full=require_full,
            hermes_toolsets_payload=hermes_toolsets_payload,
            tool_catalog_payload=tool_catalog_payload,
            hermes_config_payload=hermes_config_payload,
            hermes_sessions_payload=hermes_sessions_payload,
            hermes_handoffs_payload=hermes_handoffs_payload,
            hermes_resume_context_payload=hermes_resume_context_payload,
        )
    )

    app.include_router(
        create_full_controls_router(
            require_full=require_full,
            process_list=lambda **kwargs: ProcessRegistry(runtime.session_store.path).list(**kwargs),
            list_terminal_backends=list_backends,
            terminal_sessions=lambda **kwargs: terminal_backend_sessions(state_path=runtime.session_store.path, **kwargs),
        )
    )

    app.include_router(
        create_plugins_skills_router(
            require_full=require_full,
            full_tool_call=full_tool_call,
            build_full_runtime=build_full_runtime,
            plugin_manager_factory=NativePluginManager,
            plugin_self_test_payload=_plugin_self_test_payload,
            plugin_tools=_plugin_tools,
        )
    )

    def refresh_mcp_runtime() -> None:
        nonlocal full_runtime
        runtime.refresh_tool_registry()
        full_runtime = None

    app.include_router(
        create_mcp_router(
            require_api=require_api,
            require_full=require_full,
            full_tool_call=full_tool_call,
            mcp_aggregator_factory=MCPAggregator,
            refresh_mcp_runtime=refresh_mcp_runtime,
            classify_mcp_error=_classify_mcp_error,
            mcp_action_error_payload=_mcp_action_error_payload,
        )
    )

    app.include_router(
        create_learning_rl_router(
            require_full=require_full,
            learning_loop_factory=lambda: LearningLoop(session_store=runtime.session_store, state_path=runtime.session_store.path),
            rl_manager_factory=lambda: RLAtroposManager(runtime.session_store.path),
        )
    )

    def gateway_message_store() -> GatewayMessageStore:
        return GatewayMessageStore(runtime.session_store.path)

    def gateway_directory_store() -> GatewayChannelDirectoryStore:
        return GatewayChannelDirectoryStore(runtime.session_store.path)

    def gateway_runtime() -> GatewayRuntime:
        return GatewayRuntime(messages=gateway_message_store())

    def gateway_daemon_status_payload() -> dict[str, Any]:
        from .gateway_daemon import daemon_enabled

        if _daemon is None:
            return {"object": "gateway.daemon", "data": {"enabled": daemon_enabled(), "running": False, "listeners": {}}}
        return {"object": "gateway.daemon", "data": _daemon.status()}

    app.include_router(
        create_gateway_router(
            require_api=require_api,
            require_full=require_full,
            gateway_runtime_factory=gateway_runtime,
            message_store_factory=gateway_message_store,
            directory_store_factory=gateway_directory_store,
            config_store_factory=GatewayConfigStore,
            delivery_router_factory=DeliveryRouter,
            adapter_for=adapter_for,
            normalize_platform=normalize_platform,
            gateway_daemon_status_payload=gateway_daemon_status_payload,
        )
    )

    def connector_manager_factory(*, include_daemon: bool = False) -> Any:
        from .connector_manager import ConnectorManager

        return ConnectorManager(
            mcp_aggregator=getattr(runtime, "_mcp_aggregator", None),
            plugin_manager=getattr(runtime, "_plugin_manager", None),
            gateway_config=GatewayConfigStore(),
            gateway_daemon=getattr(app.state, "_daemon", None) if include_daemon and hasattr(app, "state") else None,
        )

    app.include_router(
        create_connectors_router(
            require_full=require_full,
            connector_manager_factory=connector_manager_factory,
        )
    )

    app.include_router(
        create_webhooks_router(
            require_full=require_full,
            full_tool_call=full_tool_call,
            webhook_store_factory=lambda: WebhookStore(runtime.session_store.path),
        )
    )

    return app


def build_server(
    host: str = "127.0.0.1",
    port: int = 8767,
    *,
    runtime: AgentRuntime | None = None,
    intent_executor: IntentExecutor | None = None,
) -> ThreadingHTTPServer:
    from .fallback_server import build_server as build_fallback_server

    return build_fallback_server(
        host=host,
        port=port,
        runtime=runtime,
        intent_executor=intent_executor,
    )

def main(argv: list[str] | None = None) -> None:
    from .server_cli import main as server_cli_main

    server_cli_main(argv)


if __name__ == "__main__":
    main()
