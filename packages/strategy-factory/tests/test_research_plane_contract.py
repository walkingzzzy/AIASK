from strategy_factory.application.research_plane_contract import (
    CANDIDATE_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_PLANE_CONTRACT_VERSION,
    TASK_ARTIFACT_CONTRACT_VERSION,
    build_research_plane_artifact,
)


def test_research_plane_contract_builds_factor_task_candidate_and_evidence_artifacts():
    factor_research = {
        "summary": {
            "factor_source_mode": "governed_candidate_pool",
            "stale": False,
            "active_factor_count": 2,
            "active_candidate_count": 3,
            "active_family_names": ["momentum", "value_factor"],
            "active_regime_names": ["trend"],
            "top_factor_names": ["momentum_20d", "value_rank"],
            "top_candidate_names": ["candidate_alpha"],
            "family_preference_order": ["momentum", "value_factor", "ma_cross"],
            "family_preference_source_mode": "stock_family_allocation",
            "governed_candidate_pool_mode": "strict_governed",
            "governed_candidate_pool_provisional": False,
            "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
            "governed_candidate_pool_provisional_pending_count": 0,
            "governed_candidate_pool_strict_shortfall_count": 2,
            "stock_family_allocation_count": 8,
            "stock_family_allocation_source_mode": "stock_universe_projection",
            "factor_llm_provider_health_status": "healthy",
            "factor_llm_provider_ready": True,
        },
        "source_chain": ["snapshot.factor_ic", "factor_scheduler.status"],
        "lifecycle_feedback_input": {
            "contract_version": "strategy_factory.lifecycle_feedback_input.v1",
            "available": True,
        },
        "family_reward_table": {
            "momentum": {
                "budget_weight": 0.62,
                "feedback_budget_multiplier": 1.1,
                "feedback_priority_adjustment": 0.08,
                "promotion_ready_ratio": 0.4,
                "forward_window_coverage_ratio": 0.55,
                "family_route_action": "family_explore",
            }
        },
        "family_debt_table": {
            "momentum": {
                "zero_signal_ratio": 0.2,
                "low_signal_ratio": 0.3,
                "evidence_debt_ratio": 0.15,
                "control_mode": "normal",
                "control_reasons": [],
                "family_freeze_active": False,
                "family_route_action": "family_explore",
            }
        },
        "search_route_actions": [
            {
                "family": "momentum",
                "scope": "family",
                "action": "family_explore",
                "control_mode": "normal",
                "budget_weight": 0.62,
                "budget_multiplier": 1.1,
                "priority_adjustment": 0.08,
                "reasons": [],
            }
        ],
        "top_candidate_lineage": [
            {
                "artifact_id": "candidate_alpha",
                "name": "candidate_alpha",
                "family": "momentum",
                "registry_stage": "governed",
                "latest_validation_at": "2026-04-08T09:30:00+08:00",
            }
        ],
    }
    readiness = {
        "decision": "proceed",
        "readiness_score": 0.93,
        "can_proceed": True,
        "blocking_reason_codes": [],
    }
    autonomy_stage = {
        "task_count": 2,
        "completed_task_count": 2,
        "failed_task_count": 0,
        "generated_count": 2,
        "task_source_counts": {"snapshot": 1, "event_driven": 1},
        "event_task_count": 1,
        "snapshot_task_count": 1,
        "bulk_stock_task_count": 0,
        "event_evidence_count": 3,
        "experiment_count": 2,
        "task_run_ids": ["task_run_1", "task_run_2"],
        "external_llm_status": "succeeded",
        "external_llm_status_counts": {"succeeded": 2},
        "external_llm_attempt_count": 2,
        "external_llm_network_request_count": 2,
        "external_llm_real_request_count": 2,
        "external_llm_selected_count": 1,
        "external_llm_effective_response_count": 2,
        "external_llm_effective_response_ratio": 1.0,
        "external_llm_provider_health_status": "healthy",
        "task_scan": {
            "summary": {
                "bulk_stock_matrix_enabled": False,
                "bulk_stock_matrix_stock_count": 0,
                "bulk_stock_matrix_eligible_stock_count": 0,
            },
            "tasks": [
                {
                    "task_id": "snapshot_1",
                    "task_source": "snapshot",
                    "candidate_family": "momentum",
                    "generation_limit": 2,
                    "target_symbols": ["600519"],
                },
                {
                    "task_id": "event_1",
                    "task_source": "event_driven",
                    "candidate_family": "value_factor",
                    "generation_limit": 1,
                    "target_symbols": ["000858"],
                    "event_id": "evt_1",
                },
            ],
        },
        "task_results": [
            {
                "task": {
                    "task_id": "snapshot_1",
                    "task_source": "snapshot",
                    "candidate_family": "momentum",
                    "target_symbols": ["600519"],
                },
                "task_run_id": "task_run_1",
                "status": "completed",
                "generated_count": 1,
                "evidence_count": 1,
                "external_llm_status": "succeeded",
            },
            {
                "task": {
                    "task_id": "event_1",
                    "task_source": "event_driven",
                    "candidate_family": "value_factor",
                    "target_symbols": ["000858"],
                    "event_id": "evt_1",
                },
                "task_run_id": "task_run_2",
                "status": "completed",
                "generated_count": 1,
                "evidence_count": 2,
                "external_llm_status": "succeeded",
            },
        ],
    }
    candidates = [
        {
            "name": "candidate_alpha",
            "strategy_type": "momentum",
            "target_symbols": ["600519"],
            "spawn_reason": "fear_greed local rule",
            "generation_reason": {"source": "fear_greed"},
            "candidate_contract_snapshot": {"targeting": {"target_pool_id": "explicit:600519"}},
            "params": {"candidate_provenance": {"generator_mode": "rule"}},
            "candidate_evidence_status": {"required_audits_complete": True},
        },
        {
            "name": "candidate_beta",
            "strategy_type": "value_factor",
            "target_symbols": ["000858"],
            "experiment_id": "exp_beta",
            "research_task": {"task_source": "event_driven", "candidate_family": "value_factor"},
            "params": {"candidate_provenance": {"generator_mode": "external_llm"}},
        },
    ]
    experiments = [
        {"experiment_id": "exp_alpha", "task_id": "snapshot_1", "status": "recorded"},
        {"experiment_id": "exp_beta", "task_id": "event_1", "status": "recorded"},
    ]

    artifact = build_research_plane_artifact(
        factor_research=factor_research,
        readiness=readiness,
        autonomy_stage=autonomy_stage,
        candidates=candidates,
        experiments=experiments,
    )

    assert artifact["contract_version"] == RESEARCH_PLANE_CONTRACT_VERSION
    assert artifact["available"] is True
    assert artifact["research_artifact"]["contract_version"] == RESEARCH_ARTIFACT_CONTRACT_VERSION
    assert artifact["task_artifact"]["contract_version"] == TASK_ARTIFACT_CONTRACT_VERSION
    assert artifact["candidate_artifact"]["contract_version"] == CANDIDATE_ARTIFACT_CONTRACT_VERSION
    assert (
        artifact["evidence_artifact"]["contract_version"]
        == RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION
    )
    assert artifact["research_artifact"]["active_candidate_count"] == 3
    assert artifact["research_artifact"]["family_preference_order"] == ["momentum", "value_factor", "ma_cross"]
    assert artifact["research_artifact"]["family_preference_source_mode"] == "stock_family_allocation"
    assert artifact["research_artifact"]["governed_candidate_pool_provisional_spillover_policy_status"] == "spillover_applied"
    assert artifact["research_artifact"]["governed_candidate_pool_strict_shortfall_count"] == 2
    assert artifact["research_artifact"]["lifecycle_feedback_input_contract_version"] == "strategy_factory.lifecycle_feedback_input.v1"
    assert artifact["research_artifact"]["lifecycle_feedback_input_available"] is True
    assert artifact["research_artifact"]["family_reward_table"]["momentum"]["budget_weight"] == 0.62
    assert artifact["research_artifact"]["family_debt_table"]["momentum"]["control_mode"] == "normal"
    assert artifact["research_artifact"]["search_route_actions"][0]["action"] == "family_explore"
    assert artifact["research_artifact"]["search_route_action_counts"] == {"family_explore": 1}
    assert artifact["task_artifact"]["planned_task_count"] == 2
    assert artifact["task_artifact"]["task_source_counts"] == {"snapshot": 1, "event_driven": 1}
    assert artifact["task_artifact"]["task_origin_counts"] == {"open_research": 2}
    assert artifact["candidate_artifact"]["candidate_count"] == 2
    assert artifact["candidate_artifact"]["candidate_origin_counts"] == {
        "local_rule": 1,
        "external_autonomy": 1,
    }
    assert artifact["candidate_artifact"]["local_rule_candidate_count"] == 1
    assert artifact["candidate_artifact"]["external_autonomy_candidate_count"] == 1
    assert artifact["candidate_artifact"]["generator_type_counts"] == {"rule": 1, "external_llm": 1}
    assert artifact["candidate_artifact"]["family_counts"] == {"momentum": 1, "value_factor": 1}
    assert artifact["evidence_artifact"]["task_evidence_count"] == 3
    assert artifact["evidence_artifact"]["experiment_count"] == 2
    assert artifact["evidence_artifact"]["external_llm_status"] == "succeeded"
    assert artifact["evidence_artifact"]["task_origin_counts"] == {"open_research": 2}


