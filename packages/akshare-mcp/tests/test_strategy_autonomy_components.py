import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.strategy_generators import RuleStrategyGenerator
from akshare_mcp.services.strategy_autonomy import StrategyAutonomyService, StrategySpec
from akshare_mcp.services.strategy_autonomy_components import (
    CandidateGenerationService,
    CommitteeReviewService,
    ExperimentRecorder,
)
from akshare_mcp.storage.timescaledb.strategy_ai import StrategyAIMixin


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
    assert [spec.strategy_type for spec in merged_specs] == ["momentum", "quality_factor", "value_factor"]
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
async def test_candidate_generation_service_metadata_only_task_keeps_default_rule_generation():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])

    service.rule_generator.generate = lambda *_args, **_kwargs: [
        StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="metadata-rule")
    ]
    service.llm_generator.generate = AsyncMock(return_value=[])
    service.llm_generator.get_last_report = lambda: {}
    service.optimizer.evolve = AsyncMock(return_value=[])

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 58},
        limit=1,
        research_task={"metadata": {"factor_research": {"degraded": False}}},
    )

    assert len(result["rule_specs"]) == 1
    assert [spec.strategy_type for spec in result["merged_specs"]] == ["momentum"]


@pytest.mark.asyncio
async def test_candidate_generation_service_can_skip_external_llm_when_scheduler_blocks_provider():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])

    service.rule_generator.generate = lambda *_args, **_kwargs: [
        StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="scheduler-blocked-rule")
    ]
    service.llm_generator.generate = AsyncMock(side_effect=AssertionError("scheduler-blocked task should skip llm"))
    service.optimizer.evolve = AsyncMock(return_value=[])

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 58},
        limit=3,
        research_task={
            "task_id": "task_provider_blocked",
            "disable_external_llm": True,
            "external_llm_skip_reason": "empty_200_false_success_detected",
        },
    )

    assert [spec.strategy_type for spec in result["merged_specs"]] == ["momentum"]
    assert result["llm_report"]["external_provider"]["status"] == "skipped"
    assert result["llm_report"]["external_provider"]["skip_reason"] == "empty_200_false_success_detected"


@pytest.mark.asyncio
async def test_candidate_generation_service_replays_persisted_hypotheses_when_external_llm_is_blocked():
    service = CandidateGenerationService()
    db = MagicMock()
    db.get_strategy = AsyncMock(
        return_value={"id": "sid_parent_replay", "strategy_type": "momentum", "params": {"lookback": 12}}
    )

    service.rule_generator.generate = lambda *_args, **_kwargs: [
        StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="scheduler-blocked-rule")
    ]
    service.llm_generator.generate = AsyncMock(side_effect=AssertionError("scheduler-blocked task should skip llm"))
    service.llm_generator.replay_persisted_specs = AsyncMock(
        return_value={
            "specs": [
                StrategySpec(
                    strategy_type="quality_factor",
                    params={"lookback": 18},
                    name="replayed-hypothesis",
                    metadata={"generator_type": "hypothesis_replay"},
                )
            ],
            "report": {
                "status": "succeeded",
                "trigger_reason": "empty_200_false_success_detected",
                "selected_count": 1,
            },
        }
    )
    service.optimizer.evolve = AsyncMock(return_value=[])

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 58},
        limit=3,
        research_task={
            "task_id": "task_provider_blocked_replay",
            "disable_external_llm": True,
            "external_llm_skip_reason": "empty_200_false_success_detected",
        },
        parent_strategy_id="sid_parent_replay",
    )

    assert [spec.strategy_type for spec in result["replay_specs"]] == ["quality_factor"]
    assert [spec.strategy_type for spec in result["merged_specs"]] == ["quality_factor", "momentum"]
    assert result["llm_report"]["replay_provider"]["status"] == "succeeded"
    assert result["llm_report"]["replay_provider"]["selected_count"] == 1


