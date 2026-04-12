from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import strategy_factory.application.factor_research as factor_research_mod
from strategy_factory.application._budget_feedback import (
    LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION,
)
from strategy_factory.application.factor_research import FactorResearchBuilder
from strategy_factory.application.opportunity import MarketOpportunityScanner
from strategy_factory.domain.constants import preferred_strategy_types_for_factor
from strategy_factory.domain.spawner import StrategySpawner


def test_factor_research_family_plans_zero_budget_when_feedback_control_active():
    plans = FactorResearchBuilder._build_family_plans(
        ["momentum", "quality_factor"],
        priority=0.72,
        budget_feedback_root={
            "momentum": {
                "paper_hit_ratio": 0.16,
                "runtime_alert_pressure": 0.9,
                "realized_turnover": 1.5,
                "capacity_crowding": 1.18,
            },
            "quality_factor": {
                "paper_hit_ratio": 0.62,
                "runtime_alert_pressure": 0.08,
                "realized_turnover": 0.22,
                "capacity_crowding": 0.16,
            },
        },
    )

    by_family = {plan["family"]: plan for plan in plans}

    assert by_family["momentum"]["feedback_control_mode"] == "freeze"
    assert by_family["momentum"]["feedback_suppressed"] is True
    assert by_family["momentum"]["budget_weight"] == 0.0
    assert by_family["quality_factor"]["feedback_control_mode"] == "normal"
    assert by_family["quality_factor"]["budget_weight"] > 0.0


def test_factor_research_family_plans_keep_reduced_budget_for_relaxable_backlog_control():
    plans = FactorResearchBuilder._build_family_plans(
        ["momentum", "quality_factor"],
        priority=0.72,
        budget_feedback_root={
            "momentum": {
                "strategy_count": 8,
                "zero_signal_ratio": 1.0,
                "low_signal_ratio": 1.0,
                "forward_window_coverage_ratio": 0.0,
                "promotion_ready_ratio": 0.0,
                "promotion_review_coverage_ratio": 0.0,
                "evidence_debt_ratio": 1.0,
            },
            "quality_factor": {
                "paper_hit_ratio": 0.62,
                "runtime_alert_pressure": 0.08,
                "realized_turnover": 0.22,
                "capacity_crowding": 0.16,
            },
        },
    )

    by_family = {plan["family"]: plan for plan in plans}

    assert by_family["momentum"]["feedback_control_original_mode"] == "freeze"
    assert by_family["momentum"]["feedback_control_mode"] == "normal"
    assert by_family["momentum"]["feedback_control_relaxed_mode"] == "normal"
    assert by_family["momentum"]["feedback_control_relaxed"] is True
    assert by_family["momentum"]["budget_weight"] > 0.0
    assert by_family["quality_factor"]["budget_weight"] > by_family["momentum"]["budget_weight"]


def test_preferred_strategy_types_for_real_registry_families():
    assert preferred_strategy_types_for_factor("overextension_filter")[0] == "mean_reversion_short"
    assert preferred_strategy_types_for_factor("breakout_structure")[0] == "momentum"
    assert preferred_strategy_types_for_factor("volatility_response")[0] == "volatility_breakout"
    assert preferred_strategy_types_for_factor("intraday_overnight_bridge")[0] == "gap_fill"


@pytest.mark.asyncio
async def test_factor_research_uses_snapshot_date_for_freshness():
    db = MagicMock()

    async def _history_side_effect(factor_name, *_args, **_kwargs):
        if factor_name == "value":
            return [
                {"ic_date": "2026-03-19", "ic_value": 0.06},
                {"ic_date": "2026-03-18", "ic_value": 0.05},
            ]
        return []

    db.get_factor_ic_history = AsyncMock(side_effect=_history_side_effect)

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-03-19",
            "factor_ic": {"value": 0.05},
            "factor_ic_trend": {"value": "rising"},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    assert artifact["latest_factor_date"] == "2026-03-19"
    assert artifact["freshness_days"] == 0


