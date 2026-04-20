
from __future__ import annotations

from typing import Any

from ..domain.constants import (
    FACTORY_BACKLOG_RELAX_ENABLED,
    FACTORY_BACKLOG_RELAX_PRIORITY_PENALTY,
)

FEEDBACK_METRIC_KEYS = (
    "ema_submit_count",
    "paper_hit_ratio",
    "paper_skill_lcb",
    "paper_recent_skill_lcb",
    "paper_stability_gap",
    "paper_coverage_ratio",
    "execution_conversion_efficiency",
    "runtime_alert_pressure",
    "realized_turnover",
    "capacity_crowding",
    "zero_signal_ratio",
    "low_signal_ratio",
    "forward_window_coverage_ratio",
    "promotion_ready_ratio",
    "promotion_review_coverage_ratio",
    "evidence_debt_ratio",
    "gate_failure_rate",
    "trace_completeness_ratio",
    "admission_quality_objective",
    "high_precision_objective",
    "raw_validation_a_rate",
    "raw_validation_b_rate",
    "raw_validation_c_rate",
    "raw_validation_d_rate",
    "raw_validation_total_score_mean",
    "strict_incubation_ready_rate",
    "live_candidate_ready_rate",
)

CONTROL_MODE_SEVERITY: dict[str, int] = {
    "normal": 0,
    "cooldown": 1,
    "suppress": 2,
    "freeze": 3,
}
LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION = "strategy_factory.lifecycle_feedback_input.v1"
FEEDBACK_SCOPE_NAMES: tuple[str, ...] = (
    "target_pool_feedback",
    "generator_mode_feedback",
    "holding_bucket_feedback",
)

RELAXABLE_RESEARCH_CONTROL_REASON_MARKERS: tuple[str, ...] = (
    "zero_signal_backlog",
    "low_signal_backlog",
    "forward_window_coverage",
    "promotion_ready_gap",
    "promotion_review_gap",
    "evidence_debt",
)
HARD_RESEARCH_CONTROL_REASON_MARKERS: tuple[str, ...] = (
    "runtime_alert_pressure",
    "paper_hit_ratio",
    "paper_skill_lcb",
    "paper_recent_skill_lcb",
    "paper_stability_gap",
    "turnover_or_crowding",
    "open_risk_load",
    "promotion_review_rejected",
    "promotion_review_score_freeze",
    "promotion_review_score_suppress",
)
DUAL_AXIS_BUDGET_ACTION_PRIORITY_SCALE = "prioritize_scale"
DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET = "retain_family_reduce_budget"
DUAL_AXIS_BUDGET_ACTION_SMALL_BUDGET_OBSERVE = "small_budget_observe"
DUAL_AXIS_BUDGET_ACTION_COOL_OR_FREEZE = "cool_or_freeze"
DUAL_AXIS_BUDGET_ACTIONS: tuple[str, ...] = (
    DUAL_AXIS_BUDGET_ACTION_PRIORITY_SCALE,
    DUAL_AXIS_BUDGET_ACTION_RETAIN_FAMILY_REDUCE_BUDGET,
    DUAL_AXIS_BUDGET_ACTION_SMALL_BUDGET_OBSERVE,
    DUAL_AXIS_BUDGET_ACTION_COOL_OR_FREEZE,
)
DUAL_AXIS_EXECUTION_CONVERSION_HIGH_THRESHOLD = 0.20
DUAL_AXIS_EXECUTION_CONVERSION_FREEZE_THRESHOLD = 0.10
DUAL_AXIS_PREDICTION_SKILL_HIGH_THRESHOLD = 0.0

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "ema_submit_count": (
        "ema_submit_count",
        "submit_count_ema",
        "avg_submit_count",
        "submit_count",
        "passed_count",
        "strategy_count",
    ),
    "paper_hit_ratio": (
        "paper_hit_ratio",
        "ema_paper_hit_ratio",
        "avg_paper_hit_ratio",
        "paper_hit_ratio_avg",
    ),
    "paper_skill_lcb": (
        "paper_skill_lcb",
        "paper_primary_skill_lcb",
        "paper_signal_skill_lcb",
        "primary_skill_lcb",
        "skill_lcb",
    ),
    "paper_recent_skill_lcb": (
        "paper_recent_skill_lcb",
        "paper_recent_primary_skill_lcb",
        "recent_primary_skill_lcb",
        "recent_skill_lcb",
    ),
    "paper_stability_gap": (
        "paper_stability_gap",
        "stability_gap",
    ),
    "paper_coverage_ratio": (
        "paper_coverage_ratio",
        "paper_signal_coverage_ratio",
        "coverage_ratio",
    ),
    "execution_conversion_efficiency": (
        "execution_conversion_efficiency",
        "audit_execution_conversion_efficiency",
        "paper_execution_conversion_efficiency",
        "execution_efficiency",
    ),
    "runtime_alert_pressure": (
        "runtime_alert_pressure",
        "ema_runtime_alert_pressure",
        "avg_runtime_alert_pressure",
        "runtime_pressure",
    ),
    "realized_turnover": (
        "realized_turnover",
        "ema_realized_turnover",
        "avg_realized_turnover",
        "turnover_rate",
        "turnover_proxy",
    ),
    "capacity_crowding": (
        "capacity_crowding",
        "ema_capacity_crowding",
        "avg_capacity_crowding",
        "adv_utilization",
    ),
    "zero_signal_ratio": (
        "zero_signal_ratio",
        "zero_signal_backlog_ratio",
    ),
    "low_signal_ratio": (
        "low_signal_ratio",
        "effective_signal_gap_ratio",
    ),
    "forward_window_coverage_ratio": (
        "forward_window_coverage_ratio",
        "observed_forward_window_ratio",
        "forward_coverage_ratio",
    ),
    "promotion_ready_ratio": (
        "promotion_ready_ratio",
        "ready_ratio",
    ),
    "promotion_review_coverage_ratio": (
        "promotion_review_coverage_ratio",
        "review_coverage_ratio",
    ),
    "evidence_debt_ratio": (
        "evidence_debt_ratio",
        "signal_evidence_debt_ratio",
    ),
    "gate_failure_rate": (
        "gate_failure_rate",
        "submission_gate_failure_rate",
        "gate_b_failure_rate",
    ),
    "trace_completeness_ratio": (
        "trace_completeness_ratio",
        "prediction_trace_completeness_ratio",
    ),
    "admission_quality_objective": (
        "admission_quality_objective",
        "bandit_admission_quality_objective",
    ),
    "high_precision_objective": (
        "high_precision_objective",
        "bandit_high_precision_objective",
    ),
    "raw_validation_a_rate": (
        "raw_validation_a_rate",
        "family_raw_a_rate",
    ),
    "raw_validation_b_rate": (
        "raw_validation_b_rate",
        "family_raw_b_rate",
    ),
    "raw_validation_c_rate": (
        "raw_validation_c_rate",
        "family_raw_c_rate",
    ),
    "raw_validation_d_rate": (
        "raw_validation_d_rate",
        "family_raw_d_rate",
    ),
    "raw_validation_total_score_mean": (
        "raw_validation_total_score_mean",
        "family_raw_validation_total_score_mean",
        "raw_total_score_mean",
    ),
    "strict_incubation_ready_rate": (
        "strict_incubation_ready_rate",
        "family_strict_incubation_ready_rate",
    ),
    "live_candidate_ready_rate": (
        "live_candidate_ready_rate",
        "family_live_candidate_ready_rate",
    ),
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value or {})
    except Exception:
        return {}