@pytest.mark.asyncio
async def test_candidate_generation_service_can_skip_optimizer_when_scheduler_blocks_rl_mode():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])

    service.rule_generator.generate = lambda *_args, **_kwargs: [
        StrategySpec(strategy_type="momentum", params={"lookback": 20}, name="scheduler-blocked-rule")
    ]
    service.llm_generator.generate = AsyncMock(return_value=[])
    service.llm_generator.get_last_report = lambda: {"external_provider": {"status": "skipped"}}
    service.optimizer.evolve = AsyncMock(side_effect=AssertionError("scheduler-blocked task should skip optimizer"))

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-03", "fear_greed_index": 58},
        limit=3,
        research_task={
            "task_id": "task_rl_mode_blocked",
            "disable_optimizer": True,
            "optimizer_skip_reason": "refresh_absorption_without_creation",
        },
    )

    assert [spec.strategy_type for spec in result["merged_specs"]] == ["momentum"]
    assert result["llm_report"]["optimizer"]["status"] == "skipped"
    assert result["llm_report"]["optimizer"]["skip_reason"] == "refresh_absorption_without_creation"


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

    assert [spec.strategy_type for spec in result["merged_specs"]] == ["quality_factor", "growth_factor", "momentum"]
    assert result["llm_report"]["external_provider"]["status"] == "succeeded"
    assert db.list_strategies.await_count == 2
    assert service.llm_generator.generate.await_count == 1
    assert service.optimizer.evolve.await_count == 2


@pytest.mark.asyncio
async def test_candidate_generation_service_honors_preferred_strategy_types_without_legacy_alias():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=[])
    observed_preferred_types: list[list[str]] = []

    def _generate(_snapshot, *, limit, preferred_types=None):
        observed_preferred_types.append(list(preferred_types or []))
        return [StrategySpec(strategy_type="rsi", params={"rsi_period": 6}, name="preferred-rule")]

    service.rule_generator.generate = _generate
    service.llm_generator.generate = AsyncMock(return_value=[])
    service.llm_generator.get_last_report = lambda: {}
    service.optimizer.evolve = AsyncMock(return_value=[])

    result = await service.generate(
        db,
        snapshot={"date": "2026-04-08", "fear_greed_index": 49},
        limit=3,
        research_task={
            "task_id": "task_new_contract_only",
            "preferred_strategy_types": ["rsi", "value_factor"],
            "allowed_strategy_types": ["rsi"],
            "preference_strength": "hard",
            "validation_focus": "candidate_target_only",
        },
    )

    assert observed_preferred_types == [["rsi", "value_factor"]]
    assert [spec.strategy_type for spec in result["merged_specs"]] == ["rsi"]


def test_strategy_autonomy_service_llm_summary_exposes_provider_health_ratios():
    summary = StrategyAutonomyService._summarize_llm_report(
        {
            "external_provider": {
                "status": "fallback_only",
                "requests": [
                    {
                        "status": "fallback",
                        "error_type": "ProviderCompatibilityError",
                        "error": "response missing extractable content",
                        "request_metrics": {
                            "attempt_count": 1,
                            "status": "compatibility_failed",
                            "empty_200_response": True,
                        },
                    },
                    {
                        "status": "compatibility_skip",
                        "request_metrics": {"attempt_count": 0},
                    },
                ],
            }
        }
    )

    external = summary["external_provider"]
    assert external["network_request_count"] == 1
    assert external["real_request_count"] == 1
    assert external["compatibility_skip_count"] == 1
    assert external["compatibility_failure_count"] == 1
    assert external["compatibility_failure_ratio"] == 1.0
    assert external["effective_response_ratio"] == 0.0
    assert external["empty_200_response_count"] == 1


def test_strategy_autonomy_service_research_task_summary_exposes_normalized_preference_contract():
    summary = StrategyAutonomyService._summarize_research_task(
        {
            "task_id": "task_contract_summary",
            "preferred_strategy_types": ["rsi", "value_factor"],
            "allowed_strategy_types": ["rsi", "ma_cross"],
            "preference_strength": "hard",
            "validation_focus": "candidate_target_only",
            "target_symbols": ["300750"],
        },
        factor_research=None,
    )

    assert summary["preferred_strategy_types"] == ["rsi", "value_factor"]
    assert summary["strategy_preferences"] == ["rsi", "value_factor"]
    assert summary["allowed_strategy_types"] == ["rsi", "ma_cross"]
    assert summary["preference_strength"] == "hard"
    assert summary["validation_focus"] == "candidate_target_only"
    assert summary["target_symbols"] == ["300750"]


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
    assert candidate["evidence_chain"]["evidences"][0]["evidence_id"].startswith("momentum_ev_")
    assert candidate["prediction_contract"]["claims"][0]["evidence_ids"]
    assert candidate["confidence_contract"]["prediction_quality"]["quality"]
    assert candidate["trade_plan"]["entry"]["claim_ids"] == ["momentum_claim_entry"]
    assert candidate["trade_plan"]["exit"]["claim_ids"] == ["momentum_claim_exit"]


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
async def test_experiment_recorder_summarizes_large_payload_without_writing_files(tmp_path):
    recorder = ExperimentRecorder()
    db = MagicMock()
    db.save_strategy_generation_experiment = AsyncMock(side_effect=lambda payload: dict(payload))

    spec = StrategySpec(
        strategy_type="momentum",
        params={"lookback": 15, "dsl": {"entry": {"any": [{"op": "gt", "value": "x" * 512}]}}},
        name="externalize-me",
        description="large experiment payload",
        tags=["ai_generated"],
        metadata={
            "generator_type": "llm_proxy",
            "research_task": {"task_id": "task_large_payload", "task_source": "snapshot"},
            "llm_response": {
                "provider": "mock",
                "raw_response": "y" * 4096,
                "request_metrics": {"attempt_count": 1, "response_chars": 4096},
                "candidates": [{"name": "candidate-a"}],
            },
        },
    )

    payload = await recorder.record_experiment(
        db,
        spec,
        source="test_component",
        snapshot={"date": "2026-04-06"},
        task_run={"id": 101},
    )

    assert payload["parameters"]["dsl_present"] is True
    assert "raw_response" not in payload["evaluation"]["llm_response"]
    assert payload["evaluation"]["llm_response"]["request_metrics"]["response_chars"] == 4096
    assert "full_payload_storage" not in payload["evaluation"]
    assert list(tmp_path.rglob("*.json")) == []