@pytest.mark.asyncio
async def test_factor_research_prefers_governed_candidate_pool(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    async def _fake_quant_manager(*, action, code=None, **kwargs):
        del code
        assert action == "factor_candidate_registry"
        assert kwargs.get("kwargs", {}).get("op") == "active_pool"
        assert kwargs.get("kwargs", {}).get("market_codes_only") is True
        return {
            "success": True,
            "data": {
                "summary": {"count": 1},
                "active_pool": {
                    "count": 1,
                    "latest_active_candidate_updated_at": "2026-03-18T10:15:00+08:00",
                    "family_summary": [
                        {"family": "sentiment", "count": 1, "promote_count": 1, "review_count": 0, "avg_total_score": 81.0, "max_total_score": 81.0}
                    ],
                    "regime_summary": [{"regime": "trend", "count": 1}],
                    "top_candidates": [
                        {
                            "artifact_id": "candidate_001",
                            "name": "sentiment_breakout_factor",
                            "family": "sentiment",
                            "expected_regime": ["trend"],
                            "grade": "A",
                            "recommendation": "promote",
                            "registry_stage": "governed",
                            "total_score": 81.0,
                            "source_generation_artifact_id": "llm_episode_001",
                            "source_validation_artifact_id": "candidate_001",
                            "latest_validation_at": "2026-03-18T10:15:00+08:00",
                            "risk_audit": {
                                "overall_risk_level": "low",
                                "lookahead_available": True,
                                "multiple_testing_available": True,
                                "required_audits_complete": True,
                                "blocked": False,
                            },
                        }
                    ],
                },
            },
        }

    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: _fake_quant_manager)
    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-03-19",
            "factor_ic": {},
            "factor_ic_trend": {},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    assert artifact["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert artifact["active_candidate_pool"]["count"] == 1
    assert artifact["summary"]["governed_latest_candidate_at"] == "2026-03-18T10:15:00+08:00"
    assert artifact["summary"]["governed_freshness_days"] == 1
    assert artifact["summary"]["top_candidate_lineage"][0]["source_generation_artifact_id"] == "llm_episode_001"
    assert artifact["summary"]["top_candidate_lineage"][0]["expected_regime"] == ["trend"]
    assert artifact["summary"]["top_candidate_lineage"][0]["latest_validation_age_days"] == 1
    assert artifact["summary"]["top_candidate_lineage"][0]["evidence_status"]["required_audits_complete"] is True
    assert artifact["top_candidate_lineage"][0]["registry_stage"] == "governed"
    assert "sentiment" in artifact["active_factors"]
    assert "momentum" in artifact["preferred_strategy_types"]


@pytest.mark.asyncio
async def test_factor_research_accepts_provisional_governed_candidate_pool(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    async def _fake_quant_manager(*, action, code=None, **kwargs):
        del code, kwargs
        if action == "factor_candidate_registry":
            return {
                "success": True,
                "data": {
                    "summary": {"count": 1, "registry_stage_counts": {"validated": 1}},
                    "active_pool": {
                        "active_pool_mode": "provisional_validated_watch",
                        "count": 1,
                        "strict_count": 0,
                        "provisional_count": 1,
                        "source_count": 1,
                        "latest_active_candidate_updated_at": "2026-03-18T10:15:00+08:00",
                        "family_summary": [
                            {"family": "momentum", "count": 1, "promote_count": 0, "review_count": 0, "avg_total_score": 49.5, "max_total_score": 49.5}
                        ],
                        "regime_summary": [{"regime": "trend", "count": 1}],
                        "top_candidates": [
                            {
                                "artifact_id": "candidate_watch_001",
                                "name": "momentum_watch_factor",
                                "family": "momentum",
                                "expected_regime": ["trend"],
                                "grade": "C",
                                "recommendation": "watch",
                                "registry_stage": "validated",
                                "pool_entry_mode": "provisional_validated_watch",
                                "total_score": 49.5,
                                "source_generation_artifact_id": "llm_episode_watch_001",
                                "source_validation_artifact_id": "candidate_watch_001",
                                "latest_validation_at": "2026-03-18T10:15:00+08:00",
                                "risk_audit": {
                                    "overall_risk_level": "medium",
                                    "lookahead_available": True,
                                    "multiple_testing_available": True,
                                    "required_audits_complete": True,
                                    "blocked": False,
                                },
                            }
                        ],
                    },
                },
            }
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: _fake_quant_manager)
    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-03-19",
            "factor_ic": {},
            "factor_ic_trend": {},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    assert artifact["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert artifact["summary"]["governed_candidate_pool_mode"] == "provisional_validated_watch"
    assert artifact["summary"]["governed_candidate_pool_provisional"] is True
    assert artifact["summary"]["governed_candidate_pool_strict_count"] == 0
    assert artifact["summary"]["governed_candidate_pool_provisional_count"] == 1
    assert artifact["active_candidate_pool"]["active_pool_mode"] == "provisional_validated_watch"
    assert artifact["top_candidate_lineage"][0]["pool_entry_mode"] == "provisional_validated_watch"
    assert artifact["top_candidate_lineage"][0]["registry_stage"] == "validated"
    assert "governed_candidate_pool_provisional" in artifact["quality_flags"]
    assert "momentum" in artifact["active_factors"]


@pytest.mark.asyncio
async def test_factor_research_separates_blocked_pending_and_ineligible_governance_candidates(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_governed_candidate_pool",
        AsyncMock(
            return_value={
                "available": True,
                "summary": {
                    "count": 8,
                    "active_count": 1,
                    "blocked_active_count": 4,
                    "registry_stage_counts": {"governed": 1, "validated": 7},
                },
                "active_pool": {
                    "active_pool_mode": "strict_governed",
                    "count": 1,
                    "strict_count": 1,
                    "provisional_count": 0,
                    "source_count": 8,
                    "excluded_count": 7,
                    "blocked_excluded_count": 4,
                    "pending_excluded_count": 2,
                    "ineligible_excluded_count": 1,
                    "latest_active_candidate_updated_at": "2026-04-08T15:48:16+08:00",
                    "exclusion_reason_counts": {
                        "multiple_testing_risk_high": 4,
                        "registry_stage_validated": 2,
                        "recommendation_reject": 1,
                        "score_below_provisional_threshold": 1,
                    },
                    "blocked_exclusion_reason_counts": {
                        "multiple_testing_risk_high": 4,
                    },
                    "pending_exclusion_reason_counts": {
                        "registry_stage_validated": 2,
                    },
                    "ineligible_exclusion_reason_counts": {
                        "recommendation_reject": 1,
                        "score_below_provisional_threshold": 1,
                    },
                    "family_summary": [
                        {
                            "family": "volatility_conditioned_reversal",
                            "count": 1,
                            "promote_count": 0,
                            "review_count": 1,
                            "avg_total_score": 64.2,
                            "max_total_score": 64.2,
                        }
                    ],
                    "regime_summary": [{"regime": "trend", "count": 1}],
                    "top_candidates": [
                        {
                            "artifact_id": "candidate_governed_001",
                            "name": "ShockAbsorptionReversal",
                            "family": "volatility_conditioned_reversal",
                            "expected_regime": ["trend"],
                            "grade": "B",
                            "recommendation": "review",
                            "registry_stage": "governed",
                            "total_score": 64.2,
                            "source_validation_artifact_id": "candidate_governed_001",
                            "latest_validation_at": "2026-04-08T15:48:16+08:00",
                            "risk_audit": {
                                "overall_risk_level": "medium",
                                "lookahead_available": True,
                                "multiple_testing_available": True,
                                "required_audits_complete": True,
                                "blocked": False,
                            },
                        }
                    ],
                    "excluded_candidates": [
                        {
                            "artifact_id": "candidate_blocked_001",
                            "name": "BlockedCandidate",
                            "family": "range_participation",
                            "registry_stage": "validated",
                            "admission_blocked": True,
                            "latest_validation_at": "2026-04-08T15:48:20+08:00",
                            "risk_audit": {
                                "blocked": True,
                                "block_reasons": ["multiple_testing_risk_high"],
                            },
                        },
                        {
                            "artifact_id": "candidate_pending_001",
                            "name": "PendingCandidate",
                            "family": "price_structure",
                            "registry_stage": "validated",
                            "admission_blocked": False,
                            "latest_validation_at": "2026-04-08T15:48:22+08:00",
                            "risk_audit": {
                                "blocked": False,
                                "block_reasons": [],
                            },
                            "exclusion_bucket": "pending",
                        },
                        {
                            "artifact_id": "candidate_ineligible_001",
                            "name": "RejectCandidate",
                            "family": "trend_quality",
                            "registry_stage": "validated",
                            "recommendation": "reject",
                            "latest_validation_at": "2026-04-08T15:48:25+08:00",
                            "risk_audit": {
                                "blocked": False,
                                "block_reasons": [],
                            },
                            "exclusion_bucket": "ineligible",
                        },
                    ],
                },
            }
        ),
    )
    monkeypatch.setattr(FactorResearchBuilder, "_load_model_registry_lineage", AsyncMock(return_value={"available": False}))
    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_budget_feedback",
        AsyncMock(
            return_value={
                "available": False,
                "reason": "feedback_unavailable",
                "feedback": {},
                "summary": {},
            }
        ),
    )
    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_stock_family_allocation",
        AsyncMock(return_value={"available": False, "reason": "empty_stock_allocation", "allocation": {}, "summary": {}}),
    )
    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-04-08",
            "factor_ic": {},
            "factor_ic_trend": {},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    assert artifact["summary"]["governed_source_candidate_count"] == 8
    assert artifact["summary"]["governed_active_registry_candidate_count"] == 1
    assert artifact["summary"]["governed_blocked_candidate_count"] == 4
    assert artifact["summary"]["governed_pending_candidate_count"] == 2
    assert artifact["summary"]["governed_ineligible_candidate_count"] == 1
    assert artifact["summary"]["governed_blocked_ratio"] == pytest.approx(0.5)
    assert artifact["summary"]["governed_pending_ratio"] == pytest.approx(0.25)
    assert artifact["summary"]["governed_ineligible_ratio"] == pytest.approx(0.125)
    assert artifact["summary"]["governed_blocking_reason_counts"] == {"multiple_testing_risk_high": 4}
    assert artifact["summary"]["governed_pending_reason_counts"] == {"registry_stage_validated": 2}
    assert artifact["summary"]["governed_ineligible_reason_counts"] == {
        "recommendation_reject": 1,
        "score_below_provisional_threshold": 1,
    }
    assert "governed_candidate_pool_blocked_ratio_elevated" in artifact["quality_flags"]
    assert "governed_candidate_pool_blocked_ratio_high" not in artifact["quality_flags"]


