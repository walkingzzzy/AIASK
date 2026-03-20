"""Legacy patch-surface bridge helpers.

These helpers keep the old ``akshare_mcp.services.strategy_factory.*`` patch
surface working while letting migrated modules prefer local implementations.
"""

from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any


def load_legacy_module(module_name: str):
    try:
        return import_module(module_name)
    except Exception:
        return None


def get_compat_value(module_name: str, name: str, default: Any) -> Any:
    module = load_legacy_module(module_name)
    if module is None:
        return default
    return getattr(module, name, default)


def get_compat_symbol(
    module_name: str,
    name: str,
    fallback: Any,
    *,
    exclude: Any | None = None,
) -> Any:
    module = load_legacy_module(module_name)
    if module is None:
        return fallback
    compat = getattr(module, name, None)
    if compat is None:
        return fallback
    if exclude is not None and compat is exclude:
        return fallback
    return compat


def call_compat(
    module_name: str,
    name: str,
    fallback: Any,
    *args,
    exclude: Any | None = None,
    **kwargs,
):
    target = get_compat_symbol(module_name, name, fallback, exclude=exclude)
    return target(*args, **kwargs)


async def call_compat_async(
    module_name: str,
    name: str,
    fallback: Any,
    *args,
    exclude: Any | None = None,
    **kwargs,
):
    result = call_compat(module_name, name, fallback, *args, exclude=exclude, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


__all__ = [
    "load_legacy_module",
    "get_compat_value",
    "get_compat_symbol",
    "call_compat",
    "call_compat_async",
]
