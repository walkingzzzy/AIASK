from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.strategy_generators import RuleStrategyGenerator
from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec
from akshare_mcp.services.strategy_autonomy_components import (
    CandidateGenerationService,
    CommitteeReviewService,
    ExperimentRecorder,
)


@pytest.mark.asyncio
async def test_candidate_generation_service_merges_and_deduplicates_specs():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(side_effect=[
        [{"id": "sid_incubating", "strategy_type": "momentum", "params": {"lookback": 12}}],
        [{"id": "sid_listed", "strategy_type": "value_factor", "params": {"lookback": 30}}],
    ])

    duplicate_rule = StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="rule-dup")
    unique_rule = StrategySpec(strategy_type="value_factor", params={"lookback": 30}, name="rule-unique")
    llm_duplicate = StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="llm-dup")
    evolved_unique = StrategySpec(strategy_type="quality_factor", params={"lookback": 18}, name="evolved-unique")

    service.rule_generator.generate = lambda *_args, **_kwargs: [duplicate_rule, unique_rule]
    service.llm_generator.generate = AsyncMock(return_value=[llm_duplicate])
    service.llm_generator.get_last_report = lambda: {"external_provider": {"status": "succeeded"}}
    service.optimizer.evolve = AsyncMock(side_effect=[[evolved_unique], []])

    result = await service.generate(
        db,
        snapshot={"date": "2026-03-10"},
        limit=3,
        research_task={"task_id": "task_autonomy", "strategy_preferences": ["momentum", "value_factor", "quality_factor"]},
    )

    merged_specs = result["merged_specs"]
    assert len(merged_specs) == 3
    assert [spec.strategy_type for spec in merged_specs] == ["momentum", "value_factor", "quality_factor"]
    assert all(spec.metadata["research_task"]["task_id"] == "task_autonomy" for spec in merged_specs)
    assert result["llm_report"]["external_provider"]["status"] == "succeeded"


@pytest.mark.asyncio
async def test_candidate_generation_service_runs_bulk_stock_matrix_in_rule_only_mode_by_default():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])

    rule_specs = [
        StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="bulk-rule-1"),
        StrategySpec(strategy_type="ma_cross", params={"short_period": 5, "long_period": 20}, name="bulk-rule-2"),
    ]

    service.rule_generator.generate = lambda *_args, **_kwargs: list(rule_specs)
    service.llm_generator.generate = AsyncMock(side_effect=AssertionError("bulk task should not call llm generator by default"))
    service.optimizer.evolve = AsyncMock(side_effect=AssertionError("bulk task should not call optimizer by default"))

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 55},
        limit=2,
        research_task={
            "task_id": "bulk_task_1",
            "task_source": "bulk_stock_matrix",
            "strategy_preferences": ["momentum", "ma_cross"],
        },
    )

    assert [spec.strategy_type for spec in result["rule_specs"]] == ["momentum", "momentum"]
    assert result["llm_specs"] == []
    assert result["evolved_specs"] == []
    assert [spec.strategy_type for spec in result["merged_specs"]] == ["momentum", "momentum"]
    assert result["llm_report"]["mode"] == "rule_only"
    assert result["llm_report"]["external_provider"]["status"] == "skipped"
    assert result["llm_report"]["external_provider"]["skip_reason"] == "bulk_stock_matrix_llm_disabled"
    assert result["llm_report"]["optimizer"]["status"] == "skipped"
    db.list_strategies.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_generation_service_bulk_rule_first_expands_same_family_variants():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])

    service.llm_generator.generate = AsyncMock(side_effect=AssertionError("bulk task should not call llm generator by default"))
    service.optimizer.evolve = AsyncMock(side_effect=AssertionError("bulk task should not call optimizer by default"))

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-04", "fear_greed_index": 63},
        limit=3,
        research_task={
            "task_id": "bulk_task_variants",
            "task_source": "bulk_stock_matrix",
            "strategy_preferences": ["momentum"],
            "candidate_family": "momentum",
        },
    )

    assert len(result["rule_specs"]) == 3
    assert [spec.strategy_type for spec in result["rule_specs"]] == ["momentum", "momentum", "momentum"]
    assert len({tuple(sorted(spec.params.items())) for spec in result["rule_specs"]}) == 3
    assert [spec.name for spec in result["rule_specs"]] == [
        "AI 动量强化 V1",
        "AI 动量强化 V2",
        "AI 动量强化 V3",
    ]


