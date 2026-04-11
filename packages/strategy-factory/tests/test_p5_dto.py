"""P5 验收测试 – 稳定 DTO 层。

验收标准：
- StageResultDTO / FactoryRunSummaryDTO / FactoryRunDetailDTO / FactoryStatusDTO 可从 dict 构造。
- to_dict() 输出包含所有必要字段。
- 状态枚举归一化正确（别名 'success' → 'success' / 'partial' 等）。
- normalize_run_result_to_detail / normalize_run_result_to_summary 工具函数可用。
"""

from __future__ import annotations

import pytest

from strategy_factory.api.dto import (
    FactoryRunDetailDTO,
    FactoryRunSummaryDTO,
    FactoryStatusDTO,
    StageResultDTO,
    normalize_run_result_to_detail,
    normalize_run_result_to_summary,
)
from strategy_factory.application.research_plane_contract import (
    CANDIDATE_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_PLANE_CONTRACT_VERSION,
    TASK_ARTIFACT_CONTRACT_VERSION,
)
from strategy_factory.application.governance_plane_contract import (
    DEDUP_ARTIFACT_CONTRACT_VERSION,
    GATE_ARTIFACT_CONTRACT_VERSION,
    GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    GOVERNANCE_PLANE_CONTRACT_VERSION,
    SUBMISSION_ARTIFACT_CONTRACT_VERSION,
)
from strategy_factory.application.run_models import build_stage_result


# ---------------------------------------------------------------------------
# StageResultDTO
# ---------------------------------------------------------------------------

class TestStageResultDTO:
    def test_from_dict_completed(self):
        dto = StageResultDTO.from_dict("collect", {
            "status": "completed",
            "ok": True,
            "hard_failure": False,
            "degraded": False,
            "warning_count": 0,
            "blocker_count": 0,
            "persistence_failure_count": 0,
        })
        assert dto.stage == "collect"
        assert dto.status == "completed"
        assert dto.ok is True
        assert dto.hard_failure is False

    def test_from_dict_partial(self):
        dto = StageResultDTO.from_dict("readiness", {"status": "partial", "degraded": True})
        assert dto.status == "partial"
        assert dto.degraded is True

    def test_from_dict_with_skip_reason(self):
        dto = StageResultDTO.from_dict("readiness", {
            "status": "skipped",
            "ok": True,
            "skip_reason": "runtime_disabled",
        })
        assert dto.skip_reason == "runtime_disabled"

    def test_to_dict_has_required_keys(self):
        dto = StageResultDTO.from_dict("spawn", {"status": "completed", "ok": True})
        d = dto.to_dict()
        for key in ["stage", "status", "ok", "hard_failure", "degraded"]:
            assert key in d

    def test_skip_reason_omitted_when_none(self):
        dto = StageResultDTO.from_dict("spawn", {"status": "completed"})
        d = dto.to_dict()
        assert "skip_reason" not in d

    def test_status_alias_success_normalized(self):
        dto = StageResultDTO.from_dict("collect", {"status": "success"})
        assert dto.status == "completed"

    def test_status_alias_error_normalized(self):
        dto = StageResultDTO.from_dict("factor_research", {"status": "error"})
        assert dto.status == "failed"

    def test_build_stage_result_has_contract_version(self):
        payload = build_stage_result("collect", "trace_001", {"rows": 12}, status="completed")
        assert payload["stage_contract_version"] == 1


# ---------------------------------------------------------------------------
# FactoryRunSummaryDTO
# ---------------------------------------------------------------------------

