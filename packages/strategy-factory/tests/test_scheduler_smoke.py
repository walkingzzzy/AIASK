"""Smoke tests for StrategyFactoryScheduler instantiation and basic state."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from types import MethodType


def test_scheduler_instantiation():
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

    sched = StrategyFactoryScheduler()
    assert sched.schedule_mode in ("continuous", "daily")
    assert sched._running is False
    assert sched._consecutive_failures == 0
    assert sched._circuit_open_until is None


def test_scheduler_start_stop():
    """Verify start/stop lifecycle without an event loop (no actual scheduling)."""
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler

    sched = StrategyFactoryScheduler()
    # stop without start should be safe
    sched.stop()
    assert sched._running is False


def test_scheduler_execution_mode_default():
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
    from strategy_factory.application.factory_execution import FactoryExecutionMode

    sched = StrategyFactoryScheduler()
    assert sched.execution_mode == FactoryExecutionMode.LEGACY_PRIMARY


def test_scheduler_engine_version():
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
    from strategy_factory.application.factory_execution import FACTORY_ENGINE_VERSION

    sched = StrategyFactoryScheduler()
    assert sched.engine_version == FACTORY_ENGINE_VERSION


def test_facade_scheduler_applies_explicit_runtime_providers(monkeypatch):
    import strategy_factory.application.runtime as runtime_module
    from strategy_factory import get_strategy_factory_scheduler

    monkeypatch.setattr(runtime_module, "_local_factory_scheduler", None)
    db = object()
    db_2 = object()

    def db_provider():
        return db

    def db_provider_2():
        return db_2

    adapters = SimpleNamespace(
        repository=SimpleNamespace(raw=db),
        vector_search=object(),
        validation=object(),
        risk=object(),
        incubation=object(),
        autonomy=object(),
        factor_research=object(),
    )
    adapters_2 = SimpleNamespace(
        repository=SimpleNamespace(raw=db_2),
        vector_search=object(),
        validation=object(),
        risk=object(),
        incubation=object(),
        autonomy=object(),
        factor_research=object(),
    )

    sched = get_strategy_factory_scheduler(db_provider=db_provider, runtime_adapters=adapters)

    assert sched._db_provider is db_provider
    assert sched._runtime_adapters is adapters
    assert sched._vector_gateway is adapters.vector_search
    assert sched._autonomy_gateway is adapters.autonomy

    cached = get_strategy_factory_scheduler(db_provider=db_provider_2, runtime_adapters=adapters_2)

    assert cached is sched
    assert cached._db_provider is db_provider_2
    assert cached._runtime_adapters is adapters_2
    assert cached._vector_gateway is adapters_2.vector_search
    assert cached._autonomy_gateway is adapters_2.autonomy


def test_factor_research_refresh_remains_explicit_when_auto_refresh_disabled(monkeypatch):
    from strategy_factory.application.research.runner import ResearchPlaneRunner

    monkeypatch.setenv("STRATEGY_FACTORY_FACTOR_AUTO_REFRESH", "0")

    class FakeScheduler:
        def _adapt_gateway_repository(self, db):
            return db

        def _summarize_refresh_result(self, result):
            return dict(result or {})

        def _inject_factor_refresh_meta(self, artifact, refresh_meta):
            return {**dict(artifact or {}), "freshness_repair": dict(refresh_meta)}

    class FakeFactorGateway:
        def __init__(self):
            self.refresh_count = 0

        async def build_artifact(self, db, snapshot):
            return {
                "summary": {
                    "factor_source_mode": "seed_fallback",
                    "scheduler_last_run": "2026-05-19T09:30:00+08:00",
                    "active_candidate_count": 0,
                    "governed_source_candidate_count": 0,
                }
            }

        async def refresh(self):
            self.refresh_count += 1
            return {"ok": True}

    gateway = FakeFactorGateway()
    runner = ResearchPlaneRunner(FakeScheduler(), SimpleNamespace())

    artifact = asyncio.run(
        runner.build_factor_research_artifact(
            gateway,
            object(),
            {"_factor_refresh_self_heal": False},
        )
    )

    assert gateway.refresh_count == 0
    assert artifact["freshness_repair"]["refresh_status"] == "disabled"


def test_cycle_runner_does_not_enable_factor_self_heal_by_default():
    root = Path(__file__).resolve().parents[3]
    text = (root / "packages/strategy-factory/src/strategy_factory/application/cycle_runner_parts/normalizers.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert '"_factor_refresh_self_heal": False' in text


def test_scheduler_run_once_heartbeats_task_board_during_long_cycle(tmp_path, monkeypatch):
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
    from strategy_factory.application.factory_task_board import FactoryTaskBoard

    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    scheduler = StrategyFactoryScheduler(db_provider=lambda: object())
    scheduler._task_board = board
    heartbeat_calls = {"count": 0}
    original_heartbeat = board.heartbeat

    def _heartbeat(*args, **kwargs):
        heartbeat_calls["count"] += 1
        return original_heartbeat(*args, **kwargs)

    board.heartbeat = _heartbeat
    monkeypatch.setenv("STRATEGY_FACTORY_TASK_BOARD_HEARTBEAT_MIN_SEC", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_TASK_BOARD_HEARTBEAT_SEC", "1")

    async def _execute_factory_run_once_mode(self, resolved_db, **kwargs):
        await asyncio.sleep(1.2)
        return (
            {
                "run_id": "factory_run_heartbeat",
                "status": "success",
                "summary": {},
                "artifact_refs": [],
            },
            [],
        )

    async def _persist_run_result(self, db, results, *, persistence_failures):
        return None

    scheduler._execute_factory_run_once_mode = MethodType(_execute_factory_run_once_mode, scheduler)
    scheduler._persist_run_result = MethodType(_persist_run_result, scheduler)

    result = asyncio.run(scheduler.run_once())

    assert result["status"] == "success"
    assert heartbeat_calls["count"] >= 2
    active = board.reclaim_stale()
    assert active == []
    completed = [
        row
        for row in (
            board.get_task(result["task_board"]["task_id"]),
        )
        if row is not None
    ]
    assert completed[0]["status"] == "completed"


def test_scheduler_run_once_timeout_blocks_task_board(tmp_path, monkeypatch):
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
    from strategy_factory.application.factory_task_board import FactoryTaskBoard

    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    scheduler = StrategyFactoryScheduler(db_provider=lambda: object())
    scheduler._task_board = board
    monkeypatch.setenv("STRATEGY_FACTORY_TASK_BOARD_HEARTBEAT_MIN_SEC", "1")
    monkeypatch.setenv("STRATEGY_FACTORY_TASK_BOARD_HEARTBEAT_SEC", "1")
    scheduler._resolve_run_once_timeout_sec = MethodType(lambda self: 0.01, scheduler)

    async def _execute_factory_run_once_mode(self, resolved_db, **kwargs):
        await asyncio.sleep(1.0)
        return ({"run_id": "factory_run_timeout", "status": "success"}, [])

    scheduler._execute_factory_run_once_mode = MethodType(_execute_factory_run_once_mode, scheduler)

    try:
        asyncio.run(scheduler.run_once())
    except TimeoutError as exc:
        assert "StrategyFactory run_once exceeded" in str(exc)
    else:
        raise AssertionError("run_once should have timed out")

    with board._connect() as conn:
        rows = conn.execute("SELECT * FROM factory_tasks").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "blocked"
    assert "StrategyFactory run_once exceeded" in rows[0]["blocked_reason"]


def test_scheduler_run_once_blocks_orphaned_predecessor_task(tmp_path):
    from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler
    from strategy_factory.application.factory_task_board import FactoryTaskBoard

    board = FactoryTaskBoard(tmp_path / "board.sqlite3")
    old_task = board.create_task(
        task_type="research",
        title="Strategy factory run_once",
        payload={"execution_mode": "legacy_primary"},
    )
    old_claim = board.claim_task(old_task["task_id"], worker_id="old-worker", ttl_seconds=1800)
    assert old_claim is not None
    scheduler = StrategyFactoryScheduler(db_provider=lambda: object())
    scheduler._task_board = board

    async def _execute_factory_run_once_mode(self, resolved_db, **kwargs):
        return (
            {
                "run_id": "factory_run_new",
                "status": "success",
                "summary": {},
                "artifact_refs": [],
            },
            [],
        )

    async def _persist_run_result(self, db, results, *, persistence_failures):
        return None

    scheduler._execute_factory_run_once_mode = MethodType(_execute_factory_run_once_mode, scheduler)
    scheduler._persist_run_result = MethodType(_persist_run_result, scheduler)

    result = asyncio.run(scheduler.run_once())

    assert result["status"] == "success"
    old_after = board.get_task(old_task["task_id"])
    assert old_after is not None
    assert old_after["status"] == "blocked"
    assert "superseded" in old_after["blocked_reason"]
    new_after = board.get_task(result["task_board"]["task_id"])
    assert new_after is not None
    assert new_after["status"] == "completed"
    assert isinstance(new_after["payload"].get("owner_pid"), int)
