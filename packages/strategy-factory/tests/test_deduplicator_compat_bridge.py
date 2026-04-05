from unittest.mock import AsyncMock, MagicMock

import pytest

import akshare_mcp.services.strategy_factory.utils as legacy_utils

from strategy_factory.application.deduplicator import Deduplicator
from strategy_factory.domain.strategy_profile import apply_candidate_strategy_profile


def test_deduplicator_uses_legacy_extract_event_context_patch_point(monkeypatch):
    monkeypatch.setattr(
        legacy_utils,
        "_extract_event_context",
        lambda _task, limit=5: {"event_id": "evt-1", "theme_code": "ai", "target_symbols": ["600519"][:limit]},
    )

    should_refresh = Deduplicator._should_refresh_existing(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "target_symbols": ["600519"],
            "research_task": {"task_source": "event_driven"},
        },
        {"matched_status": "listed", "matched_strategy_id": "stg-1"},
    )

    assert should_refresh is True


def test_deduplicator_refreshes_same_parent_strategy_without_event_context():
    should_refresh = Deduplicator._should_refresh_existing(
        {
            "strategy_type": "momentum",
            "params": {"lookback": 20},
            "parent_strategy_id": "stg-1",
        },
        {"matched_status": "incubating", "matched_strategy_id": "stg-1"},
    )

    assert should_refresh is True


def test_param_similarity_penalizes_missing_keys():
    similarity = Deduplicator._param_sim(
        {"lookback": 20, "threshold": 0.05},
        {"lookback": 20},
    )

    assert similarity == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_deduplicator_keeps_targeted_candidate_when_universe_only_partially_overlaps():
    dedup = Deduplicator()
    candidates = [
        {
            "strategy_type": "dsl_rule",
            "generator_type": "pipeline_staged",
            "params": {
                "dsl": {
                    "entry": {"all": []},
                    "exit": {"any": []},
                    "metadata": {"target_symbols": ["601398", "601288", "601939", "601988", "600036", "601166", "600000"]},
                }
            },
            "target_symbols": ["601398", "601288", "601939", "601988", "600036", "601166", "600000"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288", "601939", "601988", "600036", "601166", "600000"]},
            "research_task": {"task_source": "event_driven", "task_id": "evt_bank"},
        },
    ]
    existing = [
        {
            "id": "sid_existing_dsl",
            "name": "dsl_rule策略",
            "status": "incubating",
            "strategy_type": "dsl_rule",
            "params": {
                "dsl": {
                    "entry": {"all": []},
                    "exit": {"any": []},
                    "metadata": {"target_symbols": ["601398", "601288", "600036", "601166", "600000"]},
                }
            },
            "target_symbols": ["601398", "601288", "600036", "601166", "600000"],
        },
    ]
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=existing)

    unique = await dedup.deduplicate(candidates, db)

    assert len(unique) == 1
    assert unique[0]["dedup_result"]["duplicate"] is False
    assert unique[0]["dedup_result"]["refresh_existing"] is False
    assert unique[0]["dedup_result"]["target_overlap"] == 0.7143


@pytest.mark.asyncio
async def test_deduplicator_report_includes_strategy_profile_fields():
    dedup = Deduplicator()
    candidates = [
        apply_candidate_strategy_profile(
            {
                "strategy_type": "momentum",
                "candidate_family": "trend",
                "holding_period_bucket": "short",
                "alpha_source": "technical",
                "risk_level": "high",
                "regime_fit": "trend_expansion",
                "generator_mode": "bulk_stock_matrix",
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "params": {"lookback": 20, "threshold": 0.02},
            }
        )
    ]
    db = MagicMock()
    db.list_strategies = AsyncMock(side_effect=[[], []])

    unique = await dedup.deduplicate(candidates, db)

    assert len(unique) == 1
    kept = dedup.get_last_report()["kept"][0]
    assert kept["strategy_profile"]["candidate_family_id"] == "trend_short_technical_1"
    assert kept["holding_period_bucket"] == "short"
    assert kept["alpha_source"] == "technical"
    assert kept["risk_level"] == "high"
    assert kept["regime_fit"] == "trend_expansion"
    assert kept["generator_mode"] == "bulk_stock_matrix"


@pytest.mark.asyncio
async def test_deduplicator_spawns_revision_for_same_task_signature_with_expanded_target_universe():
    dedup = Deduplicator()
    candidate = {
        "strategy_type": "volatility_breakout",
        "params": {"lookback": 20, "threshold": 0.03},
        "target_symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598", "300439"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598", "300439"]},
        "research_task": {
            "task_source": "event_driven",
            "task_id": "evt_cycle_breakout",
            "event_id": "evt_cycle_breakout",
            "theme_code": "cycle_breakout",
            "target_symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598", "300439"],
        },
        "event_context": {
            "event_id": "evt_cycle_breakout",
            "theme_code": "cycle_breakout",
            "target_symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598", "300439"],
        },
    }
    existing = [
        {
            "id": "sid_cycle_existing",
            "name": "周期股波动突破",
            "status": "listed",
            "strategy_type": "volatility_breakout",
            "params": {"lookback": 20, "threshold": 0.03},
            "target_symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598"],
            "research_task": {
                "task_source": "event_driven",
                "task_id": "evt_cycle_breakout",
                "event_id": "evt_cycle_breakout",
                "theme_code": "cycle_breakout",
                "target_symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598"],
            },
            "event_context": {
                "event_id": "evt_cycle_breakout",
                "theme_code": "cycle_breakout",
                "target_symbols": ["601666", "601825", "600000", "601117", "600027", "600035", "601598"],
            },
        }
    ]
    db = MagicMock()
    db.list_strategies = AsyncMock(return_value=existing)

    unique = await dedup.deduplicate([candidate], db)

    assert len(unique) == 1
    detail = unique[0]["dedup_result"]
    assert detail["duplicate"] is False
    assert detail["refresh_existing"] is False
    assert detail["refresh_mode"] == "spawn_revision_from_existing"
    assert detail["parent_strategy_id"] == "sid_cycle_existing"
