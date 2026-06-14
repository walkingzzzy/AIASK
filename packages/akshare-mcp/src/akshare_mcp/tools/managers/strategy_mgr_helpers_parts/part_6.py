

def build_factory_recent_run_diagnostics(
    run_rows: list[dict[str, Any]] | None,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    rows = [dict(item or {}) for item in list(run_rows or []) if isinstance(item, dict)]
    requested_limit = max(1, int(limit or 5))
    items = rows[:requested_limit]
    status_counts: dict[str, int] = {}
    readiness_decision_counts: dict[str, int] = {}
    blocker_reason_counts: dict[str, int] = {}
    warning_reason_counts: dict[str, int] = {}
    governed_warning_reason_counts: dict[str, int] = {}
    evidence_warning_reason_counts: dict[str, int] = {}
    governed_blocking_reason_counts: dict[str, int] = {}
    governed_exclusion_reason_counts: dict[str, int] = {}
    governed_pending_reason_counts: dict[str, int] = {}
    governed_ineligible_reason_counts: dict[str, int] = {}
    external_llm_provider_control_mode_counts: dict[str, int] = {}
    external_llm_provider_control_reason_counts: dict[str, int] = {}
    suppressed_generator_mode_counts: dict[str, int] = {}
    blocked_count = 0
    submit_stage_entered_count = 0
    submitted_positive_count = 0
    external_llm_provider_suppressed_run_count = 0
    external_llm_provider_cooldown_run_count = 0
    raw_b_or_above_rates: list[float] = []
    strict_ready_given_raw_b_rates: list[float] = []
    live_ready_given_raw_b_rates: list[float] = []
    strict_live_alignment_gap_rates: list[float] = []
    strict_live_gap_run_count = 0
    governed_blocked_ratios: list[float] = []
    governed_strict_shortfall_counts: list[float] = []
    governed_blocked_candidate_counts: list[float] = []
    governed_source_candidate_counts: list[float] = []
    evidence_debt_ratios: list[float] = []
    zero_signal_ratios: list[float] = []
    forward_window_coverage_ratios: list[float] = []
    promotion_ready_ratios: list[float] = []
    promotion_review_coverage_ratios: list[float] = []
    provider_stage_attempt_counts: list[float] = []
    provider_real_request_counts: list[float] = []
    provider_compatibility_skip_ratios: list[float] = []
    provider_compatibility_failure_ratios: list[float] = []
    provider_effective_response_ratios: list[float] = []
    provider_empty_200_response_ratios: list[float] = []
    provider_active_attempt_run_count = 0
    provider_zero_attempt_run_count = 0
    run_briefs: list[dict[str, Any]] = []

    for row in items:
        summary = dict(row.get("summary") or {})
        stages = dict(row.get("stages") or {})
        readiness = _extract_factory_run_readiness_snapshot(row)
        def _summary_metric(field: str) -> Any:
            if field not in summary:
                return None
            value = summary.get(field)
            return None if value in (None, "", [], {}) else value

        status_key = str(row.get("status") or "").strip().lower() or "unknown"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        decision = str(readiness.get("decision") or "unknown").strip().lower() or "unknown"
        readiness_decision_counts[decision] = readiness_decision_counts.get(decision, 0) + 1
        if decision == "blocked":
            blocked_count += 1
        for reason_code in list(readiness.get("blocking_reason_codes") or []):
            blocker_reason_counts[reason_code] = blocker_reason_counts.get(reason_code, 0) + 1
        for reason_code in list(readiness.get("warning_reason_codes") or []):
            warning_reason_counts[reason_code] = warning_reason_counts.get(reason_code, 0) + 1
            if _is_governed_reason_code(reason_code):
                governed_warning_reason_counts[reason_code] = governed_warning_reason_counts.get(reason_code, 0) + 1
            if _is_evidence_debt_reason_code(reason_code):
                evidence_warning_reason_counts[reason_code] = evidence_warning_reason_counts.get(reason_code, 0) + 1
        for reason_code, count in dict(readiness.get("governed_blocking_reason_counts") or {}).items():
            governed_blocking_reason_counts[reason_code] = (
                governed_blocking_reason_counts.get(reason_code, 0) + int(count or 0)
            )
        for reason_code, count in dict(readiness.get("governed_exclusion_reason_counts") or {}).items():
            governed_exclusion_reason_counts[reason_code] = (
                governed_exclusion_reason_counts.get(reason_code, 0) + int(count or 0)
            )
        for reason_code, count in dict(readiness.get("governed_pending_reason_counts") or {}).items():
            governed_pending_reason_counts[reason_code] = (
                governed_pending_reason_counts.get(reason_code, 0) + int(count or 0)
            )
        for reason_code, count in dict(readiness.get("governed_ineligible_reason_counts") or {}).items():
            governed_ineligible_reason_counts[reason_code] = (
                governed_ineligible_reason_counts.get(reason_code, 0) + int(count or 0)
            )
        external_llm_provider_control_mode = _normalized_text(
            _summary_metric("external_llm_provider_control_mode")
            or row.get("external_llm_provider_control_mode")
        )
        external_llm_provider_control_reasons = _normalize_reason_codes(
            _summary_metric("external_llm_provider_control_reasons")
            or row.get("external_llm_provider_control_reasons")
        )
        feedback_generator_mode_control_mode_counts = {
            _normalized_text(key): int(value or 0)
            for key, value in dict(
                _summary_metric("feedback_generator_mode_control_mode_counts")
                or row.get("feedback_generator_mode_control_mode_counts")
                or {}
            ).items()
            if _normalized_text(key)
        }
        suppressed_generator_modes = [
            _normalized_text(item)
            for item in _normalize_reason_codes(
                _summary_metric("suppressed_generator_modes")
                or row.get("suppressed_generator_modes")
            )
            if _normalized_text(item)
        ]
        if external_llm_provider_control_mode:
            external_llm_provider_control_mode_counts[external_llm_provider_control_mode] = (
                external_llm_provider_control_mode_counts.get(external_llm_provider_control_mode, 0) + 1
            )
        for reason_code in external_llm_provider_control_reasons:
            external_llm_provider_control_reason_counts[reason_code] = (
                external_llm_provider_control_reason_counts.get(reason_code, 0) + 1
            )
        for generator_mode in suppressed_generator_modes:
            suppressed_generator_mode_counts[generator_mode] = (
                suppressed_generator_mode_counts.get(generator_mode, 0) + 1
            )
        external_llm_provider_suppressed = bool(
            external_llm_provider_control_mode == "suppress"
            or "external_llm" in suppressed_generator_modes
            or int(feedback_generator_mode_control_mode_counts.get("suppress") or 0) > 0
        )
        external_llm_provider_cooldown = external_llm_provider_control_mode == "cooldown"
        if external_llm_provider_suppressed:
            external_llm_provider_suppressed_run_count += 1
        if external_llm_provider_cooldown:
            external_llm_provider_cooldown_run_count += 1

        governed_blocked_ratio = (
            _safe_float(readiness.get("governed_blocked_ratio"))
            if readiness.get("governed_blocked_ratio") not in (None, "", [], {})
            else None
        )
        governed_strict_shortfall_count = (
            int(readiness.get("governed_candidate_pool_strict_shortfall_count") or 0)
            if readiness.get("governed_candidate_pool_strict_shortfall_count") not in (None, "", [], {})
            else None
        )
        governed_blocked_candidate_count = (
            int(readiness.get("governed_blocked_candidate_count") or 0)
            if readiness.get("governed_blocked_candidate_count") not in (None, "", [], {})
            else None
        )
        governed_source_candidate_count = (
            int(readiness.get("governed_source_candidate_count") or 0)
            if readiness.get("governed_source_candidate_count") not in (None, "", [], {})
            else None
        )
        evidence_debt_ratio = (
            _safe_float(readiness.get("budget_feedback_evidence_debt_ratio"))
            if readiness.get("budget_feedback_evidence_debt_ratio") not in (None, "", [], {})
            else None
        )
        zero_signal_ratio = (
            _safe_float(readiness.get("budget_feedback_zero_signal_ratio"))
            if readiness.get("budget_feedback_zero_signal_ratio") not in (None, "", [], {})
            else None
        )
        forward_window_coverage_ratio = (
            _safe_float(readiness.get("budget_feedback_forward_window_coverage_ratio"))
            if readiness.get("budget_feedback_forward_window_coverage_ratio") not in (None, "", [], {})
            else None
        )
        promotion_ready_ratio = (
            _safe_float(readiness.get("budget_feedback_promotion_ready_ratio"))
            if readiness.get("budget_feedback_promotion_ready_ratio") not in (None, "", [], {})
            else None
        )
        promotion_review_coverage_ratio = (
            _safe_float(readiness.get("budget_feedback_promotion_review_coverage_ratio"))
            if readiness.get("budget_feedback_promotion_review_coverage_ratio") not in (None, "", [], {})
            else None
        )
        external_llm_stage_attempt_count = int(_summary_metric("external_llm_stage_attempt_count") or 0)
        external_llm_real_request_count = int(_summary_metric("external_llm_real_request_count") or 0)
        external_llm_compatibility_skip_count = int(
            _summary_metric("external_llm_compatibility_skip_count") or 0
        )
        external_llm_compatibility_failure_count = int(
            _summary_metric("external_llm_compatibility_failure_count") or 0
        )
        external_llm_effective_response_count = int(
            _summary_metric("external_llm_effective_response_count") or 0
        )
        external_llm_empty_200_response_count = int(
            _summary_metric("external_llm_empty_200_response_count") or 0
        )
        external_llm_compatibility_skip_ratio = (
            round(external_llm_compatibility_skip_count / external_llm_stage_attempt_count, 4)
            if external_llm_stage_attempt_count
            else 0.0
        )
        external_llm_compatibility_failure_ratio = (
            round(external_llm_compatibility_failure_count / external_llm_real_request_count, 4)
            if external_llm_real_request_count
            else 0.0
        )
        external_llm_effective_response_ratio = (
            round(external_llm_effective_response_count / external_llm_real_request_count, 4)
            if external_llm_real_request_count
            else 0.0
        )
        external_llm_empty_200_response_ratio = (
            round(external_llm_empty_200_response_count / external_llm_real_request_count, 4)
            if external_llm_real_request_count
            else 0.0
        )
        if external_llm_stage_attempt_count > 0 or external_llm_real_request_count > 0:
            provider_active_attempt_run_count += 1
        else:
            provider_zero_attempt_run_count += 1
        _append_numeric(governed_blocked_ratios, governed_blocked_ratio)
        _append_numeric(governed_strict_shortfall_counts, governed_strict_shortfall_count)
        _append_numeric(governed_blocked_candidate_counts, governed_blocked_candidate_count)
        _append_numeric(governed_source_candidate_counts, governed_source_candidate_count)
        _append_numeric(evidence_debt_ratios, evidence_debt_ratio)
        _append_numeric(zero_signal_ratios, zero_signal_ratio)
        _append_numeric(forward_window_coverage_ratios, forward_window_coverage_ratio)
        _append_numeric(promotion_ready_ratios, promotion_ready_ratio)
        _append_numeric(promotion_review_coverage_ratios, promotion_review_coverage_ratio)
        _append_numeric(provider_stage_attempt_counts, external_llm_stage_attempt_count)
        _append_numeric(provider_real_request_counts, external_llm_real_request_count)
        _append_numeric(provider_compatibility_skip_ratios, external_llm_compatibility_skip_ratio)
        _append_numeric(provider_compatibility_failure_ratios, external_llm_compatibility_failure_ratio)
        _append_numeric(provider_effective_response_ratios, external_llm_effective_response_ratio)
        _append_numeric(provider_empty_200_response_ratios, external_llm_empty_200_response_ratio)

        submit_stage = dict(stages.get("submit") or {})
        submit_stage_entered = bool(submit_stage) or any(
            int(_summary_metric(key) or 0) > 0
            for key in ("submitted", "research_only_count", "deferred_submission_count")
        )
        if submit_stage_entered:
            submit_stage_entered_count += 1
        submitted = int(_summary_metric("submitted") or 0)
        if submitted > 0:
            submitted_positive_count += 1

        raw_b_or_above_rate_value = _summary_metric("raw_b_or_above_rate")
        strict_ready_given_raw_b_rate_value = _summary_metric("strict_ready_given_raw_b_rate")
        live_ready_given_raw_b_rate_value = _summary_metric("live_ready_given_raw_b_rate")
        gap_rate_value = _summary_metric("strict_live_alignment_gap_rate")
        gap_count_value = _summary_metric("strict_live_alignment_gap_count")
        gap_status_counts = _summary_metric("strict_live_alignment_status_counts")
        if gap_count_value is None and isinstance(gap_status_counts, dict):
            gap_count_value = int(dict(gap_status_counts).get("strict_only_gap") or 0)

        raw_b_or_above_rate = (
            _safe_float(raw_b_or_above_rate_value)
            if raw_b_or_above_rate_value not in (None, "", [], {})
            else None
        )
        strict_ready_given_raw_b_rate = (
            _safe_float(strict_ready_given_raw_b_rate_value)
            if strict_ready_given_raw_b_rate_value not in (None, "", [], {})
            else None
        )
        live_ready_given_raw_b_rate = (
            _safe_float(live_ready_given_raw_b_rate_value)
            if live_ready_given_raw_b_rate_value not in (None, "", [], {})
            else None
        )
        strict_live_alignment_gap_rate = (
            _safe_float(gap_rate_value)
            if gap_rate_value not in (None, "", [], {})
            else None
        )
        strict_live_alignment_gap_count = (
            int(gap_count_value or 0)
            if gap_count_value not in (None, "", [], {})
            else None
        )
        if submit_stage_entered and raw_b_or_above_rate is not None:
            raw_b_or_above_rates.append(raw_b_or_above_rate)
        if submit_stage_entered and strict_ready_given_raw_b_rate is not None:
            strict_ready_given_raw_b_rates.append(strict_ready_given_raw_b_rate)
        if submit_stage_entered and live_ready_given_raw_b_rate is not None:
            live_ready_given_raw_b_rates.append(live_ready_given_raw_b_rate)
        if submit_stage_entered and strict_live_alignment_gap_rate is not None:
            strict_live_alignment_gap_rates.append(strict_live_alignment_gap_rate)
        if submit_stage_entered and strict_live_alignment_gap_count and strict_live_alignment_gap_count > 0:
            strict_live_gap_run_count += 1

        run_briefs.append(
            {
                "run_id": str(row.get("run_id") or "").strip() or None,
                "status": status_key,
                "started_at": row.get("started_at"),
                "completed_at": row.get("completed_at"),
                "readiness_decision": decision,
                "readiness_score": _safe_float(readiness.get("score"), 0.0)
                if readiness.get("score") is not None
                else None,
                "submit_stage_entered": submit_stage_entered,
                "submitted": submitted,
                "research_only_count": int(_summary_metric("research_only_count") or 0),
                "deferred_submission_count": int(_summary_metric("deferred_submission_count") or 0),
                "blocking_reason_codes": list(readiness.get("blocking_reason_codes") or []),
                "warning_reason_codes": list(readiness.get("warning_reason_codes") or []),
                "external_llm_provider_control_mode": external_llm_provider_control_mode or None,
                "external_llm_provider_control_reasons": external_llm_provider_control_reasons,
                "suppressed_generator_modes": suppressed_generator_modes,
                "external_llm_provider_suppressed": external_llm_provider_suppressed,
                "external_llm_provider_cooldown": external_llm_provider_cooldown,
                "governed_blocked_ratio": governed_blocked_ratio,
                "governed_candidate_pool_strict_shortfall_count": governed_strict_shortfall_count,
                "governed_blocked_candidate_count": governed_blocked_candidate_count,
                "governed_source_candidate_count": governed_source_candidate_count,
                "budget_feedback_evidence_debt_ratio": evidence_debt_ratio,
                "budget_feedback_zero_signal_ratio": zero_signal_ratio,
                "budget_feedback_forward_window_coverage_ratio": forward_window_coverage_ratio,
                "budget_feedback_promotion_ready_ratio": promotion_ready_ratio,
                "budget_feedback_promotion_review_coverage_ratio": promotion_review_coverage_ratio,
                "external_llm_stage_attempt_count": external_llm_stage_attempt_count,
                "external_llm_real_request_count": external_llm_real_request_count,
                "external_llm_compatibility_skip_ratio": external_llm_compatibility_skip_ratio,
                "external_llm_compatibility_failure_ratio": external_llm_compatibility_failure_ratio,
                "external_llm_effective_response_ratio": external_llm_effective_response_ratio,
                "external_llm_empty_200_response_ratio": external_llm_empty_200_response_ratio,
                "raw_b_or_above_rate": raw_b_or_above_rate,
                "strict_ready_given_raw_b_rate": strict_ready_given_raw_b_rate,
                "live_ready_given_raw_b_rate": live_ready_given_raw_b_rate,
                "strict_live_alignment_gap_count": strict_live_alignment_gap_count,
                "strict_live_alignment_gap_rate": strict_live_alignment_gap_rate,
            }
        )

    latest_run = run_briefs[0] if run_briefs else {}
    return {
        "contract_version": "strategy_factory.recent_run_diagnostics.v1",
        "window_size": requested_limit,
        "analyzed_run_count": len(run_briefs),
        "status_counts": status_counts,
        "readiness_decision_counts": readiness_decision_counts,
        "readiness_blocked_count": blocked_count,
        "readiness_blocked_rate": _rate(blocked_count, len(run_briefs)),
        "submit_stage_entered_count": submit_stage_entered_count,
        "submit_stage_entered_rate": _rate(submit_stage_entered_count, len(run_briefs)),
        "submitted_positive_count": submitted_positive_count,
        "submitted_positive_rate": _rate(submitted_positive_count, len(run_briefs)),
        "blocker_reason_topn": _top_reason_counts(blocker_reason_counts),
        "warning_reason_topn": _top_reason_counts(warning_reason_counts),
        "external_llm_provider_control_mode_counts": external_llm_provider_control_mode_counts,
        "external_llm_provider_suppressed_run_count": external_llm_provider_suppressed_run_count,
        "external_llm_provider_suppressed_run_rate": _rate(
            external_llm_provider_suppressed_run_count,
            len(run_briefs),
        ),
        "external_llm_provider_cooldown_run_count": external_llm_provider_cooldown_run_count,
        "external_llm_provider_cooldown_run_rate": _rate(
            external_llm_provider_cooldown_run_count,
            len(run_briefs),
        ),
        "external_llm_provider_control_reason_topn": _top_reason_counts(
            external_llm_provider_control_reason_counts,
        ),
        "suppressed_generator_mode_topn": _top_named_counts(
            suppressed_generator_mode_counts,
            name_key="mode",
        ),
        "governed_pool_diagnostics": {
            "measurement_run_count": len(governed_blocked_ratios),
            "latest_governed_blocked_ratio": latest_run.get("governed_blocked_ratio") or 0.0,
            "recent_governed_blocked_ratio_mean": _mean(governed_blocked_ratios),
            "latest_governed_candidate_pool_strict_shortfall_count": (
                latest_run.get("governed_candidate_pool_strict_shortfall_count") or 0
            ),
            "recent_governed_candidate_pool_strict_shortfall_mean": _mean(
                governed_strict_shortfall_counts
            ),
            "latest_governed_blocked_candidate_count": (
                latest_run.get("governed_blocked_candidate_count") or 0
            ),
            "recent_governed_blocked_candidate_count_mean": _mean(
                governed_blocked_candidate_counts
            ),
            "latest_governed_source_candidate_count": (
                latest_run.get("governed_source_candidate_count") or 0
            ),
            "recent_governed_source_candidate_count_mean": _mean(
                governed_source_candidate_counts
            ),
            "warning_reason_topn": _top_reason_counts(governed_warning_reason_counts),
            "blocking_reason_topn": _top_reason_counts(governed_blocking_reason_counts),
            "exclusion_reason_topn": _top_reason_counts(governed_exclusion_reason_counts),
            "pending_reason_topn": _top_reason_counts(governed_pending_reason_counts),
            "ineligible_reason_topn": _top_reason_counts(governed_ineligible_reason_counts),
        },
        "evidence_debt_diagnostics": {
            "measurement_run_count": len(evidence_debt_ratios),
            "latest_budget_feedback_evidence_debt_ratio": (
                latest_run.get("budget_feedback_evidence_debt_ratio") or 0.0
            ),
            "recent_budget_feedback_evidence_debt_ratio_mean": _mean(evidence_debt_ratios),
            "latest_budget_feedback_zero_signal_ratio": (
                latest_run.get("budget_feedback_zero_signal_ratio") or 0.0
            ),
            "recent_budget_feedback_zero_signal_ratio_mean": _mean(zero_signal_ratios),
            "latest_budget_feedback_forward_window_coverage_ratio": (
                latest_run.get("budget_feedback_forward_window_coverage_ratio") or 0.0
            ),
            "recent_budget_feedback_forward_window_coverage_ratio_mean": _mean(
                forward_window_coverage_ratios
            ),
            "latest_budget_feedback_promotion_ready_ratio": (
                latest_run.get("budget_feedback_promotion_ready_ratio") or 0.0
            ),
            "recent_budget_feedback_promotion_ready_ratio_mean": _mean(promotion_ready_ratios),
            "latest_budget_feedback_promotion_review_coverage_ratio": (
                latest_run.get("budget_feedback_promotion_review_coverage_ratio") or 0.0
            ),
            "recent_budget_feedback_promotion_review_coverage_ratio_mean": _mean(
                promotion_review_coverage_ratios
            ),
            "warning_reason_topn": _top_reason_counts(evidence_warning_reason_counts),
        },
        "provider_control_diagnostics": {
            "measurement_run_count": len(run_briefs),
            "active_attempt_run_count": provider_active_attempt_run_count,
            "zero_attempt_run_count": provider_zero_attempt_run_count,
            "latest_stage_attempt_count": latest_run.get("external_llm_stage_attempt_count") or 0,
            "recent_stage_attempt_count_mean": _mean(provider_stage_attempt_counts),
            "latest_real_request_count": latest_run.get("external_llm_real_request_count") or 0,
            "recent_real_request_count_mean": _mean(provider_real_request_counts),
            "latest_compatibility_skip_ratio": (
                latest_run.get("external_llm_compatibility_skip_ratio") or 0.0
            ),
            "recent_compatibility_skip_ratio_mean": _mean(provider_compatibility_skip_ratios),
            "latest_compatibility_failure_ratio": (
                latest_run.get("external_llm_compatibility_failure_ratio") or 0.0
            ),
            "recent_compatibility_failure_ratio_mean": _mean(
                provider_compatibility_failure_ratios
            ),
            "latest_effective_response_ratio": (
                latest_run.get("external_llm_effective_response_ratio") or 0.0
            ),
            "recent_effective_response_ratio_mean": _mean(provider_effective_response_ratios),
            "latest_empty_200_response_ratio": (
                latest_run.get("external_llm_empty_200_response_ratio") or 0.0
            ),
            "recent_empty_200_response_ratio_mean": _mean(
                provider_empty_200_response_ratios
            ),
        },
        "quality_progress": {
            "quality_measurement_run_count": len(raw_b_or_above_rates),
            "latest_raw_b_or_above_rate": latest_run.get("raw_b_or_above_rate") or 0.0,
            "recent_raw_b_or_above_rate_mean": _mean(raw_b_or_above_rates),
            "latest_strict_ready_given_raw_b_rate": latest_run.get("strict_ready_given_raw_b_rate") or 0.0,
            "recent_strict_ready_given_raw_b_rate_mean": _mean(strict_ready_given_raw_b_rates),
            "latest_live_ready_given_raw_b_rate": latest_run.get("live_ready_given_raw_b_rate") or 0.0,
            "recent_live_ready_given_raw_b_rate_mean": _mean(live_ready_given_raw_b_rates),
            "strict_live_gap_measurement_run_count": len(strict_live_alignment_gap_rates),
            "latest_strict_live_alignment_gap_rate": latest_run.get("strict_live_alignment_gap_rate") or 0.0,
            "recent_strict_live_alignment_gap_rate_mean": _mean(strict_live_alignment_gap_rates),
            "strict_live_gap_run_count": strict_live_gap_run_count,
            "strict_live_gap_run_rate": _rate(
                strict_live_gap_run_count,
                len(strict_live_alignment_gap_rates),
            ),
        },
        "recent_runs": run_briefs,
    }


_FORMAL_BLOCKER_LABELS = {
    "diagnostic_only_not_allowed_for_incubation": "Diagnostic-only runtime cannot enter formal incubation.",
    "default_profile_not_allowed_for_single_name_runtime": "Default runtime profile is not allowed for single-name formal runtime.",
    "execution_readiness_tier:missing_executable_contract": "Executable contract readiness is missing.",
    "execution_readiness_tier:observe_diagnostic_only": "Runtime is observe/diagnostic only, not formal-ready.",
    "missing_executable_contract": "Executable contract readiness is missing.",
    "proxy_runtime_not_allowed_for_formal_incubation": "Proxy runtime evidence cannot enter formal incubation.",
    "runtime_family_semantic_mismatch": "Runtime family semantics do not match the strategy contract.",
    "semantic_runtime_mismatch": "Runtime semantics do not match the strategy contract.",
    "strict_incubation_pass_required_for_formal_track": "Strict incubation pass is required for formal admission.",
    "trade_prediction_contract_not_ready": "Trade-prediction contract is not ready.",
}

_FORMAL_BLOCKER_ACTIONS = {
    "diagnostic_only_not_allowed_for_incubation": "Route only non-diagnostic runtime evidence to formal incubation; keep diagnostic samples in observe.",
    "default_profile_not_allowed_for_single_name_runtime": "Attach a single-name runtime profile before requesting formal admission.",
    "execution_readiness_tier:missing_executable_contract": "Persist the executable DSL/runtime contract and replay admission.",
    "execution_readiness_tier:observe_diagnostic_only": "Upgrade the runtime contract from observe-diagnostic to formal_runtime_ready.",
    "missing_executable_contract": "Persist the executable DSL/runtime contract and replay admission.",
    "proxy_runtime_not_allowed_for_formal_incubation": "Replace proxy runtime evidence with strategy-family matching runtime evidence.",
    "runtime_family_semantic_mismatch": "Repair the semantic runtime family before replaying formal admission.",
    "semantic_runtime_mismatch": "Repair the semantic runtime contract before replaying formal admission.",
    "strict_incubation_pass_required_for_formal_track": "Improve strict gate evidence before consuming formal incubation slots.",
    "trade_prediction_contract_not_ready": "Complete trade-prediction contract readiness before formal admission.",
}

_FORMAL_BLOCKER_CANONICAL = {
    "diagnostic_only_runtime": "diagnostic_only_not_allowed_for_incubation",
    "execution_readiness_tier:missing": "execution_readiness_tier:missing_executable_contract",
    "missing_executable_contract": "execution_readiness_tier:missing_executable_contract",
    "semantic_runtime_mismatch": "runtime_family_semantic_mismatch",
}


def _canonical_formal_blocker(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        return ""
    normalized = code.lower().replace(" ", "_")
    if normalized.startswith("execution_readiness_tier:"):
        tier = normalized.split(":", 1)[1].strip() or "unknown"
        if tier == "missing":
            tier = "missing_executable_contract"
        return f"execution_readiness_tier:{tier}"
    return _FORMAL_BLOCKER_CANONICAL.get(normalized, normalized)


def _formal_blocker_values_from(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, dict):
        raw_items: list[Any] = []
        for key in ("reason_code", "reason", "code", "name"):
            if value.get(key) not in (None, "", [], {}):
                raw_items.append(value.get(key))
        return [_canonical_formal_blocker(item) for item in raw_items if _canonical_formal_blocker(item)]
    raw_values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for raw in raw_values:
        if isinstance(raw, dict):
            result.extend(_formal_blocker_values_from(raw))
            continue
        code = _canonical_formal_blocker(raw)
        if code:
            result.append(code)
    return result


def _top_formal_blockers(counts: dict[str, int], *, limit: int = 5) -> list[dict[str, Any]]:
    items = []
    for reason_code, count in dict(counts or {}).items():
        code = _canonical_formal_blocker(reason_code)
        if not code or int(count or 0) <= 0:
            continue
        items.append(
            {
                "reason_code": code,
                "count": int(count or 0),
                "label": _FORMAL_BLOCKER_LABELS.get(code, code.replace("_", " ")),
                "next_action": _FORMAL_BLOCKER_ACTIONS.get(
                    code,
                    "Inspect the latest strategy quality report and replay admission after the contract gap is repaired.",
                ),
            }
        )
    items.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("reason_code") or "")))
    return items[: max(1, int(limit or 5))]