_SAMPLE_RUN_RESULT = {
    "run_id": "run_001",
    "trace_id": "trace_001",
    "status": "success",
    "started_at": "2026-01-01T10:00:00+08:00",
    "completed_at": "2026-01-01T10:05:00+08:00",
    "elapsed_seconds": 300.0,
    "summary": {
        "trace_id": "trace_001",
        "candidates_spawned": 12,
        "submitted": 3,
        "eliminated": 1,
        "factory_readiness_score": 0.92,
        "factory_readiness_can_proceed": True,
        "stock_family_allocation_count": 128,
        "family_preference_order": ["momentum", "quality_factor"],
        "family_preference_source_mode": "stock_family_allocation",
        "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
        "governed_pending_candidate_count": 0,
        "external_llm_provider_health_status": "degraded",
        "external_llm_provider_control_mode": "suppress",
        "candidate_local_attempt_count": 6,
        "task_local_attempt_count": 4,
        "cohort_effective_trials": 9.5,
        "refresh_existing_count": 1,
        "spawn_revision_from_existing_count": 2,
        "unique_family_holding_universe_count": 5,
        "economic_semantics_missing_count": 2,
        "research_only_count": 1,
        "deferred_submission_count": 1,
        "validation_grade_distribution": {"D": 1, "C": 2},
        "raw_validation_grade_distribution": {"D": 2, "C": 1},
        "effective_validation_grade_distribution": {"C": 3},
        "raw_validation_total_score_mean": 46.5,
        "raw_validation_total_score_p50": 45.0,
        "raw_validation_total_score_p90": 54.0,
        "raw_validation_a_rate": 0.0,
        "raw_validation_b_rate": 0.0,
        "raw_validation_c_rate": 0.3333,
        "raw_validation_d_rate": 0.6667,
        "strict_incubation_ready_count": 2,
        "strict_incubation_ready_rate": 0.6667,
        "live_candidate_ready_count": 1,
        "live_candidate_ready_rate": 0.3333,
        "raw_b_or_above_count": 1,
        "raw_b_or_above_rate": 0.3333,
        "strict_ready_given_raw_b_count": 1,
        "strict_ready_given_raw_b_rate": 1.0,
        "live_ready_given_raw_b_count": 0,
        "live_ready_given_raw_b_rate": 0.0,
        "validation_family_quality_panel": [
            {
                "strategy_family": "momentum",
                "holding_period_bucket": "swing",
                "validation_focus": "target_only",
                "strategy_count": 3,
                "raw_validation_grade_distribution": {"D": 2, "C": 1},
                "effective_validation_grade_distribution": {"C": 3},
                "raw_validation_total_score_mean": 46.5,
                "family_raw_a_rate": 0.0,
                "family_raw_b_rate": 0.0,
                "family_mean_trade_density": 0.84,
                "family_mean_post_cost_sharpe": 1.12,
                "family_mean_dsr": 0.16,
                "family_mean_pbo": 0.42,
            }
        ],
        "research_summary": {"research_plane_contract_version": "strategy_factory.research_plane.v1"},
        "feedback_summary": {"family_count": 2, "feedback_available": True},
        "incubation_summary": {"gate_3_passed": 2},
        "live_ready_summary": {"live_ready_review_count": 1},
    },
    "_run_audit": {
        "hard_failure_count": 0,
        "degraded_stage_count": 0,
        "persistence_failure_count": 0,
    },
    "stages": {
        "collect": {"status": "completed", "ok": True},
        "readiness": {"status": "completed", "ok": True},
        "spawn": {"status": "completed", "ok": True},
        "submit": {"status": "completed", "ok": True},
    },
}


