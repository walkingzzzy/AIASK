from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest

from strategy_factory.application.deduplicator import Deduplicator
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
from strategy_factory.application.submitter import StrategySubmitter


def _make_pseudo_klines(n: int = 60) -> list[dict]:
    rows = []
    price = 100.0
    for _ in range(n):
        open_price = price
        price = open_price * 1.001
        rows.append(
            {
                "open": round(open_price, 6),
                "high": round(price, 6),
                "low": round(open_price, 6),
                "close": round(price, 6),
                "volume": 1.0,
            }
        )
    return rows


class _InjectedValidationGateway:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def run_validation_report(self, strategy_type: str, params: dict, db):
        self.calls.append((strategy_type, dict(params or {})))
        return {
            "rating": {
                "grade": "A",
                "total_score": 88.0,
                "recommendation": "Strong",
            },
            "walk_forward": {"oos_rank_ic_mean": 0.08},
        }


class _InjectedRiskGateway:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def run_risk_report(self, strategy_type: str, params: dict, db):
        self.calls.append((strategy_type, dict(params or {})))
        return {"var_percent": 1.2, "cvar_percent": 1.8, "stress_loss_percent": -9.0}


class _InjectedIncubationGateway:
    def __init__(self):
        self.ensure_calls: list[dict] = []
        self.pipeline_calls: list[dict] = []

    async def ensure_account(self, db, strategy: dict, *, source_run_id=None, stage="warmup"):
        self.ensure_calls.append(
            {
                "strategy_id": strategy.get("id"),
                "source_run_id": source_run_id,
                "stage": stage,
            }
        )
        return {"account": {"id": "paper_acc_injected"}}

    async def run_pipeline(self, db, strategy: dict, *, source="strategy_factory_submit", auto_apply_review=False):
        self.pipeline_calls.append(
            {
                "strategy_id": strategy.get("id"),
                "status": strategy.get("status"),
                "source": source,
                "auto_apply_review": auto_apply_review,
            }
        )
        return {
            "task_run_id": 321,
            "snapshot": {
                "pipeline_stage": "warmup",
                "pipeline_status": "collecting",
                "readiness_score": 0.67,
            },
        }


class _InjectedVectorGateway:
    def __init__(self):
        self.calls: list[dict] = []
        self.last_backend_used = "index"
        self.last_meta = {"backend_requested": "index", "backend_used": "index"}

    def find_similar_patterns(self, **kwargs):
        self.calls.append(kwargs)
        return [{"code": "s1", "similarity": 0.97}]


@pytest.mark.asyncio
async def test_submitter_prefers_explicit_gateways_over_legacy_patch_points(monkeypatch):
    validation_gateway = _InjectedValidationGateway()
    risk_gateway = _InjectedRiskGateway()
    incubation_gateway = _InjectedIncubationGateway()
    submitter = StrategySubmitter(
        validation_gateway=validation_gateway,
        risk_gateway=risk_gateway,
        incubation_gateway=incubation_gateway,
    )

    db = MagicMock()
    db.save_strategy = AsyncMock()
    db.save_strategy_metrics = AsyncMock()
    db.update_strategy_status = AsyncMock()
    db.save_strategy_lineage = AsyncMock()
    db.save_strategy_quality_report = AsyncMock()
    db.save_strategy_generation_experiment = AsyncMock()

    monkeypatch.setattr(
        "akshare_mcp.services.strategy_factory._run_validation_report",
        AsyncMock(side_effect=AssertionError("legacy validation runner should not be used")),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.strategy_factory._run_risk_report",
        AsyncMock(side_effect=AssertionError("legacy risk runner should not be used")),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.strategy_factory.submission_gate.run_submission_quality_gate",
        AsyncMock(return_value={"passed": True, "reasons": [], "reason_codes": []}),
    )

    class _DummyVectorPlatform:
        async def build_strategy_profile(self, *_args, **_kwargs):
            return {"id": 9, "backend": "index", "metadata": {"audit": {"backend_used": "index"}}}

    monkeypatch.setattr(
        "akshare_mcp.services.vector_platform.get_strategy_vector_platform",
        lambda: _DummyVectorPlatform(),
    )

    result = await submitter.submit(
        [
            {
                "strategy_type": "momentum",
                "params": {"lookback": 20, "threshold": 0.02},
                "backtest_metrics": {
                    "sharpe_ratio": 1.2,
                    "total_return": 0.18,
                    "max_drawdown": 0.08,
                    "win_rate": 0.57,
                    "trades_count": 6,
                },
                "spawn_reason": "adapter injection",
            }
        ],
        {"date": "2026-03-20", "fg_level": "neutral", "fear_greed_index": 52},
        db,
    )

    assert len(validation_gateway.calls) == 1
    assert len(risk_gateway.calls) == 1
    validation_strategy_type, validation_params = validation_gateway.calls[0]
    risk_strategy_type, risk_params = risk_gateway.calls[0]
    assert validation_strategy_type == "momentum"
    assert risk_strategy_type == "momentum"
    assert validation_params["lookback"] == 20
    assert validation_params["threshold"] == 0.02
    assert "holding_horizon" in validation_params
    assert "trade_plan" in validation_params
    assert "risk_rules" in validation_params
    assert "validation_profile" in validation_params
    assert validation_params["task_signature"].startswith("snapshot|")
    assert risk_params == validation_params
    assert len(incubation_gateway.ensure_calls) == 1
    assert len(incubation_gateway.pipeline_calls) == 1
    assert result["passed_quality_gate"] == 1
    assert result["strategies"][0]["incubation_account_id"] == "paper_acc_injected"
    assert result["strategies"][0]["incubation_task_run_id"] == 321


