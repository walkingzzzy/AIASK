from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import strategy_factory.application._factory_scheduler_loop as loop_mod
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


class _FakeScanner:
    def __init__(self, tasks: list[dict]):
        self._tasks = list(tasks)

    async def scan(self, _db, _snapshot):
        return {
            "tasks": list(self._tasks),
            "summary": {
                "task_sources": self._build_task_source_counts(self._tasks),
                "event_task_count": 0,
            },
        }

    @staticmethod
    def _task_key(task: dict) -> str:
        return str(task.get("task_id") or task.get("task_key") or "").strip()

    @classmethod
    def _deduplicate_tasks(cls, tasks: list[dict]) -> list[dict]:
        unique: list[dict] = []
        seen: set[str] = set()
        for task in list(tasks or []):
            key = cls._task_key(task)
            if key in seen:
                continue
            seen.add(key)
            unique.append(dict(task))
        return unique

    @staticmethod
    def _task_sort_key(task: dict):
        return float(task.get("priority") or 0.0)

    @staticmethod
    def _build_task_source_counts(tasks: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in list(tasks or []):
            source = str(task.get("task_source") or "unknown").strip() or "unknown"
            counts[source] = counts.get(source, 0) + 1
        return counts


def _fake_cycle(task: dict, *, status: str = "succeeded") -> dict:
    target_symbols = list(task.get("target_symbols") or [])
    return {
        "generated_count": 1,
        "reviewed_count": 1,
        "candidates": [
            {
                "strategy_type": "ma_cross",
                "name": f"candidate_{task.get('task_id')}",
                "params": {"short_period": 5, "long_period": 20},
                "target_symbols": target_symbols,
                "metadata": {"target_symbols": target_symbols},
                "tags": [],
            }
        ],
        "experiment_records": [],
        "llm_generation": {
            "external_provider": {
                "status": status,
                "requests": [],
                "selected_count": 1,
                "elapsed_seconds": 0.01,
            }
        },
        "lifecycle": {
            "state": "completed",
            "current_phase": "completed",
            "failed_phase": None,
            "terminal_phase": "completed",
            "phase_status_counts": {"completed": 1},
            "completed_phase_count": 1,
            "event_count": 0,
            "phase_order": ["generating", "completed"],
        },
    }


async def _fake_call_optional(_target, _method_name, *_args, default=None, **_kwargs):
    return default


@pytest.mark.asyncio
async def test_run_autonomy_batches_caps_bulk_tasks_after_merge(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": f"snapshot_{idx}",
            "task_key": f"snapshot_{idx}",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": [f"600{idx:03d}"],
            "priority": 100 - idx,
        }
        for idx in range(8)
    ]
    bulk_tasks = [
        {
            "task_id": f"bulk_{idx}",
            "task_key": f"bulk_{idx}",
            "task_source": "bulk_stock_matrix",
            "opportunity_type": "stock_strategy_matrix",
            "target_symbols": [f"300{idx:03d}"],
            "generation_limit": 1,
            "priority": 1000 - idx,
        }
        for idx in range(30)
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()

    call_task_ids: list[str] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        assert limit >= 1
        assert source.startswith("strategy_factory:")
        task = dict(research_task or {})
        call_task_ids.append(str(task.get("task_id")))
        return _fake_cycle(task)

    fake_autonomy.generate_factory_candidates = _generate_factory_candidates

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.get_strategy_factory_package",
        lambda: factory_pkg,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop._call_optional_async",
        _fake_call_optional,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.StockStrategyMatrixPlanner.plan",
        AsyncMock(
            return_value={
                "summary": {
                    "enabled": True,
                    "task_count": len(bulk_tasks),
                    "eligible_stock_count": len(bulk_tasks),
                    "effective_task_budget": len(bulk_tasks),
                    "estimated_candidate_count": len(bulk_tasks),
                },
                "tasks": bulk_tasks,
            }
        ),
    )
    monkeypatch.setattr(scheduler, "_get_autonomy_gateway", lambda: fake_autonomy)
    monkeypatch.setattr(
        scheduler,
        "_resolve_bulk_stock_matrix_cursor",
        AsyncMock(return_value={"next_universe_offset": 0, "source": "default", "resume_from_run_id": None}),
    )
    monkeypatch.setattr(
        scheduler,
        "_bulk_stock_matrix_run_window_state",
        lambda _now: {
            "run_window_active": True,
            "configured_enabled": True,
            "run_window": "off_hours",
            "current_period": "off_hours",
            "skip_reason": None,
        },
    )
    monkeypatch.setattr(scheduler, "_prepare_shared_generation_context", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, "_persist_task_evidence", AsyncMock(return_value=[]))

    result = await scheduler._run_autonomy_batches(SimpleNamespace(), {"date": "2026-04-03", "fear_greed_index": 45})

    stage = result["stage"]
    expected_scan_budget = loop_mod.AUTONOMY_MAX_RESEARCH_TASKS
    expected_bulk_budget = min(len(bulk_tasks), loop_mod.AUTONOMY_MAX_BULK_RESEARCH_TASKS)
    expected_scan_selected = min(len(scan_tasks), expected_scan_budget)
    expected_bulk_selected = expected_bulk_budget
    assert stage["task_count"] == expected_scan_selected + expected_bulk_selected
    assert stage["task_source_counts"] == {"snapshot": expected_scan_selected, "bulk_stock_matrix": expected_bulk_selected}
    assert stage["max_research_tasks"] == expected_scan_budget
    assert stage["max_bulk_research_tasks"] == expected_bulk_budget
    assert stage["combined_research_task_budget"] == expected_scan_budget + expected_bulk_budget
    assert stage["selected_scan_task_count"] == expected_scan_selected
    assert stage["selected_bulk_task_count"] == expected_bulk_selected
    assert stage["planned_bulk_task_count"] == len(bulk_tasks)
    assert stage["clipped_bulk_task_count"] == max(0, len(bulk_tasks) - expected_bulk_selected)
    assert len(call_task_ids) == expected_scan_selected + expected_bulk_selected
    assert {f"snapshot_{idx}" for idx in range(8)}.issubset(set(call_task_ids))


