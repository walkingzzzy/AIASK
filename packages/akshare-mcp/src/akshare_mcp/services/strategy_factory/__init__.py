"""策略工厂兼容导出层（已废弃，请迁移至 ``strategy_factory`` 独立包）。

真正实现已迁至同级独立包 ``packages/strategy-factory``。
这里继续保留旧导入路径，目的是兼容历史调用方与少量 patch 测试面。
``strategy_factory`` 主源码已经移除 legacy runtime / facade accessor；
本模块不再对应任何隐藏运行时分流，只是旧 import 路径的兼容导出。

.. deprecated::
   Direct imports from ``akshare_mcp.services.strategy_factory`` are deprecated.
   Use ``from strategy_factory.application import ...`` or
   ``from strategy_factory.api.facade import ...`` instead.
   This compatibility export layer will be removed in a future release.
"""

from __future__ import annotations

import asyncio
import warnings
from typing import Optional

warnings.warn(
    "Importing from akshare_mcp.services.strategy_factory is deprecated. "
    "Use the strategy_factory package directly (strategy_factory.application / strategy_factory.api.facade).",
    DeprecationWarning,
    stacklevel=2,
)

from .backtest_filter import BacktestFilter
from .collect import DataCollector
from .constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_MAX_RESEARCH_TASKS,
    AUTONOMY_STARTUP_DELAY_SEC,
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    BACKTEST_DEFAULT_THRESHOLDS,
    BACKTEST_TYPE_THRESHOLDS,
    CATEGORY_MINIMUMS,
    DEPRECATION_THRESHOLDS,
    FACTORY_DAILY_RUN_TIME,
    FACTORY_ERROR_BACKOFF_SEC,
    FACTORY_MARKET_HOURS_INTERVAL_SEC,
    FACTORY_MAX_DAILY_RUNS,
    FACTORY_OFF_HOURS_INTERVAL_SEC,
    FACTORY_SCHEDULE_MODE,
    PIPELINE_MODE,
    PIPELINE_STAGE_MAX_TOKENS,
    PIPELINE_STAGE_TEMPERATURE,
    PIPELINE_STAGE_TIMEOUT_SEC,
    PROMOTION_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
    QUALITY_GATE_THRESHOLDS,
    REPRESENTATIVE_STOCKS,
    RISK_REPORT_THRESHOLDS,
)
from .event_engine import LocalEventDrivenResearchEngine, get_local_event_engine
from .elimination import EliminationChecker
from .factor_research import FactorResearchBuilder
from .factory_scheduler import StrategyFactoryScheduler
from .opportunity import MarketOpportunityScanner
from .spawner import StrategySpawner
from .submitter import StrategySubmitter
from .naming import _auto_name
from .panels import _build_strategy_panels, _run_risk_report, _run_validation_report
from .quality_gates import (
    build_legacy_gate_report,
    finalize_gate_report,
    run_gated_filter,
    run_gated_submission_pipeline,
)
from .runtime import _call_optional_async
from .targets import (
    _extract_target_codes_from_payload,
    _normalize_target_codes,
    _resolve_strategy_sample_codes,
    _update_strategy_status,
)
from .utils import (
    get_strategy_factory_package,
)

# 旧导入路径仍保留单例语义，避免历史启动/测试代码行为变化。
_factory_scheduler: Optional[StrategyFactoryScheduler] = None


async def run_submission_quality_gate(*args, **kwargs):
    from .submission_gate import run_submission_quality_gate as _run_submission_quality_gate

    return await _run_submission_quality_gate(*args, **kwargs)


def get_strategy_factory_scheduler() -> StrategyFactoryScheduler:
    global _factory_scheduler
    if _factory_scheduler is None:
        _factory_scheduler = StrategyFactoryScheduler()
    return _factory_scheduler


def __getattr__(name: str):
    if name == "Deduplicator":
        from .deduplicator import Deduplicator as _Deduplicator

        return _Deduplicator
    raise AttributeError(name)


__all__ = [
    "REPRESENTATIVE_STOCKS",
    "CATEGORY_MINIMUMS",
    "BACKTEST_DEFAULT_THRESHOLDS",
    "BACKTEST_AI_PROTOTYPE_THRESHOLDS",
    "PROVISIONAL_PASS_THRESHOLDS",
    "QUALITY_GATE_THRESHOLDS",
    "RISK_REPORT_THRESHOLDS",
    "PROMOTION_THRESHOLDS",
    "DEPRECATION_THRESHOLDS",
    "AUTONOMY_MAX_RESEARCH_TASKS",
    "AUTONOMY_CANDIDATES_PER_TASK",
    "AUTONOMY_STARTUP_DELAY_SEC",
    "BACKTEST_TYPE_THRESHOLDS",
    "FACTORY_SCHEDULE_MODE",
    "FACTORY_MARKET_HOURS_INTERVAL_SEC",
    "FACTORY_OFF_HOURS_INTERVAL_SEC",
    "FACTORY_MAX_DAILY_RUNS",
    "FACTORY_ERROR_BACKOFF_SEC",
    "FACTORY_DAILY_RUN_TIME",
    "PIPELINE_MODE",
    "PIPELINE_STAGE_MAX_TOKENS",
    "PIPELINE_STAGE_TEMPERATURE",
    "PIPELINE_STAGE_TIMEOUT_SEC",
    "_call_optional_async",
    "_auto_name",
    "_update_strategy_status",
    "_normalize_target_codes",
    "_extract_target_codes_from_payload",
    "_resolve_strategy_sample_codes",
    "_build_strategy_panels",
    "_run_validation_report",
    "_run_risk_report",
    "run_gated_filter",
    "run_gated_submission_pipeline",
    "build_legacy_gate_report",
    "finalize_gate_report",
    "run_submission_quality_gate",
    "DataCollector",
    "MarketOpportunityScanner",
    "StrategySpawner",
    "BacktestFilter",
    "Deduplicator",
    "LocalEventDrivenResearchEngine",
    "get_local_event_engine",
    "FactorResearchBuilder",
    "StrategySubmitter",
    "EliminationChecker",
    "StrategyFactoryScheduler",
    "asyncio",
    "_factory_scheduler",
    "get_strategy_factory_scheduler",
]
