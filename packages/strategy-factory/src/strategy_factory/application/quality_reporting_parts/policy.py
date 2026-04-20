

PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED = 2


def maybe_grant_provisional_incubation(
    strategy: Optional[dict],
    quality_gate: Optional[dict],
    *,
    validation_report: Optional[dict] = None,
    risk_report: Optional[dict] = None,
    backtest_metrics: Optional[dict] = None,
) -> dict:
    gate = normalize_quality_gate_result(quality_gate)
    if gate.get("passed"):
        return gate
    if not is_factory_provisional_candidate(strategy):
        return gate
    if not has_only_statistical_gate_failures(gate):
        return gate
    if not risk_report:
        return gate

    checks_passed, passed_names, failed_names = _count_statistical_checks_passed(gate)
    technical_validation_fallback = (
        checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED
        and is_provisional_technical_strategy(strategy)
        and has_degenerate_validation_statistics(validation_report)
    )
    if checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED and not technical_validation_fallback:
        logger.info(
            "Provisional incubation denied: only %d/%d statistical checks passed (%s failed)",
            checks_passed,
            checks_passed + len(failed_names),
            ", ".join(failed_names),
        )
        return gate

    metrics = dict(backtest_metrics or {})
    sharpe_ratio = safe_metric_value(metrics, "sharpe_ratio")
    max_drawdown = abs(safe_metric_value(metrics, "max_drawdown"))
    trades_count = safe_metric_value(metrics, "trade_count", "trades_count")
    if (
        sharpe_ratio < PROVISIONAL_PASS_THRESHOLDS["sharpe_min"]
        or max_drawdown > PROVISIONAL_PASS_THRESHOLDS["mdd_max"]
        or trades_count < PROVISIONAL_PASS_THRESHOLDS["trades_min"]
    ):
        return gate

    risk = dict(risk_report or {})
    var_percent = safe_metric_value(risk, "var_percent")
    cvar_percent = safe_metric_value(risk, "cvar_percent")
    stress_loss_percent = safe_metric_value(risk, "stress_loss_percent")
    if (
        var_percent > RISK_REPORT_THRESHOLDS["var_percent_max"]
        or cvar_percent > RISK_REPORT_THRESHOLDS["cvar_percent_max"]
        or stress_loss_percent <= RISK_REPORT_THRESHOLDS["stress_loss_percent_min"]
    ):
        return gate

    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    validation_grade = str(rating.get("grade") or "").strip().upper()

    warnings = list(gate.get("reasons") or [])
    if validation_grade == "D" and "validation_grade_d" not in warnings:
        warnings.append("validation_grade_d")
    if technical_validation_fallback:
        for extra_warning in (
            "validation_report_degenerate",
            "provisional_path:technical_validation_fallback",
        ):
            if extra_warning not in warnings:
                warnings.append(extra_warning)
    for failed_name in failed_names:
        tag = f"provisional_skip:{failed_name}"
        if tag not in warnings:
            warnings.append(tag)
    warnings = list(dict.fromkeys(warnings))
    return normalize_quality_gate_result({
        **gate,
        "passed": True,
        "passed_strict": False,
        "provisional_pass": True,
        "review_mode": "incubation_only",
        "reasons": [],
        "reason": "",
        "warnings": warnings,
        "original_reasons": gate.get("reasons") or [],
        "original_reason_codes": gate.get("reason_codes") or [],
        "statistical_checks_passed": checks_passed,
        "statistical_checks_passed_names": passed_names,
        "statistical_checks_failed_names": failed_names,
    })
