

def _evaluate_trade_profile(
    strategy: dict,
    profile: dict[str, Any],
    backtest_metrics: Optional[dict],
    risk_report: Optional[dict],
    *,
    admission_level: str = "incubation",
    attempt_adjustment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    metrics = dict(backtest_metrics or {})
    attempt_adjustment = resolve_attempt_adjustment(strategy, attempt_adjustment=attempt_adjustment)
    thresholds = _trade_gate_thresholds(
        strategy,
        profile,
        attempt_adjustment,
        admission_level=admission_level,
    )
    validation_focus = str(profile.get("validation_focus") or "target_plus_representative")
    is_event = str(profile.get("profile") or "") == "event_trade_validation" or validation_focus == "event_target_only"
    reasons: list[str] = []
    warnings: list[str] = []

    post_cost_sharpe = safe_metric_value(metrics, "post_cost_sharpe", "sharpe_ratio")
    total_return = safe_metric_value(metrics, "total_return", "target_layer_oos_return")
    target_layer_oos_return = safe_metric_value(metrics, "target_layer_oos_return", "total_return")
    target_layer_abnormal_return = safe_metric_value(metrics, "target_layer_abnormal_return", "target_layer_oos_return", "total_return")
    trade_count = safe_metric_value(metrics, "trade_count", "trades_count")
    max_drawdown = abs(safe_metric_value(metrics, "max_drawdown"))
    avg_holding_days = safe_metric_value(metrics, "avg_holding_days")
    turnover_proxy = safe_metric_value(metrics, "turnover_proxy")
    if turnover_proxy <= 0 and trade_count > 0:
        turnover_proxy = round(trade_count / max(avg_holding_days, 5.0), 4) if avg_holding_days > 0 else float(trade_count)
    event_window_hit_ratio = safe_metric_value(metrics, "event_window_hit_ratio")
    post_event_decay = safe_metric_value(metrics, "post_event_decay")
    trade_density = safe_metric_value(metrics, "trade_density")
    parameter_stability = safe_metric_value(metrics, "parameter_perturbation_trade_stability")
    primary_validation_layer = str(metrics.get("primary_validation_layer") or "").strip().lower()
    event_study_mode = str(metrics.get("event_study_mode") or "").strip().lower()
    event_sample_count = int(safe_metric_value(metrics, "event_sample_count"))
    event_anchor_count = int(safe_metric_value(metrics, "event_anchor_count"))
    control_group_count = int(safe_metric_value(metrics, "control_group_count"))
    event_sample_source = metrics.get("event_sample_source")
    event_time_anchors = list(metrics.get("event_time_anchors") or [])
    traceable_to_event_samples = bool(metrics.get("traceable_to_event_samples"))
    event_audit_incomplete = bool(metrics.get("event_audit_incomplete"))
    observe_softening_allowed = _can_soften_incubation_trade_metric(
        admission_level=admission_level,
        post_cost_sharpe=post_cost_sharpe,
        trade_count=trade_count,
        target_layer_abnormal_return=target_layer_abnormal_return,
        primary_validation_layer=primary_validation_layer,
        is_event=is_event,
    )

    if post_cost_sharpe < thresholds["post_cost_sharpe_min"]:
        reasons.append(f"post_cost_sharpe {post_cost_sharpe:.3f} < {thresholds['post_cost_sharpe_min']:.3f}")
    if trade_count < thresholds["trade_count_min"]:
        reasons.append(f"trade_count {trade_count:.0f} < {thresholds['trade_count_min']:.0f}")
    if total_return < thresholds["total_return_min"]:
        warnings.append(f"total_return {total_return:.3f} < {thresholds['total_return_min']:.3f}")
    if target_layer_oos_return < thresholds["target_layer_oos_return_min"]:
        target_layer_reason = (
            f"target_layer_oos_return {target_layer_oos_return:.3f} < {thresholds['target_layer_oos_return_min']:.3f}"
        )
        target_layer_shortfall = thresholds["target_layer_oos_return_min"] - target_layer_oos_return
        if (
            observe_softening_allowed
            and target_layer_shortfall <= _INCUBATION_OBSERVE_TARGET_LAYER_OOS_SOFT_BAND
        ):
            warnings.append(f"{target_layer_reason} [observe_band]")
        else:
            reasons.append(target_layer_reason)
    if max_drawdown > thresholds["max_drawdown_max"]:
        drawdown_reason = f"max_drawdown {max_drawdown:.3f} > {thresholds['max_drawdown_max']:.3f}"
        drawdown_excess = max_drawdown - thresholds["max_drawdown_max"]
        if observe_softening_allowed and drawdown_excess <= _INCUBATION_OBSERVE_MDD_SOFT_BAND:
            warnings.append(f"{drawdown_reason} [observe_band]")
        else:
            reasons.append(drawdown_reason)
    if thresholds["event_window_hit_ratio_min"] > 0:
        if event_window_hit_ratio <= 0 and admission_level == "incubation":
            warnings.append("event_window_hit_ratio_missing")
        elif event_window_hit_ratio < thresholds["event_window_hit_ratio_min"]:
            reasons.append(
                f"event_window_hit_ratio {event_window_hit_ratio:.3f} < {thresholds['event_window_hit_ratio_min']:.3f}"
            )
    if post_event_decay < thresholds["post_event_decay_min"]:
        warnings.append(
            f"post_event_decay {post_event_decay:.3f} < {thresholds['post_event_decay_min']:.3f}"
        )
    if trade_density > thresholds["trade_density_max"]:
        density_reason = f"trade_density {trade_density:.3f} > {thresholds['trade_density_max']:.3f}"
        if admission_level in {"incubation", "live"}:
            reasons.append(density_reason)
        else:
            warnings.append(density_reason)
    if parameter_stability and parameter_stability < thresholds["parameter_perturbation_trade_stability_min"]:
        stability_reason = (
            "parameter_perturbation_trade_stability "
            f"{parameter_stability:.3f} < {thresholds['parameter_perturbation_trade_stability_min']:.3f}"
        )
        if admission_level in {"incubation", "live"}:
            reasons.append(stability_reason)
        else:
            warnings.append(stability_reason)
    if is_event:
        if event_sample_count <= 0:
            reasons.append("event_sample_count_missing")
        if event_audit_incomplete:
            reasons.append("event_audit_incomplete")
        if event_study_mode and event_study_mode != "sample_driven":
            reasons.append(f"event_study_mode_{event_study_mode}")
        if str(event_sample_source or "").strip().lower() == "auto_context_minimal":
            reasons.append("event_sample_source_auto_context_minimal")
        if event_sample_count > 0 and not traceable_to_event_samples:
            reasons.append("event_sample_traceability_missing")

    risk = dict(risk_report or {})
    stress_loss_percent = safe_metric_value(risk, "stress_loss_percent")
    if stress_loss_percent and stress_loss_percent <= -25.0:
        reasons.append(f"stress_loss_percent {stress_loss_percent:.2f} <= -25.00")

    if admission_level == "live":
        mt_thresholds = _effective_live_multiple_testing_thresholds(strategy, profile, metrics)
        reasons.extend(_live_multiple_testing_reasons(metrics, mt_thresholds))

    return normalize_quality_gate_result(
        {
            "passed": len(reasons) == 0,
            "passed_strict": len(reasons) == 0,
            "profile": profile.get("profile"),
            "validation_focus": profile.get("validation_focus"),
            "primary_validation_layer": profile.get("primary_validation_layer"),
            "attempt_adjustment": attempt_adjustment,
            "thresholds": thresholds,
            "admission_level": admission_level,
            "reasons": reasons,
            "warnings": warnings,
            "trade_count": round(trade_count, 4),
            "avg_holding_days": round(avg_holding_days, 4),
            "turnover_proxy": round(turnover_proxy, 4),
            "post_cost_sharpe": round(post_cost_sharpe, 4),
            "target_layer_oos_return": round(target_layer_oos_return, 4),
            "target_layer_abnormal_return": round(target_layer_abnormal_return, 4),
            "event_window_hit_ratio": round(event_window_hit_ratio, 4),
            "post_event_decay": round(post_event_decay, 4),
            "trade_density": round(trade_density, 4),
            "parameter_perturbation_trade_stability": round(parameter_stability, 4),
            "event_study_mode": event_study_mode or None,
            "event_sample_count": int(event_sample_count),
            "event_anchor_count": int(event_anchor_count),
            "control_group_count": int(control_group_count),
            "event_sample_source": event_sample_source,
            "event_time_anchors": event_time_anchors[:8],
            "traceable_to_event_samples": bool(traceable_to_event_samples),
            "event_audit_incomplete": bool(event_audit_incomplete),
        }
    )


def _evaluate_trade_profile_for_admission(
    strategy: dict,
    profile: dict[str, Any],
    gate_payload: Optional[dict],
    risk_report: Optional[dict],
    *,
    admission_level: str,
    attempt_adjustment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    try:
        return _evaluate_trade_profile(
            strategy,
            profile,
            gate_payload,
            risk_report,
            admission_level=admission_level,
            attempt_adjustment=attempt_adjustment,
        )
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument" not in message:
            raise
        return _evaluate_trade_profile(strategy, profile, gate_payload, risk_report)


def _evaluate_statistical_admission(
    strategy: dict,
    profile: dict[str, Any],
    gate_payload: Optional[dict],
    *,
    admission_level: str = "incubation",
    attempt_adjustment: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(gate_payload or {})
    attempt_adjustment = resolve_attempt_adjustment(strategy, attempt_adjustment=attempt_adjustment)
    thresholds = _statistical_gate_thresholds(
        attempt_adjustment,
        admission_level=admission_level,
    )
    reasons: list[str] = []
    warnings: list[str] = []

    wf_ic_ir = safe_metric_value(payload, "wf_ic_ir")
    pkf_ic = safe_metric_value(payload, "pkf_ic")
    bootstrap_ci_lower = safe_metric_value(payload, "bootstrap_ci_lower")
    param_sensitivity = safe_metric_value(payload, "param_sensitivity")

    if wf_ic_ir < thresholds["walk_forward_ic_ir_min"]:
        reasons.append(f"walk_forward_ic_ir {wf_ic_ir:.3f} < {thresholds['walk_forward_ic_ir_min']:.3f}")
    if pkf_ic < thresholds["purged_kfold_ic_min"]:
        reasons.append(f"purged_kfold_ic {pkf_ic:.3f} < {thresholds['purged_kfold_ic_min']:.3f}")
    if bootstrap_ci_lower < thresholds["bootstrap_ci_lower_min"]:
        reasons.append(f"bootstrap_ci_lower {bootstrap_ci_lower:.3f} < {thresholds['bootstrap_ci_lower_min']:.3f}")
    if param_sensitivity > thresholds["param_sensitivity_max"]:
        reasons.append(f"param_sensitivity {param_sensitivity:.3f} > {thresholds['param_sensitivity_max']:.3f}")

    period_robustness = dict(payload.get("period_robustness") or {})
    first_ic = _first_float_value(period_robustness, "first_half_ic")
    second_ic = _first_float_value(period_robustness, "second_half_ic")
    if first_ic is not None and second_ic is not None:
        if first_ic < -0.02 or second_ic < -0.02:
            reasons.append(
                f"period_robustness {first_ic:.3f}/{second_ic:.3f} < -0.020"
            )
        elif (first_ic > 0.01 > second_ic) or (second_ic > 0.01 > first_ic):
            warnings.append(
                f"period_direction_reversal {first_ic:.3f}/{second_ic:.3f}"
            )

    if admission_level == "live":
        mt_thresholds = _multiple_testing_thresholds(admission_level)
        reasons.extend(_live_multiple_testing_reasons(payload, mt_thresholds))

    return normalize_quality_gate_result(
        {
            "passed": len(reasons) == 0,
            "passed_strict": len(reasons) == 0,
            "profile": profile.get("profile"),
            "validation_focus": profile.get("validation_focus"),
            "primary_validation_layer": profile.get("primary_validation_layer"),
            "attempt_adjustment": attempt_adjustment,
            "thresholds": thresholds,
            "admission_level": admission_level,
            "reasons": reasons,
            "warnings": warnings,
            "wf_ic_ir": round(wf_ic_ir, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(bootstrap_ci_lower, 4),
            "param_sensitivity": round(param_sensitivity, 4),
        }
    )


def _merge_text_items(*groups: Optional[list[str]]) -> list[str]:
    items: list[str] = []
    for group in groups:
        for item in group or []:
            text = str(item or "").strip()
            if text and text not in items:
                items.append(text)
    return items


def _with_gate_protocol(gate: dict[str, Any], protocol: str) -> dict[str, Any]:
    return normalize_quality_gate_result({**dict(gate or {}), "gate_protocol": protocol})


def _merge_trade_primary_gate(
    trade_gate: dict[str, Any],
    supplemental_statistical_gate: Optional[dict[str, Any]],
) -> dict[str, Any]:
    supplemental = normalize_quality_gate_result(supplemental_statistical_gate)
    trade_gate_payload = normalize_quality_gate_result(trade_gate)
    warnings = _merge_text_items(trade_gate.get("warnings"), supplemental.get("warnings"))
    if supplemental.get("reasons"):
        warnings = _merge_text_items(warnings, ["supplemental_statistical_gate_failed"])
    base_protocol = str(trade_gate_payload.get("gate_protocol") or "").strip().lower()
    profile_name = base_protocol.split(":", 1)[0] if ":" in base_protocol else base_protocol
    merged_protocol = (
        f"{profile_name}:trade_primary_with_supplemental_audit"
        if profile_name
        else "trade_primary_with_supplemental_audit"
    )
    merged = {
        **dict(trade_gate_payload or {}),
        **{
            key: value
            for key, value in supplemental.items()
            if key in _SUPPLEMENTAL_STATISTICAL_FIELDS
        },
        "warnings": warnings,
        "primary_gate_protocol": trade_gate_payload.get("gate_protocol"),
        "supplemental_gate_protocol": "supplemental_statistical_audit",
        "gate_protocol": merged_protocol,
        "supplemental_statistical_gate": {
            "passed": bool(supplemental.get("passed")),
            "reasons": list(supplemental.get("reasons") or []),
            "warnings": list(supplemental.get("warnings") or []),
        },
    }
    return normalize_quality_gate_result(merged)


def _committee_review_snapshot(strategy: dict) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    candidate_provenance = dict(_strategy_payload_value(payload, "candidate_provenance") or payload.get("candidate_provenance") or {})
    summary = dict(_strategy_payload_value(payload, "quality_summary") or payload.get("quality_summary") or {})
    review_report = dict(_strategy_payload_value(payload, "quality_report") or payload.get("quality_report") or payload.get("review_report") or {})
    return dict(
        payload.get("committee_review")
        or params.get("committee_review")
        or candidate_provenance.get("committee_review")
        or review_report.get("committee_review")
        or summary.get("committee_review")
        or {}
    )


def _derive_trade_aware_validation_grade(
    strategy: dict,
    gate: Optional[dict[str, Any]],
    *,
    raw_validation_grade: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    grade = str(raw_validation_grade or "").strip().upper() or None
    if grade != "D":
        return grade, None
    payload = dict(strategy or {})
    strategy_profile = dict(_strategy_payload_value(payload, "strategy_profile") or payload.get("strategy_profile") or {})
    candidate_provenance = dict(
        _strategy_payload_value(payload, "candidate_provenance") or payload.get("candidate_provenance") or {}
    )
    task_preference = dict(gate or {}).get("task_preference") if isinstance(gate, dict) else {}
    preferred_strategy_types = list(dict(task_preference or {}).get("preferred_strategy_types") or [])
    strategy_type = str(
        payload.get("strategy_type")
        or _strategy_payload_value(payload, "candidate_family")
        or candidate_provenance.get("candidate_family")
        or strategy_profile.get("strategy_family")
        or (preferred_strategy_types[0] if preferred_strategy_types else "")
        or ""
    ).strip().lower()
    if strategy_type not in _TRADE_AWARE_VALIDATION_GRADE_FAMILIES:
        return grade, None
    normalized_gate = dict(gate or {})
    profile_name = str(normalized_gate.get("profile") or "").strip().lower()
    validation_focus = str(
        normalized_gate.get("validation_focus")
        or dict(payload.get("params") or {}).get("validation_focus")
        or dict(dict(payload.get("params") or {}).get("validation_profile") or {}).get("validation_focus")
        or dict(payload.get("research_task") or {}).get("validation_focus")
        or ""
    ).strip().lower()
    if profile_name not in _TRADE_PRIMARY_PROFILES:
        return grade, None
    if validation_focus not in _TARGET_ONLY_VALIDATION_FOCUSES:
        return grade, None

    trade_density = safe_metric_value(normalized_gate, "trade_density")
    post_cost_sharpe = safe_metric_value(normalized_gate, "post_cost_sharpe")
    target_layer_oos_return = safe_metric_value(normalized_gate, "target_layer_oos_return")
    trade_stability = safe_metric_value(normalized_gate, "parameter_perturbation_trade_stability")
    dsr = safe_metric_value(normalized_gate, "deflated_sharpe_ratio")
    pbo = safe_metric_value(normalized_gate, "pbo")
    rc_pvalue = safe_metric_value(normalized_gate, "white_reality_check_pvalue")
    spa_pvalue = safe_metric_value(normalized_gate, "hansen_spa_pvalue")

    if trade_density <= 0 or trade_density > 1.2:
        return grade, None

    evidence_score = 0.0
    if trade_density <= 1.0:
        evidence_score += 2.0
    elif trade_density <= 1.2:
        evidence_score += 1.0
    if post_cost_sharpe >= 1.0:
        evidence_score += 2.0
    elif post_cost_sharpe >= 0.8:
        evidence_score += 1.0
    if target_layer_oos_return >= 0.18:
        evidence_score += 1.5
    elif target_layer_oos_return >= 0.08:
        evidence_score += 1.0
    if trade_stability >= 0.5:
        evidence_score += 1.0
    elif trade_stability >= 0.25:
        evidence_score += 0.5
    if dsr >= 0.1:
        evidence_score += 1.0
    elif dsr >= 0.03:
        evidence_score += 0.5
    if pbo <= 0.7:
        evidence_score += 1.0
    elif pbo <= 0.85:
        evidence_score += 0.5
    if rc_pvalue <= 0.2 and spa_pvalue <= 0.2:
        evidence_score += 0.5

    if evidence_score < 5.0:
        return grade, None
    return "C", f"trade_aware_validation_grade_upgrade:{strategy_type}:score={evidence_score:.2f}"


def _resolve_admission_review_context(
    strategy: dict,
    *,
    validation_report: Optional[dict] = None,
    gate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    quality_summary = dict(_strategy_payload_value(payload, "quality_summary") or payload.get("quality_summary") or {})
    review_report = dict(_strategy_payload_value(payload, "quality_report") or payload.get("quality_report") or payload.get("review_report") or {})
    committee_review = _committee_review_snapshot(payload)
    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    trade_quality_adjustment = dict(validation.get("trade_quality_adjustment") or {})
    validation_profile = dict(validation.get("validation_profile") or {})
    reported_validation_grade = str(
        rating.get("grade")
        or _strategy_payload_value(payload, "validation_grade")
        or quality_summary.get("validation_grade")
        or dict(review_report.get("summary") or {}).get("validation_grade")
        or ""
    ).strip().upper() or None
    baseline_validation_grade = str(
        rating.get("base_grade")
        or reported_validation_grade
        or ""
    ).strip().upper() or None
    raw_validation_grade = reported_validation_grade
    validation_grade, validation_grade_adjustment_reason = _derive_trade_aware_validation_grade(
        payload,
        gate,
        raw_validation_grade=raw_validation_grade,
    )
    if not validation_grade_adjustment_reason and bool(trade_quality_adjustment.get("applied")):
        validation_grade_adjustment_reason = str(
            trade_quality_adjustment.get("adjustment_reason") or ""
        ).strip() or None
    committee_decision = _normalize_text(
        committee_review.get("decision")
        or _strategy_payload_value(payload, "promotion_review_recommendation")
        or payload.get("promotion_review_recommendation")
    ) or None
    committee_final_score = committee_review.get("final_score")
    try:
        committee_final_score = None if committee_final_score is None else round(float(committee_final_score), 4)
    except Exception:
        committee_final_score = None
    promotion_review_score = (
        _strategy_payload_value(payload, "promotion_review_score")
        or quality_summary.get("promotion_review_score")
        or payload.get("promotion_review_score")
    )
    try:
        promotion_review_score = None if promotion_review_score is None else round(float(promotion_review_score), 4)
    except Exception:
        promotion_review_score = None
    accept_blockers = [
        str(item or "").strip()
        for item in list(committee_review.get("accept_blockers") or [])
        if str(item or "").strip()
    ]
    validation_focus = str(
        dict(gate or {}).get("validation_focus")
        or dict(params.get("validation_profile") or {}).get("validation_focus")
        or dict(params.get("research_task") or {}).get("validation_focus")
        or validation_profile.get("validation_focus")
        or ""
    ).strip().lower() or None
    return {
        "validation_grade": validation_grade,
        "raw_validation_grade": raw_validation_grade,
        "validation_baseline_grade": baseline_validation_grade,
        "effective_validation_grade": validation_grade,
        "validation_grade_adjustment_reason": validation_grade_adjustment_reason,
        "validation_focus": validation_focus,
        "validation_focus_layer": _resolve_validation_focus_layer(validation_focus or ""),
        "committee_decision": committee_decision,
        "committee_final_score": committee_final_score,
        "promotion_review_score": promotion_review_score,
        "accept_blockers": accept_blockers,
    }


def _review_stage_blockers(
    strategy: dict,
    *,
    admission_level: str,
    validation_report: Optional[dict] = None,
    gate: Optional[dict[str, Any]] = None,
) -> tuple[list[str], dict[str, Any]]:
    semantic_runtime_context = _resolve_semantic_runtime_context(strategy, gate=gate)
    if admission_level == "research":
        context = _resolve_admission_review_context(strategy, validation_report=validation_report, gate=gate)
        context.update(semantic_runtime_context)
        return [], context
    context = _resolve_admission_review_context(strategy, validation_report=validation_report, gate=gate)
    context.update(semantic_runtime_context)
    thresholds = _review_gate_thresholds(admission_level)
    blockers: list[str] = []
    validation_grade = str(context.get("validation_grade") or "").strip().upper()
    committee_decision = _normalize_text(context.get("committee_decision"))
    committee_final_score = context.get("committee_final_score")
    promotion_review_score = context.get("promotion_review_score")
    accept_blockers = list(context.get("accept_blockers") or [])

    if validation_grade in _NON_PROMOTABLE_VALIDATION_GRADES:
        blockers.append(f"validation_grade_{validation_grade.lower()}_not_allowed_for_{admission_level}")
    if committee_decision in _NON_PROMOTABLE_REVIEW_DECISIONS or committee_decision in _NON_PROMOTABLE_REVIEW_RECOMMENDATIONS:
        blockers.append(f"committee_review_{committee_decision}_not_allowed_for_{admission_level}")
    if committee_final_score is not None and committee_final_score < thresholds["committee_final_score_min"]:
        blockers.append(
            f"committee_final_score {committee_final_score:.3f} < {thresholds['committee_final_score_min']:.3f}"
        )
    if promotion_review_score is not None and promotion_review_score < thresholds["promotion_review_score_min"]:
        blockers.append(
            f"promotion_review_score {promotion_review_score:.3f} < {thresholds['promotion_review_score_min']:.3f}"
        )
    if accept_blockers:
        blockers.extend(f"committee_accept_blocker:{item}" for item in accept_blockers)
    semantic_contract_missing_fields = list(context.get("semantic_contract_missing_fields") or [])
    if semantic_contract_missing_fields:
        blockers.append("final_strategy_missing_semantic_contract")
    if not bool(context.get("semantic_runtime_match", True)):
        blockers.append("runtime_family_semantic_mismatch")
    if bool(context.get("proxy_runtime_used")):
        blockers.append("proxy_runtime_not_allowed_for_formal_incubation")
    if bool(context.get("default_profile_not_allowed")):
        blockers.append("default_profile_not_allowed_for_single_name_runtime")
    if bool(context.get("diagnostic_only")):
        blockers.append(f"diagnostic_only_not_allowed_for_{admission_level}")
    if str(context.get("execution_readiness_tier") or "").strip().lower() not in {"", "formal_runtime_ready"}:
        blockers.append(f"execution_readiness_tier:{context.get('execution_readiness_tier')}")
    return blockers, context
