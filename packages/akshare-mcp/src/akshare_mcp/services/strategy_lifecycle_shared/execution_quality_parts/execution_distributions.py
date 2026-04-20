
from .common import (
    _quality_report_field,
    _safe_boolish,
    _safe_float,
    _safe_int,
    _string,
)


def _build_execution_quality_snapshot(execution_quality: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(execution_quality or {})
    audit = dict(payload.get("audit") or {})
    execution_audit_gate_status = _string(
        payload.get("execution_audit_gate_status") or audit.get("execution_audit_gate_status")
    ) or "missing"
    evidence_gap_codes = list(payload.get("evidence_gap_codes") or [])
    if execution_audit_gate_status in {"missing", "bootstrap_pending", "insufficient_samples", "insufficient_evidence"}:
        evidence_gap_codes.append(f"execution_audit_gate:{execution_audit_gate_status}")
    execution_quality_label = _string(payload.get("execution_quality_label")).lower()
    if execution_audit_gate_status == "passed":
        status = "strong"
    elif execution_quality_label in {"strong", "candidate", "weak", "insufficient_evidence"}:
        status = execution_quality_label
    elif execution_audit_gate_status == "failed_metrics":
        status = "weak"
    else:
        status = "insufficient_evidence"
    return {
        "contract_version": "strategy_factory.execution_quality_snapshot.v2",
        "status": status,
        "evidence_status": _string(payload.get("evidence_status")) or None,
        "evidence_gap_codes": _unique_tokens(evidence_gap_codes, limit=16),
        "execution_audit_gate_status": execution_audit_gate_status,
        "realized_trade_count": _safe_int(payload.get("realized_trade_count") or audit.get("realized_trade_count")),
        "order_count": _safe_int(payload.get("order_count")),
        "trade_count": _safe_int(payload.get("trade_count")),
        "mapped_position_count": _safe_int(payload.get("mapped_position_count") or audit.get("mapped_position_count")),
        "incomplete_position_count": _safe_int(
            payload.get("incomplete_position_count") or audit.get("incomplete_position_count")
        ),
        "realized_pnl_total": _safe_float(payload.get("realized_pnl_total") or audit.get("realized_pnl_total")),
        "fill_rate": _safe_float(payload.get("fill_rate")),
        "round_trip_close_rate": _safe_float(payload.get("round_trip_close_rate")),
        "trade_expectancy": _safe_float(payload.get("trade_expectancy")),
        "pnl_conversion_efficiency": _safe_float(payload.get("pnl_conversion_efficiency")),
        "execution_conversion_efficiency": _safe_float(payload.get("execution_conversion_efficiency")),
        "realized_slippage_vs_model": _safe_float(payload.get("realized_slippage_vs_model"))
        if payload.get("realized_slippage_vs_model") is not None
        else None,
        "realized_vs_modeled_cost_gap": _safe_float(
            payload.get("realized_vs_modeled_cost_gap")
            if payload.get("realized_vs_modeled_cost_gap") is not None
            else payload.get("realized_slippage_vs_model")
        ),
        "trade_density": _safe_float(payload.get("trade_density")),
        "entry_quality": _safe_float(payload.get("entry_quality") or payload.get("fill_rate")),
        "exit_discipline": _safe_float(
            payload.get("exit_discipline") or payload.get("round_trip_close_rate")
        ),
        "regime_mismatch_events": list(payload.get("regime_mismatch_events") or []),
        "missed_trade_ratio": _safe_float(payload.get("missed_trade_ratio"))
        if payload.get("missed_trade_ratio") is not None
        else None,
        "hard_gate_ready": bool(payload.get("execution_hard_gate_passed")),
    }


def _resolve_high_precision_overview_context(
    strategy: dict[str, Any],
    *,
    quality_report: Optional[dict[str, Any]],
    quality_gate: Optional[dict[str, Any]],
    quality_summary: Optional[dict[str, Any]],
) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    validation_profile = dict(
        _quality_report_field(quality_report, quality_gate, quality_summary, "validation_profile")
        or dict(quality_report or {}).get("validation_profile")
        or payload.get("validation_profile")
        or params.get("validation_profile")
        or {}
    )
    research_context = dict(payload.get("research_context") or params.get("research_context") or {})
    hypothesis_artifact = dict(
        payload.get("hypothesis_artifact")
        or params.get("hypothesis_artifact")
        or research_context.get("hypothesis_artifact")
        or {}
    )
    cost_sensitivity_grid = dict(
        hypothesis_artifact.get("cost_sensitivity_grid")
        or payload.get("cost_sensitivity_grid")
        or params.get("cost_sensitivity_grid")
        or {}
    )
    market_regime_assumption = dict(
        hypothesis_artifact.get("market_regime_assumption")
        or payload.get("market_regime_assumption")
        or params.get("market_regime_assumption")
        or research_context.get("market_regime_assumption")
        or {}
    )
    objective_profile = (
        _string(_quality_report_field(quality_report, quality_gate, quality_summary, "objective_profile")).lower()
        or _string(validation_profile.get("objective_profile")).lower()
        or _string(hypothesis_artifact.get("objective_profile")).lower()
        or _string(research_context.get("objective_profile")).lower()
        or None
    )
    if not objective_profile and _string(payload.get("generator_mode")).lower() == "futures_calendar_research_adapter":
        objective_profile = "high_precision"
    preferred_regime = _string(
        market_regime_assumption.get("preferred_regime") or validation_profile.get("preferred_regime")
    ) or None
    avoid_regime = _string(
        market_regime_assumption.get("avoid_regime") or validation_profile.get("avoid_regime")
    ) or None
    holding_rationale = _string(hypothesis_artifact.get("holding_rationale")) or None
    failure_mode = hypothesis_artifact.get("failure_mode")
    event_prefilter = dict(
        hypothesis_artifact.get("event_prefilter")
        or payload.get("event_prefilter")
        or params.get("event_prefilter")
        or {}
    )
    trade_density_preference = _string(validation_profile.get("trade_density_preference")).lower() or None
    entry_selectivity = _string(validation_profile.get("entry_selectivity")).lower() or None
    event_prefilter_required = _safe_boolish(
        event_prefilter.get("required")
        if event_prefilter.get("required") is not None
        else validation_profile.get("event_prefilter_required"),
        default=objective_profile == "high_precision" and _string(payload.get("strategy_type")).lower() == "event_structure_breakout",
    )
    event_prefilter_summary = dict(
        _quality_report_field(quality_report, quality_gate, quality_summary, "event_prefilter_summary")
        or {}
    )
    if not event_prefilter_summary and (event_prefilter_required or event_prefilter):
        observed_sources = [
            str(item or "").strip()
            for item in list(event_prefilter.get("observed_sources") or [])
            if str(item or "").strip()
        ]
        event_prefilter_summary = {
            "available": True,
            "required": event_prefilter_required,
            "profile": _string(
                event_prefilter.get("profile") or validation_profile.get("event_prefilter_profile")
            ) or None,
            "allowed_sources": list(event_prefilter.get("allowed_sources") or []),
            "observed_sources": observed_sources,
            "observed_confirmation_count": len(observed_sources),
            "min_confirmations": int(
                event_prefilter.get("min_confirmations")
                or validation_profile.get("event_prefilter_min_confirmations")
                or 1
            ),
            "confirmation_count": int(event_prefilter.get("confirmation_count") or len(observed_sources)),
            "passed": bool(event_prefilter.get("passed")) if event_prefilter else (not event_prefilter_required),
            "status": _string(event_prefilter.get("status")) or ("passed" if event_prefilter.get("passed") else "missing"),
            "event_id": event_prefilter.get("event_id"),
            "theme_code": event_prefilter.get("theme_code"),
            "focus_industries": list(event_prefilter.get("focus_industries") or []),
            "evidence_summary": event_prefilter.get("evidence_summary"),
            "event_anchor": dict(event_prefilter.get("event_anchor") or {}),
            "anchor_strength": event_prefilter.get("anchor_strength"),
        }
    event_anchor_summary = dict(
        _quality_report_field(quality_report, quality_gate, quality_summary, "event_anchor_summary")
        or event_prefilter_summary.get("event_anchor")
        or {}
    )
    backtest_metrics_contract_status = _string(
        _quality_report_field(quality_report, quality_gate, quality_summary, "backtest_metrics_contract_status")
        or dict(strategy.get("backtest_metrics_contract") or {}).get("status")
        or dict(strategy.get("params") or {}).get("backtest_metrics_contract_status")
    ).lower() or None
    regime_required = _safe_boolish(
        validation_profile.get("regime_required"),
        default=objective_profile == "high_precision",
    )
    cost_robust_required = _safe_boolish(
        validation_profile.get("cost_robust_required")
        if validation_profile.get("cost_robust_required") is not None
        else hypothesis_artifact.get("cost_robust_required"),
        default=objective_profile == "high_precision",
    )
    precision_readiness = _string(
        _quality_report_field(quality_report, quality_gate, quality_summary, "precision_readiness")
    ).lower() or None
    regime_validation_summary = dict(
        _quality_report_field(quality_report, quality_gate, quality_summary, "regime_validation_summary")
        or {}
    )
    if not regime_validation_summary and objective_profile == "high_precision":
        regime_validation_summary = {
            "available": bool(preferred_regime or avoid_regime or regime_required),
            "preferred_regime": preferred_regime,
            "avoid_regime": avoid_regime,
            "regime_required": regime_required,
            "passed": (not regime_required) or bool(preferred_regime and avoid_regime),
        }
    if not precision_readiness and objective_profile == "high_precision":
        has_core_contract = bool(
            holding_rationale
            and failure_mode not in (None, "", [], {})
            and entry_selectivity
            and ((not event_prefilter_required) or bool(event_prefilter_summary.get("passed")))
            and ((not regime_required) or (preferred_regime and avoid_regime))
            and ((not cost_robust_required) or cost_sensitivity_grid)
        )
        if has_core_contract:
            precision_readiness = "observe"
    return {
        "objective_profile": objective_profile,
        "precision_readiness": precision_readiness,
        "regime_validation_summary": regime_validation_summary,
        "cost_robustness_summary": dict(
            _quality_report_field(quality_report, quality_gate, quality_summary, "cost_robustness_summary")
            or {}
        ),
        "trade_density_summary": dict(
            _quality_report_field(quality_report, quality_gate, quality_summary, "trade_density_summary")
            or {}
        ),
        "event_prefilter_summary": event_prefilter_summary,
        "event_anchor_summary": event_anchor_summary,
        "backtest_metrics_contract_status": backtest_metrics_contract_status,
        "preferred_regime": preferred_regime,
        "avoid_regime": avoid_regime,
        "holding_rationale": holding_rationale,
        "failure_mode": failure_mode,
        "cost_sensitivity_grid": cost_sensitivity_grid,
        "trade_density_preference": trade_density_preference,
        "entry_selectivity": entry_selectivity,
        "trade_density": _safe_float(
            _quality_report_field(quality_report, quality_gate, quality_summary, "trade_density")
        ),
        "avg_holding_days": _safe_float(
            _quality_report_field(quality_report, quality_gate, quality_summary, "avg_holding_days")
        ),
        "cost_robust_required": cost_robust_required,
    }


def _build_position_cycle_evidence(
    *,
    signal_quality: Optional[dict[str, Any]],
    execution_quality: Optional[dict[str, Any]],
    context: Optional[dict[str, Any]],
) -> dict[str, Any]:
    high_precision_context = dict(context or {})
    if _string(high_precision_context.get("objective_profile")).lower() != "high_precision":
        return {}
    signal_payload = dict(signal_quality or {})
    execution_payload = dict(execution_quality or {})
    audit_payload = dict(execution_payload.get("audit") or {})
    primary_horizon = _safe_int(signal_payload.get("primary_horizon"), 5)
    primary_bucket = dict((signal_payload.get("by_horizon") or {}).get(str(primary_horizon)) or {})
    cycle_count = max(
        _safe_int(execution_payload.get("realized_trade_count")),
        _safe_int(execution_payload.get("trade_count")),
        _safe_int(primary_bucket.get("effective_n")),
    )
    cycle_hit_rate = _safe_float(
        audit_payload.get("execution_win_rate")
        if audit_payload.get("execution_win_rate") is not None
        else primary_bucket.get("hit_rate")
    )
    cycle_hit_rate_lcb = _safe_float(primary_bucket.get("hit_rate_lcb"))
    avg_holding_days = _safe_float(high_precision_context.get("avg_holding_days"))
    regime_validation_summary = dict(high_precision_context.get("regime_validation_summary") or {})
    cost_robustness_summary = dict(high_precision_context.get("cost_robustness_summary") or {})
    trade_density_summary = dict(high_precision_context.get("trade_density_summary") or {})
    event_prefilter_summary = dict(high_precision_context.get("event_prefilter_summary") or {})
    regime_validation_passed = regime_validation_summary.get("passed")
    if regime_validation_passed is None and high_precision_context.get("preferred_regime") and high_precision_context.get("avoid_regime"):
        regime_validation_passed = True
    event_prefilter_passed = bool(event_prefilter_summary.get("passed")) if event_prefilter_summary.get("required") else True
    regime_consistency = 1.0 if regime_validation_passed else (
        0.0 if regime_validation_summary.get("available") else None
    )
    cost_robustness = 1.0 if cost_robustness_summary.get("passed") else (
        0.0 if cost_robustness_summary.get("required") else None
    )
    payoff_asymmetry = _safe_float(
        audit_payload.get("avg_win_loss_ratio")
        if audit_payload.get("avg_win_loss_ratio") is not None
        else execution_payload.get("avg_win_loss_ratio")
    )
    adverse_regime_avoidance = bool(
        high_precision_context.get("avoid_regime")
        and regime_validation_passed
        and not list(execution_payload.get("regime_mismatch_events") or [])
    )
    if not event_prefilter_passed:
        status = "insufficient_evidence"
    elif cycle_count >= 6 and (cycle_hit_rate_lcb or 0.0) > 0.5 and (regime_consistency or 0.0) >= 0.75:
        status = "strong"
    elif cycle_count >= 3 and (cycle_hit_rate or 0.0) >= 0.55 and (regime_consistency or 0.0) >= 0.5:
        status = "candidate"
    else:
        status = "insufficient_evidence"
    return {
        "contract_version": "strategy_factory.position_cycle_evidence.v1",
        "status": status,
        "cycle_count": cycle_count,
        "cycle_hit_rate": cycle_hit_rate,
        "cycle_hit_rate_lcb": cycle_hit_rate_lcb,
        "avg_holding_days": avg_holding_days,
        "regime_consistency": regime_consistency,
        "cost_robustness": cost_robustness,
        "trade_density": _safe_float(
            trade_density_summary.get("observed_trade_density")
            if trade_density_summary.get("observed_trade_density") is not None
            else high_precision_context.get("trade_density")
        ),
        "trade_density_preference": _string(trade_density_summary.get("preference")) or None,
        "payoff_asymmetry": payoff_asymmetry,
        "adverse_regime_avoidance": adverse_regime_avoidance,
        "event_prefilter_passed": event_prefilter_passed,
    }
