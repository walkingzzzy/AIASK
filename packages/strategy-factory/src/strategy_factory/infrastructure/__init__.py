"""Lazy infrastructure exports for MCP-backed adapters and service loaders."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MAP: dict[str, tuple[str, str]] = {
    "MCPAutonomyGatewayImpl": (".mcp_adapters", "MCPAutonomyGatewayImpl"),
    "MCPFactorResearchGatewayImpl": (".mcp_adapters", "MCPFactorResearchGatewayImpl"),
    "MCPIncubationGatewayImpl": (".mcp_adapters", "MCPIncubationGatewayImpl"),
    "MCPRiskGatewayImpl": (".mcp_adapters", "MCPRiskGatewayImpl"),
    "MCPRuntimeAdapters": (".mcp_adapters", "MCPRuntimeAdapters"),
    "MCPStrategyFactoryRepositoryAdapter": (".mcp_adapters", "MCPStrategyFactoryRepositoryAdapter"),
    "MCPValidationGatewayImpl": (".mcp_adapters", "MCPValidationGatewayImpl"),
    "MCPVectorSearchGatewayImpl": (".mcp_adapters", "MCPVectorSearchGatewayImpl"),
    "adapt_repository": (".mcp_adapters", "adapt_repository"),
    "build_mcp_runtime_adapters": (".mcp_adapters", "build_mcp_runtime_adapters"),
    "StrategyFactoryRepositoryAdapter": (".mcp_adapters", "StrategyFactoryRepositoryAdapter"),
    "build_strategy_vector_profile": (".mcp_services", "build_strategy_vector_profile"),
    "get_autonomy_lifecycle_runtime": (".mcp_services", "get_autonomy_lifecycle_runtime"),
    "get_backtest_engine_class": (".mcp_services", "get_backtest_engine_class"),
    "get_factor_scheduler_singleton": (".mcp_services", "get_factor_scheduler_singleton"),
    "get_normalize_klines": (".mcp_services", "get_normalize_klines"),
    "get_risk_model_class": (".mcp_services", "get_risk_model_class"),
    "get_sentiment_analyzer": (".mcp_services", "get_sentiment_analyzer"),
    "get_strategy_dsl_compiler": (".mcp_services", "get_strategy_dsl_compiler"),
    "get_strategy_registry": (".mcp_services", "get_strategy_registry"),
    "get_strategy_vector_platform_factory": (".mcp_services", "get_strategy_vector_platform_factory"),
    "get_validation_runtime": (".mcp_services", "get_validation_runtime"),
}

__all__ = list(_EXPORT_MAP)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORT_MAP[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name, __name__)
    return getattr(module, attr_name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
