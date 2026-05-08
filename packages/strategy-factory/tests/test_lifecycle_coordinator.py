from __future__ import annotations

import asyncio

from strategy_factory.application.services import lifecycle_coordinator as lifecycle_module


class _FakeDb:
    def __init__(self) -> None:
        self.saved_task_runs: list[dict] = []
        self.updated_task_runs: list[dict] = []
        self.saved_domain_events: list[dict] = []
        self.saved_snapshots: list[dict] = []

    async def save_strategy_task_run(self, payload: dict):
        row = {"id": len(self.saved_task_runs) + 1, **payload}
        self.saved_task_runs.append(row)
        return row

    async def update_strategy_task_run(self, task_run_id: int, **payload):
        row = {"id": task_run_id, **payload}
        self.updated_task_runs.append(row)
        return row

    async def upsert_execution_audit_snapshot(self, payload: dict):
        self.saved_snapshots.append(dict(payload))
        return dict(payload)

    async def save_strategy_domain_event(self, payload: dict):
        row = {"id": len(self.saved_domain_events) + 1, **payload}
        self.saved_domain_events.append(row)
        return row


class _FakeIncubationGateway:
    def __init__(self) -> None:
        self.ensure_calls: list[dict] = []
        self.pipeline_calls: list[dict] = []

    async def ensure_account(self, db, strategy: dict, **kwargs):
        self.ensure_calls.append({"strategy": dict(strategy), "kwargs": dict(kwargs)})
        return {"account": {"id": "paper-1"}, "binding": {"account_id": "paper-1"}}

    async def run_pipeline(self, db, strategy: dict, **kwargs):
        self.pipeline_calls.append({"strategy": dict(strategy), "kwargs": dict(kwargs)})
        return {
            "snapshot": {
                "id": "pipeline-1",
                "pipeline_stage": "observe",
                "pipeline_status": "ok",
                "readiness_score": 0.82,
                "closure_snapshot_id": "cls-1",
                "oversized_blob": {"x": "y" * 1024},
            },
            "status": "ok",
            "task_run_id": 77,
        }


class _FakeSubmitter:
    def __init__(self, *, enable_backtest: bool = True) -> None:
        self.gateway = _FakeIncubationGateway()
        self.paper_calls: list[dict] = []
        self.live_calls: list[dict] = []
        self.backtest_calls: list[dict] = []
        self.backtest_metrics_by_period: dict[str, dict] = {}
        self.enable_backtest = enable_backtest

    def _get_incubation_gateway(self):
        return self.gateway

    async def _enqueue_paper_observation(self, db, strategy: dict, snapshot: dict):
        self.paper_calls.append({"strategy": dict(strategy), "snapshot": dict(snapshot)})
        return {"paper_account_id": "paper-observe-1", "paper_lane_ready": True}

    async def _enqueue_live_ready_review(self, db, strategy: dict, snapshot: dict, gate: dict, *, trace_context=None):
        self.live_calls.append(
            {
                "strategy": dict(strategy),
                "snapshot": dict(snapshot),
                "gate": dict(gate),
                "trace_context": dict(trace_context or {}),
            }
        )
        return {"promotion_review_id": "promo-1", "final_status": "listed", "submission_action_completed": True}

    async def _backtest_strategy(self, strategy: dict, *, start_date: str, end_date: str):
        if not self.enable_backtest:
            raise AssertionError("backtest should be disabled for this fake submitter")
        self.backtest_calls.append({"strategy": dict(strategy), "start_date": start_date, "end_date": end_date})
        return dict(self.backtest_metrics_by_period.get(start_date) or {"max_drawdown": 0.12, "sharpe_ratio": 0.4, "total_return": 0.03})


class _FakeSubmitterWithoutBacktest:
    def __init__(self) -> None:
        self.gateway = _FakeIncubationGateway()
        self.paper_calls: list[dict] = []
        self.live_calls: list[dict] = []

    def _get_incubation_gateway(self):
        return self.gateway

    async def _enqueue_paper_observation(self, db, strategy: dict, snapshot: dict):
        self.paper_calls.append({"strategy": dict(strategy), "snapshot": dict(snapshot)})
        return {"paper_account_id": "paper-observe-1", "paper_lane_ready": True}

    async def _enqueue_live_ready_review(self, db, strategy: dict, snapshot: dict, gate: dict, *, trace_context=None):
        self.live_calls.append({"strategy": dict(strategy), "snapshot": dict(snapshot), "gate": dict(gate), "trace_context": dict(trace_context or {})})
        return {"promotion_review_id": "promo-1", "final_status": "listed", "submission_action_completed": True}


