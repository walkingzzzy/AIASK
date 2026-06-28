"""Canonical incubation runtime owned by Strategy Factory.

Phase 2B complete: Orchestration logic now lives in application layer.
"""

from __future__ import annotations

from typing import Any

from ..application.incubation import IncubationOrchestrator
from ..infrastructure.runtime_services import get_incubation_runtime_support_factory


class IncubationRuntime:
    """Host-neutral incubation runtime with Strategy Factory-owned orchestration.

    Phase 2B: Delegates to application-layer orchestrator for cycle coordination.
    """

    def __init__(self, support: Any):
        self._support = support
        self._orchestrator = IncubationOrchestrator(support) if support else None

    def preflight(self) -> dict[str, Any]:
        return {
            "available": self._support is not None,
            "runtime_type": type(self._support).__name__ if self._support is not None else None,
            "orchestrator_ready": self._orchestrator is not None,
        }

    def status(self) -> dict[str, Any]:
        status = getattr(self._support, "status", None)
        if callable(status):
            return dict(status() or {})
        return self.preflight()

    async def start(self) -> None:
        """Start paper runtime engines (MatchingEngine + NavEngine)."""
        start_method = getattr(self._support, "_start_paper_trading_daemons", None)
        if callable(start_method):
            await start_method()

    async def stop(self) -> None:
        """Stop paper runtime engines."""
        stop_method = getattr(self._support, "_stop_paper_trading_daemons", None)
        if callable(stop_method):
            await stop_method()

    async def run_once(
        self,
        *,
        trigger: str = "scheduled",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute one complete incubation cycle.

        Phase 2B: Delegates to application-layer orchestrator.
        """
        if self._orchestrator is None:
            return {
                "success": False,
                "error": "incubation_support_missing",
                "trigger": trigger,
            }

        return await self._orchestrator.run_cycle(
            trigger=trigger,
            dry_run=dry_run,
        )


def build_incubation_runtime(*, support: Any | None = None) -> IncubationRuntime:
    resolved_support = support or get_incubation_runtime_support_factory()()
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
