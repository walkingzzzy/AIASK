from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from strategy_factory.application.cycle_runner import FactoryCycleRunner, FactoryRunContext
from strategy_factory.application.research.runner import ResearchGenerationResult
from strategy_factory.application.run_models import StageStatus, build_stage_result
from strategy_factory.application.services.readiness_service import ReadinessService


def _healthy_snapshot() -> dict:
    return {
        "date": "2026-05-06",
        "fear_greed_index": 50,
        "fg_level": "neutral",
        "sources": {"event_driven": {"status": "success"}},
        "event_driven": {"tasks_ready_count": 1},
        "completeness": {"completion_ratio": 1.0},
    }


def _governed_factor_summary(**overrides) -> dict:
    summary = {
        "factor_source_mode": "governed_candidate_pool",
        "active_candidate_count": 6,
        "governed_source_candidate_count": 80,
        "governed_candidate_pool_mode": "strict_governed",
        "active_family_names": ["momentum"],
        "active_regime_names": ["neutral"],
        "governed_blocked_candidate_count": 38,
        "governed_blocked_ratio": 0.475,
        "governed_pending_candidate_count": 4,
        "governed_pending_ratio": 0.05,
        "budget_feedback_strategy_count": 10,
        "budget_feedback_zero_signal_ratio": 0.5,
        "budget_feedback_forward_window_coverage_ratio": 0.2,
        "budget_feedback_promotion_ready_ratio": 0.0,
        "budget_feedback_promotion_review_coverage_ratio": 0.0,
        "budget_feedback_evidence_debt_ratio": 0.9,
        "governed_freshness_days": 12,
        "scheduler_recent_success": True,
    }
    summary.update(overrides)
    return summary


def test_readiness_warnings_only_allows_generation_but_blocks_production():
    result = ReadinessService().evaluate(
        _healthy_snapshot(),
        {"summary": _governed_factor_summary()},
    )

    assert result["readiness_score"] < result["min_score"]
    assert result["blockers"] == []
    assert result["critical_blockers"] == []
    assert result["can_proceed"] is False
    assert result["generation_can_proceed"] is True
    assert result["generation_blockers"] == []
    assert result["production_can_proceed"] is False
    assert "governed_candidate_pool_blocked_candidates" in result["production_blockers"]
    assert result["readiness_mode"] == "generation_allowed_production_blocked"


def test_readiness_critical_blocker_blocks_generation():
    result = ReadinessService().evaluate(
        _healthy_snapshot(),
        {"summary": {"factor_source_mode": "seed_fallback"}},
    )

    assert result["can_proceed"] is False
    assert result["generation_can_proceed"] is False
    assert "governed_candidate_pool_required" in result["generation_blockers"]
    assert result["production_can_proceed"] is False
    assert result["readiness_mode"] == "generation_blocked"


def test_readiness_clean_state_allows_generation_and_production():
    result = ReadinessService().evaluate(
        _healthy_snapshot(),
        {"summary": _governed_factor_summary(governed_blocked_ratio=0.0, budget_feedback_zero_signal_ratio=0.0, budget_feedback_forward_window_coverage_ratio=1.0, budget_feedback_promotion_ready_ratio=1.0, budget_feedback_promotion_review_coverage_ratio=1.0, budget_feedback_evidence_debt_ratio=0.0, governed_freshness_days=0)},
    )

    assert result["readiness_score"] >= result["min_score"]
    assert result["can_proceed"] is True
    assert result["generation_can_proceed"] is True
    assert result["production_can_proceed"] is True
    assert result["readiness_mode"] == "production_allowed"


def test_readiness_uses_active_blocked_ratio_after_quarantine_accounting():
    result = ReadinessService().evaluate(
        _healthy_snapshot(),
        {
            "summary": _governed_factor_summary(
                governed_source_candidate_count=80,
                governed_blocked_candidate_count=38,
                governed_quarantined_candidate_count=38,
                governed_active_blocked_candidate_count=0,
                governed_governance_denominator=42,
                governed_blocked_ratio=0.0,
                budget_feedback_zero_signal_ratio=0.0,
                budget_feedback_forward_window_coverage_ratio=1.0,
                budget_feedback_promotion_ready_ratio=1.0,
                budget_feedback_promotion_review_coverage_ratio=1.0,
                budget_feedback_evidence_debt_ratio=0.0,
                governed_freshness_days=0,
            )
        },
    )

    assert "governed_candidate_pool_blocked_ratio_elevated" not in result["warnings"]
    assert result["governed_blocked_candidate_count"] == 38
    assert result["governed_blocked_ratio"] == 0.0
    assert result["production_can_proceed"] is True


