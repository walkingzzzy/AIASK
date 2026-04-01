"""Scheduler handlers for quant_manager."""

from __future__ import annotations

from typing import Callable


async def handle_scheduler_status(*, ok: Callable[..., dict]) -> dict:
    from ...services.factor_scheduler import get_factor_scheduler

    scheduler = get_factor_scheduler()
    return ok(scheduler.status())


async def handle_scheduler_run_now(*, ok: Callable[..., dict]) -> dict:
    from ...services.factor_scheduler import get_factor_scheduler

    scheduler = get_factor_scheduler()
    result = await scheduler.run_once()
    return ok(result or {"message": "run completed"})
