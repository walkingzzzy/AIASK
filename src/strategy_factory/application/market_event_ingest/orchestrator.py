"""Market Event Ingest orchestrator - event pipeline execution logic.

This module owns the orchestration of market event ingestion: scanning sources,
normalizing events, clustering, signal generation. Concrete implementations
are delegated to the provider interface.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from .contracts import MarketEventIngestResult
from .provider import MarketEventIngestProvider

logger = logging.getLogger(__name__)


class MarketEventIngestOrchestrator:
    """Orchestrates market event ingest pipeline.

    Owns the pipeline sequencing, error handling, and result aggregation.
    Does not own concrete implementations - those are injected via provider.
    """

    def __init__(self, provider: MarketEventIngestProvider):
        self._provider = provider

    async def run_cycle(
        self,
        *,
        as_of: date | None = None,
        lookback_days: int = 7,
    ) -> dict[str, Any]:
        """Execute one complete market event ingest cycle.

        Args:
            as_of: Event scan date (defaults to today)
            lookback_days: Days to look back for events

        Returns:
            Complete cycle result with all phase outputs
        """
        db = await self._provider.get_db()
        if hasattr(db, "initialize"):
            await db.initialize()

        today = as_of or date.today()
        start = datetime.now(timezone.utc)
        run_id = f"market_event_{int(start.timestamp())}_{uuid4().hex[:8]}"
        trace_id = uuid4().hex[:12]

        logger.info(
            "MarketEventIngestOrchestrator [%s]: starting cycle run_id=%s as_of=%s",
            trace_id,
            run_id,
            today,
        )

        result = MarketEventIngestResult(
            success=True,
            run_id=run_id,
        )

        try:
            # Phase 1: Scan event sources
            logger.info("MarketEventIngestOrchestrator [%s] Phase 1: Scan sources", trace_id)
            scan_result = await self._provider.scan_event_sources(
                db,
                as_of=today,
                lookback_days=lookback_days,
            )
            result.sources_scanned = int(scan_result.get("sources_scanned") or 0)
            result.events_ingested = int(scan_result.get("events_ingested") or 0)
            result.phase_results["phase_1_scan"] = scan_result

            raw_events = scan_result.get("raw_events") or []
            logger.info(
                "MarketEventIngestOrchestrator [%s]: ingested %d events from %d sources",
                trace_id,
                result.events_ingested,
                result.sources_scanned,
            )

            # Phase 2: Normalize events
            logger.info("MarketEventIngestOrchestrator [%s] Phase 2: Normalize", trace_id)
            normalize_result = await self._provider.normalize_events(db, raw_events)
            result.events_normalized = int(normalize_result.get("normalized_count") or 0)
            result.phase_results["phase_2_normalize"] = normalize_result

            normalized_events = normalize_result.get("normalized_events") or []

            # Phase 3: Cluster events
            logger.info("MarketEventIngestOrchestrator [%s] Phase 3: Cluster", trace_id)
            cluster_result = await self._provider.cluster_events(db, normalized_events)
            result.clusters_created = int(cluster_result.get("clusters_created") or 0)
            result.phase_results["phase_3_cluster"] = cluster_result

            clusters = cluster_result.get("clusters") or []

            # Phase 4: Generate signals
            logger.info("MarketEventIngestOrchestrator [%s] Phase 4: Generate signals", trace_id)
            signal_result = await self._provider.generate_event_signals(db, clusters)
            result.signals_generated = int(signal_result.get("signals_generated") or 0)
            result.phase_results["phase_4_signals"] = signal_result

            signals = signal_result.get("signals") or []

            # Phase 5: Detect theme events
            logger.info("MarketEventIngestOrchestrator [%s] Phase 5: Theme detection", trace_id)
            theme_result = await self._provider.detect_theme_events(db, clusters)
            result.theme_events_detected = int(theme_result.get("themes_detected") or 0)
            result.phase_results["phase_5_themes"] = theme_result

            # Phase 6: Persist
            logger.info("MarketEventIngestOrchestrator [%s] Phase 6: Persist", trace_id)
            await self._provider.persist_events(db, normalized_events, clusters, signals)

            result.elapsed_seconds = (datetime.now(timezone.utc) - start).total_seconds()

            logger.info(
                "MarketEventIngestOrchestrator [%s]: completed in %.1fs (events=%d, clusters=%d, signals=%d)",
                trace_id,
                result.elapsed_seconds,
                result.events_normalized,
                result.clusters_created,
                result.signals_generated,
            )

        except Exception as exc:
            logger.exception("MarketEventIngestOrchestrator [%s]: cycle failed", trace_id)
            result.success = False
            result.errors.append(str(exc))
            result.elapsed_seconds = (datetime.now(timezone.utc) - start).total_seconds()

        return {
            "success": result.success,
            "run_id": result.run_id,
            "sources_scanned": result.sources_scanned,
            "events_ingested": result.events_ingested,
            "events_normalized": result.events_normalized,
            "clusters_created": result.clusters_created,
            "signals_generated": result.signals_generated,
            "theme_events_detected": result.theme_events_detected,
            "phase_results": result.phase_results,
            "errors": result.errors,
            "elapsed_seconds": result.elapsed_seconds,
        }
