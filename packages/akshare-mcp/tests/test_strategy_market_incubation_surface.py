from __future__ import annotations

from akshare_mcp.tools.managers.strategy_mgr_crud import _build_strategy_incubation_surface


def test_incubation_surface_defaults_to_not_started_before_incubator():
    surface = _build_strategy_incubation_surface(
        {"id": "strategy-draft", "status": "draft"},
    )

    assert surface["pipeline_stage"] == "not_started"
    assert surface["entered_incubator"] is False
    assert surface["promotion_ready"] is False
    assert surface["latest_decision"] is None
    assert surface["blocker_count"] == 0
    assert surface["risk_count"] == 0


def test_incubation_surface_prefers_pipeline_snapshot_stage_over_overview_and_account():
    surface = _build_strategy_incubation_surface(
        {"id": "strategy-incubating", "status": "incubating"},
        latest_pipeline_snapshot={
            "pipeline_stage": "candidate",
            "latest_decision": "observe",
            "blockers": ["wait_more_days"],
            "risk_flags": ["drawdown_watch"],
        },
        overview={
            "pipeline_stage": "failed",
            "promotion_ready": True,
            "execution_audit_gate_status": "passed",
            "blockers": ["ignored_by_priority"],
            "risk_flags": [],
        },
        incubation_account={"stage": "warmup"},
    )

    assert surface["pipeline_stage"] == "candidate"
    assert surface["entered_incubator"] is True
    assert surface["promotion_ready"] is True
    assert surface["latest_decision"] == "observe"
    assert surface["execution_audit_gate_status"] == "passed"
    assert surface["blocker_count"] == 1
    assert surface["risk_count"] == 0


def test_incubation_surface_falls_back_to_promoted_for_listed_status():
    surface = _build_strategy_incubation_surface(
        {"id": "strategy-listed", "status": "listed"},
    )

    assert surface["pipeline_stage"] == "promoted"
    assert surface["entered_incubator"] is True
    assert surface["promotion_ready"] is True


def test_incubation_surface_uses_metric_decision_when_snapshot_decision_missing():
    surface = _build_strategy_incubation_surface(
        {"id": "strategy-suspended", "status": "suspended"},
        overview={
            "pipeline_stage": "failed",
            "promotion_ready": False,
            "execution_audit_gate_status": "failed",
            "risk_flags": ["hard_gate_failed", "runtime_halt"],
        },
        incubation_account={"stage": "candidate"},
        latest_metric={"decision": "halt"},
    )

    assert surface["pipeline_stage"] == "failed"
    assert surface["promotion_ready"] is False
    assert surface["latest_decision"] == "halt"
    assert surface["execution_audit_gate_status"] == "failed"
    assert surface["risk_count"] == 2
