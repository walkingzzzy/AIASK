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