@pytest.mark.asyncio
async def test_deduplicator_prefers_explicit_vector_gateway(monkeypatch):
    vector_gateway = _InjectedVectorGateway()
    dedup = Deduplicator(vector_gateway=vector_gateway)
    db = MagicMock()
    db.list_strategies = AsyncMock(
        side_effect=[
            [{"id": "s1", "name": "既有策略", "status": "incubating", "strategy_type": "momentum", "params": {"lookback": 18, "threshold": 0.03}}],
            [],
        ]
    )

    async def _fake_gather(payloads, _db):
        return [_make_pseudo_klines() for _ in payloads]

    monkeypatch.setattr(dedup, "_bounded_behavior_gather", _fake_gather)

    unique = await dedup.deduplicate(
        [{"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}}],
        db,
    )

    assert unique == []
    assert len(vector_gateway.calls) == 1
    assert set(vector_gateway.calls[0]["candidate_klines_dict"]) == {"s1"}
    assert dedup.get_last_report()["dropped"][0]["dedup_result"]["match_type"] == "vector"
    assert dedup.get_last_report()["dropped"][0]["dedup_result"]["vector_backend"] == "index"


def test_scheduler_passes_explicit_gateways_to_migrated_modules():
    validation_gateway = object()
    risk_gateway = object()
    incubation_gateway = object()
    vector_gateway = object()
    scheduler = StrategyFactoryScheduler(
        vector_gateway=vector_gateway,
        validation_gateway=validation_gateway,
        risk_gateway=risk_gateway,
        incubation_gateway=incubation_gateway,
    )

    class _DummyDedup:
        def __init__(self, *, vector_gateway=None):
            self.vector_gateway = vector_gateway

    class _DummySubmitter:
        def __init__(self, *, validation_gateway=None, risk_gateway=None, incubation_gateway=None):
            self.validation_gateway = validation_gateway
            self.risk_gateway = risk_gateway
            self.incubation_gateway = incubation_gateway

    dedup = scheduler._build_deduplicator(SimpleNamespace(Deduplicator=_DummyDedup))
    submitter = scheduler._build_submitter(SimpleNamespace(StrategySubmitter=_DummySubmitter))

    assert dedup.vector_gateway is vector_gateway
    assert submitter.validation_gateway is validation_gateway
    assert submitter.risk_gateway is risk_gateway
    assert submitter.incubation_gateway is incubation_gateway


class _InjectedAutonomyGateway:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate_factory_candidates(self, db, snapshot, *, limit=4, research_task=None, source=""):
        self.calls.append(
            {
                "db_type": type(db).__name__,
                "snapshot_date": snapshot.get("date"),
                "limit": limit,
                "research_task": dict(research_task or {}),
                "source": source,
            }
        )
        return {
            "generated_count": 1,
            "reviewed_count": 1,
            "candidates": [
                {
                    "strategy_type": "dsl_rule",
                    "params": {"dsl": {"metadata": {"target_symbols": ["688981"]}}},
                    "generator_type": "external_llm",
                    "target_symbols": ["688981"],
                    "stock_pool": {"selection_mode": "explicit", "symbols": ["688981"]},
                    "tags": ["external_llm", "ai_generated"],
                }
            ],
            "experiments": [{"task_id": (research_task or {}).get("task_id")}],
            "llm_generation": {"external_provider": {"status": "succeeded", "requests": [], "selected_count": 1, "elapsed_seconds": 0.1}},
        }


class _InjectedFactorResearchGateway:
    def __init__(self):
        self.calls: list[dict] = []

    async def build_artifact(self, db, snapshot):
        self.calls.append(
            {
                "db_type": type(db).__name__,
                "snapshot_date": snapshot.get("date"),
            }
        )
        return {
            "active_factors": ["value"],
            "preferred_strategy_types": ["value_factor"],
            "degraded": False,
            "summary": {
                "active_factor_count": 1,
                "top_factor_names": ["value"],
                "preferred_strategy_types": ["value_factor"],
            },
        }

    def status(self):
        return {"running": False}


@pytest.mark.asyncio
async def test_scheduler_run_once_prefers_explicit_autonomy_and_factor_research_gateways(monkeypatch):
    autonomy_gateway = _InjectedAutonomyGateway()
    factor_research_gateway = _InjectedFactorResearchGateway()
    scheduler = StrategyFactoryScheduler(
        autonomy_gateway=autonomy_gateway,
        factor_research_gateway=factor_research_gateway,
    )

    db = MagicMock()
    db.save_strategy_factory_run = AsyncMock()
    db.save_daily_snapshot = AsyncMock()
    db.save_strategy_task_run = AsyncMock(return_value={"id": 1})
    db.update_strategy_task_run = AsyncMock()

    class _DummyCollector:
        async def collect(self, _db):
            return {
                "date": "2026-03-20",
                "fear_greed_index": 58,
                "fg_level": "neutral",
                "listed_count": 1,
                "incubating_count": 0,
                "degraded": False,
                "completeness": {"completion_ratio": 1.0, "missing_sources": []},
                "failure_reasons": [],
            }

    class _DummySpawner:
        def spawn(self, _snapshot):
            return []

        def get_last_report(self):
            return {"summary": {"candidate_count": 0, "quota_fill_count": 0, "signal_trigger_count": 0}}

    class _DummyFilter:
        async def filter(self, candidates, _db):
            return candidates

        def get_last_report(self):
            return {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0, "failed_reason_counts": {}, "thresholds_by_type": {}}, "passed": [], "failed": []}

    class _DummyDedup:
        async def deduplicate(self, candidates, _db):
            return candidates

        def get_last_report(self):
            return {"summary": {"input_count": 1, "kept_count": 1, "dropped_count": 0}, "kept": [], "dropped": []}

    class _DummySubmitter:
        async def submit(self, candidates, _snapshot, _db):
            return {
                "submitted": len(candidates),
                "passed_quality_gate": len(candidates),
                "gate_3_passed": len(candidates),
                "gate_3_failed": 0,
                "gate_3_provisional_passed": 0,
                "gate_3_failure_reason_topn": [],
                "strategies": list(candidates),
            }

    class _DummyEliminator:
        async def check(self, _db, _fg_level):
            return []

    async def _scan(_self, _db, _snapshot):
        return {
            "summary": {"task_count": 1, "task_sources": {"snapshot": 1}, "task_types": {"sector_breakout": 1}},
            "tasks": [
                {
                    "task_id": "task_value",
                    "task_key": "task_value",
                    "task_source": "snapshot",
                    "opportunity_type": "sector_breakout",
                    "target_symbols": ["688981"],
                    "generation_limit": 1,
                }
            ],
        }

    monkeypatch.setattr("akshare_mcp.storage.get_db", lambda: db)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.DataCollector", _DummyCollector)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySpawner", _DummySpawner)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.BacktestFilter", _DummyFilter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.Deduplicator", _DummyDedup)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.StrategySubmitter", _DummySubmitter)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.EliminationChecker", _DummyEliminator)
    monkeypatch.setattr("akshare_mcp.services.strategy_factory.MarketOpportunityScanner.scan", _scan)
    monkeypatch.setattr(
        "akshare_mcp.services.strategy_factory.FactorResearchBuilder.build",
        AsyncMock(side_effect=AssertionError("legacy factor research builder should not be used")),
    )
    monkeypatch.setattr(
        "akshare_mcp.services.strategy_autonomy.get_strategy_autonomy_service",
        lambda: MagicMock(generate_factory_candidates=AsyncMock(side_effect=AssertionError("legacy autonomy service should not be used"))),
    )

    result = await scheduler.run_once()

    assert result["status"] == "success"
    assert factor_research_gateway.calls == [{"db_type": "MagicMock", "snapshot_date": "2026-03-20"}]
    assert autonomy_gateway.calls[0]["db_type"] == "MagicMock"
    assert autonomy_gateway.calls[0]["research_task"]["task_id"] == "task_value"
    assert result["summary"]["active_factor_count"] == 1
    assert result["summary"]["autonomy_generated"] == 1


def test_scheduler_accepts_runtime_adapter_bundle_for_all_gateway_slots():
    bundle = SimpleNamespace(
        vector_search=object(),
        validation=object(),
        risk=object(),
        incubation=object(),
        autonomy=object(),
        factor_research=object(),
    )
    scheduler = StrategyFactoryScheduler(runtime_adapters=bundle)

    assert scheduler._vector_gateway is bundle.vector_search
    assert scheduler._validation_gateway is bundle.validation
    assert scheduler._risk_gateway is bundle.risk
    assert scheduler._incubation_gateway is bundle.incubation
    assert scheduler._autonomy_gateway is bundle.autonomy
    assert scheduler._factor_research_gateway is bundle.factor_research


def test_scheduler_uses_market_timezone_aware_clock():
    scheduler = StrategyFactoryScheduler()

    now = scheduler._now()

    assert now.tzinfo is not None
    assert now.utcoffset() is not None
