

def _estimate_run_correction_metrics(
    attempt_adjustment: dict[str, Any],
    *,
    observed_score: float,
    score_series: Optional[np.ndarray] = None,
    family_returns: Optional[np.ndarray] = None,
    validation_runtime: Any = None,
) -> dict[str, Any]:
    attempt_count = max(1, int(attempt_adjustment.get("attempt_count") or 1))
    cohort_effective_trials = max(
        1.0,
        float(attempt_adjustment.get("cohort_effective_trials") or attempt_count or 1.0),
    )
    selection_ratio = float(attempt_adjustment.get("selection_ratio") or 0.0)
    penalty = float(attempt_adjustment.get("penalty") or 0.0)
    observed_score = float(observed_score or 0.0)
    batch_correlation_mode = str(attempt_adjustment.get("batch_correlation_mode") or "").strip().lower() or None
    batch_correlation_multiplier = float(attempt_adjustment.get("batch_correlation_multiplier") or 1.0)
    batch_correlation_sibling_count = int(attempt_adjustment.get("batch_correlation_sibling_count") or 0)

    arr = np.asarray(score_series if score_series is not None else [], dtype=float)
    arr = arr[np.isfinite(arr)]
    raw_sharpe_proxy = _observed_sharpe_proxy(arr, observed_score)
    sample_size = int(arr.size)
    dsr_hurdle = (
        float(np.sqrt(max(0.0, 2.0 * np.log(max(cohort_effective_trials, 1.0)) / max(sample_size, 1))))
        if sample_size
        else penalty
    )
    deflated_sharpe_proxy = float(raw_sharpe_proxy - dsr_hurdle)

    # PBO 的正式实现需要 CSCV / family-level ranking；当前先给出 run-level proxy，
    # 明确把 selection_ratio 与 deflated score 合并为过拟合风险信号。
    logistic_term = 1.0 / (1.0 + np.exp(max(-8.0, min(8.0, deflated_sharpe_proxy * 2.0))))
    pbo_proxy = float(min(0.99, max(0.01, (1.0 - min(selection_ratio, 1.0)) * logistic_term + penalty)))

    reality_check_pvalue_proxy = float(min(0.99, max(0.01, 0.05 + penalty)))
    spa_pvalue_proxy = float(min(0.99, max(0.01, 0.05 + penalty * 0.8)))
    mode = "attempt_only_proxy"

    if sample_size >= 24:
        rng = np.random.default_rng(42)
        centered = arr - float(np.mean(arr))
        observed_mean = float(np.mean(arr))
        observed_std = float(np.std(arr, ddof=1))
        observed_t = observed_mean / (observed_std / np.sqrt(sample_size)) if observed_std > 1e-9 else 0.0
        effective_trial_count = max(1, int(math.ceil(cohort_effective_trials)))
        bootstrap_rounds = min(96, max(32, effective_trial_count * 4))
        candidate_family = min(16, max(2, effective_trial_count))
        rc_samples: list[float] = []
        spa_samples: list[float] = []
        for _ in range(bootstrap_rounds):
            max_mean = -np.inf
            max_t = -np.inf
            for _ in range(candidate_family):
                sample = centered[rng.integers(0, sample_size, size=sample_size)]
                sample_mean = float(np.mean(sample))
                sample_std = float(np.std(sample, ddof=1))
                sample_t = sample_mean / (sample_std / np.sqrt(sample_size)) if sample_std > 1e-9 else 0.0
                if sample_mean > max_mean:
                    max_mean = sample_mean
                if max(0.0, sample_t) > max_t:
                    max_t = max(0.0, sample_t)
            rc_samples.append(max_mean)
            spa_samples.append(max_t)
        rc_arr = np.asarray(rc_samples, dtype=float)
        spa_arr = np.asarray(spa_samples, dtype=float)
        reality_check_pvalue_proxy = float(np.mean(rc_arr >= observed_mean))
        spa_pvalue_proxy = float(np.mean(spa_arr >= max(0.0, observed_t)))
        mode = "bootstrap_family_proxy"

    warnings: list[str] = []
    formal_fields: dict[str, Any] = {}
    runtime_dsr = getattr(validation_runtime, "deflated_sharpe_ratio", None) if validation_runtime else None
    runtime_pbo = getattr(validation_runtime, "probability_of_backtest_overfitting", None) if validation_runtime else None
    runtime_rc = getattr(validation_runtime, "white_reality_check", None) if validation_runtime else None
    runtime_spa = getattr(validation_runtime, "hansen_spa_test", None) if validation_runtime else None

    family_arr = np.asarray(family_returns if family_returns is not None else [], dtype=float)
    if family_arr.ndim == 1 and family_arr.size:
        family_arr = family_arr.reshape(-1, 1)
    if family_arr.ndim != 2:
        family_arr = np.zeros((0, 0), dtype=float)

    if callable(runtime_dsr) and sample_size >= 3:
        try:
            trial_sharpes = None
            if family_arr.size and family_arr.shape[1] >= 1:
                trial_sharpes = np.asarray(
                    [_observed_sharpe_proxy(family_arr[:, j], 0.0) for j in range(family_arr.shape[1])],
                    dtype=float,
                )
            dsr_result = runtime_dsr(
                arr,
                observed_sharpe=raw_sharpe_proxy,
                n_trials=max(int(math.ceil(cohort_effective_trials)), int(family_arr.shape[1] or 1)),
                sharpe_trials=trial_sharpes,
                periods_per_year=252.0,
            )
            formal_fields.update(
                {
                    "multiple_testing_mode": "formal_runtime",
                    "deflated_sharpe_ratio": round(float(dsr_result.get("dsr", 0.0) or 0.0), 4),
                    "deflated_sharpe_reference_sharpe": round(float(dsr_result.get("reference_sharpe", 0.0) or 0.0), 4),
                    "deflated_sharpe_effective_trials": round(float(dsr_result.get("effective_trials", 0.0) or 0.0), 4),
                }
            )
            formal_fields.setdefault("multiple_testing", {})["deflated_sharpe"] = dict(dsr_result or {})
        except Exception as exc:
            warnings.append(f"run_correction:formal_dsr_failed:{type(exc).__name__}")

    if callable(runtime_pbo) and callable(runtime_rc) and callable(runtime_spa) and family_arr.shape[0] >= 12 and family_arr.shape[1] >= 2:
        try:
            pbo_result = runtime_pbo(family_arr, n_splits=8, metric="sharpe", periods_per_year=252.0, seed=42)
            bootstrap_trials = max(1, int(math.ceil(cohort_effective_trials)))
            rc_result = runtime_rc(
                family_arr,
                n_bootstrap=min(512, max(200, bootstrap_trials * 8)),
                stationary_bootstrap_p=0.1,
                seed=42,
            )
            spa_result = runtime_spa(
                family_arr,
                n_bootstrap=min(512, max(200, bootstrap_trials * 8)),
                stationary_bootstrap_p=0.1,
                seed=42,
                center="consistent",
            )
            formal_fields.update(
                {
                    "multiple_testing_mode": "formal_runtime",
                    "pbo": round(float(pbo_result.get("pbo", 0.0) or 0.0), 4),
                    "white_reality_check_pvalue": round(float(rc_result.get("p_value", 0.0) or 0.0), 4),
                    "hansen_spa_pvalue": round(float(spa_result.get("p_value", 0.0) or 0.0), 4),
                }
            )
            mt_bucket = formal_fields.setdefault("multiple_testing", {})
            mt_bucket["pbo"] = dict(pbo_result or {})
            mt_bucket["white_reality_check"] = dict(rc_result or {})
            mt_bucket["hansen_spa"] = dict(spa_result or {})
        except Exception as exc:
            warnings.append(f"run_correction:formal_family_tests_failed:{type(exc).__name__}")

    if deflated_sharpe_proxy < 0:
        warnings.append("run_correction:deflated_sharpe_proxy_negative")
    if pbo_proxy > 0.55:
        warnings.append("run_correction:pbo_proxy_high")
    if reality_check_pvalue_proxy > 0.2:
        warnings.append("run_correction:reality_check_pvalue_proxy_weak")
    if spa_pvalue_proxy > 0.2:
        warnings.append("run_correction:spa_pvalue_proxy_weak")

    return {
        "run_correction_mode": mode,
        "raw_sharpe_proxy": round(raw_sharpe_proxy, 4),
        "deflated_sharpe_proxy": round(deflated_sharpe_proxy, 4),
        "pbo_proxy": round(pbo_proxy, 4),
        "reality_check_pvalue_proxy": round(reality_check_pvalue_proxy, 4),
        "spa_pvalue_proxy": round(spa_pvalue_proxy, 4),
        "cohort_effective_trials": round(cohort_effective_trials, 4),
        "batch_correlation_mode": batch_correlation_mode,
        "batch_correlation_multiplier": round(batch_correlation_multiplier, 4),
        "batch_correlation_sibling_count": batch_correlation_sibling_count,
        **formal_fields,
        "warnings": warnings,
    }


