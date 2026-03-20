"""Typed contracts for the strategy_factory migration."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable


JSONDict = dict[str, Any]


@runtime_checkable
class StrategyFactoryRepository(Protocol):
    """Repository contract observed across the migrated strategy factory modules."""

    async def get_klines(self, code: str, limit: int = 500) -> list[Mapping[str, Any]]: ...

    async def get_limit_up_stats(self) -> Mapping[str, Any]: ...

    async def get_factor_ic_history(self, factor_name: str, horizon: str, limit: int) -> list[Mapping[str, Any]]: ...

    async def count_strategies_by_type(self, status: str) -> Mapping[str, int]: ...

    async def save_daily_snapshot(self, snapshot_date: Any, snapshot: Mapping[str, Any]) -> Any: ...

    async def list_strategies(self, status: str, limit: int = 500) -> list[Mapping[str, Any]]: ...

    async def get_strategy(self, strategy_id: str) -> Optional[Mapping[str, Any]]: ...

    async def get_strategy_metrics(self, strategy_id: str) -> list[Mapping[str, Any]]: ...

    async def get_signal_stats(self, strategy_id: str) -> Mapping[str, Any]: ...

    async def save_strategy(self, data: Mapping[str, Any]) -> Any: ...

    async def save_strategy_quality_report(self, strategy_id: str, report_type: str, report: Mapping[str, Any]) -> Any: ...

    async def update_strategy_status(self, strategy_id: str, status: str, **kwargs: Any) -> Any: ...

    async def save_strategy_lineage(
        self,
        strategy_id: str,
        parent_strategy_id: Optional[str],
        reason: str,
        snapshot: Mapping[str, Any],
    ) -> Any: ...

    async def save_strategy_metrics(self, strategy_id: str, period: str, payload: Mapping[str, Any]) -> Any: ...

    async def save_elimination_log(self, strategy_id: str, log_date: Any, red_flags: list[str], reason: str) -> Any: ...

    async def get_strategy_generation_experiment(self, experiment_id: str) -> Optional[Mapping[str, Any]]: ...

    async def save_strategy_generation_experiment(self, payload: Mapping[str, Any]) -> Any: ...

    async def save_factory_task_evidence(self, payload: Mapping[str, Any]) -> Any: ...

    async def save_strategy_task_run(self, payload: Mapping[str, Any]) -> Any: ...

    async def update_strategy_task_run(self, task_run_id: Any, **kwargs: Any) -> Any: ...

    async def list_stock_universe(self, limit: int = 200, offset: int = 0) -> list[Mapping[str, Any]]: ...

    async def list_factory_event_clusters(self, status: Optional[str] = None, limit: int = 200) -> list[Mapping[str, Any]]: ...

    async def save_factory_theme_definition(self, payload: Mapping[str, Any]) -> Any: ...

    async def save_strategy_factory_run(self, results: Mapping[str, Any]) -> Any: ...


@runtime_checkable
class VectorSearchGateway(Protocol):
    """Gateway for vector-pattern lookup used by dedup/vector layers."""

    @property
    def last_backend_used(self) -> str: ...

    @property
    def last_meta(self) -> Mapping[str, Any]: ...

    def find_similar_patterns(
        self,
        query_klines: list[Mapping[str, Any]],
        candidate_klines_dict: Mapping[str, list[Mapping[str, Any]]],
        top_k: int = 10,
        method: str = "price_volume",
        metric: str = "cosine",
        backend: Optional[str] = None,
        allow_fallback: Optional[bool] = None,
    ) -> list[JSONDict]: ...


@runtime_checkable
class AutonomyGateway(Protocol):
    """Gateway for the external strategy autonomy service."""

    async def generate_factory_candidates(
        self,
        db: StrategyFactoryRepository,
        snapshot: Mapping[str, Any],
        *,
        limit: int = 4,
        research_task: Optional[Mapping[str, Any]] = None,
        source: str = "",
    ) -> JSONDict: ...


@runtime_checkable
class FactorResearchGateway(Protocol):
    """Gateway for factor scheduler / factor-research metadata."""

    async def build_artifact(
        self,
        db: StrategyFactoryRepository,
        snapshot: Mapping[str, Any],
    ) -> JSONDict: ...

    def status(self) -> Mapping[str, Any]: ...


@runtime_checkable
class IncubationGateway(Protocol):
    """Gateway for incubation account binding and pipeline warm-up."""

    async def ensure_account(
        self,
        db: StrategyFactoryRepository,
        strategy: Mapping[str, Any],
        *,
        source_run_id: Optional[Any] = None,
        stage: str = "warmup",
    ) -> JSONDict: ...

    async def run_pipeline(
        self,
        db: StrategyFactoryRepository,
        strategy: Mapping[str, Any],
        *,
        source: str = "strategy_factory_submit",
        auto_apply_review: bool = False,
    ) -> JSONDict: ...

    async def submit(
        self,
        db: StrategyFactoryRepository,
        strategy: Mapping[str, Any],
        *,
        source_run_id: Optional[Any] = None,
        source: str = "strategy_factory_submit",
        auto_apply_review: bool = False,
        stage: str = "warmup",
    ) -> JSONDict: ...


@runtime_checkable
class ValidationGateway(Protocol):
    """Gateway for validation reports derived from strategy panels."""

    async def run_validation_report(self, strategy_type: str, params: Mapping[str, Any], db: Any) -> Optional[JSONDict]: ...


@runtime_checkable
class RiskGateway(Protocol):
    """Gateway for risk reports derived from strategy panels."""

    async def run_risk_report(self, strategy_type: str, params: Mapping[str, Any], db: Any) -> Optional[JSONDict]: ...
