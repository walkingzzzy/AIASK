import akshare_mcp.services.strategy_factory.utils as legacy_utils

from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


def test_factory_scheduler_uses_legacy_extract_event_context_patch_point(monkeypatch):
    monkeypatch.setattr(
        legacy_utils,
        "_extract_event_context",
        lambda _task, limit=5: {
            "event_id": "evt-1",
            "theme_code": "robotics",
            "target_symbols": ["600519"][:limit],
            "supporting_reasons": ["policy_tailwind"],
            "score_summary": {"avg_final_score": 0.82},
        },
    )

    items = StrategyFactoryScheduler._build_event_task_evidence_items({"task_key": "task-1"})

    assert items[0]["event_id"] == "evt-1"
    assert any(item["evidence_type"] == "target_symbol" for item in items)
