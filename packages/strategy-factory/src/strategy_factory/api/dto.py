"""Stable Data Transfer Objects for the strategy factory product interface.

These DTOs decouple the BFF / MCP tool layer from the raw run result dicts,
providing versioned, stable contracts for:

- FactoryStatusDTO        → factory_status tool
- FactoryRunSummaryDTO    → factory_runs list item
- FactoryRunDetailDTO     → factory_run_detail tool
- StageResultDTO          → single stage within a run detail

P5 implementation: product layer reads from DTOs, not from raw run dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..application.governance_plane_contract import build_governance_plane_artifact
from ..application.research_plane_contract import build_research_plane_artifact
from ..application.run_models import FactoryRunStatus, StageStatus, normalize_run_status, normalize_stage_status


# ---------------------------------------------------------------------------
# Stage DTO
# ---------------------------------------------------------------------------

@dataclass
class StageResultDTO:
    """DTO for a single stage within a factory run."""

    stage: str
    status: str
    ok: bool
    hard_failure: bool
    degraded: bool
    skip_reason: Optional[str]
    warning_count: int
    blocker_count: int
    persistence_failure_count: int

    @classmethod
    def from_dict(cls, stage: str, data: Any) -> "StageResultDTO":
        d = dict(data) if isinstance(data, dict) else {}
        status_enum = normalize_stage_status(d.get("status"))
        return cls(
            stage=stage,
            status=status_enum.value,
            ok=bool(d.get("ok", True)),
            hard_failure=bool(d.get("hard_failure")),
            degraded=bool(d.get("degraded")),
            skip_reason=d.get("skip_reason"),
            warning_count=int(d.get("warning_count") or 0),
            blocker_count=int(d.get("blocker_count") or 0),
            persistence_failure_count=int(d.get("persistence_failure_count") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "stage": self.stage,
            "status": self.status,
            "ok": self.ok,
            "hard_failure": self.hard_failure,
            "degraded": self.degraded,
            "warning_count": self.warning_count,
            "blocker_count": self.blocker_count,
            "persistence_failure_count": self.persistence_failure_count,
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result


# ---------------------------------------------------------------------------
# Factory run summary DTO (list item)
# ---------------------------------------------------------------------------

@dataclass
class FactoryRunSummaryDTO:
    """DTO for a factory run summary as shown in the factory_runs list."""

    run_id: str
    trace_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    elapsed_seconds: float
    candidates_spawned: int
    submitted: int
    eliminated: int
    hard_failure_count: int
    degraded_stage_count: int
    persistence_failure_count: int
    skip_reason: Optional[str]
    error: Optional[str]
    readiness_score: Optional[float]
    readiness_can_proceed: Optional[bool]
    stock_family_allocation_count: int
    family_preference_order: list[str] = field(default_factory=list)
    family_preference_source_mode: Optional[str] = None
    governed_candidate_pool_provisional_spillover_policy_status: Optional[str] = None
    governed_pending_candidate_count: int = 0
    external_llm_provider_health_status: Optional[str] = None
    external_llm_provider_control_mode: Optional[str] = None
    candidate_local_attempt_count: int = 0
    task_local_attempt_count: int = 0
    cohort_effective_trials: float = 0.0
    refresh_existing_count: int = 0
    spawn_revision_from_existing_count: int = 0
    unique_family_holding_universe_count: int = 0
    economic_semantics_missing_count: int = 0
    research_only_count: int = 0
    deferred_submission_count: int = 0
    validation_grade_distribution: dict[str, int] = field(default_factory=dict)
    raw_validation_grade_distribution: dict[str, int] = field(default_factory=dict)
    effective_validation_grade_distribution: dict[str, int] = field(default_factory=dict)
    raw_validation_total_score_mean: float = 0.0
    raw_validation_total_score_p50: float = 0.0
    raw_validation_total_score_p90: float = 0.0
    raw_validation_a_rate: float = 0.0
    raw_validation_b_rate: float = 0.0
    raw_validation_c_rate: float = 0.0
    raw_validation_d_rate: float = 0.0
    strict_incubation_ready_count: int = 0
    strict_incubation_ready_rate: float = 0.0
    live_candidate_ready_count: int = 0
    live_candidate_ready_rate: float = 0.0
    raw_b_or_above_count: int = 0
    raw_b_or_above_rate: float = 0.0
    strict_ready_given_raw_b_count: int = 0
    strict_ready_given_raw_b_rate: float = 0.0
    live_ready_given_raw_b_count: int = 0
    live_ready_given_raw_b_rate: float = 0.0
    validation_family_quality_panel: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryRunSummaryDTO":
        d = dict(data or {})
        summary = dict(d.get("summary") or {})
        audit = dict(d.get("_run_audit") or {})
        submission_artifact = dict(
            (_normalize_governance_plane_detail(d).get("submission_artifact") or {})
        )
        status = normalize_run_status(d.get("status"), default=FactoryRunStatus.FAILED).value
        return cls(
            run_id=str(d.get("run_id") or ""),
            trace_id=str(d.get("trace_id") or summary.get("trace_id") or ""),
            status=status,
            started_at=str(d.get("started_at") or ""),
            completed_at=d.get("completed_at"),
            elapsed_seconds=float(d.get("elapsed_seconds") or 0.0),
            candidates_spawned=int(summary.get("candidates_spawned") or 0),
            submitted=int(summary.get("submitted") or 0),
            eliminated=int(summary.get("eliminated") or 0),
            hard_failure_count=int(audit.get("hard_failure_count") or 0),
            degraded_stage_count=int(audit.get("degraded_stage_count") or 0),
            persistence_failure_count=int(audit.get("persistence_failure_count") or 0),
            skip_reason=summary.get("skip_reason"),
            error=d.get("error"),
            readiness_score=summary.get("factory_readiness_score"),
            readiness_can_proceed=summary.get("factory_readiness_can_proceed"),
            stock_family_allocation_count=int(summary.get("stock_family_allocation_count") or 0),
            family_preference_order=[
                str(item or "").strip()
                for item in list(summary.get("family_preference_order") or [])
                if str(item or "").strip()
            ],
            family_preference_source_mode=(
                str(summary.get("family_preference_source_mode") or "").strip() or None
            ),
            governed_candidate_pool_provisional_spillover_policy_status=(
                str(summary.get("governed_candidate_pool_provisional_spillover_policy_status") or "").strip()
                or str(d.get("governed_candidate_pool_provisional_spillover_policy_status") or "").strip()
                or None
            ),
            governed_pending_candidate_count=int(
                summary.get("governed_pending_candidate_count")
                or d.get("governed_pending_candidate_count")
                or 0
            ),
            external_llm_provider_health_status=(
                str(summary.get("external_llm_provider_health_status") or d.get("external_llm_provider_health_status") or "").strip()
                or None
            ),
            external_llm_provider_control_mode=(
                str(summary.get("external_llm_provider_control_mode") or d.get("external_llm_provider_control_mode") or "").strip()
                or None
            ),
            candidate_local_attempt_count=int(
                summary.get("candidate_local_attempt_count")
                or d.get("candidate_local_attempt_count")
                or 0
            ),
            task_local_attempt_count=int(
                summary.get("task_local_attempt_count")
                or d.get("task_local_attempt_count")
                or 0
            ),
            cohort_effective_trials=float(
                summary.get("cohort_effective_trials")
                or d.get("cohort_effective_trials")
                or 0.0
            ),
            refresh_existing_count=int(
                summary.get("refresh_existing_count")
                or d.get("refresh_existing_count")
                or 0
            ),
            spawn_revision_from_existing_count=int(
                summary.get("spawn_revision_from_existing_count")
                or d.get("spawn_revision_from_existing_count")
                or 0
            ),
            unique_family_holding_universe_count=int(
                summary.get("unique_family_holding_universe_count")
                or d.get("unique_family_holding_universe_count")
                or 0
            ),
            economic_semantics_missing_count=int(
                summary.get("economic_semantics_missing_count")
                or d.get("economic_semantics_missing_count")
                or 0
            ),
            research_only_count=int(
                summary.get("research_only_count")
                or d.get("research_only_count")
                or 0
            ),
            deferred_submission_count=int(
                summary.get("deferred_submission_count")
                or d.get("deferred_submission_count")
                or 0
            ),
            validation_grade_distribution={
                str(key or "").strip().upper(): int(value or 0)
                for key, value in dict(
                    summary.get("validation_grade_distribution")
                    or d.get("validation_grade_distribution")
                    or submission_artifact.get("validation_grade_distribution")
                    or {}
                ).items()
                if str(key or "").strip()
            },
            raw_validation_grade_distribution={
                str(key or "").strip().upper(): int(value or 0)
                for key, value in dict(
                    summary.get("raw_validation_grade_distribution")
                    or d.get("raw_validation_grade_distribution")
                    or submission_artifact.get("raw_validation_grade_distribution")
                    or summary.get("validation_grade_distribution")
                    or d.get("validation_grade_distribution")
                    or submission_artifact.get("validation_grade_distribution")
                    or {}
                ).items()
                if str(key or "").strip()
            },
            effective_validation_grade_distribution={
                str(key or "").strip().upper(): int(value or 0)
                for key, value in dict(
                    summary.get("effective_validation_grade_distribution")
                    or d.get("effective_validation_grade_distribution")
                    or submission_artifact.get("effective_validation_grade_distribution")
                    or summary.get("validation_grade_distribution")
                    or d.get("validation_grade_distribution")
                    or submission_artifact.get("validation_grade_distribution")
                    or {}
                ).items()
                if str(key or "").strip()
            },
            raw_validation_total_score_mean=float(
                summary.get("raw_validation_total_score_mean")
                or d.get("raw_validation_total_score_mean")
                or submission_artifact.get("raw_validation_total_score_mean")
                or 0.0
            ),
            raw_validation_total_score_p50=float(
                summary.get("raw_validation_total_score_p50")
                or d.get("raw_validation_total_score_p50")
                or submission_artifact.get("raw_validation_total_score_p50")
                or 0.0
            ),
            raw_validation_total_score_p90=float(
                summary.get("raw_validation_total_score_p90")
                or d.get("raw_validation_total_score_p90")
                or submission_artifact.get("raw_validation_total_score_p90")
                or 0.0
            ),
            raw_validation_a_rate=float(
                summary.get("raw_validation_a_rate")
                or d.get("raw_validation_a_rate")
                or submission_artifact.get("raw_validation_a_rate")
                or 0.0
            ),
            raw_validation_b_rate=float(
                summary.get("raw_validation_b_rate")
                or d.get("raw_validation_b_rate")
                or submission_artifact.get("raw_validation_b_rate")
                or 0.0
            ),
            raw_validation_c_rate=float(
                summary.get("raw_validation_c_rate")
                or d.get("raw_validation_c_rate")
                or submission_artifact.get("raw_validation_c_rate")
                or 0.0
            ),
            raw_validation_d_rate=float(
                summary.get("raw_validation_d_rate")
                or d.get("raw_validation_d_rate")
                or submission_artifact.get("raw_validation_d_rate")
                or 0.0
            ),
            strict_incubation_ready_count=int(
                summary.get("strict_incubation_ready_count")
                or d.get("strict_incubation_ready_count")
                or submission_artifact.get("strict_incubation_ready_count")
                or 0
            ),
            strict_incubation_ready_rate=float(
                summary.get("strict_incubation_ready_rate")
                or d.get("strict_incubation_ready_rate")
                or submission_artifact.get("strict_incubation_ready_rate")
                or 0.0
            ),
            live_candidate_ready_count=int(
                summary.get("live_candidate_ready_count")
                or d.get("live_candidate_ready_count")
                or submission_artifact.get("live_candidate_ready_count")
                or 0
            ),
            live_candidate_ready_rate=float(
                summary.get("live_candidate_ready_rate")
                or d.get("live_candidate_ready_rate")
                or submission_artifact.get("live_candidate_ready_rate")
                or 0.0
            ),
            raw_b_or_above_count=int(
                summary.get("raw_b_or_above_count")
                or d.get("raw_b_or_above_count")
                or submission_artifact.get("raw_b_or_above_count")
                or 0
            ),
            raw_b_or_above_rate=float(
                summary.get("raw_b_or_above_rate")
                or d.get("raw_b_or_above_rate")
                or submission_artifact.get("raw_b_or_above_rate")
                or 0.0
            ),
            strict_ready_given_raw_b_count=int(
                summary.get("strict_ready_given_raw_b_count")
                or d.get("strict_ready_given_raw_b_count")
                or submission_artifact.get("strict_ready_given_raw_b_count")
                or 0
            ),
            strict_ready_given_raw_b_rate=float(
                summary.get("strict_ready_given_raw_b_rate")
                or d.get("strict_ready_given_raw_b_rate")
                or submission_artifact.get("strict_ready_given_raw_b_rate")
                or 0.0
            ),
            live_ready_given_raw_b_count=int(
                summary.get("live_ready_given_raw_b_count")
                or d.get("live_ready_given_raw_b_count")
                or submission_artifact.get("live_ready_given_raw_b_count")
                or 0
            ),
            live_ready_given_raw_b_rate=float(
                summary.get("live_ready_given_raw_b_rate")
                or d.get("live_ready_given_raw_b_rate")
                or submission_artifact.get("live_ready_given_raw_b_rate")
                or 0.0
            ),
            validation_family_quality_panel=[
                dict(item or {})
                for item in list(
                    summary.get("validation_family_quality_panel")
                    or d.get("validation_family_quality_panel")
                    or submission_artifact.get("validation_family_quality_panel")
                    or []
                )
                if isinstance(item, dict)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "candidates_spawned": self.candidates_spawned,
            "submitted": self.submitted,
            "eliminated": self.eliminated,
            "hard_failure_count": self.hard_failure_count,
            "degraded_stage_count": self.degraded_stage_count,
            "persistence_failure_count": self.persistence_failure_count,
            "readiness_score": self.readiness_score,
            "readiness_can_proceed": self.readiness_can_proceed,
            "stock_family_allocation_count": self.stock_family_allocation_count,
            "family_preference_order": list(self.family_preference_order),
            "governed_pending_candidate_count": self.governed_pending_candidate_count,
            "candidate_local_attempt_count": self.candidate_local_attempt_count,
            "task_local_attempt_count": self.task_local_attempt_count,
            "cohort_effective_trials": self.cohort_effective_trials,
            "refresh_existing_count": self.refresh_existing_count,
            "spawn_revision_from_existing_count": self.spawn_revision_from_existing_count,
            "unique_family_holding_universe_count": self.unique_family_holding_universe_count,
            "economic_semantics_missing_count": self.economic_semantics_missing_count,
            "research_only_count": self.research_only_count,
            "deferred_submission_count": self.deferred_submission_count,
            "validation_grade_distribution": dict(self.validation_grade_distribution),
            "raw_validation_grade_distribution": dict(self.raw_validation_grade_distribution),
            "effective_validation_grade_distribution": dict(
                self.effective_validation_grade_distribution
            ),
            "raw_validation_total_score_mean": self.raw_validation_total_score_mean,
            "raw_validation_total_score_p50": self.raw_validation_total_score_p50,
            "raw_validation_total_score_p90": self.raw_validation_total_score_p90,
            "raw_validation_a_rate": self.raw_validation_a_rate,
            "raw_validation_b_rate": self.raw_validation_b_rate,
            "raw_validation_c_rate": self.raw_validation_c_rate,
            "raw_validation_d_rate": self.raw_validation_d_rate,
            "strict_incubation_ready_count": self.strict_incubation_ready_count,
            "strict_incubation_ready_rate": self.strict_incubation_ready_rate,
            "live_candidate_ready_count": self.live_candidate_ready_count,
            "live_candidate_ready_rate": self.live_candidate_ready_rate,
            "raw_b_or_above_count": self.raw_b_or_above_count,
            "raw_b_or_above_rate": self.raw_b_or_above_rate,
            "strict_ready_given_raw_b_count": self.strict_ready_given_raw_b_count,
            "strict_ready_given_raw_b_rate": self.strict_ready_given_raw_b_rate,
            "live_ready_given_raw_b_count": self.live_ready_given_raw_b_count,
            "live_ready_given_raw_b_rate": self.live_ready_given_raw_b_rate,
            "validation_family_quality_panel": list(self.validation_family_quality_panel),
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        if self.error:
            result["error"] = self.error
        if self.family_preference_source_mode:
            result["family_preference_source_mode"] = self.family_preference_source_mode
        if self.governed_candidate_pool_provisional_spillover_policy_status:
            result["governed_candidate_pool_provisional_spillover_policy_status"] = (
                self.governed_candidate_pool_provisional_spillover_policy_status
            )
        if self.external_llm_provider_health_status:
            result["external_llm_provider_health_status"] = (
                self.external_llm_provider_health_status
            )
        if self.external_llm_provider_control_mode:
            result["external_llm_provider_control_mode"] = (
                self.external_llm_provider_control_mode
            )
        return result


# ---------------------------------------------------------------------------
# Factory run detail DTO
# ---------------------------------------------------------------------------

@dataclass
class FactoryRunDetailDTO:
    """DTO for a complete factory run detail, including per-stage breakdown."""

    summary: FactoryRunSummaryDTO
    stages: list[StageResultDTO] = field(default_factory=list)
    snapshot_summary: dict[str, Any] = field(default_factory=dict)
    quality_gate: dict[str, Any] = field(default_factory=dict)
    research_summary: dict[str, Any] = field(default_factory=dict)
    research_plane: dict[str, Any] = field(default_factory=dict)
    research_artifact: dict[str, Any] = field(default_factory=dict)
    task_artifact: dict[str, Any] = field(default_factory=dict)
    candidate_artifact: dict[str, Any] = field(default_factory=dict)
    evidence_artifact: dict[str, Any] = field(default_factory=dict)
    governance_plane: dict[str, Any] = field(default_factory=dict)
    gate_artifact: dict[str, Any] = field(default_factory=dict)
    dedup_artifact: dict[str, Any] = field(default_factory=dict)
    submission_artifact: dict[str, Any] = field(default_factory=dict)
    governance_evidence_artifact: dict[str, Any] = field(default_factory=dict)
    feedback_summary: dict[str, Any] = field(default_factory=dict)
    incubation_summary: dict[str, Any] = field(default_factory=dict)
    live_ready_summary: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryRunDetailDTO":
        d = dict(data or {})
        summary_dto = FactoryRunSummaryDTO.from_dict(d)
        raw_summary = dict(d.get("summary") or {})
        raw_stages = dict(d.get("stages") or {})
        stage_payloads = {
            name: payload
            for name, payload in raw_stages.items()
            if isinstance(payload, dict)
        }
        research_plane = _normalize_research_plane_detail(d)
        governance_plane = _normalize_governance_plane_detail(d)
        stages = [
            StageResultDTO.from_dict(name, payload)
            for name, payload in stage_payloads.items()
        ]
        return cls(
            summary=summary_dto,
            stages=stages,
            snapshot_summary=dict(d.get("snapshot_summary") or {}),
            quality_gate=dict(d.get("quality_gate") or d.get("gate_report") or {}),
            research_summary=dict(raw_summary.get("research_summary") or {}),
            research_plane=research_plane,
            research_artifact=dict(research_plane.get("research_artifact") or {}),
            task_artifact=dict(research_plane.get("task_artifact") or {}),
            candidate_artifact=dict(research_plane.get("candidate_artifact") or {}),
            evidence_artifact=dict(research_plane.get("evidence_artifact") or {}),
            governance_plane=governance_plane,
            gate_artifact=dict(governance_plane.get("gate_artifact") or {}),
            dedup_artifact=dict(governance_plane.get("dedup_artifact") or {}),
            submission_artifact=dict(governance_plane.get("submission_artifact") or {}),
            governance_evidence_artifact=dict(governance_plane.get("evidence_artifact") or {}),
            feedback_summary=dict(raw_summary.get("feedback_summary") or {}),
            incubation_summary=dict(raw_summary.get("incubation_summary") or {}),
            live_ready_summary=dict(raw_summary.get("live_ready_summary") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary.to_dict(),
            "stages": {s.stage: s.to_dict() for s in self.stages},
            "snapshot_summary": self.snapshot_summary,
            "quality_gate": self.quality_gate,
            "research_summary": self.research_summary,
            "research_plane": self.research_plane,
            "research_artifact": self.research_artifact,
            "task_artifact": self.task_artifact,
            "candidate_artifact": self.candidate_artifact,
            "evidence_artifact": self.evidence_artifact,
            "governance_plane": self.governance_plane,
            "gate_artifact": self.gate_artifact,
            "dedup_artifact": self.dedup_artifact,
            "submission_artifact": self.submission_artifact,
            "governance_evidence_artifact": self.governance_evidence_artifact,
            "feedback_summary": self.feedback_summary,
            "incubation_summary": self.incubation_summary,
            "live_ready_summary": self.live_ready_summary,
        }

    def get_stage(self, name: str) -> Optional[StageResultDTO]:
        for s in self.stages:
            if s.stage == name:
                return s
        return None

    def failed_stages(self) -> list[str]:
        return [s.stage for s in self.stages if s.status == StageStatus.FAILED.value]

    def partial_stages(self) -> list[str]:
        return [s.stage for s in self.stages if s.status == StageStatus.PARTIAL.value]


# ---------------------------------------------------------------------------
# Factory status DTO (scheduler status)
# ---------------------------------------------------------------------------

@dataclass
class FactoryStatusDTO:
    """DTO for the scheduler-level factory status (factory_status tool)."""

    running: bool
    schedule_mode: str
    runtime_enabled: bool
    event_runtime_mode: str
    last_run: Optional[str]
    last_status: Optional[str]
    daily_run_count: int
    max_daily_runs: int
    cycle_count: int
    factor_auto_refresh_enabled: bool
    readiness_hard_block_enabled: bool
    readiness_min_score: float
    last_stock_family_allocation_count: int = 0
    last_family_preference_order: list[str] = field(default_factory=list)
    last_family_preference_source_mode: Optional[str] = None
    last_governed_candidate_pool_provisional_spillover_policy_status: Optional[str] = None
    last_governed_pending_candidate_count: int = 0
    last_external_llm_provider_health_status: Optional[str] = None
    last_external_llm_provider_control_mode: Optional[str] = None
    last_candidate_local_attempt_count: int = 0
    last_task_local_attempt_count: int = 0
    last_cohort_effective_trials: float = 0.0
    last_refresh_existing_count: int = 0
    last_spawn_revision_from_existing_count: int = 0
    last_unique_family_holding_universe_count: int = 0
    last_economic_semantics_missing_count: int = 0
    last_research_only_count: int = 0
    last_deferred_submission_count: int = 0
    last_validation_grade_distribution: dict[str, int] = field(default_factory=dict)
    last_raw_validation_grade_distribution: dict[str, int] = field(default_factory=dict)
    last_effective_validation_grade_distribution: dict[str, int] = field(default_factory=dict)
    last_raw_validation_total_score_mean: float = 0.0
    last_raw_validation_total_score_p50: float = 0.0
    last_raw_validation_total_score_p90: float = 0.0
    last_raw_validation_a_rate: float = 0.0
    last_raw_validation_b_rate: float = 0.0
    last_raw_validation_c_rate: float = 0.0
    last_raw_validation_d_rate: float = 0.0
    last_strict_incubation_ready_count: int = 0
    last_strict_incubation_ready_rate: float = 0.0
    last_live_candidate_ready_count: int = 0
    last_live_candidate_ready_rate: float = 0.0
    last_raw_b_or_above_count: int = 0
    last_raw_b_or_above_rate: float = 0.0
    last_strict_ready_given_raw_b_count: int = 0
    last_strict_ready_given_raw_b_rate: float = 0.0
    last_live_ready_given_raw_b_count: int = 0
    last_live_ready_given_raw_b_rate: float = 0.0
    last_validation_family_quality_panel: list[dict[str, Any]] = field(default_factory=list)
    quality_baseline: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryStatusDTO":
        d = dict(data or {})
        last_result = dict(d.get("last_result") or {})
        last_summary = dict(last_result.get("summary") or d.get("last_summary") or {})
        last_submission_artifact = dict(
            (_normalize_governance_plane_detail(last_result).get("submission_artifact") or {})
        )
        return cls(
            running=bool(d.get("running")),
            schedule_mode=str(d.get("schedule_mode") or "continuous"),
            runtime_enabled=bool(d.get("runtime_enabled")),
            event_runtime_mode=str(d.get("event_runtime_mode") or ""),
            last_run=str(d["last_run"]) if d.get("last_run") else None,
            last_status=str(last_result.get("status") or "") or None,
            daily_run_count=int(d.get("daily_run_count") or 0),
            max_daily_runs=int(d.get("max_daily_runs") or 0),
            cycle_count=int(d.get("cycle_count") or 0),
            factor_auto_refresh_enabled=bool(d.get("factor_auto_refresh_enabled")),
            readiness_hard_block_enabled=bool(d.get("readiness_hard_block_enabled")),
            readiness_min_score=float(d.get("readiness_min_score") or 0.0),
            last_stock_family_allocation_count=int(
                last_summary.get("stock_family_allocation_count") or 0
            ),
            last_family_preference_order=[
                str(item or "").strip()
                for item in list(last_summary.get("family_preference_order") or [])
                if str(item or "").strip()
            ],
            last_family_preference_source_mode=(
                str(last_summary.get("family_preference_source_mode") or "").strip() or None
            ),
            last_governed_candidate_pool_provisional_spillover_policy_status=(
                str(
                    last_summary.get("governed_candidate_pool_provisional_spillover_policy_status")
                    or ""
                ).strip()
                or None
            ),
            last_governed_pending_candidate_count=int(
                last_summary.get("governed_pending_candidate_count")
                or last_result.get("governed_pending_candidate_count")
                or 0
            ),
            last_external_llm_provider_health_status=(
                str(
                    last_summary.get("external_llm_provider_health_status")
                    or last_result.get("external_llm_provider_health_status")
                    or ""
                ).strip()
                or None
            ),
            last_external_llm_provider_control_mode=(
                str(
                    last_summary.get("external_llm_provider_control_mode")
                    or last_result.get("external_llm_provider_control_mode")
                    or ""
                ).strip()
                or None
            ),
            last_candidate_local_attempt_count=int(
                last_summary.get("candidate_local_attempt_count")
                or last_result.get("candidate_local_attempt_count")
                or 0
            ),
            last_task_local_attempt_count=int(
                last_summary.get("task_local_attempt_count")
                or last_result.get("task_local_attempt_count")
                or 0
            ),
            last_cohort_effective_trials=float(
                last_summary.get("cohort_effective_trials")
                or last_result.get("cohort_effective_trials")
                or 0.0
            ),
            last_refresh_existing_count=int(
                last_summary.get("refresh_existing_count")
                or last_result.get("refresh_existing_count")
                or 0
            ),
            last_spawn_revision_from_existing_count=int(
                last_summary.get("spawn_revision_from_existing_count")
                or last_result.get("spawn_revision_from_existing_count")
                or 0
            ),
            last_unique_family_holding_universe_count=int(
                last_summary.get("unique_family_holding_universe_count")
                or last_result.get("unique_family_holding_universe_count")
                or 0
            ),
            last_economic_semantics_missing_count=int(
                last_summary.get("economic_semantics_missing_count")
                or last_result.get("economic_semantics_missing_count")
                or 0
            ),
            last_research_only_count=int(
                last_summary.get("research_only_count")
                or last_result.get("research_only_count")
                or 0
            ),
            last_deferred_submission_count=int(
                last_summary.get("deferred_submission_count")
                or last_result.get("deferred_submission_count")
                or 0
            ),
            last_validation_grade_distribution={
                str(key or "").strip().upper(): int(value or 0)
                for key, value in dict(
                    last_summary.get("validation_grade_distribution")
                    or last_result.get("validation_grade_distribution")
                    or last_submission_artifact.get("validation_grade_distribution")
                    or {}
                ).items()
                if str(key or "").strip()
            },
            last_raw_validation_grade_distribution={
                str(key or "").strip().upper(): int(value or 0)
                for key, value in dict(
                    last_summary.get("raw_validation_grade_distribution")
                    or last_result.get("raw_validation_grade_distribution")
                    or last_submission_artifact.get("raw_validation_grade_distribution")
                    or last_summary.get("validation_grade_distribution")
                    or last_result.get("validation_grade_distribution")
                    or last_submission_artifact.get("validation_grade_distribution")
                    or {}
                ).items()
                if str(key or "").strip()
            },
            last_effective_validation_grade_distribution={
                str(key or "").strip().upper(): int(value or 0)
                for key, value in dict(
                    last_summary.get("effective_validation_grade_distribution")
                    or last_result.get("effective_validation_grade_distribution")
                    or last_submission_artifact.get("effective_validation_grade_distribution")
                    or last_summary.get("validation_grade_distribution")
                    or last_result.get("validation_grade_distribution")
                    or last_submission_artifact.get("validation_grade_distribution")
                    or {}
                ).items()
                if str(key or "").strip()
            },
            last_raw_validation_total_score_mean=float(
                last_summary.get("raw_validation_total_score_mean")
                or last_result.get("raw_validation_total_score_mean")
                or last_submission_artifact.get("raw_validation_total_score_mean")
                or 0.0
            ),
            last_raw_validation_total_score_p50=float(
                last_summary.get("raw_validation_total_score_p50")
                or last_result.get("raw_validation_total_score_p50")
                or last_submission_artifact.get("raw_validation_total_score_p50")
                or 0.0
            ),
            last_raw_validation_total_score_p90=float(
                last_summary.get("raw_validation_total_score_p90")
                or last_result.get("raw_validation_total_score_p90")
                or last_submission_artifact.get("raw_validation_total_score_p90")
                or 0.0
            ),
            last_raw_validation_a_rate=float(
                last_summary.get("raw_validation_a_rate")
                or last_result.get("raw_validation_a_rate")
                or last_submission_artifact.get("raw_validation_a_rate")
                or 0.0
            ),
            last_raw_validation_b_rate=float(
                last_summary.get("raw_validation_b_rate")
                or last_result.get("raw_validation_b_rate")
                or last_submission_artifact.get("raw_validation_b_rate")
                or 0.0
            ),
            last_raw_validation_c_rate=float(
                last_summary.get("raw_validation_c_rate")
                or last_result.get("raw_validation_c_rate")
                or last_submission_artifact.get("raw_validation_c_rate")
                or 0.0
            ),
            last_raw_validation_d_rate=float(
                last_summary.get("raw_validation_d_rate")
                or last_result.get("raw_validation_d_rate")
                or last_submission_artifact.get("raw_validation_d_rate")
                or 0.0
            ),
            last_strict_incubation_ready_count=int(
                last_summary.get("strict_incubation_ready_count")
                or last_result.get("strict_incubation_ready_count")
                or last_submission_artifact.get("strict_incubation_ready_count")
                or 0
            ),
            last_strict_incubation_ready_rate=float(
                last_summary.get("strict_incubation_ready_rate")
                or last_result.get("strict_incubation_ready_rate")
                or last_submission_artifact.get("strict_incubation_ready_rate")
                or 0.0
            ),
            last_live_candidate_ready_count=int(
                last_summary.get("live_candidate_ready_count")
                or last_result.get("live_candidate_ready_count")
                or last_submission_artifact.get("live_candidate_ready_count")
                or 0
            ),
            last_live_candidate_ready_rate=float(
                last_summary.get("live_candidate_ready_rate")
                or last_result.get("live_candidate_ready_rate")
                or last_submission_artifact.get("live_candidate_ready_rate")
                or 0.0
            ),
            last_raw_b_or_above_count=int(
                last_summary.get("raw_b_or_above_count")
                or last_result.get("raw_b_or_above_count")
                or last_submission_artifact.get("raw_b_or_above_count")
                or 0
            ),
            last_raw_b_or_above_rate=float(
                last_summary.get("raw_b_or_above_rate")
                or last_result.get("raw_b_or_above_rate")
                or last_submission_artifact.get("raw_b_or_above_rate")
                or 0.0
            ),
            last_strict_ready_given_raw_b_count=int(
                last_summary.get("strict_ready_given_raw_b_count")
                or last_result.get("strict_ready_given_raw_b_count")
                or last_submission_artifact.get("strict_ready_given_raw_b_count")
                or 0
            ),
            last_strict_ready_given_raw_b_rate=float(
                last_summary.get("strict_ready_given_raw_b_rate")
                or last_result.get("strict_ready_given_raw_b_rate")
                or last_submission_artifact.get("strict_ready_given_raw_b_rate")
                or 0.0
            ),
            last_live_ready_given_raw_b_count=int(
                last_summary.get("live_ready_given_raw_b_count")
                or last_result.get("live_ready_given_raw_b_count")
                or last_submission_artifact.get("live_ready_given_raw_b_count")
                or 0
            ),
            last_live_ready_given_raw_b_rate=float(
                last_summary.get("live_ready_given_raw_b_rate")
                or last_result.get("live_ready_given_raw_b_rate")
                or last_submission_artifact.get("live_ready_given_raw_b_rate")
                or 0.0
            ),
            last_validation_family_quality_panel=[
                dict(item or {})
                for item in list(
                    last_summary.get("validation_family_quality_panel")
                    or last_result.get("validation_family_quality_panel")
                    or last_submission_artifact.get("validation_family_quality_panel")
                    or []
                )
                if isinstance(item, dict)
            ],
            quality_baseline=dict(d.get("quality_baseline") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "running": self.running,
            "schedule_mode": self.schedule_mode,
            "runtime_enabled": self.runtime_enabled,
            "event_runtime_mode": self.event_runtime_mode,
            "last_run": self.last_run,
            "last_status": self.last_status,
            "daily_run_count": self.daily_run_count,
            "max_daily_runs": self.max_daily_runs,
            "cycle_count": self.cycle_count,
            "factor_auto_refresh_enabled": self.factor_auto_refresh_enabled,
            "readiness_hard_block_enabled": self.readiness_hard_block_enabled,
            "readiness_min_score": self.readiness_min_score,
            "last_stock_family_allocation_count": self.last_stock_family_allocation_count,
            "last_family_preference_order": list(self.last_family_preference_order),
            "last_governed_pending_candidate_count": self.last_governed_pending_candidate_count,
            "last_candidate_local_attempt_count": self.last_candidate_local_attempt_count,
            "last_task_local_attempt_count": self.last_task_local_attempt_count,
            "last_cohort_effective_trials": self.last_cohort_effective_trials,
            "last_refresh_existing_count": self.last_refresh_existing_count,
            "last_spawn_revision_from_existing_count": self.last_spawn_revision_from_existing_count,
            "last_unique_family_holding_universe_count": self.last_unique_family_holding_universe_count,
            "last_economic_semantics_missing_count": self.last_economic_semantics_missing_count,
            "last_research_only_count": self.last_research_only_count,
            "last_deferred_submission_count": self.last_deferred_submission_count,
            "last_validation_grade_distribution": dict(self.last_validation_grade_distribution),
            "last_raw_validation_grade_distribution": dict(
                self.last_raw_validation_grade_distribution
            ),
            "last_effective_validation_grade_distribution": dict(
                self.last_effective_validation_grade_distribution
            ),
            "last_raw_validation_total_score_mean": self.last_raw_validation_total_score_mean,
            "last_raw_validation_total_score_p50": self.last_raw_validation_total_score_p50,
            "last_raw_validation_total_score_p90": self.last_raw_validation_total_score_p90,
            "last_raw_validation_a_rate": self.last_raw_validation_a_rate,
            "last_raw_validation_b_rate": self.last_raw_validation_b_rate,
            "last_raw_validation_c_rate": self.last_raw_validation_c_rate,
            "last_raw_validation_d_rate": self.last_raw_validation_d_rate,
            "last_strict_incubation_ready_count": self.last_strict_incubation_ready_count,
            "last_strict_incubation_ready_rate": self.last_strict_incubation_ready_rate,
            "last_live_candidate_ready_count": self.last_live_candidate_ready_count,
            "last_live_candidate_ready_rate": self.last_live_candidate_ready_rate,
            "last_raw_b_or_above_count": self.last_raw_b_or_above_count,
            "last_raw_b_or_above_rate": self.last_raw_b_or_above_rate,
            "last_strict_ready_given_raw_b_count": self.last_strict_ready_given_raw_b_count,
            "last_strict_ready_given_raw_b_rate": self.last_strict_ready_given_raw_b_rate,
            "last_live_ready_given_raw_b_count": self.last_live_ready_given_raw_b_count,
            "last_live_ready_given_raw_b_rate": self.last_live_ready_given_raw_b_rate,
            "last_validation_family_quality_panel": list(self.last_validation_family_quality_panel),
            "quality_baseline": dict(self.quality_baseline),
        }
        if self.last_family_preference_source_mode:
            result["last_family_preference_source_mode"] = self.last_family_preference_source_mode
        if self.last_governed_candidate_pool_provisional_spillover_policy_status:
            result["last_governed_candidate_pool_provisional_spillover_policy_status"] = (
                self.last_governed_candidate_pool_provisional_spillover_policy_status
            )
        if self.last_external_llm_provider_health_status:
            result["last_external_llm_provider_health_status"] = (
                self.last_external_llm_provider_health_status
            )
        if self.last_external_llm_provider_control_mode:
            result["last_external_llm_provider_control_mode"] = (
                self.last_external_llm_provider_control_mode
            )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_research_plane_detail(data: dict[str, Any]) -> dict[str, Any]:
    raw = dict(data or {})
    research_plane = dict(raw.get("research_plane") or {})
    if research_plane:
        return research_plane
    snapshot = dict(raw.get("snapshot") or {})
    stages = dict(raw.get("stages") or {})
    factor_stage = dict(stages.get("factor_research") or {})
    autonomy_stage = dict(stages.get("autonomy") or {})
    factor_research = dict(raw.get("factor_research") or snapshot.get("factor_research") or {})
    if factor_stage.get("research_artifact") and not factor_research.get("research_artifact"):
        factor_research = {
            **factor_research,
            "research_artifact": dict(factor_stage.get("research_artifact") or {}),
        }
    experiments_payload = dict(raw.get("experiments") or {})
    experiments = list(experiments_payload.get("items") or raw.get("experiment_records") or [])
    return build_research_plane_artifact(
        factor_research=factor_research,
        readiness=dict(raw.get("readiness") or {}),
        autonomy_stage=autonomy_stage,
        candidates=list(raw.get("candidates") or []),
        experiments=experiments,
    )


def _normalize_governance_plane_detail(data: dict[str, Any]) -> dict[str, Any]:
    raw = dict(data or {})
    governance_plane = dict(raw.get("governance_plane") or {})
    if governance_plane:
        return governance_plane

    stages = dict(raw.get("stages") or {})
    quality_gate_report = dict(
        raw.get("quality_gate")
        or raw.get("gate_report")
        or stages.get("quality_gate")
        or {}
    )
    backtest_report = dict(
        raw.get("backtest_report")
        or stages.get("backtest")
        or {}
    )
    dedup_report = dict(
        raw.get("dedup_report")
        or stages.get("deduplicate")
        or {}
    )
    submit_result = dict(
        raw.get("submit_result")
        or stages.get("submit")
        or {}
    )
    return build_governance_plane_artifact(
        quality_gate_report=quality_gate_report,
        backtest_report=backtest_report,
        dedup_report=dedup_report,
        submit_result=submit_result,
    )

def normalize_run_result_to_detail(data: dict[str, Any]) -> FactoryRunDetailDTO:
    """Convert a raw cycle-runner result dict to a stable detail DTO."""
    return FactoryRunDetailDTO.from_dict(data)


def normalize_run_result_to_summary(data: dict[str, Any]) -> FactoryRunSummaryDTO:
    """Convert a raw cycle-runner result dict to a stable summary DTO."""
    return FactoryRunSummaryDTO.from_dict(data)


__all__ = [
    "FactoryRunDetailDTO",
    "FactoryRunSummaryDTO",
    "FactoryStatusDTO",
    "StageResultDTO",
    "normalize_run_result_to_detail",
    "normalize_run_result_to_summary",
]
