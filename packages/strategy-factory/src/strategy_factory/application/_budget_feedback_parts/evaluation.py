

def _stronger_control_mode(*modes: Any) -> str:
    strongest = "normal"
    strongest_severity = CONTROL_MODE_SEVERITY["normal"]
    for mode in modes:
        token = _coerce_control_mode(mode)
        severity = CONTROL_MODE_SEVERITY.get(token, 0)
        if severity > strongest_severity:
            strongest = token
            strongest_severity = severity
    return strongest


def _promotion_review_score_blocks_budget(
    *,
    status: str,
    recommendation: str,
) -> bool:
    if status == "watch" or recommendation == "observe":
        return False
    return True


def _classify_dual_axis_budget_action(metrics: dict[str, Any]) -> dict[str, Any]:
    execution_conversion_efficiency_available = bool(
        metrics.get("execution_conversion_efficiency_available")
    )
    execution_conversion_efficiency = _clamp(
        safe_float(metrics.get("execution_conversion_efficiency"), 0.0),
        0.0,
        1.0,
    )
    paper_skill_lcb = _clamp(safe_float(metrics.get("paper_skill_lcb"), 0.0), -1.0, 1.0)
    if not execution_conversion_efficiency_available:
        return {
            "applied": False,
            "action": None,
            "prediction_axis": "unknown",
            "execution_axis": "unknown",
            "retain_family": False,
            "reduce_budget": False,
            "execution_optimization_queue": False,
            "small_budget_observe": False,
            "prioritize_scale": False,
            "cool_or_freeze": False,
            "no_expansion": False,
            "budget_multiplier_floor": None,
            "budget_multiplier_cap": None,
            "priority_adjustment_delta": 0.0,
            "failure_penalty_delta": 0.0,
            "control_mode_floor": None,
            "reason_code": None,
        }

    high_prediction = paper_skill_lcb > DUAL_AXIS_PREDICTION_SKILL_HIGH_THRESHOLD
    high_execution = (
        execution_conversion_efficiency >= DUAL_AXIS_EXECUTION_CONVERSION_HIGH_THRESHOLD
    )
    if high_prediction and high_execution:
        action = DUAL_AXIS_BUDGET_ACTION_PRIORITY_SCALE
        priority_adjustment_delta = 4.0
        budget_multiplier_floor = 1.15
        budget_multiplier_cap = None
        failure_penalty_delta = -0.02
        control_mode_floor = None
    elif high_prediction and not high_execution:
        action = DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET
        priority_adjustment_delta = -2.5
        budget_multiplier_floor = None
        budget_multiplier_cap = 0.78
        failure_penalty_delta = 0.03
        control_mode_floor = None
    elif not high_prediction and high_execution:
        action = DUAL_AXIS_BUDGET_ACTION_SMALL_BUDGET_OBSERVE
        priority_adjustment_delta = -5.0
        budget_multiplier_floor = None
        budget_multiplier_cap = 0.58
        failure_penalty_delta = 0.05
        control_mode_floor = None
    else:
        action = DUAL_AXIS_BUDGET_ACTION_COOL_OR_FREEZE
        priority_adjustment_delta = -10.0
        budget_multiplier_floor = None
        budget_multiplier_cap = 0.35
        failure_penalty_delta = 0.08
        control_mode_floor = (
            "freeze"
            if (
                paper_skill_lcb <= -0.03
                and execution_conversion_efficiency < DUAL_AXIS_EXECUTION_CONVERSION_FREEZE_THRESHOLD
            )
            else "cooldown"
        )

    return {
        "applied": True,
        "action": action,
        "prediction_axis": "high" if high_prediction else "low",
        "execution_axis": "high" if high_execution else "low",
        "retain_family": action == DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET,
        "reduce_budget": action
        in {
            DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET,
            DUAL_AXIS_BUDGET_ACTION_SMALL_BUDGET_OBSERVE,
            DUAL_AXIS_BUDGET_ACTION_COOL_OR_FREEZE,
        },
        "execution_optimization_queue": action
        == DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET,
        "small_budget_observe": action == DUAL_AXIS_BUDGET_ACTION_SMALL_BUDGET_OBSERVE,
        "prioritize_scale": action == DUAL_AXIS_BUDGET_ACTION_PRIORITY_SCALE,
        "cool_or_freeze": action == DUAL_AXIS_BUDGET_ACTION_COOL_OR_FREEZE,
        "no_expansion": action == DUAL_AXIS_BUDGET_ACTION_SMALL_BUDGET_OBSERVE,
        "budget_multiplier_floor": budget_multiplier_floor,
        "budget_multiplier_cap": budget_multiplier_cap,
        "priority_adjustment_delta": priority_adjustment_delta,
        "failure_penalty_delta": failure_penalty_delta,
        "control_mode_floor": control_mode_floor,
        "reason_code": (
            f"dual_axis_{action}"
            if action in DUAL_AXIS_BUDGET_ACTIONS
            else None
        ),
    }