@pytest.mark.asyncio
async def test_factor_research_enriches_top_candidate_lineage_with_model_registry(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    async def _fake_quant_manager(*, action, code=None, **kwargs):
        del code
        params = kwargs.get("kwargs", {})
        if action == "factor_candidate_registry":
            return {
                "success": True,
                "data": {
                    "summary": {"count": 1, "governed_active_count": 1},
                    "active_pool": {
                        "count": 1,
                        "top_candidates": [
                            {
                                "artifact_id": "candidate_lineage_001",
                                "name": "lineage_sentiment_factor",
                                "family": "sentiment",
                                "registry_stage": "governed",
                                "source_generation_artifact_id": "llm_episode_lineage_001",
                                "source_validation_artifact_id": "candidate_lineage_001",
                                "latest_validation_at": "2026-03-20T08:30:00+08:00",
                            }
                        ],
                    },
                },
            }
        if action == "model_registry" and params.get("op") == "lineage":
            return {
                "success": True,
                "data": {
                    "summary": {"champion_count": 1, "challenger_count": 0, "retrain_plan_count": 1},
                    "items": [
                        {
                            "validation_artifact_id": "candidate_lineage_001",
                            "deployment_stages": ["champion"],
                            "model_registry_items": [
                                {"artifact_id": "model_registry_candidate_lineage_001", "deployment_stage": "champion"}
                            ],
                            "retrain_statuses": ["planned"],
                            "retrain_plans": [{"artifact_id": "retrain_plan_lineage_001", "status": "planned"}],
                            "latest_retrain_run": {"artifact_id": "retrain_run_lineage_001", "status": "partial"},
                        }
                    ],
                },
            }
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: _fake_quant_manager)
    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-03-20",
            "factor_ic": {},
            "factor_ic_trend": {},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    top_lineage = artifact["top_candidate_lineage"][0]
    assert top_lineage["model_registry_artifact_ids"] == ["model_registry_candidate_lineage_001"]
    assert top_lineage["model_registry_stages"] == ["champion"]
    assert top_lineage["retrain_plan_statuses"] == ["planned"]
    assert top_lineage["latest_retrain_run_status"] == "partial"
    assert top_lineage["latest_validation_age_days"] == 0
    assert top_lineage["evidence_status"]["required_audits_complete"] is False
    assert artifact["summary"]["model_registry_lineage_available"] is True
    assert artifact["summary"]["model_registry_lineage_summary"]["champion_count"] == 1
    assert "model_registry_lineage_available" in artifact["quality_flags"]


