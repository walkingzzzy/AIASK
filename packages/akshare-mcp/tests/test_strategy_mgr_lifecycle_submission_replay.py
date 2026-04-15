from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from akshare_mcp.tools.managers import strategy_mgr_lifecycle as lifecycle_mod


@pytest.mark.asyncio
async def test_handle_submission_replay_rechecks_and_replays(monkeypatch):
    captured: dict[str, object] = {}

    class _Submitter:
        async def replay_existing_submission(self, strategy, snapshot, db, **kwargs):
            captured["strategy"] = strategy
            captured["snapshot"] = snapshot
            captured["db"] = db
            captured["kwargs"] = kwargs
            return {
                "strategy_id": strategy["id"],
                "name": strategy["name"],
                "status": "submitted",
                "submission_lane": "observe_incubation",
                "incubation_budget_track": "deferred_submission",
                "submission_action_trigger": "bootstrap_observe_from_deferred_budget",
                "paper_lane_ready": True,
                "live_review_ready": False,
                "gate": {"passed": True, "strict_incubation_ready": True},
                "quality_report": {"summary": {"validation_grade": "A"}},
            }

    class _DB:
        async def get_strategy(self, strategy_id: str):
            return {
                "id": strategy_id,
                "name": "待重放策略",
                "status": "submitted",
                "strategy_type": "momentum",
                "params": {"incubation_budget": {"track": "deferred_submission"}},
            }

    monkeypatch.setattr("strategy_factory.StrategySubmitter", lambda: _Submitter())
    monkeypatch.setattr(
        lifecycle_mod,
        "get_latest_quality_report",
        AsyncMock(return_value={"snapshot": {"date": "2026-04-13"}}),
    )
    monkeypatch.setattr(
        lifecycle_mod,
        "_build_recheck_quality_inputs",
        AsyncMock(
            return_value=(
                {"rating": {"grade": "A"}},
                {"var_percent": 0.11},
                {"sharpe_ratio": 1.2, "trades_count": 9},
            )
        ),
    )

    db = _DB()
    result = await lifecycle_mod.handle_submission_replay(db, {"strategy_id": "sid_replay_1"})

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["items"][0]["submission_lane"] == "observe_incubation"
    assert result["data"]["items"][0]["validation_grade"] == "A"
    assert captured["strategy"]["id"] == "sid_replay_1"
    assert captured["snapshot"]["date"] == "2026-04-13"
    assert captured["kwargs"]["validation_report"]["rating"]["grade"] == "A"
