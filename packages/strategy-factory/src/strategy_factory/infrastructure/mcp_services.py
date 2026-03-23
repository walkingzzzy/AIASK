"""Lazy MCP service loaders used by the migrated strategy_factory package.

This module centralizes imports of ``akshare_mcp.services.*`` so the
application layer can stay focused on factory orchestration and contracts.
"""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from typing import Any


_DEFAULT_AUTONOMY_PHASE_ORDER = (
    "prepared",
    "generating",
    "reviewing",
    "recording",
    "submitting",
    "completed",
)


def get_backtest_engine_class():
    return import_module("akshare_mcp.services.backtest.engine").BacktestEngine


def get_strategy_registry():
    return import_module("akshare_mcp.services.backtest.strategy_registry").StrategyRegistry


def get_normalize_klines():
    return import_module("akshare_mcp.services.data_pipeline").normalize_klines


def get_risk_model_class():
    return import_module("akshare_mcp.services.risk_model").RiskModel


def get_validation_runtime():
    module = import_module("akshare_mcp.services.validation")
    return SimpleNamespace(
        FactorValidationPipeline=module.FactorValidationPipeline,
        PurgedKFoldCV=module.PurgedKFoldCV,
        WalkForwardValidator=module.WalkForwardValidator,
        bootstrap_ic_ci=module.bootstrap_ic_ci,
        deflated_sharpe_ratio=module.deflated_sharpe_ratio,
        probability_of_backtest_overfitting=module.probability_of_backtest_overfitting,
        white_reality_check=module.white_reality_check,
        hansen_spa_test=module.hansen_spa_test,
    )


def get_factor_scheduler_singleton():
    return import_module("akshare_mcp.services.factor_scheduler").get_factor_scheduler()


def get_quant_manager_callable():
    return import_module("akshare_mcp.tools.managers.quant_manager").quant_manager


def get_runtime_warmup_runner():
    return import_module("akshare_mcp.tools.managers.data_sync_manager").run_runtime_data_warmup


def get_sentiment_analyzer():
    return import_module("akshare_mcp.services.sentiment").sentiment_analyzer


def get_db_provider():
    return import_module("akshare_mcp.storage").get_db


def get_index_kline_provider():
    return import_module("akshare_mcp.tools.market.kline").get_index_kline


def get_strategy_dsl_compiler():
    return import_module("akshare_mcp.services.strategy_dsl").compile_strategy_blueprint


def get_strategy_vector_platform_factory():
    return import_module("akshare_mcp.services.vector_platform").get_strategy_vector_platform


def get_autonomy_lifecycle_runtime():
    try:
        module = import_module("akshare_mcp.services.strategy_autonomy_lifecycle")
    except ModuleNotFoundError:
        return SimpleNamespace(
            AUTONOMY_PHASE_ORDER=_DEFAULT_AUTONOMY_PHASE_ORDER,
            summarize_autonomy_lifecycle=_summarize_autonomy_lifecycle_fallback,
        )
    return SimpleNamespace(
        AUTONOMY_PHASE_ORDER=tuple(module.AUTONOMY_PHASE_ORDER),
        summarize_autonomy_lifecycle=module.summarize_autonomy_lifecycle,
    )


def build_strategy_vector_profile(db: Any, strategy: dict[str, Any]):
    platform = get_strategy_vector_platform_factory()()
    return platform.build_strategy_profile(db, strategy)


def _summarize_autonomy_lifecycle_fallback(lifecycle: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(lifecycle or {})
    return {
        "state": payload.get("state"),
        "current_phase": payload.get("current_phase"),
        "failed_phase": payload.get("failed_phase"),
        "terminal_phase": payload.get("terminal_phase"),
        "phase_status_counts": dict(payload.get("phase_status_counts") or {}),
        "completed_phase_count": int(payload.get("completed_phase_count") or 0),
        "event_count": int(payload.get("event_count") or len(payload.get("events") or [])),
        "phase_order": list(payload.get("phase_order") or _DEFAULT_AUTONOMY_PHASE_ORDER),
    }


__all__ = [
    "build_strategy_vector_profile",
    "get_autonomy_lifecycle_runtime",
    "get_backtest_engine_class",
    "get_db_provider",
    "get_factor_scheduler_singleton",
    "get_quant_manager_callable",
    "get_runtime_warmup_runner",
    "get_index_kline_provider",
    "get_normalize_klines",
    "get_risk_model_class",
    "get_sentiment_analyzer",
    "get_strategy_dsl_compiler",
    "get_strategy_registry",
    "get_strategy_vector_platform_factory",
    "get_validation_runtime",
]
