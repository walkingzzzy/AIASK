"""Contract tests for full / worker / tool-only startup registration boundaries."""

from __future__ import annotations

import importlib
import importlib.util
import os

import pytest


_FULL_ONLY_MODULES = {
    "akshare_mcp.tools.vector",
    "akshare_mcp.tools.skills",
    "akshare_mcp.tools.quant",
    "akshare_mcp.tools.sentiment",
    "akshare_mcp.tools.data_sync",
    "akshare_mcp.tools.factor_profile",
}

_FULL_ONLY_MANAGER_MODULES = {
    "akshare_mcp.tools.managers.vector_search_manager",
    "akshare_mcp.tools.managers.quant_manager",
    "akshare_mcp.tools.managers.sentiment_manager",
    "akshare_mcp.tools.managers.data_sync_manager",
}

_FULL_ONLY_TOOL_NAMES = {
    "vector_search_manager",
    "quant_manager",
    "sentiment_manager",
    "data_sync_manager",
    "search_by_kline",
    "list_skills",
    "calculate_fear_greed_index",
    "get_factor_library",
    "get_sync_status",
    "get_factor_profile",
}


def _resolve_import_name(name: str, package: str | None) -> str:
    if package and name.startswith("."):
        return importlib.util.resolve_name(name, package)
    return name


def _reload_server(monkeypatch, profile: str):
    import akshare_mcp.server as server_mod
    import akshare_mcp.tools.managers as managers_mod

    captured_imports: list[str] = []
    original_import_module = importlib.import_module

    def _tracking_import(name: str, package: str | None = None):
        captured_imports.append(_resolve_import_name(name, package))
        return original_import_module(name, package)

    monkeypatch.setenv("AKSHARE_MCP_STARTUP_PROFILE", profile)
    monkeypatch.setattr(importlib, "import_module", _tracking_import)
    monkeypatch.setattr(managers_mod, "import_module", _tracking_import)

    reloaded = importlib.reload(server_mod)
    tool_names = set(getattr(reloaded.mcp._tool_manager, "_tools", {}).keys())
    return reloaded, tool_names, captured_imports


@pytest.fixture(autouse=True)
def _restore_server_profile():
    previous = os.environ.get("AKSHARE_MCP_STARTUP_PROFILE")
    yield
    if previous is None:
        os.environ.pop("AKSHARE_MCP_STARTUP_PROFILE", None)
    else:
        os.environ["AKSHARE_MCP_STARTUP_PROFILE"] = previous

    import akshare_mcp.server as server_mod

    importlib.reload(server_mod)


def test_tool_only_profile_should_skip_full_only_tools_and_managers(monkeypatch):
    _, tool_names, captured_imports = _reload_server(monkeypatch, "tool-only")

    assert "alerts_manager" in tool_names
    for tool_name in _FULL_ONLY_TOOL_NAMES:
        assert tool_name not in tool_names

    assert _FULL_ONLY_MODULES.isdisjoint(captured_imports)
    assert _FULL_ONLY_MANAGER_MODULES.isdisjoint(captured_imports)


def test_full_profile_should_register_full_toolset(monkeypatch):
    _, tool_names, captured_imports = _reload_server(monkeypatch, "full")

    for tool_name in _FULL_ONLY_TOOL_NAMES:
        assert tool_name in tool_names

    assert any(name in _FULL_ONLY_MODULES for name in captured_imports)
    assert any(name in _FULL_ONLY_MANAGER_MODULES for name in captured_imports)


def test_worker_profile_should_register_full_toolset_without_downgrading_to_tool_only(monkeypatch):
    _, tool_names, captured_imports = _reload_server(monkeypatch, "worker")

    for tool_name in _FULL_ONLY_TOOL_NAMES:
        assert tool_name in tool_names

    assert any(name in _FULL_ONLY_MODULES for name in captured_imports)
    assert any(name in _FULL_ONLY_MANAGER_MODULES for name in captured_imports)
