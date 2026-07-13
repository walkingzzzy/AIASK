from __future__ import annotations

from aiask_quant_core.strategy_explanation import (
    EXPLANATION_VERSION,
    INCUBATION_EXPLANATION_VERSION,
    build_incubation_explanation,
    build_strategy_case_file,
    build_strategy_explanation,
    ensure_strategy_explanation,
    evaluate_strategy_explanation_completeness,
    explain_reason_code,
    render_strategy_description,
)


def test_build_strategy_explanation_summarizes_generated_strategy() -> None:
    candidate = {
        "name": "event breakout candidate",
        "description": "Breakout after theme event confirmation",
        "strategy_type": "event_structure_breakout",
        "target_symbols": ["600000", "000001"],
        "tags": ["pipeline_staged"],
        "generation_reason": {
            "source": "external_llm",
            "provider": "openai",
            "model": "test-model",
            "category": "event",
            "rationale": "Theme strength and volume contraction support a breakout setup.",
        },
        "research_task": {
            "task_id": "task-1",
            "theme": "AI infrastructure",
            "opportunity_type": "sector_breakout",
            "candidate_family": "event_breakout",
        },
        "trade_plan": {
            "entry_bias": "breakout_with_volume_confirmation",
            "exit_bias": "false_breakout_or_time_stop",
        },
        "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 12},
        "holding_horizon": {"min_days": 3, "max_days": 12},
    }

    explanation = build_strategy_explanation(
        candidate,
        metrics={"sharpe_ratio": 1.23, "total_return": 0.18, "max_drawdown": -0.06},
        source="unit_test",
    )

    assert explanation["version"] == EXPLANATION_VERSION
    assert explanation["summary"] == "Breakout after theme event confirmation"
    assert "strategy_explained" in explanation["labels"]
    assert "type:event_structure_breakout" in explanation["labels"]
    assert "family:event_breakout" in explanation["labels"]
    assert "source=external_llm" in explanation["why_generated"]
    assert "provider=openai" in explanation["why_generated"]
    assert explanation["target_scope"]["symbols"] == ["600000", "000001"]
    assert explanation["signal_logic"]["entry"] == "breakout_with_volume_confirmation"
    assert explanation["risk_notes"]["risk_rules"]["stop_loss_pct"] == 0.08
    assert explanation["evidence"]["metrics"]["sharpe_ratio"] == 1.23

    rendered = render_strategy_description("event breakout candidate", explanation)
    assert "Why:" in rendered
    assert "Targets: 600000, 000001" in rendered
    assert "Entry: breakout_with_volume_confirmation" in rendered


def test_ensure_strategy_explanation_marks_completeness() -> None:
    complete = ensure_strategy_explanation(
        {
            "name": "complete",
            "description": "complete thesis",
            "strategy_type": "momentum",
            "target_symbols": ["600519"],
            "generation_reason": {
                "source": "rule",
                "rationale": "Fear regime with quality factors.",
            },
            "trade_plan": {"entry_bias": "pullback", "exit_bias": "time_stop"},
        },
        source="unit_test",
    )
    assert complete["completeness"]["complete"] is True
    assert "explanation_complete" in complete["labels"]

    incomplete = ensure_strategy_explanation(
        {"name": "bare", "strategy_type": "momentum"},
        source="unit_test",
    )
    assert incomplete["completeness"]["complete"] is False
    assert "explanation_incomplete" in incomplete["labels"]
    missing = set(incomplete["completeness"]["missing_fields"])
    assert missing.intersection({"rationale_or_thesis", "signal_logic_entry_or_exit", "target_scope", "why_generated"})



def test_incubation_explanation_and_case_file() -> None:
    strategy = {
        "id": "s1",
        "name": "demo",
        "status": "incubating",
        "generation_reason": {
            "source": "rule",
            "rationale": "demo rationale for generation",
        },
        "description": "demo thesis",
        "trade_plan": {"entry_bias": "breakout", "exit_bias": "stop"},
        "target_symbols": ["000001"],
    }
    gen = ensure_strategy_explanation(strategy, source="unit_test")
    inc = build_incubation_explanation(
        strategy=strategy,
        overview={
            "pipeline_stage": "observe",
            "decision": "hold",
            "execution_audit_gate_status": "bootstrap_pending",
            "blockers": ["execution_audit_gate:bootstrap_pending"],
            "promotion_ready": False,
        },
        evidence_snapshot={
            "signals_total": 2,
            "orders_total": 1,
            "trades_total": 0,
            "open_positions": 1,
            "closed": 0,
        },
        source="unit_test",
    )
    assert inc["version"] == INCUBATION_EXPLANATION_VERSION
    assert inc["why_incubating"]
    assert inc["why_blocked"]
    assert inc["next_evidence_needed"]
    assert "bootstrap" in explain_reason_code("execution_audit_gate:bootstrap_pending").lower() or "样本" in explain_reason_code(
        "execution_audit_gate:bootstrap_pending"
    )

    case = build_strategy_case_file(
        strategy=strategy,
        strategy_explanation=gen,
        incubation_explanation=inc,
        source="unit_test",
    )
    assert case["why_generated"]
    assert case["why_incubating"]
    assert case["readable"]["completeness_zh"]


def test_evaluate_completeness_empty() -> None:
    report = evaluate_strategy_explanation_completeness({})
    assert report["complete"] is False
    assert report["quality"] == "empty"