def _make_request(*, lane: str, passed: bool, final_status: str = "submitted"):
    return lifecycle_module.LifecycleTransitionRequest(
        strategy_id="strategy-1",
        name="Strategy One",
        candidate={
            "params": {
                "prediction_trace_id": "pred-1",
                "task_run_id": "parent-1",
            },
            "factory_run_id": "factory-run-1",
        },
        data={"strategy_type": "momentum"},
        gate={
            "passed": passed,
            "provisional_pass": passed,
            "execution_audit_gate_status": "passed" if passed else "failed_metrics",
            "execution_audit_gate_reasons": [] if passed else ["max_drawdown"],
            "execution_hard_gate_passed": passed,
            "audit": {"realized_trade_count": 24 if passed else 3},
        },
        quality_report={"summary": {"validation_grade": "A"}},
        snapshot={"date": "2026-04-20"},
        submission_lane=lane,
        submission_action={
            "final_status": final_status,
            "submission_action_trigger": "quality_gate_passed" if passed else "quality_gate_failed",
        },
        factory_run_id="factory-run-1",
        correlation_id="corr-1",
        source_action="strategy_factory_submit",
        quality_gate_summary={"validation_grade": "A"},
    )


def test_lifecycle_coordinator_formal_incubation_path_persists_snapshot_and_trace(monkeypatch):
    db = _FakeDb()
    submitter = _FakeSubmitter()
    coordinator = lifecycle_module.StrategyLifecycleCoordinator(submitter)
    status_updates: list[dict] = []
    vector_calls: list[dict] = []

    async def _fake_update_strategy_status(db, strategy_id: str, status: str, **kwargs):
        status_updates.append({"strategy_id": strategy_id, "status": status, "kwargs": dict(kwargs)})
        return {"strategy_id": strategy_id, "status": status}

    async def _fake_build_vector_profile(db, strategy: dict):
        vector_calls.append(dict(strategy))
        return {
            "id": "vector-1",
            "backend": "pgvector",
            "collection_name": "strategy_behavior",
            "metadata": {"audit": {"score": 1, "oversized_blob": "z" * 1024}},
        }

    monkeypatch.setattr(lifecycle_module, "_update_strategy_status", _fake_update_strategy_status)
    monkeypatch.setattr(lifecycle_module, "build_strategy_vector_profile", _fake_build_vector_profile)

    result = asyncio.run(
        coordinator.execute(
            db,
            _make_request(lane="formal_incubation", passed=True),
        )
    )

    assert result.final_status == "incubating"
    assert result.action_refs["lifecycle_task_run_id"] == 1
    assert result.action_refs["incubation_account_id"] == "paper-1"
    assert result.action_refs["vector_profile_id"] == "vector-1"
    assert [step.step for step in result.steps] == [
        "status_transition",
        "ensure_incubation_account",
        "run_incubation_pipeline",
        "build_vector_profile",
    ]
    assert status_updates[0]["status"] == "incubating"
    assert db.saved_snapshots[0]["correlation_id"] == "corr-1"
    assert submitter.gateway.ensure_calls[0]["strategy"]["_closure_trace"]["correlation_id"] == "corr-1"
    assert submitter.gateway.pipeline_calls[0]["strategy"]["status"] == "incubating"
    assert vector_calls[0]["_closure_trace"]["factory_run_id"] == "factory-run-1"
    assert len(submitter.backtest_calls) == 5
    assert submitter.backtest_calls[0]["start_date"] == "2015-06-12"
    assert submitter.backtest_calls[-1]["end_date"] == "2024-02-05"
    persisted_result = dict(db.updated_task_runs[-1]["result"] or {})
    assert persisted_result["incubation_pipeline"] == {
        "task_run_id": 77,
        "status": "ok",
        "id": "pipeline-1",
        "pipeline_stage": "observe",
        "pipeline_status": "ok",
        "readiness_score": 0.82,
        "closure_snapshot_id": "cls-1",
    }
    assert "oversized_blob" not in persisted_result["incubation_pipeline"]
    assert persisted_result["vector_profile"] == {
        "id": "vector-1",
        "backend": "pgvector",
        "collection_name": "strategy_behavior",
    }
    assert persisted_result["vector_audit"] == {"score": 1}
    assert persisted_result["stress_test_summary"] == {
        "overall_verdict": "pass",
        "failed_count": 0,
        "total_scenarios": 5,
        "evidence_mode": "historical_backtest",
        "diagnostic_only": False,
    }


def test_lifecycle_coordinator_formal_incubation_stress_reject_blocks_side_effects(monkeypatch):
    db = _FakeDb()
    submitter = _FakeSubmitter()
    submitter.backtest_metrics_by_period = {
        "2015-06-12": {"max_drawdown": 0.55, "sharpe_ratio": -4.0, "total_return": -0.35},
        "2016-01-04": {"max_drawdown": 0.50, "sharpe_ratio": -3.5, "total_return": -0.2},
    }
    coordinator = lifecycle_module.StrategyLifecycleCoordinator(submitter)
    status_updates: list[dict] = []

    async def _fake_update_strategy_status(db, strategy_id: str, status: str, **kwargs):
        status_updates.append({"strategy_id": strategy_id, "status": status, "kwargs": dict(kwargs)})
        return {"strategy_id": strategy_id, "status": status}

    async def _unexpected_vector_profile(db, strategy: dict):
        raise AssertionError("stress reject should not build vector profile")

    monkeypatch.setattr(lifecycle_module, "_update_strategy_status", _fake_update_strategy_status)
    monkeypatch.setattr(lifecycle_module, "build_strategy_vector_profile", _unexpected_vector_profile)

    result = asyncio.run(
        coordinator.execute(
            db,
            _make_request(lane="formal_incubation", passed=True),
        )
    )

    assert result.final_status == "rejected"
    assert [step.step for step in result.steps] == ["stress_test_gate"]
    assert result.action_audit["submission_action_completed"] is False
    assert result.action_audit["stress_gate_reason"] == "stress_test_rejected"
    assert result.stress_test_summary["overall_verdict"] == "reject"
    assert result.stress_test_summary["evidence_mode"] == "historical_backtest"
    assert submitter.gateway.ensure_calls == []
    assert submitter.gateway.pipeline_calls == []
    assert status_updates == []
    persisted_result = dict(db.updated_task_runs[-1]["result"] or {})
    assert persisted_result["final_status"] == "rejected"
    assert persisted_result["stress_test_summary"]["overall_verdict"] == "reject"