@pytest.mark.asyncio
async def test_factor_research_builds_stock_family_allocation(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])
    db.list_stock_universe = AsyncMock(
        return_value=[
            {
                "code": "300001",
                "name": "算力成长A",
                "industry": "算力",
                "sector": "算力",
                "market_cap": 120_000_000_000,
                "pe_ratio": 42,
                "pb_ratio": 4.2,
            },
            {
                "code": "600001",
                "name": "银行价值A",
                "industry": "银行",
                "sector": "银行",
                "market_cap": 88_000_000_000,
                "pe_ratio": 8.5,
                "pb_ratio": 0.9,
            },
        ]
    )

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())
    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: None)
    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_governed_candidate_pool",
        AsyncMock(
            return_value={
                "available": True,
                "active_pool": {
                    "count": 1,
                    "top_candidates": [
                        {
                            "artifact_id": "cand_stock_1",
                            "name": "sentiment_breakout_factor",
                            "family": "sentiment",
                            "codes": ["300001"],
                            "registry_stage": "governed",
                            "total_score": 86.0,
                            "latest_validation_at": "2026-04-01T09:30:00+08:00",
                        }
                    ],
                },
            }
        ),
    )

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-04-02",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_ic": {"growth": 0.05, "value": 0.03},
            "factor_ic_trend": {"growth": "rising", "value": "rising"},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    allocation = dict(artifact["stock_family_allocation"])
    assert set(allocation) == {"300001", "600001"}
    assert allocation["300001"]["families"][0] == "momentum"
    assert "value_factor" in allocation["600001"]["families"]
    assert allocation["300001"]["top_family"] == "momentum"
    assert allocation["300001"]["top_validation_profile"] == "trade_rule_validation"
    assert allocation["300001"]["family_plans"][0]["family"] == "momentum"
    assert allocation["300001"]["family_plans"][0]["family_rank"] == 1
    assert allocation["300001"]["family_plans"][0]["budget_weight"] > 0.0
    assert allocation["300001"]["family_plans"][0]["failure_penalty"] > 0.0
    assert allocation["300001"]["family_plans"][0]["validation_profile"]["profile"] == "trade_rule_validation"
    assert allocation["300001"]["family_plans"][0]["validation_profile"]["validation_focus"] == "candidate_target_only"
    assert any(
        plan["validation_profile"]["profile"] == "factor_rank_validation"
        for plan in allocation["600001"]["family_plans"]
    )
    assert sum(plan["budget_weight"] for plan in allocation["300001"]["family_plans"]) == pytest.approx(1.0)
    assert allocation["300001"]["priority"] > allocation["600001"]["priority"]
    assert artifact["summary"]["stock_family_allocation_count"] == 2
    assert artifact["summary"]["stock_family_allocation_source_mode"] == "stock_universe_projection"
    assert artifact["summary"]["stock_family_allocation_entropy"] > 0.0
    assert artifact["summary"]["family_preference_source_mode"] in {
        "stock_family_allocation",
        "feedback_router",
    }
    assert artifact["summary"]["family_preference_order"][0] == "momentum"
    assert "growth_factor" in artifact["summary"]["family_preference_order"][:3]
    assert artifact["family_preference_order"][0] == "momentum"


@pytest.mark.asyncio
async def test_factor_research_quality_family_plan_uses_trade_rule_validation_for_target_only(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])
    db.list_stock_universe = AsyncMock(
        return_value=[
            {
                "code": "600519",
                "name": "白酒龙头",
                "industry": "消费",
                "sector": "消费",
                "market_cap": 180_000_000_000,
                "pe_ratio": 28,
                "pb_ratio": 8.0,
            }
        ]
    )

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())
    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: None)
    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_governed_candidate_pool",
        AsyncMock(
            return_value={
                "available": True,
                "active_pool": {
                    "count": 1,
                    "top_candidates": [
                        {
                            "artifact_id": "cand_quality_1",
                            "name": "quality_family_candidate",
                            "family": "quality_factor",
                            "codes": ["600519"],
                            "registry_stage": "governed",
                            "total_score": 82.0,
                            "latest_validation_at": "2026-04-01T09:30:00+08:00",
                        }
                    ],
                },
            }
        ),
    )
    monkeypatch.setattr(FactorResearchBuilder, "_load_budget_feedback", AsyncMock(return_value={}))

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-04-02",
            "fear_greed_index": 52,
            "fg_level": "neutral",
            "hot_sectors": ["消费"],
            "cold_sectors": [],
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    plan = artifact["stock_family_allocation"]["600519"]["family_plans"][0]
    assert plan["family"] == "quality_factor"
    assert plan["validation_profile"]["profile"] == "trade_rule_validation"
    assert plan["validation_profile"]["validation_focus"] == "candidate_target_only"


