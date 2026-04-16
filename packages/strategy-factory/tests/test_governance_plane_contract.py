from strategy_factory.application.governance_plane_contract import (
    DEDUP_ARTIFACT_CONTRACT_VERSION,
    GATE_ARTIFACT_CONTRACT_VERSION,
    GATE_ARTIFACT_V2_CONTRACT_VERSION,
    GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    GOVERNANCE_PLANE_CONTRACT_VERSION,
    GOVERNANCE_PLANE_V2_CONTRACT_VERSION,
    PREDICTION_TRACE_CONTRACT_VERSION,
    SUBMISSION_ARTIFACT_CONTRACT_VERSION,
    build_governance_plane_artifact,
)


def test_governance_plane_contract_builds_gate_dedup_submission_and_evidence_artifacts():
    artifact = build_governance_plane_artifact(
        quality_gate_report={
            "gate_0": {"passed_count": 6, "failed_count": 2},
            "pre_gate": {"passed_count": 5, "failed_count": 1},
            "gate_1": {"passed_count": 4, "failed_count": 1},
            "gate_2": {"input_count": 4, "passed_count": 3, "failed_count": 1},
            "gate_3": {
                "input_count": 3,
                "pending_count": 0,
                "passed_count": 2,
                "failed_count": 1,
                "provisional_passed_count": 1,
                "failure_reason_topn": [{"reason_code": "attempt_adjusted_penalty", "count": 1}],
            },
        },
        backtest_report={
            "summary": {
                "input_count": 4,
                "passed_count": 3,
                "failed_count": 1,
                "failed_reason_counts": {"capacity_guard": 1},
                "thresholds_by_type": {"momentum": {"sharpe_ratio": 0.8}},
            }
        },
        dedup_report={
            "summary": {
                "input_count": 3,
                "existing_count": 1,
                "kept_count": 2,
                "dropped_count": 1,
                "refreshed_existing_count": 1,
                "vector_checks": 3,
                "coarse_hit_ratio": 0.5,
                "refresh_decision_basis_counts": {"tested_object_hash_changed": 1},
            },
            "kept": [
                {
                    "strategy_type": "momentum",
                    "generator_type": "external_llm",
                    "target_symbols": ["600519"],
                    "dedup_result": {
                        "duplicate": False,
                        "refresh_existing": True,
                        "refresh_mode": "refresh_metrics_only",
                        "refresh_decision_basis": "tested_object_hash_changed",
                        "target_overlap": 1.0,
                    },
                }
            ],
            "dropped": [
                {
                    "strategy_type": "value_factor",
                    "target_symbols": ["000858"],
                    "dedup_result": {
                        "duplicate": True,
                        "duplicate_level": "strict",
                        "refresh_existing": False,
                    },
                }
            ],
        },
        submit_result={
            "created": 1,
            "created_total": 1,
            "created_strategy_pool": 1,
            "created_audit_only": 0,
            "refreshed": 1,
            "gate_3_input": 2,
            "submitted": 2,
            "passed_quality_gate": 2,
            "gate_3_passed": 2,
            "gate_3_failed": 0,
            "gate_3_provisional_passed": 1,
            "incubation_budget_summary": {"family_counts": {"momentum": 1}},
            "strategies": [
                {
                    "strategy_id": "sid_1",
                    "name": "治理候选一号",
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
                        "expansion_applied": True,
                        "expansion_reason": "strict_intersection_trimmed",
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
                    "raw_validation_grade": "C",
                    "effective_validation_grade": "B",
                    "validation_grade_adjustment_reason": "committee_override_after_runtime_review",
                    "raw_validation_total_score": 58.0,
                    "validation_total_score": 62.0,
                    "strict_incubation_ready": True,
                    "live_candidate_ready": False,
                    "trade_density": 0.84,
                    "post_cost_sharpe": 1.12,
                    "run_correction": {"deflated_sharpe_ratio": 0.16, "pbo": 0.42},
                    "candidate_family": "momentum",
                    "generator_mode": "external_llm",
                    "vector_profile_id": "vp_1",
                    "multiple_testing_registry": {"available": True},
                    "multiple_testing_registry_record_id": "mt_1",
                    "candidate_lineage_contract": {"lineage_id": "lineage_1"},
                    "cost_assumptions": {"commission_bps": 8},
                    "explicit_cost_breakdown": {"commission_bps": 8},
                    "implicit_cost_breakdown": {"slippage_bps": 12},
                    "execution_reality": {"tradability_filter": True},
                    "backtest_assumptions": {
                        "slippage_bps": 12,
                        "market_impact_bps": 6,
                        "capacity_participation_rate": 0.2,
                        "tradability_filter": True,
                    },
                }
            ],
        },
    )

    assert artifact["contract_version"] == GOVERNANCE_PLANE_CONTRACT_VERSION
    assert artifact["available"] is True
    assert artifact["gate_artifact"]["contract_version"] == GATE_ARTIFACT_CONTRACT_VERSION
    assert artifact["dedup_artifact"]["contract_version"] == DEDUP_ARTIFACT_CONTRACT_VERSION
    assert artifact["submission_artifact"]["contract_version"] == SUBMISSION_ARTIFACT_CONTRACT_VERSION
    assert (
        artifact["evidence_artifact"]["contract_version"]
        == GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION
    )
    assert artifact["gate_artifact"]["gate_2_passed"] == 3
    assert artifact["dedup_artifact"]["refresh_mode_counts"]["refresh_metrics_only"] == 1
    assert artifact["submission_artifact"]["submission_lane_counts"]["paper"] == 1
    assert artifact["submission_artifact"]["primary_validation_layer_counts"]["target"] == 1
    assert artifact["submission_artifact"]["validation_profile_counts"]["event_trade_validation"] == 1
    assert artifact["submission_artifact"]["committee_decision_counts"]["revise"] == 1
    assert artifact["submission_artifact"]["committee_review_count"] == 1
    assert artifact["submission_artifact"]["constraint_violation_counts"]["strict_intersection_trimmed"] == 1
    assert artifact["submission_artifact"]["constraint_check_count"] == 1
    assert artifact["submission_artifact"]["event_window_config_count"] == 1
    assert artifact["submission_artifact"]["attempt_adjustment_count"] == 1
    assert artifact["submission_artifact"]["task_signature_count"] == 1
    assert artifact["submission_artifact"]["validation_grade_distribution"] == {"B": 1}
    assert artifact["submission_artifact"]["raw_validation_grade_distribution"] == {"C": 1}
    assert artifact["submission_artifact"]["effective_validation_grade_distribution"] == {"B": 1}
    assert artifact["submission_artifact"]["raw_validation_total_score_mean"] == 58.0
    assert artifact["submission_artifact"]["raw_validation_b_rate"] == 0.0
    assert artifact["submission_artifact"]["strict_incubation_ready_count"] == 1
    assert artifact["submission_artifact"]["strict_incubation_ready_rate"] == 1.0
    assert artifact["submission_artifact"]["live_candidate_ready_count"] == 0
    assert artifact["submission_artifact"]["raw_b_or_above_count"] == 0
    assert artifact["submission_artifact"]["strict_ready_given_raw_b_rate"] == 0.0
    assert artifact["submission_artifact"]["validation_family_quality_panel"][0]["strategy_family"] == "momentum"
    assert (
        artifact["submission_artifact"]["validation_family_quality_panel"][0]["raw_validation_grade_distribution"]
        == {"C": 1}
    )
    assert (
        artifact["submission_artifact"]["validation_family_quality_panel"][0]["family_mean_trade_density"]
        == 0.84
    )
    assert artifact["submission_artifact"]["validation_family_quality_panel"][0]["family_mean_dsr"] == 0.16
    assert artifact["submission_artifact"]["strategy_briefs"][0]["primary_validation_layer"] == "target"
    assert artifact["submission_artifact"]["strategy_briefs"][0]["refresh_mode"] == "refresh_metrics_only"
    assert artifact["submission_artifact"]["strategy_briefs"][0]["raw_validation_grade"] == "C"
    assert artifact["submission_artifact"]["strategy_briefs"][0]["effective_validation_grade"] == "B"
    assert (
        artifact["submission_artifact"]["strategy_briefs"][0]["validation_grade_adjustment_reason"]
        == "committee_override_after_runtime_review"
    )
    assert (
        artifact["submission_artifact"]["strategy_briefs"][0]["validation_profile"]["profile"]
        == "event_trade_validation"
    )
    assert (
        artifact["submission_artifact"]["strategy_briefs"][0]["constraint_check"]["constraint_violation"]
        == "strict_intersection_trimmed"
    )
    assert (
        artifact["submission_artifact"]["strategy_briefs"][0]["committee_review"]["decision"] == "revise"
    )
    assert (
        artifact["submission_artifact"]["strategy_briefs"][0]["committee_review"]["accept_blockers"]
        == ["execution_floor_failed", "task_alignment_floor_failed"]
    )
    assert artifact["submission_artifact"]["strategy_briefs"][0]["has_committee_review"] is True
    assert (
        artifact["submission_artifact"]["strategy_briefs"][0]["attempt_adjustment"]["penalty"] == 0.03
    )
    assert artifact["evidence_artifact"]["multiple_testing_registry_record_count"] == 1
    assert artifact["evidence_artifact"]["committee_review_count"] == 1
    assert artifact["evidence_artifact"]["constraint_check_count"] == 1
    assert artifact["evidence_artifact"]["validation_profile_count"] == 1
    assert artifact["evidence_artifact"]["event_window_config_count"] == 1
    assert artifact["evidence_artifact"]["attempt_adjustment_count"] == 1
    assert artifact["evidence_artifact"]["task_signature_count"] == 1
    assert artifact["evidence_artifact"]["capacity_assumption_count"] == 1
    assert artifact["evidence_artifact"]["extension_interface_support"]["constraint_check_supported"] is True
    assert artifact["evidence_artifact"]["extension_interface_support"]["committee_review_supported"] is True
    assert artifact["evidence_artifact"]["extension_interface_support"]["refresh_mode_supported"] is True
    assert artifact["source_chain"] == [
        "governance.gate_artifact",
        "governance.dedup_artifact",
        "governance.submission_artifact",
        "governance.evidence_artifact",
        "governance.gate_artifact_v2",
    ]