def test_readiness_reports_pending_evidence_refresh_without_mature_feedback_debt():
    result = ReadinessService().evaluate(
        _healthy_snapshot(),
        {
            "summary": _governed_factor_summary(
                governed_blocked_ratio=0.0,
                budget_feedback_source_strategy_count=2,
                budget_feedback_strategy_count=0,
                budget_feedback_pending_evidence_refresh_count=2,
                budget_feedback_pending_evidence_refresh_reason_counts={
                    "submitted_runtime_evidence_pending": 2
                },
                budget_feedback_zero_signal_ratio=0.0,
                budget_feedback_forward_window_coverage_ratio=1.0,
                budget_feedback_promotion_ready_ratio=1.0,
                budget_feedback_promotion_review_coverage_ratio=1.0,
                budget_feedback_evidence_debt_ratio=0.0,
                governed_freshness_days=0,
            )
        },
    )

    assert result["budget_feedback_strategy_count"] == 0
    assert result["budget_feedback_source_strategy_count"] == 2
    assert result["budget_feedback_pending_evidence_refresh_count"] == 2
    assert result["budget_feedback_pending_evidence_refresh_reason_counts"] == {
        "submitted_runtime_evidence_pending": 2
    }
    assert not [warning for warning in result["warnings"] if warning.startswith("incubating_")]
    assert result["production_can_proceed"] is True


class _FakeCollector:
    async def collect(self, db):
        return _healthy_snapshot()


class _FakeEliminator:
    async def check(self, db, fg_level):
        return []


class _FakePipelineRun:
    def __init__(self, read_only: bool):
        self.passed = [{"name": "candidate-1"}]
        self.unique = [{"name": "candidate-1"}]
        self.quality_gate_report = {
            "gate_0": {"passed_count": 1, "failed_count": 0},
            "gate_1": {"passed_count": 1, "failed_count": 0},
            "gate_2": {"passed_count": 1, "failed_count": 0},
        }
        self.backtest_report = {"summary": {"input_count": 1, "passed_count": 1, "failed_count": 0}}
        self.submit_result = {"submitted": 0, "read_only": read_only, "diagnostic_only": read_only}
        self.governance_plane = {"available": True}

    def deduplicator_report(self):
        return {"summary": {"available": True}}


class _FakeCandidatePipeline:
    calls: list[dict] = []

    def __init__(self, factory_pkg, scheduler):
        self.factory_pkg = factory_pkg
        self.scheduler = scheduler

    async def run(self, candidates, snapshot, db, *, read_only=False):
        self.calls.append({"candidates": list(candidates), "read_only": read_only})
        return _FakePipelineRun(read_only)


class _FakeResearchRunner:
    def __init__(self, scheduler, factory_pkg):
        pass

    async def build_factor_research_artifact(self, factor_gateway, db, snapshot):
        return {"summary": _governed_factor_summary()}

    def build_research_plane(self, **kwargs):
        candidates = list(kwargs.get("candidates") or [])
        return {
            "available": True,
            "contract_version": "test",
            "research_artifact": {"contract_version": "test"},
            "task_artifact": {"contract_version": "test"},
            "candidate_artifact": {"contract_version": "test", "candidate_count": len(candidates)},
            "evidence_artifact": {"contract_version": "test"},
        }

    async def run_generation(self, db, snapshot):
        candidate = {"name": "candidate-1", "strategy_type": "momentum", "params": {"lookback": 20}}
        return ResearchGenerationResult(
            local_candidates=[candidate],
            generated_candidates=[candidate],
            local_spawn_report={"summary": {"candidate_count": 1, "strategy_type_coverage_count": 1}},
            autonomy_stage={"generated_count": 0},
        )


