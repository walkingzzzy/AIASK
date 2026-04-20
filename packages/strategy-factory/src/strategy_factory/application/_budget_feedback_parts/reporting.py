

def _derive_skill_scope_control(bucket: dict[str, Any], *, scope_name: str) -> dict[str, Any]:
    payload = dict(bucket or {})
    if not payload:
        return {
            "scope": scope_name,
            "mode": "normal",
            "severity": 0,
            "cooldown_active": False,
            "suppressed": False,
            "freeze_active": False,
            "reasons": [],
        }

    paper_skill_lcb = _clamp(safe_float(_metric_value(payload, "paper_skill_lcb"), 0.0), -1.0, 1.0)
    paper_recent_skill_lcb = _clamp(
        safe_float(_metric_value(payload, "paper_recent_skill_lcb"), paper_skill_lcb),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(
        safe_float(_metric_value(payload, "paper_stability_gap"), 0.0),
        0.0,
        1.0,
    )
    paper_coverage_ratio = _clamp(
        safe_float(_metric_value(payload, "paper_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    runtime_alert_pressure = _clamp(
        safe_float(_metric_value(payload, "runtime_alert_pressure"), 0.0),
        0.0,
        1.0,
    )
    realized_turnover = _clamp(
        safe_float(_metric_value(payload, "realized_turnover"), 0.0),
        0.0,
        2.0,
    )
    capacity_crowding = _clamp(
        safe_float(_metric_value(payload, "capacity_crowding"), 0.0),
        0.0,
        2.0,
    )
    runtime_alert_count = _safe_int(payload.get("runtime_alert_count"))
    runtime_risk_event_count = _safe_int(payload.get("runtime_risk_event_count"))
    strategy_count = _safe_int(payload.get("strategy_count"))
    zero_signal_ratio = _clamp(safe_float(_metric_value(payload, "zero_signal_ratio"), 0.0), 0.0, 1.0)
    low_signal_ratio = _clamp(safe_float(_metric_value(payload, "low_signal_ratio"), 0.0), 0.0, 1.0)
    forward_window_coverage_ratio = _clamp(
        safe_float(_metric_value(payload, "forward_window_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    promotion_ready_ratio = _clamp(
        safe_float(_metric_value(payload, "promotion_ready_ratio"), 1.0),
        0.0,
        1.0,
    )
    promotion_review_coverage_ratio = _clamp(
        safe_float(_metric_value(payload, "promotion_review_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    evidence_debt_ratio = _clamp(
        safe_float(_metric_value(payload, "evidence_debt_ratio"), 0.0),
        0.0,
        1.0,
    )
    promotion_review_count = _safe_int(payload.get("promotion_review_count"))
    promotion_review_score = _clamp(safe_float(payload.get("promotion_review_score"), 0.5), 0.0, 1.0)
    promotion_review_status = normalize_text(payload.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(payload.get("promotion_review_recommendation"))
    freeze_active = any(
        _truthy_flag(payload.get(key))
        for key in ("freeze", "freeze_active", "scope_freeze_active", "hard_freeze")
    )
    suppressed = any(
        _truthy_flag(payload.get(key))
        for key in ("suppress", "suppress_active", "suppressed")
    )
    cooldown_active = any(
        _truthy_flag(payload.get(key))
        for key in ("cooldown", "cooldown_active")
    )
    reasons: list[str] = []

    if runtime_alert_pressure >= 0.88:
        freeze_active = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_freeze")
    elif runtime_alert_pressure >= 0.72:
        suppressed = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_suppress")
    elif runtime_alert_pressure >= 0.55:
        cooldown_active = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_cooldown")

    if paper_skill_lcb <= -0.08 or paper_recent_skill_lcb <= -0.10:
        freeze_active = True
        reasons.append(f"{scope_name}_paper_skill_lcb_collapse")
    elif paper_skill_lcb <= -0.03 or paper_recent_skill_lcb <= -0.05:
        suppressed = True
        reasons.append(f"{scope_name}_paper_skill_lcb_suppress")
    elif paper_skill_lcb < 0.015 or paper_recent_skill_lcb < -0.005:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_skill_lcb_cooldown")

    if paper_stability_gap >= 0.18:
        freeze_active = True
        reasons.append(f"{scope_name}_paper_stability_gap_freeze")
    elif paper_stability_gap >= 0.11:
        suppressed = True
        reasons.append(f"{scope_name}_paper_stability_gap_suppress")
    elif paper_stability_gap > 0.07:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_stability_gap_cooldown")

    if paper_coverage_ratio <= 0.15 and strategy_count >= 4:
        suppressed = True
        reasons.append(f"{scope_name}_paper_coverage_ratio_suppress")
    elif paper_coverage_ratio < 0.45 and strategy_count >= 3:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_coverage_ratio_cooldown")

    if realized_turnover >= 1.45 or capacity_crowding >= 1.20:
        freeze_active = True
        reasons.append(f"{scope_name}_turnover_or_crowding_freeze")
    elif realized_turnover >= 1.15 or capacity_crowding >= 0.95:
        suppressed = True
        reasons.append(f"{scope_name}_turnover_or_crowding_suppress")
    elif realized_turnover >= 0.90 or capacity_crowding >= 0.75:
        cooldown_active = True
        reasons.append(f"{scope_name}_turnover_or_crowding_cooldown")

    if runtime_alert_count + runtime_risk_event_count >= 6:
        freeze_active = True
        reasons.append(f"{scope_name}_open_risk_load_freeze")
    elif runtime_alert_count + runtime_risk_event_count >= 4:
        suppressed = True
        reasons.append(f"{scope_name}_open_risk_load_suppress")
    elif runtime_alert_count + runtime_risk_event_count >= 2:
        cooldown_active = True
        reasons.append(f"{scope_name}_open_risk_load_cooldown")

    if strategy_count >= 2:
        if zero_signal_ratio >= 0.85 and strategy_count >= 4:
            freeze_active = True
            reasons.append(f"{scope_name}_zero_signal_backlog_freeze")
        elif zero_signal_ratio >= 0.65 and strategy_count >= 3:
            suppressed = True
            reasons.append(f"{scope_name}_zero_signal_backlog_suppress")
        elif zero_signal_ratio >= 0.40:
            cooldown_active = True
            reasons.append(f"{scope_name}_zero_signal_backlog_cooldown")

        if low_signal_ratio >= 0.90 and strategy_count >= 4:
            suppressed = True
            reasons.append(f"{scope_name}_low_signal_backlog_suppress")
        elif low_signal_ratio >= 0.60 and strategy_count >= 3:
            cooldown_active = True
            reasons.append(f"{scope_name}_low_signal_backlog_cooldown")

        if forward_window_coverage_ratio <= 0.15 and strategy_count >= 4:
            suppressed = True
            reasons.append(f"{scope_name}_forward_window_coverage_suppress")
        elif forward_window_coverage_ratio <= 0.35 and strategy_count >= 3:
            cooldown_active = True
            reasons.append(f"{scope_name}_forward_window_coverage_cooldown")

        if promotion_ready_ratio <= 0.10 and strategy_count >= 4:
            suppressed = True
            reasons.append(f"{scope_name}_promotion_ready_gap_suppress")
        elif promotion_ready_ratio <= 0.25 and strategy_count >= 3:
            cooldown_active = True
            reasons.append(f"{scope_name}_promotion_ready_gap_cooldown")

        if promotion_review_coverage_ratio <= 0.05 and strategy_count >= 8:
            suppressed = True
            reasons.append(f"{scope_name}_promotion_review_gap_suppress")
        elif promotion_review_coverage_ratio <= 0.15 and strategy_count >= 4:
            cooldown_active = True
            reasons.append(f"{scope_name}_promotion_review_gap_cooldown")

        if evidence_debt_ratio >= 0.82 and strategy_count >= 4:
            freeze_active = True
            reasons.append(f"{scope_name}_evidence_debt_freeze")
        elif evidence_debt_ratio >= 0.65 and strategy_count >= 3:
            suppressed = True
            reasons.append(f"{scope_name}_evidence_debt_suppress")
        elif evidence_debt_ratio >= 0.45:
            cooldown_active = True
            reasons.append(f"{scope_name}_evidence_debt_cooldown")

    if promotion_review_count > 0:
        if (
            promotion_review_status == "rejected"
            or promotion_review_recommendation == "deprecate"
        ):
            freeze_active = True
            reasons.append(f"{scope_name}_promotion_review_rejected")
        elif (
            promotion_review_status == "watch"
            or promotion_review_recommendation == "observe"
        ):
            cooldown_active = True
            reasons.append(f"{scope_name}_promotion_review_watch")
        if promotion_review_score <= 0.2:
            freeze_active = True
            reasons.append(f"{scope_name}_promotion_review_score_freeze")
        elif promotion_review_score <= 0.35:
            suppressed = True
            reasons.append(f"{scope_name}_promotion_review_score_suppress")
        elif promotion_review_score < 0.5:
            cooldown_active = True
            reasons.append(f"{scope_name}_promotion_review_score_cooldown")

    return _finalize_scope_control(
        scope_name=scope_name,
        freeze_active=freeze_active,
        suppressed=suppressed,
        cooldown_active=cooldown_active,
        reasons=reasons,
    )


def resolve_feedback_metrics(
    snapshot_or_feedback: Any,
    *,
    family: str,
    target_pool_id: str | None = None,
    holding_bucket: str | None = None,
    generator_mode: str | None = None,
) -> dict[str, Any]:
    feedback_root = extract_feedback_root(snapshot_or_feedback)
    family_bucket = _resolve_bucket(feedback_root, family)
    target_pool_bucket = _scope_bucket(family_bucket, "target_pool_feedback", target_pool_id)
    holding_bucket_bucket = _scope_bucket(
        family_bucket,
        "holding_bucket_feedback",
        holding_bucket,
    )
    generator_bucket = _scope_bucket(family_bucket, "generator_mode_feedback", generator_mode)
    scopes = (
        (family_bucket, 1.0),
        (target_pool_bucket, 0.8),
        (holding_bucket_bucket, 0.72),
        (generator_bucket, 0.65),
    )
    family_control = _derive_scope_control(family_bucket, scope_name="family")
    target_pool_control = _derive_scope_control(target_pool_bucket, scope_name="target_pool")
    holding_bucket_control = _derive_scope_control(
        holding_bucket_bucket,
        scope_name="holding_bucket",
    )
    generator_mode_control = _derive_scope_control(generator_bucket, scope_name="generator_mode")
    legacy_scope_controls = (
        family_control,
        target_pool_control,
        holding_bucket_control,
        generator_mode_control,
    )
    skill_family_control = _derive_skill_scope_control(family_bucket, scope_name="family")
    skill_target_pool_control = _derive_skill_scope_control(
        target_pool_bucket,
        scope_name="target_pool",
    )
    skill_holding_bucket_control = _derive_skill_scope_control(
        holding_bucket_bucket,
        scope_name="holding_bucket",
    )
    skill_generator_mode_control = _derive_skill_scope_control(
        generator_bucket,
        scope_name="generator_mode",
    )
    skill_scope_controls = (
        skill_family_control,
        skill_target_pool_control,
        skill_holding_bucket_control,
        skill_generator_mode_control,
    )
    resolved: dict[str, Any] = {
        "family": normalize_text(family) or "unknown",
        "target_pool_id": str(target_pool_id or "").strip() or None,
        "holding_bucket": normalize_text(holding_bucket) or None,
        "generator_mode": normalize_text(generator_mode) or None,
        "family_feedback_available": bool(family_bucket),
        "target_pool_feedback_available": bool(target_pool_bucket),
        "holding_bucket_feedback_available": bool(holding_bucket_bucket),
        "generator_mode_feedback_available": bool(generator_bucket),
    }
    defaults = {
        "ema_submit_count": 0.0,
        "paper_hit_ratio": 0.5,
        "paper_skill_lcb": 0.0,
        "paper_recent_skill_lcb": 0.0,
        "paper_stability_gap": 0.0,
        "paper_coverage_ratio": 1.0,
        "execution_conversion_efficiency": 0.0,
        "runtime_alert_pressure": 0.0,
        "realized_turnover": 0.0,
        "capacity_crowding": 0.0,
        "zero_signal_ratio": 0.0,
        "low_signal_ratio": 0.0,
        "forward_window_coverage_ratio": 1.0,
        "promotion_ready_ratio": 1.0,
        "promotion_review_coverage_ratio": 1.0,
        "evidence_debt_ratio": 0.0,
        "gate_failure_rate": 0.0,
        "trace_completeness_ratio": 1.0,
        "admission_quality_objective": 0.0,
        "high_precision_objective": 0.0,
        "raw_validation_a_rate": 0.0,
        "raw_validation_b_rate": 0.0,
        "raw_validation_c_rate": 0.0,
        "raw_validation_d_rate": 0.0,
        "raw_validation_total_score_mean": 0.0,
        "strict_incubation_ready_rate": 0.0,
        "live_candidate_ready_rate": 0.0,
    }
    for metric in FEEDBACK_METRIC_KEYS:
        weighted_total = 0.0
        total_weight = 0.0
        for bucket, weight in scopes:
            value = _metric_value(bucket, metric)
            if value is None:
                continue
            weighted_total += value * weight
            total_weight += weight
        resolved[metric] = round(weighted_total / total_weight, 4) if total_weight else defaults[metric]
    execution_conversion_efficiency_available = any(
        _metric_present(bucket, "execution_conversion_efficiency") for bucket, _weight in scopes
    )
    resolved["execution_conversion_efficiency_available"] = execution_conversion_efficiency_available
    legacy_budget_multiplier = compute_budget_multiplier(resolved)
    legacy_priority_adjustment = compute_priority_adjustment(resolved)
    legacy_failure_penalty_adjustment = compute_failure_penalty_adjustment(resolved)
    skill_budget_multiplier = compute_skill_budget_multiplier(resolved)
    skill_priority_adjustment = compute_skill_priority_adjustment(resolved)
    skill_failure_penalty_adjustment = compute_skill_failure_penalty_adjustment(resolved)
    highest_control = max(legacy_scope_controls, key=lambda item: int(item.get("severity") or 0))
    skill_highest_control = max(skill_scope_controls, key=lambda item: int(item.get("severity") or 0))
    control_reasons: list[str] = []
    for scope_control in legacy_scope_controls:
        for reason in list(scope_control.get("reasons") or []):
            if reason not in control_reasons:
                control_reasons.append(reason)
    skill_control_reasons: list[str] = []
    for scope_control in skill_scope_controls:
        for reason in list(scope_control.get("reasons") or []):
            if reason not in skill_control_reasons:
                skill_control_reasons.append(reason)
    legacy_control_mode = highest_control.get("mode") or "normal"
    skill_control_mode = skill_highest_control.get("mode") or "normal"
    dual_axis_action = _classify_dual_axis_budget_action(resolved)
    if bool(dual_axis_action.get("applied")):
        budget_floor = dual_axis_action.get("budget_multiplier_floor")
        budget_cap = dual_axis_action.get("budget_multiplier_cap")
        priority_delta = safe_float(dual_axis_action.get("priority_adjustment_delta"), 0.0)
        failure_penalty_delta = safe_float(
            dual_axis_action.get("failure_penalty_delta"),
            0.0,
        )
        if budget_floor is not None:
            legacy_budget_multiplier = max(legacy_budget_multiplier, float(budget_floor))
            skill_budget_multiplier = max(skill_budget_multiplier, float(budget_floor))
        if budget_cap is not None:
            legacy_budget_multiplier = min(legacy_budget_multiplier, float(budget_cap))
            skill_budget_multiplier = min(skill_budget_multiplier, float(budget_cap))
        legacy_priority_adjustment += priority_delta
        skill_priority_adjustment += priority_delta
        legacy_failure_penalty_adjustment += failure_penalty_delta
        skill_failure_penalty_adjustment += failure_penalty_delta
        control_floor = dual_axis_action.get("control_mode_floor")
        legacy_control_mode = _stronger_control_mode(legacy_control_mode, control_floor)
        skill_control_mode = _stronger_control_mode(skill_control_mode, control_floor)
        reason_code = str(dual_axis_action.get("reason_code") or "").strip()
        if reason_code and reason_code not in control_reasons:
            control_reasons.append(reason_code)
        if reason_code and reason_code not in skill_control_reasons:
            skill_control_reasons.append(reason_code)
    (
        legacy_budget_multiplier,
        legacy_priority_adjustment,
        legacy_failure_penalty_adjustment,
    ) = _apply_control_mode_caps(
        control_mode=legacy_control_mode,
        budget_multiplier=legacy_budget_multiplier,
        priority_adjustment=legacy_priority_adjustment,
        failure_penalty_adjustment=legacy_failure_penalty_adjustment,
    )
    (
        skill_budget_multiplier,
        skill_priority_adjustment,
        skill_failure_penalty_adjustment,
    ) = _apply_control_mode_caps(
        control_mode=skill_control_mode,
        budget_multiplier=skill_budget_multiplier,
        priority_adjustment=skill_priority_adjustment,
        failure_penalty_adjustment=skill_failure_penalty_adjustment,
    )
    resolved["family_control_mode"] = family_control.get("mode")
    resolved["target_pool_control_mode"] = target_pool_control.get("mode")
    resolved["holding_bucket_control_mode"] = holding_bucket_control.get("mode")
    resolved["generator_mode_control_mode"] = generator_mode_control.get("mode")
    resolved["legacy_family_control_mode"] = family_control.get("mode")
    resolved["legacy_target_pool_control_mode"] = target_pool_control.get("mode")
    resolved["legacy_holding_bucket_control_mode"] = holding_bucket_control.get("mode")
    resolved["legacy_generator_mode_control_mode"] = generator_mode_control.get("mode")
    resolved["skill_family_control_mode"] = skill_family_control.get("mode")
    resolved["skill_target_pool_control_mode"] = skill_target_pool_control.get("mode")
    resolved["skill_holding_bucket_control_mode"] = skill_holding_bucket_control.get("mode")
    resolved["skill_generator_mode_control_mode"] = skill_generator_mode_control.get("mode")
    resolved["legacy_control_mode"] = legacy_control_mode
    resolved["skill_control_mode"] = skill_control_mode
    resolved["control_mode"] = legacy_control_mode
    resolved["effective_feedback_signal"] = (
        "prediction_execution_dual_axis"
        if bool(dual_axis_action.get("applied"))
        else "legacy_paper_hit_ratio"
    )
    resolved["cooldown_active"] = bool(
        CONTROL_MODE_SEVERITY.get(legacy_control_mode, 0) >= 1
    )
    resolved["suppressed"] = bool(CONTROL_MODE_SEVERITY.get(legacy_control_mode, 0) >= 2)
    resolved["family_freeze_active"] = bool(family_control.get("freeze_active"))
    resolved["target_pool_freeze_active"] = bool(target_pool_control.get("freeze_active"))
    resolved["holding_bucket_freeze_active"] = bool(holding_bucket_control.get("freeze_active"))
    resolved["generator_mode_freeze_active"] = bool(generator_mode_control.get("freeze_active"))
    resolved["legacy_cooldown_active"] = bool(
        CONTROL_MODE_SEVERITY.get(legacy_control_mode, 0) >= 1
    )
    resolved["legacy_suppressed"] = bool(
        CONTROL_MODE_SEVERITY.get(legacy_control_mode, 0) >= 2
    )
    resolved["legacy_family_freeze_active"] = bool(family_control.get("freeze_active"))
    resolved["legacy_target_pool_freeze_active"] = bool(target_pool_control.get("freeze_active"))
    resolved["legacy_holding_bucket_freeze_active"] = bool(holding_bucket_control.get("freeze_active"))
    resolved["legacy_generator_mode_freeze_active"] = bool(generator_mode_control.get("freeze_active"))
    resolved["skill_cooldown_active"] = bool(
        CONTROL_MODE_SEVERITY.get(skill_control_mode, 0) >= 1
    )
    resolved["skill_suppressed"] = bool(
        CONTROL_MODE_SEVERITY.get(skill_control_mode, 0) >= 2
    )
    resolved["skill_family_freeze_active"] = bool(skill_family_control.get("freeze_active"))
    resolved["skill_target_pool_freeze_active"] = bool(skill_target_pool_control.get("freeze_active"))
    resolved["skill_holding_bucket_freeze_active"] = bool(
        skill_holding_bucket_control.get("freeze_active")
    )
    resolved["skill_generator_mode_freeze_active"] = bool(
        skill_generator_mode_control.get("freeze_active")
    )
    resolved["control_reasons"] = control_reasons
    resolved["legacy_control_reasons"] = control_reasons
    resolved["skill_control_reasons"] = skill_control_reasons
    resolved["budget_action_applied"] = bool(dual_axis_action.get("applied"))
    resolved["budget_feedback_action"] = dual_axis_action.get("action")
    resolved["prediction_axis"] = dual_axis_action.get("prediction_axis")
    resolved["execution_axis"] = dual_axis_action.get("execution_axis")
    resolved["retain_family"] = bool(dual_axis_action.get("retain_family"))
    resolved["reduce_budget"] = bool(dual_axis_action.get("reduce_budget"))
    resolved["execution_optimization_queue"] = bool(
        dual_axis_action.get("execution_optimization_queue")
    )
    resolved["small_budget_observe"] = bool(dual_axis_action.get("small_budget_observe"))
    resolved["prioritize_scale"] = bool(dual_axis_action.get("prioritize_scale"))
    resolved["cool_or_freeze"] = bool(dual_axis_action.get("cool_or_freeze"))
    resolved["no_expansion"] = bool(dual_axis_action.get("no_expansion"))
    resolved["budget_action_control_mode_floor"] = dual_axis_action.get("control_mode_floor")
    resolved["budget_multiplier"] = legacy_budget_multiplier
    resolved["priority_adjustment"] = legacy_priority_adjustment
    resolved["failure_penalty_adjustment"] = legacy_failure_penalty_adjustment
    resolved["legacy_budget_multiplier"] = legacy_budget_multiplier
    resolved["legacy_priority_adjustment"] = legacy_priority_adjustment
    resolved["legacy_failure_penalty_adjustment"] = legacy_failure_penalty_adjustment
    resolved["skill_budget_multiplier"] = skill_budget_multiplier
    resolved["skill_priority_adjustment"] = skill_priority_adjustment
    resolved["skill_failure_penalty_adjustment"] = skill_failure_penalty_adjustment
    resolved["promotion_review_count"] = max(
        _safe_int(family_bucket.get("promotion_review_count")),
        _safe_int(target_pool_bucket.get("promotion_review_count")),
        _safe_int(holding_bucket_bucket.get("promotion_review_count")),
        _safe_int(generator_bucket.get("promotion_review_count")),
    )
    resolved["promotion_review_status"] = (
        normalize_text(generator_bucket.get("promotion_review_status"))
        or normalize_text(holding_bucket_bucket.get("promotion_review_status"))
        or normalize_text(target_pool_bucket.get("promotion_review_status"))
        or normalize_text(family_bucket.get("promotion_review_status"))
        or None
    )
    resolved["promotion_review_recommendation"] = (
        normalize_text(generator_bucket.get("promotion_review_recommendation"))
        or normalize_text(holding_bucket_bucket.get("promotion_review_recommendation"))
        or normalize_text(target_pool_bucket.get("promotion_review_recommendation"))
        or normalize_text(family_bucket.get("promotion_review_recommendation"))
        or None
    )
    resolved["promotion_review_score"] = round(
        max(
            safe_float(family_bucket.get("promotion_review_score"), 0.0),
            safe_float(target_pool_bucket.get("promotion_review_score"), 0.0),
            safe_float(holding_bucket_bucket.get("promotion_review_score"), 0.0),
            safe_float(generator_bucket.get("promotion_review_score"), 0.0),
        ),
        4,
    )
    high_precision_failure_reasons: list[str] = []
    if safe_float(resolved.get("realized_turnover"), 0.0) > 0.8:
        high_precision_failure_reasons.append("overtrading")
    if (
        safe_float(resolved.get("paper_recent_skill_lcb"), safe_float(resolved.get("paper_skill_lcb"), 0.0)) < 0.0
        and safe_float(resolved.get("paper_skill_lcb"), 0.0) > 0.0
    ):
        high_precision_failure_reasons.append("regime_mismatch")
    if (
        safe_float(resolved.get("execution_conversion_efficiency"), 0.0) < 0.12
        or safe_float(resolved.get("capacity_crowding"), 0.0) > 0.45
    ):
        high_precision_failure_reasons.append("cost_fragility")
    if (
        safe_float(resolved.get("admission_quality_objective"), 0.0) < 0.35
        and safe_float(resolved.get("trace_completeness_ratio"), 1.0) < 0.6
    ):
        high_precision_failure_reasons.append("weak_failure_mode")
    resolved["high_precision_failure_reasons"] = high_precision_failure_reasons
    return resolved