def test_governance_plane_contract_supports_empty_runs():
    artifact = build_governance_plane_artifact()

    assert artifact["contract_version"] == GOVERNANCE_PLANE_CONTRACT_VERSION
    assert artifact["available"] is False
    assert artifact["gate_artifact"]["available"] is False
    assert artifact["dedup_artifact"]["available"] is False
    assert artifact["submission_artifact"]["available"] is False
    assert artifact["evidence_artifact"]["available"] is False


def test_governance_plane_contract_dual_writes_v2_gate_and_trace_views():
    artifact = build_governance_plane_artifact(
        candidates=[
            {
                "prediction_trace_id": "pred_trace_1",
                "research_protocol_version": "strategy_factory.research_protocol.v2",
                "candidate_contract_version": "strategy_factory.candidate_contract.v2",
                "spec_completeness": "incomplete",
                "completion_issues": [
                    {"field": "walk_forward_config", "reason_code": "research_protocol_required_field_legacy_default"}
                ],
                "execution_semantic_gap": True,
            }
        ],
        quality_gate_report={
            "gate_0": {"passed_count": 1, "failed_count": 0},
            "pre_gate": {"passed_count": 1, "failed_count": 0},
            "gate_1": {"passed_count": 1, "failed_count": 0},
            "gate_2": {"input_count": 1, "passed_count": 1, "failed_count": 0},
            "gate_3": {"input_count": 1, "passed_count": 1, "failed_count": 0},
        },
        submit_result={
            "submitted": 1,
            "gate_3_passed": 1,
            "strategies": [
                {
                    "strategy_id": "sid_v2",
                    "prediction_trace_id": "pred_trace_1",
                    "research_protocol_version": "strategy_factory.research_protocol.v2",
                    "candidate_contract_version": "strategy_factory.candidate_contract.v2",
                    "spec_completeness": "incomplete",
                    "execution_audit_gate_status": "ready",
                    "promotion_ready": False,
                }
            ],
        },
    )

    assert artifact["gate_artifact_v2"]["contract_version"] == GATE_ARTIFACT_V2_CONTRACT_VERSION
    assert artifact["governance_plane_v2"]["contract_version"] == GOVERNANCE_PLANE_V2_CONTRACT_VERSION
    assert artifact["prediction_trace_summary"]["contract_version"] == PREDICTION_TRACE_CONTRACT_VERSION
    assert artifact["gate_a"]["gate_name"] == "gate_a"
    assert artifact["gate_a"]["decision"] == "reject"
    assert artifact["gate_a"]["hard_failures"][0]["reason_code"] == "execution_semantic_gap"
    assert artifact["gate_a"]["evidence_gap_codes"] == ["research_protocol_required_field_legacy_default"]
    assert artifact["gate_a"]["status"] == "blocked"
    assert artifact["gate_b"]["status"] == "passed"
    assert artifact["gate_c"]["status"] == "observe"
    assert (
        artifact["protocol_versions"]["research_protocol_version_counts"]["strategy_factory.research_protocol.v2"]
        == 2
    )
    assert artifact["prediction_trace_summary"]["trace_count"] == 1
    assert artifact["prediction_trace_summary"]["missing_count"] == 1
    assert artifact["prediction_trace_ledger"]["trace_count"] == 1
    assert artifact["governance_plane_v2"]["prediction_trace_ledger"]["entries"][0]["prediction_trace_id"] == "pred_trace_1"


