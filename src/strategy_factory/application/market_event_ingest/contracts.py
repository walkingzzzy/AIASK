"""Market Event Ingest contracts and DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketEventIngestResult:
    """Result of a market event ingest cycle."""

    success: bool
    run_id: str | None = None
    sources_scanned: int = 0
    events_ingested: int = 0
    events_normalized: int = 0
    clusters_created: int = 0
    signals_generated: int = 0
    theme_events_detected: int = 0
    phase_results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
