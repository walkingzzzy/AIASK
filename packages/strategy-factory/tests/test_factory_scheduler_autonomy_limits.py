from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import strategy_factory.application._factory_scheduler_loop as loop_mod
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
from strategy_factory.application.research_plane_contract import (
    CANDIDATE_ARTIFACT_CONTRACT_VERSION,
    RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    TASK_ARTIFACT_CONTRACT_VERSION,
)


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
async def test_run_autonomy_batches_emits_source_level_research_artifacts(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": "snapshot_1",
            "task_key": "snapshot_1",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "candidate_family": "momentum",
            "target_symbols": ["600001"],
            "priority": 10,
        }
    ]
    bulk_tasks = [
        {
            "task_id": "bulk_1",
            "task_key": "bulk_1",
            "task_source": "bulk_stock_matrix",
            "opportunity_type": "stock_strategy_matrix",
            "candidate_family": "value_factor",
            "target_symbols": ["300001"],
            "generation_limit": 1,
            "priority": 20,
        }
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        assert limit >= 1
        assert source.startswith("strategy_factory:")
        return _fake_cycle(dict(research_task or {}))

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
                    "task_count": 1,
                    "stock_count": 1,
                    "eligible_stock_count": 1,
                    "effective_task_budget": 1,
                    "estimated_candidate_count": 1,
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

    assert stage["scan_task_artifact"]["contract_version"] == TASK_ARTIFACT_CONTRACT_VERSION
    assert stage["scan_task_artifact"]["planned_task_count"] == 1
    assert stage["scan_task_artifact"]["task_source_counts"] == {"snapshot": 1}
    assert stage["bulk_task_artifact"]["contract_version"] == TASK_ARTIFACT_CONTRACT_VERSION
    assert stage["bulk_task_artifact"]["planned_task_count"] == 1
    assert stage["bulk_task_artifact"]["task_source_counts"] == {"bulk_stock_matrix": 1}
    assert stage["task_artifact"]["contract_version"] == TASK_ARTIFACT_CONTRACT_VERSION
    assert stage["task_artifact"]["planned_task_count"] == 2
    assert stage["task_artifact"]["executed_task_count"] == 2
    assert stage["task_artifact"]["task_source_counts"] == {"snapshot": 1, "bulk_stock_matrix": 1}
    assert stage["candidate_artifact"]["contract_version"] == CANDIDATE_ARTIFACT_CONTRACT_VERSION
    assert stage["candidate_artifact"]["candidate_count"] == 2
    assert stage["evidence_artifact"]["contract_version"] == RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION
    assert stage["evidence_artifact"]["task_result_status_counts"] == {"completed": 2}
    assert stage["evidence_artifact"]["experiment_count"] == 0
    assert stage["task_artifact_available"] is True
    assert stage["candidate_artifact_available"] is True
    assert stage["evidence_artifact_available"] is True


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


def test_scheduler_disables_external_llm_concurrency_when_provider_health_blocked(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    monkeypatch.setattr(loop_mod, "RESEARCH_TASK_CONCURRENCY", 10)
    monkeypatch.setattr(loop_mod, "STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY", 8)

    fake_external_provider = SimpleNamespace(
        config=SimpleNamespace(max_concurrency=2),
        is_enabled=lambda: True,
        get_health_snapshot=lambda: {
            "scheduler_should_disable": True,
            "scheduler_skip_reason": "empty_200_false_success_detected",
        },
    )
    fake_generation_service = SimpleNamespace(
        llm_generator=SimpleNamespace(external_provider=fake_external_provider),
        _bulk_llm_enabled=lambda: True,
    )
    fake_autonomy = SimpleNamespace(raw=SimpleNamespace(generation_service=fake_generation_service))

    assert scheduler._bulk_tasks_use_external_llm(fake_autonomy) is False
    assert scheduler._resolve_research_task_concurrency(fake_autonomy, has_bulk_tasks=True) == 10
    assert scheduler._resolve_bulk_research_task_concurrency(fake_autonomy, has_bulk_tasks=True) == 8


def test_merge_autonomy_tasks_preserves_scan_lane_and_interleaves_bulk_families():
    scan_tasks = [
        {
            "task_id": "scan_1",
            "task_key": "scan_1",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "priority": 1,
        }
    ]
    bulk_tasks = [
        {
            "task_id": "bulk_momentum_1",
            "task_key": "bulk_momentum_1",
            "task_source": "bulk_stock_matrix",
            "candidate_family": "momentum",
            "priority": 100,
        },
        {
            "task_id": "bulk_momentum_2",
            "task_key": "bulk_momentum_2",
            "task_source": "bulk_stock_matrix",
            "candidate_family": "momentum",
            "priority": 99,
        },
        {
            "task_id": "bulk_mean_reversion_1",
            "task_key": "bulk_mean_reversion_1",
            "task_source": "bulk_stock_matrix",
            "candidate_family": "mean_reversion",
            "priority": 98,
        },
        {
            "task_id": "bulk_mean_reversion_2",
            "task_key": "bulk_mean_reversion_2",
            "task_source": "bulk_stock_matrix",
            "candidate_family": "mean_reversion",
            "priority": 97,
        },
        {
            "task_id": "bulk_breakout_1",
            "task_key": "bulk_breakout_1",
            "task_source": "bulk_stock_matrix",
            "candidate_family": "breakout",
            "priority": 96,
        },
    ]

    merged_tasks, budget_meta = StrategyFactoryScheduler._merge_autonomy_tasks_with_budget(
        _FakeScanner(scan_tasks),
        scan_tasks,
        bulk_tasks,
    )

    assert [task["task_id"] for task in merged_tasks] == [
        "scan_1",
        "bulk_momentum_1",
        "bulk_mean_reversion_1",
        "bulk_breakout_1",
        "bulk_momentum_2",
        "bulk_mean_reversion_2",
    ]
    assert budget_meta["selected_scan_task_count"] == 1
    assert budget_meta["selected_bulk_task_count"] == 5


def test_aggregate_submission_audit_metrics_exposes_generator_mode_ratios():
    metrics = StrategyFactoryScheduler._aggregate_submission_audit_metrics(
        {
            "created_total": 1,
            "strategies": [
                {
                    "generator_type": "rl_bandit",
                    "created_total": False,
                    "refresh_mode": "refresh_metrics_only",
                    "tested_object_hash_changed": False,
                },
                {
                    "generator_type": "rl_bandit",
                    "created_total": True,
                    "refresh_mode": "spawn_revision_from_existing",
                    "tested_object_hash_changed": True,
                },
                {
                    "generator_type": "external_llm",
                    "created_total": False,
                    "refresh_mode": "refresh_metrics_only",
                    "tested_object_hash_changed": False,
                },
            ],
        }
    )

    assert metrics["refresh_absorption_ratio"] == 0.6667
    assert metrics["revision_creation_ratio"] == 1.0
    assert metrics["generator_mode_submission_metrics"]["rl_bandit"] == {
        "strategy_count": 2,
        "created_total_count": 1,
        "refresh_metrics_only_count": 1,
        "spawn_revision_from_existing_count": 1,
        "tested_object_hash_changed_count": 1,
        "refresh_absorption_ratio": 0.5,
        "revision_creation_ratio": 1.0,
    }
    assert metrics["generator_mode_submission_metrics"]["external_llm"] == {
        "strategy_count": 1,
        "created_total_count": 0,
        "refresh_metrics_only_count": 1,
        "spawn_revision_from_existing_count": 0,
        "tested_object_hash_changed_count": 0,
        "refresh_absorption_ratio": 1.0,
        "revision_creation_ratio": 0.0,
    }


@pytest.mark.asyncio
async def test_run_autonomy_batches_separates_network_requests_from_compatibility_skips(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": "task_real_request",
            "task_key": "task_real_request",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["600000"],
            "priority": 10,
        },
        {
            "task_id": "task_compat_skip",
            "task_key": "task_compat_skip",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["600519"],
            "priority": 9,
        },
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        task_id = str(task.get("task_id") or "")
        target_symbols = list(task.get("target_symbols") or [])
        if task_id == "task_compat_skip":
            requests = [
                {
                    "stage_id": "event_recognition",
                    "status": "compatibility_skip",
                    "request_metrics": {"attempt_count": 0},
                }
            ]
        else:
            requests = [
                {
                    "stage_id": "event_recognition",
                    "status": "fallback",
                    "request_metrics": {"attempt_count": 2},
                },
                {
                    "stage_id": "theme_propagation",
                    "status": "succeeded",
                    "request_metrics": {"attempt_count": 1},
                },
            ]
        return {
            "generated_count": 1,
            "reviewed_count": 1,
            "candidates": [
                {
                    "strategy_type": "ma_cross",
                    "name": f"candidate_{task_id}",
                    "params": {"short_period": 5, "long_period": 20},
                    "target_symbols": target_symbols,
                    "metadata": {"target_symbols": target_symbols},
                    "tags": [],
                }
            ],
            "experiment_records": [],
            "llm_generation": {
                "external_provider": {
                    "status": "fallback_only",
                    "requests": requests,
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

    result = await scheduler._run_autonomy_batches(SimpleNamespace(), {"date": "2026-04-03", "fear_greed_index": 45})

    stage = result["stage"]
    assert stage["external_llm_attempt_count"] == 3
    assert stage["external_llm_stage_attempt_count"] == 3
    assert stage["external_llm_network_request_count"] == 3
    assert stage["external_llm_real_request_count"] == 2
    assert stage["external_llm_compatibility_skip_count"] == 1
    assert stage["external_llm_cooldown_skip_count"] == 0
    assert stage["external_llm_compatibility_failure_count"] == 0
    assert stage["external_llm_compatibility_failure_ratio"] == 0.0
    assert stage["external_llm_effective_response_count"] == 1
    assert stage["external_llm_effective_response_ratio"] == 0.5
    assert stage["external_llm_empty_200_response_count"] == 0
    assert stage["external_llm_request_status_counts"] == {
        "fallback": 1,
        "succeeded": 1,
        "compatibility_skip": 1,
    }

    by_name = {
        str(item.get("name")): dict(item.get("params") or {})
        for item in result["candidates"]
    }
    assert by_name["candidate_task_real_request"]["task_stage_attempt_count"] == 2
    assert by_name["candidate_task_real_request"]["task_network_request_count"] == 3
    assert by_name["candidate_task_real_request"]["task_real_request_count"] == 2
    assert by_name["candidate_task_real_request"]["task_compatibility_skip_count"] == 0
    assert by_name["candidate_task_real_request"]["task_compatibility_failure_count"] == 0
    assert by_name["candidate_task_real_request"]["task_effective_response_count"] == 1
    assert by_name["candidate_task_real_request"]["task_effective_response_ratio"] == 0.5
    assert by_name["candidate_task_compat_skip"]["task_stage_attempt_count"] == 1
    assert by_name["candidate_task_compat_skip"]["task_network_request_count"] == 0
    assert by_name["candidate_task_compat_skip"]["task_real_request_count"] == 0
    assert by_name["candidate_task_compat_skip"]["task_compatibility_skip_count"] == 1
    assert by_name["candidate_task_compat_skip"]["task_compatibility_failure_count"] == 0
    assert by_name["candidate_task_compat_skip"]["task_empty_200_response_count"] == 0


@pytest.mark.asyncio
async def test_run_autonomy_batches_filters_feedback_blocked_tasks_and_cools_down_generation(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": "task_blocked",
            "task_key": "task_blocked",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "strategy_preferences": ["momentum"],
            "priority": 48,
            "generation_limit": 4,
        },
        {
            "task_id": "task_cooldown",
            "task_key": "task_cooldown",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["601318"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["601318"]},
            "strategy_preferences": ["quality_factor"],
            "priority": 52,
            "generation_limit": 4,
        },
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()
    called_tasks: list[dict] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        called_tasks.append(task)
        assert source.startswith("strategy_factory:")
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

    result = await scheduler._run_autonomy_batches(
        SimpleNamespace(),
        {
            "date": "2026-04-03",
            "fear_greed_index": 45,
            "factor_research": {
                "budget_feedback": {
                    "momentum": {
                        "target_pool_feedback": {
                            "explicit:600519": {
                                "paper_hit_ratio": 0.2,
                                "runtime_alert_pressure": 0.8,
                            }
                        }
                    },
                    "quality_factor": {
                        "target_pool_feedback": {
                            "explicit:601318": {
                                "paper_hit_ratio": 0.35,
                                "runtime_alert_pressure": 0.2,
                            }
                        }
                    },
                }
            },
        },
    )

    stage = result["stage"]
    assert stage["blocked_feedback_task_count"] == 1
    assert stage["planned_feedback_cooldown_task_count"] == 1
    assert stage["suppressed_target_pools"] == ["explicit:600519"]
    assert [task["task_id"] for task in called_tasks] == ["task_cooldown"]
    assert called_tasks[0]["generation_limit"] == 1
    assert called_tasks[0]["priority"] < 52


@pytest.mark.asyncio
async def test_run_autonomy_batches_relaxes_bulk_backlog_freeze_into_cooldown(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scanner = _FakeScanner([])
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()
    called_tasks: list[dict] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        called_tasks.append(task)
        assert source.startswith("strategy_factory:")
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
                "summary": {"enabled": True, "task_count": 1},
                "tasks": [
                    {
                        "task_id": "bulk_task_relaxed",
                        "task_key": "bulk_task_relaxed",
                        "task_source": "bulk_stock_matrix",
                        "opportunity_type": "stock_strategy_matrix",
                        "candidate_family": "multi_factor",
                        "target_symbols": ["600519"],
                        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                        "strategy_preferences": ["multi_factor"],
                        "priority": 62,
                        "generation_limit": 4,
                    }
                ],
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
            "run_window": "always",
            "current_period": "off_hours",
            "skip_reason": None,
        },
    )
    monkeypatch.setattr(scheduler, "_prepare_shared_generation_context", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, "_persist_task_evidence", AsyncMock(return_value=[]))

    result = await scheduler._run_autonomy_batches(
        SimpleNamespace(),
        {
            "date": "2026-04-03",
            "fear_greed_index": 45,
            "factor_research": {
                "budget_feedback": {
                    "multi_factor": {
                        "strategy_count": 6,
                        "zero_signal_ratio": 1.0,
                        "low_signal_ratio": 1.0,
                        "evidence_debt_ratio": 0.92,
                    }
                }
            },
        },
    )

    stage = result["stage"]
    assert stage["task_count"] == 1
    assert stage["planned_feedback_control_mode_counts"] == {"normal": 1}
    assert stage["planned_feedback_limited_task_count"] == 1
    assert stage["planned_feedback_relaxed_task_count"] == 1
    assert stage["blocked_feedback_task_count"] == 0
    assert [task["task_id"] for task in called_tasks] == ["bulk_task_relaxed"]
    assert called_tasks[0]["feedback_control_mode"] == "normal"
    assert called_tasks[0]["feedback_control_original_mode"] == "freeze"
    assert called_tasks[0]["feedback_control_relaxed_mode"] == "normal"
    assert called_tasks[0]["feedback_generation_limited"] is True
    assert called_tasks[0]["generation_limit"] == 1
    assert called_tasks[0]["priority"] < 62


@pytest.mark.asyncio
async def test_run_autonomy_batches_relaxes_snapshot_generator_mode_freeze_into_normal(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": "snapshot_task_relaxed",
            "task_key": "snapshot_task_relaxed",
            "task_source": "snapshot",
            "opportunity_type": "factor_acceleration",
            "strategy_preferences": ["momentum"],
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "priority": 58,
            "generation_limit": 4,
        }
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    fake_autonomy = SimpleNamespace()
    called_tasks: list[dict] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        called_tasks.append(task)
        assert source.startswith("strategy_factory:")
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
            "run_window": "always",
            "current_period": "market_hours",
            "skip_reason": "outside_run_window",
        },
    )
    monkeypatch.setattr(scheduler, "_prepare_shared_generation_context", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler, "_persist_task_evidence", AsyncMock(return_value=[]))

    result = await scheduler._run_autonomy_batches(
        SimpleNamespace(),
        {
            "date": "2026-04-03",
            "fear_greed_index": 45,
            "factor_research": {
                "budget_feedback": {
                    "momentum": {
                        "generator_mode_feedback": {
                            "rule": {
                                "strategy_count": 6,
                                "zero_signal_ratio": 1.0,
                                "low_signal_ratio": 1.0,
                                "forward_window_coverage_ratio": 0.0,
                                "promotion_ready_ratio": 0.0,
                                "promotion_review_coverage_ratio": 0.0,
                                "evidence_debt_ratio": 0.92,
                            }
                        }
                    }
                }
            },
        },
    )

    stage = result["stage"]
    assert stage["task_count"] == 1
    assert stage["planned_feedback_control_mode_counts"] == {"normal": 1}
    assert stage["planned_feedback_generator_mode_control_mode_counts"] == {"freeze": 1}
    assert stage["selected_feedback_control_mode_counts"] == {"normal": 1}
    assert stage["selected_feedback_generator_mode_control_mode_counts"] == {"freeze": 1}
    assert stage["planned_feedback_limited_task_count"] == 1
    assert stage["planned_feedback_relaxed_task_count"] == 1
    assert stage["blocked_feedback_task_count"] == 0
    assert [task["task_id"] for task in called_tasks] == ["snapshot_task_relaxed"]
    assert called_tasks[0]["generator_mode"] == "rule"
    assert called_tasks[0]["feedback_generator_mode_control_mode"] == "freeze"
    assert called_tasks[0]["feedback_control_mode"] == "normal"
    assert called_tasks[0]["feedback_control_original_mode"] == "freeze"
    assert called_tasks[0]["feedback_control_relaxed_mode"] == "normal"
    assert called_tasks[0]["feedback_control_relax_reason"] == "snapshot_research_backlog_normal_throttle"
    assert called_tasks[0]["feedback_generation_limited"] is True
    assert called_tasks[0]["generation_limit"] == 1
    assert called_tasks[0]["priority"] < 58


@pytest.mark.asyncio
async def test_run_autonomy_batches_applies_provider_and_rl_mode_controls(monkeypatch):
    scheduler = StrategyFactoryScheduler()
    scheduler.last_result = {
        "run_id": "prev_1",
        "summary": {
            "external_llm_stage_attempt_count": 2,
            "external_llm_real_request_count": 1,
            "external_llm_compatibility_skip_count": 1,
            "external_llm_compatibility_failure_count": 0,
            "external_llm_effective_response_count": 1,
            "external_llm_empty_200_response_count": 0,
            "generator_mode_submission_metrics": {
                "rl_bandit": {
                    "strategy_count": 1,
                    "created_total_count": 0,
                    "refresh_metrics_only_count": 1,
                    "spawn_revision_from_existing_count": 0,
                    "tested_object_hash_changed_count": 0,
                    "refresh_absorption_ratio": 1.0,
                    "revision_creation_ratio": 0.0,
                }
            },
        },
    }

    scan_tasks = [
        {
            "task_id": "snapshot_task",
            "task_key": "snapshot_task",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["600000"],
            "strategy_preferences": ["momentum"],
            "priority": 30,
            "generation_limit": 2,
        }
    ]
    bulk_tasks = [
        {
            "task_id": "bulk_task",
            "task_key": "bulk_task",
            "task_source": "bulk_stock_matrix",
            "candidate_family": "momentum",
            "target_symbols": ["300001"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["300001"]},
            "priority": 88,
            "generation_limit": 2,
        }
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    captured_tasks: list[dict] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        captured_tasks.append(task)
        return _fake_cycle(task)

    fake_provider = SimpleNamespace(
        config=SimpleNamespace(max_concurrency=2),
        is_enabled=lambda: True,
        get_health_snapshot=lambda: {"health_status": "healthy"},
    )
    fake_generation_service = SimpleNamespace(
        llm_generator=SimpleNamespace(external_provider=fake_provider),
        _bulk_llm_enabled=lambda: True,
    )
    fake_autonomy = SimpleNamespace(
        raw=SimpleNamespace(generation_service=fake_generation_service),
        generate_factory_candidates=_generate_factory_candidates,
    )

    persisted_runs = [
        {
            "run_id": "prev_2",
            "summary": {
                "external_llm_stage_attempt_count": 2,
                "external_llm_real_request_count": 1,
                "external_llm_compatibility_skip_count": 1,
                "external_llm_compatibility_failure_count": 0,
                "external_llm_effective_response_count": 1,
                "external_llm_empty_200_response_count": 0,
                "generator_mode_submission_metrics": {
                    "rl_bandit": {
                        "strategy_count": 1,
                        "created_total_count": 0,
                        "refresh_metrics_only_count": 1,
                        "spawn_revision_from_existing_count": 0,
                        "tested_object_hash_changed_count": 0,
                        "refresh_absorption_ratio": 1.0,
                        "revision_creation_ratio": 0.0,
                    }
                },
            },
        }
    ]

    async def _call_optional(target, method_name, *args, default=None, **kwargs):
        method = getattr(target, method_name, None)
        if not callable(method):
            return default
        result = method(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    db = SimpleNamespace(list_strategy_factory_runs=AsyncMock(return_value=persisted_runs))

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.get_strategy_factory_package",
        lambda: factory_pkg,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop._call_optional_async",
        _call_optional,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.StockStrategyMatrixPlanner.plan",
        AsyncMock(return_value={"summary": {"enabled": True, "task_count": 1}, "tasks": bulk_tasks}),
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

    result = await scheduler._run_autonomy_batches(db, {"date": "2026-04-03", "fear_greed_index": 45})

    stage = result["stage"]
    assert stage["external_llm_provider_control_mode"] == "cooldown"
    assert stage["generator_mode_controls"]["rl_bandit"]["control_mode"] == "cooldown"
    by_task_id = {task["task_id"]: task for task in captured_tasks}
    assert by_task_id["snapshot_task"]["disable_optimizer"] is True
    assert by_task_id["snapshot_task"].get("disable_external_llm") is not True
    assert by_task_id["bulk_task"]["disable_external_llm"] is True
    assert by_task_id["bulk_task"]["disable_optimizer"] is True


def test_build_external_provider_control_downgrades_stale_skip_only_suppress():
    control = StrategyFactoryScheduler._build_external_provider_control(
        [
            {
                "run_id": "latest_zero_attempt",
                "external_llm_stage_attempt_count": 0,
                "external_llm_real_request_count": 0,
                "external_llm_compatibility_skip_count": 0,
                "external_llm_compatibility_failure_count": 0,
                "external_llm_effective_response_count": 0,
                "external_llm_empty_200_response_count": 0,
            },
            {
                "run_id": "older_skip_only",
                "external_llm_stage_attempt_count": 8,
                "external_llm_real_request_count": 0,
                "external_llm_compatibility_skip_count": 8,
                "external_llm_compatibility_failure_count": 0,
                "external_llm_effective_response_count": 0,
                "external_llm_empty_200_response_count": 8,
            },
        ],
        {},
    )

    assert control["control_mode"] == "cooldown"
    assert control["control_reasons"] == ["compatibility_skip_ratio_too_high"]
    assert control["active_attempt_run_count"] == 1
    assert control["zero_attempt_run_streak"] == 1
    assert control["suppress_recovery_probe_recommended"] is True
    assert control["suppress_recovery_probe_reason"] == "skip_only_history_without_recent_probe"


def test_build_external_provider_control_keeps_suppress_for_repeated_skip_only_runs():
    control = StrategyFactoryScheduler._build_external_provider_control(
        [
            {
                "run_id": "latest_skip_only",
                "external_llm_stage_attempt_count": 4,
                "external_llm_real_request_count": 0,
                "external_llm_compatibility_skip_count": 4,
                "external_llm_compatibility_failure_count": 0,
                "external_llm_effective_response_count": 0,
                "external_llm_empty_200_response_count": 4,
            },
            {
                "run_id": "older_skip_only",
                "external_llm_stage_attempt_count": 4,
                "external_llm_real_request_count": 0,
                "external_llm_compatibility_skip_count": 4,
                "external_llm_compatibility_failure_count": 0,
                "external_llm_effective_response_count": 0,
                "external_llm_empty_200_response_count": 4,
            },
        ],
        {},
    )

    assert control["control_mode"] == "suppress"
    assert control["suppress_recovery_probe_recommended"] is False
    assert control["active_attempt_run_count"] == 2
    assert control["zero_attempt_run_streak"] == 0


@pytest.mark.asyncio
async def test_run_autonomy_batches_uses_lifecycle_feedback_generator_mode_controls(monkeypatch):
    scheduler = StrategyFactoryScheduler()

    scan_tasks = [
        {
            "task_id": "snapshot_task",
            "task_key": "snapshot_task",
            "task_source": "snapshot",
            "opportunity_type": "snapshot_case",
            "target_symbols": ["600000"],
            "priority": 36,
            "generation_limit": 2,
        }
    ]

    scanner = _FakeScanner(scan_tasks)
    factory_pkg = SimpleNamespace(MarketOpportunityScanner=lambda: scanner)
    captured_tasks: list[dict] = []

    async def _generate_factory_candidates(_db, _snapshot, *, limit=4, research_task=None, source=""):
        task = dict(research_task or {})
        captured_tasks.append(task)
        return _fake_cycle(task)

    fake_provider = SimpleNamespace(
        config=SimpleNamespace(max_concurrency=2),
        is_enabled=lambda: True,
        get_health_snapshot=lambda: {"health_status": "healthy"},
    )
    fake_generation_service = SimpleNamespace(
        llm_generator=SimpleNamespace(external_provider=fake_provider),
        _bulk_llm_enabled=lambda: True,
    )
    fake_autonomy = SimpleNamespace(
        raw=SimpleNamespace(generation_service=fake_generation_service),
        generate_factory_candidates=_generate_factory_candidates,
    )

    async def _call_optional(target, method_name, *args, default=None, **kwargs):
        method = getattr(target, method_name, None)
        if not callable(method):
            return default
        result = method(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    db = SimpleNamespace(list_strategy_factory_runs=AsyncMock(return_value=[]))

    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop.get_strategy_factory_package",
        lambda: factory_pkg,
    )
    monkeypatch.setattr(
        "strategy_factory.application._factory_scheduler_loop._call_optional_async",
        _call_optional,
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

    result = await scheduler._run_autonomy_batches(
        db,
        {
            "date": "2026-04-03",
            "fear_greed_index": 45,
            "factor_research": {
                "lifecycle_feedback_input": {
                    "contract_version": "strategy_factory.lifecycle_feedback_input.v1",
                    "available": True,
                    "feedback": {
                        "momentum": {
                            "generator_mode_feedback": {
                                "external_llm": {
                                    "promotion_review_count": 1,
                                    "promotion_review_status": "rejected",
                                    "promotion_review_recommendation": "deprecate",
                                    "promotion_review_score": 0.18,
                                }
                            }
                        }
                    },
                    "summary": {
                        "family_count": 1,
                        "generator_mode_scope_count": 1,
                        "promotion_review_count": 1,
                        "promotion_review_status_counts": {"rejected": 1},
                    },
                }
            },
        },
    )

    stage = result["stage"]
    assert stage["generator_mode_controls"]["external_llm"]["control_mode"] == "freeze"
    assert captured_tasks[0]["disable_external_llm"] is True
    assert captured_tasks[0]["external_llm_skip_reason"] == "generator_mode_promotion_review_rejected"
