"""Typed contracts for the strategy_factory migration."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable


JSONDict = dict[str, Any]


@runtime_checkable
class StrategyFactoryRepository(Protocol):
    """Minimal repository contract observed in the current factory implementation."""

    async def get_klines(self, code: str, limit: int = 500) -> list[Mapping[str, Any]]: ...

    async def get_limit_up_stats(self) -> Mapping[str, Any]: ...

    async def get_factor_ic_history(self, factor_name: str, horizon: str, limit: int) -> list[Mapping[str, Any]]: ...

    async def count_strategies_by_type(self, status: str) -> Mapping[str, int]: ...

    async def save_daily_snapshot(self, snapshot_date: Any, snapshot: Mapping[str, Any]) -> Any: ...

    async def list_strategies(self, status: str, limit: int = 500) -> list[Mapping[str, Any]]: ...

    async def get_strategy_metrics(self, strategy_id: str) -> list[Mapping[str, Any]]: ...

    async def save_strategy(self, data: Mapping[str, Any]) -> Any: ...

    async def update_strategy_status(self, strategy_id: str, status: str, **kwargs: Any) -> Any: ...

    async def save_strategy_lineage(
        self,
        strategy_id: str,
        parent_strategy_id: Optional[str],
        reason: str,
        snapshot: Mapping[str, Any],
    ) -> Any: ...

    async def save_strategy_metrics(self, strategy_id: str, period: str, payload: Mapping[str, Any]) -> Any: ...

    async def save_strategy_factory_run(self, results: Mapping[str, Any]) -> Any: ...


@runtime_checkable
class VectorSearchGateway(Protocol):
    async def find_similar(self, candidate: Mapping[str, Any], existing: list[Mapping[str, Any]]) -> JSONDict: ...


@runtime_checkable
class AutonomyGateway(Protocol):
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
    def status(self) -> Mapping[str, Any]: ...


@runtime_checkable
class IncubationGateway(Protocol):
    async def submit(self, strategy: Mapping[str, Any], payload: Optional[Mapping[str, Any]] = None) -> JSONDict: ...


@runtime_checkable
class ValidationGateway(Protocol):
    async def run_validation_report(self, strategy_type: str, params: Mapping[str, Any], db: Any) -> Optional[JSONDict]: ...


@runtime_checkable
class RiskGateway(Protocol):
    async def run_risk_report(self, strategy_type: str, params: Mapping[str, Any], db: Any) -> Optional[JSONDict]: ...
