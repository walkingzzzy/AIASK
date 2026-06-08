from __future__ import annotations

from datetime import date


def test_active_factor_pool_fallback_uses_eligible_legacy_active_factors() -> None:
    from strategy_factory.application.research._research_build_steps import (
        apply_active_factor_pool_fallback,
    )
    from strategy_factory.application.research.factor_research_builder import (
        FactorResearchBuilder,
    )

    factors = [
        {
            "factor_id": "factor_legacy_active",
            "name": "legacy_active_alpha",
            "family": "momentum",
            "status": "active",
            "expression_dsl": "close / ma(close, 20) - 1",
            "admission_grade": "A",
            "fitness": 1.25,
            "last_evaluated_at": "2026-06-06T22:00:00+00:00",
            "validation_summary": {},
        },
        {
            "factor_id": "factor_quarantine",
            "name": "quarantine_alpha",
            "family": "momentum",
            "status": "quarantine",
            "expression_dsl": "close / ma(close, 10) - 1",
            "admission_grade": "A",
            "fitness": 99.0,
            "validation_summary": {"quality_status": "quarantine"},
        },
    ]
    eligible = [
        item
        for item in factors
        if FactorResearchBuilder._is_eligible_active_pool_factor(item)
    ]
    runtime_context = {
        "governed_top_candidates": [],
        "active_candidate_pool": {},
    }

    candidates = apply_active_factor_pool_fallback(
        FactorResearchBuilder,
        runtime_context,
        eligible,
        snapshot_date=date(2026, 6, 7),
    )

    assert [item["name"] for item in candidates] == ["legacy_active_alpha"]
    assert runtime_context["governed_candidate_pool_mode"] == "active_factor_pool_fallback"
    assert runtime_context["active_candidate_pool"]["count"] == 1
    assert runtime_context["governed_source_candidate_count"] == 1
    assert runtime_context["active_candidate_pool"]["top_candidates"][0]["pool_entry_mode"] == (
        "active_factor_pool_fallback"
    )