class TestFactoryRunSummaryDTO:
    def test_from_dict_basic(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.run_id == "run_001"
        assert dto.status == "success"
        assert dto.candidates_spawned == 12
        assert dto.submitted == 3
        assert dto.elapsed_seconds == pytest.approx(300.0)
        assert dto.stock_family_allocation_count == 128
        assert dto.family_preference_source_mode == "stock_family_allocation"
        assert dto.governed_candidate_pool_provisional_spillover_policy_status == "spillover_applied"
        assert dto.external_llm_provider_health_status == "degraded"
        assert dto.external_llm_provider_control_mode == "suppress"
        assert dto.candidate_local_attempt_count == 6
        assert dto.cohort_effective_trials == pytest.approx(9.5)

    def test_from_dict_partial(self):
        data = {**_SAMPLE_RUN_RESULT, "status": "partial"}
        data["_run_audit"] = {"degraded_stage_count": 1, "hard_failure_count": 0, "persistence_failure_count": 0}
        dto = FactoryRunSummaryDTO.from_dict(data)
        assert dto.status == "partial"
        assert dto.degraded_stage_count == 1

    def test_from_dict_skipped(self):
        data = {
            "run_id": "r", "trace_id": "t",
            "status": "skipped",
            "summary": {"skip_reason": "runtime_disabled"},
            "_run_audit": {},
        }
        dto = FactoryRunSummaryDTO.from_dict(data)
        assert dto.status == "skipped"
        assert dto.skip_reason == "runtime_disabled"

    def test_to_dict_has_required_keys(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        for key in ["run_id", "status", "elapsed_seconds", "submitted", "candidates_spawned"]:
            assert key in d

    def test_error_omitted_when_none(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        assert "error" not in d

    def test_error_included_when_present(self):
        data = {**_SAMPLE_RUN_RESULT, "status": "failed", "error": "something went wrong"}
        dto = FactoryRunSummaryDTO.from_dict(data)
        d = dto.to_dict()
        assert d["error"] == "something went wrong"

    def test_readiness_fields(self):
        dto = FactoryRunSummaryDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.readiness_score == pytest.approx(0.92)
        assert dto.readiness_can_proceed is True
        assert dto.family_preference_order == ["momentum", "quality_factor"]
        assert dto.governed_pending_candidate_count == 0
        assert dto.refresh_existing_count == 1
        assert dto.spawn_revision_from_existing_count == 2
        assert dto.unique_family_holding_universe_count == 5
        assert dto.economic_semantics_missing_count == 2
        assert dto.research_only_count == 1
        assert dto.deferred_submission_count == 1
        assert dto.validation_grade_distribution == {"D": 1, "C": 2}
        assert dto.raw_validation_grade_distribution == {"D": 2, "C": 1}
        assert dto.effective_validation_grade_distribution == {"C": 3}
        assert dto.raw_validation_total_score_mean == pytest.approx(46.5)
        assert dto.raw_validation_total_score_p50 == pytest.approx(45.0)
        assert dto.raw_validation_total_score_p90 == pytest.approx(54.0)
        assert dto.raw_validation_d_rate == pytest.approx(0.6667)
        assert dto.strict_incubation_ready_count == 2
        assert dto.live_candidate_ready_rate == pytest.approx(0.3333)
        assert dto.raw_b_or_above_count == 1
        assert dto.strict_ready_given_raw_b_rate == pytest.approx(1.0)
        assert dto.validation_family_quality_panel[0]["strategy_family"] == "momentum"
        assert dto.validation_family_quality_panel[0]["family_mean_dsr"] == pytest.approx(0.16)

    def test_from_dict_falls_back_to_submission_artifact_quality_panel(self):
        data = {
            **_SAMPLE_RUN_RESULT,
            "summary": {
                "trace_id": "trace_001",
                "candidates_spawned": 4,
                "submitted": 2,
                "eliminated": 0,
            },
            "stages": {
                **_SAMPLE_RUN_RESULT["stages"],
                "submit": {
                    "status": "completed",
                    "ok": True,
                    "strategies": [
                        {
                            "strategy_id": "sid_fallback_1",
                            "candidate_family": "momentum",
                            "holding_period_bucket": "medium",
                            "submission_lane": "deferred_submission",
                            "quality_summary": {
                                "validation_grade": "C",
                                "raw_validation_grade": "B",
                                "effective_validation_grade": "C",
                                "raw_validation_total_score": 56.0,
                                "candidate_family": "momentum",
                                "holding_period_bucket": "medium",
                            },
                        }
                    ],
                },
            },
        }

        dto = FactoryRunSummaryDTO.from_dict(data)

        assert dto.raw_validation_grade_distribution == {"B": 1}
        assert dto.raw_validation_b_rate == pytest.approx(1.0)
        assert dto.validation_family_quality_panel[0]["strategy_family"] == "momentum"


# ---------------------------------------------------------------------------
# FactoryRunDetailDTO
# ---------------------------------------------------------------------------

class TestFactoryRunDetailDTO:
    def test_from_dict_stages(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.summary.run_id == "run_001"
        stage_names = [s.stage for s in dto.stages]
        assert "collect" in stage_names
        assert "readiness" in stage_names

    def test_get_stage(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        stage = dto.get_stage("collect")
        assert stage is not None
        assert stage.stage == "collect"

    def test_get_stage_missing(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.get_stage("nonexistent") is None

    def test_failed_stages_empty_when_all_pass(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        assert dto.failed_stages() == []

    def test_failed_stages_detected(self):
        data = dict(_SAMPLE_RUN_RESULT)
        data["stages"] = {
            "factor_research": {"status": "failed", "ok": False},
            "collect": {"status": "completed", "ok": True},
        }
        dto = FactoryRunDetailDTO.from_dict(data)
        assert "factor_research" in dto.failed_stages()

    def test_to_dict_includes_stages(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        assert "stages" in d
        assert isinstance(d["stages"], dict)

    def test_to_dict_includes_layered_summaries(self):
        dto = FactoryRunDetailDTO.from_dict(_SAMPLE_RUN_RESULT)
        d = dto.to_dict()
        assert d["research_summary"]["research_plane_contract_version"] == "strategy_factory.research_plane.v1"
        assert d["feedback_summary"]["family_count"] == 2
        assert d["incubation_summary"]["gate_3_passed"] == 2
        assert d["live_ready_summary"]["live_ready_review_count"] == 1

    def test_from_dict_ignores_fallback_stage_metadata_entries(self):
        data = {
            **_SAMPLE_RUN_RESULT,
            "stages": {
                **_SAMPLE_RUN_RESULT["stages"],
                "truncated": True,
                "field_name": "stages",
                "stage_count": 4,
                "stage_names": ["collect", "readiness", "spawn", "submit"],
            },
        }

        dto = FactoryRunDetailDTO.from_dict(data)

        assert {stage.stage for stage in dto.stages} == {"collect", "readiness", "spawn", "submit"}

    def test_from_dict_reconstructs_research_plane_from_stage_artifacts(self):
        data = {
            **_SAMPLE_RUN_RESULT,
            "research_plane": {},
            "factor_research": {
                "summary": {
                    "factor_source_mode": "governed_candidate_pool",
                    "family_preference_order": ["momentum", "quality_factor"],
                    "family_preference_source_mode": "stock_family_allocation",
                    "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                    "governed_candidate_pool_strict_shortfall_count": 2,
                    "stock_family_allocation_count": 48,
                    "stock_family_allocation_source_mode": "stock_universe_projection",
                },
            },
            "stages": {
                "factor_research": {
                    "status": "completed",
                    "ok": True,
                    "research_artifact": {
                        "contract_version": RESEARCH_ARTIFACT_CONTRACT_VERSION,
                        "available": True,
                        "active_factor_count": 2,
                    },
                },
                "autonomy": {
                    "status": "completed",
                    "ok": True,
                    "task_artifact": {
                        "contract_version": TASK_ARTIFACT_CONTRACT_VERSION,
                        "available": True,
                        "planned_task_count": 3,
                    },
                    "candidate_artifact": {
                        "contract_version": CANDIDATE_ARTIFACT_CONTRACT_VERSION,
                        "available": True,
                        "candidate_count": 4,
                    },
                    "evidence_artifact": {
                        "contract_version": RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
                        "available": True,
                        "experiment_count": 2,
                    },
                },
            },
        }

        dto = FactoryRunDetailDTO.from_dict(data)
        d = dto.to_dict()

        assert d["research_plane"]["contract_version"] == RESEARCH_PLANE_CONTRACT_VERSION
        assert d["research_artifact"]["contract_version"] == RESEARCH_ARTIFACT_CONTRACT_VERSION
        assert d["research_artifact"]["family_preference_order"] == ["momentum", "quality_factor"]
        assert d["research_artifact"]["family_preference_source_mode"] == "stock_family_allocation"
        assert d["task_artifact"]["planned_task_count"] == 3
        assert d["candidate_artifact"]["candidate_count"] == 4
        assert d["evidence_artifact"]["experiment_count"] == 2

    def test_from_dict_reconstructs_governance_plane_from_stage_artifacts(self):
        data = {
            **_SAMPLE_RUN_RESULT,
            "governance_plane": {},
            "quality_gate": {
                "gate_0": {"passed_count": 5, "failed_count": 1},
                "pre_gate": {"passed_count": 4, "failed_count": 1},
                "gate_1": {"passed_count": 3, "failed_count": 1},
                "gate_2": {"input_count": 3, "passed_count": 2, "failed_count": 1},
                "gate_3": {
                    "input_count": 2,
                    "passed_count": 1,
                    "failed_count": 1,
                    "failure_reason_topn": [{"reason_code": "attempt_adjusted_penalty", "count": 1}],
                },
            },
            "stages": {
                "backtest": {
                    "status": "completed",
                    "ok": True,
                    "summary": {
                        "input_count": 3,
                        "passed_count": 2,
                        "failed_count": 1,
                        "failed_reason_counts": {"capacity_guard": 1},
                    },
                },
                "deduplicate": {
                    "status": "completed",
                    "ok": True,
                    "summary": {
                        "input_count": 2,
                        "kept_count": 1,
                        "dropped_count": 1,
                        "refreshed_existing_count": 1,
                    },
                    "kept": [
                        {
                            "strategy_type": "momentum",
                            "target_symbols": ["600519"],
                            "dedup_result": {
                                "duplicate": False,
                                "refresh_existing": True,
                                "refresh_mode": "refresh_metrics_only",
                            },
                        }
                    ],
                },
                "submit": {
                    "status": "completed",
                    "ok": True,
                    "submitted": 1,
                    "gate_3_passed": 1,
                    "gate_3_failed": 0,
                    "strategies": [
                        {
                            "strategy_id": "sid_governance_1",
                            "name": "治理候选",
                            "status": "submitted",
                            "submission_lane": "paper",
                            "submission_action_type": "create",
                            "primary_validation_layer": "target",
                            "refresh_mode": "refresh_metrics_only",
                            "task_signature": "event_driven|evt_1|ai||event_target_only|600519",
                            "validation_profile": {
                                "profile": "event_trade_validation",
                                "validation_focus": "event_target_only",
                                "primary_validation_layer": "target",
                            },
                            "constraint_check": {
                                "constraint_violation": "strict_intersection_trimmed",
                                "intersection_ratio": 0.5,
                            },
                            "committee_review": {
                                "decision": "revise",
                                "final_score": 0.6842,
                                "execution_score": 0.48,
                                "capacity_score": 0.55,
                                "task_alignment_score": 0.44,
                                "accept_blockers": [
                                    "execution_floor_failed",
                                    "task_alignment_floor_failed",
                                ],
                            },
                            "event_window_config": {"lookback_days": 3, "forward_days": 5},
                            "position_assumption": "single_name_full_notional",
                            "attempt_adjustment": {"attempt_count": 4, "selection_ratio": 0.25, "penalty": 0.03},
                            "vector_profile_id": "vp_1",
                            "multiple_testing_registry": {"available": True},
                            "multiple_testing_registry_record_id": "mt_1",
                            "candidate_lineage_contract": {"lineage_id": "lineage_1"},
                            "cost_assumptions": {"commission_bps": 8},
                            "explicit_cost_breakdown": {"commission_cost": 120.0},
                            "implicit_cost_breakdown": {"slippage_cost": 36.0},
                            "execution_reality": {"tradability_filter": True},
                        }
                    ],
                },
            },
        }

        dto = FactoryRunDetailDTO.from_dict(data)
        d = dto.to_dict()

        assert d["governance_plane"]["contract_version"] == GOVERNANCE_PLANE_CONTRACT_VERSION
        assert d["gate_artifact"]["contract_version"] == GATE_ARTIFACT_CONTRACT_VERSION
        assert d["dedup_artifact"]["contract_version"] == DEDUP_ARTIFACT_CONTRACT_VERSION
        assert d["submission_artifact"]["contract_version"] == SUBMISSION_ARTIFACT_CONTRACT_VERSION
        assert (
            d["governance_evidence_artifact"]["contract_version"]
            == GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION
        )
        assert d["gate_artifact"]["gate_3_passed"] == 1
        assert d["dedup_artifact"]["kept_count"] == 1
        assert d["submission_artifact"]["strategy_count"] == 1
        assert d["submission_artifact"]["committee_review_count"] == 1
        assert d["submission_artifact"]["committee_decision_counts"]["revise"] == 1
        assert d["submission_artifact"]["constraint_check_count"] == 1
        assert d["submission_artifact"]["strategy_briefs"][0]["primary_validation_layer"] == "target"
        assert d["submission_artifact"]["strategy_briefs"][0]["refresh_mode"] == "refresh_metrics_only"
        assert d["submission_artifact"]["strategy_briefs"][0]["committee_review"]["decision"] == "revise"
        assert (
            d["submission_artifact"]["strategy_briefs"][0]["committee_review"]["accept_blockers"]
            == ["execution_floor_failed", "task_alignment_floor_failed"]
        )
        assert d["submission_artifact"]["strategy_briefs"][0]["has_committee_review"] is True
        assert d["submission_artifact"]["strategy_briefs"][0]["task_signature"].startswith("event_driven|evt_1")
        assert d["governance_evidence_artifact"]["committee_review_count"] == 1
        assert d["governance_evidence_artifact"]["multiple_testing_registry_record_count"] == 1
        assert d["governance_evidence_artifact"]["constraint_check_count"] == 1


# ---------------------------------------------------------------------------
# FactoryStatusDTO
# ---------------------------------------------------------------------------

class TestFactoryStatusDTO:
    def _sample_status(self) -> dict:
        return {
            "running": True,
            "schedule_mode": "continuous",
            "runtime_enabled": True,
            "event_runtime_mode": "live",
            "last_run": "2026-01-01T10:00:00",
            "last_result": {
                "status": "success",
                "summary": {
                    "stock_family_allocation_count": 64,
                    "family_preference_order": ["momentum", "ma_cross"],
                "family_preference_source_mode": "stock_family_allocation",
                "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                "governed_pending_candidate_count": 1,
                "external_llm_provider_health_status": "degraded",
                "external_llm_provider_control_mode": "suppress",
                "candidate_local_attempt_count": 7,
                "task_local_attempt_count": 5,
                "cohort_effective_trials": 10.5,
                "refresh_existing_count": 2,
                "spawn_revision_from_existing_count": 1,
                "unique_family_holding_universe_count": 4,
                "economic_semantics_missing_count": 3,
                "research_only_count": 2,
                "deferred_submission_count": 1,
                "validation_grade_distribution": {"D": 2},
                "raw_validation_grade_distribution": {"D": 1, "C": 1},
                "effective_validation_grade_distribution": {"C": 2},
                "raw_validation_total_score_mean": 43.5,
                "raw_validation_total_score_p50": 43.0,
                "raw_validation_total_score_p90": 47.0,
                "raw_validation_a_rate": 0.0,
                "raw_validation_b_rate": 0.0,
                "raw_validation_c_rate": 0.5,
                "raw_validation_d_rate": 0.5,
                "strict_incubation_ready_count": 1,
                "strict_incubation_ready_rate": 0.5,
                "live_candidate_ready_count": 1,
                "live_candidate_ready_rate": 0.5,
                "raw_b_or_above_count": 0,
                "raw_b_or_above_rate": 0.0,
                "strict_ready_given_raw_b_count": 0,
                "strict_ready_given_raw_b_rate": 0.0,
                "live_ready_given_raw_b_count": 0,
                "live_ready_given_raw_b_rate": 0.0,
                "validation_family_quality_panel": [
                    {
                        "strategy_family": "momentum",
                        "holding_period_bucket": "swing",
                        "validation_focus": "target_only",
                        "strategy_count": 2,
                        "raw_validation_grade_distribution": {"D": 1, "C": 1},
                    }
                ],
            },
        },
            "daily_run_count": 1,
            "max_daily_runs": 3,
            "cycle_count": 42,
            "factor_auto_refresh_enabled": True,
            "readiness_hard_block_enabled": False,
            "readiness_min_score": 0.6,
            "quality_baseline": {
                "contract_version": "strategy_factory.quality_baseline.v1",
                "submitted_strategy_cohort": {
                    "factory_strategy_count": 2,
                    "validation_grade_distribution": {"D": 2},
                    "raw_validation_grade_distribution": {"D": 1, "C": 1},
                },
            },
        }

    def test_from_dict_basic(self):
        dto = FactoryStatusDTO.from_dict(self._sample_status())
        assert dto.running is True
        assert dto.schedule_mode == "continuous"
        assert dto.cycle_count == 42
        assert dto.last_status == "success"
        assert dto.last_stock_family_allocation_count == 64
        assert dto.last_family_preference_order == ["momentum", "ma_cross"]
        assert dto.last_family_preference_source_mode == "stock_family_allocation"
        assert dto.last_governed_candidate_pool_provisional_spillover_policy_status == "spillover_applied"
        assert dto.last_external_llm_provider_health_status == "degraded"
        assert dto.last_external_llm_provider_control_mode == "suppress"
        assert dto.last_candidate_local_attempt_count == 7
        assert dto.last_cohort_effective_trials == pytest.approx(10.5)
        assert dto.last_validation_grade_distribution == {"D": 2}
        assert dto.last_raw_validation_grade_distribution == {"D": 1, "C": 1}
        assert dto.last_effective_validation_grade_distribution == {"C": 2}
        assert dto.last_raw_validation_total_score_mean == pytest.approx(43.5)
        assert dto.last_strict_incubation_ready_count == 1
        assert dto.last_live_candidate_ready_rate == pytest.approx(0.5)
        assert dto.last_raw_b_or_above_count == 0
        assert dto.quality_baseline["contract_version"] == "strategy_factory.quality_baseline.v1"

    def test_last_status_none_when_no_last_result(self):
        data = {**self._sample_status(), "last_result": None}
        dto = FactoryStatusDTO.from_dict(data)
        assert dto.last_status is None

    def test_to_dict(self):
        dto = FactoryStatusDTO.from_dict(self._sample_status())
        d = dto.to_dict()
        for key in ["running", "schedule_mode", "runtime_enabled", "cycle_count"]:
            assert key in d
        assert d["last_stock_family_allocation_count"] == 64
        assert d["last_family_preference_order"] == ["momentum", "ma_cross"]
        assert d["last_candidate_local_attempt_count"] == 7
        assert d["last_research_only_count"] == 2
        assert d["last_validation_grade_distribution"] == {"D": 2}
        assert d["last_raw_validation_grade_distribution"] == {"D": 1, "C": 1}
        assert d["last_strict_incubation_ready_rate"] == pytest.approx(0.5)
        assert d["last_live_candidate_ready_count"] == 1
        assert d["last_validation_family_quality_panel"][0]["strategy_family"] == "momentum"
        assert d["quality_baseline"]["submitted_strategy_cohort"]["factory_strategy_count"] == 2

    def test_from_dict_falls_back_to_last_submission_artifact_quality_panel(self):
        data = self._sample_status()
        data["last_result"] = {
            "status": "success",
            "summary": {
                "stock_family_allocation_count": 64,
                "family_preference_order": ["momentum", "ma_cross"],
            },
            "stages": {
                "submit": {
                    "status": "completed",
                    "ok": True,
                    "strategies": [
                        {
                            "strategy_id": "sid_last_fallback_1",
                            "candidate_family": "momentum",
                            "holding_period_bucket": "medium",
                            "submission_lane": "deferred_submission",
                            "quality_summary": {
                                "validation_grade": "C",
                                "raw_validation_grade": "B",
                                "effective_validation_grade": "C",
                                "raw_validation_total_score": 55.0,
                                "candidate_family": "momentum",
                                "holding_period_bucket": "medium",
                            },
                        }
                    ],
                }
            },
        }

        dto = FactoryStatusDTO.from_dict(data)

        assert dto.last_raw_validation_grade_distribution == {"B": 1}
        assert dto.last_raw_validation_b_rate == pytest.approx(1.0)
        assert dto.last_validation_family_quality_panel[0]["strategy_family"] == "momentum"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestNormalizeHelpers:
    def test_normalize_to_detail(self):
        dto = normalize_run_result_to_detail(_SAMPLE_RUN_RESULT)
        assert isinstance(dto, FactoryRunDetailDTO)
        assert dto.summary.status == "success"

    def test_normalize_to_summary(self):
        dto = normalize_run_result_to_summary(_SAMPLE_RUN_RESULT)
        assert isinstance(dto, FactoryRunSummaryDTO)
        assert dto.run_id == "run_001"

    def test_normalize_empty_dict(self):
        dto = normalize_run_result_to_summary({})
        assert dto.status == "failed"

    def test_normalize_detail_empty_stages(self):
        dto = normalize_run_result_to_detail({"run_id": "r", "status": "skipped", "stages": {}})
        assert dto.stages == []


# ---------------------------------------------------------------------------
# Import contract – api/__init__ exports
# ---------------------------------------------------------------------------

def test_api_init_exports_dtos():
    from strategy_factory import api
    for name in [
        "FactoryRunDetailDTO",
        "FactoryRunSummaryDTO",
        "FactoryStatusDTO",
        "StageResultDTO",
        "normalize_run_result_to_detail",
        "normalize_run_result_to_summary",
    ]:
        assert hasattr(api, name), f"strategy_factory.api missing: {name}"
