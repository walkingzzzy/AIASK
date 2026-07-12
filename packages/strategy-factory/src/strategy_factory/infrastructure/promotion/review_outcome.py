"""Pure promotion review outcome + score (no DB I/O).

Extracted from akshare-mcp StrategyPromotionPipelineService so host
services remain thin adapters. Numeric weights are locked for fixture
parity; changing them requires an explicit gate-change note.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


def _normalized_status(value: object) -> str:
    return str(value or "").strip().lower()


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _trace_evidence_gap_codes(overview: Mapping[str, Any]) -> list[str]:
    payload = _as_dict(overview.get("prediction_trace_ledger"))
    codes: list[str] = []
    for item in list(payload.get("evidence_gap_codes") or []):
        token = _normalized_status(item)
        if token and token not in codes:
            codes.append(token)
    return codes


def _hard_gate_reasons(overview: Mapping[str, Any]) -> list[str]:
    payload = _as_dict(overview.get("hard_gate_result"))
    reasons: list[str] = []
    for item in list(payload.get("reasons") or overview.get("blockers") or []):
        token = str(item or "").strip()
        if token and token not in reasons:
            reasons.append(token)
    return reasons


_CRITICAL_TRACE_GAPS = {
    "missing_actual_fill",
    "missing_position_round_trip",
    "missing_pnl_audit",
    "missing_pnl_audit_summary",
}


def evaluate_promotion_review_outcome(
    overview: Mapping[str, Any] | None,
) -> tuple[str, str, list[str]]:
    """Return (status, recommendation, blockers) from an overview-like dict.

    status: approved | rejected | watch
    recommendation: promote | deprecate | observe
    """
    overview = dict(overview or {})
    objective_profile = _normalized_status(overview.get("objective_profile"))
    signal_status = _normalized_status(
        _as_dict(overview.get("signal_quality_snapshot")).get("status")
    )
    execution_status = _normalized_status(
        _as_dict(overview.get("execution_quality_snapshot")).get("status")
    )
    hard_gate_reasons = _hard_gate_reasons(overview)
    critical_trace_gaps = [
        code for code in _trace_evidence_gap_codes(overview) if code in _CRITICAL_TRACE_GAPS
    ]
    position_cycle_evidence = _as_dict(overview.get("position_cycle_evidence"))
    position_cycle_status = _normalized_status(position_cycle_evidence.get("status"))
    precision_readiness = _normalized_status(overview.get("precision_readiness"))
    cost_robustness_summary = _as_dict(overview.get("cost_robustness_summary"))
    trade_density_summary = _as_dict(overview.get("trade_density_summary"))
    event_prefilter_summary = _as_dict(overview.get("event_prefilter_summary"))

    blockers: list[str] = []
    blockers.extend(hard_gate_reasons)
    blockers.extend(code for code in critical_trace_gaps if code not in blockers)
    if signal_status and signal_status != "strong" and "signal_quality_snapshot_not_strong" not in blockers:
        blockers.append("signal_quality_snapshot_not_strong")
    if execution_status in {"weak", "insufficient_evidence", "missing"} and (
        f"execution_quality_snapshot:{execution_status}" not in blockers
    ):
        blockers.append(f"execution_quality_snapshot:{execution_status}")
    if objective_profile == "high_precision":
        if precision_readiness not in {"candidate", "strong"}:
            blockers.append(f"high_precision_precision_readiness:{precision_readiness or 'missing'}")
        if position_cycle_status in {"", "weak", "insufficient_evidence", "observe"}:
            blockers.append(f"high_precision_cycle_evidence:{position_cycle_status or 'missing'}")
        if trade_density_summary and not bool(trade_density_summary.get("passed")):
            blockers.append("high_precision_trade_density_not_ready")
        if cost_robustness_summary.get("required") and not bool(cost_robustness_summary.get("passed")):
            blockers.append("high_precision_cost_fragility")
        if event_prefilter_summary.get("required") and not bool(event_prefilter_summary.get("passed")):
            blockers.append("high_precision_event_prefilter_not_ready")
        if overview.get("adverse_regime_avoidance") is False:
            blockers.append("high_precision_adverse_regime_not_avoided")
    if overview.get("deprecation_risk"):
        return "rejected", "deprecate", blockers
    if (
        bool(overview.get("promotion_ready"))
        and signal_status == "strong"
        and execution_status in {"strong", "passed"}
        and not blockers
    ):
        return "approved", "promote", blockers
    return "watch", "observe", blockers


def score_promotion_review(
    overview: Mapping[str, Any] | None,
    metric: Optional[Mapping[str, Any]] = None,
) -> float:
    """Numeric promotion score in [0, 1] (same weights as host pipeline)."""
    overview = dict(overview or {})
    objective_profile = _normalized_status(overview.get("objective_profile"))
    signal_status = _normalized_status(
        _as_dict(overview.get("signal_quality_snapshot")).get("status")
    )
    execution_status = _normalized_status(
        _as_dict(overview.get("execution_quality_snapshot")).get("status")
    )
    hard_gate_reasons = _hard_gate_reasons(overview)
    trace_gap_codes = _trace_evidence_gap_codes(overview)
    precision_readiness = _normalized_status(overview.get("precision_readiness"))
    position_cycle_evidence = _as_dict(overview.get("position_cycle_evidence"))
    position_cycle_status = _normalized_status(position_cycle_evidence.get("status"))
    event_prefilter_summary = _as_dict(overview.get("event_prefilter_summary"))
    score = 0.2
    if signal_status == "strong":
        score += 0.24
    elif signal_status == "candidate":
        score += 0.10
    elif signal_status == "weak":
        score -= 0.18
    elif signal_status == "insufficient_evidence":
        score -= 0.14
    if execution_status in {"strong", "passed"}:
        score += 0.24
    elif execution_status == "candidate":
        score += 0.08
    elif execution_status == "weak":
        score -= 0.22
    elif execution_status == "insufficient_evidence":
        score -= 0.18
    if overview.get("promotion_ready"):
        score += 0.12
    if overview.get("execution_hard_gate_passed"):
        score += 0.08
    elif str(overview.get("execution_audit_gate_status") or "") == "failed_metrics":
        score -= 0.18
    if overview.get("deprecation_risk"):
        score -= 0.35
    score -= min(len(hard_gate_reasons), 5) * 0.08
    score -= min(len(trace_gap_codes), 5) * 0.05
    if objective_profile == "high_precision":
        if precision_readiness == "strong":
            score += 0.12
        elif precision_readiness == "candidate":
            score += 0.06
        else:
            score -= 0.08
        if position_cycle_status == "strong":
            score += 0.10
        elif position_cycle_status == "candidate":
            score += 0.05
        else:
            score -= 0.08
        regime_consistency = float(position_cycle_evidence.get("regime_consistency") or 0)
        cost_robustness = float(position_cycle_evidence.get("cost_robustness") or 0)
        score += max(min(regime_consistency, 1.0), 0.0) * 0.06
        score += max(min(cost_robustness, 1.0), 0.0) * 0.05
        if _as_dict(overview.get("trade_density_summary")) and not bool(
            _as_dict(overview.get("trade_density_summary")).get("passed")
        ):
            score -= 0.10
        if _as_dict(overview.get("cost_robustness_summary")).get("required") and not bool(
            _as_dict(overview.get("cost_robustness_summary")).get("passed")
        ):
            score -= 0.12
        if event_prefilter_summary.get("required") and not bool(event_prefilter_summary.get("passed")):
            score -= 0.10
        if overview.get("adverse_regime_avoidance") is False:
            score -= 0.08
    if metric:
        metric_d = dict(metric)
        sharpe = float(metric_d.get("sharpe_ratio") or 0)
        hit_rate = float(metric_d.get("hit_rate_5d") or 0)
        forward_sharpe = float(metric_d.get("forward_sharpe_5d") or 0)
        score += min(max(sharpe, -1.0), 2.0) * 0.08
        score += hit_rate * 0.12
        score += max(forward_sharpe, -1.0) * 0.08
    score -= min(len(list(overview.get("blockers") or [])), 5) * 0.05
    score -= min(len(list(overview.get("risk_flags") or [])), 5) * 0.05
    return round(max(0.0, min(score, 1.0)), 4)


__all__ = [
    "evaluate_promotion_review_outcome",
    "score_promotion_review",
]
