"""Runtime MCP manager contract tests.

These tests execute against the real FastMCP registration layer so we can catch:
- missing imports that only fail after tool registration
- help handlers that crash at runtime
- schema regressions where top-level structured fields disappear
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "strategy-factory" / "src"))

from akshare_mcp.server import mcp


def _manager_names() -> list[str]:
    return sorted(name for name in mcp._tool_manager._tools if name.endswith("_manager"))


EXPECTED_SCHEMA_FIELDS: dict[str, set[str]] = {
    "alerts_manager": {"user_id", "status", "code", "indicator", "condition", "value", "alert_id"},
    "data_sync_manager": {"codes", "task_id", "task_type", "period", "status", "schedule", "force", "limit", "priority"},
    "decision_manager": {"code", "codes", "weights", "investment_style", "criteria", "limit", "portfolio_id"},
    "live_trading_manager": {"code", "symbol", "order_id", "status", "limit", "symbols", "confirm_token", "dry_run"},
    "paper_trading_manager": {"user_id", "account_id", "code", "price", "shares", "quantity", "order_id", "trade_type"},
    "portfolio_manager": {"user_id", "portfolio_id", "code", "shares", "cost_price", "name", "description", "initial_capital"},
    "performance_manager": {"portfolio_id", "backtest_id", "artifact_id", "benchmark", "lookback_days"},
    "research_manager": {"code", "limit"},
    "risk_manager": {"portfolio_id", "codes", "weights", "scenario", "scenarios", "confidence", "method", "lookback_days"},
    "vector_search_manager": {"code", "query", "top_n", "days", "similarity_type", "doc_types", "limit", "search_backend"},
    "watchlist_manager": {"user_id", "group_id", "code", "codes", "name", "note", "color", "limit"},
    "user_manager": {"user_id", "actor_user_id", "preferences", "limit", "allow_cross_user"},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", _manager_names())
async def test_all_managers_help_should_work_at_runtime(tool_name: str):
    tool = mcp._tool_manager._tools[tool_name]
    try:
        result = await tool.run({"action": "help"})
    except ToolError as exc:  # pragma: no cover - explicit failure signal
        pytest.fail(f"{tool_name} help raised ToolError: {exc}")
    except Exception as exc:  # pragma: no cover - explicit failure signal
        pytest.fail(f"{tool_name} help raised {type(exc).__name__}: {exc}")

    if isinstance(result, str):
        result = json.loads(result)

    assert isinstance(result, dict), f"{tool_name} should return a dict"
    assert result.get("success") is not False, f"{tool_name} help returned failure: {result}"


@pytest.mark.parametrize("tool_name,expected_fields", EXPECTED_SCHEMA_FIELDS.items())
def test_selected_managers_should_expose_structured_top_level_fields(tool_name: str, expected_fields: set[str]):
    tool = mcp._tool_manager._tools[tool_name]
    schema = getattr(tool, "parameters", None) or getattr(tool, "inputSchema", None) or {}
    properties = set((schema.get("properties") or {}).keys())
    missing = expected_fields - properties
    assert not missing, f"{tool_name} missing structured schema fields: {sorted(missing)}"
