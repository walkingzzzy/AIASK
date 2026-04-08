from strategy_factory.application.governance_plane_contract import (
    DEDUP_ARTIFACT_CONTRACT_VERSION,
    GATE_ARTIFACT_CONTRACT_VERSION,
    GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    GOVERNANCE_PLANE_CONTRACT_VERSION,
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
    assert artifact["submission_artifact"]["strategy_briefs"][0]["primary_validation_layer"] == "target"
    assert artifact["submission_artifact"]["strategy_briefs"][0]["refresh_mode"] == "refresh_metrics_only"
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
    ]


def test_governance_plane_contract_supports_empty_runs():
    artifact = build_governance_plane_artifact()

    assert artifact["contract_version"] == GOVERNANCE_PLANE_CONTRACT_VERSION
    assert artifact["available"] is False
    assert artifact["gate_artifact"]["available"] is False
    assert artifact["dedup_artifact"]["available"] is False
    assert artifact["submission_artifact"]["available"] is False
    assert artifact["evidence_artifact"]["available"] is False