def _dual_axis_feedback_summary(feedback_root: dict[str, Any]) -> dict[str, Any]:
    action_counts: dict[str, int] = {}
    execution_optimization_queue_count = 0
    small_budget_observe_count = 0
    prioritize_scale_count = 0
    cool_or_freeze_count = 0
    retain_family_reduce_budget_count = 0
    action_family_count = 0
    for family_name, raw_bucket in feedback_root.items():
        if not isinstance(raw_bucket, dict):
            continue
        metrics = resolve_feedback_metrics(feedback_root, family=str(family_name or ""))
        if not bool(metrics.get("budget_action_applied")):
            continue
        action_family_count += 1
        action = normalize_text(metrics.get("budget_feedback_action"))
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
        if bool(metrics.get("execution_optimization_queue")):
            execution_optimization_queue_count += 1
        if bool(metrics.get("small_budget_observe")):
            small_budget_observe_count += 1
        if bool(metrics.get("prioritize_scale")):
            prioritize_scale_count += 1
        if bool(metrics.get("cool_or_freeze")):
            cool_or_freeze_count += 1
        if action == DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET:
            retain_family_reduce_budget_count += 1
    return {
        "budget_action_counts": action_counts,
        "execution_optimization_queue_count": execution_optimization_queue_count,
        "small_budget_observe_count": small_budget_observe_count,
        "prioritize_scale_count": prioritize_scale_count,
        "cool_or_freeze_count": cool_or_freeze_count,
        "retain_family_reduce_budget_count": retain_family_reduce_budget_count,
        "dual_axis_action_family_count": action_family_count,
    }


def _resolve_bucket(feedback_root: dict[str, Any], family: str) -> dict[str, Any]:
    return dict(feedback_root.get(normalize_text(family)) or {})


def _scope_bucket(family_bucket: dict[str, Any], scope_name: str, scope_key: str | None) -> dict[str, Any]:
    if not scope_key:
        return {}
    raw_scope = family_bucket.get(scope_name)
    if not isinstance(raw_scope, dict):
        return {}
    return dict(raw_scope.get(normalize_text(scope_key)) or raw_scope.get(str(scope_key).strip()) or {})


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return int(default)


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    token = normalize_text(value)
    return token in {"1", "true", "yes", "active", "on", "cooldown", "suppress", "freeze"}


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


def _finalize_scope_control(
    *,
    scope_name: str,
    freeze_active: bool,
    suppressed: bool,
    cooldown_active: bool,
    reasons: list[str],
) -> dict[str, Any]:
    if freeze_active:
        mode = "freeze"
        severity = 3
    elif suppressed:
        mode = "suppress"
        severity = 2
    elif cooldown_active:
        mode = "cooldown"
        severity = 1
    else:
        mode = "normal"
        severity = 0

    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason not in deduped_reasons:
            deduped_reasons.append(reason)

    return {
        "scope": scope_name,
        "mode": mode,
        "severity": severity,
        "cooldown_active": severity >= 1,
        "suppressed": severity >= 2,
        "freeze_active": freeze_active,
        "reasons": deduped_reasons,
    }