def test_research_plane_contract_exposes_lifecycle_feedback_summary_counts():
    artifact = build_research_plane_artifact(
        factor_research={
            "summary": {
                "factor_source_mode": "governed_candidate_pool",
                "budget_feedback_family_count": 3,
                "budget_feedback_strategy_count": 12,
                "budget_feedback_target_pool_scope_count": 2,
                "budget_feedback_holding_bucket_scope_count": 2,
                "budget_feedback_generator_mode_scope_count": 1,
                "budget_feedback_runtime_alert_count": 4,
                "budget_feedback_runtime_risk_event_count": 5,
                "budget_feedback_promotion_review_count": 2,
                "budget_feedback_promotion_review_status_counts": {"watch": 1, "approved": 1},
                "budget_feedback_signal_count_total": 24,
                "budget_feedback_zero_signal_strategy_count": 5,
                "budget_feedback_zero_signal_ratio": 0.4167,
                "budget_feedback_low_signal_strategy_count": 8,
                "budget_feedback_low_signal_ratio": 0.6667,
                "budget_feedback_observed_forward_window_count": 18,
                "budget_feedback_missing_forward_window_count": 30,
                "budget_feedback_expected_forward_window_count": 48,
                "budget_feedback_forward_window_coverage_ratio": 0.375,
                "budget_feedback_promotion_ready_count": 2,
                "budget_feedback_promotion_ready_ratio": 0.1667,
                "budget_feedback_promotion_review_coverage_ratio": 0.1667,
                "budget_feedback_evidence_debt_strategy_count": 9,
                "budget_feedback_evidence_debt_ratio": 0.5896,
            },
            "lifecycle_feedback_input": {
                "contract_version": "strategy_factory.lifecycle_feedback_input.v1",
                "available": True,
            },
        },
    )

    research_artifact = artifact["research_artifact"]
    assert research_artifact["lifecycle_feedback_family_count"] == 3
    assert research_artifact["lifecycle_feedback_strategy_count"] == 12
    assert research_artifact["lifecycle_feedback_target_pool_scope_count"] == 2
    assert research_artifact["lifecycle_feedback_holding_bucket_scope_count"] == 2
    assert research_artifact["lifecycle_feedback_generator_mode_scope_count"] == 1
    assert research_artifact["lifecycle_feedback_runtime_alert_count"] == 4
    assert research_artifact["lifecycle_feedback_runtime_risk_event_count"] == 5
    assert research_artifact["lifecycle_feedback_promotion_review_count"] == 2
    assert research_artifact["lifecycle_feedback_promotion_review_status_counts"] == {
        "watch": 1,
        "approved": 1,
    }
    assert research_artifact["lifecycle_feedback_signal_count_total"] == 24
    assert research_artifact["lifecycle_feedback_zero_signal_strategy_count"] == 5
    assert research_artifact["lifecycle_feedback_zero_signal_ratio"] == 0.4167
    assert research_artifact["lifecycle_feedback_low_signal_strategy_count"] == 8
    assert research_artifact["lifecycle_feedback_low_signal_ratio"] == 0.6667
    assert research_artifact["lifecycle_feedback_observed_forward_window_count"] == 18
    assert research_artifact["lifecycle_feedback_missing_forward_window_count"] == 30
    assert research_artifact["lifecycle_feedback_expected_forward_window_count"] == 48
    assert research_artifact["lifecycle_feedback_forward_window_coverage_ratio"] == 0.375
    assert research_artifact["lifecycle_feedback_promotion_ready_count"] == 2
    assert research_artifact["lifecycle_feedback_promotion_ready_ratio"] == 0.1667
    assert research_artifact["lifecycle_feedback_promotion_review_coverage_ratio"] == 0.1667
    assert research_artifact["lifecycle_feedback_evidence_debt_strategy_count"] == 9
    assert research_artifact["lifecycle_feedback_evidence_debt_ratio"] == 0.5896
    assert research_artifact["family_reward_table"] == {}
    assert research_artifact["family_debt_table"] == {}
    assert research_artifact["search_route_actions"] == []