def _trade_gate_thresholds(
    strategy: dict,
    profile: dict[str, Any],
    attempt_adjustment: dict[str, Any],
    *,
    admission_level: str = "incubation",
) -> dict[str, float]:
    penalty = float(attempt_adjustment.get("penalty") or 0.0)
    validation_focus = str(profile.get("validation_focus") or "target_plus_representative")
    is_event = str(profile.get("profile") or "") == "event_trade_validation" or validation_focus == "event_target_only"
    trade_profiles = dict(_admission_threshold_bundle(admission_level).get("trade_profiles") or TRADE_GATE_PROFILE_THRESHOLDS)
    base = dict(trade_profiles.get("event_trade_validation" if is_event else "default") or TRADE_GATE_PROFILE_THRESHOLDS["default"])
    if admission_level == "live":
        family = _target_only_live_trade_family(strategy, profile)
        if family == "quality_factor":
            base["trade_count_min"] = min(float(base.get("trade_count_min", 8.0)), 4.0)
        elif family in {"ma_cross", "momentum"}:
            base["trade_count_min"] = min(float(base.get("trade_count_min", 8.0)), 6.0)
    return {
        "post_cost_sharpe_min": float(base.get("post_cost_sharpe_min", 0.10)) + penalty,
        "trade_count_min": float(base.get("trade_count_min", 4.0)),
        "total_return_min": float(base.get("total_return_min", -0.02)),
        "target_layer_oos_return_min": float(base.get("target_layer_oos_return_min", -0.01)),
        "max_drawdown_max": float(base.get("max_drawdown_max", 0.45)),
        "event_window_hit_ratio_min": float(base.get("event_window_hit_ratio_min", 0.0)),
        "post_event_decay_min": float(base.get("post_event_decay_min", -1.0)),
        "trade_density_max": float(base.get("trade_density_max", 1.2)),
        "parameter_perturbation_trade_stability_min": float(
            base.get("parameter_perturbation_trade_stability_min", 0.25)
        ),
    }