def test_governance_plane_contract_trace_ledger_does_not_treat_account_only_as_intended_order():
    artifact = build_governance_plane_artifact(
        submit_result={
            "submitted": 1,
            "strategies": [
                {
                    "strategy_id": "sid_account_only",
                    "prediction_trace_id": "pred_trace_account_only",
                    "paper_account_id": "paper_only_1",
                    "execution_quality_snapshot": {
                        "order_count": 0,
                        "trade_count": 0,
                        "realized_trade_count": 0,
                    },
                }
            ],
        }
    )

    entry = artifact["prediction_trace_ledger"]["entries"][0]
    assert entry["prediction_trace_id"] == "pred_trace_account_only"
    assert entry["intended_order"]["available"] is False
    assert entry["intended_order"]["source_mode"] == "summary_fallback"
    assert "missing_intended_order" in entry["evidence_gap_codes"]


def test_governance_plane_contract_prefers_strategy_level_prediction_trace_ledger():
    artifact = build_governance_plane_artifact(
        submit_result={
            "submitted": 1,
            "strategies": [
                {
                    "strategy_id": "sid_entity_1",
                    "prediction_trace_id": "pred_trace_entity_1",
                    "prediction_trace_ledger": {
                        "prediction_trace_id": "pred_trace_entity_1",
                        "hypothesis_spec": {
                            "available": True,
                            "source_mode": "entity_backed",
                            "count": 1,
                            "dsl_signature": "rsi_reversal_v7",
                        },
                        "signal_event": {
                            "available": True,
                            "source_mode": "entity_backed",
                            "count": 3,
                            "recent_signal_ids": ["sig_3", "sig_2", "sig_1"],
                            "latest_signal_snapshot_id": "snap_1",
                        },
                        "intended_order": {
                            "available": True,
                            "source_mode": "entity_backed",
                            "count": 2,
                            "order_ids": ["ord_2", "ord_1"],
                            "paper_account_id": "acct_1",
                        },
                        "actual_fill": {
                            "available": True,
                            "source_mode": "entity_backed",
                            "count": 2,
                            "trade_ids": ["trd_2", "trd_1"],
                            "realized_trade_count": 2,
                        },
                        "position_round_trip": {
                            "available": True,
                            "source_mode": "entity_backed",
                            "count": 1,
                            "position_ids": ["pos_1"],
                            "closed_position_count": 1,
                            "round_trip_close_rate": 1.0,
                        },
                        "pnl_audit_summary": {
                            "available": True,
                            "source_mode": "entity_backed",
                            "count": 5,
                            "nav_row_count": 5,
                            "realized_pnl_total": 1234.5,
                            "trade_expectancy": 0.08,
                        },
                        "gate_decisions": {
                            "execution_audit_gate_status": "passed",
                            "promotion_ready": True,
                            "hard_gate_passed": True,
                            "failure_reasons": [],
                        },
                        "evidence_gap_codes": [],
                    },
                    "candidate_family": "mean_reversion",
                    "status": "incubating",
                    "submission_lane": "paper",
                }
            ],
        }
    )

    entry = artifact["prediction_trace_ledger"]["entries"][0]
    assert entry["signal_event"]["source_mode"] == "entity_backed"
    assert entry["signal_event"]["count"] == 3
    assert entry["signal_event"]["recent_signal_ids"] == ["sig_3", "sig_2", "sig_1"]
    assert entry["intended_order"]["order_ids"] == ["ord_2", "ord_1"]
    assert entry["actual_fill"]["trade_ids"] == ["trd_2", "trd_1"]
    assert entry["position_round_trip"]["position_ids"] == ["pos_1"]
    assert entry["pnl_audit_summary"]["realized_pnl_total"] == 1234.5
    assert entry["gate_decisions"]["execution_audit_gate_status"] == "passed"
    assert entry["gate_decisions"]["hard_gate_passed"] is True


