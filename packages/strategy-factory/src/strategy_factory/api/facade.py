"""Stable public facade for the strategy_factory migration."""

from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any

from ..application.runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package
from ..domain.constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_MAX_RESEARCH_TASKS,
    AUTONOMY_STARTUP_DELAY_SEC,
    AUTONOMY_TASK_HARD_CAP,
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    BACKTEST_DEFAULT_THRESHOLDS,
    BACKTEST_TYPE_THRESHOLDS,
    CATEGORY_MINIMUMS,
    DEPRECATION_THRESHOLDS,
    FACTORY_DAILY_RUN_TIME,
    FACTORY_EVENT_RUNTIME_MODE,
    FACTORY_FACTOR_AUTO_REFRESH,
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    FACTORY_ERROR_BACKOFF_SEC,
    FACTORY_MARKET_HOURS_INTERVAL_SEC,
    FACTORY_MAX_DAILY_RUNS,
    FACTORY_OFF_HOURS_INTERVAL_SEC,
    FACTORY_READINESS_HARD_BLOCK,
    FACTORY_READINESS_MIN_COMPLETION_RATIO,
    FACTORY_READINESS_MIN_SCORE,
    FACTORY_PRE_GATE_ENABLED,
    FACTORY_RUNTIME_ENABLED,
    FACTORY_SCHEDULE_MODE,
    FACTORY_THROUGHPUT_TARGET_CANDIDATES_PER_HOUR,
    FACTORY_THROUGHPUT_TARGET_GATE3_PER_HOUR,
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
    SPAWNER_EVENT_SOURCE_BASE_CAP,
    SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS,
    SPAWNER_EVENT_FILL_BUDGET_MAX,
    SPAWNER_FILL_BUDGET_MAX,
    SPAWNER_TARGET_TOTAL,
    STOCK_STRATEGY_MATRIX_ENABLED,
    STOCK_STRATEGY_MATRIX_BATCH_SIZE,
    STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
    STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
    STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
    STOCK_STRATEGY_MATRIX_RUN_WINDOW,
    STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
    preferred_strategy_types_for_factor,
)

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "BacktestFilter": ("..application.backtest_filter", "BacktestFilter"),
    "DataCollector": ("..application.collect", "DataCollector"),
    "Deduplicator": ("..application.deduplicator", "Deduplicator"),
    "EliminationChecker": ("..application.elimination", "EliminationChecker"),
    "FactorResearchBuilder": ("..application.factor_research", "FactorResearchBuilder"),
    "LocalEventDrivenResearchEngine": ("..application.event_engine", "LocalEventDrivenResearchEngine"),
    "MarketOpportunityScanner": ("..application.opportunity", "MarketOpportunityScanner"),
    "StrategyFactoryScheduler": ("..application.factory_scheduler", "StrategyFactoryScheduler"),
    "StrategySpawner": ("..domain.spawner", "StrategySpawner"),
    "StrategySubmitter": ("..application.submitter", "StrategySubmitter"),
    "_call_optional_async": ("..application.runtime", "_call_optional_async"),
    "get_local_event_engine": ("..application.event_engine", "get_local_event_engine"),
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
    "call_optional_async",
    "auto_name",
    "get_local_event_engine",
    "get_strategy_factory_scheduler",
    "preferred_strategy_types_for_factor",
    "run_submission_quality_gate",
    "build_strategy_panels",
    "extract_event_context",
    "get_factory_constants",
]


def _filter_supported_kwargs(factory: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    if not kwargs:
        return {}
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return dict(kwargs)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return dict(kwargs)
    allowed = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {key: value for key, value in kwargs.items() if key in allowed}


def _resolve_export(name: str) -> Any:
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name, __package__)
    return getattr(module, attr_name)


def _get_runtime_symbol(name: str) -> Any:
    try:
        package = _runtime_get_strategy_factory_package()
    except Exception:
        return None
    try:
        return getattr(package, name, None)
    except Exception:
        return None


def get_strategy_factory_scheduler(**kwargs):
    local_scheduler_cls = _resolve_export("StrategyFactoryScheduler")
    target = _get_runtime_symbol("get_strategy_factory_scheduler")
    if callable(target):
        filtered_kwargs = _filter_supported_kwargs(target, kwargs)
        return target(**filtered_kwargs) if filtered_kwargs else target()
    filtered_kwargs = _filter_supported_kwargs(local_scheduler_cls, kwargs)
    return local_scheduler_cls(**filtered_kwargs)


async def run_submission_quality_gate(*args, **kwargs):
    local_target = import_module("..application.submission_gate", __package__).run_submission_quality_gate
    target = _get_runtime_symbol("run_submission_quality_gate") or local_target
    return await target(*args, **kwargs)


async def call_optional_async(*args, **kwargs):
    target = _resolve_export("_call_optional_async")
    return await target(*args, **kwargs)


