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


def test_ranked_factor_context_preserves_five_active_pool_factors() -> None:
    from strategy_factory.application.research._research_build_steps import (
        build_ranked_factor_context,
    )
    from strategy_factory.application.research.factor_research_builder import (
        FactorResearchBuilder,
    )

    governed_candidates = [
        {"name": f"gp_factor_{idx}", "family": f"gp_factor_{idx}"}
        for idx in range(1, 6)
    ]

    context = build_ranked_factor_context(
        FactorResearchBuilder,
        factor_ic={},
        factor_trend={},
        names=[],
        history_meta={},
        governed_top_candidates=governed_candidates,
        snapshot={},
    )

    assert context["active_factors"] == [
        "gp_factor_1",
        "gp_factor_2",
        "gp_factor_3",
        "gp_factor_4",
        "gp_factor_5",
    ]
    assert context["top_factor_names"] == context["active_factors"]


def test_fresh_governed_pool_downgrades_history_stale_to_warning() -> None:
    from strategy_factory.application.research._research_artifact_payload import (
        build_factor_research_artifact_payload,
    )
    from strategy_factory.application.research.factor_research_builder import (
        FactorResearchBuilder,
    )

    payload = build_factor_research_artifact_payload(
        FactorResearchBuilder,
        snapshot={},
        snapshot_date=date(2026, 6, 9),
        latest_factor_date=date(2026, 6, 1),
        history_meta={},
        factor_ic_source={"status": "success"},
        factor_context={
            "ranked_factors": [],
            "positive_rising_factors": [],
            "active_factors": ["gp_factor_1", "gp_factor_2"],
            "preferred_strategy_types": ["momentum"],
            "top_factor_names": ["gp_factor_1", "gp_factor_2"],
        },
        runtime_context={
            "governed_pool": {
                "available": True,
                "active_pool": {"count": 2},
            },
            "active_candidate_pool": {"count": 2},
            "governed_candidate_pool_mode": "active_factor_pool_fallback",
            "governed_top_candidates": [
                {
                    "name": "gp_factor_1",
                    "family": "gp_factor_1",
                    "latest_validation_at": "2026-06-09T00:00:00+00:00",
                }
            ],
            "governed_source_candidate_count": 2,
            "governed_active_registry_candidate_count": 2,
            "governed_latest_candidate_at": "2026-06-09T00:00:00+00:00",
            "governed_freshness_days": 0,
            "scheduler_status": {},
            "scheduler_quality_flags": [],
            "scheduler_recent_success": False,
        },
        stock_family_allocation={},
        stock_family_allocation_summary={},
        lightweight_mock_fallback=False,
    )

    assert payload["history_stale"] is True
    assert payload["governed_pool_fresh"] is True
    assert payload["stale"] is False
    assert "factor_history_stale" in payload["quality_flags"]
    assert "stale" not in payload["quality_flags"]
    assert payload["summary"]["history_stale"] is True
    assert payload["summary"]["stale"] is False