def _derive_scope_control(bucket: dict[str, Any], *, scope_name: str) -> dict[str, Any]:
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

    paper_hit_ratio = max(0.0, min(safe_float(_metric_value(payload, "paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(_metric_value(payload, "runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(_metric_value(payload, "realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(_metric_value(payload, "capacity_crowding"), 0.0), 2.0))
    runtime_alert_count = _safe_int(payload.get("runtime_alert_count"))
    runtime_risk_event_count = _safe_int(payload.get("runtime_risk_event_count"))
    strategy_count = _safe_int(payload.get("strategy_count"))
    gate_failure_rate = max(0.0, min(safe_float(_metric_value(payload, "gate_failure_rate"), 0.0), 1.0))
    gate_3_input_count = max(
        _safe_int(payload.get("gate_3_input_count")),
        _safe_int(payload.get("gate_3_input")),
        _safe_int(payload.get("gate_3_input_count_ema")),
        strategy_count,
    )
    gate_3_failure_streak = _safe_int(payload.get("gate_3_failure_streak"))
    zero_signal_ratio = max(0.0, min(safe_float(_metric_value(payload, "zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(_metric_value(payload, "low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(_metric_value(payload, "forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(_metric_value(payload, "promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(_metric_value(payload, "promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(
        0.0,
        min(safe_float(_metric_value(payload, "evidence_debt_ratio"), 0.0), 1.0),
    )
    promotion_review_count = _safe_int(payload.get("promotion_review_count"))
    promotion_review_score = max(
        0.0,
        min(safe_float(payload.get("promotion_review_score"), 0.5), 1.0),
    )
    promotion_review_status = normalize_text(payload.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(payload.get("promotion_review_recommendation"))
    freeze_active = any(
        _truthy_flag(payload.get(key))
        for key in (
            "freeze",
            "freeze_active",
            "scope_freeze_active",
            "hard_freeze",
        )
    )
    suppressed = any(
        _truthy_flag(payload.get(key))
        for key in (
            "suppress",
            "suppress_active",
            "suppressed",
        )
    )
    cooldown_active = any(
        _truthy_flag(payload.get(key))
        for key in (
            "cooldown",
            "cooldown_active",
        )
    )
    reasons: list[str] = []

    if gate_3_input_count >= 3 and gate_failure_rate >= 0.95:
        suppressed = True
        reasons.append(f"{scope_name}_gate_failure_rate_suppress")
    elif gate_3_input_count >= 2 and gate_failure_rate >= 0.75:
        cooldown_active = True
        reasons.append(f"{scope_name}_gate_failure_rate_cooldown")
    if gate_3_input_count >= 8 and gate_failure_rate >= 0.98 and gate_3_failure_streak >= 3:
        freeze_active = True
        reasons.append(f"{scope_name}_gate_failure_rate_freeze")

    if runtime_alert_pressure >= 0.88:
        freeze_active = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_freeze")
    elif runtime_alert_pressure >= 0.72:
        suppressed = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_suppress")
    elif runtime_alert_pressure >= 0.55:
        cooldown_active = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_cooldown")

    if paper_hit_ratio <= 0.18:
        freeze_active = True
        reasons.append(f"{scope_name}_paper_hit_ratio_collapse")
    elif paper_hit_ratio <= 0.28:
        suppressed = True
        reasons.append(f"{scope_name}_paper_hit_ratio_suppress")
    elif paper_hit_ratio < 0.40:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_hit_ratio_cooldown")

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
        if _promotion_review_score_blocks_budget(
            status=promotion_review_status,
            recommendation=promotion_review_recommendation,
        ):
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
