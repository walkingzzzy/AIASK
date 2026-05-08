from __future__ import annotations

import asyncio

import pytest

from akshare_mcp.workers import strategy_factory_worker as worker


class _TimeoutDb:
    def __init__(self):
        self.updates: list[dict] = []

    async def heartbeat_strategy_task_run(self, *args, **kwargs):
        return {}

    async def update_strategy_task_run(self, run_id: int, **payload):
        self.updates.append({"run_id": run_id, **payload})
        return {"id": run_id, **payload}


@pytest.mark.asyncio
async def test_worker_timeout_marks_retryable_and_clears_lease(monkeypatch):
    async def slow_execute(db, task_run):
        await asyncio.sleep(1.0)

    monkeypatch.setattr(worker, "_execute_task_run", slow_execute)
    monkeypatch.setattr(worker, "_timeout_seconds", lambda action: 0.01)

    db = _TimeoutDb()
    await worker._execute_with_timeout(
        db,
        {
            "id": 42,
            "task_name": "factory_dispatch_run",
            "attempt_count": 1,
            "max_attempts": 3,
            "payload": {"action": "factory_dispatch_run"},
        },
        worker_id="unit-worker",
    )

    assert db.updates
    update = db.updates[-1]
    assert update["status"] == "retryable_timeout"
    assert update["clear_lease"] is True
    assert update["result"]["retryable"] is True


@pytest.mark.asyncio
async def test_worker_timeout_marks_failed_after_max_attempts(monkeypatch):
    async def slow_execute(db, task_run):
        await asyncio.sleep(1.0)

    monkeypatch.setattr(worker, "_execute_task_run", slow_execute)
    monkeypatch.setattr(worker, "_timeout_seconds", lambda action: 0.01)

    db = _TimeoutDb()
    await worker._execute_with_timeout(
        db,
        {
            "id": 43,
            "task_name": "incubation_pipeline_run",
            "attempt_count": 3,
            "max_attempts": 3,
            "payload": {"action": "incubation_pipeline_run"},
        },
        worker_id="unit-worker",
    )

    update = db.updates[-1]
    assert update["status"] == "failed_timeout"
    assert update["result"]["retryable"] is False