@pytest.mark.asyncio
async def test_experiment_recorder_persists_structured_hypothesis_artifact():
    recorder = ExperimentRecorder()
    db = MagicMock()
    db.save_strategy_generation_experiment = AsyncMock(side_effect=lambda payload: dict(payload))

    spec = StrategySpec(
        strategy_type="rsi",
        params={"lookback": 6},
        name="l2-hypothesis",
        description="legacy description should not win",
        tags=["ai_generated"],
        metadata={
            "generator_type": "external_llm",
            "research_task": {"task_id": "task_hypothesis_persist", "task_source": "snapshot"},
            "hypothesis_artifact": {
                "artifact_id": "hyp_persisted",
                "alpha_hypothesis": "超跌修复在一周内兑现。",
                "family_hint": "rsi",
                "holding_rationale": "信号半衰期较短。",
                "alpha_half_life": 8,
                "position_model": "equal_weight",
                "market_regime_assumption": {"preferred_regime": "short_term_dislocation_repair"},
                "validation_focus": "target_plus_representative",
            },
            "hypothesis_lowering_audit": {
                "source": "external_llm",
                "target_symbols": ["603855"],
            },
            "holding_horizon": {"min_days": 2, "max_days": 8},
            "trade_plan": {"entry_bias": "oversold_repair"},
            "risk_rules": {"stop_loss_pct": 0.05, "max_holding_days": 8},
            "position_sizing": {"mode": "equal_weight"},
            "execution_notes": "focus on liquid names",
            "rebalance_rule": {"mode": "signal_rebalance", "frequency_days": 2},
            "portfolio_spec": {"target_weight_scheme": "single_name"},
            "execution_assumptions": {"slippage_bps": 5, "tradability_filter": True},
            "validation_profile": {"profile": "trade_rule_validation", "validation_focus": "target_plus_representative"},
        },
    )

    payload = await recorder.record_experiment(
        db,
        spec,
        source="test_component",
        snapshot={"date": "2026-04-09"},
        task_run={"id": 102},
    )

    assert payload["hypothesis"] == "超跌修复在一周内兑现。"
    assert payload["strategy_spec"]["hypothesis_artifact"]["artifact_id"] == "hyp_persisted"
    assert payload["strategy_spec"]["replay_contract"]["holding_horizon"]["max_days"] == 8
    assert payload["strategy_spec"]["replay_contract"]["execution_assumptions"]["slippage_bps"] == 5
    assert payload["evaluation"]["hypothesis_artifact"]["family_hint"] == "rsi"
    assert payload["evaluation"]["hypothesis_lowering_audit"]["source"] == "external_llm"


