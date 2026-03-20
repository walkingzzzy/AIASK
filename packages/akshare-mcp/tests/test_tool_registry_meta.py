from pathlib import Path

from akshare_mcp.tool_registry import build_tool_registry, summarize_tool_registry


def test_tool_registry_should_export_runtime_tools():
    rows = build_tool_registry()
    summary = summarize_tool_registry(rows)

    assert summary["tool_count"] == len(rows)
    assert len(rows) >= 100
    assert summary["missing_implementation_path_count"] == 0


def test_tool_registry_should_unwrap_decorated_implementation_path():
    rows = build_tool_registry()
    row_map = {row["name"]: row for row in rows}

    kline = row_map["get_kline"]
    assert kline["unwrap_applied"] is True
    assert Path(kline["wrapper_path"]).name == "cache_manager.py"
    assert Path(kline["implementation_path"]).name == "kline.py"
    assert kline["implementation_path"].endswith("tools/market/kline.py")
    assert "stock_code" in (kline["signature"] or "")


def test_tool_registry_should_keep_server_wrapped_tools_resolvable():
    rows = build_tool_registry()
    row_map = {row["name"]: row for row in rows}

    market_blocks = row_map["get_market_blocks"]
    assert market_blocks["implementation_path"] is not None
    assert Path(market_blocks["implementation_path"]).name == "server.py"
    assert market_blocks["category"] == "sector"
