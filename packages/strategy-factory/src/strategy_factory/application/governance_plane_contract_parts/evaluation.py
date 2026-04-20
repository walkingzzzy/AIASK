

def build_dedup_artifact(
    *,
    dedup_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = dict(dedup_report or {})
    summary = dict(report.get("summary") or {})
    kept = [dict(item or {}) for item in list(report.get("kept") or []) if isinstance(item, dict)]
    dropped = [dict(item or {}) for item in list(report.get("dropped") or []) if isinstance(item, dict)]
    refresh_mode_counts = _count_by([*kept, *dropped], lambda item: dict(item.get("dedup_result") or {}).get("refresh_mode"))
    duplicate_level_counts = _count_by(
        dropped,
        lambda item: dict(item.get("dedup_result") or {}).get("duplicate_level"),
    )
    return {
        "contract_version": DEDUP_ARTIFACT_CONTRACT_VERSION,
        "available": bool(report),
        "input_count": _safe_int(summary.get("input_count")),
        "existing_count": _safe_int(summary.get("existing_count")),
        "existing_scan_count": _safe_int(summary.get("existing_scan_count")),
        "kept_count": _safe_int(summary.get("kept_count"), len(kept)),
        "dropped_count": _safe_int(summary.get("dropped_count"), len(dropped)),
        "refreshed_existing_count": _safe_int(summary.get("refreshed_existing_count")),
        "vector_checks": _safe_int(summary.get("vector_checks")),
        "coarse_hit_ratio": round(_safe_float(summary.get("coarse_hit_ratio")), 4),
        "refresh_mode_counts": refresh_mode_counts,
        "duplicate_level_counts": duplicate_level_counts,
        "refresh_decision_basis_counts": dict(summary.get("refresh_decision_basis_counts") or {}),
        "revision_trigger_reason_counts": dict(summary.get("revision_trigger_reason_counts") or {}),
        "tested_object_hash_changed_count": _safe_int(summary.get("tested_object_hash_changed_count")),
        "existing_identity_available_count": _safe_int(summary.get("existing_identity_available_count")),
        "existing_tested_object_available_count": _safe_int(
            summary.get("existing_tested_object_available_count")
        ),
        "kept_briefs": [_dedup_brief(item) for item in kept[:12]],
        "dropped_briefs": [_dedup_brief(item) for item in dropped[:12]],
    }


def build_submission_artifact(
    *,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(submit_result or {})
    strategies = [dict(item or {}) for item in list(payload.get("strategies") or []) if isinstance(item, dict)]
    submission_lane_counts = _count_by(strategies, lambda item: item.get("submission_lane"))
    submission_action_type_counts = _count_by(strategies, lambda item: item.get("submission_action_type"))
    strategy_status_counts = _count_by(strategies, lambda item: item.get("status"))
    committee_decision_counts = _count_by(strategies, _committee_decision)
    refresh_mode_counts = _count_by(strategies, lambda item: item.get("refresh_mode"))
    primary_validation_layer_counts = _count_by(strategies, _primary_validation_layer)
    validation_profile_counts = _count_by(strategies, _validation_profile_name)
    constraint_violation_counts = _count_by(strategies, _constraint_violation)
    committee_review_count = sum(1 for item in strategies if _has_mapping(item, "committee_review"))
    constraint_check_count = sum(1 for item in strategies if _has_mapping(item, "constraint_check"))
    validation_profile_count = sum(1 for item in strategies if _has_mapping(item, "validation_profile"))
    event_window_config_count = sum(1 for item in strategies if _has_mapping(item, "event_window_config"))
    position_assumption_count = sum(1 for item in strategies if _has_text(item, "position_assumption"))
    cost_assumptions_count = sum(1 for item in strategies if _has_mapping(item, "cost_assumptions"))
    explicit_cost_breakdown_count = sum(
        1 for item in strategies if _has_mapping(item, "explicit_cost_breakdown")
    )
    implicit_cost_breakdown_count = sum(
        1 for item in strategies if _has_mapping(item, "implicit_cost_breakdown")
    )
    attempt_adjustment_count = sum(1 for item in strategies if _has_mapping(item, "attempt_adjustment"))
    task_signature_count = sum(1 for item in strategies if _has_text(item, "task_signature"))
    research_only_count = sum(1 for item in strategies if _research_only(item))
    deferred_submission_count = sum(
        1
        for item in strategies
        if _normalized_text(item.get("submission_lane")) == "deferred_submission"
    )
    validation_grade_distribution: dict[str, int] = {}
    raw_validation_grade_distribution: dict[str, int] = {}
    effective_validation_grade_distribution: dict[str, int] = {}
    raw_validation_total_scores: list[float] = []
    strict_incubation_ready_count = 0
    live_candidate_ready_count = 0
    raw_b_or_above_count = 0
    strict_ready_given_raw_b_count = 0
    live_ready_given_raw_b_count = 0
    for item in strategies:
        effective_grade = _effective_validation_grade(item)
        raw_grade = _raw_validation_grade(item)
        strict_ready = _bool_payload(item, "strict_incubation_ready")
        live_ready = _bool_payload(item, "live_candidate_ready")
        if effective_grade:
            validation_grade_distribution[effective_grade] = (
                validation_grade_distribution.get(effective_grade, 0) + 1
            )
            effective_validation_grade_distribution[effective_grade] = (
                effective_validation_grade_distribution.get(effective_grade, 0) + 1
            )
        if raw_grade:
            raw_validation_grade_distribution[raw_grade] = (
                raw_validation_grade_distribution.get(raw_grade, 0) + 1
            )
        raw_score = _validation_total_score(item, raw=True)
        if raw_score is not None:
            raw_validation_total_scores.append(float(raw_score))
        if strict_ready:
            strict_incubation_ready_count += 1
        if live_ready:
            live_candidate_ready_count += 1
        if _is_raw_b_or_above(raw_grade):
            raw_b_or_above_count += 1
            if strict_ready:
                strict_ready_given_raw_b_count += 1
            if live_ready:
                live_ready_given_raw_b_count += 1
    candidate_local_attempt_count = sum(_candidate_local_attempt_count(item) for item in strategies)
    task_local_attempt_count = sum(_task_local_attempt_count(item) for item in strategies)
    cohort_effective_trials = round(
        sum(_cohort_effective_trials(item) for item in strategies),
        4,
    )
    unique_family_holding_universe_count = len(
        {
            (
                _candidate_family(item) or "unknown",
                _holding_bucket(item) or "unknown",
                _target_universe_key(item) or "unknown",
            )
            for item in strategies
        }
    )
    economic_semantics_missing_count = sum(
        1 for item in strategies if _economic_semantics_missing(item)
    )
    family_quality_panel = _aggregate_family_quality_panel(strategies)
    raw_validation_total_score_mean = round(
        sum(raw_validation_total_scores) / len(raw_validation_total_scores),
        4,
    ) if raw_validation_total_scores else 0.0
    return {
        "contract_version": SUBMISSION_ARTIFACT_CONTRACT_VERSION,
        "available": bool(payload),
        "strategy_count": len(strategies),
        "created_count": _safe_int(payload.get("created")),
        "created_total_count": _safe_int(payload.get("created_total")),
        "created_strategy_pool_count": _safe_int(payload.get("created_strategy_pool")),
        "created_audit_only_count": _safe_int(payload.get("created_audit_only")),
        "refreshed_count": _safe_int(payload.get("refreshed")),
        "gate_3_input": _safe_int(payload.get("gate_3_input")),
        "submitted_count": _safe_int(payload.get("submitted")),
        "passed_quality_gate_count": _safe_int(payload.get("passed_quality_gate")),
        "gate_3_passed": _safe_int(payload.get("gate_3_passed")),
        "gate_3_failed": _safe_int(payload.get("gate_3_failed")),
        "gate_3_provisional_passed": _safe_int(payload.get("gate_3_provisional_passed")),
        "incubation_budget_summary": dict(payload.get("incubation_budget_summary") or {}),
        "gate_3_failure_reason_topn": _compact_reason_topn(payload.get("gate_3_failure_reason_topn")),
        "submission_lane_counts": submission_lane_counts,
        "submission_action_type_counts": submission_action_type_counts,
        "strategy_status_counts": strategy_status_counts,
        "committee_decision_counts": committee_decision_counts,
        "refresh_mode_counts": refresh_mode_counts,
        "committee_review_count": committee_review_count,
        "primary_validation_layer_counts": primary_validation_layer_counts,
        "validation_profile_counts": validation_profile_counts,
        "constraint_violation_counts": constraint_violation_counts,
        "constraint_check_count": constraint_check_count,
        "validation_profile_count": validation_profile_count,
        "event_window_config_count": event_window_config_count,
        "position_assumption_count": position_assumption_count,
        "cost_assumptions_count": cost_assumptions_count,
        "explicit_cost_breakdown_count": explicit_cost_breakdown_count,
        "implicit_cost_breakdown_count": implicit_cost_breakdown_count,
        "attempt_adjustment_count": attempt_adjustment_count,
        "task_signature_count": task_signature_count,
        "research_only_count": research_only_count,
        "deferred_submission_count": deferred_submission_count,
        "validation_grade_distribution": validation_grade_distribution,
        "raw_validation_grade_distribution": raw_validation_grade_distribution,
        "effective_validation_grade_distribution": effective_validation_grade_distribution,
        "raw_validation_total_score_mean": raw_validation_total_score_mean,
        "raw_validation_total_score_p50": _percentile(raw_validation_total_scores, 0.5),
        "raw_validation_total_score_p90": _percentile(raw_validation_total_scores, 0.9),
        **_grade_rates(raw_validation_grade_distribution, len(strategies)),
        "strict_incubation_ready_count": strict_incubation_ready_count,
        "strict_incubation_ready_rate": _rate(strict_incubation_ready_count, len(strategies)),
        "live_candidate_ready_count": live_candidate_ready_count,
        "live_candidate_ready_rate": _rate(live_candidate_ready_count, len(strategies)),
        "raw_b_or_above_count": raw_b_or_above_count,
        "raw_b_or_above_rate": _rate(raw_b_or_above_count, len(strategies)),
        "strict_ready_given_raw_b_count": strict_ready_given_raw_b_count,
        "strict_ready_given_raw_b_rate": _rate(
            strict_ready_given_raw_b_count,
            raw_b_or_above_count,
        ),
        "live_ready_given_raw_b_count": live_ready_given_raw_b_count,
        "live_ready_given_raw_b_rate": _rate(
            live_ready_given_raw_b_count,
            raw_b_or_above_count,
        ),
        "validation_family_quality_panel": family_quality_panel,
        "candidate_local_attempt_count": candidate_local_attempt_count,
        "task_local_attempt_count": task_local_attempt_count,
        "cohort_effective_trials": cohort_effective_trials,
        "unique_family_holding_universe_count": unique_family_holding_universe_count,
        "economic_semantics_missing_count": economic_semantics_missing_count,
        "strategy_briefs": [_strategy_brief(item) for item in strategies[:12]],
    }


def build_governance_evidence_artifact(
    *,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(submit_result or {})
    strategies = [dict(item or {}) for item in list(payload.get("strategies") or []) if isinstance(item, dict)]

    def _has_numeric(item: dict[str, Any], key: str) -> bool:
        source = dict(item.get("backtest_assumptions") or {})
        cost = dict(item.get("cost_assumptions") or {})
        if source.get(key) is not None or cost.get(key) is not None:
            return True
        return False

    vector_backend_counts = _count_by(
        strategies,
        lambda item: item.get("vector_backend_used") or item.get("vector_backend"),
    )
    quality_report_count = len(strategies)
    multiple_testing_registry_count = sum(1 for item in strategies if _has_mapping(item, "multiple_testing_registry"))
    multiple_testing_registry_record_count = sum(
        1 for item in strategies if _string(item.get("multiple_testing_registry_record_id"))
    )
    lineage_contract_count = sum(1 for item in strategies if _has_mapping(item, "candidate_lineage_contract"))
    lineage_id_count = sum(
        1
        for item in strategies
        if _string(dict(item.get("candidate_lineage_contract") or {}).get("lineage_id"))
    )
    committee_review_count = sum(1 for item in strategies if _has_mapping(item, "committee_review"))
    constraint_check_count = sum(1 for item in strategies if _has_mapping(item, "constraint_check"))
    validation_profile_count = sum(1 for item in strategies if _has_mapping(item, "validation_profile"))
    event_window_config_count = sum(1 for item in strategies if _has_mapping(item, "event_window_config"))
    position_assumption_count = sum(1 for item in strategies if _has_text(item, "position_assumption"))
    vector_profile_count = sum(1 for item in strategies if _string(item.get("vector_profile_id")))
    cost_assumptions_count = sum(1 for item in strategies if _has_mapping(item, "cost_assumptions"))
    explicit_cost_breakdown_count = sum(1 for item in strategies if _has_mapping(item, "explicit_cost_breakdown"))
    implicit_cost_breakdown_count = sum(1 for item in strategies if _has_mapping(item, "implicit_cost_breakdown"))
    execution_reality_count = sum(1 for item in strategies if _has_mapping(item, "execution_reality"))
    attempt_adjustment_count = sum(1 for item in strategies if _has_mapping(item, "attempt_adjustment"))
    task_signature_count = sum(1 for item in strategies if _has_text(item, "task_signature"))
    refresh_mode_count = sum(1 for item in strategies if _has_text(item, "refresh_mode"))
    primary_validation_layer_count = sum(1 for item in strategies if bool(_primary_validation_layer(item)))
    slippage_assumption_count = sum(1 for item in strategies if _has_numeric(item, "slippage_bps"))
    market_impact_assumption_count = sum(1 for item in strategies if _has_numeric(item, "market_impact_bps"))
    capacity_assumption_count = sum(
        1
        for item in strategies
        if dict(item.get("backtest_assumptions") or {}).get("capacity_participation_rate") is not None
        or _string(dict(item.get("backtest_assumptions") or {}).get("capacity_bucket"))
    )
    tradability_filter_count = sum(
        1
        for item in strategies
        if dict(item.get("backtest_assumptions") or {}).get("tradability_filter") is not None
    )
    evidence_briefs = [
        {
            **_strategy_brief(item),
            "lineage_id": _string(dict(item.get("candidate_lineage_contract") or {}).get("lineage_id")) or None,
            "vector_backend": (
                _string(item.get("vector_backend_used"))
                or _string(item.get("vector_backend"))
                or None
            ),
            "has_cost_assumptions": _has_mapping(item, "cost_assumptions"),
            "has_execution_reality": _has_mapping(item, "execution_reality"),
            "has_multiple_testing_registry": _has_mapping(item, "multiple_testing_registry"),
        }
        for item in strategies[:12]
    ]
    return {
        "contract_version": GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
        "available": bool(strategies),
        "quality_report_count": quality_report_count,
        "multiple_testing_registry_count": multiple_testing_registry_count,
        "multiple_testing_registry_record_count": multiple_testing_registry_record_count,
        "lineage_contract_count": lineage_contract_count,
        "lineage_id_count": lineage_id_count,
        "committee_review_count": committee_review_count,
        "constraint_check_count": constraint_check_count,
        "validation_profile_count": validation_profile_count,
        "event_window_config_count": event_window_config_count,
        "position_assumption_count": position_assumption_count,
        "vector_profile_count": vector_profile_count,
        "vector_backend_counts": vector_backend_counts,
        "cost_assumptions_count": cost_assumptions_count,
        "explicit_cost_breakdown_count": explicit_cost_breakdown_count,
        "implicit_cost_breakdown_count": implicit_cost_breakdown_count,
        "execution_reality_count": execution_reality_count,
        "attempt_adjustment_count": attempt_adjustment_count,
        "task_signature_count": task_signature_count,
        "refresh_mode_count": refresh_mode_count,
        "primary_validation_layer_count": primary_validation_layer_count,
        "slippage_assumption_count": slippage_assumption_count,
        "market_impact_assumption_count": market_impact_assumption_count,
        "capacity_assumption_count": capacity_assumption_count,
        "tradability_filter_count": tradability_filter_count,
        "extension_interface_support": {
            "constraint_check_supported": bool(constraint_check_count),
            "validation_profile_supported": bool(validation_profile_count),
            "event_window_supported": bool(event_window_config_count),
            "position_assumption_supported": bool(position_assumption_count),
            "committee_review_supported": bool(committee_review_count),
            "cost_assumptions_supported": bool(cost_assumptions_count),
            "execution_reality_supported": bool(execution_reality_count),
            "attempt_adjustment_supported": bool(attempt_adjustment_count),
            "task_signature_supported": bool(task_signature_count),
            "refresh_mode_supported": bool(refresh_mode_count),
            "primary_validation_layer_supported": bool(primary_validation_layer_count),
            "slippage_supported": bool(slippage_assumption_count),
            "market_impact_supported": bool(market_impact_assumption_count),
            "capacity_supported": bool(capacity_assumption_count),
            "tradability_filter_supported": bool(tradability_filter_count),
        },
        "strategy_evidence_briefs": evidence_briefs,
    }


def _legacy_gate_mapping(
    *,
    quality_gate_report: dict[str, Any] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = dict(quality_gate_report or {})
    submit = dict(submit_result or {})
    return {
        "gate_a": ["gate_0", "pre_gate", "gate_1", "semantic_contract", "strategy_reviewer"],
        "gate_b": ["gate_2", "gate_3", "submission_gate", "dedup", "submit"],
        "gate_c": [
            "signal_quality",
            "execution_quality",
            "execution_audit_gate_status",
            "hard_gate_result",
            "promotion_ready",
        ],
        "legacy_counts": {
            "gate_0_passed": _safe_int(dict(quality.get("gate_0") or {}).get("passed_count")),
            "pre_gate_passed": _safe_int(dict(quality.get("pre_gate") or {}).get("passed_count")),
            "gate_1_passed": _safe_int(dict(quality.get("gate_1") or {}).get("passed_count")),
            "gate_2_passed": _safe_int(dict(quality.get("gate_2") or {}).get("passed_count")),
            "gate_3_passed": _safe_int(dict(quality.get("gate_3") or {}).get("passed_count")),
            "submitted": _safe_int(submit.get("submitted")),
        },
    }


def build_gate_a_artifact(
    *,
    candidates: list[dict[str, Any]] | None = None,
    quality_gate_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = dict(quality_gate_report or {})
    gate_0 = dict(quality.get("gate_0") or {})
    pre_gate = dict(quality.get("pre_gate") or {})
    gate_1 = dict(quality.get("gate_1") or {})
    items = [dict(item or {}) for item in list(candidates or []) if isinstance(item, dict)]
    completeness_counts = _count_by(
        items,
        lambda item: _candidate_spec_completeness(item) or "unknown",
    )
    blocking_reason_counts: dict[str, int] = {}
    evidence_gap_codes: list[str] = []
    revision_actions: list[str] = []
    evidence_refs: list[str] = []
    hard_failures: list[dict[str, Any]] = []
    artifact_ids: list[str] = []
    retrieval_context_ids: list[str] = []
    for item in items:
        for issue in list(_candidate_payload_value(item, "completion_issues") or []):
            payload = dict(issue or {})
            reason_code = _string(payload.get("reason_code") or payload.get("issue") or payload.get("field"))
            if reason_code:
                blocking_reason_counts[reason_code] = blocking_reason_counts.get(reason_code, 0) + 1
                decision = _normalized_text(payload.get("decision") or payload.get("severity"))
                if decision == "reject":
                    failure = _normalize_hard_failure_entry(
                        reason_code,
                        issue=_string(payload.get("issue")) or "hard_failure",
                        field=payload.get("field"),
                    )
                    if failure:
                        hard_failures.append(failure)
                else:
                    evidence_gap_codes.append(reason_code)
            field_name = _string(payload.get("field"))
            if field_name:
                action = f"provide_required_research_field:{field_name}"
                if action not in revision_actions:
                    revision_actions.append(action)
        for failure in list(_candidate_payload_value(item, "hard_failures") or []):
            payload = dict(failure or {})
            normalized = _normalize_hard_failure_entry(
                payload.get("reason_code") or payload.get("issue"),
                issue=_string(payload.get("issue")) or "hard_failure",
                field=payload.get("field"),
                detail=payload.get("detail"),
            )
            if normalized:
                hard_failures.append(normalized)
        if bool(_candidate_payload_value(item, "execution_semantic_gap")):
            blocking_reason_counts["execution_semantic_gap"] = blocking_reason_counts.get("execution_semantic_gap", 0) + 1
            failure = _normalize_hard_failure_entry(
                "execution_semantic_gap",
                issue="execution_semantic_gap",
            )
            if failure:
                hard_failures.append(failure)
            if "repair_execution_semantic_gap" not in revision_actions:
                revision_actions.append("repair_execution_semantic_gap")
        for field_name in list(_candidate_payload_value(item, "semantic_contract_missing_fields") or []):
            key = _string(field_name)
            if key:
                reason_code = f"semantic_contract_missing:{key}"
                blocking_reason_counts[reason_code] = blocking_reason_counts.get(reason_code, 0) + 1
                failure = _normalize_hard_failure_entry(
                    reason_code,
                    issue="semantic_contract_missing_field",
                    field=key,
                )
                if failure:
                    hard_failures.append(failure)
                action = f"repair_semantic_contract_field:{key}"
                if action not in revision_actions:
                    revision_actions.append(action)
        trace_id = _candidate_prediction_trace_id(item)
        if trace_id and trace_id not in evidence_refs:
            evidence_refs.append(trace_id)
        for artifact_id in _candidate_artifact_ids(item):
            if artifact_id not in artifact_ids:
                artifact_ids.append(artifact_id)
        for context_id in _candidate_retrieval_context_ids(item):
            if context_id not in retrieval_context_ids:
                retrieval_context_ids.append(context_id)
    has_activity = bool(items or quality)
    blocked = bool(
        _safe_int(gate_0.get("failed_count"))
        or _safe_int(pre_gate.get("failed_count"))
        or _safe_int(gate_1.get("failed_count"))
        or blocking_reason_counts
    )
    hard_failures = _unique_hard_failures(hard_failures)
    decision = "reject" if hard_failures else "revise" if blocked else "pass"
    return {
        "contract_version": GATE_ARTIFACT_V2_CONTRACT_VERSION,
        "gate_name": "gate_a",
        "stage": "gate_a",
        "decision": decision,
        "status": "pending" if not has_activity else "blocked" if blocked else "passed",
        "hard_failures": hard_failures,
        "evidence_gap_codes": _compact_list(evidence_gap_codes, limit=16),
        "artifact_ids": artifact_ids[:16],
        "retrieval_context_ids": retrieval_context_ids[:16],
        "trace_ids": evidence_refs[:12],
        "family_outcome_summary": _family_outcome_summary(items),
        "blocking_reasons": _top_counts(blocking_reason_counts, label_key="reason_code"),
        "warnings": ["spec_completeness_incomplete"] if completeness_counts.get("incomplete") else [],
        "revision_actions": revision_actions[:12],
        "evidence_refs": evidence_refs[:12],
        "legacy_gate_mapping": ["gate_0", "pre_gate", "gate_1"],
        "input_count": len(items),
        "gate_0_passed": _safe_int(gate_0.get("passed_count")),
        "pre_gate_passed": _safe_int(pre_gate.get("passed_count")),
        "gate_1_passed": _safe_int(gate_1.get("passed_count")),
        "spec_completeness_counts": completeness_counts,
    }


def build_gate_b_artifact(
    *,
    quality_gate_report: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = dict(quality_gate_report or {})
    backtest = dict(backtest_report or {})
    submit = dict(submit_result or {})
    gate_2 = dict(quality.get("gate_2") or {})
    gate_3 = dict(quality.get("gate_3") or {})
    backtest_summary = dict(backtest.get("summary") or {})
    strategies = [dict(item or {}) for item in list(submit.get("strategies") or []) if isinstance(item, dict)]
    failure_reason_counts = {
        _string(item.get("reason") or item.get("reason_code")): _safe_int(item.get("count"))
        for item in list(gate_3.get("failure_reason_topn") or submit.get("gate_3_failure_reason_topn") or [])
        if _string(item.get("reason") or item.get("reason_code"))
    }
    blocked = bool(_safe_int(gate_3.get("failed_count") or submit.get("gate_3_failed")))
    has_activity = bool(quality or backtest or submit)
    hard_failures = _unique_hard_failures(
        [
            _normalize_hard_failure_entry(code, issue="submission_gate_blocker")
            for code in failure_reason_counts
        ]
    )
    warnings = _compact_list(gate_3.get("warning_codes") or submit.get("warning_codes") or [])
    trace_ids: list[str] = []
    artifact_ids: list[str] = []
    retrieval_context_ids: list[str] = []
    review_decision_counts: dict[str, int] = {}
    sample_business_admission_decision: dict[str, Any] = {}
    sample_benchmark_comparison: dict[str, Any] = {}
    sample_cost_sensitivity_summary: dict[str, Any] = {}
    sample_cash_sleeve_audit: dict[str, Any] = {}
    for item in strategies:
        review_decision = _normalized_text(
            dict(item.get("gate_b") or {}).get("review_decision")
            or dict(item.get("business_admission_decision") or {}).get("decision")
            or item.get("gate_b_review_decision")
        )
        if review_decision:
            review_decision_counts[review_decision] = review_decision_counts.get(review_decision, 0) + 1
        if not sample_business_admission_decision:
            sample_business_admission_decision = dict(
                dict(item.get("gate_b") or {}).get("business_admission_decision")
                or item.get("business_admission_decision")
                or {}
            )
        if not sample_benchmark_comparison:
            sample_benchmark_comparison = dict(
                dict(item.get("gate_b") or {}).get("benchmark_comparison")
                or item.get("benchmark_comparison")
                or {}
            )
        if not sample_cost_sensitivity_summary:
            sample_cost_sensitivity_summary = dict(
                dict(item.get("gate_b") or {}).get("cost_sensitivity_summary")
                or item.get("cost_sensitivity_summary")
                or {}
            )
        if not sample_cash_sleeve_audit:
            sample_cash_sleeve_audit = dict(
                dict(item.get("gate_b") or {}).get("cash_sleeve_audit")
                or item.get("cash_sleeve_audit")
                or {}
            )
        for trace_id in _candidate_trace_ids(item):
            if trace_id not in trace_ids:
                trace_ids.append(trace_id)
        for artifact_id in _candidate_artifact_ids(item):
            if artifact_id not in artifact_ids:
                artifact_ids.append(artifact_id)
        for context_id in _candidate_retrieval_context_ids(item):
            if context_id not in retrieval_context_ids:
                retrieval_context_ids.append(context_id)
    decision = "block" if blocked else "pass" if has_activity else "pending"
    review_decision = "pending"
    if review_decision_counts.get("reject"):
        review_decision = "reject"
    elif review_decision_counts.get("revise"):
        review_decision = "revise"
    elif has_activity:
        review_decision = "pass"
    return {
        "contract_version": GATE_ARTIFACT_V2_CONTRACT_VERSION,
        "gate_name": "gate_b",
        "stage": "gate_b",
        "decision": decision,
        "review_decision": review_decision,
        "status": (
            "pending"
            if not has_activity
            else "blocked"
            if blocked
            else "passed"
            if _safe_int(submit.get("submitted") or gate_3.get("passed_count") or gate_2.get("passed_count"))
            else "pending"
        ),
        "hard_failures": hard_failures,
        "evidence_gap_codes": warnings,
        "artifact_ids": artifact_ids[:16],
        "retrieval_context_ids": retrieval_context_ids[:16],
        "trace_ids": trace_ids[:12],
        "family_outcome_summary": _family_outcome_summary(strategies),
        "blocking_reasons": _top_counts(failure_reason_counts, label_key="reason_code"),
        "warnings": warnings,
        "evidence_refs": [],
        "legacy_gate_mapping": ["gate_2", "gate_3"],
        "business_admission_decision_distribution": review_decision_counts,
        "business_admission_decision": sample_business_admission_decision,
        "benchmark_comparison": sample_benchmark_comparison,
        "cost_sensitivity_summary": sample_cost_sensitivity_summary,
        "cash_sleeve_audit": sample_cash_sleeve_audit,
        "gate_2_input": _safe_int(gate_2.get("input_count"), _safe_int(backtest_summary.get("input_count"))),
        "gate_2_passed": _safe_int(gate_2.get("passed_count"), _safe_int(backtest_summary.get("passed_count"))),
        "gate_2_failed": _safe_int(gate_2.get("failed_count"), _safe_int(backtest_summary.get("failed_count"))),
        "gate_3_input": _safe_int(gate_3.get("input_count"), _safe_int(submit.get("gate_3_input"))),
        "gate_3_passed": _safe_int(gate_3.get("passed_count"), _safe_int(submit.get("gate_3_passed"))),
        "gate_3_failed": _safe_int(gate_3.get("failed_count"), _safe_int(submit.get("gate_3_failed"))),
        "gate_3_provisional_passed": _safe_int(
            gate_3.get("provisional_passed_count"),
            _safe_int(submit.get("gate_3_provisional_passed")),
        ),
    }
