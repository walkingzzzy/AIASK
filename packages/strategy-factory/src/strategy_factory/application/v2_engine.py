"""Dedicated V2 strategy factory engine orchestration."""

from __future__ import annotations

from typing import Any

from .cycle_runner import FactoryCycleOutcome, FactoryCycleRunner, FactoryRunContext


class FactoryV2Engine:
    """Dedicated V2 engine entrypoint.

    V2 keeps using the already-migrated service boundaries, but execution is
    now routed through an explicit engine object instead of sharing the legacy
    scheduler runner path directly.
    """

    ENGINE_PATH = "v2_orchestrated"
    ENGINE_COMPONENTS = (
        "warmup",
        "collect",
        "factor_research",
        "readiness",
        "task_orchestrator",
        "candidate_pipeline",
        "submission_coordinator",
        "elimination",
        "summary_persist",
    )

    def __init__(self, scheduler: Any, context: FactoryRunContext):
        self._scheduler = scheduler
        self._context = context
        self._runner = FactoryCycleRunner(scheduler, context)

    async def run(self) -> FactoryCycleOutcome:
        outcome = await self._runner.run()
        result = dict(outcome.result or {})
        summary = dict(result.get("summary") or {})
        summary["engine_path"] = self.ENGINE_PATH
        summary["engine_components"] = list(self.ENGINE_COMPONENTS)
        summary["v2_engine"] = True
        result["summary"] = summary

        run_header = dict(result.get("run_header") or {})
        run_header["engine_path"] = self.ENGINE_PATH
        run_header["engine_components"] = list(self.ENGINE_COMPONENTS)
        result["run_header"] = run_header

        pipeline = dict(result.get("pipeline") or {})
        pipeline["engine_path"] = self.ENGINE_PATH
        pipeline["engine_components"] = list(self.ENGINE_COMPONENTS)
        result["pipeline"] = pipeline
        result["engine_path"] = self.ENGINE_PATH
        outcome.result = result
        return outcome


__all__ = ["FactoryV2Engine"]
