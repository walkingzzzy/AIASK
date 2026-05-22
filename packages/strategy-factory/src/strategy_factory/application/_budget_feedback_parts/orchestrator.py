

def _build_skill_feedback_proxy(metrics: dict[str, Any]) -> dict[str, Any]:
    proxy = dict(metrics or {})
    paper_skill_lcb = _clamp(safe_float(metrics.get("paper_skill_lcb"), 0.0), -1.0, 1.0)
    paper_coverage_ratio = _clamp(
        safe_float(metrics.get("paper_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    forward_window_coverage_ratio = _clamp(
        safe_float(metrics.get("forward_window_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    proxy["paper_hit_ratio"] = _clamp(0.5 + paper_skill_lcb, 0.0, 1.0)
    proxy["forward_window_coverage_ratio"] = min(
        forward_window_coverage_ratio,
        paper_coverage_ratio,
    )
    return proxy


def compute_budget_multiplier(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    zero_signal_ratio = max(0.0, min(safe_float(metrics.get("zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(metrics.get("low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(0.0, min(safe_float(metrics.get("evidence_debt_ratio"), 0.0), 1.0))
    raw_validation_a_rate = max(0.0, min(safe_float(metrics.get("raw_validation_a_rate"), 0.0), 1.0))
    raw_validation_b_rate = max(0.0, min(safe_float(metrics.get("raw_validation_b_rate"), 0.0), 1.0))
    raw_validation_d_rate = max(0.0, min(safe_float(metrics.get("raw_validation_d_rate"), 1.0), 1.0))
    raw_validation_total_score_mean = max(
        0.0,
        min(safe_float(metrics.get("raw_validation_total_score_mean"), 0.0), 100.0),
    )
    strict_incubation_ready_rate = max(
        0.0,
        min(safe_float(metrics.get("strict_incubation_ready_rate"), 0.0), 1.0),
    )
    ema_submit_count = max(0.0, min(safe_float(metrics.get("ema_submit_count"), 0.0), 8.0))
    promotion_review_count = _safe_int(metrics.get("promotion_review_count"))
    promotion_review_score = max(0.0, min(safe_float(metrics.get("promotion_review_score"), 0.5), 1.0))
    promotion_review_status = normalize_text(metrics.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(metrics.get("promotion_review_recommendation"))
    high_precision_objective = max(
        0.0,
        min(safe_float(metrics.get("high_precision_objective"), 0.0), 1.0),
    )

    paper_bonus = (paper_hit_ratio - 0.5) * 0.7
    turnover_penalty = max(realized_turnover - 0.55, 0.0) * 0.25
    crowding_penalty = max(capacity_crowding - 0.45, 0.0) * 0.22
    evidence_penalty = (
        zero_signal_ratio * 0.28
        + low_signal_ratio * 0.08
        + max(0.55 - forward_window_coverage_ratio, 0.0) * 0.30
        + max(0.45 - promotion_ready_ratio, 0.0) * 0.18
        + max(0.30 - promotion_review_coverage_ratio, 0.0) * 0.12
        + evidence_debt_ratio * 0.22
    )
    ab_quality_bonus = (
        raw_validation_a_rate * 0.28
        + raw_validation_b_rate * 0.18
        + strict_incubation_ready_rate * 0.16
        + max(raw_validation_total_score_mean - 55.0, 0.0) / 45.0 * 0.18
    )
    low_quality_penalty = (
        raw_validation_d_rate * 0.24
        + max(0.30 - (raw_validation_a_rate + raw_validation_b_rate), 0.0) * 0.22
    )
    submit_bonus = min(ema_submit_count / 10.0, 0.12)
    promotion_review_adjustment = 0.0
    if promotion_review_count > 0:
        promotion_review_adjustment += (promotion_review_score - 0.5) * 0.18
        if promotion_review_status == "approved" or promotion_review_recommendation == "promote":
            promotion_review_adjustment += 0.05
        elif promotion_review_status == "watch" or promotion_review_recommendation == "observe":
            promotion_review_adjustment -= 0.06
        elif promotion_review_status == "rejected" or promotion_review_recommendation == "deprecate":
            promotion_review_adjustment -= 0.18
    multiplier = (
        1.0
        + paper_bonus
        - runtime_alert_pressure * 0.42
        - turnover_penalty
        - crowding_penalty
        - evidence_penalty
        + ab_quality_bonus
        - low_quality_penalty
        + submit_bonus
        + promotion_review_adjustment
        + high_precision_objective * 0.10
    )
    return round(min(max(multiplier, 0.4), 1.75), 4)


def compute_skill_budget_multiplier(metrics: dict[str, Any]) -> float:
    proxy = _build_skill_feedback_proxy(metrics)
    paper_recent_skill_lcb = _clamp(
        safe_float(metrics.get("paper_recent_skill_lcb"), metrics.get("paper_skill_lcb")),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(safe_float(metrics.get("paper_stability_gap"), 0.0), 0.0, 1.0)
    paper_coverage_ratio = _clamp(safe_float(metrics.get("paper_coverage_ratio"), 1.0), 0.0, 1.0)
    multiplier = compute_budget_multiplier(proxy)
    multiplier += paper_recent_skill_lcb * 0.45
    multiplier -= max(paper_stability_gap - 0.05, 0.0) * 1.15
    multiplier -= max(0.60 - paper_coverage_ratio, 0.0) * 0.32
    multiplier += _clamp(safe_float(metrics.get("high_precision_objective"), 0.0), 0.0, 1.0) * 0.08
    return round(min(max(multiplier, 0.3), 1.75), 4)


def compute_priority_adjustment(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    zero_signal_ratio = max(0.0, min(safe_float(metrics.get("zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(metrics.get("low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(0.0, min(safe_float(metrics.get("evidence_debt_ratio"), 0.0), 1.0))
    raw_validation_a_rate = max(0.0, min(safe_float(metrics.get("raw_validation_a_rate"), 0.0), 1.0))
    raw_validation_b_rate = max(0.0, min(safe_float(metrics.get("raw_validation_b_rate"), 0.0), 1.0))
    raw_validation_d_rate = max(0.0, min(safe_float(metrics.get("raw_validation_d_rate"), 1.0), 1.0))
    raw_validation_total_score_mean = max(
        0.0,
        min(safe_float(metrics.get("raw_validation_total_score_mean"), 0.0), 100.0),
    )
    strict_incubation_ready_rate = max(
        0.0,
        min(safe_float(metrics.get("strict_incubation_ready_rate"), 0.0), 1.0),
    )
    ema_submit_count = max(0.0, min(safe_float(metrics.get("ema_submit_count"), 0.0), 8.0))
    promotion_review_count = _safe_int(metrics.get("promotion_review_count"))
    promotion_review_score = max(0.0, min(safe_float(metrics.get("promotion_review_score"), 0.5), 1.0))
    promotion_review_status = normalize_text(metrics.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(metrics.get("promotion_review_recommendation"))
    high_precision_objective = max(
        0.0,
        min(safe_float(metrics.get("high_precision_objective"), 0.0), 1.0),
    )

    turnover_penalty = max(realized_turnover - 0.55, 0.0)
    crowding_penalty = max(capacity_crowding - 0.45, 0.0)
    promotion_review_adjustment = 0.0
    if promotion_review_count > 0:
        promotion_review_adjustment += (promotion_review_score - 0.5) * 6.0
        if promotion_review_status == "approved" or promotion_review_recommendation == "promote":
            promotion_review_adjustment += 3.0
        elif promotion_review_status == "watch" or promotion_review_recommendation == "observe":
            promotion_review_adjustment -= 5.0
        elif promotion_review_status == "rejected" or promotion_review_recommendation == "deprecate":
            promotion_review_adjustment -= 10.0
    adjustment = (
        (paper_hit_ratio - 0.5) * 14.0
        - runtime_alert_pressure * 8.5
        - turnover_penalty * 5.0
        - crowding_penalty * 4.5
        - zero_signal_ratio * 10.0
        - low_signal_ratio * 3.0
        - max(0.55 - forward_window_coverage_ratio, 0.0) * 8.0
        - max(0.40 - promotion_ready_ratio, 0.0) * 6.0
        - max(0.25 - promotion_review_coverage_ratio, 0.0) * 4.0
        - evidence_debt_ratio * 7.0
        + raw_validation_a_rate * 11.0
        + raw_validation_b_rate * 7.0
        + strict_incubation_ready_rate * 6.0
        + max(raw_validation_total_score_mean - 55.0, 0.0) / 45.0 * 5.0
        - raw_validation_d_rate * 9.0
        - max(0.30 - (raw_validation_a_rate + raw_validation_b_rate), 0.0) * 8.0
        + min(ema_submit_count, 6.0) * 0.75
        + promotion_review_adjustment
        + high_precision_objective * 2.5
    )
    return round(adjustment, 4)


def compute_skill_priority_adjustment(metrics: dict[str, Any]) -> float:
    proxy = _build_skill_feedback_proxy(metrics)
    paper_recent_skill_lcb = _clamp(
        safe_float(metrics.get("paper_recent_skill_lcb"), metrics.get("paper_skill_lcb")),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(safe_float(metrics.get("paper_stability_gap"), 0.0), 0.0, 1.0)
    paper_coverage_ratio = _clamp(safe_float(metrics.get("paper_coverage_ratio"), 1.0), 0.0, 1.0)
    adjustment = compute_priority_adjustment(proxy)
    adjustment += paper_recent_skill_lcb * 9.0
    adjustment -= max(paper_stability_gap - 0.05, 0.0) * 24.0
    adjustment -= max(0.60 - paper_coverage_ratio, 0.0) * 7.0
    return round(adjustment, 4)


def compute_failure_penalty_adjustment(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    zero_signal_ratio = max(0.0, min(safe_float(metrics.get("zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(metrics.get("low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(0.0, min(safe_float(metrics.get("evidence_debt_ratio"), 0.0), 1.0))
    raw_validation_a_rate = max(0.0, min(safe_float(metrics.get("raw_validation_a_rate"), 0.0), 1.0))
    raw_validation_b_rate = max(0.0, min(safe_float(metrics.get("raw_validation_b_rate"), 0.0), 1.0))
    raw_validation_d_rate = max(0.0, min(safe_float(metrics.get("raw_validation_d_rate"), 1.0), 1.0))
    raw_validation_total_score_mean = max(
        0.0,
        min(safe_float(metrics.get("raw_validation_total_score_mean"), 0.0), 100.0),
    )
    strict_incubation_ready_rate = max(
        0.0,
        min(safe_float(metrics.get("strict_incubation_ready_rate"), 0.0), 1.0),
    )
    promotion_review_count = _safe_int(metrics.get("promotion_review_count"))
    promotion_review_score = max(0.0, min(safe_float(metrics.get("promotion_review_score"), 0.5), 1.0))
    promotion_review_status = normalize_text(metrics.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(metrics.get("promotion_review_recommendation"))

    turnover_penalty = max(realized_turnover - 0.55, 0.0) * 0.08
    crowding_penalty = max(capacity_crowding - 0.45, 0.0) * 0.06
    paper_credit = max(paper_hit_ratio - 0.55, 0.0) * 0.08
    promotion_review_penalty = 0.0
    if promotion_review_count > 0:
        promotion_review_penalty += max(0.5 - promotion_review_score, 0.0) * 0.12
        if promotion_review_status == "watch" or promotion_review_recommendation == "observe":
            promotion_review_penalty += 0.08
        elif promotion_review_status == "rejected" or promotion_review_recommendation == "deprecate":
            promotion_review_penalty += 0.14
        elif promotion_review_status == "approved" or promotion_review_recommendation == "promote":
            promotion_review_penalty -= 0.03
    adjustment = (
        runtime_alert_pressure * 0.12
        + turnover_penalty
        + crowding_penalty
        + zero_signal_ratio * 0.06
        + low_signal_ratio * 0.03
        + max(0.55 - forward_window_coverage_ratio, 0.0) * 0.08
        + max(0.40 - promotion_ready_ratio, 0.0) * 0.06
        + max(0.25 - promotion_review_coverage_ratio, 0.0) * 0.04
        + evidence_debt_ratio * 0.05
        + raw_validation_d_rate * 0.12
        + max(0.25 - (raw_validation_a_rate + raw_validation_b_rate), 0.0) * 0.08
        + max(50.0 - raw_validation_total_score_mean, 0.0) / 50.0 * 0.07
        - paper_credit
        - raw_validation_a_rate * 0.04
        - raw_validation_b_rate * 0.03
        - strict_incubation_ready_rate * 0.04
        + promotion_review_penalty
    )
    return round(min(max(adjustment, -0.06), 0.22), 4)


def compute_skill_failure_penalty_adjustment(metrics: dict[str, Any]) -> float:
    proxy = _build_skill_feedback_proxy(metrics)
    paper_skill_lcb = _clamp(safe_float(metrics.get("paper_skill_lcb"), 0.0), -1.0, 1.0)
    paper_recent_skill_lcb = _clamp(
        safe_float(metrics.get("paper_recent_skill_lcb"), paper_skill_lcb),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(safe_float(metrics.get("paper_stability_gap"), 0.0), 0.0, 1.0)
    paper_coverage_ratio = _clamp(safe_float(metrics.get("paper_coverage_ratio"), 1.0), 0.0, 1.0)
    adjustment = compute_failure_penalty_adjustment(proxy)
    adjustment += max(0.0 - paper_recent_skill_lcb, 0.0) * 0.14
    adjustment += max(paper_stability_gap - 0.05, 0.0) * 0.28
    adjustment += max(0.60 - paper_coverage_ratio, 0.0) * 0.08
    adjustment -= max(paper_skill_lcb, 0.0) * 0.05
    return round(min(max(adjustment, -0.06), 0.24), 4)


__all__ = [
    "CONTROL_MODE_SEVERITY",
    "LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION",
    "apply_feedback_controls_to_task",
    "FEEDBACK_METRIC_KEYS",
    "compute_budget_multiplier",
    "compute_failure_penalty_adjustment",
    "compute_priority_adjustment",
    "compute_skill_budget_multiplier",
    "compute_skill_failure_penalty_adjustment",
    "compute_skill_priority_adjustment",
    "collect_generator_mode_feedback_controls",
    "derive_target_pool_id",
    "extract_feedback_root",
    "extract_feedback_families",
    "extract_generator_mode",
    "extract_holding_bucket",
    "extract_target_pool_id",
    "is_relaxable_feedback_backlog_control",
    "normalize_feedback_input_contract",
    "normalize_text",
    "relax_feedback_control_for_research_task",
    "resolve_feedback_metrics",
    "resolve_task_feedback_metrics",
    "safe_float",
    "summarize_task_feedback_controls",
]
