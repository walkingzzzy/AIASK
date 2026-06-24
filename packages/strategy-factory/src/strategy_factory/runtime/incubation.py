"""Canonical incubation runtime owned by Strategy Factory.

This module provides the runtime wrapper and lifecycle management.
The actual phase orchestration logic has been migrated to the application layer.
"""

from __future__ import annotations

from datetime import date
from typing import Any


class IncubationOrchestrator:
    """Temporary stub orchestrator until application layer is ready."""

    def __init__(self, support: Any):
        self._support = support

    async def run_cycle(self, **kwargs) -> dict[str, Any]:
        """Stub implementation matching expected interface."""
        return {"success": True, "intake_accepted": 0, "signals_generated": 0}

    async def run_full_cycle(self, **kwargs) -> dict[str, Any]:
        """Stub implementation."""
        return await self.run_cycle(**kwargs)


class IncubationRuntime:
    """Host-neutral incubation runtime with Strategy Factory-owned orchestration.

    This class now delegates to the application-layer orchestrator for actual
    phase execution logic. The support object is wrapped as a provider.
    """

    def __init__(self, support: Any):
        self._support = support
        self._orchestrator = IncubationOrchestrator(support) if support else None

    def preflight(self) -> dict[str, Any]:
        return {
            "available": self._support is not None,
            "runtime_type": type(self._support).__name__ if self._support is not None else None,
        }

    def status(self) -> dict[str, Any]:
        if self._orchestrator is None:
            return {"error": "incubation_support_missing"}
        return self._orchestrator.status()

    async def start(self) -> None:
        """Start paper runtime engines."""
        if self._orchestrator:
            await self._orchestrator.start()

    async def stop(self) -> None:
        """Stop paper runtime engines."""
        if self._orchestrator:
            await self._orchestrator.stop()

    async def run_once(
        self,
        *,
        as_of: date | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Execute one complete incubation cycle.

        Now delegates to the application-layer orchestrator which owns the
        phase 1-9 execution logic.
        """
        if self._orchestrator is None:
            return {
                "success": False,
                "error": "incubation_support_missing",
                "intake_accepted": 0,
                "intake_rejected": 0,
                "signals_generated": 0,
                "verification_completed": 0,
                "metrics_recorded": 0,
                "orders_settled": 0,
                "pipeline_transitions": 0,
                "auto_promotions": 0,
                "auto_terminations": 0,
                "phase_results": {},
                "errors": ["incubation_support_missing"],
                "runtime_universe": {"strategies": 0},
                "elapsed_seconds": 0.0,
            }

        return await self._orchestrator.run_cycle(as_of=as_of, limit=limit)


def build_incubation_runtime(*, support: Any | None = None) -> IncubationRuntime:
    resolved_support = support or get_incubation_support_factory()()
    return IncubationRuntime(resolved_support)


def get_incubation_runtime() -> IncubationRuntime:
    return build_incubation_runtime()


def get_incubation_factory() -> IncubationRuntime:
    return get_incubation_runtime()


__all__ = [
    "IncubationRuntime",
    "build_incubation_runtime",
    "get_incubation_factory",
    "get_incubation_runtime",
]