def build_strict_incubation_blocker_summary(
    run_rows: list[dict[str, Any]] | None,
    recent_run_diagnostics: dict[str, Any] | None = None,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    rows = [dict(item or {}) for item in list(run_rows or []) if isinstance(item, dict)]
    requested_limit = max(1, int(limit or 5))
    items = rows[:requested_limit]
    diagnostics = dict(recent_run_diagnostics or {})
    blocker_counts: dict[str, int] = {}
    sample_blocked: list[dict[str, Any]] = []
    analyzed_strategy_count = 0
    strict_not_ready_count = 0
    raw_b_or_above_count = 0
    strict_ready_given_raw_b_count = 0
    submitted_count = 0
    formal_requested_count = 0
    observe_lane_count = 0
    diagnostic_lane_count = 0

    def add_blocker(code: Any, *, count: int = 1) -> None:
        normalized = _canonical_formal_blocker(code)
        if not normalized:
            return
        blocker_counts[normalized] = blocker_counts.get(normalized, 0) + max(1, int(count or 1))

    for row in items:
        summary = dict(row.get("summary") or {})
        submission_artifact = dict(row.get("submission_artifact") or {})
        strategy_briefs = [
            dict(item or {})
            for item in list(submission_artifact.get("strategy_briefs") or [])
            if isinstance(item, dict)
        ]
        analyzed_strategy_count += len(strategy_briefs)
        submitted_count += int(summary.get("submitted") or row.get("submitted") or submission_artifact.get("submitted_count") or 0)
        for reason in _formal_blocker_values_from(summary.get("formal_track_blockers")):
            add_blocker(reason)
        for reason in _formal_blocker_values_from(summary.get("admission_block_reasons")):
            add_blocker(reason)
        for item in _formal_blocker_values_from(submission_artifact.get("gate_3_failure_reason_topn")):
            add_blocker(item)
        for brief in strategy_briefs:
            strict_ready = brief.get("strict_incubation_ready") is True
            raw_b_or_above = bool(brief.get("raw_b_or_above")) or str(
                brief.get("raw_validation_grade") or brief.get("validation_grade") or ""
            ).strip().upper() in {"A", "B"}
            if raw_b_or_above:
                raw_b_or_above_count += 1
                if strict_ready:
                    strict_ready_given_raw_b_count += 1
            if not strict_ready:
                strict_not_ready_count += 1
            lane = str(brief.get("submission_lane") or "").strip().lower()
            if lane == "observe_incubation":
                observe_lane_count += 1
            if lane == "diagnostic_observation":
                diagnostic_lane_count += 1
            if brief.get("formal_track_requested") is True:
                formal_requested_count += 1
            reasons = []
            for key in (
                "formal_track_blockers",
                "admission_block_reasons",
                "hard_fail_reasons",
                "submission_action_gaps",
                "trade_prediction_contract_reject_reasons",
            ):
                reasons.extend(_formal_blocker_values_from(brief.get(key)))
            tier = str(brief.get("execution_readiness_tier") or "").strip()
            if tier and tier != "formal_runtime_ready":
                reasons.append(_canonical_formal_blocker(f"execution_readiness_tier:{tier}"))
            if brief.get("diagnostic_only") is True:
                reasons.append("diagnostic_only_not_allowed_for_incubation")
            if str(brief.get("runtime_bootstrap_reason") or "").strip() == "default_profile":
                reasons.append("default_profile_not_allowed_for_single_name_runtime")
            unique_reasons = list(dict.fromkeys([reason for reason in reasons if reason]))
            for reason in unique_reasons:
                add_blocker(reason)
            if unique_reasons and len(sample_blocked) < 5:
                sample_blocked.append(
                    {
                        "strategy_id": brief.get("strategy_id"),
                        "family": brief.get("candidate_family") or brief.get("strategy_type"),
                        "grade": brief.get("raw_validation_grade") or brief.get("validation_grade"),
                        "submission_lane": brief.get("submission_lane"),
                        "strict_incubation_ready": strict_ready,
                        "blockers": unique_reasons[:6],
                    }
                )

    quality_progress = dict(diagnostics.get("quality_progress") or {})
    recent_runs = [dict(item or {}) for item in list(diagnostics.get("recent_runs") or []) if isinstance(item, dict)]
    if not raw_b_or_above_count:
        raw_b_or_above_rate = float(quality_progress.get("recent_raw_b_or_above_rate_mean") or 0.0)
    else:
        raw_b_or_above_rate = _rate(raw_b_or_above_count, analyzed_strategy_count)
    strict_ready_given_raw_b_rate = (
        _rate(strict_ready_given_raw_b_count, raw_b_or_above_count)
        if raw_b_or_above_count
        else float(quality_progress.get("recent_strict_ready_given_raw_b_rate_mean") or 0.0)
    )
    if not submitted_count:
        submitted_count = sum(int(item.get("submitted") or 0) for item in recent_runs)
    for item in list(diagnostics.get("blocker_reason_topn") or []):
        payload = dict(item or {})
        add_blocker(payload.get("reason_code"), count=int(payload.get("count") or 1))

    top_blockers = _top_formal_blockers(blocker_counts)
    status = "ready"
    if not items and not recent_runs:
        status = "no_recent_runs"
    elif top_blockers or strict_ready_given_raw_b_rate == 0.0:
        status = "blocked"
    headline = (
        "No recent Strategy Factory runs were available for formal-admission analysis."
        if status == "no_recent_runs"
        else "Recent runs still fail formal admission because strict incubation readiness is zero."
        if strict_ready_given_raw_b_rate == 0.0 and (raw_b_or_above_count or submitted_count)
        else "Recent runs expose recurring formal-admission blockers."
        if top_blockers
        else "No recurring strict-incubation blocker was detected in recent runs."
    )
    next_action = (
        top_blockers[0]["next_action"]
        if top_blockers
        else "Run another factory cycle with full contract persistence enabled and inspect the latest quality report."
    )
    return {
        "contract_version": "strategy_factory.strict_incubation_blockers.v1",
        "status": status,
        "headline": headline,
        "window_size": requested_limit,
        "analyzed_run_count": len(items) or int(diagnostics.get("analyzed_run_count") or 0),
        "analyzed_strategy_count": analyzed_strategy_count,
        "submitted_count": submitted_count,
        "strict_not_ready_count": strict_not_ready_count,
        "raw_b_or_above_count": raw_b_or_above_count,
        "raw_b_or_above_rate": raw_b_or_above_rate,
        "strict_ready_given_raw_b_count": strict_ready_given_raw_b_count,
        "strict_ready_given_raw_b_rate": strict_ready_given_raw_b_rate,
        "formal_requested_count": formal_requested_count,
        "observe_lane_count": observe_lane_count,
        "diagnostic_lane_count": diagnostic_lane_count,
        "top_blockers": top_blockers,
        "sample_blocked_strategies": sample_blocked,
        "next_action": next_action,
    }


async def refresh_factory_run_detail_quality_contract(db, row: Optional[dict]) -> dict:
    detail = normalize_factory_run_detail_contract(row)
    if not detail or not db:
        return detail
    submission_artifact = dict(detail.get("submission_artifact") or {})
    strategy_briefs = [
        dict(item or {})
        for item in list(submission_artifact.get("strategy_briefs") or [])
        if isinstance(item, dict)
    ]
    if not strategy_briefs:
        return detail

    refreshed_briefs: list[dict[str, Any]] = []
    refreshed = False
    for brief in strategy_briefs:
        strategy_id = str(brief.get("strategy_id") or "").strip()
        if not strategy_id:
            refreshed_briefs.append(brief)
            continue
        latest_report = await get_latest_quality_report(db, strategy_id)
        if not latest_report:
            refreshed_briefs.append(brief)
            continue
        normalized_report = normalize_quality_report_contract(
            latest_report,
            strategy_id=strategy_id,
            strategy_type=brief.get("candidate_family") or brief.get("strategy_type"),
        )
        latest_summary = dict(normalized_report.get("summary") or {})
        raw_latest_summary = dict(latest_report.get("summary") or {})
        latest_quality_gate = dict(latest_report.get("quality_gate") or {})
        latest_validation_profile = dict(latest_report.get("validation_profile") or {})
        merged_brief = dict(brief)
        for key, value in raw_latest_summary.items():
            if value in (None, "", [], {}):
                continue
            latest_summary[key] = deepcopy(value)
        if latest_validation_profile.get("validation_focus") not in (None, "", [], {}):
            latest_summary["validation_focus"] = deepcopy(latest_validation_profile.get("validation_focus"))
        for metric_key in (
            "trade_density",
            "post_cost_sharpe",
            "deflated_sharpe_ratio",
            "pbo",
            "strict_incubation_ready",
            "live_candidate_ready",
        ):
            if latest_quality_gate.get(metric_key) not in (None, "", [], {}):
                latest_summary[metric_key] = deepcopy(latest_quality_gate.get(metric_key))
        for key, value in latest_summary.items():
            if value in (None, "", [], {}):
                continue
            merged_brief[key] = deepcopy(value)
        refreshed_briefs.append(merged_brief)
        refreshed = True

    if not refreshed:
        return detail

    refreshed_summary = _summarize_factory_submission_briefs(refreshed_briefs)
    submission_artifact["strategy_briefs"] = refreshed_briefs
    for key, value in refreshed_summary.items():
        submission_artifact[key] = deepcopy(value)

    detail["submission_artifact"] = submission_artifact
    for key, value in refreshed_summary.items():
        detail[key] = deepcopy(value)

    summary = dict(detail.get("summary") or {})
    for key, value in refreshed_summary.items():
        summary[key] = deepcopy(value)
    detail["summary"] = summary
    return detail
