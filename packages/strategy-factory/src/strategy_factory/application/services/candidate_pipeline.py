"""CandidatePipeline – wraps the spawn → gate → dedup → submit pipeline.

Provides a typed service boundary for the candidate processing phase,
replacing the inline pipeline logic in FactoryCycleRunner.run().

P4 refactor: the pipeline exposes a structured CandidatePipelineReport so
callers (cycle_runner, tests) can access per-gate counts without fragile
dict key lookups.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Optional

from ..governance_plane_contract import build_governance_plane_artifact
from ...domain.candidates import CandidatePipelineReport

logger = logging.getLogger(__name__)


class CandidatePipeline:
    """Executes gate-0/1/2 → dedup → gate-3 for a list of candidates.

    This service delegates to the existing ``factory_pkg`` runtime objects
    (BacktestFilter, Deduplicator, StrategySubmitter, run_gated_filter,
    run_gated_submission_pipeline) so no existing behaviour changes.

    Usage::

        pipeline = CandidatePipeline(factory_pkg, scheduler)
        result = await pipeline.run(candidates, snapshot, db)
        # result.report.submitted, result.quality_gate_report, etc.
    """

    def __init__(self, factory_pkg: Any, scheduler: Any) -> None:
        self._pkg = factory_pkg
        self._scheduler = scheduler

    async def run(
        self,
        candidates: list[dict[str, Any]],
        snapshot: dict[str, Any],
        db: Any,
        *,
        read_only: bool = False,
    ) -> "PipelineRunResult":
        """Run the full candidate pipeline and return a structured result."""
        pkg = self._pkg
        scheduler = self._scheduler
        backtest_filter = pkg.BacktestFilter()
        deduplicator = scheduler._build_deduplicator(pkg)
        submitter = scheduler._build_submitter(pkg)

        supports_unified_submission = bool(
            candidates
            and not read_only
            and hasattr(pkg, "run_gated_submission_pipeline")
            and hasattr(pkg, "run_gated_filter")
            and inspect.iscoroutinefunction(getattr(db, "get_klines", None))
        )
        supports_unified_gate = bool(
            candidates
            and hasattr(pkg, "run_gated_filter")
            and inspect.iscoroutinefunction(getattr(db, "get_klines", None))
        )

        if supports_unified_submission:
            pipeline_run = await pkg.run_gated_submission_pipeline(
                candidates,
                snapshot,
                db,
                backtest_filter=backtest_filter,
                deduplicator=deduplicator,
                submitter=submitter,
                gated_runner=pkg.run_gated_filter,
                kline_cache=getattr(backtest_filter, "_kline_cache", None),
            )
            passed = list(pipeline_run.get("passed") or [])
            unique = list(pipeline_run.get("unique") or [])
            quality_gate_report = dict(
                pipeline_run.get("gate_report") or pipeline_run.get("quality_gate") or {}
            )
            backtest_report = dict(pipeline_run.get("backtest_report") or {})
            submit_result = dict(pipeline_run.get("submit_result") or {})
        elif supports_unified_gate:
            gate_run = await pkg.run_gated_filter(
                candidates,
                db,
                backtest_filter,
                kline_cache=getattr(backtest_filter, "_kline_cache", None),
            )
            passed = list(gate_run.get("passed") or [])
            quality_gate_report = dict(
                gate_run.get("gate_report") or gate_run.get("quality_gate") or {}
            )
            backtest_report = self._extract_backtest_report(
                quality_gate_report, backtest_filter, candidates, passed
            )
            if not quality_gate_report:
                quality_gate_report = pkg.build_legacy_gate_report(
                    candidates, passed, backtest_report
                )
            unique = await deduplicator.deduplicate(passed, db)
            submit_result = await submitter.submit(
                unique,
                snapshot,
                db,
                read_only=read_only,
            )
            quality_gate_report = pkg.finalize_gate_report(quality_gate_report, submit_result)
        else:
            passed = await backtest_filter.filter(candidates, db)
            quality_gate_report = {}
            backtest_report = self._extract_backtest_report(
                {}, backtest_filter, candidates, passed
            )
            quality_gate_report = pkg.build_legacy_gate_report(
                candidates, passed, backtest_report
            )
            unique = await deduplicator.deduplicate(passed, db)
            submit_result = await submitter.submit(
                unique,
                snapshot,
                db,
                read_only=read_only,
            )
            quality_gate_report = pkg.finalize_gate_report(quality_gate_report, submit_result)

        report = self._build_report(
            candidates, passed, unique, submit_result, quality_gate_report, backtest_report
        )
        dedup_report = (
            dict(deduplicator.get_last_report() or {})
            if hasattr(deduplicator, "get_last_report")
            else {}
        )
        governance_plane = build_governance_plane_artifact(
            candidates=candidates,
            quality_gate_report=quality_gate_report,
            backtest_report=backtest_report,
            dedup_report=dedup_report,
            submit_result=submit_result,
        )

        return PipelineRunResult(
            passed=passed,
            unique=unique,
            quality_gate_report=quality_gate_report,
            backtest_report=backtest_report,
            submit_result=submit_result,
            deduplicator=deduplicator,
            dedup_report=dedup_report,
            report=report,
            governance_plane=governance_plane,
            read_only=read_only,
        )

    @staticmethod
    def _extract_backtest_report(
        quality_gate_report: dict[str, Any],
        backtest_filter: Any,
        candidates: list[dict[str, Any]],
        passed: list[dict[str, Any]],
    ) -> dict[str, Any]:
        report = (quality_gate_report.get("gate_2") or {}).get("report")
        if report:
            return dict(report)
        if hasattr(backtest_filter, "get_last_report"):
            return dict(backtest_filter.get_last_report() or {})
        return {
            "summary": {
                "input_count": len(candidates),
                "passed_count": len(passed),
                "failed_count": max(len(candidates) - len(passed), 0),
                "failed_reason_counts": {},
                "thresholds_by_type": {},
            },
            "passed": [],
            "failed": [],
        }

    @staticmethod
    def _build_report(
        candidates: list[dict[str, Any]],
        passed: list[dict[str, Any]],
        unique: list[dict[str, Any]],
        submit_result: dict[str, Any],
        quality_gate_report: dict[str, Any],
        backtest_report: dict[str, Any],
    ) -> CandidatePipelineReport:
        backtest_summary = backtest_report.get("summary") or {}
        gate_0 = dict(quality_gate_report.get("gate_0") or {})
        pre_gate = dict(quality_gate_report.get("pre_gate") or {})
        gate_1 = dict(quality_gate_report.get("gate_1") or {})
        gate_2 = dict(quality_gate_report.get("gate_2") or {})

        submitted = int(submit_result.get("submitted") or 0)
        gate_3_passed = int(
            submit_result.get("gate_3_passed")
            or submit_result.get("passed_quality_gate")
            or 0
        )
        gate_3_failed = int(
            submit_result.get("gate_3_failed")
            or max(submitted - gate_3_passed, 0)
        )
        gate_3_provisional = int(submit_result.get("gate_3_provisional_passed") or 0)

        failure_reason_counts: dict[str, int] = {}
        for item in list(submit_result.get("gate_3_failure_reason_topn") or []):
            if isinstance(item, dict) and item.get("reason"):
                failure_reason_counts[str(item["reason"])] = int(item.get("count") or 0)
        for reason, count in dict(
            backtest_summary.get("failed_reason_counts") or {}
        ).items():
            failure_reason_counts[str(reason)] = (
                failure_reason_counts.get(str(reason), 0) + int(count or 0)
            )

        return CandidatePipelineReport(
            total_spawned=len(candidates),
            gate_0_passed=int(gate_0.get("passed_count") or 0),
            gate_0_failed=int(gate_0.get("failed_count") or 0),
            pre_gate_passed=int(pre_gate.get("passed_count") or 0),
            pre_gate_failed=int(pre_gate.get("failed_count") or 0),
            gate_1_passed=int(gate_1.get("passed_count") or 0),
            gate_1_failed=int(gate_1.get("failed_count") or 0),
            gate_2_passed=int(gate_2.get("passed_count") or backtest_summary.get("passed_count") or len(passed)),
            gate_2_failed=int(gate_2.get("failed_count") or backtest_summary.get("failed_count") or max(len(candidates) - len(passed), 0)),
            after_dedup=len(unique),
            gate_3_passed=gate_3_passed,
            gate_3_failed=gate_3_failed,
            gate_3_provisional=gate_3_provisional,
            submitted=submitted,
            failure_reason_counts=failure_reason_counts,
        )


class PipelineRunResult:
    """Structured result of a CandidatePipeline.run() call."""

    def __init__(
        self,
        *,
        passed: list[dict[str, Any]],
        unique: list[dict[str, Any]],
        quality_gate_report: dict[str, Any],
        backtest_report: dict[str, Any],
        submit_result: dict[str, Any],
        deduplicator: Any,
        dedup_report: dict[str, Any],
        report: CandidatePipelineReport,
        governance_plane: dict[str, Any],
        read_only: bool,
    ) -> None:
        self.passed = passed
        self.unique = unique
        self.quality_gate_report = quality_gate_report
        self.backtest_report = backtest_report
        self.submit_result = submit_result
        self.deduplicator = deduplicator
        self.dedup_report = dedup_report
        self.report = report
        self.governance_plane = governance_plane
        self.read_only = bool(read_only)
        self.gate_artifact = dict(governance_plane.get("gate_artifact") or {})
        self.dedup_artifact = dict(governance_plane.get("dedup_artifact") or {})
        self.submission_artifact = dict(governance_plane.get("submission_artifact") or {})
        self.evidence_artifact = dict(governance_plane.get("evidence_artifact") or {})

    def backtest_summary(self) -> dict[str, Any]:
        return dict(self.backtest_report.get("summary") or {})

    def deduplicator_report(self) -> dict[str, Any]:
        if self.dedup_report:
            return dict(self.dedup_report)
        if hasattr(self.deduplicator, "get_last_report"):
            return dict(self.deduplicator.get_last_report() or {})
        return {}


__all__ = [
    "CandidatePipeline",
    "PipelineRunResult",
]
