"""策略工厂运行时共享工具。"""

from __future__ import annotations

import asyncio
import inspect
from functools import lru_cache
from importlib import import_module
from types import SimpleNamespace
from typing import Any

from ..infrastructure.mcp_services import get_backtest_engine_class

_local_factory_scheduler = None


def _load_local_symbol(module_name: str, attr_name: str) -> Any:
    module = import_module(module_name, __package__)
    return getattr(module, attr_name)


def _get_local_strategy_factory_scheduler():
    global _local_factory_scheduler
    if _local_factory_scheduler is None:
        scheduler_cls = _load_local_symbol(".factory_scheduler", "StrategyFactoryScheduler")
        _local_factory_scheduler = scheduler_cls()
    return _local_factory_scheduler


@lru_cache(maxsize=1)
def _build_local_runtime_view():
    StrategySpawner = _load_local_symbol(".research.spawner", "StrategySpawner")
    BacktestFilter = _load_local_symbol(".backtest_filter", "BacktestFilter")
    DataCollector = _load_local_symbol(".collect", "DataCollector")
    Deduplicator = _load_local_symbol(".deduplicator", "Deduplicator")
    EliminationChecker = _load_local_symbol(".elimination", "EliminationChecker")
    LocalEventDrivenResearchEngine = _load_local_symbol(".event_engine", "LocalEventDrivenResearchEngine")
    get_local_event_engine = _load_local_symbol(".event_engine", "get_local_event_engine")
    FactorResearchBuilder = _load_local_symbol(".research.factor_research", "FactorResearchBuilder")
    StrategyFactoryScheduler = _load_local_symbol(".factory_scheduler", "StrategyFactoryScheduler")
    MarketOpportunityScanner = _load_local_symbol(".research.opportunity", "MarketOpportunityScanner")
    _build_strategy_panels = _load_local_symbol(".panels", "_build_strategy_panels")
    _run_risk_report = _load_local_symbol(".panels", "_run_risk_report")
    _run_validation_report = _load_local_symbol(".panels", "_run_validation_report")
    build_legacy_gate_report = _load_local_symbol(".quality_gates", "build_legacy_gate_report")
    finalize_gate_report = _load_local_symbol(".quality_gates", "finalize_gate_report")
    run_gated_filter = _load_local_symbol(".quality_gates", "run_gated_filter")
    run_gated_submission_pipeline = _load_local_symbol(".quality_gates", "run_gated_submission_pipeline")
    run_submission_quality_gate = _load_local_symbol(".submission_gate", "run_submission_quality_gate")
    StrategySubmitter = _load_local_symbol(".submitter", "StrategySubmitter")
    _extract_event_context = _load_local_symbol(".utils", "_extract_event_context")

    BacktestEngine = get_backtest_engine_class()

    return SimpleNamespace(
        asyncio=asyncio,
        BacktestEngine=BacktestEngine,
        DataCollector=DataCollector,
        MarketOpportunityScanner=MarketOpportunityScanner,
        StrategySpawner=StrategySpawner,
        BacktestFilter=BacktestFilter,
        Deduplicator=Deduplicator,
        StrategySubmitter=StrategySubmitter,
        EliminationChecker=EliminationChecker,
        LocalEventDrivenResearchEngine=LocalEventDrivenResearchEngine,
        get_local_event_engine=get_local_event_engine,
        FactorResearchBuilder=FactorResearchBuilder,
        StrategyFactoryScheduler=StrategyFactoryScheduler,
        _build_strategy_panels=_build_strategy_panels,
        _run_validation_report=_run_validation_report,
        _run_risk_report=_run_risk_report,
        run_gated_filter=run_gated_filter,
        run_gated_submission_pipeline=run_gated_submission_pipeline,
        build_legacy_gate_report=build_legacy_gate_report,
        finalize_gate_report=finalize_gate_report,
        get_strategy_factory_scheduler=_get_local_strategy_factory_scheduler,
        run_submission_quality_gate=run_submission_quality_gate,
        _extract_event_context=_extract_event_context,
    )


def get_strategy_factory_package():
    """返回本地策略工厂运行时视图。"""
    return _build_local_runtime_view()


async def _call_optional_async(target: Any, method_name: str, *args, default=None, **kwargs):
    method = getattr(target, method_name, None)
    if not callable(method):
        return default
    try:
        result = method(*args, **kwargs)
    except StopIteration:
        return default
    except StopAsyncIteration:
        return default
    if inspect.isawaitable(result):
        try:
            return await result
        except StopIteration:
            return default
        except StopAsyncIteration:
            return default
    return result


__all__ = [
    "get_strategy_factory_package",
    "_call_optional_async",
]
