"""AKShare-backed runtime providers for the Strategy Factory package.

This module is an in-process bridge, not an MCP tool surface. It lets callers
run ``strategy_factory`` directly while using AKShare MCP's SQLite storage and
local service implementations as explicit runtime providers.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable


def get_strategy_factory_db_provider() -> Callable[[], Any]:
    """Return the AKShare SQLite DB provider used by Strategy Factory runs."""

    from ..storage import get_db

    return get_db


async def _get_index_kline_from_db(index_code: str, period: str = "daily", limit: int = 60) -> dict[str, Any]:
    if str(period or "daily").lower() not in {"daily", "day", "1d", "d"}:
        return {
            "success": False,
            "data": [],
            "source": "sqlite.kline_1d",
            "degraded": True,
            "message": "only daily index klines are synchronized to SQLite",
        }
    db = get_strategy_factory_db_provider()()
    rows = await db.get_index_klines(str(index_code or ""), limit=max(1, int(limit or 60)))
    return {
        "success": bool(rows),
        "data": rows,
        "source": "sqlite.kline_1d",
        "degraded": not bool(rows),
        "message": None if rows else "index klines missing in SQLite; run TDX sync",
    }


def _build_strategy_vector_profile(db: Any, strategy: dict[str, Any]):
    from ..services.vector_platform import get_strategy_vector_platform

    platform = get_strategy_vector_platform()
    return platform.build_strategy_profile(db, strategy)


def _strategy_lifecycle_shared_runtime() -> Any:
    from ..services import strategy_lifecycle_shared as module

    return SimpleNamespace(
        build_incubation_overview=getattr(module, "build_incubation_overview", None),
    )


def _autonomy_lifecycle_runtime() -> Any:
    from ..services import strategy_autonomy_lifecycle as module

    return SimpleNamespace(
        AUTONOMY_PHASE_ORDER=tuple(module.AUTONOMY_PHASE_ORDER),
        summarize_autonomy_lifecycle=module.summarize_autonomy_lifecycle,
    )


def configure_strategy_factory_runtime_services() -> None:
    """Register AKShare service providers in Strategy Factory's host registry."""

    from strategy_factory.api.runtime import configure_runtime_services

    configure_runtime_services(
        db_provider=get_strategy_factory_db_provider(),
        factor_scheduler=lambda: __import__(
            "akshare_mcp.services.factor_scheduler",
            fromlist=["get_factor_scheduler"],
        ).get_factor_scheduler(),
        factor_mining_factory=lambda: __import__(
            "akshare_mcp.services.factor_mining_factory",
            fromlist=["get_factor_mining_factory"],
        ).get_factor_mining_factory(),
        factor_pool_gateway=lambda: __import__(
            "akshare_mcp.services.factor_mining_factory.api",
            fromlist=["get_factor_pool_gateway"],
        ).get_factor_pool_gateway(),
        quant_manager_callable=__import__(
            "akshare_mcp.tools.managers.quant_manager",
            fromlist=["quant_manager"],
        ).quant_manager,
        runtime_warmup_runner=__import__(
            "akshare_mcp.tools.managers.data_sync_manager",
            fromlist=["run_runtime_data_warmup"],
        ).run_runtime_data_warmup,
        strategy_promotion_pipeline_service=lambda: __import__(
            "akshare_mcp.services.promotion_pipeline",
            fromlist=["get_strategy_promotion_pipeline_service"],
        ).get_strategy_promotion_pipeline_service(),
        strategy_runtime_control_service=lambda: __import__(
            "akshare_mcp.services.runtime_control",
            fromlist=["get_strategy_runtime_control_service"],
        ).get_strategy_runtime_control_service(),
        strategy_lifecycle_shared_runtime=_strategy_lifecycle_shared_runtime(),
        event_context_builder=__import__(
            "akshare_mcp.services.decision_event_builder",
            fromlist=["build_event_context"],
        ).build_event_context,
        sentiment_analyzer=__import__(
            "akshare_mcp.services.sentiment",
            fromlist=["sentiment_analyzer"],
        ).sentiment_analyzer,
        financial_semantic_service_factory=__import__(
            "akshare_mcp.services.financial_semantic_service",
            fromlist=["get_financial_semantic_service"],
        ).get_financial_semantic_service,
        index_kline_provider=_get_index_kline_from_db,
        strategy_dsl_compiler=__import__(
            "akshare_mcp.services.strategy_dsl",
            fromlist=["compile_strategy_blueprint"],
        ).compile_strategy_blueprint,
        strategy_vector_platform_factory=__import__(
            "akshare_mcp.services.vector_platform",
            fromlist=["get_strategy_vector_platform"],
        ).get_strategy_vector_platform,
        autonomy_lifecycle_runtime=_autonomy_lifecycle_runtime(),
        strategy_vector_profile_builder=_build_strategy_vector_profile,
        execution_audit_snapshot_builder=__import__(
            "akshare_mcp.services.strategy_lifecycle_shared.execution_audit_snapshot",
            fromlist=["build_execution_audit_snapshot_payload"],
        ).build_execution_audit_snapshot_payload,
        closure_review_builder=__import__(
            "akshare_mcp.services.strategy_lifecycle_shared",
            fromlist=["build_closure_review"],
        ).build_closure_review,
        strategy_llm_provider_loader=__import__(
            "akshare_mcp.services.strategy_llm_provider",
            fromlist=["get_strategy_llm_provider"],
        ).get_strategy_llm_provider,
    )


def build_strategy_factory_runtime_adapters(db: Any | None = None) -> Any:
    """Build Strategy Factory runtime adapters backed by AKShare services."""

    configure_strategy_factory_runtime_services()

    from strategy_factory.api.runtime import build_runtime_adapters
    from ..services.vector_search import VectorSearchEngine
    from ..services.strategy_autonomy import get_strategy_autonomy_service
    from ..services.factor_scheduler import get_factor_scheduler
    from ..services.incubation import get_strategy_incubation_service
    from ..services.incubation_pipeline import get_strategy_incubation_pipeline_service

    resolved_db = db if db is not None else get_strategy_factory_db_provider()()
    autonomy_service = get_strategy_autonomy_service()
    try:
        setattr(autonomy_service, "requires_repository_task_persistence", True)
    except Exception:
        pass
    return build_runtime_adapters(
        resolved_db,
        vector_engine=VectorSearchEngine(backend="index", allow_fallback=True),
        autonomy_service=autonomy_service,
        factor_scheduler=get_factor_scheduler(),
        incubation_service=get_strategy_incubation_service(),
        incubation_pipeline_service=get_strategy_incubation_pipeline_service(),
    )


def build_strategy_factory_scheduler_kwargs(db: Any | None = None) -> dict[str, Any]:
    """Return kwargs for ``strategy_factory.get_strategy_factory_scheduler``."""

    db_provider = get_strategy_factory_db_provider()
    resolved_db = db if db is not None else db_provider()
    return {
        "db_provider": db_provider,
        "runtime_adapters": build_strategy_factory_runtime_adapters(resolved_db),
    }


__all__ = [
    "build_strategy_factory_runtime_adapters",
    "build_strategy_factory_scheduler_kwargs",
    "configure_strategy_factory_runtime_services",
    "get_strategy_factory_db_provider",
]