@pytest.mark.asyncio
async def test_candidate_generation_service_can_enable_bulk_stock_matrix_llm_and_optimizer(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_LLM_ENABLED", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_OPTIMIZER_ENABLED", "1")

    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(side_effect=[
        [{"id": "sid_incubating", "strategy_type": "momentum", "params": {"lookback": 12}}],
        [{"id": "sid_listed", "strategy_type": "value_factor", "params": {"lookback": 30}}],
    ])

    service.rule_generator.generate = lambda *_args, **_kwargs: [
        StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="bulk-rule")
    ]
    service.llm_generator.generate = AsyncMock(
        return_value=[StrategySpec(strategy_type="quality_factor", params={"lookback": 18}, name="bulk-llm")]
    )
    service.llm_generator.get_last_report = lambda: {"external_provider": {"status": "succeeded", "selected_count": 1}}
    service.optimizer.evolve = AsyncMock(
        side_effect=[[StrategySpec(strategy_type="growth_factor", params={"lookback": 25}, name="bulk-evolved")], []]
    )

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 61},
        limit=3,
        research_task={
            "task_id": "bulk_task_2",
            "task_source": "bulk_stock_matrix",
            "strategy_preferences": ["momentum", "quality_factor", "growth_factor"],
        },
    )

    assert [spec.strategy_type for spec in result["merged_specs"]] == ["momentum", "quality_factor", "growth_factor"]
    assert result["llm_report"]["external_provider"]["status"] == "succeeded"
    assert db.list_strategies.await_count == 2
    assert service.llm_generator.generate.await_count == 1
    assert service.optimizer.evolve.await_count == 2


def test_rule_strategy_generator_prefers_task_requested_types_before_global_defaults():
    generator = RuleStrategyGenerator()

    specs = generator.generate(
        {
            "fear_greed_index": 52,
            "factor_research": {
                "preferred_strategy_types": ["rsi", "value_factor"],
                "summary": {"top_factor_names": ["reversal"]},
            },
        },
        limit=2,
        preferred_types=["momentum", "ma_cross"],
    )

    assert [spec.strategy_type for spec in specs] == ["momentum", "ma_cross"]


def test_rule_strategy_generator_supports_expanded_factory_types():
    generator = RuleStrategyGenerator()

    specs = generator.generate(
        {
            "fear_greed_index": 68,
            "factor_research": {
                "preferred_strategy_types": [
                    "volatility_breakout",
                    "north_capital_track",
                    "sector_rotation",
                    "gap_fill",
                    "mean_reversion_short",
                    "margin_divergence",
                ],
            },
        },
        limit=6,
        preferred_types=[
            "volatility_breakout",
            "north_capital_track",
            "sector_rotation",
            "gap_fill",
            "mean_reversion_short",
            "margin_divergence",
        ],
    )

    assert [spec.strategy_type for spec in specs] == [
        "volatility_breakout",
        "north_capital_track",
        "sector_rotation",
        "gap_fill",
        "mean_reversion_short",
        "margin_divergence",
    ]


def test_rule_strategy_generator_to_candidate_materializes_trade_contract():
    generator = RuleStrategyGenerator()

    specs = generator.generate(
        {
            "fear_greed_index": 55,
            "factor_research": {
                "preferred_strategy_types": ["momentum"],
            },
        },
        limit=1,
        preferred_types=["momentum"],
    )

    candidate = specs[0].to_candidate("strategy_factory:rule", "exp_rule_1")

    for key in (
        "holding_horizon",
        "trade_plan",
        "risk_rules",
        "rebalance_rule",
        "portfolio_spec",
        "execution_assumptions",
        "validation_profile",
    ):
        assert candidate[key]
        assert candidate["params"][key]
    assert candidate["validation_profile"]["profile"] == "trade_rule_validation"
    assert candidate["execution_assumptions"]["tradability_filter"] is True


def test_rule_strategy_generator_expanded_family_materializes_rule_template_contract():
    generator = RuleStrategyGenerator()

    specs = generator.generate(
        {
            "fear_greed_index": 66,
            "factor_research": {
                "preferred_strategy_types": ["sector_rotation"],
            },
        },
        limit=1,
        preferred_types=["sector_rotation"],
    )

    candidate = specs[0].to_candidate("strategy_factory:rule", "exp_rule_sector_rotation")

    assert candidate["portfolio_spec"]["target_weight_scheme"] == "equal_weight"
    assert candidate["portfolio_spec"]["weight_method"] == "sector_score_tilt"
    assert candidate["risk_rules"]["max_holding_days"] == 20
    assert candidate["validation_profile"]["primary_validation_layer"] == "combined"
    assert candidate["targeting_policy"]["universe_scope"] == "liquid_sector_leaders"
    assert candidate["generation_reason"]["template_generation_profile"] == "conservative_rotation"
    assert candidate["generation_reason"]["rule_template_contract"]["target_layer"] == "combined"


