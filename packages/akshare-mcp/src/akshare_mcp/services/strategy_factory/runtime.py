"""策略工厂运行时共享工具。"""

from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any


def get_strategy_factory_package():
    """返回策略工厂包对象，供阶段模块读取包级别可 monkeypatch 的导出。"""
    return import_module(__package__)


async def _call_optional_async(target: Any, method_name: str, *args, default=None, **kwargs):
    method = getattr(target, method_name, None)
    if not callable(method):
        return default
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result
