from __future__ import annotations

from types import SimpleNamespace

import pytest

from akshare_mcp.services.strategy_autonomy_components import CandidateGenerationService
from akshare_mcp.services.strategy_spec import StrategySpec


class _RuleGenerator:
    def generate(self, snapshot, *, limit=1, preferred_types=None):
        strategy_type = list(preferred_types or ["multi_factor"])[0]
        return [
            StrategySpec(
                strategy_type=strategy_type,
                params={},
                name="empty-param-rule-spec",
                metadata={},
            )
        ]


class _LLMGenerator:
    async def generate(self, *args, **kwargs):
        return []

    def get_last_report(self):
        return {}


class _Optimizer:
    async def evolve(self, *args, **kwargs):
        return []


class _MultiTypeRuleGenerator:
    def generate(self, snapshot, *, limit=1, preferred_types=None):
        return [
            StrategySpec(
                strategy_type=strategy_type,
                params={},
                name=f"{strategy_type}-spec-{idx}",
                metadata={"target_symbols": [f"6000{idx:02d}"]},
            )
            for idx, strategy_type in enumerate(
                ["momentum", "ma_cross", "rsi", "value_factor", "quality_factor"],
                1,
            )
        ]


@pytest.mark.asyncio
async def test_candidate_generation_materializes_merged_specs_before_review(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_LLM_ENABLED", "0")
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_OPTIMIZER_ENABLED", "0")
    service = CandidateGenerationService(
        rule_generator=_RuleGenerator(),
        llm_generator=_LLMGenerator(),
        optimizer=_Optimizer(),
    )

    result = await service.generate(
        SimpleNamespace(),
        snapshot={"date": "2026-05-06"},
        limit=2,
        research_task={
            "task_id": "bulk-1",
            "task_source": "bulk_stock_matrix",
            "preferred_strategy_types": ["multi_factor"],
            "target_symbols": ["600519", "000858"],
        },
    )

    merged = list(result["merged_specs"])
    assert len(merged) == 2
    hashes = set()
    for spec in merged:
        params = dict(spec.params or {})
        assert params["signal_rule"]
        assert params["strategy_instance_hash"]
        assert params["tested_object_hash"]
        assert params["candidate_contract_hash"] == params["strategy_instance_hash"]
        assert params["param_materialization_version"]
        assert spec.metadata["strategy_instance_hash"] == params["strategy_instance_hash"]
        hashes.add(params["strategy_instance_hash"])
    assert len(hashes) == 2


@pytest.mark.asyncio
async def test_candidate_generation_ranks_pool_for_type_coverage_before_limit(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_LLM_ENABLED", "0")
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_OPTIMIZER_ENABLED", "0")
    service = CandidateGenerationService(
        rule_generator=_MultiTypeRuleGenerator(),
        llm_generator=_LLMGenerator(),
        optimizer=_Optimizer(),
    )

    result = await service.generate(
        SimpleNamespace(),
        snapshot={"date": "2026-05-06"},
        limit=3,
        research_task={},
    )

    pool_types = {spec.strategy_type for spec in result["candidate_pool_specs"]}
    selected_types = [spec.strategy_type for spec in result["merged_specs"]]
    assert len(pool_types) >= 5
    assert len(selected_types) == 3
    assert len(set(selected_types)) == 3


@pytest.mark.asyncio
async def test_candidate_generation_preserves_existing_params_and_adds_signal_rule(monkeypatch):
    class MomentumRuleGenerator:
        def generate(self, snapshot, *, limit=1, preferred_types=None):
            return [
                StrategySpec(
                    strategy_type="momentum",
                    params={"lookback": 42, "threshold": 0.01},
                    name="momentum-with-core-fields",
                )
            ]

    monkeypatch.setenv("STRATEGY_FACTORY_BULK_LLM_ENABLED", "0")
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_OPTIMIZER_ENABLED", "0")
    service = CandidateGenerationService(
        rule_generator=MomentumRuleGenerator(),
        llm_generator=_LLMGenerator(),
        optimizer=_Optimizer(),
    )

    result = await service.generate(
        SimpleNamespace(),
        snapshot={"date": "2026-05-06"},
        limit=2,
        research_task={},
    )

    params = dict(result["merged_specs"][0].params or {})
    assert 5 <= params["lookback"] <= 80
    assert params["lookback_days"] == params["lookback"]
    assert 0.006 <= params["threshold"] <= 0.08
    assert params["threshold_pct"] == params["threshold"]
    assert str(params["lookback"]) in params["signal_rule"]
    assert str(params["threshold"]) in params["signal_rule"]


@pytest.mark.asyncio
async def test_candidate_generation_variants_template_params_by_slot(monkeypatch):
    class MarginRuleGenerator:
        def generate(self, snapshot, *, limit=1, preferred_types=None):
            return [
                StrategySpec(
                    strategy_type="margin_divergence",
                    params={"lookback": 12, "rebound_window": 3, "repair_rebound_pct": 0.012, "signal_rule": "stale_rule"},
                    name="margin-template",
                    metadata={},
                )
            ]

    monkeypatch.setenv("STRATEGY_FACTORY_BULK_LLM_ENABLED", "0")
    monkeypatch.setenv("STRATEGY_FACTORY_BULK_OPTIMIZER_ENABLED", "0")
    service = CandidateGenerationService(
        rule_generator=MarginRuleGenerator(),
        llm_generator=_LLMGenerator(),
        optimizer=_Optimizer(),
    )

    result = await service.generate(
        SimpleNamespace(),
        snapshot={"date": "2026-05-06"},
        limit=3,
        research_task={
            "task_id": "bulk-margin",
            "task_source": "bulk_stock_matrix",
            "preferred_strategy_types": ["margin_divergence"],
            "target_symbols": ["600905", "600930", "601985"],
        },
    )

    params_list = [dict(spec.params or {}) for spec in result["merged_specs"]]
    hashes = {params["strategy_instance_hash"] for params in params_list}

    assert len(params_list) == 3
    assert len(hashes) == 3
    assert all(params["signal_rule"] != "stale_rule" for params in params_list)