def test_lifecycle_coordinator_formal_incubation_proxy_stress_review_blocks_side_effects(monkeypatch):
    db = _FakeDb()
    submitter = _FakeSubmitterWithoutBacktest()
    coordinator = lifecycle_module.StrategyLifecycleCoordinator(submitter)

    async def _fake_update_strategy_status(db, strategy_id: str, status: str, **kwargs):
        return {"strategy_id": strategy_id, "status": status}

    async def _unexpected_vector_profile(db, strategy: dict):
        raise AssertionError("proxy stress review should not build vector profile")

    monkeypatch.setattr(lifecycle_module, "_update_strategy_status", _fake_update_strategy_status)
    monkeypatch.setattr(lifecycle_module, "build_strategy_vector_profile", _unexpected_vector_profile)

    result = asyncio.run(
        coordinator.execute(
            db,
            _make_request(lane="formal_incubation", passed=True),
        )
    )

    assert result.final_status == "submitted"
    assert [step.step for step in result.steps] == ["stress_test_gate"]
    assert result.steps[0].status == "blocked"
    assert result.action_audit["submission_action_completed"] is False
    assert result.action_audit["stress_gate_reason"] == "stress_test_review_required"
    assert result.stress_test_summary["overall_verdict"] == "review"
    assert result.stress_test_summary["evidence_mode"] == "backtest_metrics_proxy"
    assert result.stress_test_summary["diagnostic_only"] is True
    assert submitter.gateway.ensure_calls == []
    assert submitter.gateway.pipeline_calls == []


def test_lifecycle_coordinator_observe_lane_skips_formal_pipeline(monkeypatch):
    db = _FakeDb()
    submitter = _FakeSubmitter()
    coordinator = lifecycle_module.StrategyLifecycleCoordinator(submitter)

    async def _fake_update_strategy_status(db, strategy_id: str, status: str, **kwargs):
        return {"strategy_id": strategy_id, "status": status}

    async def _unexpected_vector_profile(db, strategy: dict):
        raise AssertionError("observe_incubation should not build vector profile")

    monkeypatch.setattr(lifecycle_module, "_update_strategy_status", _fake_update_strategy_status)
    monkeypatch.setattr(lifecycle_module, "build_strategy_vector_profile", _unexpected_vector_profile)

    result = asyncio.run(coordinator.execute(db, _make_request(lane="observe_incubation", passed=True)))

    assert result.final_status == "submitted"
    assert [step.step for step in result.steps] == ["status_transition", "enqueue_paper_observation"]
    assert result.paper_action["paper_account_id"] == "paper-observe-1"
    assert submitter.gateway.pipeline_calls == []
    assert submitter.paper_calls[0]["strategy"]["_closure_trace"]["submission_lane"] == "observe_incubation"


def test_lifecycle_coordinator_failed_gate_rejects_without_downstream_side_effects(monkeypatch):
    db = _FakeDb()
    submitter = _FakeSubmitter()
    coordinator = lifecycle_module.StrategyLifecycleCoordinator(submitter)
    status_updates: list[dict] = []

    async def _fake_update_strategy_status(db, strategy_id: str, status: str, **kwargs):
        status_updates.append({"strategy_id": strategy_id, "status": status})
        return {"strategy_id": strategy_id, "status": status}

    async def _unexpected_vector_profile(db, strategy: dict):
        raise AssertionError("failed gate should not build vector profile")

    monkeypatch.setattr(lifecycle_module, "_update_strategy_status", _fake_update_strategy_status)
    monkeypatch.setattr(lifecycle_module, "build_strategy_vector_profile", _unexpected_vector_profile)

    result = asyncio.run(
        coordinator.execute(
            db,
            _make_request(lane="formal_incubation", passed=False, final_status="rejected"),
        )
    )

    assert result.final_status == "rejected"
    assert [step.step for step in result.steps] == ["status_transition"]
    assert status_updates == [{"strategy_id": "strategy-1", "status": "rejected"}]
    assert submitter.gateway.ensure_calls == []
    assert submitter.paper_calls == []
    assert submitter.live_calls == []
