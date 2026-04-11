from strategy_factory.application._autonomy_task_result import (
    build_completed_task_result,
    build_external_request_metrics,
    build_failed_task_result,
    enrich_candidates_with_task_metrics,
)


def test_build_external_request_metrics_summarizes_request_counts_and_ratios():
    requests = [
        {"status": "succeeded"},
        {"status": "compatibility_skip"},
        {"status": "fallback", "network_request": True, "real_request": True},
    ]

    metrics = build_external_request_metrics(
        requests,
        summarize_request_status_counts=lambda items: {
            "succeeded": 1,
            "compatibility_skip": 1,
            "fallback": 1,
        },
        count_network_requests=lambda items: 3,
        count_real_requests=lambda items: 2,
        request_is_compatibility_failure=lambda item: False,
        request_is_empty_200_response=lambda item: False,
        normalize_request_status=lambda status: str(status or "").strip().lower(),
    )

    assert metrics["attempt_count"] == 3
    assert metrics["network_request_count"] == 3
    assert metrics["real_request_count"] == 2
    assert metrics["compatibility_skip_count"] == 1
    assert metrics["cooldown_skip_count"] == 0
    assert metrics["compatibility_failure_count"] == 0
    assert metrics["effective_response_count"] == 1
    assert metrics["effective_response_ratio"] == 0.5
    assert metrics["request_status_counts"] == {
        "succeeded": 1,
        "compatibility_skip": 1,
        "fallback": 1,
    }


def test_build_completed_and_failed_task_result_preserve_task_metadata():
    completed = build_completed_task_result(
        enriched_task={"task_source": "snapshot", "event_id": "event_1", "theme_code": "infra"},
        task_run_id="task_run_1",
        evidence_count=2,
        generated_count=4,
        reviewed_count=3,
        external_status="fallback_only",
        llm_generation={"provider": "stub"},
        lifecycle={"state": "completed"},
        lifecycle_summary={"completed_phase_count": 5},
        request_metrics={
            "attempt_count": 3,
            "network_request_count": 3,
            "real_request_count": 2,
            "compatibility_skip_count": 1,
            "cooldown_skip_count": 0,
            "compatibility_failure_count": 0,
            "effective_response_count": 1,
            "empty_200_response_count": 0,
            "compatibility_failure_ratio": 0.0,
            "effective_response_ratio": 0.5,
            "request_status_counts": {"fallback": 1},
        },
    )
    failed = build_failed_task_result(
        enriched_task={"task_source": "snapshot", "event_id": "event_1", "theme_code": "infra"},
        task_run_id="task_run_2",
        evidence_count=1,
        error="boom",
        lifecycle={"state": "failed"},
        lifecycle_summary={"failed_phase": "generating"},
    )

    assert completed["status"] == "completed"
    assert completed["generated_count"] == 4
    assert completed["external_llm_effective_response_ratio"] == 0.5
    assert completed["external_llm_request_status_counts"] == {"fallback": 1}
    assert failed["status"] == "failed"
    assert failed["generated_count"] == 0
    assert failed["error"] == "boom"
    assert failed["task_run_id"] == "task_run_2"


def test_enrich_candidates_with_task_metrics_writes_task_level_params():
    candidates = [
        {"name": "candidate_a", "params": {"existing": 1}},
        {"name": "candidate_b"},
    ]

    enriched = enrich_candidates_with_task_metrics(
        candidates,
        enriched_task={"task_id": "task_1"},
        enrich_candidate_targeting=lambda candidate, task: {**candidate, "task_id": task.get("task_id")},
        request_metrics={
            "attempt_count": 2,
            "network_request_count": 3,
            "real_request_count": 2,
            "compatibility_skip_count": 1,
            "cooldown_skip_count": 0,
            "compatibility_failure_count": 0,
            "effective_response_count": 1,
            "empty_200_response_count": 0,
            "compatibility_failure_ratio": 0.0,
            "effective_response_ratio": 0.5,
        },
        selected_count=4,
    )

    assert enriched[0]["task_id"] == "task_1"
    assert enriched[0]["params"]["existing"] == 1
    assert enriched[0]["params"]["task_stage_attempt_count"] == 2
    assert enriched[0]["params"]["task_real_request_count"] == 2
    assert enriched[0]["params"]["task_effective_response_ratio"] == 0.5
    assert enriched[1]["params"]["task_selected_count"] == 4
