
        @classmethod
        def _build_layered_run_summary(
            cls,
            summary: Optional[dict[str, Any]],
            submit_result: Optional[dict],
        ) -> dict[str, Any]:
            base = dict(summary or {})
            strategies = list((submit_result or {}).get("strategies") or [])
            submission_lane_counts: dict[str, int] = {}
            submission_action_type_counts: dict[str, int] = {}
            strategy_status_counts: dict[str, int] = {}
            live_candidate_ready_count = 0
            live_review_ready_count = 0

            def _normalized_text(value: Any) -> str:
                return str(value or "").strip().lower()

            def _count_value(bucket: dict[str, int], value: Any) -> None:
                key = _normalized_text(value)
                if not key:
                    return
                bucket[key] = bucket.get(key, 0) + 1

            def _family_value(record: dict[str, Any]) -> str:
                provenance = dict(record.get("candidate_provenance") or {})
                return _normalized_text(
                    record.get("candidate_family_id")
                    or provenance.get("candidate_family_id")
                    or record.get("candidate_family")
                    or provenance.get("candidate_family")
                    or record.get("strategy_type")
                )

            def _task_source_value(record: dict[str, Any]) -> str:
                research_task = dict(record.get("research_task") or {})
                return _normalized_text(research_task.get("task_source") or record.get("task_source"))

            def _generator_value(record: dict[str, Any]) -> str:
                provenance = dict(record.get("candidate_provenance") or {})
                return _normalized_text(
                    record.get("generator_type")
                    or record.get("generator_mode")
                    or provenance.get("generator_mode")
                    or provenance.get("generator_type")
                )

            def _refresh_mode_value(record: dict[str, Any]) -> str:
                return _normalized_text(
                    record.get("refresh_mode")
                    or dict(record.get("dedup_result") or {}).get("refresh_mode")
                )

            def _source_mix(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
                generator_counts: dict[str, int] = {}
                task_source_counts: dict[str, int] = {}
                lane_counts: dict[str, int] = {}
                for record in records:
                    _count_value(generator_counts, _generator_value(record))
                    _count_value(task_source_counts, _task_source_value(record))
                    _count_value(lane_counts, record.get("submission_lane"))
                return {
                    "generator_type_counts": generator_counts,
                    "task_source_counts": task_source_counts,
                    "submission_lane_counts": lane_counts,
                }

            def _family_mix(records: list[dict[str, Any]]) -> dict[str, int]:
                counts: dict[str, int] = {}
                for record in records:
                    _count_value(counts, _family_value(record))
                return counts

            def _refresh_ratio(records: list[dict[str, Any]]) -> dict[str, Any]:
                mode_counts: dict[str, int] = {}
                for record in records:
                    _count_value(mode_counts, _refresh_mode_value(record))
                refresh_count = sum(count for key, count in mode_counts.items() if key)
                denominator = len(records)
                return {
                    "count": refresh_count,
                    "denominator": denominator,
                    "ratio": round(refresh_count / denominator, 4) if denominator else 0.0,
                    "mode_counts": mode_counts,
                }

            def _promotion_ratio(numerator: int, denominator: int) -> dict[str, Any]:
                return {
                    "count": int(numerator),
                    "denominator": int(denominator),
                    "ratio": round(float(numerator) / float(denominator), 4) if denominator else 0.0,
                }

            for item in strategies:
                record = dict(item or {})
                if bool(record.get("live_candidate_ready")):
                    live_candidate_ready_count += 1
                if bool(record.get("live_review_ready")):
                    live_review_ready_count += 1
                submission_lane = str(record.get("submission_lane") or "").strip().lower()
                if submission_lane:
                    submission_lane_counts[submission_lane] = submission_lane_counts.get(submission_lane, 0) + 1
                submission_action_type = str(record.get("submission_action_type") or "").strip().lower()
                if submission_action_type:
                    submission_action_type_counts[submission_action_type] = (
                        submission_action_type_counts.get(submission_action_type, 0) + 1
                    )
                status = str(record.get("status") or record.get("final_status") or "").strip().lower()
                if status:
                    strategy_status_counts[status] = strategy_status_counts.get(status, 0) + 1

            research_records = [dict(item or {}) for item in strategies]
            incubation_records = [dict(item or {}) for item in strategies]
            live_ready_records = [
                dict(item or {})
                for item in strategies
                if bool((item or {}).get("live_candidate_ready"))
                or bool((item or {}).get("live_review_ready"))
                or bool((item or {}).get("direct_trade_candidate"))
                or bool((item or {}).get("promotion_review_id"))
                or bool((item or {}).get("paper_account_id"))
                or _normalized_text((item or {}).get("submission_lane")) == "live_ready_review"
            ]

            return {
                "research_summary": {
                    "runtime_enabled": bool(base.get("runtime_enabled", True)),
                    "event_runtime_mode": base.get("event_runtime_mode"),
                    "research_plane_contract_version": base.get("research_plane_contract_version"),
                    "research_artifact_contract_version": base.get("research_artifact_contract_version"),
                    "task_artifact_contract_version": base.get("research_task_artifact_contract_version"),
                    "candidate_artifact_contract_version": base.get(
                        "research_candidate_artifact_contract_version"
                    ),
                    "evidence_artifact_contract_version": base.get(
                        "research_evidence_artifact_contract_version"
                    ),
                    "task_contract_observed": bool(base.get("research_task_artifact_available")),
                    "candidate_contract_observed": bool(base.get("research_candidate_artifact_available")),
                    "evidence_contract_observed": bool(base.get("research_evidence_artifact_available")),
                    "readiness_score": base.get("factory_readiness_score"),
                    "readiness_can_proceed": bool(base.get("factory_readiness_can_proceed", True)),
                    "factor_source_mode": base.get("factor_source_mode"),
                    "factor_llm_provider_health_status": base.get("factor_llm_provider_health_status"),
                    "factor_llm_provider_ready": bool(base.get("factor_llm_provider_ready")),
                    "governed_candidate_pool_active": bool(base.get("governed_candidate_pool_active")),
                    "governed_candidate_pool_runtime_state": base.get("governed_candidate_pool_runtime_state"),
                    "governed_candidate_pool_mode": base.get("governed_candidate_pool_mode"),
                    "governed_candidate_pool_provisional": bool(base.get("governed_candidate_pool_provisional")),
                    "spawned_candidate_count": int(base.get("candidates_spawned") or 0),
                    "autonomy_generated_count": int(base.get("autonomy_generated") or 0),
                    "autonomy_task_count": int(base.get("autonomy_task_count") or 0),
                    "research_task_count": int(base.get("research_task_count") or 0),
                    "research_candidate_count": int(base.get("research_candidate_count") or 0),
                    "candidate_origin_counts": dict(base.get("research_candidate_origin_counts") or {}),
                    "local_rule_candidate_count": int(
                        base.get("research_local_rule_candidate_count") or 0
                    ),
                    "external_autonomy_candidate_count": int(
                        base.get("research_external_autonomy_candidate_count") or 0
                    ),
                    "governed_candidate_activation_count": int(
                        base.get("research_governed_candidate_activation_count") or 0
                    ),
                    "research_experiment_count": int(base.get("research_experiment_count") or 0),
                    "research_task_evidence_count": int(base.get("research_task_evidence_count") or 0),
                    "task_origin_counts": dict(base.get("research_task_origin_counts") or {}),
                    "governed_candidate_activation_task_count": int(
                        base.get("research_governed_candidate_activation_task_count") or 0
                    ),
                    "snapshot_task_count": int(base.get("snapshot_task_count") or 0),
                    "bulk_stock_task_count": int(base.get("bulk_stock_task_count") or 0),
                    "gate_0_passed": int(base.get("gate_0_passed") or 0),
                    "pre_gate_passed": int(base.get("pre_gate_passed") or 0),
                    "gate_1_passed": int(base.get("gate_1_passed") or 0),
                    "gate_2_input": int(base.get("gate_2_input") or 0),
                    "gate_2_passed": int(base.get("gate_2_passed") or 0),
                    "gate_2_failed": int(base.get("candidates_failed_backtest") or 0),
                    "source_mix": _source_mix(research_records),
                    "family_mix": _family_mix(research_records),
                    "gate_hit": {
                        "gate_0_passed": int(base.get("gate_0_passed") or 0),
                        "pre_gate_passed": int(base.get("pre_gate_passed") or 0),
                        "gate_1_passed": int(base.get("gate_1_passed") or 0),
                        "gate_2_input": int(base.get("gate_2_input") or 0),
                        "gate_2_passed": int(base.get("gate_2_passed") or 0),
                        "gate_2_failed": int(base.get("candidates_failed_backtest") or 0),
                    },
                    "refresh_ratio": _refresh_ratio(research_records),
                    "promotion_ratio": _promotion_ratio(
                        live_candidate_ready_count,
                        len(research_records),
                    ),
                },
                "feedback_summary": {
                    "lifecycle_feedback_input_contract_version": base.get(
                        "lifecycle_feedback_input_contract_version"
                    ),
                    "lifecycle_feedback_input_observed": bool(
                        base.get("lifecycle_feedback_input_available")
                    ),
                    "feedback_available": bool(base.get("budget_feedback_available")),
                    "family_count": int(base.get("budget_feedback_family_count") or 0),
                    "strategy_count": int(base.get("budget_feedback_strategy_count") or 0),
                    "target_pool_scope_count": int(
                        base.get("budget_feedback_target_pool_scope_count") or 0
                    ),
                    "generator_mode_scope_count": int(
                        base.get("budget_feedback_generator_mode_scope_count") or 0
                    ),
                    "runtime_alert_count": int(
                        base.get("budget_feedback_runtime_alert_count") or 0
                    ),
                    "runtime_risk_event_count": int(
                        base.get("budget_feedback_runtime_risk_event_count") or 0
                    ),
                    "promotion_review_count": int(
                        base.get("budget_feedback_promotion_review_count") or 0
                    ),
                    "promotion_review_status_counts": dict(
                        base.get("budget_feedback_promotion_review_status_counts") or {}
                    ),
                    "paper_hit_ratio": float(base.get("budget_feedback_paper_hit_ratio") or 0.5),
                    "paper_skill_lcb": float(base.get("budget_feedback_paper_skill_lcb") or 0.0),
                    "paper_recent_skill_lcb": float(
                        base.get("budget_feedback_paper_recent_skill_lcb") or 0.0
                    ),
                    "paper_stability_gap": float(
                        base.get("budget_feedback_paper_stability_gap") or 0.0
                    ),
                    "paper_coverage_ratio": float(
                        base.get("budget_feedback_paper_coverage_ratio") or 1.0
                    ),
                    "execution_conversion_efficiency": (
                        float(base.get("budget_feedback_execution_conversion_efficiency"))
                        if base.get("budget_feedback_execution_conversion_efficiency") is not None
                        else None
                    ),
                    "execution_conversion_efficiency_observed_count": int(
                        base.get(
                            "budget_feedback_execution_conversion_efficiency_observed_count"
                        )
                        or 0
                    ),
                    "legacy_control_mode_counts": dict(
                        base.get("budget_feedback_legacy_control_mode_counts") or {}
                    ),
                    "skill_control_mode_counts": dict(
                        base.get("budget_feedback_skill_control_mode_counts") or {}
                    ),
                    "budget_action_counts": dict(
                        base.get("budget_feedback_action_counts") or {}
                    ),
                    "dual_axis_action_family_count": int(
                        base.get("budget_feedback_dual_axis_action_family_count") or 0
                    ),
                    "execution_optimization_queue_count": int(
                        base.get("budget_feedback_execution_optimization_queue_count") or 0
                    ),
                    "small_budget_observe_count": int(
                        base.get("budget_feedback_small_budget_observe_count") or 0
                    ),
                    "prioritize_scale_count": int(
                        base.get("budget_feedback_prioritize_scale_count") or 0
                    ),
                    "cool_or_freeze_count": int(
                        base.get("budget_feedback_cool_or_freeze_count") or 0
                    ),
                    "retain_family_reduce_budget_count": int(
                        base.get("budget_feedback_retain_family_reduce_budget_count") or 0
                    ),
                    "signal_count_total": int(base.get("budget_feedback_signal_count_total") or 0),
                    "zero_signal_strategy_count": int(
                        base.get("budget_feedback_zero_signal_strategy_count") or 0
                    ),
                    "zero_signal_ratio": float(
                        base.get("budget_feedback_zero_signal_ratio") or 0.0
                    ),
                    "low_signal_strategy_count": int(
                        base.get("budget_feedback_low_signal_strategy_count") or 0
                    ),
                    "low_signal_ratio": float(base.get("budget_feedback_low_signal_ratio") or 0.0),
                    "observed_forward_window_count": int(
                        base.get("budget_feedback_observed_forward_window_count") or 0
                    ),
                    "missing_forward_window_count": int(
                        base.get("budget_feedback_missing_forward_window_count") or 0
                    ),
                    "expected_forward_window_count": int(
                        base.get("budget_feedback_expected_forward_window_count") or 0
                    ),
                    "forward_window_coverage_ratio": float(
                        base.get("budget_feedback_forward_window_coverage_ratio") or 1.0
                    ),
                    "promotion_ready_count": int(
                        base.get("budget_feedback_promotion_ready_count") or 0
                    ),
                    "promotion_ready_ratio": float(
                        base.get("budget_feedback_promotion_ready_ratio") or 1.0
                    ),
                    "promotion_review_coverage_ratio": float(
                        base.get("budget_feedback_promotion_review_coverage_ratio") or 1.0
                    ),
                    "evidence_debt_strategy_count": int(
                        base.get("budget_feedback_evidence_debt_strategy_count") or 0
                    ),
                    "evidence_debt_ratio": float(
                        base.get("budget_feedback_evidence_debt_ratio") or 0.0
                    ),
                    "blocked_task_count": int(base.get("blocked_feedback_task_count") or 0),
                    "planned_cooldown_task_count": int(
                        base.get("planned_feedback_cooldown_task_count") or 0
                    ),
                    "planned_control_mode_counts": dict(
                        base.get("planned_feedback_control_mode_counts") or {}
                    ),
                    "planned_legacy_control_mode_counts": dict(
                        base.get("planned_feedback_legacy_control_mode_counts")
                        or base.get("planned_feedback_control_mode_counts")
                        or {}
                    ),
                    "planned_skill_control_mode_counts": dict(
                        base.get("planned_feedback_skill_control_mode_counts") or {}
                    ),
                    "planned_target_pool_control_mode_counts": dict(
                        base.get("planned_feedback_target_pool_control_mode_counts") or {}
                    ),
                    "planned_holding_bucket_control_mode_counts": dict(
                        base.get("planned_feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "planned_generator_mode_control_mode_counts": dict(
                        base.get("planned_feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "planned_skill_target_pool_control_mode_counts": dict(
                        base.get("planned_feedback_skill_target_pool_control_mode_counts") or {}
                    ),
                    "planned_skill_holding_bucket_control_mode_counts": dict(
                        base.get("planned_feedback_skill_holding_bucket_control_mode_counts")
                        or {}
                    ),
                    "planned_skill_generator_mode_control_mode_counts": dict(
                        base.get("planned_feedback_skill_generator_mode_control_mode_counts")
                        or {}
                    ),
                    "selected_control_mode_counts": dict(
                        base.get("selected_feedback_control_mode_counts") or {}
                    ),
                    "selected_legacy_control_mode_counts": dict(
                        base.get("selected_feedback_legacy_control_mode_counts")
                        or base.get("selected_feedback_control_mode_counts")
                        or {}
                    ),
                    "selected_skill_control_mode_counts": dict(
                        base.get("selected_feedback_skill_control_mode_counts") or {}
                    ),
                    "selected_target_pool_control_mode_counts": dict(
                        base.get("selected_feedback_target_pool_control_mode_counts") or {}
                    ),
                    "selected_holding_bucket_control_mode_counts": dict(
                        base.get("selected_feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "selected_generator_mode_control_mode_counts": dict(
                        base.get("selected_feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "selected_skill_target_pool_control_mode_counts": dict(
                        base.get("selected_feedback_skill_target_pool_control_mode_counts") or {}
                    ),
                    "selected_skill_holding_bucket_control_mode_counts": dict(
                        base.get("selected_feedback_skill_holding_bucket_control_mode_counts")
                        or {}
                    ),
                    "selected_skill_generator_mode_control_mode_counts": dict(
                        base.get("selected_feedback_skill_generator_mode_control_mode_counts")
                        or {}
                    ),
                    "submission_control_mode_counts": dict(
                        base.get("feedback_control_mode_counts") or {}
                    ),
                    "submission_legacy_control_mode_counts": dict(
                        base.get("feedback_legacy_control_mode_counts")
                        or base.get("feedback_control_mode_counts")
                        or {}
                    ),
                    "submission_skill_control_mode_counts": dict(
                        base.get("feedback_skill_control_mode_counts") or {}
                    ),
                    "submission_target_pool_control_mode_counts": dict(
                        base.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "submission_holding_bucket_control_mode_counts": dict(
                        base.get("feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "submission_generator_mode_control_mode_counts": dict(
                        base.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "submission_skill_target_pool_control_mode_counts": dict(
                        base.get("feedback_skill_target_pool_control_mode_counts") or {}
                    ),
                    "submission_skill_holding_bucket_control_mode_counts": dict(
                        base.get("feedback_skill_holding_bucket_control_mode_counts") or {}
                    ),
                    "submission_skill_generator_mode_control_mode_counts": dict(
                        base.get("feedback_skill_generator_mode_control_mode_counts") or {}
                    ),
                    "suppressed_families": list(base.get("suppressed_families") or []),
                    "suppressed_target_pools": list(base.get("suppressed_target_pools") or []),
                    "suppressed_generator_modes": list(base.get("suppressed_generator_modes") or []),
                },
                "incubation_summary": {
                    "candidates_after_dedup": int(base.get("candidates_after_dedup") or 0),
                    "gate_3_input": int(base.get("gate_3_input") or 0),
                    "gate_3_passed": int(base.get("gate_3_passed") or 0),
                    "gate_3_failed": int(base.get("gate_3_failed") or 0),
                    "submitted_count": int(base.get("submitted") or 0),
                    "created_strategy_pool_count": int(base.get("created_strategy_pool") or 0),
                    "created_audit_only_count": int(base.get("created_audit_only") or 0),
                    "formal_incubation_count": int(base.get("formal_incubation_count") or 0),
                    "observe_incubation_count": int(base.get("observe_incubation_count") or 0),
                    "deferred_budget_queue_count": int(base.get("deferred_budget_queue_count") or 0),
                    "refresh_metrics_only_count": int(base.get("refresh_metrics_only_count") or 0),
                    "spawn_revision_from_existing_count": int(base.get("spawn_revision_from_existing_count") or 0),
                    "revision_creation_ratio": cls._safe_float(base.get("revision_creation_ratio")),
                    "refresh_absorption_ratio": cls._safe_float(base.get("refresh_absorption_ratio")),
                    "refresh_decision_basis_counts": dict(base.get("refresh_decision_basis_counts") or {}),
                    "revision_trigger_reason_counts": dict(base.get("revision_trigger_reason_counts") or {}),
                    "generator_mode_submission_metrics": dict(base.get("generator_mode_submission_metrics") or {}),
                    "tested_object_hash_changed_count": int(base.get("tested_object_hash_changed_count") or 0),
                    "existing_identity_available_count": int(base.get("existing_identity_available_count") or 0),
                    "existing_tested_object_available_count": int(base.get("existing_tested_object_available_count") or 0),
                    "target_alignment_violation_counts": dict(base.get("target_alignment_violation_counts") or {}),
                    "generator_precompile_reject_reason_counts": dict(
                        base.get("generator_precompile_reject_reason_counts") or {}
                    ),
                    "contract_reject_reason_counts": dict(base.get("contract_reject_reason_counts") or {}),
                    "feedback_control_mode_counts": dict(base.get("feedback_control_mode_counts") or {}),
                    "feedback_legacy_control_mode_counts": dict(
                        base.get("feedback_legacy_control_mode_counts")
                        or base.get("feedback_control_mode_counts")
                        or {}
                    ),
                    "feedback_skill_control_mode_counts": dict(
                        base.get("feedback_skill_control_mode_counts") or {}
                    ),
                    "feedback_target_pool_control_mode_counts": dict(
                        base.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "feedback_holding_bucket_control_mode_counts": dict(
                        base.get("feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "feedback_generator_mode_control_mode_counts": dict(
                        base.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "feedback_skill_target_pool_control_mode_counts": dict(
                        base.get("feedback_skill_target_pool_control_mode_counts") or {}
                    ),
                    "feedback_skill_holding_bucket_control_mode_counts": dict(
                        base.get("feedback_skill_holding_bucket_control_mode_counts") or {}
                    ),
                    "feedback_skill_generator_mode_control_mode_counts": dict(
                        base.get("feedback_skill_generator_mode_control_mode_counts") or {}
                    ),
                    "submission_lane_counts": submission_lane_counts,
                    "submission_action_type_counts": submission_action_type_counts,
                    "strategy_status_counts": strategy_status_counts,
                    "source_mix": _source_mix(incubation_records),
                    "family_mix": _family_mix(incubation_records),
                    "gate_hit": {
                        "gate_3_input": int(base.get("gate_3_input") or 0),
                        "gate_3_passed": int(base.get("gate_3_passed") or 0),
                        "gate_3_failed": int(base.get("gate_3_failed") or 0),
                        "submitted_count": int(base.get("submitted") or 0),
                        "created_strategy_pool_count": int(base.get("created_strategy_pool") or 0),
                    },
                    "refresh_ratio": _refresh_ratio(incubation_records),
                    "promotion_ratio": _promotion_ratio(
                        int(base.get("live_ready_review_count") or live_review_ready_count),
                        len(incubation_records),
                    ),
                },
                "live_ready_summary": {
                    "live_candidate_ready_count": live_candidate_ready_count,
                    "live_review_ready_count": live_review_ready_count,
                    "live_ready_review_count": int(base.get("live_ready_review_count") or 0),
                    "direct_trade_candidate_count": int(base.get("direct_trade_candidate_count") or 0),
                    "paper_account_bound_count": int(base.get("paper_account_bound_count") or 0),
                    "runtime_review_count": int(base.get("runtime_review_count") or 0),
                    "promotion_review_count": int(base.get("promotion_review_count") or 0),
                    "submission_action_type_counts": submission_action_type_counts,
                    "promotion_review_status_counts": dict(base.get("promotion_review_status_counts") or {}),
                    "source_mix": _source_mix(live_ready_records),
                    "family_mix": _family_mix(live_ready_records),
                    "gate_hit": {
                        "live_candidate_ready_count": live_candidate_ready_count,
                        "live_review_ready_count": live_review_ready_count,
                        "live_ready_review_count": int(base.get("live_ready_review_count") or 0),
                        "direct_trade_candidate_count": int(base.get("direct_trade_candidate_count") or 0),
                        "paper_account_bound_count": int(base.get("paper_account_bound_count") or 0),
                        "runtime_review_count": int(base.get("runtime_review_count") or 0),
                        "promotion_review_count": int(base.get("promotion_review_count") or 0),
                    },
                    "refresh_ratio": _refresh_ratio(live_ready_records),
                    "promotion_ratio": _promotion_ratio(
                        int(base.get("promotion_review_count") or 0),
                        max(
                            int(base.get("live_ready_review_count") or 0),
                            len(live_ready_records),
                        ),
                    ),
                },
            }