@pytest.mark.asyncio
async def test_run_autonomy_batches_marks_timed_out_task_as_failed(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": "slow_task",
            "task_key": "slow_task",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["600000"],
            "priority": 10,
        }
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()

    async def _slow_generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        await asyncio.sleep(0.05)
        return _fake_cycle(dict(research_task or {}), status="succeeded")

    fake_autonomy.generate_factory_candidates = _slow_generate_factory_candidates

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.get_strategy_factory_package",
        lambda: factory_pkg,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop._call_optional_async",
        _fake_call_optional,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.StockStrategyMatrixPlanner.plan",
        AsyncMock(return_value={"summary": {"enabled": False, "task_count": 0}, "tasks": []}),
    )
    monkeypatch.setattr(scheduler, "_get_autonomy_gateway", lambda: fake_autonomy)
    monkeypatch.setattr(
        scheduler,
        "_resolve_bulk_stock_matrix_cursor",
        AsyncMock(return_value={"next_universe_offset": 0, "source": "default", "resume_from_run_id": None}),
    )
    monkeypatch.setattr(
        scheduler,
        "_bulk_stock_matrix_run_window_state",
        lambda _now: {
            "run_window_active": False,
            "configured_enabled": False,
            "run_window": "off_hours",
            "current_period": "market_hours",
            "skip_reason": "outside_run_window",
        },
    )
    monkeypatch.setattr(scheduler, "_prepare_shared_generation_context", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, "_persist_task_evidence", AsyncMock(return_value=[]))
    monkeypatch.setattr(scheduler, "_resolve_research_task_timeout_sec", lambda: 0.01)

    result = await scheduler._run_autonomy_batches(SimpleNamespace(), {"date": "2026-04-03", "fear_greed_index": 45})

    stage = result["stage"]
    assert stage["completed_task_count"] == 0
    assert stage["failed_task_count"] == 1
    assert stage["external_llm_status"] == "failed"
    assert "timed out" in str(stage["task_results"][0]["error"])


