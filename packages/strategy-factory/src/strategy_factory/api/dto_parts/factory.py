

# ---------------------------------------------------------------------------
# Factory run summary DTO (list item)
# ---------------------------------------------------------------------------

@dataclass
class FactoryRunSummaryDTO:
    """DTO for a factory run summary as shown in the factory_runs list."""

    run_id: str
    trace_id: str
    prediction_trace_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    elapsed_seconds: float
    candidates_spawned: int
    submitted: int
    submit_stage_entered: bool
    submit_stage_status: Optional[str]
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
    external_llm_provider_control_reasons: list[str] = field(default_factory=list)
    suppressed_generator_modes: list[str] = field(default_factory=list)
    feedback_generator_mode_control_mode_counts: dict[str, int] = field(default_factory=dict)
    external_llm_provider_suppressed: bool = False
    external_llm_provider_cooldown: bool = False
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
    incubation_budget_formal_runtime_ready_candidate_count: int = 0
    incubation_budget_formal_runtime_ready_selected_count: int = 0
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
    prediction_quality_distribution: Optional[dict[str, int]] = None
    execution_quality_distribution: Optional[dict[str, int]] = None
    evidence_alignment_distribution: Optional[dict[str, int]] = None
    confidence_contract_ready_rate: Optional[float] = None
    execution_mode: Optional[str] = None
    engine_version: Optional[str] = None
    parity_status: Optional[str] = None
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryRunSummaryDTO":
        d = dict(data or {})
        summary = dict(d.get("summary") or {})
        audit = dict(d.get("_run_audit") or {})
        submission_artifact = dict(
            (_normalize_governance_plane_detail(d).get("submission_artifact") or {})
        )
        governance_plane = _normalize_governance_plane_detail(d)
        prediction_trace_summary = dict(governance_plane.get("prediction_trace_summary") or {})
        sample_prediction_trace_ids = [
            str(item or "").strip()
            for item in list(prediction_trace_summary.get("sample_trace_ids") or [])
            if str(item or "").strip()
        ]
        raw_stages = dict(d.get("stages") or {})
        submit_stage = (
            dict(raw_stages.get("submit") or {})
            if isinstance(raw_stages.get("submit"), dict)
            else {}
        )
        submit_stage_status_raw = submit_stage.get("status")
        submit_stage_status = (
            normalize_stage_status(submit_stage_status_raw).value
            if submit_stage_status_raw not in (None, "", [], {})
            else None
        )
        submitted = int(
            summary.get("submitted")
            or d.get("submitted")
            or submission_artifact.get("submitted")
            or 0
        )
        research_only_count = int(
            summary.get("research_only_count")
            or d.get("research_only_count")
            or submission_artifact.get("research_only_count")
            or 0
        )
        deferred_submission_count = int(
            summary.get("deferred_submission_count")
            or d.get("deferred_submission_count")
            or submission_artifact.get("deferred_submission_count")
            or 0
        )
        submit_stage_entered = bool(submit_stage) or any(
            count > 0
            for count in (
                submitted,
                research_only_count,
                deferred_submission_count,
            )
        )
        status = normalize_run_status(d.get("status"), default=FactoryRunStatus.FAILED).value
        external_llm_provider_control_mode = (
            str(summary.get("external_llm_provider_control_mode") or d.get("external_llm_provider_control_mode") or "").strip()
            or None
        )
        external_llm_provider_control_reasons = [
            str(item or "").strip()
            for item in list(
                summary.get("external_llm_provider_control_reasons")
                or d.get("external_llm_provider_control_reasons")
                or []
            )
            if str(item or "").strip()
        ]
        suppressed_generator_modes = [
            str(item or "").strip()
            for item in list(
                summary.get("suppressed_generator_modes")
                or d.get("suppressed_generator_modes")
                or []
            )
            if str(item or "").strip()
        ]
        feedback_generator_mode_control_mode_counts = {
            str(key or "").strip(): int(value or 0)
            for key, value in dict(
                summary.get("feedback_generator_mode_control_mode_counts")
                or d.get("feedback_generator_mode_control_mode_counts")
                or {}
            ).items()
            if str(key or "").strip()
        }
        external_llm_provider_suppressed = bool(
            str(external_llm_provider_control_mode or "").strip().lower() == "suppress"
            or "external_llm" in {str(item).strip().lower() for item in suppressed_generator_modes}
            or int(feedback_generator_mode_control_mode_counts.get("suppress") or 0) > 0
        )
        external_llm_provider_cooldown = (
            str(external_llm_provider_control_mode or "").strip().lower() == "cooldown"
        )
        return cls(
            run_id=str(d.get("run_id") or ""),
            trace_id=str(d.get("trace_id") or summary.get("trace_id") or ""),
            prediction_trace_id=(
                str(
                    d.get("prediction_trace_id")
                    or summary.get("prediction_trace_id")
                    or (sample_prediction_trace_ids[0] if sample_prediction_trace_ids else "")
                    or d.get("trace_id")
                    or summary.get("trace_id")
                    or ""
                )
            ),
            status=status,
            started_at=str(d.get("started_at") or ""),
            completed_at=d.get("completed_at"),
            elapsed_seconds=float(d.get("elapsed_seconds") or 0.0),
            candidates_spawned=int(summary.get("candidates_spawned") or 0),
            submitted=submitted,
            submit_stage_entered=submit_stage_entered,
            submit_stage_status=submit_stage_status,
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
            external_llm_provider_control_mode=external_llm_provider_control_mode,
            external_llm_provider_control_reasons=external_llm_provider_control_reasons,
            suppressed_generator_modes=suppressed_generator_modes,
            feedback_generator_mode_control_mode_counts=feedback_generator_mode_control_mode_counts,
            external_llm_provider_suppressed=external_llm_provider_suppressed,
            external_llm_provider_cooldown=external_llm_provider_cooldown,
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
            research_only_count=research_only_count,
            deferred_submission_count=deferred_submission_count,
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
            incubation_budget_formal_runtime_ready_candidate_count=int(
                summary.get("incubation_budget_formal_runtime_ready_candidate_count")
                or d.get("incubation_budget_formal_runtime_ready_candidate_count")
                or submission_artifact.get("formal_runtime_ready_candidate_count")
                or dict(submission_artifact.get("incubation_budget_summary") or {}).get(
                    "formal_runtime_ready_candidate_count"
                )
                or 0
            ),
            incubation_budget_formal_runtime_ready_selected_count=int(
                summary.get("incubation_budget_formal_runtime_ready_selected_count")
                or d.get("incubation_budget_formal_runtime_ready_selected_count")
                or submission_artifact.get("formal_runtime_ready_selected_count")
                or dict(submission_artifact.get("incubation_budget_summary") or {}).get(
                    "formal_runtime_ready_selected_count"
                )
                or 0
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
            prediction_quality_distribution=(
                {
                    str(key or "").strip(): int(value or 0)
                    for key, value in dict(
                        summary.get("prediction_quality_distribution")
                        or d.get("prediction_quality_distribution")
                        or {}
                    ).items()
                    if str(key or "").strip()
                }
                if (
                    summary.get("prediction_quality_distribution")
                    or d.get("prediction_quality_distribution")
                )
                else None
            ),
            execution_quality_distribution=(
                {
                    str(key or "").strip(): int(value or 0)
                    for key, value in dict(
                        summary.get("execution_quality_distribution")
                        or d.get("execution_quality_distribution")
                        or {}
                    ).items()
                    if str(key or "").strip()
                }
                if (
                    summary.get("execution_quality_distribution")
                    or d.get("execution_quality_distribution")
                )
                else None
            ),
            evidence_alignment_distribution=(
                {
                    str(key or "").strip(): int(value or 0)
                    for key, value in dict(
                        summary.get("evidence_alignment_distribution")
                        or d.get("evidence_alignment_distribution")
                        or {}
                    ).items()
                    if str(key or "").strip()
                }
                if (
                    summary.get("evidence_alignment_distribution")
                    or d.get("evidence_alignment_distribution")
                )
                else None
            ),
            confidence_contract_ready_rate=(
                float(
                    summary.get("confidence_contract_ready_rate")
                    if summary.get("confidence_contract_ready_rate") is not None
                    else d.get("confidence_contract_ready_rate")
                )
                if (
                    summary.get("confidence_contract_ready_rate") is not None
                    or d.get("confidence_contract_ready_rate") is not None
                )
                else None
            ),
            execution_mode=(
                str(d.get("execution_mode") or summary.get("execution_mode") or "").strip() or None
            ),
            engine_version=(
                str(d.get("engine_version") or summary.get("engine_version") or "").strip() or None
            ),
            parity_status=(
                str(
                    d.get("parity_status")
                    or summary.get("parity_status")
                    or dict(d.get("parity_result") or {}).get("status")
                    or ""
                ).strip()
                or None
            ),
            artifact_refs=[
                dict(item or {})
                for item in list(d.get("artifact_refs") or summary.get("artifact_refs") or [])
                if isinstance(item, dict)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "prediction_trace_id": self.prediction_trace_id or self.trace_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "candidates_spawned": self.candidates_spawned,
            "submitted": self.submitted,
            "submit_stage_entered": self.submit_stage_entered,
            "eliminated": self.eliminated,
            "hard_failure_count": self.hard_failure_count,
            "degraded_stage_count": self.degraded_stage_count,
            "persistence_failure_count": self.persistence_failure_count,
            "readiness_score": self.readiness_score,
            "readiness_can_proceed": self.readiness_can_proceed,
            "stock_family_allocation_count": self.stock_family_allocation_count,
            "family_preference_order": list(self.family_preference_order),
            "governed_pending_candidate_count": self.governed_pending_candidate_count,
            "external_llm_provider_control_reasons": list(self.external_llm_provider_control_reasons),
            "suppressed_generator_modes": list(self.suppressed_generator_modes),
            "feedback_generator_mode_control_mode_counts": dict(
                self.feedback_generator_mode_control_mode_counts
            ),
            "external_llm_provider_suppressed": self.external_llm_provider_suppressed,
            "external_llm_provider_cooldown": self.external_llm_provider_cooldown,
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
            "incubation_budget_formal_runtime_ready_candidate_count": (
                self.incubation_budget_formal_runtime_ready_candidate_count
            ),
            "incubation_budget_formal_runtime_ready_selected_count": (
                self.incubation_budget_formal_runtime_ready_selected_count
            ),
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
        if self.submit_stage_status:
            result["submit_stage_status"] = self.submit_stage_status
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
        if self.prediction_quality_distribution is not None:
            result["prediction_quality_distribution"] = dict(
                self.prediction_quality_distribution
            )
        if self.execution_quality_distribution is not None:
            result["execution_quality_distribution"] = dict(
                self.execution_quality_distribution
            )
        if self.evidence_alignment_distribution is not None:
            result["evidence_alignment_distribution"] = dict(
                self.evidence_alignment_distribution
            )
        if self.confidence_contract_ready_rate is not None:
            result["confidence_contract_ready_rate"] = (
                self.confidence_contract_ready_rate
            )
        if self.execution_mode:
            result["execution_mode"] = self.execution_mode
        if self.engine_version:
            result["engine_version"] = self.engine_version
        if self.parity_status:
            result["parity_status"] = self.parity_status
        if self.artifact_refs:
            result["artifact_refs"] = list(self.artifact_refs)
        return result