class _FakeScheduler:
    def __init__(self):
        self.audit_results: list[dict] = []

    def _now(self):
        return datetime(2026, 5, 6, tzinfo=timezone.utc)

    async def _run_startup_warmup(self):
        return {"status": "skipped", "ok": True}

    def _get_factor_research_gateway(self):
        return SimpleNamespace()

    def _compact_factor_research_snapshot(self, factor_research):
        return {"summary": dict((factor_research or {}).get("summary") or {})}

    def _with_stage_meta(self, stage_name, trace_id, payload, *, status, ok=None, hard_failure=False, degraded=None, skip_reason=None):
        return build_stage_result(stage_name, trace_id, payload, status=status, ok=ok, hard_failure=hard_failure, degraded=degraded, skip_reason=skip_reason)

    def _aggregate_vector_submission_metrics(self, submit_result):
        return {}

    def _aggregate_backtest_audit_metrics(self, backtest_report):
        return {}

    def _aggregate_submission_audit_metrics(self, submit_result):
        return {}

    def _build_layered_run_summary(self, summary, submit_result):
        return {}

    def _apply_run_audit(self, results, persistence_failures=None):
        self.audit_results.append(dict(results))


def test_cycle_runner_continues_generation_read_only_when_only_production_blocked(monkeypatch):
    runner_module = __import__(
        "strategy_factory.application.cycle_runner",
        fromlist=["CandidatePipeline", "ResearchPlaneRunner"],
    )
    _FakeCandidatePipeline.calls = []
    monkeypatch.setattr(runner_module, "CandidatePipeline", _FakeCandidatePipeline)
    monkeypatch.setattr(runner_module, "ResearchPlaneRunner", _FakeResearchRunner)

    factory_pkg = SimpleNamespace(DataCollector=_FakeCollector, EliminationChecker=_FakeEliminator)
    context = FactoryRunContext(
        db=SimpleNamespace(),
        factory_pkg=factory_pkg,
        runtime_adapters=SimpleNamespace(),
        start=datetime(2026, 5, 6, tzinfo=timezone.utc),
        trace_id="trace-1",
        run_id="run-1",
    )

    outcome = asyncio.run(FactoryCycleRunner(_FakeScheduler(), context).run())

    assert outcome.result["status"] == "partial"
    assert "spawn" in outcome.result["stages"]
    assert "backtest" in outcome.result["stages"]
    assert _FakeCandidatePipeline.calls == [{"candidates": [{"name": "candidate-1", "strategy_type": "momentum", "params": {"lookback": 20}}], "read_only": True}]
    assert outcome.result["submit_result"]["read_only"] is True
    assert outcome.result["summary"]["factory_generation_can_proceed"] is True
    assert outcome.result["summary"]["factory_production_can_proceed"] is False
    assert outcome.result["summary"]["submission_mode"] == "read_only_due_to_readiness"


def test_cycle_runner_still_skips_when_generation_blocked(monkeypatch):
    class GenerationBlockedResearchRunner(_FakeResearchRunner):
        async def build_factor_research_artifact(self, factor_gateway, db, snapshot):
            return {"summary": {"factor_source_mode": "seed_fallback"}}

    runner_module = __import__(
        "strategy_factory.application.cycle_runner",
        fromlist=["CandidatePipeline", "ResearchPlaneRunner"],
    )
    _FakeCandidatePipeline.calls = []
    monkeypatch.setattr(runner_module, "CandidatePipeline", _FakeCandidatePipeline)
    monkeypatch.setattr(runner_module, "ResearchPlaneRunner", GenerationBlockedResearchRunner)

    factory_pkg = SimpleNamespace(DataCollector=_FakeCollector, EliminationChecker=_FakeEliminator)
    context = FactoryRunContext(
        db=SimpleNamespace(),
        factory_pkg=factory_pkg,
        runtime_adapters=SimpleNamespace(),
        start=datetime(2026, 5, 6, tzinfo=timezone.utc),
        trace_id="trace-2",
        run_id="run-2",
    )

    outcome = asyncio.run(FactoryCycleRunner(_FakeScheduler(), context).run())

    assert outcome.result["status"] == "skipped"
    assert "spawn" not in outcome.result["stages"]
    assert _FakeCandidatePipeline.calls == []
    assert outcome.result["summary"]["factory_generation_can_proceed"] is False
    assert outcome.result["summary"]["submission_mode"] == "skipped_due_to_generation_readiness"
