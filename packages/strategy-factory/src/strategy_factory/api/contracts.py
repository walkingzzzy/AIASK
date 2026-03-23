"""Typed contracts for the strategy_factory migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable


JSONDict = dict[str, Any]


# ---------------------------------------------------------------------------
# Strategy object protocol types (WP0)
# ---------------------------------------------------------------------------


@dataclass
class StrategyResearchContract:
    """Research task binding contract for a candidate."""

    task_id: str = ""
    task_source: str = ""
    opportunity_type: str = ""
    preferred_strategy_types: list[str] = field(default_factory=list)
    allowed_strategy_types: list[str] = field(default_factory=list)
    preference_strength: str = "soft"
    target_symbols: list[str] = field(default_factory=list)
    stock_pool: JSONDict = field(default_factory=dict)
    target_symbol_policy: str = "prefer_intersection"
    universe_expansion_policy: str = "allow_market_fallback"
    validation_focus: str = "target_plus_representative"
    event_window: JSONDict = field(default_factory=dict)
    estimation_window: JSONDict = field(default_factory=dict)
    holding_window: JSONDict = field(default_factory=dict)
    task_signature: str = ""


@dataclass
class StrategyTargetingPolicy:
    """Relationship between candidate and research-task target pools."""

    target_symbol_policy: str = "prefer_intersection"
    universe_expansion_policy: str = "allow_market_fallback"
    validation_focus: str = "target_plus_representative"
    constraint_violation: bool = False
    expansion_applied: bool = False
    expansion_reason: Optional[str] = None
    expansion_source: Optional[str] = None
    coverage_ratio: float = 0.0
    intersection_ratio: float = 0.0


@dataclass
class StrategyPortfolioSpec:
    """Portfolio / position sizing semantics."""

    position_assumption: str = "single_name_full_notional"
    target_weight_scheme: str = "single_name"
    max_position_pct: Optional[float] = None
    target_weight_map: JSONDict = field(default_factory=dict)


@dataclass
class StrategyExecutionAssumptions:
    """Execution and cost assumptions for a candidate."""

    commission_rate: float = 0.00025
    slippage_bps: float = 0.0
    slippage_model: str = "fixed"
    market_impact_bps: float = 0.0
    tradability_filter: bool = True
    capacity_participation_rate: float = 0.0
    adv_ratio_limit: float = 0.0
    capacity_bucket: Optional[str] = None


@dataclass
class StrategyValidationProfile:
    """Gate-1 / Gate-2 / Gate-3 primary validation protocol."""

    profile: str = "trade_rule_validation"
    validation_focus: str = "target_plus_representative"
    primary_validation_layer: str = "target"


@dataclass
class StrategySubmissionAudit:
    """Submission and audit trail for a candidate."""

    constraint_check: JSONDict = field(default_factory=dict)
    attempt_adjustment: JSONDict = field(default_factory=dict)
    task_signature: str = ""
    refresh_mode: str = ""
    primary_validation_layer: str = "target"
    event_window_config: JSONDict = field(default_factory=dict)
    cost_assumptions: JSONDict = field(default_factory=dict)
    position_assumption: str = ""
    candidate_provenance: JSONDict = field(default_factory=dict)


@dataclass(frozen=True)
class FactoryBacktestAssumptions:
    """Normalized execution assumptions shared by the factory backtest path."""

    initial_capital: float = 100000.0
    commission_rate: float = 0.00025
    slippage_bps: float = 0.0
    market_impact_bps: float = 0.0
    arrival_price_policy: str = "next_open_proxy"
    implementation_shortfall_proxy: float = 0.0
    tradability_filter: bool = True
    slippage_model: str = "fixed"
    max_position_pct: Optional[float] = None
    capacity_participation_rate: float = 0.0
    adv_ratio_limit: float = 0.0
    capacity_bucket: Optional[str] = None
    position_assumption: str = "single_name_full_notional"
    target_weight_scheme: str = "single_name"
    validation_focus: str = "target_plus_representative"

    def to_backtest_kwargs(self) -> JSONDict:
        return {
            "initial_capital": float(self.initial_capital),
            "commission": float(self.commission_rate),
            "slippage": float(self.slippage_bps) / 10000.0,
            "market_impact_bps": float(self.market_impact_bps),
            "arrival_price_policy": str(self.arrival_price_policy or "next_open_proxy"),
            "implementation_shortfall_proxy": float(self.implementation_shortfall_proxy),
            "tradability_filter": bool(self.tradability_filter),
            "slippage_model": str(self.slippage_model or "fixed"),
            "max_position_pct": float(self.max_position_pct) if self.max_position_pct is not None else None,
            "capacity_participation_rate": float(self.capacity_participation_rate),
            "adv_ratio_limit": float(self.adv_ratio_limit),
            "capacity_bucket": self.capacity_bucket,
            "position_assumption": str(self.position_assumption or "single_name_full_notional"),
            "target_weight_scheme": str(self.target_weight_scheme or "single_name"),
            "validation_focus": str(self.validation_focus or "target_plus_representative"),
        }

    def to_audit_dict(self) -> JSONDict:
        return {
            "initial_capital": float(self.initial_capital),
            "commission_rate": float(self.commission_rate),
            "slippage_bps": float(self.slippage_bps),
            "market_impact_bps": float(self.market_impact_bps),
            "arrival_price_policy": str(self.arrival_price_policy or "next_open_proxy"),
            "implementation_shortfall_proxy": float(self.implementation_shortfall_proxy),
            "tradability_filter": bool(self.tradability_filter),
            "slippage_model": str(self.slippage_model or "fixed"),
            "max_position_pct": float(self.max_position_pct) if self.max_position_pct is not None else None,
            "capacity_participation_rate": float(self.capacity_participation_rate),
            "adv_ratio_limit": float(self.adv_ratio_limit),
            "capacity_bucket": self.capacity_bucket,
            "position_assumption": str(self.position_assumption or "single_name_full_notional"),
            "target_weight_scheme": str(self.target_weight_scheme or "single_name"),
            "validation_focus": str(self.validation_focus or "target_plus_representative"),
        }


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

    async def refresh(self) -> JSONDict: ...


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
