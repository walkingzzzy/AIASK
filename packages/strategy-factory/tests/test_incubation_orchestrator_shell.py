from __future__ import annotations

import asyncio

from strategy_factory.runtime.incubation_orchestrator_shell import (
    build_once_cycle_plan,
    run_phase_plan,
)
from strategy_factory.runtime.incubation_phases import required_phase_names


def test_build_once_cycle_plan_includes_required_phases() -> None:
    plan = build_once_cycle_plan(dry_run=True)
    names = set(plan.names())
    for required in required_phase_names():
        assert required in names


def test_run_phase_plan_dry_run_does_not_call_handlers() -> None:
    called: list[str] = []

    async def intake() -> dict:
        called.append("intake")
        return {"success": True}

    plan = build_once_cycle_plan(dry_run=True)
    result = asyncio.run(run_phase_plan(plan, {"intake": intake}))
    assert result["success"] is True
    assert result["dry_run"] is True
    assert called == []
    assert any(item["name"] == "intake" and item["dry_run"] for item in result["results"])


def test_missing_required_handler_fails() -> None:
    plan = build_once_cycle_plan(dry_run=False)
    result = asyncio.run(run_phase_plan(plan, {}))
    assert result["success"] is False
    assert result["required_failed"]