@pytest.mark.asyncio
async def test_factor_research_builds_stock_family_allocation_from_real_registry_families_without_codes(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])
    db.list_stock_universe = AsyncMock(
        return_value=[
            {
                "code": "300001",
                "name": "算力成长A",
                "industry": "算力",
                "sector": "算力",
                "market_cap": 120_000_000_000,
                "pe_ratio": 42,
                "pb_ratio": 4.2,
            },
            {
                "code": "600001",
                "name": "银行价值A",
                "industry": "银行",
                "sector": "银行",
                "market_cap": 88_000_000_000,
                "pe_ratio": 8.5,
                "pb_ratio": 0.9,
            },
        ]
    )

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())
    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: None)
    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_governed_candidate_pool",
        AsyncMock(
            return_value={
                "available": True,
                "active_pool": {
                    "count": 2,
                    "strict_count": 1,
                    "provisional_count": 1,
                    "provisional_spillover_count": 1,
                    "provisional_spillover_policy": {
                        "status": "spillover_applied",
                        "decision": "spillover_applied",
                        "strict_shortfall_count": 5,
                        "pending_provisional_count": 0,
                        "pending_reason_code": None,
                    },
                    "top_candidates": [
                        {
                            "artifact_id": "cand_stock_real_1",
                            "name": "CrowdedMoveExhaustionFilter",
                            "family": "overextension_filter",
                            "registry_stage": "governed",
                            "recommendation": "review",
                            "total_score": 65.0,
                            "latest_validation_at": "2026-04-01T09:30:00+08:00",
                        },
                        {
                            "artifact_id": "cand_stock_real_2",
                            "name": "RangeEscapePersistence",
                            "family": "breakout_structure",
                            "registry_stage": "validated",
                            "recommendation": "watch",
                            "total_score": 50.0,
                            "latest_validation_at": "2026-04-01T09:31:00+08:00",
                        },
                    ],
                },
            }
        ),
    )
    monkeypatch.setattr(
        FactorResearchBuilder,
        "_load_budget_feedback",
        AsyncMock(
            return_value={
                "available": True,
                "feedback": {
                    "momentum": {
                        "strategy_count": 8,
                        "zero_signal_ratio": 1.0,
                        "low_signal_ratio": 1.0,
                        "forward_window_coverage_ratio": 0.0,
                        "promotion_ready_ratio": 0.0,
                        "promotion_review_coverage_ratio": 0.0,
                        "evidence_debt_ratio": 1.0,
                    }
                },
                "summary": {"family_count": 1, "strategy_count": 8},
            }
        ),
    )

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-04-02",
            "fear_greed_index": 68,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_ic": {"growth": 0.05, "value": 0.03},
            "factor_ic_trend": {"growth": "rising", "value": "rising"},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    allocation = dict(artifact["stock_family_allocation"])
    assert allocation
    assert artifact["summary"]["stock_family_allocation_count"] == 2
    assert artifact["summary"]["governed_candidate_pool_provisional_spillover_policy_status"] == "spillover_applied"
    assert artifact["summary"]["governed_candidate_pool_strict_shortfall_count"] == 5
    assert artifact["summary"]["governed_candidate_pool_provisional_pending_count"] == 0
    assert "mean_reversion_short" in allocation["600001"]["families"] or "momentum" in allocation["300001"]["families"]
    assert any(
        str(plan.get("feedback_control_mode") or "").strip().lower() == "normal"
        and bool(plan.get("feedback_control_relaxed"))
        for plan in allocation["300001"]["family_plans"]
    )
    assert artifact["summary"]["family_preference_source_mode"] in {
        "stock_family_allocation",
        "feedback_router",
    }
    assert artifact["summary"]["family_preference_order"][0] in {"momentum", "mean_reversion_short"}


@pytest.mark.asyncio
async def test_factor_research_surfaces_scheduler_provider_health(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])

    class _Scheduler:
        def status(self):
            return {
                "running": False,
                "quality_flags": [],
                "last_run": "2026-04-05T09:30:00+08:00",
                "freshness_sec": 60,
                "last_result": {
                    "llm_validation": {"status": "partial"},
                },
                "llm_provider": {
                    "enabled": True,
                    "ready": False,
                    "health_status": "degraded",
                    "rebuild_count": 2,
                    "last_error_type": "ReadTimeout",
                },
            }

    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: None)
    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-04-05",
            "factor_ic": {"value": 0.06},
            "factor_ic_trend": {"value": "rising"},
            "sources": {"factor_ic": {"status": "success"}},
        },
    )

    assert artifact["summary"]["factor_llm_provider_enabled"] is True
    assert artifact["summary"]["factor_llm_provider_ready"] is False
    assert artifact["summary"]["factor_llm_provider_health_status"] == "degraded"
    assert artifact["summary"]["factor_llm_provider_rebuild_count"] == 2
    assert artifact["summary"]["factor_llm_provider_last_error_type"] == "ReadTimeout"
    assert "factor_llm_provider_degraded" in artifact["quality_flags"]


