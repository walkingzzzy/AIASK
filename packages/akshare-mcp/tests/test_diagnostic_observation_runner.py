from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.incubation_factory.accelerator import IncubationAccelerator
from akshare_mcp.services.incubation_factory.metrics_recorder import MetricsRecorder
from akshare_mcp.services.incubation_factory.runner import IncubationFactoryRunner
from akshare_mcp.services.incubation_pipeline import StrategyIncubationPipelineService


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", raising=False)
    monkeypatch.delenv("INCUBATION_FACTORY_DIAGNOSTIC_BATCH_LIMIT", raising=False)
    yield


@pytest.mark.asyncio
async def test_runner_diagnostic_intake_disabled_by_default():
    runner = IncubationFactoryRunner(dry_run=True)
    db = MagicMock()
    db.list_diagnostic_observation_strategies = AsyncMock(return_value=[{"id": "s1"}])

    result = await runner._list_diagnostic_observation(db)

    assert result == []
    db.list_diagnostic_observation_strategies.assert_not_called()


@pytest.mark.asyncio
async def test_runner_diagnostic_intake_enabled_uses_batch_limit(monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", "1")
    monkeypatch.setenv("INCUBATION_FACTORY_DIAGNOSTIC_BATCH_LIMIT", "4")
    runner = IncubationFactoryRunner(dry_run=True)
    db = MagicMock()
    db.list_diagnostic_observation_strategies = AsyncMock(return_value=[{"id": "s1"}])

    result = await runner._list_diagnostic_observation(db)

    assert result == [{"id": "s1"}]
    db.list_diagnostic_observation_strategies.assert_called_once_with(limit=4)


@pytest.mark.asyncio
async def test_runner_diagnostic_intake_db_failure_returns_empty(monkeypatch):
    monkeypatch.setenv("INCUBATION_FACTORY_DIAGNOSTIC_INTAKE_ENABLED", "1")
    runner = IncubationFactoryRunner(dry_run=True)
    db = MagicMock()
    db.list_diagnostic_observation_strategies = AsyncMock(side_effect=RuntimeError("boom"))

    result = await runner._list_diagnostic_observation(db)

    assert result == []


@pytest.mark.asyncio
async def test_runner_records_diagnostic_processed_event():
    runner = IncubationFactoryRunner(dry_run=True)
    db = MagicMock()
    db.save_strategy_domain_event = AsyncMock()

    await runner._record_diagnostic_processed_event(
        db,
        {"id": "s1", "name": "diag", "strategy_type": "momentum"},
        {"primary_hit_rate": 0.35, "primary_skill_lcb": -0.01, "coverage_ratio": 0.7},
        {"signals_generated": 2},
    )

    db.save_strategy_domain_event.assert_called_once()
    event = db.save_strategy_domain_event.call_args[0][0]
    assert event["event_type"] == "incubation_factory.diagnostic_observation_processed"
    assert event["source"] == "incubation_factory_diagnostic"
    assert event["payload"]["stage"] == "diagnostic"
    assert event["payload"]["diagnostic_observation"] is True
    assert event["payload"]["signals_generated"] == 2


def test_metrics_recorder_uses_diagnostic_intake_stage():
    metric = MetricsRecorder()._build_metric(
        strategy={"id": "s1", "status": "submitted", "_intake_stage": "diagnostic"},
        verification={
            "primary_hit_rate": 0.35,
            "primary_skill_lcb": -0.01,
            "coverage_ratio": 0.7,
            "primary_effective_n": 3,
        },
        nav_info={},
        account_id="acct-1",
        metric_date=date(2026, 5, 29),
    )

    assert metric["stage"] == "diagnostic"
    assert metric["metadata"]["intake_stage"] == "diagnostic"
    assert metric["metadata"]["diagnostic_observation"] is True


def test_metrics_recorder_sanitizes_non_finite_values():
    metric = MetricsRecorder()._build_metric(
        strategy={"id": "s1", "status": "submitted", "_intake_stage": "diagnostic"},
        verification={
            "primary_hit_rate": "nan",
            "primary_skill_lcb": float("inf"),
            "recent_primary_skill_lcb": "-inf",
            "secondary_hit_rate": float("nan"),
            "secondary_skill_lcb": "inf",
            "stability_gap": "nan",
            "coverage_ratio": "-inf",
            "forward_sharpe": float("inf"),
            "forward_ic": float("nan"),
            "primary_effective_n": float("inf"),
            "secondary_effective_n": "nan",
            "total_signals": "-inf",
            "profile": float("nan"),
            "min_days_remaining": float("inf"),
        },
        nav_info={
            "total_value": "inf",
            "cash": float("nan"),
            "market_value": "-inf",
            "nav": "nan",
            "daily_return": float("inf"),
            "max_drawdown": "-inf",
        },
        account_id="acct-1",
        metric_date=date(2026, 5, 29),
    )

    assert metric["decision"] == "observe"
    assert metric["primary_effective_n"] == 0
    assert metric["metadata"]["profile"] is None
    json.dumps(metric, allow_nan=False)


@pytest.mark.asyncio
async def test_accelerator_rejects_non_finite_verification_metrics():
    class Db:
        async def list_strategy_incubation_metrics(self, strategy_id, limit):
            return [{"decision": "promote"} for _ in range(limit)]

    result = await IncubationAccelerator()._evaluate_single(
        Db(),
        {"id": "s1", "name": "bad"},
        {
            "primary_skill_lcb": float("inf"),
            "recent_primary_skill_lcb": "inf",
            "stability_gap": "-inf",
            "coverage_ratio": "inf",
            "primary_effective_n": 100,
        },
    )

    assert result["eligible"] is False
    assert result["reason"] == "skill_lcb_too_low"


@pytest.mark.asyncio
async def test_runner_pipeline_passes_paper_observation_strategies(monkeypatch):
    calls = {}

    class Pipeline:
        async def run_batch(self, db, **kwargs):
            calls.update(kwargs)
            return {
                "count": len(kwargs.get("strategies") or []),
                "auto_promoted": 0,
                "stage_counts": {},
            }

    monkeypatch.setattr(
        "akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service",
        lambda: Pipeline(),
    )
    runner = IncubationFactoryRunner(dry_run=False)
    strategies = [
        {"id": "incubating-1", "status": "incubating"},
        {"id": "paper-1", "status": "submitted", "_intake_stage": "paper"},
    ]

    result = await runner._run_pipeline(MagicMock(), strategies=strategies)

    assert result["count"] == 2
    assert calls["statuses"] == ["incubating"]
    assert [item["id"] for item in calls["strategies"]] == ["incubating-1", "paper-1"]
    assert calls["source"] == "incubation_factory"


@pytest.mark.asyncio
async def test_pipeline_run_batch_with_strategies_skips_status_query(monkeypatch):
    service = StrategyIncubationPipelineService()
    db = MagicMock()
    db.save_strategy_task_run = AsyncMock(return_value={"id": 7, "trace_id": "trace-1"})
    db.update_strategy_task_run = AsyncMock()
    db.save_strategy_domain_event = AsyncMock()
    db.list_strategies = AsyncMock(side_effect=AssertionError("status query should not run"))

    async def fake_run_strategy(db_arg, strategy, **kwargs):
        return {
            "strategy_id": strategy["id"],
            "snapshot": {"pipeline_stage": strategy.get("_expected_stage", "observe")},
            "auto_promoted": False,
            "task_run_id": kwargs.get("task_run_id"),
        }

    monkeypatch.setattr(service, "run_strategy", fake_run_strategy)

    result = await service.run_batch(
        db,
        strategies=[
            {"id": "paper-1", "_expected_stage": "warmup"},
            {"id": "paper-1", "_expected_stage": "warmup"},
            {"id": "paper-2", "_expected_stage": "observe"},
        ],
        source="incubation_factory",
    )

    assert result["count"] == 2
    assert result["stage_counts"] == {"warmup": 1, "observe": 1}
    db.list_strategies.assert_not_called()
    payload = db.save_strategy_task_run.call_args[0][0]["payload"]
    assert payload["provided_strategies"] is True
    assert payload["strategy_count"] == 3