@pytest.mark.asyncio
async def test_experiment_recorder_persists_enveloped_semantic_contract_fields():
    recorder = ExperimentRecorder()
    db = MagicMock()
    db.save_strategy_generation_experiment = AsyncMock(side_effect=lambda payload: dict(payload))

    spec = StrategySpec(
        strategy_type="momentum",
        params={"lookback": 15},
        name="semantic-contract-persist",
        description="趋势延续候选",
        tags=["rule"],
        metadata={
            "generator_type": "rule",
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "research_task": {"task_id": "task_semantic_persist", "task_source": "snapshot", "target_symbols": ["600519"]},
            "holding_horizon": {"min_days": 5, "max_days": 15},
            "trade_plan": {
                "entry_bias": "trend_follow",
                "exit_bias": "signal_failure_or_time_stop",
                "entry": {"node_id": "entry_step_1", "claim_ids": ["claim_entry"]},
                "exit": {"node_id": "exit_step_1", "claim_ids": ["claim_exit"]},
            },
            "risk_rules": {"stop_loss_pct": 0.06, "take_profit_pct": 0.12, "max_holding_days": 15},
            "position_sizing": {"mode": "single_name"},
            "execution_assumptions": {"slippage_bps": 5, "tradability_filter": True, "slippage_model": "fixed"},
            "portfolio_spec": {"position_assumption": "single_name_full_notional", "target_weight_scheme": "single_name"},
            "validation_profile": {"profile": "trade_rule_validation", "validation_focus": "target_plus_representative"},
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev_1",
                        "source_type": "price_action",
                        "direction": "up",
                        "summary": "价格重新站上趋势均线。",
                    }
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_entry",
                        "expected_move": "up",
                        "expected_horizon": 10,
                        "evidence_ids": ["ev_1"],
                        "failure_condition": "trend_break",
                        "conflict_resolution_rule": {"policy": "risk_first"},
                    }
                ],
                "conflict_resolution_rule": {"policy": "risk_first"},
            },
            "confidence_contract": {
                "prediction_quality": {"support_samples": 24, "ece": 0.08, "brier_score": 0.17}
            },
        },
    )

    payload = await recorder.record_experiment(
        db,
        spec,
        source="test_component",
        snapshot={"date": "2026-04-14"},
        task_run={"id": 103},
    )

    assert payload["strategy_spec"]["candidate_contract_snapshot"]["strategy_type"] == "momentum"
    assert payload["strategy_spec"]["evidence_chain"]["evidences"][0]["evidence_id"] == "ev_1"
    assert payload["strategy_spec"]["prediction_contract"]["claims"][0]["claim_id"] == "claim_entry"
    assert payload["strategy_spec"]["confidence_contract"]["prediction_quality"]["support_samples"] == 24
    assert payload["evaluation"]["candidate_contract_snapshot"]["strategy_type"] == "momentum"
    assert payload["evaluation"]["confidence_contract"]["prediction_quality"]["support_samples"] == 24
    assert payload["candidate_contract_snapshot"]["strategy_type"] == "momentum"


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

    service.rule_generator.generate = lambda *_args, **_kwargs: RuleStrategyGenerator().generate(
        {
            "fear_greed_index": 58,
            "factor_research": {"preferred_strategy_types": ["momentum"]},
        },
        limit=1,
        preferred_types=["momentum"],
    )
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


def test_strategy_ai_mixin_large_task_run_result_falls_back_to_safe_summary(monkeypatch):
    monkeypatch.setenv("STRATEGY_TASK_RUN_RESULT_MAX_BYTES", "256")

    encoded = StrategyAIMixin._encode_task_run_result_json(
        {
            "task_run_id": 11,
            "status": "completed",
            "source": "test",
            "snapshot_date": "2026-04-06",
            "generated_count": 3,
            "full_result_artifact": {
                "artifact_id": "artifact_task_run_11",
                "path": "/tmp/task_run_11.json",
                "format": "json",
                "size_bytes": 8192,
            },
            "blob": "x" * 4096,
        }
    )

    decoded = json.loads(encoded)
    assert decoded["storage_mode"] == "inline_fallback_summary"
    assert decoded["truncated"] is True
    assert decoded["generated_count"] == 3
    assert decoded["full_result_artifact"]["artifact_id"] == "artifact_task_run_11"
    assert "blob" not in decoded


def test_strategy_ai_mixin_large_generation_experiment_field_falls_back_to_safe_summary(monkeypatch):
    monkeypatch.setenv("STRATEGY_GENERATION_EXPERIMENT_FIELD_MAX_BYTES", "256")

    encoded = StrategyAIMixin._encode_generation_experiment_json(
        "evaluation",
        {
            "source": "strategy_factory_submit",
            "task_run_id": 77,
            "committee_review": {
                "decision": "accept",
                "final_score": 0.91,
                "rank": 1,
            },
            "submission_result": {
                "passed": True,
                "strategy_id": "sid_123",
            },
            "blob": "x" * 4096,
        },
    )

    decoded = json.loads(encoded)
    assert decoded["storage_mode"] == "inline_fallback_summary"
    assert decoded["field_name"] == "evaluation"
    assert decoded["task_run_id"] == 77
    assert decoded["committee_review"]["decision"] == "accept"
    assert decoded["submission_result"]["strategy_id"] == "sid_123"
    assert "blob" not in decoded


