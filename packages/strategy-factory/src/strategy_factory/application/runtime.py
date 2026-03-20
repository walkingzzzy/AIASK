"""策略工厂运行时共享工具。"""

from __future__ import annotations

import asyncio
import inspect
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from .legacy_bridge import load_legacy_module

_local_factory_scheduler = None


def _get_local_strategy_factory_scheduler():
    global _local_factory_scheduler
    if _local_factory_scheduler is None:
        from .factory_scheduler import StrategyFactoryScheduler

        _local_factory_scheduler = StrategyFactoryScheduler()
    return _local_factory_scheduler


@lru_cache(maxsize=1)
def _build_local_runtime_view():
    from .factor_research import FactorResearchBuilder
    from .opportunity import MarketOpportunityScanner
    from .panels import _build_strategy_panels, _run_risk_report, _run_validation_report
    from .quality_gates import build_legacy_gate_report
    from .submission_gate import run_submission_quality_gate
    from .utils import _extract_event_context

    return SimpleNamespace(
        asyncio=asyncio,
        MarketOpportunityScanner=MarketOpportunityScanner,
        FactorResearchBuilder=FactorResearchBuilder,
        _build_strategy_panels=_build_strategy_panels,
        _run_validation_report=_run_validation_report,
        _run_risk_report=_run_risk_report,
        build_legacy_gate_report=build_legacy_gate_report,
        get_strategy_factory_scheduler=_get_local_strategy_factory_scheduler,
        run_submission_quality_gate=run_submission_quality_gate,
        _extract_event_context=_extract_event_context,
    )


def get_strategy_factory_package():
    """返回策略工厂运行时视图，优先保留旧根包 patch surface。"""
    package = load_legacy_module("akshare_mcp.services.strategy_factory")
    if package is not None:
        return package
    return _build_local_runtime_view()


async def _call_optional_async(target: Any, method_name: str, *args, default=None, **kwargs):
    method = getattr(target, method_name, None)
    if not callable(method):
        return default
    result = method(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


__all__ = ["get_strategy_factory_package", "_call_optional_async"]
