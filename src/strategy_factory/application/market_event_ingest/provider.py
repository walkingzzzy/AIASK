"""Market Event Ingest provider interface."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class MarketEventIngestProvider(Protocol):
    """Provider interface for market event ingest runtime capabilities.

    Host process must implement this interface to provide concrete
    event source scanning, normalization, clustering, and signal generation.
    """

    async def get_db(self) -> Any:
        """Return initialized database connection."""
        ...

    async def scan_event_sources(
        self,
        db: Any,
        *,
        as_of: date,
        lookback_days: int = 7,
    ) -> dict[str, Any]:
        """Scan configured event sources for new events."""
        ...

    async def normalize_events(
        self,
        db: Any,
        raw_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Normalize raw events into standard format."""
        ...

    async def cluster_events(
        self,
        db: Any,
        normalized_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Cluster related events into themes."""
        ...

    async def generate_event_signals(
        self,
        db: Any,
        clusters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate trading signals from event clusters."""
        ...

    async def detect_theme_events(
        self,
        db: Any,
        clusters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect major theme events (sector rotation, policy shifts, etc)."""
        ...

    async def persist_events(
        self,
        db: Any,
        normalized_events: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> None:
        """Persist processed events, clusters, and signals to database."""
        ...
