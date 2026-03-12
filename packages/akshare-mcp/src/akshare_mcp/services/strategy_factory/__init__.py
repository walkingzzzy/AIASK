"""策略工厂包兼容导出。"""

from __future__ import annotations

import asyncio
from typing import Optional

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
from .deduplicator import Deduplicator
from .event_engine import LocalEventDrivenResearchEngine, get_local_event_engine
from .elimination import EliminationChecker
from .factor_research import FactorResearchBuilder
from .factory_scheduler import StrategyFactoryScheduler
from .opportunity import MarketOpportunityScanner
from .spawner import StrategySpawner
from .submitter import StrategySubmitter
from .naming import _auto_name
from .panels import _build_strategy_panels, _run_risk_report, _run_validation_report
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

_factory_scheduler: Optional[StrategyFactoryScheduler] = None


def get_strategy_factory_scheduler() -> StrategyFactoryScheduler:
    global _factory_scheduler
    if _factory_scheduler is None:
        _factory_scheduler = StrategyFactoryScheduler()
    return _factory_scheduler


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
