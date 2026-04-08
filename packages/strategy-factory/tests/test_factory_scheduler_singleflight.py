from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from strategy_factory.application.cycle_runner import FactoryCycleOutcome
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


@pytest.mark.asyncio
async def test_run_once_joins_existing_inflight_execution(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    started = asyncio.Event()
    release = asyncio.Event()
    executed_run_ids: list[str] = []

    class _Runner:
        def __init__(self, owner, context):
            self.context = context

        async def run(self):
            executed_run_ids.append(self.context.run_id)
            started.set()
            await release.wait()
            return FactoryCycleOutcome(
                result={
                    "run_id": self.context.run_id,
                    "status": "success",
                    "summary": {},
                    "stages": {},
                },
                persistence_failures=[],
            )

    persist_mock = AsyncMock()

    monkeypatch.setattr("strategy_factory.application.factory_scheduler.FactoryCycleRunner", _Runner)
    monkeypatch.setattr(scheduler, "_attach_runtime_governance", lambda results, previous_result=None: None)
    monkeypatch.setattr(scheduler, "_persist_run_result", persist_mock)

    first = asyncio.create_task(scheduler.run_once(db=object()))
    await started.wait()
    second = asyncio.create_task(scheduler.run_once(db=object()))
    await asyncio.sleep(0)

    assert len(executed_run_ids) == 1

    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    assert first_result["run_id"] == second_result["run_id"] == executed_run_ids[0]
    assert persist_mock.await_count == 1
    assert scheduler._run_once_task is None