def test_research_plane_contract_supports_factor_only_runs():
    artifact = build_research_plane_artifact(
        factor_research={
            "summary": {
                "factor_source_mode": "seed_fallback",
                "stale": True,
                "active_factor_count": 1,
                "active_candidate_count": 0,
            }
        },
        readiness={
            "decision": "blocked",
            "readiness_score": 0.42,
            "can_proceed": False,
            "blocking_reason_codes": ["governed_candidate_pool_required"],
        },
    )

    assert artifact["available"] is True
    assert artifact["research_artifact"]["available"] is True
    assert artifact["task_artifact"]["available"] is False
    assert artifact["candidate_artifact"]["available"] is False
    assert artifact["evidence_artifact"]["available"] is False


def test_research_plane_contract_marks_governed_candidate_activation_candidates():
    artifact = build_research_plane_artifact(
        autonomy_stage={
            "task_scan": {
                "tasks": [
                    {
                        "task_id": "governed_1",
                        "task_source": "bulk_stock_matrix",
                        "source_candidate_artifact_id": "candidate_alpha",
                    }
                ]
            },
            "task_results": [
                {
                    "task": {
                        "task_id": "governed_1",
                        "task_source": "bulk_stock_matrix",
                        "source_candidate_artifact_id": "candidate_alpha",
                    },
                    "status": "completed",
                    "generated_count": 1,
                    "evidence_count": 1,
                }
            ],
        },
        candidates=[
            {
                "name": "candidate_gamma",
                "strategy_type": "momentum",
                "research_task": {
                    "task_source": "bulk_stock_matrix",
                    "source_candidate_artifact_id": "candidate_alpha",
                },
                "params": {"generator_type": "external_llm"},
            }
        ],
    )

    assert artifact["candidate_artifact"]["candidate_origin_counts"] == {
        "governed_candidate_activation": 1
    }
    assert artifact["candidate_artifact"]["governed_candidate_activation_count"] == 1
    assert artifact["candidate_artifact"]["candidate_briefs"][0]["research_candidate_origin"] == (
        "governed_candidate_activation"
    )
    assert artifact["task_artifact"]["task_origin_counts"] == {
        "governed_candidate_activation": 1
    }
    assert artifact["task_artifact"]["governed_candidate_activation_task_count"] == 1
    assert artifact["evidence_artifact"]["task_origin_counts"] == {
        "governed_candidate_activation": 1
    }