def extract_feedback_root(snapshot_or_feedback: Any) -> dict[str, Any]:
    payload = _coerce_mapping(snapshot_or_feedback)
    if any(
        key in payload for key in ("contract_version", "summary", "available", "reason")
    ):
        nested_feedback = payload.get("feedback")
        if isinstance(nested_feedback, dict):
            return extract_feedback_root(nested_feedback)
        return {}
    nested_contract = payload.get("lifecycle_feedback_input")
    if isinstance(nested_contract, dict):
        return extract_feedback_root(nested_contract)
    nested_budget_feedback = payload.get("budget_feedback")
    if isinstance(nested_budget_feedback, dict):
        return extract_feedback_root(nested_budget_feedback)
    nested = payload.get("family_gate_feedback")
    if isinstance(nested, dict):
        return extract_feedback_root(nested)
    return payload


def _count_feedback_scopes(
    feedback_root: dict[str, Any],
    *,
    scope_name: str,
) -> int:
    count = 0
    for bucket in feedback_root.values():
        if not isinstance(bucket, dict):
            continue
        count += len(dict(bucket.get(scope_name) or {}))
    return count


def _sum_feedback_metric(
    feedback_root: dict[str, Any],
    *,
    metric_name: str,
) -> int:
    total = 0
    for bucket in feedback_root.values():
        if not isinstance(bucket, dict):
            continue
        total += _safe_int(bucket.get(metric_name))
    return total


def _average_feedback_metric(
    feedback_root: dict[str, Any],
    *,
    metric_name: str,
    default: float,
) -> float:
    weighted_total = 0.0
    total_weight = 0.0
    for bucket in feedback_root.values():
        if not isinstance(bucket, dict):
            continue
        value = _metric_value(bucket, metric_name)
        if value is None:
            continue
        weight = max(_safe_int(bucket.get("strategy_count")), 1)
        weighted_total += float(value) * weight
        total_weight += float(weight)
    return round(weighted_total / total_weight, 4) if total_weight else round(float(default), 4)


def _family_control_mode_counts(
    feedback_root: dict[str, Any],
    *,
    signal_mode: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bucket in feedback_root.values():
        if not isinstance(bucket, dict):
            continue
        if signal_mode == "skill":
            mode = normalize_text(
                _derive_skill_scope_control(dict(bucket), scope_name="family").get("mode")
            )
        else:
            mode = normalize_text(
                _derive_scope_control(dict(bucket), scope_name="family").get("mode")
            )
        counts[mode or "normal"] = counts.get(mode or "normal", 0) + 1
    return counts


def _merge_feedback_count_maps(*mappings: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for mapping in mappings:
        for key, value in dict(mapping or {}).items():
            token = str(key or "").strip()
            if not token:
                continue
            merged[token] = merged.get(token, 0) + _safe_int(value)
    return merged
