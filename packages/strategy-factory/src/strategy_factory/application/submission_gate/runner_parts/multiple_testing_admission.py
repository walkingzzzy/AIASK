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
    missing_metrics: list[str] = []

    wf_ic_ir = _append_missing_statistical_metric(missing_metrics, payload, "wf_ic_ir", "wf_ic_ir")
    pkf_ic = _append_missing_statistical_metric(missing_metrics, payload, "pkf_ic", "pkf_ic")
    bootstrap_ci_lower = _append_missing_statistical_metric(
        missing_metrics,
        payload,
        "bootstrap_ci_lower",
        "bootstrap_ci_lower",
    )
    param_sensitivity = _append_missing_statistical_metric(
        missing_metrics,
        payload,
        "param_sensitivity",
        "param_sensitivity",
    )

    if missing_metrics:
        reasons.append("insufficient_statistical_evidence")
        reasons.append(f"missing_statistical_metrics:{','.join(missing_metrics)}")
        # P1: also emit structured reason_codes per metric so the topN
        # aggregator and dashboard can group failures by metric. The
        # aggregate ``missing_statistical_metrics:..`` line stays for
        # backward compatibility.
        for metric_name in missing_metrics:
            reasons.append(f"missing_{metric_name}")

    # P1 (R5.1, R5.3): for metrics that are present-and-real but below
    # threshold, emit a structured ``weak_<metric>`` code in addition to
    # the human-readable threshold message. ``_classify_gate3_metric_value``
    # already filtered out the placeholder 0.0 case (see audit P1-prep).
    if wf_ic_ir is not None and _classify_gate3_metric_value(wf_ic_ir) == "present_real" \
            and wf_ic_ir < thresholds["walk_forward_ic_ir_min"]:
        reasons.append(f"walk_forward_ic_ir {wf_ic_ir:.3f} < {thresholds['walk_forward_ic_ir_min']:.3f}")
        reasons.append("weak_wf_ic_ir")
    if pkf_ic is not None and _classify_gate3_metric_value(pkf_ic) == "present_real" \
            and pkf_ic < thresholds["purged_kfold_ic_min"]:
        reasons.append(f"purged_kfold_ic {pkf_ic:.3f} < {thresholds['purged_kfold_ic_min']:.3f}")
        reasons.append("weak_pkf_ic")
    if bootstrap_ci_lower is not None and _classify_gate3_metric_value(bootstrap_ci_lower) == "present_real" \
            and bootstrap_ci_lower < thresholds["bootstrap_ci_lower_min"]:
        reasons.append(f"bootstrap_ci_lower {bootstrap_ci_lower:.3f} < {thresholds['bootstrap_ci_lower_min']:.3f}")
        reasons.append("weak_bootstrap_ci_lower")
    if param_sensitivity is not None and _classify_gate3_metric_value(param_sensitivity) == "present_real" \
            and param_sensitivity > thresholds["param_sensitivity_max"]:
        reasons.append(f"param_sensitivity {param_sensitivity:.3f} > {thresholds['param_sensitivity_max']:.3f}")
        reasons.append("weak_param_sensitivity")

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

    # P1 (R5): per-metric breakdown for gate_3_evaluation. Captures the
    # value, status (missing / weak / pass), reason_code, threshold, and
    # whether the metric was derived (P1 stop-gap) vs computed (P4 final).
    gate_3_evaluation = _build_gate3_evaluation(
        wf_ic_ir=wf_ic_ir,
        pkf_ic=pkf_ic,
        bootstrap_ci_lower=bootstrap_ci_lower,
        param_sensitivity=param_sensitivity,
        thresholds=thresholds,
        payload=payload,
    )

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
            "wf_ic_ir": round(wf_ic_ir, 4) if wf_ic_ir is not None else None,
            "pkf_ic": round(pkf_ic, 4) if pkf_ic is not None else None,
            "bootstrap_ci_lower": round(bootstrap_ci_lower, 4) if bootstrap_ci_lower is not None else None,
            "param_sensitivity": round(param_sensitivity, 4) if param_sensitivity is not None else None,
            "missing_statistical_metrics": list(missing_metrics),
            "statistical_metric_missing_counts": {key: 1 for key in missing_metrics},
            "gate_3_evaluation": gate_3_evaluation,
        }
    )


def _build_gate3_evaluation(
    *,
    wf_ic_ir: float | None,
    pkf_ic: float | None,
    bootstrap_ci_lower: float | None,
    param_sensitivity: float | None,
    thresholds: dict[str, Any],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build per-metric Gate-3 evaluation rows (R5 / Property 4 / Property 9).

    Each row carries:
        - ``metric``: stable name (matches reason_code suffix)
        - ``value``: rounded numeric or None
        - ``status``: missing / weak / pass
        - ``reason_code``: ``missing_<m>``, ``weak_<m>``, or ``pass``
        - ``threshold``: numeric threshold used (None for raw signals)
        - ``derived``: True when the value is a stop-gap derivation
          rather than a real upstream computation (P1 → P4 transition)
        - ``comparator``: ">" or "<" — direction of the threshold check
    """
    audit = dict(payload.get("metric_source_audit") or {})

    def _entry(
        metric: str,
        value: float | None,
        threshold: float | None,
        comparator: str,
    ) -> dict[str, Any]:
        status = _classify_gate3_metric_value(value)
        if status == "missing":
            return {
                "metric": metric,
                "value": None,
                "status": "missing",
                "reason_code": f"missing_{metric}",
                "threshold": threshold,
                "comparator": comparator,
                "derived": _is_metric_derived(metric, audit),
            }
        # present_real
        v = float(value) if value is not None else None
        if threshold is not None and v is not None:
            if comparator == ">=":
                weak = v < threshold
            elif comparator == "<=":
                weak = v > threshold
            else:
                weak = False
        else:
            weak = False
        return {
            "metric": metric,
            "value": round(v, 4) if v is not None else None,
            "status": "weak" if weak else "pass",
            "reason_code": f"weak_{metric}" if weak else "pass",
            "threshold": threshold,
            "comparator": comparator,
            "derived": _is_metric_derived(metric, audit),
        }

    return [
        _entry("wf_ic_ir", wf_ic_ir,
               thresholds.get("walk_forward_ic_ir_min"), ">="),
        _entry("pkf_ic", pkf_ic,
               thresholds.get("purged_kfold_ic_min"), ">="),
        _entry("bootstrap_ci_lower", bootstrap_ci_lower,
               thresholds.get("bootstrap_ci_lower_min"), ">="),
        _entry("param_sensitivity", param_sensitivity,
               thresholds.get("param_sensitivity_max"), "<="),
    ]


def _is_metric_derived(metric: str, audit: dict[str, Any]) -> bool:
    """Return True when the metric value came from a stop-gap derivation
    (e.g., ``param_sensitivity`` derived from
    ``parameter_perturbation_trade_stability_inverse``).

    The audit dict is populated by ``_assign_statistical_metric`` in
    trade_profile.py with the source path string. Anything containing
    'inverse' or '_derived' marks a stop-gap path. Real upstream paths
    like ``validation_report.walk_forward`` return False.
    """
    src = str(audit.get(metric) or "").lower()
    if not src:
        return False
    if "inverse" in src or "derived" in src or "stop_gap" in src:
        return True
    return False


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
