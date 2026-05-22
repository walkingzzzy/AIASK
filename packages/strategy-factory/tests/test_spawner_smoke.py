"""Smoke tests for StrategySpawner."""

from __future__ import annotations


def test_spawner_instantiation():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    assert spawner is not None


def test_spawner_spawn_returns_list():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "fg_level": "neutral",
        "listed_count": 10,
        "incubating_count": 2,
        "factor_research": {},
        "event_driven": {},
        "sources": {},
    }
    candidates = spawner.spawn(snapshot)
    assert isinstance(candidates, list)


def test_spawner_spawn_with_factor_research():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 65,
        "fg_level": "greed",
        "listed_count": 15,
        "incubating_count": 3,
        "factor_research": {
            "summary": {
                "active_factor_count": 3,
                "top_factor_names": ["momentum", "value"],
                "preferred_strategy_types": ["momentum", "value_factor"],
            }
        },
        "event_driven": {},
        "sources": {},
    }
    candidates = spawner.spawn(snapshot)
    assert isinstance(candidates, list)
    # Should produce at least some candidates given factor research input
    for c in candidates:
        assert "strategy_type" in c
        assert "params" in c


def test_spawner_injects_factor_pool_candidates():
    from strategy_factory.domain.spawner import StrategySpawner

    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "fg_level": "neutral",
        "factor_research": {
            "factory_pool_payload": {
                "available": True,
                "factors": [
                    {
                        "factor_id": "factor-1",
                        "name": "value_quality_blend",
                        "family": "value",
                        "expression_dsl": "rank(pe_ttm) * -1 + rank(roe)",
                        "fitness": 1.2,
                        "admission_grade": "A",
                        "generation_engine": "rule_seed",
                    }
                ],
            }
        },
        "event_driven": {},
        "sources": {},
    }

    candidates = spawner.spawn(snapshot)
    factor_pool_candidates = [
        item for item in candidates if item.get("factor_pool_factor_id") == "factor-1"
    ]

    assert factor_pool_candidates
    assert factor_pool_candidates[0]["params"]["factor_pool_factor_id"] == "factor-1"
    assert factor_pool_candidates[0]["params"]["factor_dsl"] == "rank(pe_ttm) * -1 + rank(roe)"
    assert factor_pool_candidates[0]["params"]["fitness"] == 1.2
    assert factor_pool_candidates[0]["params"]["grade"] == "A"
    assert factor_pool_candidates[0]["params"]["engine"] == "rule_seed"
    assert factor_pool_candidates[0]["metadata"]["factor_pool_factor_id"] == "factor-1"
