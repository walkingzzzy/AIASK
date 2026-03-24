from __future__ import annotations

import asyncio

from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


def test_strategy_factory_scheduler_shutdown_drains_task() -> None:
    async def scenario() -> None:
        scheduler = StrategyFactoryScheduler()
        scheduler.start()
        await asyncio.sleep(0)
        await scheduler.shutdown()
        assert scheduler._task is None
        assert scheduler._running is False

    asyncio.run(scenario())
