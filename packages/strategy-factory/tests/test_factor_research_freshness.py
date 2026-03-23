from unittest.mock import AsyncMock, MagicMock

import pytest

import strategy_factory.application.factor_research as factor_research_mod
from strategy_factory.application.factor_research import FactorResearchBuilder
from strategy_factory.application.opportunity import MarketOpportunityScanner
from strategy_factory.domain.spawner import StrategySpawner


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
            return {"running": False, "quality_flags": [], "last_run": None, "freshness_sec": 0}

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
                            "total_score": 81.0,
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
    assert "sentiment" in artifact["active_factors"]
    assert "momentum" in artifact["preferred_strategy_types"]


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
                            "grade": "A",
                            "recommendation": "promote",
                            "total_score": 84.0,
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
    assert candidate_task["validation_focus"] == "candidate_target_only"
    assert candidate_task["candidate_grade"] == "A"
