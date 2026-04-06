"""Helpers for P3 budget feedback normalization and scoring."""

from __future__ import annotations

from typing import Any

FEEDBACK_METRIC_KEYS = (
    "ema_submit_count",
    "paper_hit_ratio",
    "runtime_alert_pressure",
    "realized_turnover",
    "capacity_crowding",
)

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
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def extract_feedback_root(snapshot_or_feedback: Any) -> dict[str, Any]:
    payload = dict(snapshot_or_feedback or {})
    nested = payload.get("family_gate_feedback")
    if isinstance(nested, dict):
        return dict(nested)
    return payload


def extract_target_pool_id(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    contract_snapshot = dict(item.get("candidate_contract_snapshot") or {})
    targeting = dict(contract_snapshot.get("targeting") or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or {})
    research_task = dict(item.get("research_task") or {})

    for value in (
        item.get("target_pool_id"),
        targeting.get("target_pool_id"),
        candidate_provenance.get("target_pool_id"),
        params.get("target_pool_id"),
        research_task.get("target_pool_id"),
    ):
        token = str(value or "").strip()
        if token:
            return token
    return None


def extract_generator_mode(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})
    for value in (
        item.get("generator_mode"),
        item.get("generator_type"),
        candidate_provenance.get("generator_mode"),
        candidate_provenance.get("generator_type"),
        params.get("generator_mode"),
        strategy_profile.get("generator_mode"),
    ):
        token = normalize_text(value)
        if token:
            return token
    return None


def _metric_value(bucket: dict[str, Any], metric: str) -> float | None:
    if not isinstance(bucket, dict):
        return None
    for key in _METRIC_ALIASES.get(metric, (metric,)):
        if bucket.get(key) is not None:
            return safe_float(bucket.get(key))
    return None


def _resolve_bucket(feedback_root: dict[str, Any], family: str) -> dict[str, Any]:
    return dict(feedback_root.get(normalize_text(family)) or {})


def _scope_bucket(family_bucket: dict[str, Any], scope_name: str, scope_key: str | None) -> dict[str, Any]:
    if not scope_key:
        return {}
    raw_scope = family_bucket.get(scope_name)
    if not isinstance(raw_scope, dict):
        return {}
    return dict(raw_scope.get(normalize_text(scope_key)) or raw_scope.get(str(scope_key).strip()) or {})


def resolve_feedback_metrics(
    snapshot_or_feedback: Any,
    *,
    family: str,
    target_pool_id: str | None = None,
    generator_mode: str | None = None,
) -> dict[str, Any]:
    feedback_root = extract_feedback_root(snapshot_or_feedback)
    family_bucket = _resolve_bucket(feedback_root, family)
    target_pool_bucket = _scope_bucket(family_bucket, "target_pool_feedback", target_pool_id)
    generator_bucket = _scope_bucket(family_bucket, "generator_mode_feedback", generator_mode)
    scopes = (
        (family_bucket, 1.0),
        (target_pool_bucket, 0.8),
        (generator_bucket, 0.65),
    )
    resolved: dict[str, Any] = {
        "family": normalize_text(family) or "unknown",
        "target_pool_id": str(target_pool_id or "").strip() or None,
        "generator_mode": normalize_text(generator_mode) or None,
        "family_feedback_available": bool(family_bucket),
        "target_pool_feedback_available": bool(target_pool_bucket),
        "generator_mode_feedback_available": bool(generator_bucket),
    }
    defaults = {
        "ema_submit_count": 0.0,
        "paper_hit_ratio": 0.5,
        "runtime_alert_pressure": 0.0,
        "realized_turnover": 0.0,
        "capacity_crowding": 0.0,
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
    resolved["budget_multiplier"] = compute_budget_multiplier(resolved)
    resolved["priority_adjustment"] = compute_priority_adjustment(resolved)
    resolved["failure_penalty_adjustment"] = compute_failure_penalty_adjustment(resolved)
    return resolved


def compute_budget_multiplier(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    ema_submit_count = max(0.0, min(safe_float(metrics.get("ema_submit_count"), 0.0), 8.0))

    paper_bonus = (paper_hit_ratio - 0.5) * 0.7
    turnover_penalty = max(realized_turnover - 0.55, 0.0) * 0.25
    crowding_penalty = max(capacity_crowding - 0.45, 0.0) * 0.22
    submit_bonus = min(ema_submit_count / 10.0, 0.12)
    multiplier = 1.0 + paper_bonus - runtime_alert_pressure * 0.42 - turnover_penalty - crowding_penalty + submit_bonus
    return round(min(max(multiplier, 0.4), 1.75), 4)


def compute_priority_adjustment(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    ema_submit_count = max(0.0, min(safe_float(metrics.get("ema_submit_count"), 0.0), 8.0))

    turnover_penalty = max(realized_turnover - 0.55, 0.0)
    crowding_penalty = max(capacity_crowding - 0.45, 0.0)
    adjustment = (
        (paper_hit_ratio - 0.5) * 14.0
        - runtime_alert_pressure * 8.5
        - turnover_penalty * 5.0
        - crowding_penalty * 4.5
        + min(ema_submit_count, 6.0) * 0.75
    )
    return round(adjustment, 4)


def compute_failure_penalty_adjustment(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))

    turnover_penalty = max(realized_turnover - 0.55, 0.0) * 0.08
    crowding_penalty = max(capacity_crowding - 0.45, 0.0) * 0.06
    paper_credit = max(paper_hit_ratio - 0.55, 0.0) * 0.08
    adjustment = runtime_alert_pressure * 0.12 + turnover_penalty + crowding_penalty - paper_credit
    return round(min(max(adjustment, -0.06), 0.22), 4)


__all__ = [
    "FEEDBACK_METRIC_KEYS",
    "compute_budget_multiplier",
    "compute_failure_penalty_adjustment",
    "compute_priority_adjustment",
    "extract_feedback_root",
    "extract_generator_mode",
    "extract_target_pool_id",
    "normalize_text",
    "resolve_feedback_metrics",
    "safe_float",
]
