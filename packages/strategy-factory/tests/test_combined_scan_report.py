from strategy_factory.application._combined_scan_report import build_combined_scan_report


def test_build_combined_scan_report_preserves_bulk_cursor_and_feedback_budget_fields():
    report = build_combined_scan_report(
        scan_summary={
            "event_task_count": 1,
            "task_sources": {"event_driven": 1},
            "scanner_signal": "ok",
        },
        tasks=[
            {"task_id": "event_1", "opportunity_type": "sector_breakout", "task_source": "event_driven"},
            {"task_id": "bulk_1", "opportunity_type": "momentum", "task_source": "bulk_stock_matrix"},
        ],
        task_source_counts={"event_driven": 1, "bulk_stock_matrix": 1},
        event_task_count=1,
        bulk_tasks=[{"task_id": "bulk_1", "task_source": "bulk_stock_matrix"}],
        bulk_report={
            "summary": {
                "enabled": True,
                "configured_enabled": True,
                "stock_count": 12,
                "eligible_stock_count": 20,
                "loaded_stock_count": 20,
                "pages_loaded": 1,
                "analysis_complete": True,
                "analysis_stock_coverage_ratio": 1.0,
                "run_window": "off_hours",
                "run_window_active": True,
                "run_window_current_period": "off_hours",
                "requested_task_offset": 40,
                "next_task_offset": 60,
                "cursor_source": "persisted_run",
                "cursor_resume_from_run_id": "factory_run_hist_2",
                "planned_task_count": 20,
                "selected_shard_count": 2,
                "selected_shard_ids": ["shard_a", "shard_b"],
                "allocation_mode": "factor_research_stock_family_allocation",
            }
        },
        bulk_cursor={"source": "persisted_run", "resume_from_run_id": "factory_run_hist_2"},
        task_budget_meta={
            "max_research_tasks": 16,
            "max_bulk_research_tasks": 8,
            "combined_research_task_budget": 24,
            "selected_scan_task_count": 1,
            "selected_bulk_task_count": 1,
            "planned_feedback_control_mode_counts": {"cooldown": 2, "normal": 1},
            "planned_feedback_limited_task_count": 2,
            "planned_feedback_relaxed_task_count": 1,
            "selected_feedback_control_mode_counts": {"cooldown": 1, "normal": 1},
            "selected_feedback_limited_task_count": 1,
            "selected_feedback_relaxed_task_count": 1,
            "blocked_feedback_task_count": 1,
            "suppressed_families": ["mean_reversion"],
        },
        external_provider_control={
            "control_mode": "cooldown",
            "control_reasons": ["provider_cooldown"],
        },
        generator_mode_controls={"external_llm": {"control_mode": "cooldown"}},
        opportunity_scan={"summary": {"task_count": 2}},
    )

    summary = report["summary"]

    assert summary["task_count"] == 2
    assert summary["task_types"] == {"sector_breakout": 1, "momentum": 1}
    assert summary["bulk_stock_task_count"] == 1
    assert summary["bulk_stock_matrix_run_window"] == "off_hours"
    assert summary["bulk_stock_matrix_run_window_active"] is True
    assert summary["bulk_stock_matrix_requested_task_offset"] == 40
    assert summary["bulk_stock_matrix_next_task_offset"] == 60
    assert summary["bulk_stock_matrix_cursor_source"] == "persisted_run"
    assert summary["bulk_stock_matrix_cursor_resume_from_run_id"] == "factory_run_hist_2"
    assert summary["bulk_stock_matrix_selected_shard_count"] == 2
    assert summary["bulk_stock_matrix_selected_shard_ids"] == ["shard_a", "shard_b"]
    assert summary["planned_feedback_control_mode_counts"] == {"cooldown": 2, "normal": 1}
    assert summary["planned_feedback_limited_task_count"] == 2
    assert summary["planned_feedback_relaxed_task_count"] == 1
    assert summary["selected_feedback_control_mode_counts"] == {"cooldown": 1, "normal": 1}
    assert summary["selected_feedback_limited_task_count"] == 1
    assert summary["selected_feedback_relaxed_task_count"] == 1
    assert summary["blocked_feedback_task_count"] == 1
    assert summary["suppressed_families"] == ["mean_reversion"]
    assert summary["external_llm_provider_control_mode"] == "cooldown"
    assert summary["external_llm_provider_control_reasons"] == ["provider_cooldown"]
    assert summary["generator_mode_controls"] == {"external_llm": {"control_mode": "cooldown"}}
    assert report["tasks"][0]["task_id"] == "event_1"
    assert report["opportunity_scan"]["summary"]["task_count"] == 2