def test_research_plane_contract_prefers_prebuilt_stage_artifacts():
    prebuilt_task_artifact = {
        "contract_version": TASK_ARTIFACT_CONTRACT_VERSION,
        "available": True,
        "planned_task_count": 7,
        "executed_task_count": 5,
        "task_source_counts": {"snapshot": 3, "bulk_stock_matrix": 4},
    }
    prebuilt_candidate_artifact = {
        "contract_version": CANDIDATE_ARTIFACT_CONTRACT_VERSION,
        "available": True,
        "candidate_count": 11,
        "generator_type_counts": {"external_llm": 11},
    }
    prebuilt_evidence_artifact = {
        "contract_version": RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
        "available": True,
        "task_evidence_count": 9,
        "experiment_count": 6,
        "external_llm_status": "partial",
    }

    artifact = build_research_plane_artifact(
        factor_research={
            "summary": {
                "factor_source_mode": "governed_candidate_pool",
                "active_factor_count": 2,
            }
        },
        readiness={
            "decision": "proceed",
            "readiness_score": 0.8,
            "can_proceed": True,
            "blocking_reason_codes": [],
        },
        autonomy_stage={
            "task_artifact": prebuilt_task_artifact,
            "candidate_artifact": prebuilt_candidate_artifact,
            "evidence_artifact": prebuilt_evidence_artifact,
            "task_scan": {"summary": {}, "tasks": []},
            "task_results": [],
        },
        candidates=[{"name": "candidate_should_not_replace_prebuilt"}],
        experiments=[{"experiment_id": "exp_should_not_replace_prebuilt"}],
    )

    assert artifact["task_artifact"] == prebuilt_task_artifact
    assert artifact["candidate_artifact"] == prebuilt_candidate_artifact
    assert artifact["evidence_artifact"] == prebuilt_evidence_artifact


