from __future__ import annotations

import inspect
from collections.abc import Callable
from importlib import import_module
from typing import Any


class _CaptureMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Callable[..., Any]:
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            fn = args[0]
            self.tools[fn.__name__] = fn
            return fn

        def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = fn
            return fn

        return _decorator


def load_registered_tool(module_name: str, function_name: str) -> Callable[..., Any]:
    module = import_module(module_name)
    register = getattr(module, "register", None)
    if not callable(register):
        raise RuntimeError(f"{module_name} does not expose register(mcp)")
    probe = _CaptureMCP()
    register(probe)
    fn = probe.tools.get(function_name)
    if not callable(fn):
        raise RuntimeError(f"{module_name} did not register {function_name}")
    return fn


def filter_arguments(fn: Callable[..., Any], arguments: dict[str, Any]) -> dict[str, Any]:
    signature = inspect.signature(fn)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return dict(arguments)
    return {key: value for key, value in arguments.items() if key in signature.parameters}


async def call_function(fn: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    result = fn(**filter_arguments(fn, arguments))
    if inspect.isawaitable(result):
        return await result
    return result


async def analyze_stock(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = dict(arguments or {})
    if payload.get("symbol") and not payload.get("code"):
        payload["code"] = payload["symbol"]
    fn = load_registered_tool("akshare_mcp.tools.ai_workflows", "analyze_stock_workflow")
    return await call_function(fn, payload)


async def stock_live_quote(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = dict(arguments or {})
    if payload.get("symbol") and not payload.get("code"):
        payload["code"] = payload["symbol"]
    if payload.get("stock_code") and not payload.get("code"):
        payload["code"] = payload["stock_code"]
    if payload.get("ticker") and not payload.get("code"):
        payload["code"] = payload["ticker"]
    fn = getattr(import_module("akshare_mcp.tools.market.quote"), "get_realtime_quote")
    return await call_function(fn, payload)


async def stock_news_digest(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = dict(arguments or {})
    if payload.get("symbol") and not payload.get("code"):
        payload["code"] = payload["symbol"]
    if payload.get("stock_code") and not payload.get("code"):
        payload["code"] = payload["stock_code"]
    if payload.get("ticker") and not payload.get("code"):
        payload["code"] = payload["ticker"]
    module = import_module("akshare_mcp.tools.news.news_feed")
    code = str(payload.get("code") or "").strip()
    fn = getattr(module, "get_stock_news" if code else "get_market_news")
    return await call_function(fn, payload)


async def governance_check(arguments: dict[str, Any]) -> dict[str, Any]:
    module = import_module("akshare_mcp.tools.governance_workflow")
    fn = getattr(module, "governance_check_workflow")
    return await call_function(fn, dict(arguments or {}))


async def data_validation(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.adapter_tools", "data_validation")
    return await call_function(fn, dict(arguments or {}))


async def market_temperature_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.market_temperature", "get_market_temperature_snapshot")
    return await call_function(fn, dict(arguments or {}))


async def market_temperature_cache_readiness(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.db_freshness", "check_market_temperature_cache_readiness")
    return await call_function(fn, dict(arguments or {}))


async def market_temperature_cache_history(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.market_temperature", "list_market_temperature_snapshot_cache")
    return await call_function(fn, dict(arguments or {}))


async def market_temperature_industry_history(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.market_temperature", "list_market_temperature_industry_history")
    return await call_function(fn, dict(arguments or {}))


async def market_temperature_industry_constituents(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.market_temperature", "list_market_temperature_industry_constituents")
    return await call_function(fn, dict(arguments or {}))


async def market_temperature_forward_validation(arguments: dict[str, Any]) -> dict[str, Any]:
    fn = load_registered_tool("akshare_mcp.tools.market_temperature", "get_market_temperature_forward_validation")
    return await call_function(fn, dict(arguments or {}))
