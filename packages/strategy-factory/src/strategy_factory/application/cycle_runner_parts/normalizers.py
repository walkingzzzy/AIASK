    """Runs one strategy factory cycle without owning scheduling state."""

    def __init__(self, scheduler: "StrategyFactoryScheduler", context: FactoryRunContext):
        self._scheduler = scheduler
        self._context = context
        self._readiness_service = getattr(self._scheduler, "_readiness_service", ReadinessService())
        self._research_runner = ResearchPlaneRunner(
            self._scheduler,
            self._context.factory_pkg,
        )

    async def _build_factor_research_artifact(self, factor_gateway, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        return await self._research_runner.build_factor_research_artifact(
            factor_gateway,
            db,
            snapshot,
        )

    def _build_factory_readiness(
        self,
        snapshot: dict[str, Any],
        factor_research: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return self._readiness_service.evaluate(snapshot, factor_research)

    @staticmethod
    def _resolve_readiness_stage_status(readiness: dict[str, Any]) -> StageStatus:
        if not bool(readiness.get("can_proceed")):
            return StageStatus.FAILED
        critical_blockers = [
            str(item or "").strip()
            for item in list(readiness.get("critical_blockers") or [])
            if str(item or "").strip()
        ]
        soft_blockers = [
            str(item or "").strip()
            for item in list(readiness.get("blockers") or [])
            if str(item or "").strip()
        ]
        if critical_blockers or soft_blockers:
            return StageStatus.PARTIAL
        return StageStatus.COMPLETED

    async def _persist_enriched_snapshot(self, db, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        if bool(self._context.read_only):
            return None
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
        return self._research_runner.build_research_plane(
            snapshot=snapshot,
            readiness=readiness,
            autonomy_stage=autonomy_stage,
            candidates=candidates,
            experiments=experiments,
        )

    def _attach_result_contracts(self, results: FactoryRunResult) -> FactoryRunResult:
        run_header = build_run_header(
            run_id=self._context.run_id,
            trace_id=self._context.trace_id,
            started_at=str(results.get("started_at") or self._context.start.isoformat()),
            execution_mode=self._context.execution_mode,
            engine_version=self._context.engine_version,
            parity_role=self._context.parity_role,
            read_only=self._context.read_only,
        )
        artifacts = build_run_artifacts(results)
        stage_results = summarize_stage_results(dict(results.get("stages") or {}))
        summary = dict(results.get("summary") or {})
        summary.setdefault("execution_mode", run_header.get("execution_mode"))
        summary.setdefault("engine_version", run_header.get("engine_version"))
        summary.setdefault("read_only", run_header.get("read_only"))
        results["run_header"] = run_header
        results["execution_mode"] = run_header.get("execution_mode")
        results["engine_version"] = run_header.get("engine_version")
        results["summary"] = summary
        results["stage_results"] = stage_results
        results["artifacts"] = artifacts
        results["artifact_refs"] = build_artifact_refs(artifacts)
        results.setdefault("parity_result", {})
        return results

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
                "research_candidate_origin_counts": dict(
                    candidate_artifact.get("candidate_origin_counts") or {}
                ),
                "research_local_rule_candidate_count": int(
                    candidate_artifact.get("local_rule_candidate_count") or 0
                ),
                "research_external_autonomy_candidate_count": int(
                    candidate_artifact.get("external_autonomy_candidate_count") or 0
                ),
                "research_governed_candidate_activation_count": int(
                    candidate_artifact.get("governed_candidate_activation_count") or 0
                ),
                "research_experiment_count": int(evidence_artifact.get("experiment_count") or 0),
                "research_task_evidence_count": int(evidence_artifact.get("task_evidence_count") or 0),
                "research_task_origin_counts": dict(task_artifact.get("task_origin_counts") or {}),
                "research_governed_candidate_activation_task_count": int(
                    task_artifact.get("governed_candidate_activation_task_count") or 0
                ),
                "router_artifact_contract_version": task_artifact.get(
                    "router_artifact_contract_version"
                ),
                "router_enabled": bool(task_artifact.get("router_enabled")),
                "router_strict": bool(task_artifact.get("router_strict")),
                "router_telemetry_enabled": bool(task_artifact.get("router_telemetry_enabled")),
                "router_candidate_stock_count": int(
                    task_artifact.get("router_candidate_stock_count") or 0
                ),
                "router_applied_count": int(task_artifact.get("router_applied_count") or 0),
                "router_status_counts": dict(task_artifact.get("router_status_counts") or {}),
                "router_fallback_reason_counts": dict(
                    task_artifact.get("router_fallback_reason_counts") or {}
                ),
                "router_family_counts": dict(task_artifact.get("router_family_counts") or {}),
                "router_holding_bucket_counts": dict(
                    task_artifact.get("router_holding_bucket_counts") or {}
                ),
                "profile_summary_present_count": int(
                    task_artifact.get("profile_summary_present_count") or 0
                ),
                "profile_summary_missing_count": int(
                    task_artifact.get("profile_summary_missing_count") or 0
                ),
                "profile_summary_generated_count": int(
                    task_artifact.get("profile_summary_generated_count") or 0
                ),
                "selected_router_applied_count": int(
                    task_artifact.get("selected_router_applied_count") or 0
                ),
                "selected_profile_summary_missing_count": int(
                    task_artifact.get("selected_profile_summary_missing_count") or 0
                ),
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
        refresh_existing_count = max(
            int(payload.get("refresh_existing_count") or 0),
            int(dedup_artifact.get("refreshed_existing_count") or 0),
        )
        spawn_revision_from_existing_count = max(
            int(payload.get("spawn_revision_from_existing_count") or 0),
            int(
                dict(dedup_artifact.get("refresh_mode_counts") or {}).get(
                    "spawn_revision_from_existing"
                )
                or 0
            ),
        )
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
                "refresh_existing_count": refresh_existing_count,
                "spawn_revision_from_existing_count": spawn_revision_from_existing_count,
                "research_only_count": int(submission_artifact.get("research_only_count") or 0),
                "deferred_submission_count": int(
                    submission_artifact.get("deferred_submission_count") or 0
                ),
                "validation_grade_distribution": dict(
                    submission_artifact.get("validation_grade_distribution") or {}
                ),
                "raw_validation_grade_distribution": dict(
                    submission_artifact.get("raw_validation_grade_distribution") or {}
                ),
                "effective_validation_grade_distribution": dict(
                    submission_artifact.get("effective_validation_grade_distribution") or {}
                ),
                "raw_validation_total_score_mean": float(
                    submission_artifact.get("raw_validation_total_score_mean") or 0.0
                ),
                "raw_validation_total_score_p50": float(
                    submission_artifact.get("raw_validation_total_score_p50") or 0.0
                ),
                "raw_validation_total_score_p90": float(
                    submission_artifact.get("raw_validation_total_score_p90") or 0.0
                ),
                "raw_validation_a_rate": float(
                    submission_artifact.get("raw_validation_a_rate") or 0.0
                ),
                "raw_validation_b_rate": float(
                    submission_artifact.get("raw_validation_b_rate") or 0.0
                ),
                "raw_validation_c_rate": float(
                    submission_artifact.get("raw_validation_c_rate") or 0.0
                ),
                "raw_validation_d_rate": float(
                    submission_artifact.get("raw_validation_d_rate") or 0.0
                ),
                "strict_incubation_ready_count": int(
                    submission_artifact.get("strict_incubation_ready_count") or 0
                ),
                "strict_incubation_ready_rate": float(
                    submission_artifact.get("strict_incubation_ready_rate") or 0.0
                ),
                "live_candidate_ready_count": int(
                    submission_artifact.get("live_candidate_ready_count") or 0
                ),
                "live_candidate_ready_rate": float(
                    submission_artifact.get("live_candidate_ready_rate") or 0.0
                ),
                "raw_b_or_above_count": int(
                    submission_artifact.get("raw_b_or_above_count") or 0
                ),
                "raw_b_or_above_rate": float(
                    submission_artifact.get("raw_b_or_above_rate") or 0.0
                ),
                "strict_ready_given_raw_b_count": int(
                    submission_artifact.get("strict_ready_given_raw_b_count") or 0
                ),
                "strict_ready_given_raw_b_rate": float(
                    submission_artifact.get("strict_ready_given_raw_b_rate") or 0.0
                ),
                "live_ready_given_raw_b_count": int(
                    submission_artifact.get("live_ready_given_raw_b_count") or 0
                ),
                "live_ready_given_raw_b_rate": float(
                    submission_artifact.get("live_ready_given_raw_b_rate") or 0.0
                ),
                "validation_family_quality_panel": list(
                    submission_artifact.get("validation_family_quality_panel") or []
                ),
                "candidate_local_attempt_count": int(
                    submission_artifact.get("candidate_local_attempt_count") or 0
                ),
                "task_local_attempt_count": int(
                    submission_artifact.get("task_local_attempt_count") or 0
                ),
                "cohort_effective_trials": round(
                    float(submission_artifact.get("cohort_effective_trials") or 0.0),
                    4,
                ),
                "unique_family_holding_universe_count": int(
                    submission_artifact.get("unique_family_holding_universe_count") or 0
                ),
                "economic_semantics_missing_count": int(
                    submission_artifact.get("economic_semantics_missing_count") or 0
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