def build_strategy_panels(*args, **kwargs):
    local_target = import_module("..application.panels", __package__)._build_strategy_panels
    target = _get_runtime_symbol("_build_strategy_panels") or local_target
    return target(*args, **kwargs)


def extract_event_context(*args, **kwargs):
    local_target = import_module("..application.utils", __package__)._extract_event_context
    target = _get_runtime_symbol("_extract_event_context") or local_target
    return target(*args, **kwargs)


def auto_name(*args, **kwargs):
    local_target = import_module("..domain.naming", __package__)._auto_name
    target = _get_runtime_symbol("_auto_name") or local_target
    return target(*args, **kwargs)


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
        "AUTONOMY_TASK_HARD_CAP": AUTONOMY_TASK_HARD_CAP,
        "AUTONOMY_STARTUP_DELAY_SEC": AUTONOMY_STARTUP_DELAY_SEC,
        "BACKTEST_TYPE_THRESHOLDS": BACKTEST_TYPE_THRESHOLDS,
        "FACTORY_SCHEDULE_MODE": FACTORY_SCHEDULE_MODE,
        "FACTORY_EVENT_RUNTIME_MODE": FACTORY_EVENT_RUNTIME_MODE,
        "FACTORY_RUNTIME_ENABLED": FACTORY_RUNTIME_ENABLED,
        "FACTORY_FACTOR_AUTO_REFRESH": FACTORY_FACTOR_AUTO_REFRESH,
        "FACTORY_FACTOR_REFRESH_TIMEOUT_SEC": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
        "FACTORY_READINESS_HARD_BLOCK": FACTORY_READINESS_HARD_BLOCK,
        "FACTORY_READINESS_MIN_SCORE": FACTORY_READINESS_MIN_SCORE,
        "FACTORY_READINESS_MIN_COMPLETION_RATIO": FACTORY_READINESS_MIN_COMPLETION_RATIO,
        "FACTORY_PRE_GATE_ENABLED": FACTORY_PRE_GATE_ENABLED,
        "FACTORY_MARKET_HOURS_INTERVAL_SEC": FACTORY_MARKET_HOURS_INTERVAL_SEC,
        "FACTORY_OFF_HOURS_INTERVAL_SEC": FACTORY_OFF_HOURS_INTERVAL_SEC,
        "FACTORY_MAX_DAILY_RUNS": FACTORY_MAX_DAILY_RUNS,
        "FACTORY_ERROR_BACKOFF_SEC": FACTORY_ERROR_BACKOFF_SEC,
        "FACTORY_DAILY_RUN_TIME": FACTORY_DAILY_RUN_TIME,
        "FACTORY_THROUGHPUT_TARGET_CANDIDATES_PER_HOUR": FACTORY_THROUGHPUT_TARGET_CANDIDATES_PER_HOUR,
        "FACTORY_THROUGHPUT_TARGET_GATE3_PER_HOUR": FACTORY_THROUGHPUT_TARGET_GATE3_PER_HOUR,
        "LLM_FAN_OUT_COUNT": LLM_FAN_OUT_COUNT,
        "PIPELINE_MODE": PIPELINE_MODE,
        "PIPELINE_STAGE_TIMEOUTS": PIPELINE_STAGE_TIMEOUTS,
        "PIPELINE_STAGE_MAX_TOKENS": PIPELINE_STAGE_MAX_TOKENS,
        "PIPELINE_STAGE_TEMPERATURE": PIPELINE_STAGE_TEMPERATURE,
        "PIPELINE_STAGE_TIMEOUT_SEC": PIPELINE_STAGE_TIMEOUT_SEC,
        "SPAWNER_TARGET_TOTAL": SPAWNER_TARGET_TOTAL,
        "SPAWNER_FILL_BUDGET_MAX": SPAWNER_FILL_BUDGET_MAX,
        "SPAWNER_EVENT_FILL_BUDGET_MAX": SPAWNER_EVENT_FILL_BUDGET_MAX,
        "SPAWNER_EVENT_SOURCE_BASE_CAP": SPAWNER_EVENT_SOURCE_BASE_CAP,
        "SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS": SPAWNER_EVENT_SOURCE_SUPPLEMENTAL_BONUS,
        "STOCK_STRATEGY_MATRIX_ENABLED": STOCK_STRATEGY_MATRIX_ENABLED,
        "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
        "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK": STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
        "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN": STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
        "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN": STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
        "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK": STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
        "STOCK_STRATEGY_MATRIX_BATCH_SIZE": STOCK_STRATEGY_MATRIX_BATCH_SIZE,
        "STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY": STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY,
        "STOCK_STRATEGY_MATRIX_RUN_WINDOW": STOCK_STRATEGY_MATRIX_RUN_WINDOW,
        "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD": STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
    }


def __getattr__(name: str) -> Any:
    return _resolve_export(name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
