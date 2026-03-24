from __future__ import annotations

import asyncio

from akshare_mcp.services.data_sync_scheduler import DataSyncScheduler
from akshare_mcp.services.factor_scheduler import FactorScheduler


def test_factor_scheduler_shutdown_drains_task() -> None:
    async def scenario() -> None:
        scheduler = FactorScheduler()
        scheduler.start()
        await asyncio.sleep(0)
        await scheduler.shutdown()
        assert scheduler._task is None
        assert scheduler._running is False

    asyncio.run(scenario())


def test_data_sync_scheduler_shutdown_drains_all_tasks() -> None:
    async def scenario() -> None:
        scheduler = DataSyncScheduler(sync_on_startup=True)
        scheduler.start()
        await asyncio.sleep(0)
        await scheduler.shutdown()
        assert scheduler._task is None
        assert scheduler._startup_task is None
        assert scheduler._running is False

    asyncio.run(scenario())