def test_strategy_ai_mixin_large_factory_run_stages_compact_inline_before_field_fallback(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_RUN_STAGES_MAX_BYTES", "32768")

    encoded = StrategyAIMixin._encode_factory_run_json(
        "stages",
        {
            "autonomy": {
                "stage": "autonomy",
                "status": "partial",
                "ok": True,
                "task_count": 139,
                "completed_task_count": 137,
                "failed_task_count": 2,
                "generated_count": 139,
                "external_llm_status": "partial",
                "task_source_counts": {"snapshot": 12, "event_driven": 27, "bulk_stock_matrix": 100},
                "task_scan": {
                    "summary": {
                        "task_count": 139,
                        "task_sources": {"snapshot": 12, "event_driven": 27, "bulk_stock_matrix": 100},
                        "bulk_stock_matrix_enabled": True,
                        "bulk_stock_matrix_stock_count": 100,
                    },
                    "tasks": [{"task_id": f"task_{idx}", "blob": "x" * 1024} for idx in range(80)],
                },
                "task_results": [
                    {
                        "task_run_id": idx,
                        "status": "completed",
                        "generated_count": 1,
                        "reviewed_count": 1,
                        "external_llm_status": "succeeded",
                        "task": {
                            "task_id": f"task_{idx}",
                            "task_source": "bulk_stock_matrix",
                            "opportunity_type": "momentum",
                            "target_symbols": ["600000", "600036"],
                            "generation_limit": 1,
                        },
                        "lifecycle_summary": {
                            "state": "completed",
                            "current_phase": "completed",
                            "terminal_phase": "completed",
                            "phase_status_counts": {"completed": 6},
                        },
                        "blob": "x" * 1024,
                    }
                    for idx in range(60)
                ],
                "task_artifact": {
                    "contract_version": "strategy_factory.task_artifact.v1",
                    "available": True,
                    "planned_task_count": 80,
                    "executed_task_count": 60,
                    "generated_candidate_count": 16,
                    "task_source_counts": {"bulk_stock_matrix": 80},
                    "planned_task_briefs": [
                        {"task_id": f"task_{idx}", "task_source": "bulk_stock_matrix", "generation_limit": 1}
                        for idx in range(12)
                    ],
                },
                "candidate_artifact": {
                    "contract_version": "strategy_factory.candidate_artifact.v1",
                    "available": True,
                    "candidate_count": 16,
                    "candidate_contract_ready_count": 16,
                    "candidate_evidence_ready_count": 16,
                    "candidate_origin_counts": {"external_autonomy": 13, "governed_candidate_activation": 3},
                    "candidate_briefs": [
                        {
                            "name": f"candidate_{idx}",
                            "strategy_type": "momentum",
                            "candidate_contract_ready": True,
                            "evidence_ready": True,
                            "experiment_id": f"exp_{idx}",
                        }
                        for idx in range(16)
                    ],
                },
                "evidence_artifact": {
                    "contract_version": "strategy_factory.research_evidence_artifact.v1",
                    "available": True,
                    "experiment_count": 16,
                    "task_run_count": 60,
                    "task_run_ids": [f"task_run_{idx}" for idx in range(16)],
                    "task_result_status_counts": {"completed": 60},
                    "experiment_briefs": [
                        {
                            "artifact_id": f"exp_{idx}",
                            "generator_type": "rule",
                            "candidate_contract_ready": True,
                            "evidence_ready": True,
                        }
                        for idx in range(16)
                    ],
                },
                "blob": "x" * 8192,
            }
        },
    )

    decoded = json.loads(encoded)
    assert "storage_mode" not in decoded
    assert decoded["autonomy"]["storage_mode"] == "inline_compact_stage"
    assert decoded["autonomy"]["stage"] == "autonomy"
    assert decoded["autonomy"]["task_count"] == 139
    assert decoded["autonomy"]["task_result_count"] == 60
    assert decoded["autonomy"]["task_scan"]["summary"]["bulk_stock_matrix_enabled"] is True
    assert decoded["autonomy"]["task_results"][0]["task"]["task_id"] == "task_0"
    assert decoded["autonomy"]["task_artifact"]["contract_version"] == "strategy_factory.task_artifact.v1"
    assert decoded["autonomy"]["task_artifact"]["planned_task_count"] == 80
    assert decoded["autonomy"]["candidate_artifact"]["contract_version"] == "strategy_factory.candidate_artifact.v1"
    assert decoded["autonomy"]["candidate_artifact"]["candidate_count"] == 16
    assert decoded["autonomy"]["candidate_artifact"]["candidate_contract_ready_count"] == 16
    assert decoded["autonomy"]["candidate_artifact"]["candidate_briefs"][0]["experiment_id"] == "exp_0"
    assert decoded["autonomy"]["evidence_artifact"]["contract_version"] == "strategy_factory.research_evidence_artifact.v1"
    assert decoded["autonomy"]["evidence_artifact"]["experiment_count"] == 16
    assert decoded["autonomy"]["evidence_artifact"]["task_run_count"] == 60
    assert decoded["autonomy"]["truncated"] is True
    assert decoded["autonomy"]["original_size_bytes"] > 32768
    assert "blob" not in decoded["autonomy"]


def test_strategy_ai_mixin_large_factory_run_stages_preserve_small_stage_payloads(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_RUN_STAGES_MAX_BYTES", "12288")

    encoded = StrategyAIMixin._encode_factory_run_json(
        "stages",
        {
            "collect": {
                "stage": "collect",
                "status": "completed",
                "ok": True,
                "fear_greed": 61,
                "listed_count": 12,
            },
            "quality_gate": {
                "stage": "quality_gate",
                "status": "completed",
                "ok": True,
                "gate_0": {
                    "passed_count": 120,
                    "failed_count": 18,
                    "passed": [{"name": f"passed_{idx}", "blob": "x" * 512} for idx in range(64)],
                },
                "gate_2": {
                    "input_count": 42,
                    "passed_count": 11,
                    "failed_count": 31,
                    "report": {
                        "summary": {"failed_reason_counts": {"sharpe_below_threshold": 31}},
                        "failed": [{"name": f"failed_{idx}", "blob": "x" * 512} for idx in range(48)],
                    },
                },
            },
        },
    )

    decoded = json.loads(encoded)
    assert decoded["collect"]["stage"] == "collect"
    assert decoded["collect"]["fear_greed"] == 61
    assert decoded["quality_gate"]["storage_mode"] == "inline_compact_stage"
    assert decoded["quality_gate"]["truncated"] is True
    assert decoded["quality_gate"]["original_size_bytes"] > 12288


def test_strategy_ai_mixin_large_factory_run_snapshot_summary_falls_back_to_safe_summary(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_RUN_SNAPSHOT_SUMMARY_MAX_BYTES", "1024")

    encoded = StrategyAIMixin._encode_factory_run_json(
        "snapshot_summary",
        {
            "date": "2026-04-06",
            "fear_greed": 61,
            "listed_count": 120,
            "incubating_count": 8,
            "degraded": False,
            "completion_ratio": 0.98,
            "factor_research": {
                "summary": {
                    "factor_source_mode": "governed_candidate_pool",
                    "governed_candidate_pool_mode": "strict_governed",
                    "active_candidate_count": 24,
                    "governed_source_candidate_count": 18,
                },
                "active_candidate_pool": {
                    "count": 24,
                    "family_count": 5,
                    "top_candidates": [
                        {"name": "value_momentum_blend", "family": "momentum", "priority": 0.9, "score": 0.87},
                        {"name": "quality_breakout", "family": "quality", "priority": 0.8, "score": 0.81},
                    ],
                },
                "source_chain": ["governed_pool", "scheduler"],
                "degraded": False,
                "blob": "x" * 4096,
            },
        },
    )

    decoded = json.loads(encoded)
    assert decoded["storage_mode"] == "inline_fallback_summary"
    assert decoded["field_name"] == "snapshot_summary"
    assert decoded["date"] == "2026-04-06"
    assert decoded["factor_research"]["summary"]["factor_source_mode"] == "governed_candidate_pool"
    assert decoded["factor_research"]["active_candidate_pool"]["top_candidates"][0]["name"] == "value_momentum_blend"
    assert "blob" not in decoded["factor_research"]


@pytest.mark.asyncio
async def test_candidate_generation_service_select_parents_tolerates_db_failures():
    service = CandidateGenerationService()
    db = MagicMock()
    db.list_strategies = AsyncMock(side_effect=ConnectionRefusedError("db offline"))

    parents = await service.select_parents(db)

    assert parents == []
    assert db.list_strategies.await_count == 2
