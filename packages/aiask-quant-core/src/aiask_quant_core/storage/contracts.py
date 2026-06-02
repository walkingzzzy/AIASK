"""Shared storage contracts for Strategy Factory persistence."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable


REQUIRED_REPOSITORY_METHODS: tuple[str, ...] = (
    "get_klines",
    "get_limit_up_stats",
    "get_factor_ic_history",
    "count_strategies_by_type",
    "save_daily_snapshot",
    "list_strategies",
    "get_strategy",
    "get_strategy_metrics",
    "get_signal_stats",
    "save_strategy",
    "save_strategy_quality_report",
    "update_strategy_status",
    "save_strategy_lineage",
    "save_strategy_metrics",
    "save_elimination_log",
    "get_strategy_generation_experiment",
    "save_strategy_generation_experiment",
    "save_factory_task_evidence",
    "save_strategy_candidate_evidence",
    "save_strategy_signal_evidence",
    "save_strategy_task_run",
    "update_strategy_task_run",
    "list_stock_universe",
    "list_factory_event_clusters",
    "save_factory_theme_definition",
    "save_strategy_factory_run",
    "list_strategy_factory_runs",
    "get_strategy_factory_run",
    "get_latest_strategy_factory_run",
    "save_strategy_factory_run_artifact",
    "list_strategy_factory_run_artifacts",
    "save_scheduler_state",
    "load_scheduler_state",
    "create_strategy_factory_dispatch",
    "update_strategy_factory_dispatch",
    "get_strategy_factory_dispatch",
)


@runtime_checkable
class StrategyFactoryRepository(Protocol):
    """Repository contract observed across Strategy Factory storage hosts."""

    async def get_klines(self, code: str, limit: int = 500) -> list[Mapping[str, Any]]: ...

    async def get_limit_up_stats(self) -> Mapping[str, Any]: ...

    async def get_factor_ic_history(self, factor_name: str, horizon: str, limit: int) -> list[Mapping[str, Any]]: ...

    async def count_strategies_by_type(self, status: str) -> Mapping[str, int]: ...

    async def save_daily_snapshot(self, snapshot_date: Any, snapshot: Mapping[str, Any]) -> Any: ...

    async def list_strategies(self, status: str, limit: int = 500) -> list[Mapping[str, Any]]: ...

    async def get_strategy(self, strategy_id: str) -> Optional[Mapping[str, Any]]: ...

    async def get_strategy_metrics(self, strategy_id: str) -> list[Mapping[str, Any]]: ...

    async def get_signal_stats(
        self,
        strategy_id: str,
        lookback_days: int | None = None,
        eps: float | None = None,
    ) -> Mapping[str, Any]: ...

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

    async def save_strategy_candidate_evidence(self, payload: Mapping[str, Any]) -> Any: ...

    async def save_strategy_signal_evidence(self, payload: Mapping[str, Any]) -> Any: ...

    async def save_strategy_task_run(self, payload: Mapping[str, Any]) -> Any: ...

    async def update_strategy_task_run(self, task_run_id: Any, **kwargs: Any) -> Any: ...

    async def list_stock_universe(self, limit: int = 200, offset: int = 0) -> list[Mapping[str, Any]]: ...

    async def list_factory_event_clusters(self, status: Optional[str] = None, limit: int = 200) -> list[Mapping[str, Any]]: ...

    async def save_factory_theme_definition(self, payload: Mapping[str, Any]) -> Any: ...

    async def save_strategy_factory_run(self, results: Mapping[str, Any]) -> Any: ...

    async def list_strategy_factory_runs(self, limit: int = 20) -> list[Mapping[str, Any]]: ...

    async def get_strategy_factory_run(self, run_id: str) -> Optional[Mapping[str, Any]]: ...

    async def get_latest_strategy_factory_run(self) -> Optional[Mapping[str, Any]]: ...

    async def save_strategy_factory_run_artifact(self, payload: Mapping[str, Any]) -> Any: ...

    async def list_strategy_factory_run_artifacts(self, run_id: str) -> list[Mapping[str, Any]]: ...

    async def save_scheduler_state(self, payload: Mapping[str, Any]) -> Any: ...

    async def load_scheduler_state(self, state_key: str = "strategy_factory_scheduler") -> Mapping[str, Any]: ...

    async def create_strategy_factory_dispatch(self, payload: Mapping[str, Any]) -> Any: ...

    async def update_strategy_factory_dispatch(self, dispatch_id: str, **kwargs: Any) -> Any: ...

    async def get_strategy_factory_dispatch(self, dispatch_id: str) -> Optional[Mapping[str, Any]]: ...

    async def list_strategy_factory_dispatches(
        self,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[Mapping[str, Any]]: ...


__all__ = ["REQUIRED_REPOSITORY_METHODS", "StrategyFactoryRepository"]
