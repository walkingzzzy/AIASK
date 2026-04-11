import asyncio
from unittest.mock import MagicMock

import pytest

import strategy_factory.application._factory_scheduler_loop as scheduler_loop_mod
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


@pytest.mark.asyncio
async def test_generate_for_research_task_respects_task_hard_cap(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    captured: dict = {}

    class _DummyAutonomy:
        async def generate_factory_candidates(self, db, snapshot, *, limit, research_task, source):
            captured.update({
                "db": db,
                "snapshot": snapshot,
                "limit": limit,
                "research_task": research_task,
                "source": source,
            })
            return {"generated_count": 0, "candidates": [], "experiments": []}

    monkeypatch.setattr(scheduler_loop_mod, "AUTONOMY_TASK_HARD_CAP", 6)

    await scheduler._generate_for_research_task(
        _DummyAutonomy(),
        MagicMock(),
        {"date": "2026-04-02"},
        {
            "task_id": "task_high_limit",
            "opportunity_type": "factor_acceleration",
            "generation_limit": 20,
        },
    )

    assert captured["limit"] == 6
    assert captured["source"] == "strategy_factory:factor_acceleration"


@pytest.mark.asyncio
async def test_generate_for_research_task_retries_with_local_fallback_after_timeout(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    calls: list[dict] = []

    class _DummyAutonomy:
        async def generate_factory_candidates(self, db, snapshot, *, limit, research_task, source):
            calls.append(
                {
                    "limit": limit,
                    "research_task": dict(research_task or {}),
                    "source": source,
                }
            )
            if not research_task.get("disable_external_llm"):
                await asyncio.sleep(0.05)
            return {
                "generated_count": 1,
                "candidates": [{"name": "local_fallback_candidate"}],
                "experiments": [],
            }

    monkeypatch.setattr(scheduler, "_resolve_research_task_timeout_sec", lambda: 0.01)

    result = await scheduler._generate_for_research_task(
        _DummyAutonomy(),
        MagicMock(),
        {"date": "2026-04-02"},
        {
            "task_id": "task_timeout_retry",
            "opportunity_type": "factor_acceleration",
            "generation_limit": 2,
        },
    )

    assert result["generated_count"] == 1
    assert len(calls) == 2
    assert calls[0]["research_task"].get("disable_external_llm") is not True
    assert calls[1]["research_task"]["disable_external_llm"] is True
    assert calls[1]["research_task"]["external_llm_skip_reason"] == "task_timeout_local_fallback"
    assert calls[1]["research_task"]["disable_pipeline_staged"] is True
    assert calls[1]["research_task"]["pipeline_staged_skip_reason"] == "task_timeout_local_fallback"
    assert calls[1]["research_task"]["task_timeout_local_fallback"] is True
