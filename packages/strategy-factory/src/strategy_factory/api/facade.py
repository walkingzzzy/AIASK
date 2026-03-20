"""Stable public facade for the strategy_factory migration."""

from __future__ import annotations

from typing import Any

from ..application.backtest_filter import BacktestFilter
from ..application.collect import DataCollector
from ..application.deduplicator import Deduplicator
from ..application.elimination import EliminationChecker
from ..application.event_engine import LocalEventDrivenResearchEngine, get_local_event_engine
from ..application.factor_research import FactorResearchBuilder
from ..application.factory_scheduler import StrategyFactoryScheduler
from ..application.panels import _build_strategy_panels as _local_build_strategy_panels
from ..application.runtime import _call_optional_async, get_strategy_factory_package as _runtime_get_strategy_factory_package
from ..application.submission_gate import run_submission_quality_gate as _local_run_submission_quality_gate
from ..application.submitter import StrategySubmitter
from ..application.utils import _extract_event_context as _local_extract_event_context
from ..domain.spawner import StrategySpawner
from ..domain.constants import (
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
    LLM_FAN_OUT_COUNT,
    PIPELINE_MODE,
    PIPELINE_STAGE_MAX_TOKENS,
    PIPELINE_STAGE_TEMPERATURE,
    PIPELINE_STAGE_TIMEOUTS,
    PIPELINE_STAGE_TIMEOUT_SEC,
    PROMOTION_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
    QUALITY_GATE_THRESHOLDS,
    REPRESENTATIVE_STOCKS,
    RISK_REPORT_THRESHOLDS,
    preferred_strategy_types_for_factor,
)
from ..application.opportunity import MarketOpportunityScanner


def get_strategy_factory_scheduler():
    package = _runtime_get_strategy_factory_package()
    target = getattr(package, "get_strategy_factory_scheduler", None)
    if callable(target):
        return target()
    return StrategyFactoryScheduler()


async def run_submission_quality_gate(*args, **kwargs):
    package = _runtime_get_strategy_factory_package()
    target = getattr(package, "run_submission_quality_gate", _local_run_submission_quality_gate)
    return await target(*args, **kwargs)


def build_strategy_panels(*args, **kwargs):
    package = _runtime_get_strategy_factory_package()
    target = getattr(package, "_build_strategy_panels", _local_build_strategy_panels)
    return target(*args, **kwargs)


def extract_event_context(*args, **kwargs):
    package = _runtime_get_strategy_factory_package()
    target = getattr(package, "_extract_event_context", None)
    if callable(target):
        return target(*args, **kwargs)
    return _local_extract_event_context(*args, **kwargs)


def get_factory_constants() -> dict[str, Any]:
    return {
        "REPRESENTATIVE_STOCKS": REPRESENTATIVE_STOCKS,
        "CATEGORY_MINIMUMS": CATEGORY_MINIMUMS,
        "BACKTEST_DEFAULT_THRESHOLDS": BACKTEST_DEFAULT_THRESHOLDS,
        "BACKTEST_AI_PROTOTYPE_THRESHOLDS": BACKTEST_AI_PROTOTYPE_THRESHOLDS,
        "PROVISIONAL_PASS_THRESHOLDS": PROVISIONAL_PASS_THRESHOLDS,
        "QUALITY_GATE_THRESHOLDS": QUALITY_GATE_THRESHOLDS,
        "RISK_REPORT_THRESHOLDS": RISK_REPORT_THRESHOLDS,
        "PROMOTION_THRESHOLDS": PROMOTION_THRESHOLDS,
        "DEPRECATION_THRESHOLDS": DEPRECATION_THRESHOLDS,
        "AUTONOMY_MAX_RESEARCH_TASKS": AUTONOMY_MAX_RESEARCH_TASKS,
        "AUTONOMY_CANDIDATES_PER_TASK": AUTONOMY_CANDIDATES_PER_TASK,
        "AUTONOMY_STARTUP_DELAY_SEC": AUTONOMY_STARTUP_DELAY_SEC,
        "BACKTEST_TYPE_THRESHOLDS": BACKTEST_TYPE_THRESHOLDS,
        "FACTORY_SCHEDULE_MODE": FACTORY_SCHEDULE_MODE,
        "FACTORY_MARKET_HOURS_INTERVAL_SEC": FACTORY_MARKET_HOURS_INTERVAL_SEC,
        "FACTORY_OFF_HOURS_INTERVAL_SEC": FACTORY_OFF_HOURS_INTERVAL_SEC,
        "FACTORY_MAX_DAILY_RUNS": FACTORY_MAX_DAILY_RUNS,
        "FACTORY_ERROR_BACKOFF_SEC": FACTORY_ERROR_BACKOFF_SEC,
        "FACTORY_DAILY_RUN_TIME": FACTORY_DAILY_RUN_TIME,
        "PIPELINE_MODE": PIPELINE_MODE,
        "PIPELINE_STAGE_MAX_TOKENS": PIPELINE_STAGE_MAX_TOKENS,
        "PIPELINE_STAGE_TEMPERATURE": PIPELINE_STAGE_TEMPERATURE,
        "PIPELINE_STAGE_TIMEOUT_SEC": PIPELINE_STAGE_TIMEOUT_SEC,
    }


__all__ = [
    "BACKTEST_AI_PROTOTYPE_THRESHOLDS",
    "CATEGORY_MINIMUMS",
    "DataCollector",
    "DEPRECATION_THRESHOLDS",
    "MarketOpportunityScanner",
    "FactorResearchBuilder",
    "LLM_FAN_OUT_COUNT",
    "LocalEventDrivenResearchEngine",
    "PIPELINE_MODE",
    "PIPELINE_STAGE_MAX_TOKENS",
    "PIPELINE_STAGE_TEMPERATURE",
    "PIPELINE_STAGE_TIMEOUTS",
    "PIPELINE_STAGE_TIMEOUT_SEC",
    "PROMOTION_THRESHOLDS",
    "PROVISIONAL_PASS_THRESHOLDS",
    "QUALITY_GATE_THRESHOLDS",
    "RISK_REPORT_THRESHOLDS",
    "StrategyFactoryScheduler",
    "StrategySpawner",
    "BacktestFilter",
    "Deduplicator",
    "StrategySubmitter",
    "EliminationChecker",
    "_call_optional_async",
    "get_local_event_engine",
    "get_strategy_factory_scheduler",
    "preferred_strategy_types_for_factor",
    "run_submission_quality_gate",
    "build_strategy_panels",
    "extract_event_context",
    "get_factory_constants",
]
