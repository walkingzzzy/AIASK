from strategy_factory.application._bulk_planner_summary import (
    build_bulk_planner_error_report,
    build_default_bulk_report,
    normalize_bulk_report_summary,
)


def test_build_default_bulk_report_uses_cursor_and_window_defaults():
    bulk_window_state = {
        "configured_enabled": True,
        "run_window_active": False,
        "run_window": "off_hours",
        "current_period": "market_hours",
        "skip_reason": "outside_run_window",
    }
    bulk_cursor = {
        "source": "persisted_run",
        "resume_from_run_id": "factory_run_hist_1",
        "cursor_mode": "task_offset",
        "next_universe_offset": 500,
        "next_task_offset": 20,
        "planned_task_count": 7,
    }

    report = build_default_bulk_report(bulk_window_state, bulk_cursor)
    summary = report["summary"]

    assert report["tasks"] == []
    assert summary["enabled"] is False
    assert summary["configured_enabled"] is True
    assert summary["requested_universe_offset"] == 500
    assert summary["requested_task_offset"] == 20
    assert summary["planned_task_count"] == 7
    assert summary["cursor_source"] == "persisted_run"
    assert summary["cursor_resume_from_run_id"] == "factory_run_hist_1"
    assert summary["run_window"] == "off_hours"
    assert summary["run_window_current_period"] == "market_hours"
    assert summary["skip_reason"] == "outside_run_window"


def test_build_bulk_planner_error_report_marks_planner_error():
    report = build_bulk_planner_error_report(
        {"configured_enabled": True, "run_window_active": True, "run_window": "always", "current_period": "off_hours"},
        {"source": "default", "cursor_mode": "task_offset", "next_universe_offset": 0, "next_task_offset": 0},
        RuntimeError("planner exploded"),
    )

    assert report["summary"]["enabled"] is False
    assert report["summary"]["skip_reason"] == "planner_error"
    assert report["summary"]["error"] == "planner exploded"


def test_normalize_bulk_report_summary_preserves_existing_values_and_fills_missing_defaults():
    bulk_window_state = {
        "configured_enabled": True,
        "run_window_active": True,
        "run_window": "always",
        "current_period": "off_hours",
        "skip_reason": None,
    }
    bulk_cursor = {
        "source": "persisted_run",
        "resume_from_run_id": "factory_run_hist_2",
        "cursor_mode": "task_offset",
        "next_universe_offset": 1000,
        "next_task_offset": 40,
        "planned_task_count": 12,
    }
    report = normalize_bulk_report_summary(
        {
            "summary": {
                "enabled": True,
                "stock_count": 33,
                "next_task_offset": 60,
                "selected_shard_ids": ["s1"],
            },
            "tasks": [{"task_id": "bulk_1"}],
        },
        bulk_window_state,
        bulk_cursor,
    )
    summary = report["summary"]

    assert report["tasks"] == [{"task_id": "bulk_1"}]
    assert summary["enabled"] is True
    assert summary["stock_count"] == 33
    assert summary["next_task_offset"] == 60
    assert summary["requested_universe_offset"] == 1000
    assert summary["requested_task_offset"] == 40
    assert summary["planned_task_count"] == 12
    assert summary["cursor_source"] == "persisted_run"
    assert summary["cursor_resume_from_run_id"] == "factory_run_hist_2"
    assert summary["selected_shard_ids"] == ["s1"]
