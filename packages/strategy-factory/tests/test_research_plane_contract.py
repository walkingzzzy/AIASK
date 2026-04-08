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
            "governed_candidate_pool_mode": "strict_governed",
            "governed_candidate_pool_provisional": False,
            "stock_family_allocation_count": 8,
            "factor_llm_provider_health_status": "healthy",
            "factor_llm_provider_ready": True,
        },
        "source_chain": ["snapshot.factor_ic", "factor_scheduler.status"],
        "lifecycle_feedback_input": {
            "contract_version": "strategy_factory.lifecycle_feedback_input.v1",
            "available": True,
        },
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
            "experiment_id": "exp_alpha",
            "candidate_contract_snapshot": {"targeting": {"target_pool_id": "explicit:600519"}},
            "research_task": {"task_source": "snapshot", "candidate_family": "momentum"},
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
    assert artifact["research_artifact"]["lifecycle_feedback_input_contract_version"] == "strategy_factory.lifecycle_feedback_input.v1"
    assert artifact["research_artifact"]["lifecycle_feedback_input_available"] is True
    assert artifact["task_artifact"]["planned_task_count"] == 2
    assert artifact["task_artifact"]["task_source_counts"] == {"snapshot": 1, "event_driven": 1}
    assert artifact["candidate_artifact"]["candidate_count"] == 2
    assert artifact["candidate_artifact"]["generator_type_counts"] == {"rule": 1, "external_llm": 1}
    assert artifact["candidate_artifact"]["family_counts"] == {"momentum": 1, "value_factor": 1}
    assert artifact["evidence_artifact"]["task_evidence_count"] == 3
    assert artifact["evidence_artifact"]["experiment_count"] == 2
    assert artifact["evidence_artifact"]["external_llm_status"] == "succeeded"


def test_research_plane_contract_exposes_lifecycle_feedback_summary_counts():
    artifact = build_research_plane_artifact(
        factor_research={
            "summary": {
                "factor_source_mode": "governed_candidate_pool",
                "budget_feedback_family_count": 3,
                "budget_feedback_strategy_count": 12,
                "budget_feedback_target_pool_scope_count": 2,
                "budget_feedback_generator_mode_scope_count": 1,
                "budget_feedback_runtime_alert_count": 4,
                "budget_feedback_runtime_risk_event_count": 5,
                "budget_feedback_promotion_review_count": 2,
                "budget_feedback_promotion_review_status_counts": {"watch": 1, "approved": 1},
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
    assert research_artifact["lifecycle_feedback_generator_mode_scope_count"] == 1
    assert research_artifact["lifecycle_feedback_runtime_alert_count"] == 4
    assert research_artifact["lifecycle_feedback_runtime_risk_event_count"] == 5
    assert research_artifact["lifecycle_feedback_promotion_review_count"] == 2
    assert research_artifact["lifecycle_feedback_promotion_review_status_counts"] == {
        "watch": 1,
        "approved": 1,
    }


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
    assert artifact["research_artifact"]["readiness_reference"]["decision"] == "blocked"
    assert artifact["research_artifact"]["readiness_reference"]["can_proceed"] is False


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
