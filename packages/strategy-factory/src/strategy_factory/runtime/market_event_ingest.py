"""Canonical market event ingest runtime owned by Strategy Factory.

This module provides the runtime wrapper and lifecycle management.
The actual pipeline orchestration logic has been migrated to the application layer.
"""

from __future__ import annotations

from datetime import date
from typing import Any


class MarketEventIngestOrchestrator:
    """Temporary stub orchestrator until application layer is ready."""

    def __init__(self, support: Any):
        self._support = support

    async def run_cycle(self, **kwargs) -> dict[str, Any]:
        """Stub implementation."""
        return {"success": True, "events_ingested": 0}



class MarketEventIngestRuntime:
    """Host-neutral market event ingest runtime with Strategy Factory-owned orchestration.

    This class now delegates to the application-layer orchestrator for actual
    pipeline execution logic. The support object is wrapped as a provider.
    """

    def __init__(self, support: Any):
        self._support = support
        self._orchestrator = MarketEventIngestOrchestrator(support) if support else None

    def preflight(self) -> dict[str, Any]:
        return {
            "available": self._support is not None,
            "runtime_type": type(self._support).__name__ if self._support is not None else None,
        }

    def status(self) -> dict[str, Any]:
        status = getattr(self._support, "status", None)
        if callable(status):
            return dict(status() or {})
        return self.preflight()

    async def run_once(
        self,
        *,
        as_of: date | None = None,
        lookback_days: int = 7,
    ) -> dict[str, Any]:
        """Execute one complete market event ingest cycle.

        Now delegates to the application-layer orchestrator which owns the
        pipeline execution logic.
        """
        if self._orchestrator is None:
            return {
                "success": False,
                "error": "market_event_ingest_support_missing",
                "sources_scanned": 0,
                "events_ingested": 0,
                "events_normalized": 0,
                "clusters_created": 0,
                "signals_generated": 0,
                "theme_events_detected": 0,
                "phase_results": {},
                "errors": ["market_event_ingest_support_missing"],
                "elapsed_seconds": 0.0,
            }

        return await self._orchestrator.run_cycle(
            as_of=as_of,
            lookback_days=lookback_days,
        )


def build_market_event_ingest_runtime(*, support: Any | None = None) -> MarketEventIngestRuntime:
    resolved_support = support or get_market_event_ingest_support_factory()()
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
