from __future__ import annotations

import asyncio
from types import SimpleNamespace

from strategy_factory.application.cycle_runner import FactoryCycleOutcome
from strategy_factory.application.factory_execution import (
    FactoryExecutionMode,
    resolve_factory_engine_version,
)
from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


def test_resolve_factory_engine_version_marks_v2_primary():
    assert resolve_factory_engine_version(FactoryExecutionMode.V2_PRIMARY) == "strategy_factory.v2.primary"
    assert resolve_factory_engine_version(FactoryExecutionMode.SHADOW_READONLY) == "strategy_factory.v2.shadow"
    assert resolve_factory_engine_version(FactoryExecutionMode.LEGACY_PRIMARY) == "strategy_factory.v2"


def test_v2_primary_routes_to_dedicated_engine(monkeypatch):
    scheduler = StrategyFactoryScheduler(db_provider=lambda: SimpleNamespace())
    scheduler._attach_runtime_governance = lambda results, previous_result=None: None
    loop_module = __import__(
        "strategy_factory.application._factory_scheduler_loop",
        fromlist=["placeholder"],
    )
    v2_module = __import__(
        "strategy_factory.application.v2_engine",
        fromlist=["FactoryV2Engine"],
    )
    scheduler_module = __import__(
        "strategy_factory.application.factory_scheduler",
        fromlist=["FactoryCycleRunner"],
    )

    monkeypatch.setattr(loop_module, "get_strategy_factory_package", lambda: SimpleNamespace())

    calls = {"v2": 0, "legacy": 0}

    class FakeV2Engine:
        def __init__(self, scheduler_obj, context):
            assert scheduler_obj is scheduler
            assert context.execution_mode == FactoryExecutionMode.V2_PRIMARY.value

        async def run(self):
            calls["v2"] += 1
            return FactoryCycleOutcome(
                {
                    "run_id": "v2-run",
                    "trace_id": "trace-v2",
                    "status": "success",
                    "summary": {"engine_path": "v2_orchestrated"},
                }
            )

    class FakeLegacyRunner:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run(self):
            calls["legacy"] += 1
            return FactoryCycleOutcome(
                {
                    "run_id": "legacy-run",
                    "trace_id": "trace-legacy",
                    "status": "success",
                    "summary": {},
                }
            )

    monkeypatch.setattr(v2_module, "FactoryV2Engine", FakeV2Engine)
    monkeypatch.setattr(scheduler_module, "FactoryCycleRunner", FakeLegacyRunner)

    result, failures = asyncio.run(
        scheduler._execute_factory_cycle_once(
            SimpleNamespace(),
            previous_result=None,
            execution_mode=FactoryExecutionMode.V2_PRIMARY,
        )
    )

    assert failures == []
    assert result["run_id"] == "v2-run"
    assert result["summary"]["engine_path"] == "v2_orchestrated"
    assert calls == {"v2": 1, "legacy": 0}
