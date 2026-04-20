

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
    high_confidence_enabled: bool = False
    evidence_contract_enabled: bool = False
    confidence_diagnostics_enabled: bool = False
    execution_audit_enabled: bool = False
    quality_ui_v2_enabled: bool = False
    research_protocol_v2_enabled: bool = False
    gate_model_v2_enabled: bool = False
    trace_ledger_v2_enabled: bool = False
    feedback_v2_enabled: bool = False
    trace_ledger_v2_implemented: bool = False
    governance_gate_report_v2_implemented: bool = False
    execution_audit_entity_chain_available: bool = False
    spec_completeness_mode: str = "warn"
    feature_flags: dict[str, Any] = field(default_factory=dict)
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
    execution_mode: str = "legacy_primary"
    engine_version: str = "strategy_factory.v2"
    latest_parity_result: dict[str, Any] = field(default_factory=dict)
    capability_health: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryStatusDTO":
        d = dict(data or {})
        last_result = dict(d.get("last_result") or {})
        last_summary = dict(last_result.get("summary") or d.get("last_summary") or {})
        last_submission_artifact = dict(
            (_normalize_governance_plane_detail(last_result).get("submission_artifact") or {})
        )
        feature_flags = {
            "high_confidence_enabled": bool(
                d.get("high_confidence_enabled")
                if d.get("high_confidence_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("high_confidence_enabled")
            ),
            "evidence_contract_enabled": bool(
                d.get("evidence_contract_enabled")
                if d.get("evidence_contract_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("evidence_contract_enabled")
            ),
            "confidence_diagnostics_enabled": bool(
                d.get("confidence_diagnostics_enabled")
                if d.get("confidence_diagnostics_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("confidence_diagnostics_enabled")
            ),
            "execution_audit_enabled": bool(
                d.get("execution_audit_enabled")
                if d.get("execution_audit_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("execution_audit_enabled")
            ),
            "quality_ui_v2_enabled": bool(
                d.get("quality_ui_v2_enabled")
                if d.get("quality_ui_v2_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("quality_ui_v2_enabled")
            ),
            "research_protocol_v2_enabled": bool(
                d.get("research_protocol_v2_enabled")
                if d.get("research_protocol_v2_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("research_protocol_v2_enabled")
            ),
            "gate_model_v2_enabled": bool(
                d.get("gate_model_v2_enabled")
                if d.get("gate_model_v2_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("gate_model_v2_enabled")
            ),
            "trace_ledger_v2_enabled": bool(
                d.get("trace_ledger_v2_enabled")
                if d.get("trace_ledger_v2_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("trace_ledger_v2_enabled")
            ),
            "feedback_v2_enabled": bool(
                d.get("feedback_v2_enabled")
                if d.get("feedback_v2_enabled") is not None
                else dict(d.get("feature_flags") or {}).get("feedback_v2_enabled")
            ),
        }
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
            high_confidence_enabled=feature_flags["high_confidence_enabled"],
            evidence_contract_enabled=feature_flags["evidence_contract_enabled"],
            confidence_diagnostics_enabled=feature_flags["confidence_diagnostics_enabled"],
            execution_audit_enabled=feature_flags["execution_audit_enabled"],
            quality_ui_v2_enabled=feature_flags["quality_ui_v2_enabled"],
            research_protocol_v2_enabled=feature_flags["research_protocol_v2_enabled"],
            gate_model_v2_enabled=feature_flags["gate_model_v2_enabled"],
            trace_ledger_v2_enabled=feature_flags["trace_ledger_v2_enabled"],
            feedback_v2_enabled=feature_flags["feedback_v2_enabled"],
            trace_ledger_v2_implemented=bool(d.get("trace_ledger_v2_implemented")),
            governance_gate_report_v2_implemented=bool(d.get("governance_gate_report_v2_implemented")),
            execution_audit_entity_chain_available=bool(d.get("execution_audit_entity_chain_available")),
            spec_completeness_mode=(
                str(
                    d.get("spec_completeness_mode")
                    or dict(d.get("feature_flags") or {}).get("spec_completeness_mode")
                    or "warn"
                ).strip()
                or "warn"
            ),
            feature_flags=feature_flags,
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
            execution_mode=str(
                d.get("execution_mode") or last_result.get("execution_mode") or "legacy_primary"
            ),
            engine_version=str(
                d.get("engine_version") or last_result.get("engine_version") or "strategy_factory.v2"
            ),
            latest_parity_result=dict(
                d.get("latest_parity_result") or last_result.get("parity_result") or {}
            ),
            capability_health={
                str(key or "").strip(): dict(value or {})
                for key, value in dict(d.get("capability_health") or {}).items()
                if str(key or "").strip()
            },
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
            "high_confidence_enabled": self.high_confidence_enabled,
            "evidence_contract_enabled": self.evidence_contract_enabled,
            "confidence_diagnostics_enabled": self.confidence_diagnostics_enabled,
            "execution_audit_enabled": self.execution_audit_enabled,
            "quality_ui_v2_enabled": self.quality_ui_v2_enabled,
            "research_protocol_v2_enabled": self.research_protocol_v2_enabled,
            "gate_model_v2_enabled": self.gate_model_v2_enabled,
            "trace_ledger_v2_enabled": self.trace_ledger_v2_enabled,
            "feedback_v2_enabled": self.feedback_v2_enabled,
            "trace_ledger_v2_implemented": self.trace_ledger_v2_implemented,
            "governance_gate_report_v2_implemented": self.governance_gate_report_v2_implemented,
            "execution_audit_entity_chain_available": self.execution_audit_entity_chain_available,
            "spec_completeness_mode": self.spec_completeness_mode,
            "feature_flags": {
                "high_confidence_enabled": self.high_confidence_enabled,
                "evidence_contract_enabled": self.evidence_contract_enabled,
                "confidence_diagnostics_enabled": self.confidence_diagnostics_enabled,
                "execution_audit_enabled": self.execution_audit_enabled,
                "quality_ui_v2_enabled": self.quality_ui_v2_enabled,
                "research_protocol_v2_enabled": self.research_protocol_v2_enabled,
                "gate_model_v2_enabled": self.gate_model_v2_enabled,
                "trace_ledger_v2_enabled": self.trace_ledger_v2_enabled,
                "feedback_v2_enabled": self.feedback_v2_enabled,
                "spec_completeness_mode": self.spec_completeness_mode,
                **{
                    str(key): bool(value)
                    for key, value in dict(self.feature_flags).items()
                    if str(key).strip() and not isinstance(value, str)
                },
            },
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
            "execution_mode": self.execution_mode,
            "engine_version": self.engine_version,
            "latest_parity_result": dict(self.latest_parity_result),
            "capability_health": {
                str(key): dict(value or {})
                for key, value in dict(self.capability_health).items()
                if str(key).strip()
            },
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
