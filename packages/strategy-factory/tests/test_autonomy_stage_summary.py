from strategy_factory.application._autonomy_stage_summary import (
    build_autonomy_stage_summary,
    resolve_autonomy_overall_status,
)


def test_resolve_autonomy_overall_status_reports_partial_when_completed_and_failed_mix():
    status, completed_count, failed_count = resolve_autonomy_overall_status(
        [
            {"status": "completed"},
            {"status": "failed"},
        ],
        {"succeeded": 1, "failed": 1},
    )

    assert status == "partial"
    assert completed_count == 1
    assert failed_count == 1


def test_resolve_autonomy_overall_status_treats_completed_tasks_with_local_output_as_success():
    status, completed_count, failed_count = resolve_autonomy_overall_status(
        [
            {"status": "completed"},
            {"status": "completed"},
        ],
        {"failed": 2},
        generated_candidate_count=2,
    )

    assert status == "succeeded"
    assert completed_count == 2
    assert failed_count == 0


def test_build_autonomy_stage_summary_keeps_external_llm_and_feedback_fields():
    stage = build_autonomy_stage_summary(
        task_results=[
            {"status": "completed", "task_run_id": "task_run_1"},
            {"status": "completed", "task_run_id": None},
        ],
        task_source_counts={"snapshot": 1, "bulk_stock_matrix": 1},
        event_task_count=0,
        bulk_report={
            "summary": {
                "eligible_stock_count": 20,
                "loaded_stock_count": 18,
                "pages_loaded": 2,
                "analysis_complete": True,
                "requested_task_offset": 40,
                "next_task_offset": 60,
                "cursor_source": "persisted_run",
                "selected_shard_count": 2,
                "selected_shard_ids": ["a", "b"],
            }
        },
        bulk_cursor={"source": "persisted_run", "resume_from_run_id": "factory_run_hist_3"},
        generated_candidates=[{"name": "c1"}, {"name": "c2"}],
        all_experiments=[{"id": "exp_1"}],
        external_status_counts={"succeeded": 2},
        total_attempt_count=3,
        total_network_request_count=3,
        total_real_request_count=2,
        total_compatibility_skip_count=1,
        total_cooldown_skip_count=0,
        total_compatibility_failure_count=0,
        total_effective_response_count=1,
        total_empty_200_response_count=0,
        total_request_status_counts={"succeeded": 1, "compatibility_skip": 1},
        total_selected_count=2,
        total_evidence_count=4,
        last_error_type=None,
        last_error=None,
        elapsed_seconds=1.2345,
        external_provider_health={"health_status": "healthy"},
        effective_research_concurrency=4,
        has_bulk_tasks=True,
        effective_bulk_research_concurrency=2,
        bulk_tasks_use_external_llm=True,
        research_task_timeout_sec=180.0,
        task_budget_meta={
            "max_research_tasks": 16,
            "max_bulk_research_tasks": 8,
            "combined_research_task_budget": 24,
            "selected_scan_task_count": 1,
            "selected_bulk_task_count": 1,
            "planned_feedback_control_mode_counts": {"cooldown": 2},
            "planned_feedback_limited_task_count": 2,
            "planned_feedback_relaxed_task_count": 1,
            "blocked_feedback_task_count": 1,
        },
        selected_feedback_summary={
            "feedback_control_mode_counts": {"cooldown": 1, "normal": 1},
            "feedback_limited_task_count": 1,
            "feedback_relaxed_task_count": 1,
        },
        external_provider_control={
            "control_mode": "cooldown",
            "control_reasons": ["provider_cooldown"],
            "stage_attempt_count": 3,
        },
        generator_mode_controls={"external_llm": {"control_mode": "cooldown"}},
        shared_generation_context_preloaded=True,
        persistence_failures=[{"operation": "save_strategy_task_run"}],
        lifecycle_metrics={"lifecycle_phase_count": 3},
        combined_scan_report={"summary": {"task_count": 2}},
    )

    assert stage["external_llm_status"] == "succeeded"
    assert stage["completed_task_count"] == 2
    assert stage["failed_task_count"] == 0
    assert stage["external_llm_attempt_count"] == 3
    assert stage["external_llm_real_request_count"] == 2
    assert stage["external_llm_compatibility_skip_count"] == 1
    assert stage["external_llm_effective_response_ratio"] == 0.5
    assert stage["external_llm_request_status_counts"] == {"succeeded": 1, "compatibility_skip": 1}
    assert stage["bulk_stock_matrix_requested_task_offset"] == 40
    assert stage["bulk_stock_matrix_next_task_offset"] == 60
    assert stage["bulk_stock_matrix_cursor_source"] == "persisted_run"
    assert stage["bulk_stock_matrix_cursor_resume_from_run_id"] == "factory_run_hist_3"
    assert stage["bulk_stock_matrix_selected_shard_ids"] == ["a", "b"]
    assert stage["planned_feedback_control_mode_counts"] == {"cooldown": 2}
    assert stage["planned_feedback_limited_task_count"] == 2
    assert stage["planned_feedback_relaxed_task_count"] == 1
    assert stage["selected_feedback_control_mode_counts"] == {"cooldown": 1, "normal": 1}
    assert stage["selected_feedback_limited_task_count"] == 1
    assert stage["selected_feedback_relaxed_task_count"] == 1
    assert stage["persistence_failure_count"] == 1
    assert stage["shared_generation_context_preloaded"] is True
    assert stage["task_run_ids"] == ["task_run_1"]
    assert stage["lifecycle_phase_count"] == 3