@pytest.mark.asyncio
async def test_factor_research_publishes_lifecycle_feedback_input_contract(monkeypatch):
    db = MagicMock()
    db.get_factor_ic_history = AsyncMock(return_value=[])
    db.list_strategies = AsyncMock(
        side_effect=lambda status, limit: (
            [
                {
                    "id": "strategy_feedback_001",
                    "candidate_family": "momentum",
                    "target_pool_id": "theme:ai",
                    "holding_period_bucket": "short",
                    "generator_mode": "external_llm",
                }
            ]
            if status == "incubating"
            else []
        )
    )
    db.list_strategy_incubation_metrics = AsyncMock(
        return_value=[
            {
                "hit_rate_5d": 0.72,
                "turnover_rate": 0.18,
                "exposure_rate": 0.12,
            }
        ]
    )
    db.list_strategy_runtime_risk_events = AsyncMock(
        return_value=[{"status": "open", "severity": "medium", "reason": "crowding"}]
    )
    db.list_strategy_runtime_alerts = AsyncMock(
        return_value=[{"status": "open", "severity": "low", "alert_key": "turnover_spike"}]
    )
    db.get_latest_strategy_promotion_review = AsyncMock(
        return_value={
            "status": "watch",
            "recommendation": "observe",
            "score": 0.34,
        }
    )

    class _Scheduler:
        def status(self):
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0, "last_result": {}}

    monkeypatch.setattr(factor_research_mod, "get_quant_manager_callable", lambda: None)
    monkeypatch.setattr(factor_research_mod, "get_factor_scheduler_singleton", lambda: _Scheduler())
    monkeypatch.setattr(
        factor_research_mod,
        "get_strategy_lifecycle_shared_runtime",
        lambda: SimpleNamespace(
            build_incubation_overview=AsyncMock(
                return_value={
                    "total_signals": 0,
                    "minimum_signal_count": 10,
                    "observed_forward_days": [],
                    "missing_forward_days": [1, 5, 10, 20],
                    "promotion_ready": False,
                }
            )
        ),
    )

    artifact = await FactorResearchBuilder.build(
        db,
        {
            "date": "2026-04-05",
            "factor_ic": {"value": 0.06},
            "factor_ic_trend": {"value": "rising"},
            "sources": {"factor_ic": {"status": "success"}},
            "family_gate_feedback": {
                "momentum": {
                    "ema_submit_count": 3.4,
                    "target_pool_feedback": {
                        "theme:ai": {"ema_submit_count": 1.2}
                    },
                    "holding_bucket_feedback": {
                        "short": {"ema_submit_count": 1.1}
                    },
                    "generator_mode_feedback": {
                        "external_llm": {"ema_submit_count": 1.0}
                    },
                }
            },
        },
    )

    feedback_contract = dict(artifact.get("lifecycle_feedback_input") or {})
    feedback_root = dict(feedback_contract.get("feedback") or {})
    momentum_feedback = dict(feedback_root.get("momentum") or {})

    assert feedback_contract["contract_version"] == LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION
    assert feedback_contract["available"] is True
    assert feedback_contract["summary"]["family_count"] == 1
    assert feedback_contract["summary"]["seeded_family_count"] == 1
    assert feedback_contract["summary"]["strategy_count"] == 1
    assert feedback_contract["summary"]["promotion_review_count"] == 1
    assert feedback_contract["summary"]["promotion_review_status_counts"] == {"watch": 1}
    assert feedback_contract["summary"]["target_pool_scope_count"] == 1
    assert feedback_contract["summary"]["holding_bucket_scope_count"] == 1
    assert feedback_contract["summary"]["generator_mode_scope_count"] == 1
    assert feedback_contract["summary"]["paper_hit_ratio"] == pytest.approx(0.72)
    assert feedback_contract["summary"]["paper_skill_lcb"] == pytest.approx(0.0)
    assert feedback_contract["summary"]["legacy_control_mode_counts"] == {"suppress": 1}
    assert feedback_contract["summary"]["skill_control_mode_counts"] == {"suppress": 1}
    assert momentum_feedback["ema_submit_count"] == pytest.approx(3.4)
    assert momentum_feedback["strategy_count"] == 1
    assert momentum_feedback["promotion_review_count"] == 1
    assert momentum_feedback["promotion_review_status"] == "watch"
    assert momentum_feedback["promotion_review_recommendation"] == "observe"
    assert momentum_feedback["promotion_review_score"] == pytest.approx(0.34)
    assert momentum_feedback["paper_hit_ratio"] == pytest.approx(0.72)
    assert momentum_feedback["paper_skill_lcb"] == pytest.approx(0.0)
    assert momentum_feedback["signal_count_total"] == 0
    assert momentum_feedback["zero_signal_strategy_count"] == 1
    assert momentum_feedback["zero_signal_ratio"] == pytest.approx(1.0)
    assert momentum_feedback["observed_forward_window_count"] == 0
    assert momentum_feedback["missing_forward_window_count"] == 4
    assert momentum_feedback["expected_forward_window_count"] == 4
    assert momentum_feedback["forward_window_coverage_ratio"] == pytest.approx(0.0)
    assert momentum_feedback["promotion_ready_count"] == 0
    assert momentum_feedback["promotion_ready_ratio"] == pytest.approx(0.0)
    assert momentum_feedback["promotion_review_coverage_ratio"] == pytest.approx(1.0)
    assert momentum_feedback["evidence_debt_strategy_count"] == 1
    assert momentum_feedback["evidence_debt_ratio"] == pytest.approx(0.85)
    assert (
        momentum_feedback["target_pool_feedback"]["theme:ai"]["strategy_count"] == 1
    )
    assert momentum_feedback["holding_bucket_feedback"]["short"]["strategy_count"] == 1
    assert (
        momentum_feedback["generator_mode_feedback"]["external_llm"]["strategy_count"] == 1
    )
    assert artifact["budget_feedback"] == feedback_root
    assert (
        artifact["summary"]["lifecycle_feedback_input_contract_version"]
        == LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION
    )
    assert artifact["summary"]["lifecycle_feedback_input_available"] is True
    assert artifact["summary"]["budget_feedback_target_pool_scope_count"] == 1
    assert artifact["summary"]["budget_feedback_holding_bucket_scope_count"] == 1
    assert artifact["summary"]["budget_feedback_generator_mode_scope_count"] == 1
    assert artifact["summary"]["budget_feedback_promotion_review_count"] == 1
    assert artifact["summary"]["budget_feedback_promotion_review_status_counts"] == {"watch": 1}
    assert artifact["summary"]["budget_feedback_paper_hit_ratio"] == pytest.approx(0.72)
    assert artifact["summary"]["budget_feedback_paper_skill_lcb"] == pytest.approx(0.0)
    assert artifact["summary"]["budget_feedback_skill_control_mode_counts"] == {"suppress": 1}
    assert artifact["summary"]["budget_feedback_zero_signal_strategy_count"] == 1
    assert artifact["summary"]["budget_feedback_zero_signal_ratio"] == pytest.approx(1.0)
    assert artifact["summary"]["budget_feedback_forward_window_coverage_ratio"] == pytest.approx(0.0)
    assert artifact["summary"]["budget_feedback_promotion_ready_count"] == 0
    assert artifact["summary"]["budget_feedback_promotion_ready_ratio"] == pytest.approx(0.0)
    assert artifact["summary"]["budget_feedback_promotion_review_coverage_ratio"] == pytest.approx(1.0)
    assert artifact["summary"]["budget_feedback_evidence_debt_strategy_count"] == 1
    assert artifact["summary"]["budget_feedback_evidence_debt_ratio"] == pytest.approx(0.85)
    assert "budget_feedback_zero_signal_backlog_high" in artifact["summary"]["quality_flags"]
    assert "budget_feedback_forward_window_coverage_low" in artifact["summary"]["quality_flags"]
    assert "budget_feedback_evidence_debt_high" in artifact["summary"]["quality_flags"]


