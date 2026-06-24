"""Public runtime-provider API for host integrations."""

from __future__ import annotations

from ..application.runtime import _call_optional_async, get_strategy_factory_package
from ..application.runtime_boundary import (
    RuntimeBoundaryReport,
    validate_strategy_factory_runtime,
)
from ..infrastructure.mcp_adapters import (
    MCPAutonomyGatewayImpl,
    MCPFactorResearchGatewayImpl,
    MCPIncubationGatewayImpl,
    MCPRiskGatewayImpl,
    MCPRuntimeAdapters,
    MCPStrategyFactoryRepositoryAdapter,
    MCPValidationGatewayImpl,
    MCPVectorSearchGatewayImpl,
    StrategyFactoryRepositoryAdapter,
    adapt_repository,
    build_mcp_runtime_adapters,
)
from ..infrastructure.mcp_services import (
    build_strategy_vector_profile,
    clear_runtime_services,
    configure_runtime_services,
    get_autonomy_lifecycle_runtime,
    get_backtest_engine_class,
    get_closure_review_builder,
    get_db_provider,
    get_event_context_builder,
    get_execution_audit_snapshot_builder,
    get_factor_mining_factory,
    get_factor_pool_gateway,
    get_factor_scheduler_singleton,
    get_financial_semantic_service_factory,
    get_index_kline_provider,
    get_normalize_klines,
    get_quant_manager_callable,
    get_risk_model_class,
    get_runtime_warmup_runner,
    get_sentiment_analyzer,
    get_strategy_dsl_compiler,
    get_strategy_lifecycle_shared_runtime,
    get_strategy_llm_provider_loader,
    get_strategy_promotion_pipeline_service,
    get_strategy_registry,
    get_strategy_runtime_control_service,
    get_strategy_vector_platform_factory,
    get_validation_runtime,
)

RuntimeAdapters = MCPRuntimeAdapters
VectorSearchGatewayImpl = MCPVectorSearchGatewayImpl
AutonomyGatewayImpl = MCPAutonomyGatewayImpl
FactorResearchGatewayImpl = MCPFactorResearchGatewayImpl
IncubationGatewayImpl = MCPIncubationGatewayImpl
ValidationGatewayImpl = MCPValidationGatewayImpl
RiskGatewayImpl = MCPRiskGatewayImpl
build_runtime_adapters = build_mcp_runtime_adapters


def build_scheduler_runtime_kwargs(db=None):
    """Build canonical scheduler kwargs from the registered runtime providers.

    This function bridges the old scheduler interface to the new runtime adapters.
    Used by default_bootstrap.py for backward compatibility.
    """
    from ..infrastructure.mcp_services import (
        get_strategy_autonomy_service,
        get_strategy_incubation_service,
        get_strategy_incubation_pipeline_service,
        get_factor_scheduler_singleton,
        get_validation_runner,
        get_risk_runner,
        get_strategy_vector_search_engine_builder,
    )

    db_provider = get_db_provider()
    resolved_db = db if db is not None else db_provider()

    vector_engine_builder = get_strategy_vector_search_engine_builder()
    vector_engine = vector_engine_builder() if callable(vector_engine_builder) else None

    return {
        "db_provider": db_provider,
        "runtime_adapters": build_runtime_adapters(
            resolved_db,
            vector_engine=vector_engine,
            autonomy_service=get_strategy_autonomy_service(),
            factor_scheduler=get_factor_scheduler_singleton(),
            incubation_service=get_strategy_incubation_service(),
            incubation_pipeline_service=get_strategy_incubation_pipeline_service(),
            validation_runner=get_validation_runner(),
            risk_runner=get_risk_runner(),
        ),
    }

__all__ = [
    "AutonomyGatewayImpl",
    "FactorResearchGatewayImpl",
    "IncubationGatewayImpl",
    "MCPAutonomyGatewayImpl",
    "MCPFactorResearchGatewayImpl",
    "MCPIncubationGatewayImpl",
    "MCPRiskGatewayImpl",
    "MCPRuntimeAdapters",
    "MCPStrategyFactoryRepositoryAdapter",
    "MCPValidationGatewayImpl",
    "MCPVectorSearchGatewayImpl",
    "RiskGatewayImpl",
    "RuntimeAdapters",
    "RuntimeBoundaryReport",
    "StrategyFactoryRepositoryAdapter",
    "ValidationGatewayImpl",
    "VectorSearchGatewayImpl",
    "_call_optional_async",
    "adapt_repository",
    "build_mcp_runtime_adapters",
    "build_runtime_adapters",
    "build_scheduler_runtime_kwargs",
    "build_strategy_vector_profile",
    "clear_runtime_services",
    "configure_runtime_services",
    "get_autonomy_lifecycle_runtime",
    "get_backtest_engine_class",
    "get_closure_review_builder",
    "get_db_provider",
    "get_event_context_builder",
    "get_execution_audit_snapshot_builder",
    "get_factor_mining_factory",
    "get_factor_pool_gateway",
    "get_factor_scheduler_singleton",
    "get_financial_semantic_service_factory",
    "get_index_kline_provider",
    "get_normalize_klines",
    "get_quant_manager_callable",
    "get_risk_model_class",
    "get_runtime_warmup_runner",
    "get_sentiment_analyzer",
    "get_strategy_factory_package",
    "get_strategy_dsl_compiler",
    "get_strategy_lifecycle_shared_runtime",
    "get_strategy_llm_provider_loader",
    "get_strategy_promotion_pipeline_service",
    "get_strategy_registry",
    "get_strategy_runtime_control_service",
    "get_strategy_vector_platform_factory",
    "get_validation_runtime",
    "validate_strategy_factory_runtime",
]
