from __future__ import annotations

import asyncio
from types import MethodType


def test_shadow_readonly_skips_paper_trading_cycle(monkeypatch) -> None:
    from strategy_factory.application.factory_execution import FactoryExecutionMode
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
    from strategy_factory.application.research import paper_trading_scheduler

    paper_calls = {"count": 0}

    async def _paper_cycle(_db):
        paper_calls["count"] += 1
        return {"status": "success"}

    monkeypatch.setattr(paper_trading_scheduler, "run_paper_trading_cycle", _paper_cycle)

    scheduler = StrategyFactoryScheduler()
    cycle_calls: list[dict] = []

    async def _cycle_once(
        self,
        resolved_db,
        *,
        previous_result,
        execution_mode,
        parity_role="primary",
        read_only=False,
        run_id=None,
        trace_id=None,
        target_codes=None,
    ):
        cycle_calls.append({"parity_role": parity_role, "read_only": read_only})
        return (
            {
                "run_id": run_id or "factory_run_primary",
                "trace_id": trace_id or "trace-primary",
                "status": "success",
                "summary": {},
                "artifacts": [],
            },
            [],
        )

    scheduler._execute_factory_cycle_once = MethodType(_cycle_once, scheduler)

    result, failures = asyncio.run(
        scheduler._execute_factory_run_once_mode(
            object(),
            previous_result=None,
            execution_mode=FactoryExecutionMode.SHADOW_READONLY,
        )
    )

    assert failures == []
    assert paper_calls["count"] == 0
    assert result["paper_trading_cycle"]["status"] == "skipped"
    assert result["paper_trading_cycle"]["reason"] == "shadow_readonly"
    assert cycle_calls == [
        {"parity_role": "primary", "read_only": False},
        {"parity_role": "shadow", "read_only": True},
    ]


class _DispatchDb:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    async def create_strategy_factory_dispatch(self, payload: dict) -> dict:
        row = dict(payload)
        self.rows[row["dispatch_id"]] = row
        return dict(row)

    async def update_strategy_factory_dispatch(self, dispatch_id: str, **kwargs):
        if dispatch_id not in self.rows:
            return None
        self.rows[dispatch_id].update(kwargs)
        return dict(self.rows[dispatch_id])

    async def get_strategy_factory_dispatch(self, dispatch_id: str):
        row = self.rows.get(dispatch_id)
        return dict(row) if row else None


def test_dispatch_run_persists_partial_status() -> None:
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

    scheduler = StrategyFactoryScheduler()
    db = _DispatchDb()

    async def _partial_run_once(self, db=None, *, execution_mode=None, dispatch_id=None, target_codes=None):
        return {
            "run_id": "factory_run_partial",
            "status": "partial",
            "parity_result": {"status": "matched"},
            "artifact_refs": [{"artifact_type": "research_plane"}],
        }

    scheduler.run_once = MethodType(_partial_run_once, scheduler)

    async def _run():
        accepted = await scheduler.dispatch_run(db=db)
        dispatch_id = accepted["dispatch_id"]
        task = scheduler._dispatch_tasks[dispatch_id]
        await task
        return await scheduler.get_dispatch_status(dispatch_id, db=db)

    status = asyncio.run(_run())

    assert status is not None
    assert status["status"] == "partial"
    assert status["run_id"] == "factory_run_partial"
    assert status["metadata"]["result_status"] == "partial"
    assert status["metadata"]["degraded"] is True
