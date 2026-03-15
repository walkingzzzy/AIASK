from unittest.mock import AsyncMock, MagicMock

import pytest

from akshare_mcp.services.strategy_autonomy import StrategySpec
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
