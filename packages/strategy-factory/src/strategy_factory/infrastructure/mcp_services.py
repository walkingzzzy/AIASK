"""Lazy MCP service loaders used by the migrated strategy_factory package.

This module centralizes imports of ``akshare_mcp.services.*`` so the
application layer can stay focused on factory orchestration and contracts.
"""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from typing import Any


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
    )


def get_factor_scheduler_singleton():
    return import_module("akshare_mcp.services.factor_scheduler").get_factor_scheduler()


def get_sentiment_analyzer():
    return import_module("akshare_mcp.services.sentiment").sentiment_analyzer


def get_strategy_dsl_compiler():
    return import_module("akshare_mcp.services.strategy_dsl").compile_strategy_blueprint


def get_strategy_vector_platform_factory():
    return import_module("akshare_mcp.services.vector_platform").get_strategy_vector_platform


def get_autonomy_lifecycle_runtime():
    module = import_module("akshare_mcp.services.strategy_autonomy_lifecycle")
    return SimpleNamespace(
        AUTONOMY_PHASE_ORDER=tuple(module.AUTONOMY_PHASE_ORDER),
        summarize_autonomy_lifecycle=module.summarize_autonomy_lifecycle,
    )


def build_strategy_vector_profile(db: Any, strategy: dict[str, Any]):
    platform = get_strategy_vector_platform_factory()()
    return platform.build_strategy_profile(db, strategy)


__all__ = [
    "build_strategy_vector_profile",
    "get_autonomy_lifecycle_runtime",
    "get_backtest_engine_class",
    "get_factor_scheduler_singleton",
    "get_normalize_klines",
    "get_risk_model_class",
    "get_sentiment_analyzer",
    "get_strategy_dsl_compiler",
    "get_strategy_registry",
    "get_strategy_vector_platform_factory",
    "get_validation_runtime",
]