def test_committee_review_service_attaches_rank_and_lineage():
    service = CommitteeReviewService()

    def _review(spec, _snapshot):
        if spec.name == "reject-me":
            return None, {"decision": "reject", "final_score": 0.1}
        if spec.name == "champion":
            spec.metadata = {**dict(spec.metadata or {}), "committee_review": {"final_score": 0.91, "decision": "accept"}}
            return spec, {"decision": "accept", "final_score": 0.91}
        spec.metadata = {**dict(spec.metadata or {}), "committee_review": {"final_score": 0.62, "decision": "revise"}}
        return spec, {"decision": "revise", "final_score": 0.62}

    service.reviewer.review = _review

    result = service.review_candidates(
        [
            StrategySpec(strategy_type="momentum", params={"lookback": 10}, name="champion"),
            StrategySpec(strategy_type="value_factor", params={"lookback": 20}, name="reject-me"),
            StrategySpec(strategy_type="quality_factor", params={"lookback": 18}, name="runner-up"),
        ],
        snapshot={"date": "2026-03-10"},
        parent_strategy_id="sid_parent",
        task_run_id=42,
    )

    reviewed_specs = result["reviewed_specs"]
    assert len(reviewed_specs) == 2
    assert result["rejected_count"] == 1
    assert reviewed_specs[0].metadata["parent_strategy_id"] == "sid_parent"
    assert reviewed_specs[0].metadata["task_run_id"] == 42
    assert reviewed_specs[0].metadata["committee_review"]["rank"] == 1
    assert reviewed_specs[0].metadata["committee_review"]["is_champion"] is True
    assert reviewed_specs[1].metadata["committee_review"]["rank"] == 2
    assert reviewed_specs[1].metadata["committee_review"]["is_champion"] is False


@pytest.mark.asyncio
async def test_experiment_recorder_records_candidates_independently():
    recorder = ExperimentRecorder()

    async def _save(payload):
        return dict(payload)

    db = MagicMock()
    db.save_strategy_generation_experiment = AsyncMock(side_effect=_save)

    spec = StrategySpec(
        strategy_type="momentum",
        params={"lookback": 15, "threshold": 0.01},
        name="component-candidate",
        description="component hypothesis",
        tags=["ai_generated"],
        metadata={
            "generator_type": "llm_proxy",
            "research_task": {"task_id": "task_component"},
            "target_symbols": ["600519"],
        },
    )

    result = await recorder.record_candidates(
        db,
        [spec],
        source="test_component",
        snapshot={"date": "2026-03-10"},
        task_run={"id": 88},
    )

    assert result["experiments"][0]["task_run_id"] == 88
    assert result["experiments"][0]["strategy_spec"]["research_task"]["task_id"] == "task_component"
    assert result["candidates"][0]["experiment_id"] == result["experiments"][0]["experiment_id"]
    assert result["champion"]["experiment_id"] == result["experiments"][0]["experiment_id"]


@pytest.mark.asyncio
async def test_experiment_recorder_continues_when_persistence_fails():
    recorder = ExperimentRecorder()
    db = MagicMock()
    db.save_strategy_generation_experiment = AsyncMock(side_effect=ConnectionRefusedError("db offline"))

    spec = StrategySpec(
        strategy_type="momentum",
        params={"lookback": 15},
        name="component-fallback",
        description="component fallback hypothesis",
        tags=["ai_generated"],
        metadata={"generator_type": "llm_proxy", "research_task": {"task_id": "task_fallback"}},
    )

    result = await recorder.record_candidates(
        db,
        [spec],
        source="test_component",
        snapshot={"date": "2026-04-03"},
        task_run={"id": None},
    )

    assert result["experiments"][0]["experiment_id"].startswith("exp_")
    assert result["experiments"][0]["persistence_error"] == "db offline"
    assert result["candidates"][0]["experiment_id"] == result["experiments"][0]["experiment_id"]
    assert result["champion"]["experiment_id"] == result["experiments"][0]["experiment_id"]


@pytest.mark.asyncio
async def test_strategy_autonomy_service_continues_when_task_run_and_event_persistence_fail():
    service = StrategyAutonomyService()

    async def _save_experiment(payload):
        return dict(payload)

    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])
    db.save_strategy_task_run = AsyncMock(side_effect=ConnectionRefusedError("db offline"))
    db.save_strategy_generation_experiment = AsyncMock(side_effect=_save_experiment)
    db.save_strategy_domain_event = AsyncMock(side_effect=ConnectionRefusedError("db offline"))
    db.update_strategy_task_run = AsyncMock()

    service.rule_generator.generate = lambda *_args, **_kwargs: [
        StrategySpec(strategy_type="momentum", params={"lookback": 15}, name="db-fallback", tags=["rule"])
    ]
    service.llm_generator.generate = AsyncMock(return_value=[])
    service.optimizer.evolve = AsyncMock(return_value=[])

    result = await service.run_cycle(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 58},
        limit=1,
        source="test",
    )

    assert result["generated_count"] == 1
    assert result["task_run_id"] is None
    assert result["task_run"]["trace_id"]
    assert result["lifecycle"]["state"] == "completed"
    assert result["generation"]["count"] == 1
    assert result["review"]["reviewed_count"] == 1
    assert result["experiments"]["count"] == 1
    assert db.save_strategy_task_run.await_count == 1
    assert db.save_strategy_domain_event.await_count == 1
    db.update_strategy_task_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_generation_service_select_parents_tolerates_db_failures():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(side_effect=ConnectionRefusedError("db offline"))

    parents = await service.select_parents(db)

    assert parents == []
    assert db.list_strategies.await_count == 2
