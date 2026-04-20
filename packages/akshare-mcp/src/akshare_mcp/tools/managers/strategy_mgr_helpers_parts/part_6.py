

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