def test_research_plane_contract_backfills_prebuilt_research_artifact_with_derived_fields():
    artifact = build_research_plane_artifact(
        factor_research={
            "summary": {
                "factor_source_mode": "governed_candidate_pool",
                "active_factor_count": 2,
                "family_preference_order": ["momentum", "quality_factor"],
                "family_preference_source_mode": "stock_family_allocation",
                "governed_candidate_pool_provisional_spillover_policy_status": "spillover_applied",
                "governed_candidate_pool_strict_shortfall_count": 2,
                "stock_family_allocation_count": 18,
                "stock_family_allocation_source_mode": "stock_universe_projection",
            },
            "research_artifact": {
                "contract_version": RESEARCH_ARTIFACT_CONTRACT_VERSION,
                "available": True,
                "active_factor_count": 1,
            },
            "source_chain": ["snapshot.factor_ic", "artifact_v2"],
        },
        readiness={
            "decision": "proceed",
            "readiness_score": 0.9,
            "can_proceed": True,
            "blocking_reason_codes": [],
        },
    )

    research_artifact = artifact["research_artifact"]
    assert research_artifact["available"] is True
    assert research_artifact["active_factor_count"] == 1
    assert research_artifact["family_preference_order"] == ["momentum", "quality_factor"]
    assert research_artifact["family_preference_source_mode"] == "stock_family_allocation"
    assert research_artifact["governed_candidate_pool_provisional_spillover_policy_status"] == "spillover_applied"
    assert research_artifact["governed_candidate_pool_strict_shortfall_count"] == 2
    assert research_artifact["stock_family_allocation_count"] == 18
    assert research_artifact["stock_family_allocation_source_mode"] == "stock_universe_projection"
    assert research_artifact["source_chain"] == ["snapshot.factor_ic", "artifact_v2"]