def test_factor_research_feedback_router_rewrites_family_preference_order():
    family_reward_table, family_debt_table, search_route_actions, family_plans = (
        FactorResearchBuilder._build_search_route_feedback_snapshot(
            family_preference_order=["momentum", "value_factor", "quality_factor"],
            budget_feedback_root={
                "momentum": {
                    "strategy_count": 6,
                    "zero_signal_ratio": 1.0,
                    "forward_window_coverage_ratio": 0.0,
                    "promotion_ready_ratio": 0.0,
                    "promotion_review_coverage_ratio": 0.0,
                    "evidence_debt_ratio": 0.95,
                    "raw_validation_a_rate": 0.0,
                    "raw_validation_b_rate": 0.0,
                    "raw_validation_d_rate": 0.83,
                    "raw_validation_total_score_mean": 34.0,
                    "strict_incubation_ready_rate": 0.0,
                    "target_pool_feedback": {
                        "theme:ai": {
                            "strategy_count": 4,
                            "promotion_ready_ratio": 0.6,
                            "forward_window_coverage_ratio": 0.7,
                        }
                    },
                },
                "quality_factor": {
                    "strategy_count": 4,
                    "zero_signal_ratio": 0.0,
                    "forward_window_coverage_ratio": 0.8,
                    "promotion_ready_ratio": 0.6,
                    "promotion_review_coverage_ratio": 0.75,
                    "evidence_debt_ratio": 0.1,
                    "raw_validation_a_rate": 0.12,
                    "raw_validation_b_rate": 0.48,
                    "raw_validation_d_rate": 0.0,
                    "raw_validation_total_score_mean": 68.0,
                    "strict_incubation_ready_rate": 0.34,
                    "holding_bucket_feedback": {
                        "medium": {
                            "strategy_count": 3,
                            "promotion_ready_ratio": 0.7,
                            "forward_window_coverage_ratio": 0.75,
                        }
                    },
                },
            },
        )
    )

    effective_order = FactorResearchBuilder._rewrite_family_preference_order_by_feedback(
        ["momentum", "value_factor", "quality_factor"],
        family_plans=family_plans,
    )

    assert effective_order.index("quality_factor") < effective_order.index("momentum")
    assert effective_order[-1] == "momentum"
    assert family_reward_table["quality_factor"]["family_route_action"] == "family_explore"
    assert family_reward_table["quality_factor"]["raw_validation_b_rate"] == pytest.approx(0.48)
    assert family_reward_table["quality_factor"]["strict_incubation_ready_rate"] == pytest.approx(0.34)
    assert family_reward_table["quality_factor"]["family_quality_score"] > 0.0
    assert family_debt_table["momentum"]["raw_validation_d_rate"] == pytest.approx(0.83)
    assert family_debt_table["momentum"]["family_route_action"] in {
        "family_retire",
        "family_freeze",
        "family_cooldown",
    }
    assert any(action["scope"] == "target_pool" for action in search_route_actions)
    assert any(
        action["action"] == "holding_promote" and action["scope"] == "holding_bucket"
        for action in search_route_actions
    )


def test_spawner_factor_maps_can_use_governed_candidate_pool():
    factor_ic, factor_trend = StrategySpawner._factor_maps(
        {
            "factor_research": {
                "active_candidate_pool": {
                    "top_candidates": [
                        {"family": "capital_flow", "total_score": 78.0},
                    ]
                }
            }
        }
    )

    assert factor_ic["capital_flow"] == pytest.approx(0.78)
    assert factor_trend["capital_flow"] == "rising"