@pytest.mark.asyncio
async def test_run_autonomy_batches_reserves_bulk_slots_when_scan_lane_is_oversubscribed(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": f"snapshot_{idx}",
            "task_key": f"snapshot_{idx}",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": [f"600{idx:03d}"],
            "priority": 500 - idx,
        }
        for idx in range(40)
    ]
    bulk_tasks = [
        {
            "task_id": f"bulk_{idx}",
            "task_key": f"bulk_{idx}",
            "task_source": "bulk_stock_matrix",
            "opportunity_type": "stock_strategy_matrix",
            "target_symbols": [f"300{idx:03d}"],
            "generation_limit": 1,
            "priority": 1000 - idx,
        }
        for idx in range(20)
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()
    call_task_ids: list[str] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        call_task_ids.append(str(task.get("task_id")))
        return _fake_cycle(task)

    fake_autonomy.generate_factory_candidates = _generate_factory_candidates

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.get_strategy_factory_package",
        lambda: factory_pkg,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop._call_optional_async",
        _fake_call_optional,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.StockStrategyMatrixPlanner.plan",
        AsyncMock(return_value={"summary": {"enabled": True, "task_count": len(bulk_tasks)}, "tasks": bulk_tasks}),
    )
    monkeypatch.setattr(scheduler, "_get_autonomy_gateway", lambda: fake_autonomy)
    monkeypatch.setattr(
        scheduler,
        "_resolve_bulk_stock_matrix_cursor",
        AsyncMock(return_value={"next_universe_offset": 0, "source": "default", "resume_from_run_id": None}),
    )
    monkeypatch.setattr(
        scheduler,
        "_bulk_stock_matrix_run_window_state",
        lambda _now: {
            "run_window_active": True,
            "configured_enabled": True,
            "run_window": "off_hours",
            "current_period": "off_hours",
            "skip_reason": None,
        },
    )
    monkeypatch.setattr(scheduler, "_prepare_shared_generation_context", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, "_persist_task_evidence", AsyncMock(return_value=[]))

    result = await scheduler._run_autonomy_batches(SimpleNamespace(), {"date": "2026-04-03", "fear_greed_index": 45})

    stage = result["stage"]
    expected_scan_budget = loop_mod.AUTONOMY_MAX_RESEARCH_TASKS
    expected_bulk_budget = min(len(bulk_tasks), loop_mod.AUTONOMY_MAX_BULK_RESEARCH_TASKS)
    assert stage["task_count"] == stage["selected_scan_task_count"] + stage["selected_bulk_task_count"]
    assert stage["max_research_tasks"] == expected_scan_budget
    assert stage["max_bulk_research_tasks"] == expected_bulk_budget
    assert stage["combined_research_task_budget"] == expected_scan_budget + expected_bulk_budget
    assert stage["reserved_bulk_task_budget"] == stage["max_bulk_research_tasks"]
    assert stage["selected_bulk_task_count"] == stage["planned_bulk_task_count"] == len(bulk_tasks)
    assert stage["selected_scan_task_count"] == expected_scan_budget
    assert stage["clipped_bulk_task_count"] == 0
    assert any(task_id.startswith("bulk_") for task_id in call_task_ids)


def test_resolve_bulk_research_task_concurrency_ignores_provider_limit_when_bulk_llm_disabled(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    monkeypatch.setattr(loop_mod, "RESEARCH_TASK_CONCURRENCY", 10)
    monkeypatch.setattr(loop_mod, "STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY", 8)

    fake_external_provider = SimpleNamespace(
        config=SimpleNamespace(max_concurrency=2),
        is_enabled=lambda: True,
    )
    fake_generation_service = SimpleNamespace(
        llm_generator=SimpleNamespace(external_provider=fake_external_provider),
        _bulk_llm_enabled=lambda: False,
    )
    fake_autonomy = SimpleNamespace(raw=SimpleNamespace(generation_service=fake_generation_service))

    assert scheduler._resolve_research_task_concurrency(fake_autonomy, has_bulk_tasks=False) == 2
    assert scheduler._resolve_bulk_research_task_concurrency(fake_autonomy, has_bulk_tasks=True) == 8


def test_resolve_bulk_research_task_concurrency_obeys_provider_limit_when_bulk_llm_enabled(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    monkeypatch.setattr(loop_mod, "RESEARCH_TASK_CONCURRENCY", 10)
    monkeypatch.setattr(loop_mod, "STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY", 8)

    fake_external_provider = SimpleNamespace(
        config=SimpleNamespace(max_concurrency=2),
        is_enabled=lambda: True,
    )
    fake_generation_service = SimpleNamespace(
        llm_generator=SimpleNamespace(external_provider=fake_external_provider),
        _bulk_llm_enabled=lambda: True,
    )
    fake_autonomy = SimpleNamespace(raw=SimpleNamespace(generation_service=fake_generation_service))

    assert scheduler._resolve_research_task_concurrency(fake_autonomy, has_bulk_tasks=True) == 2
    assert scheduler._resolve_bulk_research_task_concurrency(fake_autonomy, has_bulk_tasks=True) == 2
