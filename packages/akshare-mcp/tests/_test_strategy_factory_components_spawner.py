from __future__ import annotations

from ._test_strategy_factory_components_support import *

class TestStrategySpawner:
    @pytest.mark.asyncio
    async def test_factor_research_builder_builds_unified_artifact(self):
        from akshare_mcp.services.strategy_factory import FactorResearchBuilder

        with patch.object(
            FactorResearchBuilder, "_load_governed_candidate_pool",
            new_callable=AsyncMock, return_value={"available": False, "reason": "test_isolation"},
        ):
            artifact = await FactorResearchBuilder.build(
                MagicMock(),
                {
                    "factor_ic": {"value": 0.05, "quality": 0.04, "growth": -0.01},
                    "factor_ic_trend": {"value": "rising", "quality": "rising", "growth": "falling"},
                },
            )

        assert artifact["active_factors"] == ["value", "quality"]
        assert artifact["positive_rising_factors"] == ["value", "quality"]
        assert artifact["preferred_strategy_types"][:2] == ["value_factor", "multi_factor"]
        assert artifact["summary"]["active_factor_count"] == 2
        assert artifact["degraded"] is False

    @pytest.mark.asyncio
    async def test_factor_research_builder_exposes_freshness_and_decay_metadata(self):
        from akshare_mcp.services.strategy_factory import FactorResearchBuilder

        db = MagicMock()
        db.get_factor_ic_history = AsyncMock(side_effect=[
            [
                {"ic_date": "2026-03-19", "ic_value": 0.06},
                {"ic_date": "2026-03-18", "ic_value": 0.05},
                {"ic_date": "2026-03-17", "ic_value": 0.04},
                {"ic_date": "2026-03-16", "ic_value": 0.03},
                {"ic_date": "2026-03-15", "ic_value": 0.02},
                {"ic_date": "2026-03-14", "ic_value": -0.01},
                {"ic_date": "2026-03-13", "ic_value": -0.02},
                {"ic_date": "2026-03-12", "ic_value": -0.01},
                {"ic_date": "2026-03-11", "ic_value": -0.02},
                {"ic_date": "2026-03-10", "ic_value": -0.03},
            ],
            [],
            [],
            [],
            [],
        ])

        with patch.object(
            FactorResearchBuilder, "_load_governed_candidate_pool",
            new_callable=AsyncMock, return_value={"available": False, "reason": "test_isolation"},
        ):
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
        assert artifact["factor_history"]["value"]["stability_tag"] in {"improving", "stable", "regime_flip"}
        assert artifact["summary"]["quality_flags"] == []

    @pytest.mark.asyncio
    async def test_factor_research_builder_surfaces_governance_block_metadata(self):
        from akshare_mcp.services.strategy_factory import FactorResearchBuilder

        with patch.object(
            FactorResearchBuilder,
            "_load_governed_candidate_pool",
            new_callable=AsyncMock,
            return_value={
                "available": True,
                "summary": {
                    "active_count": 3,
                    "blocked_active_count": 2,
                    "registry_stage_counts": {"governed": 1, "validated": 2},
                    "lookahead_risk_counts": {"low": 2, "high": 1},
                    "multiple_testing_risk_counts": {"low": 2, "high": 1},
                    "overall_risk_counts": {"low": 1, "high": 2},
                },
                "active_pool": {
                    "source_count": 3,
                    "count": 1,
                    "excluded_count": 2,
                    "top_candidates": [
                        {
                            "artifact_id": "cand_safe",
                            "name": "cand_safe",
                            "family": "momentum",
                            "expected_regime": ["trend"],
                            "expected_holding_period": 10,
                            "grade": "A",
                            "recommendation": "promote",
                            "registry_stage": "governed",
                            "total_score": 92.0,
                            "source_generation_artifact_id": "llm_episode_safe",
                            "source_validation_artifact_id": "cand_safe",
                            "memory_record_id": "memory_safe",
                            "latest_validation_at": "2026-03-24T09:30:00+08:00",
                            "risk_audit": {
                                "overall_risk_level": "low",
                                "lookahead_available": True,
                                "multiple_testing_available": True,
                                "required_audits_complete": True,
                                "blocked": False,
                            },
                        }
                    ],
                    "excluded_candidates": [
                        {
                            "artifact_id": "cand_lookahead",
                            "name": "cand_lookahead",
                            "family": "momentum",
                            "expected_regime": ["trend"],
                            "expected_holding_period": 5,
                            "grade": "A",
                            "recommendation": "promote",
                            "registry_stage": "validated",
                            "total_score": 97.0,
                            "reasons": ["lookahead_risk_high"],
                            "source_generation_artifact_id": "llm_episode_lookahead",
                            "source_validation_artifact_id": "cand_lookahead",
                            "risk_audit": {"overall_risk_level": "high", "blocked": True},
                        },
                        {
                            "artifact_id": "cand_multiple",
                            "name": "cand_multiple",
                            "family": "quality",
                            "grade": "B",
                            "recommendation": "review",
                            "registry_stage": "validated",
                            "total_score": 88.0,
                            "reasons": ["multiple_testing_risk_high"],
                            "source_generation_artifact_id": "llm_episode_multiple",
                            "source_validation_artifact_id": "cand_multiple",
                            "risk_audit": {"overall_risk_level": "high", "blocked": True},
                        },
                    ],
                    "family_summary": [
                        {
                            "family": "momentum",
                            "count": 1,
                            "promote_count": 1,
                            "review_count": 0,
                            "avg_total_score": 92.0,
                            "max_total_score": 92.0,
                        }
                    ],
                    "regime_summary": [{"regime": "trend", "count": 1}],
                    "exclusion_reason_counts": {
                        "lookahead_risk_high": 1,
                        "multiple_testing_risk_high": 1,
                    },
                },
            },
        ):
            artifact = await FactorResearchBuilder.build(
                MagicMock(),
                {
                    "factor_ic": {"value": 0.05},
                    "factor_ic_trend": {"value": "rising"},
                },
            )

        assert artifact["summary"]["governed_source_candidate_count"] == 3
        assert artifact["summary"]["governed_blocked_candidate_count"] == 2
        assert artifact["summary"]["governed_exclusion_reason_counts"]["lookahead_risk_high"] == 1
        assert artifact["summary"]["governed_risk_counts"]["overall"]["high"] == 2
        assert artifact["summary"]["governed_registry_stage_counts"]["governed"] == 1
        assert "governed_candidate_pool_blocked_candidates" in artifact["quality_flags"]
        assert artifact["blocked_candidates"][0]["artifact_id"] == "cand_lookahead"
        assert artifact["top_candidate_lineage"][0]["source_generation_artifact_id"] == "llm_episode_safe"
        assert artifact["top_candidate_lineage"][0]["expected_holding_period"] == 10
        assert artifact["top_candidate_lineage"][0]["latest_validation_age_days"] is None
        assert artifact["blocked_candidate_lineage"][0]["expected_holding_period"] == 5
        assert artifact["summary"]["factor_source_mode"] == "governed_candidate_pool"

    def test_factory_scheduler_compact_factor_research_snapshot_preserves_governance_block_metadata(self):
        from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

        compact = StrategyFactoryScheduler._compact_factor_research_snapshot(
            {
                "summary": {
                    "active_factor_count": 2,
                    "active_candidate_count": 1,
                    "governed_source_candidate_count": 3,
                    "governed_blocked_candidate_count": 2,
                    "ranked_factor_count": 2,
                    "top_factor_names": ["value", "quality"],
                    "top_candidate_names": ["cand_safe"],
                    "active_family_names": ["momentum"],
                    "active_regime_names": ["trend"],
                    "preferred_strategy_types": ["momentum", "value_factor"],
                    "factor_source_mode": "governed_candidate_pool",
                    "governed_exclusion_reason_counts": {
                        "lookahead_risk_high": 1,
                        "multiple_testing_risk_high": 1,
                    },
                    "governed_registry_stage_counts": {"governed": 1, "validated": 2},
                    "top_candidate_lineage": [
                        {
                            "artifact_id": "cand_safe",
                            "name": "cand_safe",
                            "family": "momentum",
                            "registry_stage": "governed",
                            "expected_regime": ["trend"],
                            "expected_holding_period": 10,
                            "source_generation_artifact_id": "llm_episode_safe",
                            "source_validation_artifact_id": "cand_safe",
                            "memory_record_id": "memory_safe",
                            "latest_validation_at": "2026-03-24T09:30:00+08:00",
                            "latest_validation_age_days": 0,
                        }
                    ],
                    "governed_risk_counts": {
                        "overall": {"high": 2},
                    },
                    "degraded": False,
                    "freshness_days": 0,
                    "latest_factor_date": "2026-03-24",
                    "stale": False,
                    "quality_flags": ["governed_candidate_pool_active", "governed_candidate_pool_blocked_candidates"],
                },
                "active_candidate_pool": {
                    "source_count": 3,
                    "count": 1,
                    "excluded_count": 2,
                    "top_candidates": [
                        {
                            "artifact_id": "cand_safe",
                            "name": "cand_safe",
                            "family": "momentum",
                            "expected_regime": ["trend"],
                            "expected_holding_period": 10,
                            "grade": "A",
                            "recommendation": "promote",
                            "registry_stage": "governed",
                            "total_score": 92.0,
                            "source_generation_artifact_id": "llm_episode_safe",
                            "source_validation_artifact_id": "cand_safe",
                            "memory_record_id": "memory_safe",
                            "latest_validation_at": "2026-03-24T09:30:00+08:00",
                            "latest_validation_age_days": 0,
                            "lineage": {
                                "generation_artifact_id": "llm_episode_safe",
                                "validation_artifact_id": "cand_safe",
                                "memory_record_id": "memory_safe",
                            },
                            "risk_audit": {
                                "overall_risk_level": "low",
                                "lookahead_available": True,
                                "multiple_testing_available": True,
                                "required_audits_complete": True,
                                "blocked": False,
                            },
                        }
                    ],
                    "excluded_candidates": [
                        {
                            "artifact_id": "cand_lookahead",
                            "name": "cand_lookahead",
                            "family": "momentum",
                            "expected_regime": ["trend"],
                            "expected_holding_period": 5,
                            "grade": "A",
                            "recommendation": "promote",
                            "registry_stage": "validated",
                            "total_score": 97.0,
                            "admission_blocked": True,
                            "admission_block_reasons": ["lookahead_risk_high"],
                            "source_generation_artifact_id": "llm_episode_lookahead",
                            "source_validation_artifact_id": "cand_lookahead",
                            "latest_validation_at": "2026-03-24T08:15:00+08:00",
                            "latest_validation_age_days": 0,
                            "reasons": ["lookahead_risk_high"],
                            "risk_audit": {
                                "lookahead_risk_level": "high",
                                "overall_risk_level": "high",
                                "lookahead_available": True,
                                "multiple_testing_available": True,
                                "required_audits_complete": False,
                                "blocked": True,
                                "block_reasons": ["lookahead_risk_high"],
                            },
                        }
                    ],
                    "exclusion_reason_counts": {"lookahead_risk_high": 1},
                    "family_summary": [{"family": "momentum", "count": 1, "promote_count": 1, "review_count": 0}],
                    "regime_summary": [{"regime": "trend", "count": 1}],
                },
            }
        )

        assert compact["summary"]["governed_source_candidate_count"] == 3
        assert compact["summary"]["governed_blocked_candidate_count"] == 2
        assert compact["summary"]["governed_exclusion_reason_counts"]["lookahead_risk_high"] == 1
        assert compact["summary"]["governed_registry_stage_counts"]["governed"] == 1
        assert compact["summary"]["top_candidate_lineage"][0]["source_generation_artifact_id"] == "llm_episode_safe"
        assert compact["summary"]["top_candidate_lineage"][0]["expected_holding_period"] == 10
        assert compact["summary"]["governed_risk_counts"]["overall"]["high"] == 2
        assert compact["active_candidate_pool"]["source_count"] == 3
        assert compact["active_candidate_pool"]["excluded_count"] == 2
        assert compact["active_candidate_pool"]["exclusion_reason_counts"]["lookahead_risk_high"] == 1
        assert compact["active_candidate_pool"]["excluded_candidates"][0]["reasons"] == ["lookahead_risk_high"]
        assert compact["active_candidate_pool"]["excluded_candidates"][0]["risk_audit"]["blocked"] is True
        assert compact["active_candidate_pool"]["excluded_candidates"][0]["expected_holding_period"] == 5
        assert compact["active_candidate_pool"]["top_candidates"][0]["source_generation_artifact_id"] == "llm_episode_safe"
        assert compact["active_candidate_pool"]["top_candidates"][0]["expected_holding_period"] == 10
        assert compact["active_candidate_pool"]["top_candidates"][0]["risk_audit"]["required_audits_complete"] is True
        assert compact["active_candidate_pool"]["top_candidates"][0]["lineage"]["validation_artifact_id"] == "cand_safe"

    def test_factory_cycle_runner_readiness_exposes_governance_block_metadata(self):
        from strategy_factory.application.cycle_runner import FactoryCycleRunner, FactoryRunContext
        from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

        scheduler = StrategyFactoryScheduler()
        runner = FactoryCycleRunner(
            scheduler,
            FactoryRunContext(
                db=None,
                factory_pkg=None,
                runtime_adapters=None,
                start=datetime(2026, 3, 24, 9, 30, 0),
                trace_id="trace_governed_readiness",
                run_id="run_governed_readiness",
            ),
        )

        readiness = runner._build_factory_readiness(
            snapshot={
                "degraded": False,
                "completeness": {"completion_ratio": 1.0},
                "sources": {"event_driven": {"status": "success"}},
                "event_driven": {"tasks_ready_count": 1},
            },
            factor_research={
                "summary": {
                    "factor_source_mode": "governed_candidate_pool",
                    "active_candidate_count": 1,
                    "active_family_names": ["momentum"],
                    "active_regime_names": ["trend"],
                    "governed_source_candidate_count": 3,
                    "governed_blocked_candidate_count": 2,
                    "governed_exclusion_reason_counts": {
                        "lookahead_risk_high": 1,
                        "multiple_testing_risk_high": 1,
                    },
                    "governed_risk_counts": {"overall": {"high": 2}},
                    "degraded": False,
                    "stale": False,
                },
                "freshness_repair": {"refresh_attempted": False, "refresh_status": "not_needed"},
            },
        )

        assert readiness["governed_source_candidate_count"] == 3
        assert readiness["governed_blocked_candidate_count"] == 2
        assert readiness["governed_exclusion_reason_counts"]["lookahead_risk_high"] == 1
        assert readiness["governed_risk_counts"]["overall"]["high"] == 2
        assert "governed_candidate_pool_blocked_candidates" in readiness["warnings"]
        assert readiness["can_proceed"] is True

    def test_fear_market_generates_rsi_and_value(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fear_greed({"fear_greed_index": 20})
        types = [c["strategy_type"] for c in candidates]
        assert "rsi" in types
        assert "value_factor" in types
        assert all(c["generation_reason"]["source"] == "fear_greed" for c in candidates)
        first = candidates[0]
        assert first["generation_reason"]["summary"] == first["spawn_reason"]
        assert first["trigger_signal"] == {"field": "fear_greed_index", "value": 20, "level": "fear"}
        assert first["trigger_thresholds"][0]["field"] == "fear_greed_index"
        assert first["trigger_thresholds"][0]["operator"] == "<"
        assert first["trigger_thresholds"][0]["threshold"] == 30

    def test_greed_market_generates_momentum_and_growth(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fear_greed({"fear_greed_index": 80})
        types = [c["strategy_type"] for c in candidates]
        assert "momentum" in types
        assert "growth_factor" in types

    def test_neutral_market_generates_ma_cross(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fear_greed({"fear_greed_index": 50})
        types = [c["strategy_type"] for c in candidates]
        assert "ma_cross" in types

    def test_fund_flow_north_inflow(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fund_flow({"north_fund_3d_net": 8e9, "margin_5d_change_pct": 0})
        types = [c["strategy_type"] for c in candidates]
        assert "growth_factor" in types
        assert "quality_factor" in types
        assert all(c["generation_reason"]["source"] == "fund_flow" for c in candidates)
        assert all(c["trigger_signal"]["field"] == "north_fund_3d_net" for c in candidates)
        assert all(c["trigger_thresholds"][0]["threshold"] == 5_000_000_000 for c in candidates)

    def test_fund_flow_north_outflow(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fund_flow({"north_fund_3d_net": -8e9, "margin_5d_change_pct": 0})
        types = [c["strategy_type"] for c in candidates]
        assert "value_factor" in types
        assert "macro_timing" in types

    def test_fund_flow_margin_increase(self):
        spawner = StrategySpawner()
        candidates = spawner._from_fund_flow({"north_fund_3d_net": 0, "margin_5d_change_pct": 3.5})
        types = [c["strategy_type"] for c in candidates]
        assert "momentum" in types

    def test_factor_ic_generates_multi_factor(self):
        spawner = StrategySpawner()
        snapshot = {
            "factor_ic": {"value": 0.05, "quality": 0.04, "growth": 0.01},
            "factor_ic_trend": {"value": "rising", "quality": "rising", "growth": "flat"},
        }
        candidates = spawner._from_factor_ic(snapshot)
        types = [c["strategy_type"] for c in candidates]
        assert "multi_factor" in types
        assert "value_factor" in types
        multi_factor = next(c for c in candidates if c["strategy_type"] == "multi_factor")
        assert multi_factor["generation_reason"]["source"] == "factor_ic"
        assert multi_factor["trigger_signal"]["field"] == "factor_ic_weights"
        assert multi_factor["trigger_thresholds"][0]["operator"] == "derived_from"

    def test_factor_ic_prefers_factor_research_artifact_when_present(self):
        spawner = StrategySpawner()
        snapshot = {
            "factor_ic": {},
            "factor_ic_trend": {},
            "factor_research": {
                "ranked_factors": [
                    {
                        "factor_name": "value",
                        "ic_value": 0.06,
                        "trend": "rising",
                        "score": 0.08,
                        "preferred_strategy_types": ["value_factor", "multi_factor"],
                    },
                    {
                        "factor_name": "quality",
                        "ic_value": 0.04,
                        "trend": "rising",
                        "score": 0.06,
                        "preferred_strategy_types": ["quality_factor", "multi_factor"],
                    },
                ],
                "positive_rising_factors": ["value", "quality"],
                "preferred_strategy_types": ["value_factor", "multi_factor", "quality_factor"],
            },
        }

        candidates = spawner._from_factor_ic(snapshot)

        assert {item["strategy_type"] for item in candidates} >= {"value_factor", "quality_factor", "multi_factor"}

    def test_fill_gaps_prefers_market_aligned_types_with_budget(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 50,
            "north_fund_3d_net": 0,
            "margin_5d_change_pct": 0,
            "factor_ic": {},
            "factor_ic_trend": {},
            "event_driven": {"event_count": 0, "tasks_ready_count": 0},
            "completeness": {"completion_ratio": 1.0},
        }
        candidates = spawner._fill_gaps(snapshot, current_candidates=[])
        assert 0 < len(candidates) <= SPAWNER_FILL_BUDGET_MAX
        assert {item["strategy_type"] for item in candidates} <= {"ma_cross", "momentum", "quality_factor", "value_factor"}
        first = candidates[0]
        assert first["generation_reason"]["kind"] == "quota_fill"
        assert first["generation_reason"]["source"] == "quota_fill"
        assert first["quota_fill"]["strategy_type"] == first["strategy_type"]
        assert first["quota_fill"]["minimum_required"] == CATEGORY_MINIMUMS[first["strategy_type"]]
        assert first["trigger_thresholds"][0]["field"] == f"generated_type_counts.{first['strategy_type']}"

    def test_fill_gaps_limits_budget_when_event_research_ready(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_EVENT_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 55,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }
        current_candidates = [{"strategy_type": "ma_cross"}, {"strategy_type": "momentum"}, {"strategy_type": "multi_factor"}, {"strategy_type": "quality_factor"}, {"strategy_type": "value_factor"}]
        candidates = spawner._fill_gaps(snapshot, current_candidates=current_candidates)
        assert len(candidates) <= SPAWNER_EVENT_FILL_BUDGET_MAX

    def test_fill_gaps_allows_controlled_budget_when_event_ready_and_local_signals_are_strong(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_EVENT_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }

        candidates = spawner._fill_gaps(snapshot, current_candidates=[{"strategy_type": "quality_factor"}])

        assert 0 < len(candidates) <= SPAWNER_EVENT_FILL_BUDGET_MAX
        assert all(candidate.get("quota_fill") for candidate in candidates)

    def test_spawn_returns_nonempty(self):
        from akshare_mcp.services.strategy_factory.constants import SPAWNER_FILL_BUDGET_MAX

        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 50, "fg_level": "neutral",
            "fg_components": {"volatility": 50},
            "factor_ic": {}, "factor_ic_trend": {},
            "north_fund_3d_net": 0, "margin_5d_change_pct": 0,
            "category_counts": {},
            "completeness": {"completion_ratio": 1.0},
        }
        candidates = spawner.spawn(snapshot)
        assert len(candidates) > 0
        for c in candidates:
            assert "strategy_type" in c
            assert "params" in c
            assert "spawn_reason" in c
            assert "generation_reason" in c
            assert "trigger_signal" in c
            assert "trigger_thresholds" in c
        report = spawner.get_last_report()
        assert report["summary"]["candidate_count"] == len(candidates)
        assert 0 < report["summary"]["quota_fill_count"] <= SPAWNER_FILL_BUDGET_MAX
        assert report["summary"]["signal_trigger_count"] > 0
        assert report["summary"]["threshold_hit_count"] >= len(candidates)
        assert report["summary"]["source_counts"]["quota_fill"] > 0
        assert report["summary"]["source_counts"]["fear_greed"] > 0
        assert report["summary"]["source_counts"].get("factor_ic", 0) == 0

    def test_spawn_event_ready_keeps_controlled_local_templates(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 55,
            "fg_components": {"volatility": 50},
            "factor_ic": {},
            "factor_ic_trend": {},
            "north_fund_3d_net": 0,
            "margin_5d_change_pct": 0,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }
        candidates = spawner.spawn(snapshot)
        report = spawner.get_last_report()
        summary = report["summary"]

        assert candidates
        assert summary["event_ready"] is True
        assert summary["event_ready_supplemental"] is False
        assert summary["quota_fill_count"] == 0
        assert summary["source_counts"].get("fear_greed", 0) > 0
        assert summary["source_counts"]["fear_greed"] <= summary["source_budget_caps"]["fear_greed"]
        assert summary["source_raw_counts"]["fear_greed"] > summary["source_counts"]["fear_greed"]
        assert summary["source_counts"].get("volatility", 0) == 0
        assert summary["source_counts"].get("fund_flow", 0) == 0
        assert summary["source_trimmed_count"] >= 1
        assert all((item.get("generation_reason") or {}).get("source") != "quota_fill" for item in candidates)

    def test_spawn_allows_controlled_event_ready_fill_when_local_signals_are_strong(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }

        candidates = spawner.spawn(snapshot)
        report = spawner.get_last_report()
        summary = report["summary"]

        assert candidates
        assert summary["event_ready"] is True
        assert summary["event_ready_supplemental"] is True
        assert summary["quota_fill_count"] >= 0
        assert summary["source_counts"].get("fear_greed", 0) > 0
        assert summary["source_counts"].get("volatility", 0) > 0
        assert summary["source_counts"].get("fund_flow", 0) > 0
        assert summary["source_counts"]["fear_greed"] <= summary["source_budget_caps"]["fear_greed"]
        assert summary["source_counts"]["volatility"] <= summary["source_budget_caps"]["volatility"]
        assert summary["source_counts"]["fund_flow"] <= summary["source_budget_caps"]["fund_flow"]
        assert summary["source_raw_counts"]["fund_flow"] > summary["source_counts"]["fund_flow"]
        assert summary["source_trimmed_count"] >= 1
        assert summary["signal_trigger_count"] > 0

    def test_spawn_adds_signal_variants_when_signals_are_strong(self):
        spawner = StrategySpawner()
        snapshot = {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 0, "tasks_ready_count": 0},
            "completeness": {"completion_ratio": 1.0},
        }

        candidates = spawner.spawn(snapshot)
        variant_candidates = [
            item for item in candidates
            if (item.get("generation_reason") or {}).get("source") == "signal_variation"
        ]
        report = spawner.get_last_report()

        assert variant_candidates
        assert report["summary"]["source_counts"].get("signal_variation", 0) == len(variant_candidates)
        assert all(item["trigger_thresholds"][0]["label"] == "强信号变体扩容" for item in variant_candidates)



__all__ = [name for name in globals() if name.startswith("Test")]
