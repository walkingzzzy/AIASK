"""MCP-facing adapters for the strategy_factory contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..api.contracts import (
    AutonomyGateway,
    FactorResearchGateway,
    IncubationGateway,
    RiskGateway,
    StrategyFactoryRepository,
    ValidationGateway,
    VectorSearchGateway,
)
from ..application.panels import _run_risk_report, _run_validation_report


class MCPStrategyFactoryRepositoryAdapter:
    """Thin wrapper that exposes the current aggregate db surface as a typed repository."""

    def __init__(self, db: Any):
        self._db = db

    @property
    def raw(self) -> Any:
        return self._db

    def __getattr__(self, name: str) -> Any:
        return getattr(self._db, name)

    async def get_klines(self, code: str, limit: int = 500):
        return await self._db.get_klines(code, limit=limit)

    async def get_limit_up_stats(self):
        return await self._db.get_limit_up_stats()

    async def get_factor_ic_history(self, factor_name: str, horizon: str, limit: int):
        return await self._db.get_factor_ic_history(factor_name, horizon, limit)

    async def count_strategies_by_type(self, status: str):
        return await self._db.count_strategies_by_type(status)

    async def save_daily_snapshot(self, snapshot_date: Any, snapshot: Mapping[str, Any]):
        return await self._db.save_daily_snapshot(snapshot_date, snapshot)

    async def list_strategies(self, status: str, limit: int = 500):
        return await self._db.list_strategies(status, limit=limit)

    async def get_strategy(self, strategy_id: str):
        return await self._db.get_strategy(strategy_id)

    async def get_strategy_metrics(self, strategy_id: str):
        return await self._db.get_strategy_metrics(strategy_id)

    async def get_signal_stats(self, strategy_id: str):
        return await self._db.get_signal_stats(strategy_id)

    async def save_strategy(self, data: Mapping[str, Any]):
        return await self._db.save_strategy(data)

    async def save_strategy_quality_report(self, strategy_id: str, report_type: str, report: Mapping[str, Any]):
        return await self._db.save_strategy_quality_report(strategy_id, report_type, report)

    async def update_strategy_status(self, strategy_id: str, status: str, **kwargs: Any):
        return await self._db.update_strategy_status(strategy_id, status, **kwargs)

    async def save_strategy_lineage(
        self,
        strategy_id: str,
        parent_strategy_id: Optional[str],
        reason: str,
        snapshot: Mapping[str, Any],
    ):
        return await self._db.save_strategy_lineage(strategy_id, parent_strategy_id, reason, snapshot)

    async def save_strategy_metrics(self, strategy_id: str, period: str, payload: Mapping[str, Any]):
        return await self._db.save_strategy_metrics(strategy_id, period, payload)

    async def save_elimination_log(self, strategy_id: str, log_date: Any, red_flags: list[str], reason: str):
        return await self._db.save_elimination_log(strategy_id, log_date, red_flags, reason)

    async def get_strategy_generation_experiment(self, experiment_id: str):
        return await self._db.get_strategy_generation_experiment(experiment_id)

    async def save_strategy_generation_experiment(self, payload: Mapping[str, Any]):
        return await self._db.save_strategy_generation_experiment(payload)

    async def save_factory_task_evidence(self, payload: Mapping[str, Any]):
        return await self._db.save_factory_task_evidence(payload)

    async def save_strategy_task_run(self, payload: Mapping[str, Any]):
        return await self._db.save_strategy_task_run(payload)

    async def update_strategy_task_run(self, task_run_id: Any, **kwargs: Any):
        return await self._db.update_strategy_task_run(task_run_id, **kwargs)

    async def list_stock_universe(self, limit: int = 200, offset: int = 0):
        return await self._db.list_stock_universe(limit=limit, offset=offset)

    async def list_factory_event_clusters(self, status: Optional[str] = None, limit: int = 200):
        return await self._db.list_factory_event_clusters(status=status, limit=limit)

    async def save_factory_theme_definition(self, payload: Mapping[str, Any]):
        return await self._db.save_factory_theme_definition(payload)

    async def save_strategy_factory_run(self, results: Mapping[str, Any]):
        return await self._db.save_strategy_factory_run(results)


class MCPVectorSearchGatewayImpl:
    """Adapter over the in-process VectorSearchEngine."""

    def __init__(self, engine: Any | None = None):
        if engine is None:
            from akshare_mcp.services.vector_search import VectorSearchEngine

            engine = VectorSearchEngine(backend="index", allow_fallback=True)
        self._engine = engine

    @property
    def raw(self) -> Any:
        return self._engine

    @property
    def last_backend_used(self) -> str:
        return str(getattr(self._engine, "last_backend_used", "") or "")

    @property
    def last_meta(self) -> Mapping[str, Any]:
        return dict(getattr(self._engine, "last_meta", {}) or {})

    def find_similar_patterns(
        self,
        query_klines,
        candidate_klines_dict,
        top_k: int = 10,
        method: str = "price_volume",
        metric: str = "cosine",
        backend: Optional[str] = None,
        allow_fallback: Optional[bool] = None,
    ):
        return self._engine.find_similar_patterns(
            query_klines=query_klines,
            candidate_klines_dict=dict(candidate_klines_dict),
            top_k=top_k,
            method=method,
            metric=metric,
            backend=backend,
            allow_fallback=allow_fallback,
        )


class MCPAutonomyGatewayImpl:
    """Adapter over the MCP strategy autonomy service singleton."""

    def __init__(self, service: Any | None = None):
        if service is None:
            from akshare_mcp.services.strategy_autonomy import get_strategy_autonomy_service

            service = get_strategy_autonomy_service()
        self._service = service

    @property
    def raw(self) -> Any:
        return self._service

    async def generate_factory_candidates(
        self,
        db: StrategyFactoryRepository,
        snapshot: Mapping[str, Any],
        *,
        limit: int = 4,
        research_task: Optional[Mapping[str, Any]] = None,
        source: str = "",
    ):
        method = self._service.generate_factory_candidates
        call_variants = [
            {"limit": limit, "research_task": research_task, "source": source},
            {"limit": limit, "research_task": research_task},
            {"limit": limit, "source": source},
            {"limit": limit},
            {},
        ]
        last_exc: Exception | None = None
        for kwargs in call_variants:
            try:
                result = method(db, snapshot, **kwargs)
                if hasattr(result, "__await__"):
                    return await result
                return result
            except TypeError as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        return await method(db, snapshot)


class MCPFactorResearchGatewayImpl:
    """Adapter over the factor scheduler status API."""

    def __init__(self, scheduler: Any | None = None, builder: Any | None = None):
        if scheduler is None:
            from akshare_mcp.services.factor_scheduler import get_factor_scheduler

            scheduler = get_factor_scheduler()
        if builder is None:
            from ..application.factor_research import FactorResearchBuilder

            builder = FactorResearchBuilder
        self._scheduler = scheduler
        self._builder = builder

    @property
    def raw(self) -> Any:
        return self._scheduler

    @property
    def raw_builder(self) -> Any:
        return self._builder

    async def build_artifact(self, db: StrategyFactoryRepository, snapshot: Mapping[str, Any]):
        builder = self._builder
        if builder is None:
            return {}
        build = getattr(builder, "build", None)
        if callable(build):
            return await build(db, dict(snapshot or {}))
        if callable(builder):
            return await builder(db, dict(snapshot or {}))
        return {}

    def status(self):
        return self._scheduler.status()


class MCPIncubationGatewayImpl:
    """Adapter over incubation account binding and incubation pipeline services."""

    def __init__(self, incubation_service: Any | None = None, pipeline_service: Any | None = None):
        if incubation_service is None:
            from akshare_mcp.services.incubation import get_strategy_incubation_service

            incubation_service = get_strategy_incubation_service()
        if pipeline_service is None:
            from akshare_mcp.services.incubation_pipeline import get_strategy_incubation_pipeline_service

            pipeline_service = get_strategy_incubation_pipeline_service()
        self._incubation_service = incubation_service
        self._pipeline_service = pipeline_service

    @property
    def raw_incubation_service(self) -> Any:
        return self._incubation_service

    @property
    def raw_pipeline_service(self) -> Any:
        return self._pipeline_service

    async def ensure_account(
        self,
        db: StrategyFactoryRepository,
        strategy: Mapping[str, Any],
        *,
        source_run_id: Optional[Any] = None,
        stage: str = "warmup",
    ):
        return await self._incubation_service.ensure_account(
            db,
            strategy,
            source_run_id=source_run_id,
            stage=stage,
        )

    async def run_pipeline(
        self,
        db: StrategyFactoryRepository,
        strategy: Mapping[str, Any],
        *,
        source: str = "strategy_factory_submit",
        auto_apply_review: bool = False,
    ):
        return await self._pipeline_service.run_strategy(
            db,
            strategy,
            source=source,
            auto_apply_review=auto_apply_review,
        )

    async def submit(
        self,
        db: StrategyFactoryRepository,
        strategy: Mapping[str, Any],
        *,
        source_run_id: Optional[Any] = None,
        source: str = "strategy_factory_submit",
        auto_apply_review: bool = False,
        stage: str = "warmup",
    ):
        binding = await self.ensure_account(db, strategy, source_run_id=source_run_id, stage=stage)
        pipeline = await self.run_pipeline(
            db,
            strategy,
            source=source,
            auto_apply_review=auto_apply_review,
        )
        return {"binding": binding, "pipeline": pipeline}


class MCPValidationGatewayImpl:
    """Adapter for the validation report runner used by the factory panels."""

    def __init__(self, runner=None):
        self._runner = runner or _run_validation_report

    @property
    def raw(self) -> Any:
        return self._runner

    async def run_validation_report(self, strategy_type: str, params: Mapping[str, Any], db: Any):
        return await self._runner(strategy_type, dict(params or {}), db)


class MCPRiskGatewayImpl:
    """Adapter for the risk report runner used by the factory panels."""

    def __init__(self, runner=None):
        self._runner = runner or _run_risk_report

    @property
    def raw(self) -> Any:
        return self._runner

    async def run_risk_report(self, strategy_type: str, params: Mapping[str, Any], db: Any):
        return await self._runner(strategy_type, dict(params or {}), db)


@dataclass(frozen=True)
class MCPRuntimeAdapters:
    """Typed bundle of MCP-backed adapters for incremental dependency injection."""

    repository: StrategyFactoryRepository
    vector_search: VectorSearchGateway
    autonomy: AutonomyGateway
    factor_research: FactorResearchGateway
    incubation: IncubationGateway
    validation: ValidationGateway
    risk: RiskGateway


def adapt_repository(db: Any) -> StrategyFactoryRepository:
    if isinstance(db, MCPStrategyFactoryRepositoryAdapter):
        return db
    return MCPStrategyFactoryRepositoryAdapter(db)


def build_mcp_runtime_adapters(
    db: Any,
    *,
    vector_engine: Any | None = None,
    autonomy_service: Any | None = None,
    factor_scheduler: Any | None = None,
    factor_research_builder: Any | None = None,
    incubation_service: Any | None = None,
    incubation_pipeline_service: Any | None = None,
    validation_runner=None,
    risk_runner=None,
) -> MCPRuntimeAdapters:
    return MCPRuntimeAdapters(
        repository=adapt_repository(db),
        vector_search=MCPVectorSearchGatewayImpl(vector_engine),
        autonomy=MCPAutonomyGatewayImpl(autonomy_service),
        factor_research=MCPFactorResearchGatewayImpl(factor_scheduler, factor_research_builder),
        incubation=MCPIncubationGatewayImpl(incubation_service, incubation_pipeline_service),
        validation=MCPValidationGatewayImpl(validation_runner),
        risk=MCPRiskGatewayImpl(risk_runner),
    )


__all__ = [
    "MCPAutonomyGatewayImpl",
    "MCPFactorResearchGatewayImpl",
    "MCPIncubationGatewayImpl",
    "MCPRiskGatewayImpl",
    "MCPRuntimeAdapters",
    "MCPStrategyFactoryRepositoryAdapter",
    "MCPValidationGatewayImpl",
    "MCPVectorSearchGatewayImpl",
    "adapt_repository",
    "build_mcp_runtime_adapters",
]
