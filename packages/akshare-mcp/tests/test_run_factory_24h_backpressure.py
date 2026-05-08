from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("run_factory_24h", ROOT / "run_factory_24h.py")
run_factory_24h = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(run_factory_24h)


class _SchedulerDb:
    def __init__(self, stats):
        self.stats = dict(stats)
        self.saved: list[dict] = []

    async def get_strategy_task_queue_stats(self, **kwargs):
        return dict(self.stats)

    async def save_strategy_task_run(self, payload):
        row = {"id": len(self.saved) + 1, **dict(payload)}
        self.saved.append(row)
        task_name = payload["task_name"]
        by_task = self.stats.setdefault("queue_depth_by_task", {})
        by_task.setdefault(task_name, {})["queued"] = int(by_task.setdefault(task_name, {}).get("queued") or 0) + 1
        return row


def test_schedule_cycle_applies_backpressure_and_skips_runtime_by_default():
    async def run():
        db = _SchedulerDb(
            {
                "queue_depth_by_task": {
                    "factory_dispatch_run": {"queued": 2, "running": 0},
                    "incubation_pipeline_run": {"queued": 0, "running": 0},
                    "runtime_cycle_run": {"queued": 0, "running": 0},
                }
            }
        )
        result = await run_factory_24h.schedule_cycle(
            db,
            cycle=1,
            queue_threshold=2,
            runtime_enqueue_mode="disabled",
        )
        saved_names = [item["task_name"] for item in db.saved]
        assert saved_names == ["incubation_pipeline_run"]
        skipped_reasons = {item["task_name"]: item["reason"] for item in result["skipped_due_to_backpressure"]}
        assert skipped_reasons["factory_dispatch_run"] == "backpressure"
        assert skipped_reasons["runtime_cycle_run"] == "runtime_enqueue_disabled"

    asyncio.run(run())


def test_schedule_cycle_only_enqueues_runtime_when_enabled_and_empty():
    async def run():
        db = _SchedulerDb(
            {
                "queue_depth_by_task": {
                    "factory_dispatch_run": {"queued": 0, "running": 0},
                    "incubation_pipeline_run": {"queued": 0, "running": 0},
                    "runtime_cycle_run": {"queued": 0, "running": 0},
                }
            }
        )
        await run_factory_24h.schedule_cycle(
            db,
            cycle=1,
            queue_threshold=2,
            runtime_enqueue_mode="enabled",
        )
        saved_names = [item["task_name"] for item in db.saved]
        assert saved_names == ["factory_dispatch_run", "incubation_pipeline_run", "runtime_cycle_run"]

    asyncio.run(run())
