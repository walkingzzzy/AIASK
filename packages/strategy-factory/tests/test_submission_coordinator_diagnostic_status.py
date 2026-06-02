from __future__ import annotations

import pytest

from strategy_factory.application.services.submission_coordinator import StrategyUpsertService


class _DB:
    def __init__(self) -> None:
        self.saved_strategy: dict | None = None

    async def save_strategy(self, data: dict) -> dict:
        self.saved_strategy = dict(data)
        return dict(data)


class _Submitter:
    def __init__(self) -> None:
        self.status_updates: list[dict] = []

    async def _persist_metrics(self, strategy_id, metrics, validation_report, risk_report, db) -> None:
        return None

    async def _update_strategy_status(
        self,
        db,
        strategy_id,
        status,
        *,
        actor_id,
        reason,
        metadata,
    ) -> None:
        self.status_updates.append(
            {
                "strategy_id": strategy_id,
                "status": status,
                "actor_id": actor_id,
                "reason": reason,
                "metadata": dict(metadata or {}),
            }
        )


@pytest.mark.asyncio
async def test_diagnostic_candidate_save_payload_uses_diagnostic_status(monkeypatch):
    monkeypatch.delenv("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_STATUS", raising=False)
    db = _DB()
    submitter = _Submitter()

    persisted = await StrategyUpsertService(submitter).persist_candidate(
        strategy_id="diag-1",
        candidate={
            "diagnostic_observation": True,
            "diagnostic_fingerprint": "diag_same",
            "diagnostic_reason": "win_rate_0_372_0_400",
        },
        data={"id": "diag-1", "status": "draft"},
        metrics={},
        validation_report=None,
        risk_report=None,
        gate={"passed": False},
        db=db,
        refresh_existing=False,
        read_only=False,
    )

    assert persisted is True
    assert db.saved_strategy is not None
    assert db.saved_strategy["status"] == "diagnostic"
    assert submitter.status_updates[0]["status"] == "diagnostic"
    assert submitter.status_updates[0]["reason"] == "factory_submit_diagnostic_observation"


@pytest.mark.asyncio
async def test_diagnostic_candidate_save_payload_honors_status_rollback(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_DIAGNOSTIC_OBSERVATION_STATUS", "submitted")
    db = _DB()
    submitter = _Submitter()

    await StrategyUpsertService(submitter).persist_candidate(
        strategy_id="diag-rollback",
        candidate={"diagnostic_observation": True},
        data={"id": "diag-rollback", "status": "draft"},
        metrics={},
        validation_report=None,
        risk_report=None,
        gate={"passed": False},
        db=db,
        refresh_existing=False,
        read_only=False,
    )

    assert db.saved_strategy is not None
    assert db.saved_strategy["status"] == "submitted"
    assert submitter.status_updates[0]["status"] == "submitted"
