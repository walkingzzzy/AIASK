"""Single-cycle strategy factory runner."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .governance_plane_contract import build_governance_plane_artifact
from .research_plane_contract import build_research_plane_artifact
from .services.candidate_pipeline import CandidatePipeline
from .run_models import FactoryRunStatus, StageStatus
from .services.readiness_service import (
    READINESS_CONTRACT_VERSION,
    ReadinessService,
    build_readiness_authority,
    resolve_factor_refresh_trigger,
    resolve_governed_pool_state,
)
from ..domain.constants import (
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    is_factory_factor_auto_refresh_enabled,
    is_factory_readiness_hard_block_enabled,
    is_factory_runtime_enabled,
    resolve_event_runtime_mode,
)
from ..domain.strategy_profile import apply_candidate_strategy_profile

logger = logging.getLogger(__name__)

FactoryRunResult = dict[str, Any]


@dataclass(slots=True)
class FactoryRunContext:
    db: Any
    factory_pkg: Any
    runtime_adapters: Any
    start: datetime
    trace_id: str
    run_id: str


@dataclass(slots=True)
class FactoryCycleOutcome:
    result: FactoryRunResult
    persistence_failures: list[dict[str, Any]] = field(default_factory=list)


class FactoryCycleRunner:
    """Runs one strategy factory cycle without owning scheduling state."""

    def __init__(self, scheduler: "StrategyFactoryScheduler", context: FactoryRunContext):
        self._scheduler = scheduler
        self._context = context
        self._readiness_service = getattr(self._scheduler, "_readiness_service", ReadinessService())

    async def _build_factor_research_artifact(self, factor_gateway, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        scheduler = self._scheduler
        gateway_db = scheduler._adapt_gateway_repository(db)
        auto_refresh_enabled = is_factory_factor_auto_refresh_enabled()
        refresh_meta: dict[str, Any] = {
            "auto_refresh_enabled": auto_refresh_enabled,
            "refresh_attempted": False,
            "refresh_status": "not_needed",
            "refresh_trigger": None,
            "refresh_error": None,
            "refreshed_before_build": False,
            "refresh_result": {},
            "refresh_timeout_sec": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
        }
        artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
        summary = dict(artifact.get("summary") or {})
        refresh_trigger = resolve_factor_refresh_trigger(artifact, factor_summary=summary)
        should_refresh = bool(auto_refresh_enabled and refresh_trigger)
        refresh = getattr(factor_gateway, "refresh", None)
        if should_refresh:
            refresh_meta["refresh_attempted"] = True
            refresh_meta["refresh_trigger"] = refresh_trigger
            if callable(refresh):
                try:
                    refresh_result = refresh()
                    if inspect.isawaitable(refresh_result):
                        refresh_result = await asyncio.wait_for(
                            refresh_result,
                            timeout=FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
                        )
                    refresh_meta["refresh_status"] = "success"
                    refresh_meta["refresh_result"] = scheduler._summarize_refresh_result(refresh_result)
                    refresh_meta["refreshed_before_build"] = True
                    artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
                except asyncio.TimeoutError:
                    refresh_meta["refresh_status"] = "timeout"
                    refresh_meta["refresh_error"] = (
                        f"factor refresh exceeded {FACTORY_FACTOR_REFRESH_TIMEOUT_SEC}s"
                    )
                except Exception as exc:
                    refresh_meta["refresh_status"] = "failed"
                    refresh_meta["refresh_error"] = str(exc)
            else:
                refresh_meta["refresh_status"] = "unsupported"
                refresh_meta["refresh_error"] = "factor gateway does not expose refresh()"
        elif not auto_refresh_enabled:
            refresh_meta["refresh_status"] = "disabled"
        return scheduler._inject_factor_refresh_meta(artifact, refresh_meta)

    def _build_factory_readiness(
        self,
        snapshot: dict[str, Any],
        factor_research: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self._readiness_service.evaluate(snapshot, factor_research)

    async def _persist_enriched_snapshot(self, db, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        method = getattr(db, "save_daily_snapshot", None)
        if not callable(method):
            return None
        try:
            result = method(
                snapshot.get("date") or self._scheduler._now().date(),
                snapshot,
            )
            if inspect.isawaitable(result):
                await result
            return None
        except Exception as exc:
            logger.warning("StrategyFactory: enriched snapshot persistence failed: %s", exc)
            return {
                "operation": "save_daily_snapshot",
                "stage": "collect",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }

    def _build_research_plane(
        self,
        *,
        snapshot: dict[str, Any],
        readiness: dict[str, Any] | None = None,
        autonomy_stage: dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
        experiments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return build_research_plane_artifact(
            factor_research=snapshot.get("factor_research"),
            readiness=readiness,
            autonomy_stage=autonomy_stage,
            candidates=candidates,
            experiments=experiments,
        )

    @staticmethod
    def _build_governance_plane(
        *,
        quality_gate_report: dict[str, Any] | None = None,
        backtest_report: dict[str, Any] | None = None,
        dedup_report: dict[str, Any] | None = None,
        submit_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_governance_plane_artifact(
            quality_gate_report=quality_gate_report,
            backtest_report=backtest_report,
            dedup_report=dedup_report,
            submit_result=submit_result,
        )

    @staticmethod
    def _apply_research_plane_summary(
        summary: dict[str, Any],
        research_plane: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(summary or {})
        plane = dict(research_plane or {})
        research_artifact = dict(plane.get("research_artifact") or {})
        task_artifact = dict(plane.get("task_artifact") or {})
        candidate_artifact = dict(plane.get("candidate_artifact") or {})
        evidence_artifact = dict(plane.get("evidence_artifact") or {})
        payload.update(
            {
                "research_plane_contract_version": plane.get("contract_version"),
                "research_plane_available": bool(plane.get("available")),
                "research_artifact_contract_version": research_artifact.get("contract_version"),
                "research_task_artifact_contract_version": task_artifact.get("contract_version"),
                "research_candidate_artifact_contract_version": candidate_artifact.get("contract_version"),
                "research_evidence_artifact_contract_version": evidence_artifact.get("contract_version"),
                "research_task_artifact_available": bool(task_artifact.get("available")),
                "research_candidate_artifact_available": bool(candidate_artifact.get("available")),
                "research_evidence_artifact_available": bool(evidence_artifact.get("available")),
                "research_task_count": int(task_artifact.get("planned_task_count") or 0),
                "research_candidate_count": int(candidate_artifact.get("candidate_count") or 0),
                "research_experiment_count": int(evidence_artifact.get("experiment_count") or 0),
                "research_task_evidence_count": int(evidence_artifact.get("task_evidence_count") or 0),
                "lifecycle_feedback_input_contract_version": research_artifact.get(
                    "lifecycle_feedback_input_contract_version"
                ),
                "lifecycle_feedback_input_available": bool(
                    research_artifact.get("lifecycle_feedback_input_available")
                ),
                "lifecycle_feedback_family_count": int(
                    research_artifact.get("lifecycle_feedback_family_count") or 0
                ),
                "lifecycle_feedback_strategy_count": int(
                    research_artifact.get("lifecycle_feedback_strategy_count") or 0
                ),
                "lifecycle_feedback_target_pool_scope_count": int(
                    research_artifact.get("lifecycle_feedback_target_pool_scope_count") or 0
                ),
                "lifecycle_feedback_generator_mode_scope_count": int(
                    research_artifact.get("lifecycle_feedback_generator_mode_scope_count") or 0
                ),
                "lifecycle_feedback_runtime_alert_count": int(
                    research_artifact.get("lifecycle_feedback_runtime_alert_count") or 0
                ),
                "lifecycle_feedback_runtime_risk_event_count": int(
                    research_artifact.get("lifecycle_feedback_runtime_risk_event_count") or 0
                ),
                "lifecycle_feedback_promotion_review_count": int(
                    research_artifact.get("lifecycle_feedback_promotion_review_count") or 0
                ),
                "lifecycle_feedback_promotion_review_status_counts": dict(
                    research_artifact.get("lifecycle_feedback_promotion_review_status_counts") or {}
                ),
            }
        )
        return payload

    @staticmethod
    def _apply_governance_plane_summary(
        summary: dict[str, Any],
        governance_plane: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(summary or {})
        plane = dict(governance_plane or {})
        gate_artifact = dict(plane.get("gate_artifact") or {})
        dedup_artifact = dict(plane.get("dedup_artifact") or {})
        submission_artifact = dict(plane.get("submission_artifact") or {})
        evidence_artifact = dict(plane.get("evidence_artifact") or {})
        payload.update(
            {
                "governance_plane_contract_version": plane.get("contract_version"),
                "governance_plane_available": bool(plane.get("available")),
                "governance_gate_artifact_contract_version": gate_artifact.get("contract_version"),
                "governance_dedup_artifact_contract_version": dedup_artifact.get("contract_version"),
                "governance_submission_artifact_contract_version": submission_artifact.get(
                    "contract_version"
                ),
                "governance_evidence_artifact_contract_version": evidence_artifact.get(
                    "contract_version"
                ),
                "governance_gate_artifact_available": bool(gate_artifact.get("available")),
                "governance_dedup_artifact_available": bool(dedup_artifact.get("available")),
                "governance_submission_artifact_available": bool(
                    submission_artifact.get("available")
                ),
                "governance_evidence_artifact_available": bool(evidence_artifact.get("available")),
                "governance_gate_2_passed": int(gate_artifact.get("gate_2_passed") or 0),
                "governance_after_dedup": int(dedup_artifact.get("kept_count") or 0),
                "governance_gate_3_passed": int(submission_artifact.get("gate_3_passed") or 0),
                "governance_refresh_existing_count": int(
                    dedup_artifact.get("refreshed_existing_count") or 0
                ),
                "governance_multiple_testing_registry_count": int(
                    evidence_artifact.get("multiple_testing_registry_count") or 0
                ),
                "governance_vector_profile_count": int(
                    evidence_artifact.get("vector_profile_count") or 0
                ),
            }
        )
        return payload

    async def run(self) -> FactoryCycleOutcome:
        scheduler = self._scheduler
        db = self._context.db
        factory_pkg = self._context.factory_pkg
        start = self._context.start
        trace_id = self._context.trace_id
        results: FactoryRunResult = {
            "run_id": self._context.run_id,
            "trace_id": trace_id,
            "started_at": start.isoformat(),
            "status": "running",
            "summary": {},
            "stages": {},
        }
        persistence_failures: list[dict[str, Any]] = []

        logger.info("StrategyFactory: starting daily cycle")

        if not is_factory_runtime_enabled():
            readiness_authority = build_readiness_authority(
                can_proceed=False,
                hard_gate_enabled=is_factory_readiness_hard_block_enabled(),
                blocking_reason_codes=["runtime_disabled"],
                critical_blocking_reason_codes=["runtime_disabled"],
                skip_reason="runtime_disabled",
            )
            results["status"] = FactoryRunStatus.SKIPPED.value
            results["completed_at"] = scheduler._now().isoformat()
            results["elapsed_seconds"] = 0.0
            results["stages"]["readiness"] = scheduler._with_stage_meta(
                "readiness",
                trace_id,
                {
                    "readiness_contract_version": READINESS_CONTRACT_VERSION,
                    "runtime_enabled": False,
                    "event_runtime_mode": resolve_event_runtime_mode(),
                    "hard_block_enabled": is_factory_readiness_hard_block_enabled(),
                    "readiness_score": 0.0,
                    "can_proceed": False,
                    "warnings": [],
                    "warning_count": 0,
                    "blockers": ["runtime_disabled"],
                    "blocker_count": 1,
                    "critical_blockers": ["runtime_disabled"],
                    "critical_blocker_count": 1,
                    "authority": readiness_authority,
                    "authority_contract_version": readiness_authority.get("authority_contract_version"),
                    "decision": readiness_authority.get("decision"),
                    "blocked": readiness_authority.get("blocked"),
                    "hard_gate": readiness_authority.get("hard_gate"),
                    "gate_mode": readiness_authority.get("gate_mode"),
                    "blocking_stage": readiness_authority.get("blocking_stage"),
                    "blocking_reason_codes": list(
                        readiness_authority.get("blocking_reason_codes") or []
                    ),
                    "critical_blocking_reason_codes": list(
                        readiness_authority.get("critical_blocking_reason_codes") or []
                    ),
                    "skip_reason": readiness_authority.get("skip_reason"),
                },
                status=StageStatus.SKIPPED,
                ok=True,
                skip_reason="runtime_disabled",
            )
            results["summary"] = {
                "trace_id": trace_id,
                "runtime_enabled": False,
                "event_runtime_mode": resolve_event_runtime_mode(),
                "factory_readiness_contract_version": READINESS_CONTRACT_VERSION,
                "factory_readiness_authority_version": readiness_authority.get(
                    "authority_contract_version"
                ),
                "factory_readiness_decision": readiness_authority.get("decision"),
                "factory_readiness_hard_gate": readiness_authority.get("hard_gate"),
                "factory_readiness_blocking_stage": readiness_authority.get("blocking_stage"),
                "factory_readiness_blocking_reason_codes": list(
                    readiness_authority.get("blocking_reason_codes") or []
                ),
                "factory_readiness_critical_blocking_reason_codes": list(
                    readiness_authority.get("critical_blocking_reason_codes") or []
                ),
                "factory_readiness_score": 0.0,
                "factory_readiness_can_proceed": False,
                "factory_readiness_blocker_count": 1,
                "factory_readiness_warning_count": 0,
                "skip_reason": readiness_authority.get("skip_reason"),
                "elapsed_seconds": 0.0,
            }
            governance_plane = self._build_governance_plane()
            results["governance_plane"] = governance_plane
            results["summary"] = self._apply_governance_plane_summary(
                results["summary"],
                governance_plane,
            )
            results["summary"].update(scheduler._build_layered_run_summary(results["summary"], None))
            scheduler._apply_run_audit(results, persistence_failures=persistence_failures)
            return FactoryCycleOutcome(results, persistence_failures)

        try:
            warmup_result = await scheduler._run_startup_warmup()
            warmup_status = StageStatus.COMPLETED
            if str(warmup_result.get("status") or "").strip().lower() in {"disabled", "skipped"}:
                warmup_status = StageStatus.SKIPPED
            elif not bool(warmup_result.get("ok", True)):
                warmup_status = StageStatus.FAILED
            elif int(warmup_result.get("failed") or 0) > 0:
                warmup_status = StageStatus.PARTIAL
            results["stages"]["warmup"] = scheduler._with_stage_meta(
                "warmup",
                trace_id,
                warmup_result,
                status=warmup_status,
                ok=warmup_status != StageStatus.FAILED,
                hard_failure=warmup_status == StageStatus.FAILED,
                degraded=warmup_status == StageStatus.PARTIAL,
            )

            collector = factory_pkg.DataCollector()
            snapshot = await collector.collect(db)
            # P2-D：将调度器累积的 family 历史表现注入 snapshot
            _family_feedback = dict(getattr(scheduler, "_family_gate_feedback", {}) or {})
            if _family_feedback:
                snapshot["family_gate_feedback"] = _family_feedback
            results["snapshot_summary"] = {
                "date": snapshot.get("date"),
                "fear_greed": snapshot.get("fear_greed_index"),
                "fear_greed_index": snapshot.get("fear_greed_index"),
                "fg_level": snapshot.get("fg_level"),
                "listed_count": snapshot.get("listed_count", 0),
                "incubating_count": snapshot.get("incubating_count", 0),
                "degraded": bool(snapshot.get("degraded")),
                "completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "missing_sources": (snapshot.get("completeness") or {}).get("missing_sources") or [],
                "failure_reason_count": len(snapshot.get("failure_reasons") or []),
            }
            results["stages"]["collect"] = scheduler._with_stage_meta(
                "collect",
                trace_id,
                {
                    **results["snapshot_summary"],
                    "completeness": snapshot.get("completeness") or {},
                },
                status=StageStatus.PARTIAL if bool(snapshot.get("degraded")) else StageStatus.COMPLETED,
            )

            factor_research = {}
            try:
                factor_gateway = scheduler._get_factor_research_gateway()
                factor_research = await self._build_factor_research_artifact(
                    factor_gateway,
                    db,
                    snapshot,
                )
                snapshot["factor_research"] = dict(factor_research or {})
                factor_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
                compact_factor_research = scheduler._compact_factor_research_snapshot(snapshot.get("factor_research"))
                results["stages"]["factor_research"] = scheduler._with_stage_meta(
                    "factor_research",
                    trace_id,
                    {
                        "active_factor_count": int(factor_summary.get("active_factor_count") or 0),
                        "active_candidate_count": int(factor_summary.get("active_candidate_count") or 0),
                        "active_family_count": len(list(factor_summary.get("active_family_names") or [])),
                        "active_regime_count": len(list(factor_summary.get("active_regime_names") or [])),
                        "ranked_factor_count": int(factor_summary.get("ranked_factor_count") or 0),
                        "top_factor_names": list(factor_summary.get("top_factor_names") or []),
                        "top_candidate_names": list(factor_summary.get("top_candidate_names") or []),
                        "active_family_names": list(factor_summary.get("active_family_names") or []),
                        "active_regime_names": list(factor_summary.get("active_regime_names") or []),
                        "preferred_strategy_types": list(factor_summary.get("preferred_strategy_types") or []),
                        "factor_source_mode": factor_summary.get("factor_source_mode"),
                        "governed_candidate_pool_mode": factor_summary.get("governed_candidate_pool_mode"),
                        "governed_candidate_pool_provisional": bool(
                            factor_summary.get("governed_candidate_pool_provisional")
                        ),
                        "degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                        "freshness_days": factor_summary.get("freshness_days"),
                        "governed_freshness_days": factor_summary.get("governed_freshness_days"),
                        "governed_blocked_ratio": factor_summary.get("governed_blocked_ratio"),
                        "governed_latest_candidate_at": factor_summary.get("governed_latest_candidate_at"),
                        "latest_factor_date": factor_summary.get("latest_factor_date"),
                        "scheduler_recent_success": bool(factor_summary.get("scheduler_recent_success")),
                        "scheduler_llm_validation_status": factor_summary.get("scheduler_llm_validation_status"),
                        "stock_family_allocation_count": int(factor_summary.get("stock_family_allocation_count") or 0),
                        "stock_family_allocation_entropy": factor_summary.get("stock_family_allocation_entropy"),
                        "stock_family_allocation_source_mode": factor_summary.get("stock_family_allocation_source_mode"),
                        "quality_flags": list(factor_summary.get("quality_flags") or []),
                        "refresh_attempted": bool(factor_summary.get("refresh_attempted")),
                        "refresh_status": factor_summary.get("refresh_status"),
                        "refresh_trigger": factor_summary.get("refresh_trigger"),
                        "refresh_error": factor_summary.get("refresh_error"),
                        "active_candidate_pool": compact_factor_research.get("active_candidate_pool") or {},
                        "source_chain": list((snapshot.get("factor_research") or {}).get("source_chain") or []),
                    },
                    status=(
                        StageStatus.PARTIAL
                        if bool((snapshot.get("factor_research") or {}).get("degraded"))
                        or bool(factor_summary.get("stale"))
                        or (
                            bool(factor_summary.get("refresh_attempted"))
                            and str(factor_summary.get("refresh_status") or "").strip().lower()
                            not in {"success", "not_needed", "disabled"}
                        )
                        else StageStatus.COMPLETED
                    ),
                )
            except Exception as exc:
                logger.warning("StrategyFactory: factor research stage failed: %s", exc)
                snapshot["factor_research"] = {
                    "active_factors": [],
                    "ranked_factors": [],
                    "positive_rising_factors": [],
                    "preferred_strategy_types": [],
                    "governed_candidates": [],
                    "active_candidate_pool": {},
                    "active_family_summary": [],
                    "active_regime_summary": [],
                    "research_rationale": [str(exc)],
                    "source_chain": ["factor_research_error"],
                    "degraded": True,
                    "summary": {
                        "active_factor_count": 0,
                        "active_candidate_count": 0,
                        "ranked_factor_count": 0,
                        "top_factor_names": [],
                        "top_candidate_names": [],
                        "active_family_names": [],
                        "active_regime_names": [],
                        "preferred_strategy_types": [],
                        "factor_source_mode": "error_fallback",
                        "governed_blocked_ratio": 0.0,
                        "governed_freshness_days": None,
                        "governed_latest_candidate_at": None,
                        "scheduler_recent_success": False,
                        "scheduler_llm_validation_status": None,
                        "degraded": True,
                        "quality_flags": ["failed"],
                    },
                }
                results["stages"]["factor_research"] = scheduler._with_stage_meta(
                    "factor_research",
                    trace_id,
                    {
                        "active_factor_count": 0,
                        "active_candidate_count": 0,
                        "active_family_count": 0,
                        "active_regime_count": 0,
                        "ranked_factor_count": 0,
                        "top_factor_names": [],
                        "top_candidate_names": [],
                        "active_family_names": [],
                        "active_regime_names": [],
                        "preferred_strategy_types": [],
                        "factor_source_mode": "error_fallback",
                        "governed_blocked_ratio": 0.0,
                        "governed_freshness_days": None,
                        "governed_latest_candidate_at": None,
                        "scheduler_recent_success": False,
                        "scheduler_llm_validation_status": None,
                        "degraded": True,
                        "quality_flags": ["failed"],
                        "error": str(exc),
                    },
                    status=StageStatus.FAILED,
                    ok=False,
                    hard_failure=True,
                    degraded=True,
                )

            results["snapshot_summary"] = {
                **dict(results.get("snapshot_summary") or {}),
                "factor_research": scheduler._compact_factor_research_snapshot(snapshot.get("factor_research")),
            }

            readiness = self._build_factory_readiness(snapshot, snapshot.get("factor_research"))
            snapshot["factory_readiness"] = readiness
            readiness_status = StageStatus.COMPLETED
            readiness_event_status = str(readiness.get("event_status") or "").strip().lower()
            readiness_refresh_status = str(readiness.get("factor_refresh_status") or "").strip().lower()
            readiness_degraded = bool(
                readiness.get("snapshot_degraded")
                or readiness.get("factor_research_degraded")
                or readiness.get("factor_research_stale")
                or (
                    bool(readiness.get("factor_refresh_attempted"))
                    and readiness_refresh_status not in {"success", "not_needed", "disabled"}
                )
                or readiness_event_status in {"partial", "failed", "fallback", "error"}
            )
            if not bool(readiness.get("can_proceed")):
                readiness_status = StageStatus.FAILED
            elif readiness_degraded:
                readiness_status = StageStatus.PARTIAL
            results["stages"]["readiness"] = scheduler._with_stage_meta(
                "readiness",
                trace_id,
                readiness,
                status=readiness_status,
                ok=readiness_status != StageStatus.FAILED,
                hard_failure=False,
                degraded=readiness_status == StageStatus.PARTIAL,
            )
            research_plane = self._build_research_plane(
                snapshot=snapshot,
                readiness=readiness,
            )
            results["research_plane"] = research_plane
            governance_plane = self._build_governance_plane()
            results["governance_plane"] = governance_plane
            if "factor_research" in results.get("stages", {}):
                results["stages"]["factor_research"]["research_plane_contract_version"] = (
                    research_plane.get("contract_version")
                )
                results["stages"]["factor_research"]["research_artifact"] = dict(
                    research_plane.get("research_artifact") or {}
                )
            snapshot_persist_failure = await self._persist_enriched_snapshot(db, snapshot)
            if snapshot_persist_failure is not None:
                persistence_failures.append(snapshot_persist_failure)

            if not bool(readiness.get("can_proceed")):
                elapsed = (scheduler._now() - start).total_seconds()
                factor_research_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
                factor_refresh_summary = dict((snapshot.get("factor_research") or {}).get("freshness_repair") or {})
                results["status"] = FactoryRunStatus.SKIPPED.value
                results["completed_at"] = scheduler._now().isoformat()
                results["elapsed_seconds"] = round(elapsed, 1)
                results["summary"] = {
                    "trace_id": trace_id,
                    "runtime_enabled": bool(readiness.get("runtime_enabled")),
                    "event_runtime_mode": readiness.get("event_runtime_mode"),
                    "factory_readiness_contract_version": readiness.get("readiness_contract_version"),
                    "factory_readiness_authority_version": readiness.get(
                        "authority_contract_version"
                    ),
                    "factory_readiness_decision": readiness.get("decision"),
                    "factory_readiness_hard_gate": readiness.get("hard_gate"),
                    "factory_readiness_blocking_stage": readiness.get("blocking_stage"),
                    "factory_readiness_blocking_reason_codes": list(
                        readiness.get("blocking_reason_codes") or []
                    ),
                    "factory_readiness_critical_blocking_reason_codes": list(
                        readiness.get("critical_blocking_reason_codes") or []
                    ),
                    "factory_readiness_score": readiness.get("readiness_score"),
                    "factory_readiness_can_proceed": False,
                    "factory_readiness_blocker_count": readiness.get("blocker_count", 0),
                    "factory_readiness_warning_count": readiness.get("warning_count", 0),
                    "factor_source_mode": readiness.get("factor_source_mode"),
                    "governed_candidate_pool_active": bool(readiness.get("governed_candidate_pool_active")),
                    "governed_candidate_pool_runtime_state": readiness.get("governed_candidate_pool_runtime_state"),
                    "active_candidate_count": int(readiness.get("active_candidate_count") or 0),
                    "governed_source_candidate_count": int(readiness.get("governed_source_candidate_count") or 0),
                    "governed_blocked_candidate_count": int(readiness.get("governed_blocked_candidate_count") or 0),
                    "governed_blocked_ratio": readiness.get("governed_blocked_ratio"),
                    "governed_freshness_days": readiness.get("governed_freshness_days"),
                    "scheduler_recent_success": bool(readiness.get("scheduler_recent_success")),
                    "scheduler_llm_validation_status": readiness.get("scheduler_llm_validation_status"),
                    "factor_llm_provider_enabled": factor_research_summary.get("factor_llm_provider_enabled"),
                    "factor_llm_provider_ready": factor_research_summary.get("factor_llm_provider_ready"),
                    "factor_llm_provider_health_status": factor_research_summary.get("factor_llm_provider_health_status"),
                    "factor_llm_provider_rebuild_count": factor_research_summary.get("factor_llm_provider_rebuild_count"),
                    "factor_llm_provider_last_error_type": factor_research_summary.get("factor_llm_provider_last_error_type"),
                    "factor_research_stale": bool(factor_research_summary.get("stale")),
                    "factor_research_degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                    "factor_research_refresh_attempted": bool(factor_refresh_summary.get("refresh_attempted")),
                    "factor_research_refresh_status": factor_refresh_summary.get("refresh_status"),
                    "factor_research_refresh_trigger": factor_refresh_summary.get("refresh_trigger"),
                    "governed_exclusion_reason_counts": dict(readiness.get("governed_exclusion_reason_counts") or {}),
                    "governed_risk_counts": dict(readiness.get("governed_risk_counts") or {}),
                    "skip_reason": readiness.get("skip_reason") or "readiness_blocked",
                    "elapsed_seconds": round(elapsed, 1),
                }
                results["summary"] = self._apply_research_plane_summary(
                    results["summary"],
                    research_plane,
                )
                results["summary"] = self._apply_governance_plane_summary(
                    results["summary"],
                    governance_plane,
                )
                results["summary"].update(scheduler._build_layered_run_summary(results["summary"], None))
                logger.warning(
                    "StrategyFactory: run %s blocked by readiness controls: %s",
                    results.get("run_id"),
                    readiness.get("blockers"),
                )
                scheduler._apply_run_audit(results, persistence_failures=persistence_failures)
                return FactoryCycleOutcome(results, persistence_failures)

            spawner = factory_pkg.StrategySpawner()
            candidates = spawner.spawn(snapshot)
            spawn_report = (
                spawner.get_last_report()
                if hasattr(spawner, "get_last_report")
                else {"summary": {"candidate_count": len(candidates)}}
            )
            results["stages"]["spawn"] = scheduler._with_stage_meta(
                "spawn",
                trace_id,
                {"count": len(candidates), **spawn_report},
                status=StageStatus.COMPLETED,
            )

            autonomy_batch = {"stage": {"generated_count": 0}, "candidates": [], "experiments": []}
            autonomy_stage = {"generated_count": 0}
            autonomy_experiments: list[dict[str, Any]] = []
            try:
                autonomy_batch = await scheduler._run_autonomy_batches(db, snapshot)
                ai_candidates = autonomy_batch.get("candidates") or []
                autonomy_stage = autonomy_batch.get("stage") or {}
                autonomy_experiments = list(autonomy_batch.get("experiments") or [])
                factory_attempt_count = int(autonomy_stage.get("external_llm_attempt_count") or 0)
                factory_stage_attempt_count = int(
                    autonomy_stage.get("external_llm_stage_attempt_count")
                    or factory_attempt_count
                )
                factory_network_request_count = int(
                    autonomy_stage.get("external_llm_network_request_count") or 0
                )
                factory_compatibility_skip_count = int(
                    autonomy_stage.get("external_llm_compatibility_skip_count") or 0
                )
                factory_cooldown_skip_count = int(
                    autonomy_stage.get("external_llm_cooldown_skip_count") or 0
                )
                factory_selected_count = int(autonomy_stage.get("external_llm_selected_count") or 0)
                for ai_candidate in ai_candidates:
                    params = dict(ai_candidate.get("params") or {})
                    params["factory_attempt_count"] = factory_attempt_count
                    params["factory_stage_attempt_count"] = factory_stage_attempt_count
                    params["factory_network_request_count"] = factory_network_request_count
                    params["factory_compatibility_skip_count"] = factory_compatibility_skip_count
                    params["factory_cooldown_skip_count"] = factory_cooldown_skip_count
                    params["factory_selected_count"] = factory_selected_count
                    ai_candidate["params"] = params
                candidates = [*candidates, *ai_candidates]
                candidates = [
                    apply_candidate_strategy_profile(candidate, snapshot=snapshot)
                    for candidate in candidates
                ]
                autonomy_stage = autonomy_batch.get("stage") or {"generated_count": len(ai_candidates)}
                autonomy_stage_status = StageStatus.COMPLETED
                external_llm_status = str(autonomy_stage.get("external_llm_status") or "").strip().lower()
                if external_llm_status == "failed":
                    autonomy_stage_status = StageStatus.FAILED
                elif external_llm_status in {"partial"} or int(autonomy_stage.get("persistence_failure_count") or 0) > 0:
                    autonomy_stage_status = StageStatus.PARTIAL
                elif external_llm_status == "skipped":
                    autonomy_stage_status = StageStatus.SKIPPED
                results["stages"]["autonomy"] = scheduler._with_stage_meta(
                    "autonomy",
                    trace_id,
                    autonomy_stage,
                    status=autonomy_stage_status,
                    ok=autonomy_stage_status != StageStatus.FAILED,
                    hard_failure=autonomy_stage_status == StageStatus.FAILED,
                    degraded=autonomy_stage_status == StageStatus.PARTIAL,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: autonomy cycle failed: %s", exc)
                candidates = [
                    apply_candidate_strategy_profile(candidate, snapshot=snapshot)
                    for candidate in candidates
                ]
                autonomy_stage = {"error": str(exc), "generated_count": 0}
                results["stages"]["autonomy"] = scheduler._with_stage_meta(
                    "autonomy",
                    trace_id,
                    autonomy_stage,
                    status=StageStatus.FAILED,
                    ok=False,
                    hard_failure=True,
                    degraded=True,
                )

            research_plane = self._build_research_plane(
                snapshot=snapshot,
                readiness=readiness,
                autonomy_stage=autonomy_stage,
                candidates=candidates,
                experiments=autonomy_experiments,
            )
            results["research_plane"] = research_plane
            if "factor_research" in results.get("stages", {}):
                results["stages"]["factor_research"]["research_plane_contract_version"] = (
                    research_plane.get("contract_version")
                )
                results["stages"]["factor_research"]["research_artifact"] = dict(
                    research_plane.get("research_artifact") or {}
                )
            if "autonomy" in results.get("stages", {}):
                results["stages"]["autonomy"]["research_plane_contract_version"] = (
                    research_plane.get("contract_version")
                )
                results["stages"]["autonomy"]["task_artifact"] = dict(
                    research_plane.get("task_artifact") or {}
                )
                results["stages"]["autonomy"]["candidate_artifact"] = dict(
                    research_plane.get("candidate_artifact") or {}
                )
                results["stages"]["autonomy"]["evidence_artifact"] = dict(
                    research_plane.get("evidence_artifact") or {}
                )

            backtest_filter = factory_pkg.BacktestFilter()
            supports_unified_gate_runner = bool(
                candidates
                and hasattr(factory_pkg, "run_gated_filter")
                and inspect.iscoroutinefunction(getattr(db, "get_klines", None))
            )
            deduplicator = scheduler._build_deduplicator(factory_pkg)
            submitter = scheduler._build_submitter(factory_pkg)
            supports_unified_submission_runner = bool(
                supports_unified_gate_runner
                and hasattr(factory_pkg, "run_gated_submission_pipeline")
            )

            if supports_unified_submission_runner:
                pipeline_run = await factory_pkg.run_gated_submission_pipeline(
                    candidates,
                    snapshot,
                    db,
                    backtest_filter=backtest_filter,
                    deduplicator=deduplicator,
                    submitter=submitter,
                    gated_runner=factory_pkg.run_gated_filter,
                    kline_cache=getattr(backtest_filter, "_kline_cache", None),
                )
                passed = list(pipeline_run.get("passed") or [])
                unique = list(pipeline_run.get("unique") or [])
                quality_gate_report = dict(pipeline_run.get("gate_report") or pipeline_run.get("quality_gate") or {})
                backtest_report = dict(pipeline_run.get("backtest_report") or {})
                submit_result = dict(pipeline_run.get("submit_result") or {})
            else:
                if supports_unified_gate_runner:
                    gate_run = await factory_pkg.run_gated_filter(
                        candidates,
                        db,
                        backtest_filter,
                        kline_cache=getattr(backtest_filter, "_kline_cache", None),
                    )
                    passed = list(gate_run.get("passed") or [])
                    quality_gate_report = dict(gate_run.get("gate_report") or gate_run.get("quality_gate") or {})
                else:
                    passed = await backtest_filter.filter(candidates, db)
                    quality_gate_report = {}

                backtest_report = (
                    (quality_gate_report.get("gate_2") or {}).get("report")
                    or (
                        backtest_filter.get_last_report()
                        if hasattr(backtest_filter, "get_last_report")
                        else {
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
                    )
                )
                if not quality_gate_report:
                    quality_gate_report = factory_pkg.build_legacy_gate_report(candidates, passed, backtest_report)

                unique = await deduplicator.deduplicate(passed, db)
                submit_result = await submitter.submit(unique, snapshot, db)
                quality_gate_report = factory_pkg.finalize_gate_report(quality_gate_report, submit_result)

            backtest_summary = backtest_report.get("summary") or {}
            results["stages"]["quality_gate"] = scheduler._with_stage_meta(
                "quality_gate",
                trace_id,
                quality_gate_report,
                status=StageStatus.COMPLETED,
            )
            results["stages"]["backtest"] = scheduler._with_stage_meta(
                "backtest",
                trace_id,
                {
                    "input_count": backtest_summary.get("input_count", len(candidates)),
                    "passed_count": backtest_summary.get("passed_count", len(passed)),
                    "failed_count": backtest_summary.get("failed_count", max(len(candidates) - len(passed), 0)),
                    **backtest_report,
                },
                status=StageStatus.COMPLETED,
            )
            results["stages"]["deduplicate"] = scheduler._with_stage_meta(
                "deduplicate",
                trace_id,
                deduplicator.get_last_report(),
                status=StageStatus.COMPLETED,
            )
            results["stages"]["submit"] = scheduler._with_stage_meta(
                "submit",
                trace_id,
                submit_result,
                status=StageStatus.COMPLETED,
            )
            results["quality_gate"] = quality_gate_report
            results["gate_report"] = quality_gate_report

            eliminator = factory_pkg.EliminationChecker()
            eliminated = await eliminator.check(db, snapshot.get("fg_level", "neutral"))
            results["stages"]["elimination"] = scheduler._with_stage_meta(
                "elimination",
                trace_id,
                {"count": len(eliminated), "items": eliminated},
                status=StageStatus.COMPLETED,
            )

            elapsed = (scheduler._now() - start).total_seconds()
            results["status"] = FactoryRunStatus.SUCCESS.value
            results["completed_at"] = scheduler._now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            autonomy_summary = results.get("stages", {}).get("autonomy") or {}
            vector_summary = scheduler._aggregate_vector_submission_metrics(submit_result)
            task_scan_summary = dict((autonomy_summary.get("task_scan") or {}).get("summary") or {})
            task_source_counts = dict(
                autonomy_summary.get("task_source_counts")
                or task_scan_summary.get("task_sources")
                or {}
            )
            bulk_stock_matrix_family_counts = dict(
                task_scan_summary.get("bulk_stock_matrix_family_counts") or {}
            )
            bulk_stock_matrix_allocation_pass_counts = dict(
                task_scan_summary.get("bulk_stock_matrix_allocation_pass_counts") or {}
            )
            snapshot_task_count = int(
                autonomy_summary.get("snapshot_task_count")
                or task_source_counts.get("snapshot", 0)
            )
            autonomy_task_briefs = [
                {
                    "task_id": (item.get("task") or {}).get("task_id"),
                    "task_source": (item.get("task") or {}).get("task_source"),
                    "opportunity_type": (item.get("task") or {}).get("opportunity_type"),
                    "target_symbols": list((item.get("task") or {}).get("target_symbols") or []),
                    "candidate_family": (item.get("task") or {}).get("candidate_family"),
                    "source_candidate_artifact_id": (item.get("task") or {}).get("source_candidate_artifact_id"),
                    "factor_name": (item.get("task") or {}).get("factor_name"),
                    "generation_limit": (item.get("task") or {}).get("generation_limit"),
                    "generated_count": item.get("generated_count", 0),
                }
                for item in list(autonomy_summary.get("task_results") or [])
            ]
            factor_research_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
            factor_refresh_summary = dict((snapshot.get("factor_research") or {}).get("freshness_repair") or {})
            gate_0_summary = dict(quality_gate_report.get("gate_0") or {})
            pre_gate_summary = dict(quality_gate_report.get("pre_gate") or {})
            gate_1_summary = dict(quality_gate_report.get("gate_1") or {})
            gate_2_summary = dict(quality_gate_report.get("gate_2") or {})
            readiness_summary = dict(results.get("stages", {}).get("readiness") or {})
            warmup_summary = dict(results.get("stages", {}).get("warmup") or {})
            backtest_audit_summary = scheduler._aggregate_backtest_audit_metrics(backtest_report)
            submission_audit_summary = scheduler._aggregate_submission_audit_metrics(submit_result)
            results["summary"] = {
                "trace_id": trace_id,
                "runtime_enabled": bool(readiness_summary.get("runtime_enabled", True)),
                "event_runtime_mode": readiness_summary.get("event_runtime_mode"),
                "factory_readiness_contract_version": readiness_summary.get(
                    "readiness_contract_version"
                ),
                "factory_readiness_authority_version": readiness_summary.get(
                    "authority_contract_version"
                ),
                "factory_readiness_decision": readiness_summary.get("decision"),
                "factory_readiness_hard_gate": readiness_summary.get("hard_gate"),
                "factory_readiness_blocking_stage": readiness_summary.get("blocking_stage"),
                "factory_readiness_blocking_reason_codes": list(
                    readiness_summary.get("blocking_reason_codes") or []
                ),
                "factory_readiness_critical_blocking_reason_codes": list(
                    readiness_summary.get("critical_blocking_reason_codes") or []
                ),
                "factory_readiness_score": readiness_summary.get("readiness_score"),
                "factory_readiness_can_proceed": readiness_summary.get("can_proceed"),
                "factory_readiness_blocker_count": readiness_summary.get("blocker_count", 0),
                "factory_readiness_warning_count": readiness_summary.get("warning_count", 0),
                "fear_greed": snapshot.get("fear_greed_index"),
                "listed_count": snapshot.get("listed_count", 0),
                "snapshot_degraded": bool(snapshot.get("degraded")),
                "snapshot_completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "snapshot_failure_reason_count": len(snapshot.get("failure_reasons") or []),
                "warmup_status": warmup_summary.get("status"),
                "warmup_task_type": warmup_summary.get("task_type"),
                "warmup_matched": int(warmup_summary.get("matched") or 0),
                "warmup_executed": int(warmup_summary.get("executed") or 0),
                "warmup_failed": int(warmup_summary.get("failed") or 0),
                "candidates_spawned": len(candidates),
                "autonomy_generated": autonomy_summary.get("generated_count", 0),
                "autonomy_task_count": autonomy_summary.get("task_count", 0),
                "autonomy_completed_task_count": autonomy_summary.get("completed_task_count", 0),
                "autonomy_failed_task_count": autonomy_summary.get("failed_task_count", 0),
                "event_task_count": autonomy_summary.get("event_task_count", 0),
                "snapshot_task_count": snapshot_task_count,
                "bulk_stock_task_count": autonomy_summary.get("bulk_stock_task_count", 0),
                "bulk_stock_matrix_enabled": bool(task_scan_summary.get("bulk_stock_matrix_enabled")),
                "bulk_stock_matrix_configured_enabled": bool(
                    task_scan_summary.get("bulk_stock_matrix_configured_enabled")
                ),
                "bulk_stock_matrix_stock_count": int(task_scan_summary.get("bulk_stock_matrix_stock_count") or 0),
                "bulk_stock_matrix_eligible_stock_count": int(task_scan_summary.get("bulk_stock_matrix_eligible_stock_count") or 0),
                "bulk_stock_matrix_loaded_stock_count": int(task_scan_summary.get("bulk_stock_matrix_loaded_stock_count") or 0),
                "bulk_stock_matrix_pages_loaded": int(task_scan_summary.get("bulk_stock_matrix_pages_loaded") or 0),
                "bulk_stock_matrix_analysis_complete": bool(task_scan_summary.get("bulk_stock_matrix_analysis_complete")),
                "bulk_stock_matrix_analysis_stock_coverage_ratio": task_scan_summary.get("bulk_stock_matrix_analysis_stock_coverage_ratio"),
                "bulk_stock_matrix_family_counts": bulk_stock_matrix_family_counts,
                "bulk_stock_matrix_planned_family_counts": dict(task_scan_summary.get("bulk_stock_matrix_planned_family_counts") or {}),
                "bulk_stock_matrix_universe_limit": int(task_scan_summary.get("bulk_stock_matrix_universe_limit") or 0),
                "bulk_stock_matrix_batch_count": int(task_scan_summary.get("bulk_stock_matrix_batch_count") or 0),
                "bulk_stock_matrix_selected_batch_count": int(task_scan_summary.get("bulk_stock_matrix_selected_batch_count") or 0),
                "bulk_stock_matrix_run_window": task_scan_summary.get("bulk_stock_matrix_run_window"),
                "bulk_stock_matrix_run_window_active": bool(task_scan_summary.get("bulk_stock_matrix_run_window_active")),
                "bulk_stock_matrix_run_window_current_period": task_scan_summary.get("bulk_stock_matrix_run_window_current_period"),
                "bulk_stock_matrix_skip_reason": task_scan_summary.get("bulk_stock_matrix_skip_reason"),
                "bulk_stock_matrix_requested_universe_offset": int(task_scan_summary.get("bulk_stock_matrix_requested_universe_offset") or 0),
                "bulk_stock_matrix_effective_universe_offset": int(task_scan_summary.get("bulk_stock_matrix_effective_universe_offset") or 0),
                "bulk_stock_matrix_universe_offset_fallback": bool(task_scan_summary.get("bulk_stock_matrix_universe_offset_fallback")),
                "bulk_stock_matrix_next_universe_offset": int(task_scan_summary.get("bulk_stock_matrix_next_universe_offset") or 0),
                "bulk_stock_matrix_cursor_wrapped": bool(task_scan_summary.get("bulk_stock_matrix_cursor_wrapped")),
                "bulk_stock_matrix_cursor_mode": task_scan_summary.get("bulk_stock_matrix_cursor_mode"),
                "bulk_stock_matrix_requested_task_offset": int(task_scan_summary.get("bulk_stock_matrix_requested_task_offset") or 0),
                "bulk_stock_matrix_effective_task_offset": int(task_scan_summary.get("bulk_stock_matrix_effective_task_offset") or 0),
                "bulk_stock_matrix_task_offset_fallback": bool(task_scan_summary.get("bulk_stock_matrix_task_offset_fallback")),
                "bulk_stock_matrix_next_task_offset": int(task_scan_summary.get("bulk_stock_matrix_next_task_offset") or 0),
                "bulk_stock_matrix_task_cursor_wrapped": bool(task_scan_summary.get("bulk_stock_matrix_task_cursor_wrapped")),
                "bulk_stock_matrix_cursor_source": task_scan_summary.get("bulk_stock_matrix_cursor_source"),
                "bulk_stock_matrix_cursor_resume_from_run_id": task_scan_summary.get("bulk_stock_matrix_cursor_resume_from_run_id"),
                "bulk_stock_matrix_effective_task_budget": int(task_scan_summary.get("bulk_stock_matrix_effective_task_budget") or 0),
                "bulk_stock_matrix_max_candidates_per_run": int(task_scan_summary.get("bulk_stock_matrix_max_candidates_per_run") or 0),
                "bulk_stock_matrix_estimated_candidate_count": int(task_scan_summary.get("bulk_stock_matrix_estimated_candidate_count") or 0),
                "bulk_stock_matrix_planned_task_count": int(task_scan_summary.get("bulk_stock_matrix_planned_task_count") or 0),
                "bulk_stock_matrix_planned_candidate_count": int(task_scan_summary.get("bulk_stock_matrix_planned_candidate_count") or 0),
                "bulk_stock_matrix_tasks_per_shard": int(task_scan_summary.get("bulk_stock_matrix_tasks_per_shard") or 0),
                "bulk_stock_matrix_shard_count": int(task_scan_summary.get("bulk_stock_matrix_shard_count") or 0),
                "bulk_stock_matrix_selected_shard_count": int(task_scan_summary.get("bulk_stock_matrix_selected_shard_count") or 0),
                "bulk_stock_matrix_selected_shard_ids": list(task_scan_summary.get("bulk_stock_matrix_selected_shard_ids") or []),
                "bulk_stock_matrix_stock_coverage_ratio": task_scan_summary.get("bulk_stock_matrix_stock_coverage_ratio"),
                "bulk_stock_matrix_allocation_mode": task_scan_summary.get("bulk_stock_matrix_allocation_mode"),
                "bulk_stock_matrix_allocation_pass_counts": bulk_stock_matrix_allocation_pass_counts,
                "bulk_stock_matrix_planned_allocation_pass_counts": dict(task_scan_summary.get("bulk_stock_matrix_planned_allocation_pass_counts") or {}),
                "bulk_stock_matrix_overflow_task_count": int(task_scan_summary.get("bulk_stock_matrix_overflow_task_count") or 0),
                "task_source_counts": task_source_counts,
                "scanner_task_types": task_scan_summary.get("task_types") or {},
                "event_snapshot_mixed": bool(
                    int(autonomy_summary.get("event_task_count") or 0) > 0 and snapshot_task_count > 0
                ),
                "max_research_tasks": int(autonomy_summary.get("max_research_tasks") or 0),
                "max_bulk_research_tasks": int(autonomy_summary.get("max_bulk_research_tasks") or 0),
                "combined_research_task_budget": int(autonomy_summary.get("combined_research_task_budget") or 0),
                "scan_research_task_budget": int(autonomy_summary.get("scan_research_task_budget") or 0),
                "reserved_bulk_task_budget": int(autonomy_summary.get("reserved_bulk_task_budget") or 0),
                "selected_scan_task_count": int(autonomy_summary.get("selected_scan_task_count") or 0),
                "selected_bulk_task_count": int(autonomy_summary.get("selected_bulk_task_count") or 0),
                "planned_bulk_task_count": int(autonomy_summary.get("planned_bulk_task_count") or 0),
                "clipped_bulk_task_count": int(autonomy_summary.get("clipped_bulk_task_count") or 0),
                "blocked_feedback_task_count": int(autonomy_summary.get("blocked_feedback_task_count") or 0),
                "planned_feedback_cooldown_task_count": int(
                    autonomy_summary.get("planned_feedback_cooldown_task_count") or 0
                ),
                "planned_feedback_control_mode_counts": dict(
                    autonomy_summary.get("planned_feedback_control_mode_counts") or {}
                ),
                "planned_feedback_target_pool_control_mode_counts": dict(
                    autonomy_summary.get("planned_feedback_target_pool_control_mode_counts") or {}
                ),
                "planned_feedback_generator_mode_control_mode_counts": dict(
                    autonomy_summary.get("planned_feedback_generator_mode_control_mode_counts") or {}
                ),
                "selected_feedback_control_mode_counts": dict(
                    autonomy_summary.get("selected_feedback_control_mode_counts") or {}
                ),
                "selected_feedback_target_pool_control_mode_counts": dict(
                    autonomy_summary.get("selected_feedback_target_pool_control_mode_counts") or {}
                ),
                "selected_feedback_generator_mode_control_mode_counts": dict(
                    autonomy_summary.get("selected_feedback_generator_mode_control_mode_counts") or {}
                ),
                "suppressed_families": list(autonomy_summary.get("suppressed_families") or []),
                "suppressed_target_pools": list(autonomy_summary.get("suppressed_target_pools") or []),
                "suppressed_generator_modes": list(autonomy_summary.get("suppressed_generator_modes") or []),
                "factor_research_used": bool(snapshot.get("factor_research")),
                "active_factor_count": int(factor_research_summary.get("active_factor_count") or 0),
                "active_candidate_count": int(factor_research_summary.get("active_candidate_count") or 0),
                "governed_source_candidate_count": int(factor_research_summary.get("governed_source_candidate_count") or 0),
                "governed_blocked_candidate_count": int(factor_research_summary.get("governed_blocked_candidate_count") or 0),
                "governed_blocked_ratio": factor_research_summary.get("governed_blocked_ratio"),
                "governed_latest_candidate_at": factor_research_summary.get("governed_latest_candidate_at"),
                "governed_freshness_days": factor_research_summary.get("governed_freshness_days"),
                "governed_exclusion_reason_counts": dict(factor_research_summary.get("governed_exclusion_reason_counts") or {}),
                "governed_risk_counts": dict(factor_research_summary.get("governed_risk_counts") or {}),
                "active_family_count": len(list(factor_research_summary.get("active_family_names") or [])),
                "active_regime_count": len(list(factor_research_summary.get("active_regime_names") or [])),
                "top_factor_names": list(factor_research_summary.get("top_factor_names") or []),
                "top_candidate_names": list(factor_research_summary.get("top_candidate_names") or []),
                "active_family_names": list(factor_research_summary.get("active_family_names") or []),
                "active_regime_names": list(factor_research_summary.get("active_regime_names") or []),
                "factor_source_mode": factor_research_summary.get("factor_source_mode"),
                "governed_candidate_pool_mode": factor_research_summary.get("governed_candidate_pool_mode"),
                "governed_candidate_pool_provisional": bool(
                    factor_research_summary.get("governed_candidate_pool_provisional")
                ),
                "governed_candidate_pool_strict_count": int(
                    factor_research_summary.get("governed_candidate_pool_strict_count") or 0
                ),
                "governed_candidate_pool_provisional_count": int(
                    factor_research_summary.get("governed_candidate_pool_provisional_count") or 0
                ),
                "stock_family_allocation_count": int(factor_research_summary.get("stock_family_allocation_count") or 0),
                "stock_family_allocation_family_counts": dict(factor_research_summary.get("stock_family_allocation_family_counts") or {}),
                "stock_family_allocation_entropy": factor_research_summary.get("stock_family_allocation_entropy"),
                "stock_family_allocation_avg_priority": factor_research_summary.get("stock_family_allocation_avg_priority"),
                "stock_family_allocation_source_mode": factor_research_summary.get("stock_family_allocation_source_mode"),
                "governed_candidate_pool_active": bool(
                    resolve_governed_pool_state(factor_research_summary).get("active")
                ),
                "governed_candidate_pool_runtime_state": readiness_summary.get("governed_candidate_pool_runtime_state"),
                "factor_research_degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                "factor_research_stale": bool(factor_research_summary.get("stale")),
                "factor_research_freshness_days": factor_research_summary.get("freshness_days"),
                "scheduler_recent_success": bool(factor_research_summary.get("scheduler_recent_success")),
                "scheduler_llm_validation_status": factor_research_summary.get("scheduler_llm_validation_status"),
                "factor_scheduler_recent_success": bool(factor_research_summary.get("scheduler_recent_success")),
                "factor_scheduler_llm_validation_status": factor_research_summary.get("scheduler_llm_validation_status"),
                "factor_llm_provider_enabled": bool(factor_research_summary.get("factor_llm_provider_enabled")),
                "factor_llm_provider_ready": bool(factor_research_summary.get("factor_llm_provider_ready")),
                "factor_llm_provider_health_status": factor_research_summary.get("factor_llm_provider_health_status"),
                "factor_llm_provider_rebuild_count": int(factor_research_summary.get("factor_llm_provider_rebuild_count") or 0),
                "factor_llm_provider_last_error_type": factor_research_summary.get("factor_llm_provider_last_error_type"),
                "lifecycle_feedback_input_contract_version": factor_research_summary.get(
                    "lifecycle_feedback_input_contract_version"
                ),
                "lifecycle_feedback_input_available": bool(
                    factor_research_summary.get("lifecycle_feedback_input_available")
                ),
                "budget_feedback_available": bool(factor_research_summary.get("budget_feedback_available")),
                "budget_feedback_family_count": int(
                    factor_research_summary.get("budget_feedback_family_count") or 0
                ),
                "budget_feedback_strategy_count": int(
                    factor_research_summary.get("budget_feedback_strategy_count") or 0
                ),
                "budget_feedback_target_pool_scope_count": int(
                    factor_research_summary.get("budget_feedback_target_pool_scope_count") or 0
                ),
                "budget_feedback_generator_mode_scope_count": int(
                    factor_research_summary.get("budget_feedback_generator_mode_scope_count") or 0
                ),
                "budget_feedback_runtime_alert_count": int(
                    factor_research_summary.get("budget_feedback_runtime_alert_count") or 0
                ),
                "budget_feedback_runtime_risk_event_count": int(
                    factor_research_summary.get("budget_feedback_runtime_risk_event_count") or 0
                ),
                "budget_feedback_promotion_review_count": int(
                    factor_research_summary.get("budget_feedback_promotion_review_count") or 0
                ),
                "budget_feedback_promotion_review_status_counts": dict(
                    factor_research_summary.get("budget_feedback_promotion_review_status_counts")
                    or {}
                ),
                "factor_research_refresh_attempted": bool(factor_refresh_summary.get("refresh_attempted")),
                "factor_research_refresh_status": factor_refresh_summary.get("refresh_status"),
                "factor_research_refresh_trigger": factor_refresh_summary.get("refresh_trigger"),
                "shared_generation_context_preloaded": bool(autonomy_summary.get("shared_generation_context_preloaded")),
                "autonomy_task_briefs": autonomy_task_briefs,
                "event_evidence_count": autonomy_summary.get("event_evidence_count", 0),
                "autonomy_lifecycle_state_counts": autonomy_summary.get("lifecycle_state_counts") or {},
                "autonomy_phase_status_counts": autonomy_summary.get("phase_status_counts") or {},
                "autonomy_failed_phase_counts": autonomy_summary.get("failed_phase_counts") or {},
                "quota_fill_candidates": (spawn_report.get("summary") or {}).get("quota_fill_count", 0),
                "signal_trigger_candidates": (
                    (spawn_report.get("summary") or {}).get("signal_trigger_count", len(candidates))
                ),
                "gate_0_passed": gate_0_summary.get("passed_count"),
                "gate_0_failed": gate_0_summary.get("failed_count"),
                "pre_gate_passed": pre_gate_summary.get("passed_count"),
                "pre_gate_failed": pre_gate_summary.get("failed_count"),
                "gate_1_passed": gate_1_summary.get("passed_count"),
                "gate_1_failed": gate_1_summary.get("failed_count"),
                "gate_2_input": gate_2_summary.get("input_count", backtest_summary.get("input_count", len(candidates))),
                "gate_2_passed": gate_2_summary.get("passed_count", len(passed)),
                "candidates_passed_backtest": gate_2_summary.get("passed_count", len(passed)),
                "candidates_failed_backtest": backtest_summary.get("failed_count", max(len(candidates) - len(passed), 0)),
                "backtest_failed_reason_counts": backtest_summary.get("failed_reason_counts") or {},
                "candidates_after_dedup": len(unique),
                "created": submit_result.get("created", 0),
                "created_strategy_pool": submit_result.get(
                    "created_strategy_pool",
                    submit_result.get("created", 0),
                ),
                "created_audit_only": submit_result.get("created_audit_only", 0),
                "created_total": submit_result.get(
                    "created_total",
                    int(submit_result.get("created", 0)) + int(submit_result.get("created_audit_only", 0)),
                ),
                "gate_3_input": submit_result.get("gate_3_input", len(unique)),
                "submitted": submit_result.get("submitted", 0),
                "passed_quality_gate": submit_result.get("passed_quality_gate", 0),
                "gate_3_passed": submit_result.get("gate_3_passed", submit_result.get("passed_quality_gate", 0)),
                "gate_3_failed": submit_result.get(
                    "gate_3_failed",
                    max(
                        int(submit_result.get("gate_3_input", len(unique))) - int(submit_result.get("passed_quality_gate", 0)),
                        0,
                    ),
                ),
                "gate_3_provisional_passed": submit_result.get("gate_3_provisional_passed", 0),
                "gate_3_failure_reason_topn": list(submit_result.get("gate_3_failure_reason_topn") or []),
                # P2-D 孵化预算反馈：按 family 的孵化成功数（供下一周期 EMA 更新）
                "incubation_budget_family_counts": dict(
                    (submit_result.get("incubation_budget_summary") or {}).get("family_counts") or {}
                ),
                **submission_audit_summary,
                **backtest_audit_summary,
                **vector_summary,
                "eliminated": len(eliminated),
                "external_llm_status": autonomy_summary.get("external_llm_status"),
                "external_llm_attempt_count": autonomy_summary.get("external_llm_attempt_count", 0),
                "external_llm_stage_attempt_count": autonomy_summary.get(
                    "external_llm_stage_attempt_count",
                    autonomy_summary.get("external_llm_attempt_count", 0),
                ),
                "external_llm_network_request_count": autonomy_summary.get("external_llm_network_request_count", 0),
                "external_llm_real_request_count": autonomy_summary.get("external_llm_real_request_count", 0),
                "external_llm_compatibility_skip_count": autonomy_summary.get("external_llm_compatibility_skip_count", 0),
                "external_llm_cooldown_skip_count": autonomy_summary.get("external_llm_cooldown_skip_count", 0),
                "external_llm_compatibility_failure_count": autonomy_summary.get(
                    "external_llm_compatibility_failure_count",
                    0,
                ),
                "external_llm_compatibility_failure_ratio": autonomy_summary.get(
                    "external_llm_compatibility_failure_ratio",
                    0.0,
                ),
                "external_llm_effective_response_count": autonomy_summary.get(
                    "external_llm_effective_response_count",
                    0,
                ),
                "external_llm_effective_response_ratio": autonomy_summary.get(
                    "external_llm_effective_response_ratio",
                    0.0,
                ),
                "external_llm_empty_200_response_count": autonomy_summary.get(
                    "external_llm_empty_200_response_count",
                    0,
                ),
                "external_llm_request_status_counts": dict(
                    autonomy_summary.get("external_llm_request_status_counts") or {}
                ),
                "external_llm_selected_count": autonomy_summary.get("external_llm_selected_count", 0),
                "external_llm_last_error_type": autonomy_summary.get("external_llm_last_error_type"),
                "external_llm_last_error": autonomy_summary.get("external_llm_last_error"),
                "external_llm_provider_health_status": autonomy_summary.get("external_llm_provider_health_status"),
                "external_llm_provider_scheduler_should_disable": bool(
                    autonomy_summary.get("external_llm_provider_scheduler_should_disable")
                ),
                "external_llm_provider_scheduler_skip_reason": autonomy_summary.get(
                    "external_llm_provider_scheduler_skip_reason"
                ),
                "external_llm_provider_control_mode": autonomy_summary.get("external_llm_provider_control_mode"),
                "external_llm_provider_control_reasons": list(
                    autonomy_summary.get("external_llm_provider_control_reasons") or []
                ),
                "generator_mode_controls": dict(autonomy_summary.get("generator_mode_controls") or {}),
                "external_llm_elapsed_seconds": autonomy_summary.get("external_llm_elapsed_seconds"),
                "elapsed_seconds": round(elapsed, 1),
            }
            results["summary"] = self._apply_research_plane_summary(
                results["summary"],
                research_plane,
            )
            results["summary"].update(scheduler._build_layered_run_summary(results["summary"], submit_result))
            scheduler._apply_run_audit(results, persistence_failures=persistence_failures)

            logger.info(
                "StrategyFactory: completed in %.1fs — spawned %d, backtest passed %d, dedup %d, submitted %s, eliminated %d",
                elapsed,
                len(candidates),
                len(passed),
                len(unique),
                submit_result,
                len(eliminated),
            )
        except Exception as exc:
            elapsed = (scheduler._now() - start).total_seconds()
            logger.error("StrategyFactory: run_once failed: %s", exc, exc_info=True)
            results["status"] = FactoryRunStatus.FAILED.value
            results["completed_at"] = scheduler._now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            results["error"] = str(exc)
            results["summary"] = {"trace_id": trace_id, "elapsed_seconds": round(elapsed, 1), "error": str(exc)}
            results["summary"].update(scheduler._build_layered_run_summary(results["summary"], None))
            scheduler._apply_run_audit(results, persistence_failures=persistence_failures)

        return FactoryCycleOutcome(results, persistence_failures)


__all__ = [
    "FactoryCycleOutcome",
    "FactoryCycleRunner",
    "FactoryRunContext",
    "FactoryRunResult",
]