@pytest.mark.asyncio
async def test_market_opportunity_scanner_uses_governed_candidate_pool_tasks():
    class _UniverseDB:
        async def list_stock_universe(self, limit=120, offset=0):
            del limit, offset
            return [
                {
                    "code": "300001",
                    "name": "算力龙头A",
                    "industry": "算力",
                    "sector": "算力",
                    "market": "CN",
                    "market_cap": 120_000_000_000,
                },
                {
                    "code": "300002",
                    "name": "算力龙头B",
                    "industry": "算力",
                    "sector": "算力",
                    "market": "CN",
                    "market_cap": 95_000_000_000,
                },
                {
                    "code": "600001",
                    "name": "银行防御A",
                    "industry": "银行",
                    "sector": "银行",
                    "market": "CN",
                    "market_cap": 88_000_000_000,
                },
            ]

    scanner = MarketOpportunityScanner()
    report = await scanner.scan(
        _UniverseDB(),
        {
            "date": "2026-03-20",
            "fear_greed_index": 66,
            "fg_level": "greed",
            "hot_sectors": ["算力"],
            "cold_sectors": ["银行"],
            "factor_research": {
                "active_candidate_pool": {
                    "count": 2,
                    "family_summary": [
                        {
                            "family": "sentiment",
                            "count": 2,
                            "promote_count": 1,
                            "review_count": 1,
                            "avg_total_score": 82.0,
                            "max_total_score": 84.0,
                        }
                    ],
                    "regime_summary": [{"regime": "trend", "count": 2}],
                    "top_candidates": [
                        {
                            "artifact_id": "candidate_001",
                            "name": "sentiment_breakout_factor",
                            "family": "sentiment",
                            "expected_regime": ["trend"],
                            "expected_holding_period": 10,
                            "grade": "A",
                            "recommendation": "promote",
                            "registry_stage": "governed",
                            "total_score": 84.0,
                            "source_generation_artifact_id": "llm_episode_candidate_001",
                            "source_validation_artifact_id": "candidate_001",
                            "latest_validation_at": "2026-03-20T08:30:00+08:00",
                            "latest_validation_age_days": 0,
                            "evidence_status": {
                                "required_audits_complete": True,
                                "lookahead_available": True,
                                "multiple_testing_available": True,
                                "overall_risk_level": "low",
                                "blocked": False,
                            },
                        }
                    ],
                }
            },
        },
    )

    tasks = list(report["tasks"])
    regime_task = next(item for item in tasks if str(item.get("task_key")).startswith("regime:"))
    family_task = next(item for item in tasks if item.get("opportunity_type") == "candidate_family_activation")
    candidate_task = next(item for item in tasks if item.get("opportunity_type") == "candidate_factor_activation")

    assert regime_task["source_snapshot"]["governed_regime"] == "trend"
    assert family_task["candidate_family"] == "sentiment"
    assert "momentum" in family_task["preferred_strategy_types"]
    assert candidate_task["source_candidate_artifact_id"] == "candidate_001"
    assert candidate_task["source_generation_artifact_id"] == "llm_episode_candidate_001"
    assert candidate_task["source_validation_artifact_id"] == "candidate_001"
    assert candidate_task["candidate_registry_stage"] == "governed"
    assert candidate_task["expected_holding_period"] == 10
    assert candidate_task["latest_validation_age_days"] == 0
    assert candidate_task["candidate_evidence_status"]["required_audits_complete"] is True
    assert candidate_task["evidence_bundle"]["candidate_lineage"]["latest_validation_at"] == "2026-03-20T08:30:00+08:00"
    assert candidate_task["evidence_bundle"]["candidate_lineage"]["expected_holding_period"] == 10
    assert candidate_task["validation_focus"] == "candidate_target_only"
    assert candidate_task["candidate_grade"] == "A"


@pytest.mark.asyncio
async def test_snapshot_governed_family_contract_tightens_close_location_generation():
    class _UniverseDB:
        async def list_stock_universe(self, limit=200, offset=0):
            del limit, offset
            return [
                {
                    "code": "603855",
                    "name": "华荣科技",
                    "industry": "电力设备",
                    "sector": "电力设备",
                    "market": "CN",
                    "market_cap": 18_000_000_000,
                },
                {
                    "code": "603279",
                    "name": "景津装备",
                    "industry": "机械设备",
                    "sector": "机械设备",
                    "market": "CN",
                    "market_cap": 16_000_000_000,
                },
                {
                    "code": "002833",
                    "name": "弘亚数控",
                    "industry": "机械设备",
                    "sector": "机械设备",
                    "market": "CN",
                    "market_cap": 12_000_000_000,
                },
            ]

    scanner = MarketOpportunityScanner()
    report = await scanner.scan(
        _UniverseDB(),
        {
            "date": "2026-04-03",
            "fear_greed_index": 58,
            "fg_level": "neutral",
            "hot_sectors": ["机械设备"],
            "factor_research": {
                "active_candidate_pool": {
                    "count": 1,
                    "family_summary": [
                        {
                            "family": "close_location",
                            "count": 1,
                            "promote_count": 1,
                            "review_count": 0,
                            "avg_total_score": 79.0,
                            "max_total_score": 79.0,
                        }
                    ],
                    "top_candidates": [
                        {
                            "artifact_id": "candidate_close_location_001",
                            "name": "close_location_watch",
                            "family": "close_location",
                            "expected_regime": ["trend"],
                            "grade": "B",
                            "recommendation": "review",
                            "registry_stage": "validated",
                            "total_score": 79.0,
                            "source_generation_artifact_id": "llm_episode_close_location_001",
                            "source_validation_artifact_id": "candidate_close_location_001",
                        }
                    ],
                }
            },
        },
    )

    tasks = list(report["tasks"])
    family_task = next(item for item in tasks if item.get("opportunity_type") == "candidate_family_activation")
    candidate_task = next(item for item in tasks if item.get("opportunity_type") == "candidate_factor_activation")

    assert family_task["candidate_family"] == "close_location"
    assert family_task["template_generation_profile"] == "conservative_mean_reversion"
    assert family_task["allowed_strategy_types"] == ["rsi", "gap_fill", "ma_cross"]
    assert "momentum" not in family_task["preferred_strategy_types"]
    assert candidate_task["template_generation_profile"] == "conservative_mean_reversion"
    assert candidate_task["allowed_strategy_types"] == ["rsi", "gap_fill", "ma_cross"]
    assert "momentum" not in candidate_task["preferred_strategy_types"]
