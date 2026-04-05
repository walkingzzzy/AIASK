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
    assert allocation["300001"]["priority"] > allocation["600001"]["priority"]
    assert artifact["summary"]["stock_family_allocation_count"] == 2
    assert artifact["summary"]["stock_family_allocation_source_mode"] == "stock_universe_projection"
    assert artifact["summary"]["stock_family_allocation_entropy"] > 0.0


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
