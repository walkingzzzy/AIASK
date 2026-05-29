"""Tests for finance MCP servers — protocol compliance."""

from __future__ import annotations

import json
from typing import Any

import pytest


def _call_jsonrpc(handler, method: str, params: dict | None = None, req_id: int = 1) -> dict[str, Any]:
    request = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        request["params"] = params
    return handler(request)


def _assert_resource_prompt_capabilities(result: dict[str, Any]) -> None:
    capabilities = result["result"]["capabilities"]
    assert capabilities["tools"]["listChanged"] is False
    assert capabilities["resources"]["listChanged"] is False
    assert capabilities["prompts"]["listChanged"] is False


def _assert_empty_resources_and_prompts(handler) -> None:
    resources = _call_jsonrpc(handler, "resources/list")
    prompts = _call_jsonrpc(handler, "prompts/list")
    assert resources["result"]["resources"] == []
    assert prompts["result"]["prompts"] == []


class TestTongdaxinProtocol:
    def test_initialize(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "initialize")
        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert result["result"]["protocolVersion"] == "2024-11-05"
        assert result["result"]["serverInfo"]["name"] == "aiask-finance-tongdaxin"
        _assert_resource_prompt_capabilities(result)

    def test_tools_list(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "tools/list")
        tools = result["result"]["tools"]
        assert len(tools) >= 6
        tool_names = [t["name"] for t in tools]
        assert "tdx_realtime_quote" in tool_names
        assert "tdx_kline_history" in tool_names
        assert "tdx_minute_data" in tool_names
        assert "tdx_tick_data" in tool_names
        assert "tdx_finance_info" in tool_names
        assert "tdx_market_snapshot" in tool_names

    def test_resources_and_prompts_list(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        _assert_empty_resources_and_prompts(_handle_jsonrpc)

    def test_tools_call_missing_code(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        result = _call_jsonrpc(
            _handle_jsonrpc,
            "tools/call",
            {"name": "tdx_realtime_quote", "arguments": {}},
        )
        content = json.loads(result["result"]["content"][0]["text"])
        assert content["success"] is False
        assert "codes" in content["error"].lower() or "required" in content["error"].lower()

    def test_tools_call_unknown_tool(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        result = _call_jsonrpc(
            _handle_jsonrpc,
            "tools/call",
            {"name": "nonexistent_tool", "arguments": {}},
        )
        assert result["result"]["isError"] is True

    def test_unknown_method(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "unknown/method")
        assert "error" in result
        assert result["error"]["code"] == -32601

    def test_notification_returns_none(self):
        from aiask_finance_mcp.tongdaxin.server import _handle_jsonrpc

        result = _handle_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert result is None


class TestTonghuashunProtocol:
    def test_initialize(self):
        from aiask_finance_mcp.tonghuashun.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "initialize")
        assert result["result"]["serverInfo"]["name"] == "aiask-finance-tonghuashun"
        _assert_resource_prompt_capabilities(result)

    def test_tools_list(self):
        from aiask_finance_mcp.tonghuashun.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "tools/list")
        tools = result["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "ths_query_balance" in tool_names
        assert "ths_query_position" in tool_names
        assert "ths_place_order" in tool_names
        assert "ths_cancel_order" in tool_names

    def test_resources_and_prompts_list(self):
        from aiask_finance_mcp.tonghuashun.server import _handle_jsonrpc

        _assert_empty_resources_and_prompts(_handle_jsonrpc)

    def test_place_order_validation(self):
        from aiask_finance_mcp.tonghuashun.server import _handle_jsonrpc

        # Missing required fields
        result = _call_jsonrpc(
            _handle_jsonrpc,
            "tools/call",
            {"name": "ths_place_order", "arguments": {"code": "600519"}},
        )
        content = json.loads(result["result"]["content"][0]["text"])
        assert content["success"] is False

    def test_cancel_order_validation(self, monkeypatch):
        from aiask_finance_mcp.tonghuashun.server import _handle_jsonrpc

        monkeypatch.setenv("AIASK_FINANCE_THS_BROKER_TOKEN", "test-token")
        result = _call_jsonrpc(
            _handle_jsonrpc,
            "tools/call",
            {"name": "ths_cancel_order", "arguments": {"broker_token": "test-token"}},
        )
        content = json.loads(result["result"]["content"][0]["text"])
        assert content["success"] is False
        assert "entrust_no" in content["error"].lower()


class TestEastmoneyProtocol:
    def test_initialize(self):
        from aiask_finance_mcp.eastmoney.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "initialize")
        assert result["result"]["serverInfo"]["name"] == "aiask-finance-eastmoney"
        _assert_resource_prompt_capabilities(result)

    def test_tools_list(self):
        from aiask_finance_mcp.eastmoney.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "tools/list")
        tools = result["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "em_realtime_quote" in tool_names
        assert "em_kline_history" in tool_names
        assert "em_fund_info" in tool_names
        assert "em_news_flow" in tool_names
        assert "em_dragon_tiger_list" in tool_names

    def test_resources_and_prompts_list(self):
        from aiask_finance_mcp.eastmoney.server import _handle_jsonrpc

        _assert_empty_resources_and_prompts(_handle_jsonrpc)

    def test_kline_missing_code(self):
        from aiask_finance_mcp.eastmoney.server import _handle_jsonrpc

        result = _call_jsonrpc(
            _handle_jsonrpc,
            "tools/call",
            {"name": "em_kline_history", "arguments": {}},
        )
        content = json.loads(result["result"]["content"][0]["text"])
        assert content["success"] is False


class TestQmtProtocol:
    def test_initialize(self):
        from aiask_finance_mcp.qmt.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "initialize")
        assert result["result"]["serverInfo"]["name"] == "aiask-finance-qmt"
        _assert_resource_prompt_capabilities(result)

    def test_tools_list(self):
        from aiask_finance_mcp.qmt.server import _handle_jsonrpc

        result = _call_jsonrpc(_handle_jsonrpc, "tools/list")
        tools = result["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "qmt_query_account" in tool_names
        assert "qmt_place_order" in tool_names
        assert "qmt_cancel_order" in tool_names

    def test_resources_and_prompts_list(self):
        from aiask_finance_mcp.qmt.server import _handle_jsonrpc

        _assert_empty_resources_and_prompts(_handle_jsonrpc)

    def test_place_order_validation(self):
        from aiask_finance_mcp.qmt.server import _handle_jsonrpc

        result = _call_jsonrpc(
            _handle_jsonrpc,
            "tools/call",
            {"name": "qmt_place_order", "arguments": {}},
        )
        content = json.loads(result["result"]["content"][0]["text"])
        assert content["success"] is False
