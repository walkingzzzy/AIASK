"""Canonical market event ingest runtime owned by Strategy Factory.

Phase 2D complete: Orchestration logic now lives in application layer.
"""

from __future__ import annotations

from typing import Any

from ..application.market_event_ingest import MarketEventIngestOrchestrator
from ..infrastructure.runtime_services import get_market_event_ingest_support_factory


class MarketEventIngestRuntime:
    """Host-neutral market event ingest runtime with Strategy Factory-owned orchestration.

    Phase 2D: Delegates to application-layer orchestrator for bridge and
    normalization decision logic.
    """

    def __init__(self, support: Any):
        self._support = support
        self._orchestrator = MarketEventIngestOrchestrator(support) if support else None

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

    async def run_once(
        self,
        *,
        trigger: str = "scheduled",
        lookback_days: int = 7,
    ) -> dict[str, Any]:
        """Execute one complete market event ingest cycle.

        Phase 2D: Delegates to application-layer orchestrator.
        """
        if self._orchestrator is None:
            return {
                "success": False,
                "error": "market_event_ingest_support_missing",
                "trigger": trigger,
            }

        return await self._orchestrator.run_cycle(
            trigger=trigger,
            lookback_days=lookback_days,
        )


def build_market_event_ingest_runtime(*, support: Any | None = None) -> MarketEventIngestRuntime:
    resolved_support = support or get_market_event_ingest_runtime_support_factory()()
    return MarketEventIngestRuntime(resolved_support)


def get_market_event_ingest_runtime() -> MarketEventIngestRuntime:
    return build_market_event_ingest_runtime()


def get_market_event_ingest_factory() -> MarketEventIngestRuntime:
    return get_market_event_ingest_runtime()


__all__ = [
    "MarketEventIngestRuntime",
    "build_market_event_ingest_runtime",
    "get_market_event_ingest_factory",
    "get_market_event_ingest_runtime",
]
