from unittest.mock import AsyncMock, MagicMock

import pytest

import akshare_mcp.services.strategy_factory.utils as legacy_utils

from strategy_factory.application.deduplicator import Deduplicator


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