def test_governance_plane_contract_aggregates_raw_family_panel_from_quality_summary():
    artifact = build_governance_plane_artifact(
        submit_result={
            "created": 1,
            "created_total": 1,
            "created_strategy_pool": 1,
            "created_audit_only": 0,
            "refreshed": 0,
            "gate_3_input": 1,
            "submitted": 1,
            "passed_quality_gate": 1,
            "gate_3_passed": 1,
            "gate_3_failed": 0,
            "gate_3_provisional_passed": 0,
            "strategies": [
                {
                    "strategy_id": "sid_quality_summary_only",
                    "name": "只保留 quality summary 的候选",
                    "status": "submitted",
                    "submission_lane": "deferred_submission",
                    "candidate_family": "momentum",
                    "holding_period_bucket": "medium",
                    "generator_mode": "rule",
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
        }
    )

    assert artifact["submission_artifact"]["validation_grade_distribution"] == {"C": 1}
    assert artifact["submission_artifact"]["raw_validation_grade_distribution"] == {"B": 1}
    assert artifact["submission_artifact"]["raw_validation_b_rate"] == 1.0
    assert artifact["submission_artifact"]["raw_b_or_above_count"] == 1
    assert artifact["submission_artifact"]["raw_b_or_above_rate"] == 1.0
    assert artifact["submission_artifact"]["raw_validation_total_score_mean"] == 56.0
    assert artifact["submission_artifact"]["validation_family_quality_panel"][0]["strategy_family"] == "momentum"
    assert (
        artifact["submission_artifact"]["validation_family_quality_panel"][0]["raw_validation_grade_distribution"]
        == {"B": 1}
    )
    assert artifact["submission_artifact"]["validation_family_quality_panel"][0]["family_raw_b_rate"] == 1.0


def test_governance_plane_contract_falls_back_to_gate_review_context_for_raw_panel():
    artifact = build_governance_plane_artifact(
        submit_result={
            "created": 0,
            "created_total": 0,
            "created_strategy_pool": 0,
            "created_audit_only": 0,
            "refreshed": 0,
            "gate_3_input": 1,
            "submitted": 0,
            "passed_quality_gate": 0,
            "gate_3_passed": 0,
            "gate_3_failed": 1,
            "gate_3_provisional_passed": 0,
            "strategies": [
                {
                    "strategy_id": "sid_gate_only",
                    "name": "只保留 gate 的候选",
                    "status": "rejected",
                    "submission_lane": "rejected",
                    "candidate_family": "momentum",
                    "holding_period_bucket": "medium",
                    "generator_mode": "rule",
                    "gate_3": {
                        "trade_density": 1.28,
                        "post_cost_sharpe": 1.12,
                        "deflated_sharpe_ratio": 0.08,
                        "pbo": 0.41,
                        "validation_focus": "candidate_target_only",
                        "strict_incubation_ready": True,
                        "cohort_effective_trials": 7.0,
                        "admission_review_context": {"validation_grade": "D"},
                        "admission_evaluations": {
                            "incubation": {
                                "review_context": {"validation_grade": "D"},
                            }
                        },
                    },
                }
            ],
        }
    )

    submission = artifact["submission_artifact"]
    assert submission["raw_validation_grade_distribution"] == {"D": 1}
    assert submission["validation_grade_distribution"] == {"D": 1}
    assert submission["cohort_effective_trials"] == 7.0
    panel = submission["validation_family_quality_panel"][0]
    assert panel["strategy_family"] == "momentum"
    assert panel["validation_focus"] == "candidate_target_only"
    assert panel["raw_validation_grade_distribution"] == {"D": 1}
    assert panel["strict_incubation_ready_count"] == 1
    assert panel["strict_ready_given_raw_b_rate"] == 0.0
    assert panel["mean_trade_density"] == 1.28
    assert panel["mean_post_cost_sharpe"] == 1.12
    assert panel["mean_deflated_sharpe_ratio"] == 0.08
    assert panel["mean_pbo"] == 0.41