def _has_trade_validation_audit(backtest_metrics: Optional[dict]) -> bool:
    metrics = _materialize_backtest_metrics_contract(backtest_metrics)
    required_markers = {
        "post_cost_sharpe",
        "target_layer_oos_return",
        "target_layer_abnormal_return",
        "event_window_hit_ratio",
        "post_event_decay",
        "trade_density",
        "parameter_perturbation_trade_stability",
        "primary_validation_layer",
    }
    return any(key in metrics and metrics.get(key) is not None for key in required_markers)


def _trade_validation_audit_mode(
    *,
    incubation_budget_track: Optional[str] = None,
    submission_lane: Optional[str] = None,
) -> str:
    track = str(incubation_budget_track or "").strip().lower()
    lane = str(submission_lane or "").strip().lower()
    if lane == "live_ready_review" or track in {"formal_incubation", "live_ready_review"}:
        return "hard_fail"
    return "research_only_fallback"


def _can_soften_incubation_trade_metric(
    *,
    admission_level: str,
    post_cost_sharpe: float,
    trade_count: float,
    target_layer_abnormal_return: float,
    primary_validation_layer: str,
    is_event: bool,
) -> bool:
    if admission_level != "incubation":
        return False
    if trade_count < _INCUBATION_OBSERVE_TRADE_COUNT_FLOOR:
        return False
    if post_cost_sharpe < _INCUBATION_OBSERVE_POST_COST_SHARPE_FLOOR:
        return False
    if target_layer_abnormal_return > 0.0:
        return True
    if is_event:
        return False
    return primary_validation_layer in {"target", "combined"}


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
