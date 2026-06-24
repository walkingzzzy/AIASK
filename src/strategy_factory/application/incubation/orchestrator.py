"""Incubation orchestrator - Phase 1-9 execution logic.

This module owns the orchestration of incubation phases: intake, signal generation,
verification, metrics, settlement, pipeline, and reporting. Concrete implementations
are delegated to the provider interface.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from .contracts import IncubationResult
from .provider import IncubationProvider

logger = logging.getLogger(__name__)


class IncubationOrchestrator:
    """Orchestrates incubation phases 1-9.

    Owns the phase sequencing, error handling, and result aggregation.
    Does not own concrete implementations - those are injected via provider.
    """

    def __init__(self, provider: IncubationProvider):
        self._provider = provider

    async def run_cycle(
        self,
        *,
        as_of: date | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Execute one complete incubation cycle (Phase 1-9).

        Args:
            as_of: Signal date (defaults to today)
            limit: Maximum strategies to process

        Returns:
            Complete cycle result with all phase outputs
        """
        db = await self._provider.get_db()
        if hasattr(db, "initialize"):
            await db.initialize()

        today = as_of or date.today()
        start = datetime.now(timezone.utc)
        run_id = f"incubation_{int(start.timestamp())}_{uuid4().hex[:8]}"
        trace_id = uuid4().hex[:12]

        logger.info("IncubationOrchestrator [%s]: starting cycle run_id=%s", trace_id, run_id)

        result = IncubationResult(
            success=True,
            run_id=run_id,
        )

        try:
            # Phase 1: Intake - scan and accept new strategies
            logger.info("IncubationOrchestrator [%s] Phase 1: Intake", trace_id)
            intake_result = await self._provider.scan_and_accept_strategies(db, limit=100)
            result.intake_accepted = int(intake_result.get("accepted") or 0)
            result.intake_rejected = int(intake_result.get("rejected") or 0)
            result.phase_results["phase_1_intake"] = intake_result

            # Load incubating strategies
            strategies = await self._provider.list_incubating_strategies(db, limit=limit)
            result.runtime_universe = {"strategies": len(strategies)}
            logger.info(
                "IncubationOrchestrator [%s]: loaded %d incubating strategies",
                trace_id,
                len(strategies),
            )

            # Phase 2: Signal Generation
            logger.info("IncubationOrchestrator [%s] Phase 2: Signal Generation", trace_id)
            signal_results = []
            for strategy in strategies:
                try:
                    signal_result = await asyncio.wait_for(
                        self._provider.generate_signals(db, strategy, as_of=today),
                        timeout=30.0,
                    )
                    signal_results.append(signal_result)
                    result.signals_generated += int(signal_result.get("signals_generated") or 0)
                except asyncio.TimeoutError:
                    logger.warning("Signal generation timeout for strategy %s", strategy.get("id"))
                except Exception as exc:
                    logger.warning("Signal generation failed for strategy %s: %s", strategy.get("id"), exc)

            result.phase_results["phase_2_signals"] = {
                "strategies_processed": len(signal_results),
                "total_signals": result.signals_generated,
            }

            # Phase 3: Verification
            logger.info("IncubationOrchestrator [%s] Phase 3: Verification", trace_id)
            verification_results = []
            for strategy in strategies:
                try:
                    verification_result = await asyncio.wait_for(
                        self._provider.verify_forward_returns(db, strategy),
                        timeout=30.0,
                    )
                    verification_results.append(verification_result)
                    if verification_result.get("verified"):
                        result.verification_completed += 1
                except asyncio.TimeoutError:
                    logger.warning("Verification timeout for strategy %s", strategy.get("id"))
                except Exception as exc:
                    logger.warning("Verification failed for strategy %s: %s", strategy.get("id"), exc)

            result.phase_results["phase_3_verification"] = {
                "verified_count": result.verification_completed,
            }

            # Phase 4: Metrics Recording
            logger.info("IncubationOrchestrator [%s] Phase 4: Metrics", trace_id)
            for i, strategy in enumerate(strategies):
                if i < len(verification_results):
                    try:
                        metrics_result = await self._provider.record_metrics(
                            db,
                            strategy,
                            verification_results[i],
                        )
                        if metrics_result.get("recorded"):
                            result.metrics_recorded += 1
                    except Exception as exc:
                        logger.warning("Metrics recording failed for strategy %s: %s", strategy.get("id"), exc)

            result.phase_results["phase_4_metrics"] = {
                "metrics_recorded": result.metrics_recorded,
            }

            # Phase 5: Order Settlement
            logger.info("IncubationOrchestrator [%s] Phase 5: Settlement", trace_id)
            for i, strategy in enumerate(strategies):
                if i < len(signal_results):
                    try:
                        settlement_result = await self._provider.settle_orders(
                            db,
                            strategy,
                            signal_results[i],
                        )
                        result.orders_settled += int(settlement_result.get("settled") or 0)
                    except Exception as exc:
                        logger.warning("Settlement failed for strategy %s: %s", strategy.get("id"), exc)

            result.phase_results["phase_5_settlement"] = {
                "orders_settled": result.orders_settled,
            }

            # Phase 6: Pipeline Transitions
            logger.info("IncubationOrchestrator [%s] Phase 6: Pipeline", trace_id)
            pipeline_result = await self._provider.run_pipeline(db, strategies)
            result.pipeline_transitions = int(pipeline_result.get("transitions") or 0)
            result.auto_promotions = int(pipeline_result.get("promotions") or 0)
            result.auto_terminations = int(pipeline_result.get("terminations") or 0)
            result.phase_results["phase_6_pipeline"] = pipeline_result

            # Phase 7: Hit Rate Report
            logger.info("IncubationOrchestrator [%s] Phase 7: Hit Rate Report", trace_id)
            try:
                hit_rate_result = await self._provider.generate_hit_rate_report(
                    db,
                    strategies,
                    verification_results,
                )
                result.phase_results["phase_7_hit_rate"] = hit_rate_result
            except Exception as exc:
                logger.warning("Hit rate report generation failed: %s", exc)
                result.phase_results["phase_7_hit_rate"] = {"error": str(exc)}

            # Phase 8: Paper Runtime Status
            logger.info("IncubationOrchestrator [%s] Phase 8: Paper Runtime Status", trace_id)
            try:
                paper_status = self._provider.paper_runtime_status()
                result.phase_results["phase_8_paper_runtime"] = paper_status
            except Exception as exc:
                logger.warning("Paper runtime status check failed: %s", exc)
                result.phase_results["phase_8_paper_runtime"] = {"error": str(exc)}

            # Phase 9: Finalize
            result.elapsed_seconds = (datetime.now(timezone.utc) - start).total_seconds()

            logger.info(
                "IncubationOrchestrator [%s]: completed in %.1fs (intake=%d, signals=%d, verified=%d, promotions=%d)",
                trace_id,
                result.elapsed_seconds,
                result.intake_accepted,
                result.signals_generated,
                result.verification_completed,
                result.auto_promotions,
            )

        except Exception as exc:
            logger.exception("IncubationOrchestrator [%s]: cycle failed", trace_id)
            result.success = False
            result.errors.append(str(exc))
            result.elapsed_seconds = (datetime.now(timezone.utc) - start).total_seconds()

        return {
            "success": result.success,
            "run_id": result.run_id,
            "intake_accepted": result.intake_accepted,
            "intake_rejected": result.intake_rejected,
            "signals_generated": result.signals_generated,
            "verification_completed": result.verification_completed,
            "metrics_recorded": result.metrics_recorded,
            "orders_settled": result.orders_settled,
            "pipeline_transitions": result.pipeline_transitions,
            "auto_promotions": result.auto_promotions,
            "auto_terminations": result.auto_terminations,
            "phase_results": result.phase_results,
            "errors": result.errors,
            "runtime_universe": result.runtime_universe,
            "elapsed_seconds": result.elapsed_seconds,
        }

    async def start(self) -> None:
        """Start paper runtime engines."""
        await self._provider.start_paper_runtime()

    async def stop(self) -> None:
        """Stop paper runtime engines."""
        await self._provider.stop_paper_runtime()

    def status(self) -> dict[str, Any]:
        """Get incubation runtime status."""
        return self._provider.paper_runtime_status()
