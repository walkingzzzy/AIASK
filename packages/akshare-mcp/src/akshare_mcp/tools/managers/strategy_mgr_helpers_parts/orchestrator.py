

def _summarize_factory_submission_briefs(strategy_briefs: list[dict[str, Any]]) -> dict[str, Any]:
    briefs = [dict(item or {}) for item in list(strategy_briefs or []) if isinstance(item, dict)]
    strategy_count = len(briefs)
    validation_grade_distribution: dict[str, int] = {}
    raw_validation_grade_distribution: dict[str, int] = {}
    effective_validation_grade_distribution: dict[str, int] = {}
    raw_validation_total_scores: list[float] = []
    strict_incubation_ready_count = 0
    live_candidate_ready_count = 0
    raw_b_or_above_count = 0
    strict_ready_given_raw_b_count = 0
    live_ready_given_raw_b_count = 0
    strict_live_alignment_gap_count = 0
    strict_live_alignment_status_counts: dict[str, int] = {}
    candidate_local_attempt_count = 0
    task_local_attempt_count = 0
    cohort_effective_trials = 0.0
    economic_semantics_missing_count = 0
    unique_family_holding_universe: set[tuple[str, str, str]] = set()
    for brief in briefs:
        validation_grade = str(brief.get("validation_grade") or "").strip().upper()
        raw_validation_grade = str(
            brief.get("raw_validation_grade") or validation_grade or ""
        ).strip().upper()
        effective_validation_grade = str(
            brief.get("effective_validation_grade") or validation_grade or ""
        ).strip().upper()
        strict_ready = brief.get("strict_incubation_ready") is True
        live_ready = brief.get("live_candidate_ready") is True
        if strict_ready and live_ready:
            alignment_status = "aligned_live_ready"
        elif strict_ready:
            alignment_status = "strict_only_gap"
        elif live_ready:
            alignment_status = "live_ready_without_strict"
        else:
            alignment_status = "aligned_blocked"
        strict_live_alignment_status_counts[alignment_status] = (
            strict_live_alignment_status_counts.get(alignment_status, 0) + 1
        )
        if validation_grade:
            validation_grade_distribution[validation_grade] = (
                validation_grade_distribution.get(validation_grade, 0) + 1
            )
        if raw_validation_grade:
            raw_validation_grade_distribution[raw_validation_grade] = (
                raw_validation_grade_distribution.get(raw_validation_grade, 0) + 1
            )
        if effective_validation_grade:
            effective_validation_grade_distribution[effective_validation_grade] = (
                effective_validation_grade_distribution.get(effective_validation_grade, 0) + 1
            )
        if brief.get("raw_validation_total_score") is not None:
            raw_validation_total_scores.append(_safe_float(brief.get("raw_validation_total_score")))
        if strict_ready:
            strict_incubation_ready_count += 1
        if live_ready:
            live_candidate_ready_count += 1
        if strict_ready and not live_ready:
            strict_live_alignment_gap_count += 1
        if _is_raw_b_or_above(raw_validation_grade):
            raw_b_or_above_count += 1
            if strict_ready:
                strict_ready_given_raw_b_count += 1
            if live_ready:
                live_ready_given_raw_b_count += 1
        candidate_local_attempt_count += int(brief.get("candidate_local_attempt_count") or 0)
        task_local_attempt_count += int(brief.get("task_local_attempt_count") or 0)
        cohort_effective_trials += _safe_float(brief.get("cohort_effective_trials"), 0.0)
        if brief.get("economic_semantics_missing") is True:
            economic_semantics_missing_count += 1
        unique_family_holding_universe.add(
            (
                str(brief.get("candidate_family") or brief.get("strategy_type") or "unknown").strip().lower() or "unknown",
                _brief_holding_bucket(brief),
                _brief_target_universe_key(brief),
            )
        )

    summary = {
        "strategy_count": strategy_count,
        "validation_grade_distribution": validation_grade_distribution,
        "raw_validation_grade_distribution": raw_validation_grade_distribution,
        "effective_validation_grade_distribution": effective_validation_grade_distribution,
        "raw_validation_total_score_mean": round(
            sum(raw_validation_total_scores) / len(raw_validation_total_scores),
            4,
        ) if raw_validation_total_scores else 0.0,
        "raw_validation_total_score_p50": _percentile(raw_validation_total_scores, 0.5),
        "raw_validation_total_score_p90": _percentile(raw_validation_total_scores, 0.9),
        "strict_incubation_ready_count": strict_incubation_ready_count,
        "strict_incubation_ready_rate": _rate(strict_incubation_ready_count, strategy_count),
        "live_candidate_ready_count": live_candidate_ready_count,
        "live_candidate_ready_rate": _rate(live_candidate_ready_count, strategy_count),
        "raw_b_or_above_count": raw_b_or_above_count,
        "raw_b_or_above_rate": _rate(raw_b_or_above_count, strategy_count),
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
        "strict_live_alignment_gap_count": strict_live_alignment_gap_count,
        "strict_live_alignment_gap_rate": _rate(
            strict_live_alignment_gap_count,
            strategy_count,
        ),
        "strict_live_alignment_status_counts": strict_live_alignment_status_counts,
        "validation_family_quality_panel": _build_family_quality_panel(briefs),
        "candidate_local_attempt_count": candidate_local_attempt_count,
        "task_local_attempt_count": task_local_attempt_count,
        "cohort_effective_trials": round(cohort_effective_trials, 4),
        "unique_family_holding_universe_count": len(unique_family_holding_universe),
        "economic_semantics_missing_count": economic_semantics_missing_count,
    }
    summary.update(_grade_rates(raw_validation_grade_distribution, strategy_count))
    summary.update(_summarize_high_confidence_quality(briefs))
    return summary


