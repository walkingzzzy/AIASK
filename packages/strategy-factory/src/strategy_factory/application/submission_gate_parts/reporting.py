

def _live_multiple_testing_reasons(payload: Optional[dict], thresholds: dict[str, float]) -> list[str]:
    normalized = dict(payload or {})
    reasons: list[str] = []
    multiple_testing_mode = str(normalized.get("multiple_testing_mode") or "").strip().lower()
    if multiple_testing_mode != "formal_runtime":
        reasons.append("formal_multiple_testing_mode_required_for_live_admission")

    deflated_sharpe = _first_float_value(normalized, "deflated_sharpe_ratio")
    pbo = _first_float_value(normalized, "pbo")
    white_rc = _first_float_value(normalized, "white_reality_check_pvalue")
    spa_pvalue = _first_float_value(normalized, "hansen_spa_pvalue")

    if deflated_sharpe is None:
        reasons.append("deflated_sharpe_missing_for_live_admission")
    elif deflated_sharpe < thresholds["deflated_sharpe_ratio_min"]:
        reasons.append(
            f"deflated_sharpe {deflated_sharpe:.3f} < {thresholds['deflated_sharpe_ratio_min']:.3f}"
        )
    if pbo is None:
        reasons.append("pbo_missing_for_live_admission")
    elif pbo > thresholds["pbo_max"]:
        reasons.append(f"pbo {pbo:.3f} > {thresholds['pbo_max']:.3f}")
    if white_rc is None:
        reasons.append("white_reality_check_missing_for_live_admission")
    elif white_rc > thresholds["white_reality_check_pvalue_max"]:
        reasons.append(
            "white_reality_check_pvalue "
            f"{white_rc:.3f} > {thresholds['white_reality_check_pvalue_max']:.3f}"
        )
    if spa_pvalue is None:
        reasons.append("hansen_spa_missing_for_live_admission")
    elif spa_pvalue > thresholds["hansen_spa_pvalue_max"]:
        reasons.append(
            f"hansen_spa_pvalue {spa_pvalue:.3f} > {thresholds['hansen_spa_pvalue_max']:.3f}"
        )
    return reasons


def _target_only_live_trade_family(
    strategy: dict,
    profile: dict[str, Any],
    payload: Optional[dict] = None,
) -> str | None:
    profile_name = _normalize_text(profile.get("profile"))
    validation_focus = _normalize_text(
        profile.get("validation_focus") or dict(payload or {}).get("validation_focus")
    )
    multiple_testing_cohort_mode = _normalize_text(dict(payload or {}).get("multiple_testing_cohort_mode"))
    if profile_name != "trade_rule_validation":
        return None
    if validation_focus not in _TARGET_ONLY_VALIDATION_FOCUSES:
        return None
    if multiple_testing_cohort_mode and multiple_testing_cohort_mode != "target_only":
        return None
    family = _normalize_text(
        _strategy_payload_value(strategy, "candidate_family")
        or _strategy_payload_value(strategy, "candidate_family_id")
        or strategy.get("strategy_type")
    )
    if family in _TRADE_AWARE_VALIDATION_GRADE_FAMILIES:
        return family
    return None


def _effective_live_multiple_testing_thresholds(
    strategy: dict,
    profile: dict[str, Any],
    payload: Optional[dict],
) -> dict[str, float]:
    thresholds = dict(_multiple_testing_thresholds("live"))
    family = _target_only_live_trade_family(strategy, profile, payload)
    if not family:
        return thresholds
    thresholds["deflated_sharpe_ratio_min"] = min(
        thresholds["deflated_sharpe_ratio_min"],
        0.0,
    )
    if family == "quality_factor":
        thresholds["pbo_max"] = max(thresholds["pbo_max"], 0.80)
        thresholds["white_reality_check_pvalue_max"] = max(
            thresholds["white_reality_check_pvalue_max"],
            0.20,
        )
        thresholds["hansen_spa_pvalue_max"] = max(
            thresholds["hansen_spa_pvalue_max"],
            0.20,
        )
    elif family == "ma_cross":
        thresholds["pbo_max"] = max(thresholds["pbo_max"], 0.75)
        thresholds["white_reality_check_pvalue_max"] = max(
            thresholds["white_reality_check_pvalue_max"],
            0.30,
        )
        thresholds["hansen_spa_pvalue_max"] = max(
            thresholds["hansen_spa_pvalue_max"],
            0.30,
        )
    elif family == "momentum":
        thresholds["pbo_max"] = max(thresholds["pbo_max"], 0.70)
        thresholds["white_reality_check_pvalue_max"] = max(
            thresholds["white_reality_check_pvalue_max"],
            0.25,
        )
        thresholds["hansen_spa_pvalue_max"] = max(
            thresholds["hansen_spa_pvalue_max"],
            0.25,
        )
    return thresholds


def _observed_sharpe_proxy(series: Optional[np.ndarray], fallback_score: float) -> float:
    arr = np.asarray(series if series is not None else [], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size >= 3:
        std = float(np.std(arr, ddof=1))
        if std > 1e-9:
            return float(np.mean(arr) / std * np.sqrt(252.0))
    return float(fallback_score or 0.0)


def _strategy_return_series_for_params(
    klass,
    params: dict[str, Any],
    close_panels: list[np.ndarray],
    *,
    min_len: int,
) -> Optional[np.ndarray]:
    series_list: list[np.ndarray] = []
    for closes in close_panels:
        window = np.asarray(closes[:min_len], dtype=float)
        if window.size < min_len:
            continue
        instance = klass()
        instance.set_parameters(params or {})
        signals = np.asarray(instance.generate_signals(window), dtype=float)
        if signals.size < min_len:
            continue
        aligned = signals[:min_len]
        forward_returns = np.zeros(min_len, dtype=float)
        valid_prev = np.maximum(window[:-1], 1e-12)
        forward_returns[:-1] = (window[1:] - window[:-1]) / valid_prev
        series_list.append((aligned * forward_returns).astype(float))
    if not series_list:
        return None
    return np.mean(np.column_stack(series_list), axis=1).astype(float)


def _build_strategy_family_returns(
    klass,
    strategy_params: dict[str, Any],
    close_panels: list[np.ndarray],
    *,
    min_len: int,
) -> Optional[np.ndarray]:
    if min_len < 24 or not close_panels:
        return None
    family_series: list[np.ndarray] = []

    base_series = _strategy_return_series_for_params(klass, strategy_params, close_panels, min_len=min_len)
    if base_series is None:
        return None
    family_series.append(base_series)

    for key, value in sorted((strategy_params or {}).items()):
        if not isinstance(value, (int, float)) or value == 0:
            continue
        for mult in (0.8, 1.2):
            varied_params = dict(strategy_params or {})
            varied_value = float(value) * mult
            if isinstance(value, int):
                varied_params[key] = max(1, int(round(varied_value)))
            else:
                varied_params[key] = float(varied_value)
            varied_series = _strategy_return_series_for_params(klass, varied_params, close_panels, min_len=min_len)
            if varied_series is None:
                continue
            if any(np.allclose(varied_series, existing, atol=1e-9, rtol=1e-6) for existing in family_series):
                continue
            family_series.append(varied_series)

    if len(family_series) < 2:
        return np.column_stack(family_series)
    return np.column_stack(family_series)


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
