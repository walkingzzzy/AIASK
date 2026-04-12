"""P4 验收测试 – application services (ReadinessService / TaskOrchestrator / CandidatePipeline)。

验收标准：
- ReadinessService.evaluate() 能正确计算 can_proceed / readiness_score / warnings / blockers。
- ReadinessService 对 snapshot_degraded / factor_stale / completion_ratio 做出正确响应。
- TaskOrchestrator.classify_tasks() 正确分类任务来源。
- CandidatePipeline._build_report() 计算正确的 pipeline report。
"""

from __future__ import annotations

import pytest

from strategy_factory.application.services.readiness_service import (
    READINESS_AUTHORITY_CONTRACT_VERSION,
    READINESS_CONTRACT_VERSION,
    ReadinessService,
)
from strategy_factory.application.services.task_orchestrator import TaskOrchestrator
from strategy_factory.application.services.candidate_pipeline import CandidatePipeline
from strategy_factory.domain.candidates import CandidatePipelineReport
from strategy_factory.domain.research_tasks import ResearchTaskSpec


# ---------------------------------------------------------------------------
# ReadinessService
# ---------------------------------------------------------------------------

class TestReadinessService:
    def _svc(self) -> ReadinessService:
        return ReadinessService()

    def _good_snapshot(self) -> dict:
        return {
            "degraded": False,
            "completeness": {"completion_ratio": 1.0},
            "sources": {
                "event_driven": {"status": "success"}
            },
            "event_driven": {"tasks_ready_count": 3},
        }

    def _good_factor(self) -> dict:
        return {
            "degraded": False,
            "summary": {
                "stale": False,
                "degraded": False,
                "factor_source_mode": "governed_candidate_pool",
                "active_candidate_count": 2,
                "governed_source_candidate_count": 2,
                "governed_freshness_days": 0,
                "family_preference_order": ["momentum", "ma_cross"],
                "family_preference_source_mode": "stock_family_allocation",
                "stock_family_allocation_count": 24,
                "stock_family_allocation_source_mode": "stock_universe_projection",
                "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                "governed_candidate_pool_provisional_pending_count": 0,
                "governed_candidate_pool_strict_shortfall_count": 1,
                "active_family_names": ["momentum"],
                "active_regime_names": ["bull"],
            },
            "freshness_repair": {},
        }

    def test_all_good_can_proceed(self):
        svc = self._svc()
        result = svc.evaluate(self._good_snapshot(), self._good_factor())
        assert result["can_proceed"] is True
        assert result["readiness_score"] == pytest.approx(1.0)
        assert result["warnings"] == []
        assert result["blockers"] == []
        assert result["readiness_contract_version"] == READINESS_CONTRACT_VERSION
        assert result["authority_contract_version"] == READINESS_AUTHORITY_CONTRACT_VERSION
        assert result["decision"] == "proceed"
        assert result["blocked"] is False
        assert result["hard_gate"] == result["hard_block_enabled"]
        assert result["blocking_stage"] is None
        assert result["blocking_reason_codes"] == []
        assert result["critical_blocking_reason_codes"] == []
        assert result["skip_reason"] is None
        assert result["family_preference_order"] == ["momentum", "ma_cross"]
        assert result["family_preference_source_mode"] == "stock_family_allocation"
        assert result["stock_family_allocation_count"] == 24
        assert result["stock_family_allocation_source_mode"] == "stock_universe_projection"
        assert result["governed_candidate_pool_provisional_spillover_policy_status"] == "spillover_applied"
        assert result["governed_candidate_pool_strict_shortfall_count"] == 1

    def test_snapshot_degraded_adds_warning(self):
        svc = self._svc()
        snap = self._good_snapshot()
        snap["degraded"] = True
        result = svc.evaluate(snap, self._good_factor())
        assert "snapshot_degraded" in result["warnings"]
        assert result["readiness_score"] < 1.0

    def test_low_completion_ratio_adds_blocker(self):
        svc = self._svc()
        snap = self._good_snapshot()
        snap["completeness"]["completion_ratio"] = 0.5
        result = svc.evaluate(snap, self._good_factor())
        assert "snapshot_completion_too_low" in result["blockers"]

    def test_factor_stale_without_governed_pool_adds_blocker(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"]["stale"] = True
        factor["summary"]["active_candidate_count"] = 0
        factor["summary"]["factor_source_mode"] = "live"
        result = svc.evaluate(self._good_snapshot(), factor)
        assert "factor_research_stale" in result["blockers"]

    def test_factor_stale_with_governed_pool_adds_warning_only(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"]["stale"] = True
        factor["summary"]["factor_source_mode"] = "governed_candidate_pool"
        factor["summary"]["active_candidate_count"] = 5
        result = svc.evaluate(self._good_snapshot(), factor)
        assert "factor_research_stale" not in result["blockers"]
        assert "factor_research_history_stale_governed_pool_active" in result["warnings"]

    def test_event_partial_adds_warning(self):
        svc = self._svc()
        snap = self._good_snapshot()
        snap["sources"]["event_driven"]["status"] = "partial"
        result = svc.evaluate(snap, self._good_factor())
        assert "event_driven_partial" in result["warnings"]

    def test_returns_required_keys(self):
        svc = self._svc()
        result = svc.evaluate(self._good_snapshot(), self._good_factor())
        for key in [
            "can_proceed", "readiness_score", "warnings", "blockers",
            "runtime_enabled", "hard_block_enabled", "min_score",
            "snapshot_completion_ratio", "event_status",
        ]:
            assert key in result, f"Missing key: {key}"

    def test_none_factor_research(self):
        svc = self._svc()
        result = svc.evaluate(self._good_snapshot(), None)
        assert "can_proceed" in result

    def test_score_clamped_to_zero(self):
        svc = self._svc()
        snap = {
            "degraded": True,
            "completeness": {"completion_ratio": 0.0},
            "sources": {"event_driven": {"status": "failed"}},
            "event_driven": {"tasks_ready_count": 0},
        }
        factor = {
            "summary": {"stale": True, "degraded": True, "active_candidate_count": 0},
            "freshness_repair": {"refresh_attempted": True, "refresh_status": "timeout"},
        }
        result = svc.evaluate(snap, factor)
        assert result["readiness_score"] >= 0.0

    def test_scheduler_success_without_governed_pool_becomes_critical_blocker(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"]["factor_source_mode"] = "governed_pool_missing_after_scheduler_success"
        factor["summary"]["active_candidate_count"] = 0
        factor["summary"]["governed_source_candidate_count"] = 0
        factor["summary"]["scheduler_recent_success"] = True
        factor["summary"]["scheduler_llm_validation_status"] = "success"

        result = svc.evaluate(self._good_snapshot(), factor)

        assert result["can_proceed"] is False
        assert "governed_candidate_pool_missing_after_scheduler_success" in result["blockers"]
        assert "governed_candidate_pool_required" in result["critical_blockers"]
        assert result["critical_blocker_count"] == 2
        assert result["decision"] == "blocked"
        assert result["blocked"] is True
        assert result["blocking_stage"] == "readiness"
        assert result["skip_reason"] == "readiness_blocked"
        assert "governed_candidate_pool_required" in result["blocking_reason_codes"]
        assert "governed_candidate_pool_missing_after_scheduler_success" in result[
            "critical_blocking_reason_codes"
        ]

    def test_governed_pool_refreshing_sets_runtime_state(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"]["factor_source_mode"] = "seed_fallback"
        factor["summary"]["active_candidate_count"] = 0
        factor["summary"]["governed_source_candidate_count"] = 0
        factor["summary"]["scheduler_last_run"] = "2026-04-05T09:00:00+08:00"
        factor["freshness_repair"] = {
            "auto_refresh_enabled": True,
            "refresh_attempted": False,
        }

        result = svc.evaluate(self._good_snapshot(), factor)

        assert result["governed_candidate_pool_runtime_state"] == "refreshing_pool"
        assert result["can_proceed"] is False
        assert "governed_candidate_pool_required" in result["blockers"]
        assert "governed_candidate_pool_inactive" in result["warnings"]
        assert "governed_candidate_pool_refreshing" in result["warnings"]
        assert result["factor_refresh_recommended"] is True
        assert result["factor_refresh_recommendation_reason"] == "seed_fallback_without_governed_pool"

    def test_governed_pool_refresh_timeout_becomes_blocker(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"]["factor_source_mode"] = "seed_fallback"
        factor["summary"]["active_candidate_count"] = 0
        factor["summary"]["governed_source_candidate_count"] = 0
        factor["freshness_repair"] = {
            "auto_refresh_enabled": True,
            "refresh_attempted": True,
            "refresh_status": "timeout",
        }

        result = svc.evaluate(self._good_snapshot(), factor)

        assert result["governed_candidate_pool_runtime_state"] == "blocked_by_governed_pool"
        assert "governed_candidate_pool_required" in result["blockers"]
        assert "governed_candidate_pool_refresh_blocked" in result["warnings"]
        assert "governed_candidate_pool_unavailable_after_refresh" in result["blockers"]
        assert result["critical_blocker_count"] == 2

    def test_recoverable_governed_shortfall_does_not_hard_block(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"].update(
            {
                "factor_source_mode": "governed_pool_missing_after_scheduler_success",
                "active_candidate_count": 0,
                "governed_source_candidate_count": 3,
                "governed_candidate_pool_mode": "provisional_validated_watch",
                "governed_candidate_pool_provisional": True,
                "governed_candidate_pool_provisional_pending_count": 2,
                "governed_candidate_pool_strict_shortfall_count": 1,
                "active_family_names": [],
                "scheduler_recent_success": True,
                "scheduler_llm_validation_status": "success",
            }
        )

        result = svc.evaluate(self._good_snapshot(), factor)

        assert result["can_proceed"] is True
        assert result["governed_supply_recoverable"] is True
        assert "governed_candidate_pool_shortfall_recoverable" in result["warnings"]
        assert "governed_candidate_pool_required" not in result["blockers"]
        assert "governed_candidate_pool_missing_after_scheduler_success" not in result["blockers"]

    def test_provider_suppress_is_warning_only_when_governed_supply_viable(self):
        svc = self._svc()
        factor = self._good_factor()
        factor["summary"].update(
            {
                "suppressed_generator_modes": ["external_llm"],
                "feedback_generator_mode_control_mode_counts": {"suppress": 1, "normal": 1},
                "external_llm_provider_control_mode": "suppress",
                "external_llm_provider_control_reasons": ["provider_budget_guardrail"],
            }
        )

        result = svc.evaluate(self._good_snapshot(), factor)

        assert result["can_proceed"] is True
        assert result["external_llm_provider_suppress_active"] is True
        assert "external_llm_provider_suppressed" in result["warnings"]
        assert "external_llm_provider_suppressed" not in result["blockers"]


# ---------------------------------------------------------------------------
# TaskOrchestrator – classify_tasks
# ---------------------------------------------------------------------------

class TestTaskOrchestratorClassify:
    def test_classify_empty(self):
        specs, counts = TaskOrchestrator.classify_tasks([])
        assert specs == []
        assert counts == {}

    def test_classify_multiple_sources(self):
        tasks = [
            {"task_id": "t1", "task_key": "t1", "task_source": "event"},
            {"task_id": "t2", "task_key": "t2", "task_source": "event"},
            {"task_id": "t3", "task_key": "t3", "task_source": "snapshot"},
        ]
        specs, counts = TaskOrchestrator.classify_tasks(tasks)
        assert len(specs) == 3
        assert all(isinstance(s, ResearchTaskSpec) for s in specs)
        assert counts["event"] == 2
        assert counts["snapshot"] == 1

    def test_classify_unknown_source(self):
        tasks = [{"task_id": "t", "task_key": "t", "task_source": ""}]
        specs, counts = TaskOrchestrator.classify_tasks(tasks)
        assert counts.get("unknown") == 1

    def test_classify_preserves_fields(self):
        tasks = [
            {
                "task_id": "tid",
                "task_key": "tkey",
                "task_source": "event",
                "opportunity_type": "breakout",
                "candidate_family": "momentum",
                "generation_limit": 5,
            }
        ]
        specs, _ = TaskOrchestrator.classify_tasks(tasks)
        spec = specs[0]
        assert spec.opportunity_type == "breakout"
        assert spec.candidate_family == "momentum"
        assert spec.generation_limit == 5


# ---------------------------------------------------------------------------
# CandidatePipeline – _build_report
# ---------------------------------------------------------------------------

class TestCandidatePipelineBuildReport:
    def test_empty_run(self):
        report = CandidatePipeline._build_report(
            candidates=[],
            passed=[],
            unique=[],
            submit_result={},
            quality_gate_report={},
            backtest_report={},
        )
        assert isinstance(report, CandidatePipelineReport)
        assert report.total_spawned == 0
        assert report.submitted == 0

    def test_counts_from_submit_result(self):
        report = CandidatePipeline._build_report(
            candidates=[{}, {}, {}],
            passed=[{}, {}],
            unique=[{}],
            submit_result={
                "submitted": 1,
                "passed_quality_gate": 1,
                "gate_3_passed": 1,
                "gate_3_failed": 0,
                "gate_3_provisional_passed": 0,
            },
            quality_gate_report={},
            backtest_report={
                "summary": {
                    "input_count": 3,
                    "passed_count": 2,
                    "failed_count": 1,
                }
            },
        )
        assert report.total_spawned == 3
        assert report.gate_2_passed == 2
        assert report.after_dedup == 1
        assert report.submitted == 1

    def test_to_dict_has_all_keys(self):
        report = CandidatePipeline._build_report([], [], [], {}, {}, {})
        d = report.to_dict()
        required = [
            "total_spawned", "gate_0_passed", "gate_1_passed",
            "gate_2_passed", "after_dedup", "submitted",
        ]
        for key in required:
            assert key in d, f"Missing: {key}"

    def test_failure_reason_counts_merged(self):
        submit_result = {
            "submitted": 2,
            "gate_3_failure_reason_topn": [
                {"reason": "low_sharpe", "count": 1}
            ],
        }
        backtest_report = {
            "summary": {
                "failed_reason_counts": {"low_momentum": 1}
            }
        }
        report = CandidatePipeline._build_report(
            candidates=[{}, {}, {}],
            passed=[{}],
            unique=[{}],
            submit_result=submit_result,
            quality_gate_report={},
            backtest_report=backtest_report,
        )
        assert "low_sharpe" in report.failure_reason_counts
        assert "low_momentum" in report.failure_reason_counts


# ---------------------------------------------------------------------------
# P5 domain run result view
# ---------------------------------------------------------------------------

class TestFactoryRunResultView:
    def test_from_dict_basic(self):
        from strategy_factory.domain.run_result import FactoryRunResultView, StageResultView
        from strategy_factory.application.run_models import FactoryRunStatus, StageStatus

        raw = {
            "run_id": "run_001",
            "trace_id": "trace_001",
            "status": "success",
            "started_at": "2026-01-01T10:00:00",
            "completed_at": "2026-01-01T10:05:00",
            "elapsed_seconds": 300.0,
            "stages": {
                "collect": {"status": "completed", "ok": True},
                "readiness": {"status": "partial", "ok": True, "degraded": True},
            },
            "summary": {"submitted": 3},
            "_run_audit": {"persistence_failure_count": 0, "hard_failure_count": 0},
        }
        view = FactoryRunResultView.from_dict(raw)
        assert view.status == FactoryRunStatus.SUCCESS
        assert view.succeeded is True
        assert view.partial is False
        assert len(view.stages) == 2
        assert view.stages["readiness"].status == StageStatus.PARTIAL

    def test_failed_stages(self):
        from strategy_factory.domain.run_result import FactoryRunResultView
        raw = {
            "run_id": "r",
            "trace_id": "t",
            "status": "partial",
            "stages": {
                "factor_research": {"status": "failed", "ok": False, "hard_failure": True},
                "collect": {"status": "completed", "ok": True},
            },
            "_run_audit": {},
        }
        view = FactoryRunResultView.from_dict(raw)
        assert "factor_research" in view.failed_stages()
        assert "collect" not in view.failed_stages()