def _normalize_reason_codes(values: Any) -> list[str]:
    if values in (None, "", [], {}):
        return []
    items = values if isinstance(values, (list, tuple, set)) else [values]
    codes: list[str] = []
    for value in items:
        code = str(value or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def _top_reason_counts(reason_counts: dict[str, int], *, limit: int = 5) -> list[dict[str, Any]]:
    items = [
        {"reason_code": str(reason_code or ""), "count": int(count or 0)}
        for reason_code, count in dict(reason_counts or {}).items()
        if str(reason_code or "").strip() and int(count or 0) > 0
    ]
    items.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("reason_code") or "")))
    return items[: max(1, int(limit or 5))]


def _top_named_counts(
    counts: dict[str, int],
    *,
    name_key: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    items = [
        {name_key: str(name or ""), "count": int(count or 0)}
        for name, count in dict(counts or {}).items()
        if str(name or "").strip() and int(count or 0) > 0
    ]
    items.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get(name_key) or "")))
    return items[: max(1, int(limit or 5))]


def _normalize_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for raw_key, raw_value in dict(value or {}).items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        try:
            count = int(raw_value or 0)
        except Exception:
            continue
        if count <= 0:
            continue
        normalized[key] = count
    return normalized


def _extract_run_metric_value(payload: Optional[dict], field: str) -> Any:
    data = dict(payload or {})
    summary = dict(data.get("summary") or {})
    for container in (data, summary):
        if field not in container:
            continue
        value = container.get(field)
        if value in (None, "", [], {}):
            continue
        return value
    return None


def _extract_run_metric_or_stage_value(
    payload: Optional[dict],
    field: str,
    *,
    stage_name: str | None = None,
) -> Any:
    data = dict(payload or {})
    summary = dict(data.get("summary") or {})
    stages = dict(data.get("stages") or {})
    containers: list[dict[str, Any]] = []
    if stage_name:
        containers.append(dict(stages.get(stage_name) or {}))
    containers.extend((summary, data))
    for container in containers:
        if field not in container:
            continue
        value = container.get(field)
        if value in (None, "", [], {}):
            continue
        return value
    return None


def _append_numeric(values: list[float], raw_value: Any) -> None:
    if raw_value in (None, "", [], {}):
        return
    values.append(_safe_float(raw_value))


def _is_governed_reason_code(reason_code: str) -> bool:
    code = str(reason_code or "").strip().lower()
    return code.startswith("governed_candidate_pool_") or code == "factor_scheduler_recent_success_without_governed_pool"


def _is_evidence_debt_reason_code(reason_code: str) -> bool:
    code = str(reason_code or "").strip().lower()
    return code.startswith("incubating_") or code.startswith("budget_feedback_")


