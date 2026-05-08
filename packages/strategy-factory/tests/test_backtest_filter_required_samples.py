from __future__ import annotations

from strategy_factory.application import backtest_filter as backtest_filter_module


def test_target_only_snapshot_basket_caps_required_samples_to_target_count():
    candidate = {
        "tags": ["targeted_universe", "basket_candidate"],
        "target_symbols": ["688336", "688599"],
        "research_task": {
            "task_source": "snapshot",
            "validation_focus": "candidate_target_only",
            "target_symbols": ["688336", "688599"],
            "target_alignment_contract": {
                "min_target_sample_count": 1,
            },
        },
    }

    required = backtest_filter_module._resolve_required_sample_count(
        candidate,
        thresholds={"min_samples": 3},
        research_task=candidate["research_task"],
        validation_focus="candidate_target_only",
        target_codes=["688336", "688599"],
    )

    assert required == 2


def test_non_target_only_validation_keeps_default_required_samples():
    candidate = {
        "target_symbols": ["688336", "688599"],
        "research_task": {
            "task_source": "snapshot",
            "validation_focus": "broad_generalization",
            "target_symbols": ["688336", "688599"],
        },
    }

    required = backtest_filter_module._resolve_required_sample_count(
        candidate,
        thresholds={"min_samples": 3},
        research_task=candidate["research_task"],
        validation_focus="broad_generalization",
        target_codes=["688336", "688599"],
    )

    assert required == 3


def test_backtest_plan_uses_configured_representative_count_for_mixed_validation():
    candidate = {
        "target_symbols": ["688336", "688599"],
        "research_task": {
            "task_source": "snapshot",
            "validation_focus": "target_plus_representative",
            "target_symbols": ["688336", "688599"],
        },
    }

    evaluated_codes, target_codes, representative_codes, code_source, validation_focus = (
        backtest_filter_module.BacktestFilter._resolve_backtest_plan(candidate)
    )

    assert target_codes == ["688336", "688599"]
    assert validation_focus == "target_plus_representative"
    assert code_source == "candidate_target_plus_representative"
    assert len([code for code in evaluated_codes if code in representative_codes]) == 4
