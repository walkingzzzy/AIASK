from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.incubation_factory.metrics_recorder import MetricsRecorder
from akshare_mcp.services.incubation_factory.runner import IncubationFactoryRunner


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


@pytest.mark.asyncio
async def test_pipeline_stays_restricted_to_incubating(monkeypatch):
    calls = {}

    class Pipeline:
        async def run_batch(self, db, **kwargs):
            calls.update(kwargs)
            return {"count": 1, "auto_promoted": 0, "stage_counts": {}}

    monkeypatch.setattr(
        "akshare_mcp.services.incubation_pipeline.get_strategy_incubation_pipeline_service",
        lambda: Pipeline(),
    )
    runner = IncubationFactoryRunner(dry_run=False)

    result = await runner._run_pipeline(MagicMock())

    assert result["count"] == 1
    assert calls["statuses"] == ["incubating"]
    assert calls["source"] == "incubation_factory"