def _extract_factory_run_readiness_snapshot(payload: Optional[dict]) -> dict[str, Any]:
    data = dict(payload or {})
    summary = dict(data.get("summary") or {})
    stages = dict(data.get("stages") or {})
    readiness_stage = dict(stages.get("readiness") or {})
    can_proceed = summary.get("factory_readiness_can_proceed")
    if can_proceed is None:
        can_proceed = readiness_stage.get("can_proceed")
    decision = str(
        summary.get("factory_readiness_decision")
        or readiness_stage.get("decision")
        or ""
    ).strip().lower()
    if decision not in {"proceed", "blocked"}:
        if can_proceed is False or str(data.get("status") or "").strip().lower() == "skipped":
            decision = "blocked"
        else:
            decision = "proceed"
    blocker_codes = _normalize_reason_codes(
        summary.get("factory_readiness_effective_blocking_reason_codes")
        or summary.get("factory_readiness_blocking_reason_codes")
        or readiness_stage.get("effective_blocking_reason_codes")
        or readiness_stage.get("blocking_reason_codes")
        or readiness_stage.get("blockers")
    )
    raw_blocker_codes = _normalize_reason_codes(
        summary.get("factory_readiness_blocking_reason_codes")
        or readiness_stage.get("blocking_reason_codes")
        or readiness_stage.get("blockers")
    )
    warning_codes = _normalize_reason_codes(
        readiness_stage.get("warning_reason_codes")
        or readiness_stage.get("warnings")
    )
    return {
        "decision": decision,
        "can_proceed": bool(can_proceed) if can_proceed is not None else decision != "blocked",
        "score": _extract_run_metric_value(data, "factory_readiness_score"),
        "blocking_stage": summary.get("factory_readiness_blocking_stage") or readiness_stage.get("blocking_stage"),
        "skip_reason": summary.get("skip_reason") or readiness_stage.get("skip_reason"),
        "blocker_count": int(
            summary.get("factory_readiness_blocker_count")
            or readiness_stage.get("blocker_count")
            or len(blocker_codes)
            or 0
        ),
        "warning_count": int(
            summary.get("factory_readiness_warning_count")
            or readiness_stage.get("warning_count")
            or len(warning_codes)
            or 0
        ),
        "blocking_reason_codes": blocker_codes,
        "raw_blocking_reason_codes": raw_blocker_codes,
        "blocking_reason_codes_source": (
            summary.get("factory_readiness_blocking_reason_codes_source")
            or readiness_stage.get("blocking_reason_codes_source")
        ),
        "warning_reason_codes": warning_codes,
        "governed_blocked_ratio": _extract_run_metric_or_stage_value(
            data,
            "governed_blocked_ratio",
            stage_name="readiness",
        ),
        "governed_blocked_candidate_count": _extract_run_metric_or_stage_value(
            data,
            "governed_blocked_candidate_count",
            stage_name="readiness",
        ),
        "governed_source_candidate_count": _extract_run_metric_or_stage_value(
            data,
            "governed_source_candidate_count",
            stage_name="readiness",
        ),
        "governed_candidate_pool_strict_shortfall_count": _extract_run_metric_or_stage_value(
            data,
            "governed_candidate_pool_strict_shortfall_count",
            stage_name="readiness",
        ),
        "budget_feedback_evidence_debt_ratio": _extract_run_metric_or_stage_value(
            data,
            "budget_feedback_evidence_debt_ratio",
            stage_name="readiness",
        ),
        "budget_feedback_zero_signal_ratio": _extract_run_metric_or_stage_value(
            data,
            "budget_feedback_zero_signal_ratio",
            stage_name="readiness",
        ),
        "budget_feedback_forward_window_coverage_ratio": _extract_run_metric_or_stage_value(
            data,
            "budget_feedback_forward_window_coverage_ratio",
            stage_name="readiness",
        ),
        "budget_feedback_promotion_ready_ratio": _extract_run_metric_or_stage_value(
            data,
            "budget_feedback_promotion_ready_ratio",
            stage_name="readiness",
        ),
        "budget_feedback_promotion_review_coverage_ratio": _extract_run_metric_or_stage_value(
            data,
            "budget_feedback_promotion_review_coverage_ratio",
            stage_name="readiness",
        ),
        "governed_blocking_reason_counts": _normalize_count_map(
            _extract_run_metric_or_stage_value(
                data,
                "governed_blocking_reason_counts",
                stage_name="readiness",
            )
        ),
        "governed_exclusion_reason_counts": _normalize_count_map(
            _extract_run_metric_or_stage_value(
                data,
                "governed_exclusion_reason_counts",
                stage_name="readiness",
            )
        ),
        "governed_pending_reason_counts": _normalize_count_map(
            _extract_run_metric_or_stage_value(
                data,
                "governed_pending_reason_counts",
                stage_name="readiness",
            )
        ),
        "governed_ineligible_reason_counts": _normalize_count_map(
            _extract_run_metric_or_stage_value(
                data,
                "governed_ineligible_reason_counts",
                stage_name="readiness",
            )
        ),
    }
