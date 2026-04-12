"""Helpers for P3 budget feedback normalization and scoring."""

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
    "runtime_alert_pressure",
    "realized_turnover",
    "capacity_crowding",
    "zero_signal_ratio",
    "low_signal_ratio",
    "forward_window_coverage_ratio",
    "promotion_ready_ratio",
    "promotion_review_coverage_ratio",
    "evidence_debt_ratio",
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


def normalize_feedback_input_contract(
    snapshot_or_feedback: Any,
    *,
    reason: str | None = None,
    summary: dict[str, Any] | None = None,
    available: bool | None = None,
) -> dict[str, Any]:
    payload = _coerce_mapping(snapshot_or_feedback)
    feedback_root = extract_feedback_root(payload)
    summary_payload = dict(payload.get("summary") or {})
    if isinstance(summary, dict):
        summary_payload.update(summary)
    family_count = int(summary_payload.get("family_count") or len(feedback_root))
    target_pool_scope_count = int(
        summary_payload.get("target_pool_scope_count")
        or _count_feedback_scopes(feedback_root, scope_name="target_pool_feedback")
    )
    generator_mode_scope_count = int(
        summary_payload.get("generator_mode_scope_count")
        or _count_feedback_scopes(feedback_root, scope_name="generator_mode_feedback")
    )
    holding_bucket_scope_count = int(
        summary_payload.get("holding_bucket_scope_count")
        or _count_feedback_scopes(feedback_root, scope_name="holding_bucket_feedback")
    )
    contract_available = bool(feedback_root) if available is None else bool(available)
    resolved_reason = str(
        reason
        if reason is not None
        else payload.get("reason")
        or ("feedback_unavailable" if not contract_available else "")
    ).strip() or None
    if contract_available and resolved_reason == "feedback_unavailable":
        resolved_reason = None
    paper_hit_ratio = (
        safe_float(summary_payload.get("paper_hit_ratio"), 0.5)
        if "paper_hit_ratio" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_hit_ratio",
            default=0.5,
        )
    )
    paper_skill_lcb = (
        safe_float(summary_payload.get("paper_skill_lcb"))
        if "paper_skill_lcb" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_skill_lcb",
            default=0.0,
        )
    )
    paper_recent_skill_lcb = (
        safe_float(summary_payload.get("paper_recent_skill_lcb"))
        if "paper_recent_skill_lcb" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_recent_skill_lcb",
            default=0.0,
        )
    )
    paper_stability_gap = (
        safe_float(summary_payload.get("paper_stability_gap"))
        if "paper_stability_gap" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_stability_gap",
            default=0.0,
        )
    )
    paper_coverage_ratio = (
        safe_float(summary_payload.get("paper_coverage_ratio"), 1.0)
        if "paper_coverage_ratio" in summary_payload
        else _average_feedback_metric(
            feedback_root,
            metric_name="paper_coverage_ratio",
            default=1.0,
        )
    )
    legacy_control_mode_counts = (
        _merge_feedback_count_maps(summary_payload.get("legacy_control_mode_counts"))
        if "legacy_control_mode_counts" in summary_payload
        else _family_control_mode_counts(feedback_root, signal_mode="legacy")
    )
    skill_control_mode_counts = (
        _merge_feedback_count_maps(summary_payload.get("skill_control_mode_counts"))
        if "skill_control_mode_counts" in summary_payload
        else _family_control_mode_counts(feedback_root, signal_mode="skill")
    )
    normalized_summary = {
        **summary_payload,
        "family_count": family_count,
        "seeded_family_count": int(summary_payload.get("seeded_family_count") or family_count),
        "strategy_count": int(summary_payload.get("strategy_count") or 0),
        "runtime_alert_count": int(summary_payload.get("runtime_alert_count") or 0),
        "runtime_risk_event_count": int(summary_payload.get("runtime_risk_event_count") or 0),
        "signal_count_total": int(
            summary_payload.get("signal_count_total")
            or _sum_feedback_metric(feedback_root, metric_name="signal_count_total")
        ),
        "zero_signal_strategy_count": int(
            summary_payload.get("zero_signal_strategy_count")
            or _sum_feedback_metric(feedback_root, metric_name="zero_signal_strategy_count")
        ),
        "low_signal_strategy_count": int(
            summary_payload.get("low_signal_strategy_count")
            or _sum_feedback_metric(feedback_root, metric_name="low_signal_strategy_count")
        ),
        "observed_forward_window_count": int(
            summary_payload.get("observed_forward_window_count")
            or _sum_feedback_metric(feedback_root, metric_name="observed_forward_window_count")
        ),
        "missing_forward_window_count": int(
            summary_payload.get("missing_forward_window_count")
            or _sum_feedback_metric(feedback_root, metric_name="missing_forward_window_count")
        ),
        "expected_forward_window_count": int(
            summary_payload.get("expected_forward_window_count")
            or _sum_feedback_metric(feedback_root, metric_name="expected_forward_window_count")
        ),
        "promotion_ready_count": int(
            summary_payload.get("promotion_ready_count")
            or _sum_feedback_metric(feedback_root, metric_name="promotion_ready_count")
        ),
        "evidence_debt_strategy_count": int(
            summary_payload.get("evidence_debt_strategy_count")
            or _sum_feedback_metric(feedback_root, metric_name="evidence_debt_strategy_count")
        ),
        "promotion_review_count": int(
            summary_payload.get("promotion_review_count")
            or _sum_feedback_metric(feedback_root, metric_name="promotion_review_count")
        ),
        "target_pool_scope_count": target_pool_scope_count,
        "generator_mode_scope_count": generator_mode_scope_count,
        "holding_bucket_scope_count": holding_bucket_scope_count,
        "promotion_review_status_counts": (
            _merge_feedback_count_maps(summary_payload.get("promotion_review_status_counts"))
            if dict(summary_payload.get("promotion_review_status_counts") or {})
            else _merge_feedback_count_maps(
                *[
                    dict(bucket.get("promotion_review_status_counts") or {})
                    for bucket in feedback_root.values()
                    if isinstance(bucket, dict)
                ]
            )
        ),
        "promotion_review_recommendation_counts": (
            _merge_feedback_count_maps(summary_payload.get("promotion_review_recommendation_counts"))
            if dict(summary_payload.get("promotion_review_recommendation_counts") or {})
            else _merge_feedback_count_maps(
                *[
                    dict(bucket.get("promotion_review_recommendation_counts") or {})
                    for bucket in feedback_root.values()
                    if isinstance(bucket, dict)
                ]
            )
        ),
        "paper_hit_ratio": round(paper_hit_ratio, 4),
        "paper_skill_lcb": round(paper_skill_lcb, 4),
        "paper_recent_skill_lcb": round(paper_recent_skill_lcb, 4),
        "paper_stability_gap": round(paper_stability_gap, 4),
        "paper_coverage_ratio": round(paper_coverage_ratio, 4),
        "legacy_control_mode_counts": legacy_control_mode_counts,
        "skill_control_mode_counts": skill_control_mode_counts,
    }
    strategy_count = int(normalized_summary.get("strategy_count") or 0)
    expected_forward_window_count = int(normalized_summary.get("expected_forward_window_count") or 0)
    zero_signal_ratio = (
        round(int(normalized_summary.get("zero_signal_strategy_count") or 0) / strategy_count, 4)
        if strategy_count
        else 0.0
    )
    low_signal_ratio = (
        round(int(normalized_summary.get("low_signal_strategy_count") or 0) / strategy_count, 4)
        if strategy_count
        else 0.0
    )
    forward_window_coverage_ratio = (
        round(
            int(normalized_summary.get("observed_forward_window_count") or 0)
            / expected_forward_window_count,
            4,
        )
        if expected_forward_window_count
        else 1.0
    )
    promotion_ready_ratio = (
        round(int(normalized_summary.get("promotion_ready_count") or 0) / strategy_count, 4)
        if strategy_count
        else 1.0
    )
    promotion_review_coverage_ratio = (
        round(int(normalized_summary.get("promotion_review_count") or 0) / strategy_count, 4)
        if strategy_count
        else 1.0
    )
    evidence_debt_ratio = round(
        min(
            max(
                zero_signal_ratio * 0.45
                + (1.0 - forward_window_coverage_ratio) * 0.25
                + (1.0 - promotion_ready_ratio) * 0.15
                + (1.0 - promotion_review_coverage_ratio) * 0.15,
                0.0,
            ),
            1.0,
        ),
        4,
    )
    normalized_summary.update(
        {
            "zero_signal_ratio": zero_signal_ratio,
            "low_signal_ratio": low_signal_ratio,
            "forward_window_coverage_ratio": forward_window_coverage_ratio,
            "promotion_ready_ratio": promotion_ready_ratio,
            "promotion_review_coverage_ratio": promotion_review_coverage_ratio,
            "evidence_debt_ratio": evidence_debt_ratio,
        }
    )
    return {
        "contract_version": LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION,
        "available": contract_available,
        "reason": resolved_reason if not contract_available else resolved_reason,
        "feedback": feedback_root,
        "summary": normalized_summary,
    }


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


def derive_target_pool_id(payload: dict[str, Any] | None) -> str | None:
    explicit = extract_target_pool_id(payload)
    if explicit:
        return explicit

    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    event_context = dict(item.get("event_context") or research_task.get("event_context") or {})

    for value in (
        item.get("theme_code"),
        research_task.get("theme_code"),
        event_context.get("theme_code"),
        item.get("event_id"),
        research_task.get("event_id"),
        event_context.get("event_id"),
    ):
        token = str(value or "").strip()
        if token:
            return token

    def _resolve_symbols(values: Any) -> list[str]:
        try:
            from ..domain.targets import _normalize_target_codes

            return list(_normalize_target_codes(values, limit=12))
        except Exception:
            return []

    stock_pool = dict(item.get("stock_pool") or research_task.get("stock_pool") or {})
    selection_mode = str(stock_pool.get("selection_mode") or "").strip().lower()
    symbols = _resolve_symbols(
        [
            stock_pool.get("symbols"),
            stock_pool.get("target_symbols"),
            item.get("target_symbols"),
            research_task.get("target_symbols"),
            event_context.get("target_symbols"),
        ]
    )
    if selection_mode and symbols:
        return f"{selection_mode}:{','.join(symbols)}"
    if symbols:
        return f"symbols:{','.join(symbols)}"
    return None


def extract_generator_mode(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})
    for value in (
        item.get("generator_mode"),
        item.get("generator_type"),
        research_task.get("generator_mode"),
        research_task.get("generator_type"),
        candidate_provenance.get("generator_mode"),
        candidate_provenance.get("generator_type"),
        params.get("generator_mode"),
        strategy_profile.get("generator_mode"),
    ):
        token = normalize_text(value)
        if token:
            return token
    task_source = _resolve_research_task_source(item)
    if task_source == "snapshot":
        return "rule"
    return None


def extract_holding_bucket(payload: dict[str, Any] | None) -> str | None:
    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    params = dict(item.get("params") or {})
    candidate_provenance = dict(params.get("candidate_provenance") or item.get("candidate_provenance") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})
    for value in (
        item.get("holding_period_bucket"),
        strategy_profile.get("holding_period_bucket"),
        candidate_provenance.get("holding_period_bucket"),
        params.get("holding_period_bucket"),
        research_task.get("holding_period_bucket"),
    ):
        token = normalize_text(value)
        if token:
            return token

    holding_horizon = dict(
        item.get("holding_horizon")
        or params.get("holding_horizon")
        or research_task.get("holding_window")
        or {}
    )
    max_days = _safe_int(
        holding_horizon.get("max_days") or holding_horizon.get("alpha_half_life")
    )
    if max_days > 0:
        if max_days <= 5:
            return "short"
        if max_days <= 20:
            return "medium"
        return "long"

    strategy_type = normalize_text(
        item.get("strategy_type")
        or research_task.get("candidate_family")
        or research_task.get("strategy_type")
    )
    if strategy_type in {"momentum", "rsi", "volatility_breakout", "gap_fill", "mean_reversion_short"}:
        return "short"
    if strategy_type in {"value_factor"}:
        return "long"
    if strategy_type:
        return "medium"
    return None


def extract_feedback_families(payload: dict[str, Any] | None) -> list[str]:
    item = dict(payload or {})
    params = dict(item.get("params") or {})
    provenance = dict(params.get("candidate_provenance") or item.get("candidate_provenance") or {})
    research_task = dict(item.get("research_task") or {})
    strategy_profile = dict(item.get("strategy_profile") or {})

    families: list[str] = []

    def _append(value: Any) -> None:
        token = normalize_text(value)
        if token and token not in families:
            families.append(token)

    def _append_list(values: Any) -> None:
        if isinstance(values, (list, tuple, set)):
            for value in values:
                _append(value)
            return
        if values not in (None, "", [], {}):
            _append(values)

    for source in (item, research_task, provenance, params, strategy_profile):
        if not isinstance(source, dict):
            continue
        for key in ("candidate_family", "family", "strategy_family", "strategy_type"):
            _append(source.get(key))
        for key in ("strategy_preferences", "preferred_strategy_types", "allowed_strategy_types"):
            _append_list(source.get(key))
    return families


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


def _derive_skill_scope_control(bucket: dict[str, Any], *, scope_name: str) -> dict[str, Any]:
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

    paper_skill_lcb = _clamp(safe_float(_metric_value(payload, "paper_skill_lcb"), 0.0), -1.0, 1.0)
    paper_recent_skill_lcb = _clamp(
        safe_float(_metric_value(payload, "paper_recent_skill_lcb"), paper_skill_lcb),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(
        safe_float(_metric_value(payload, "paper_stability_gap"), 0.0),
        0.0,
        1.0,
    )
    paper_coverage_ratio = _clamp(
        safe_float(_metric_value(payload, "paper_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    runtime_alert_pressure = _clamp(
        safe_float(_metric_value(payload, "runtime_alert_pressure"), 0.0),
        0.0,
        1.0,
    )
    realized_turnover = _clamp(
        safe_float(_metric_value(payload, "realized_turnover"), 0.0),
        0.0,
        2.0,
    )
    capacity_crowding = _clamp(
        safe_float(_metric_value(payload, "capacity_crowding"), 0.0),
        0.0,
        2.0,
    )
    runtime_alert_count = _safe_int(payload.get("runtime_alert_count"))
    runtime_risk_event_count = _safe_int(payload.get("runtime_risk_event_count"))
    strategy_count = _safe_int(payload.get("strategy_count"))
    zero_signal_ratio = _clamp(safe_float(_metric_value(payload, "zero_signal_ratio"), 0.0), 0.0, 1.0)
    low_signal_ratio = _clamp(safe_float(_metric_value(payload, "low_signal_ratio"), 0.0), 0.0, 1.0)
    forward_window_coverage_ratio = _clamp(
        safe_float(_metric_value(payload, "forward_window_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    promotion_ready_ratio = _clamp(
        safe_float(_metric_value(payload, "promotion_ready_ratio"), 1.0),
        0.0,
        1.0,
    )
    promotion_review_coverage_ratio = _clamp(
        safe_float(_metric_value(payload, "promotion_review_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    evidence_debt_ratio = _clamp(
        safe_float(_metric_value(payload, "evidence_debt_ratio"), 0.0),
        0.0,
        1.0,
    )
    promotion_review_count = _safe_int(payload.get("promotion_review_count"))
    promotion_review_score = _clamp(safe_float(payload.get("promotion_review_score"), 0.5), 0.0, 1.0)
    promotion_review_status = normalize_text(payload.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(payload.get("promotion_review_recommendation"))
    freeze_active = any(
        _truthy_flag(payload.get(key))
        for key in ("freeze", "freeze_active", "scope_freeze_active", "hard_freeze")
    )
    suppressed = any(
        _truthy_flag(payload.get(key))
        for key in ("suppress", "suppress_active", "suppressed")
    )
    cooldown_active = any(
        _truthy_flag(payload.get(key))
        for key in ("cooldown", "cooldown_active")
    )
    reasons: list[str] = []

    if runtime_alert_pressure >= 0.88:
        freeze_active = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_freeze")
    elif runtime_alert_pressure >= 0.72:
        suppressed = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_suppress")
    elif runtime_alert_pressure >= 0.55:
        cooldown_active = True
        reasons.append(f"{scope_name}_runtime_alert_pressure_cooldown")

    if paper_skill_lcb <= -0.08 or paper_recent_skill_lcb <= -0.10:
        freeze_active = True
        reasons.append(f"{scope_name}_paper_skill_lcb_collapse")
    elif paper_skill_lcb <= -0.03 or paper_recent_skill_lcb <= -0.05:
        suppressed = True
        reasons.append(f"{scope_name}_paper_skill_lcb_suppress")
    elif paper_skill_lcb < 0.015 or paper_recent_skill_lcb < -0.005:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_skill_lcb_cooldown")

    if paper_stability_gap >= 0.18:
        freeze_active = True
        reasons.append(f"{scope_name}_paper_stability_gap_freeze")
    elif paper_stability_gap >= 0.11:
        suppressed = True
        reasons.append(f"{scope_name}_paper_stability_gap_suppress")
    elif paper_stability_gap > 0.07:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_stability_gap_cooldown")

    if paper_coverage_ratio <= 0.15 and strategy_count >= 4:
        suppressed = True
        reasons.append(f"{scope_name}_paper_coverage_ratio_suppress")
    elif paper_coverage_ratio < 0.45 and strategy_count >= 3:
        cooldown_active = True
        reasons.append(f"{scope_name}_paper_coverage_ratio_cooldown")

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


def resolve_feedback_metrics(
    snapshot_or_feedback: Any,
    *,
    family: str,
    target_pool_id: str | None = None,
    holding_bucket: str | None = None,
    generator_mode: str | None = None,
) -> dict[str, Any]:
    feedback_root = extract_feedback_root(snapshot_or_feedback)
    family_bucket = _resolve_bucket(feedback_root, family)
    target_pool_bucket = _scope_bucket(family_bucket, "target_pool_feedback", target_pool_id)
    holding_bucket_bucket = _scope_bucket(
        family_bucket,
        "holding_bucket_feedback",
        holding_bucket,
    )
    generator_bucket = _scope_bucket(family_bucket, "generator_mode_feedback", generator_mode)
    scopes = (
        (family_bucket, 1.0),
        (target_pool_bucket, 0.8),
        (holding_bucket_bucket, 0.72),
        (generator_bucket, 0.65),
    )
    family_control = _derive_scope_control(family_bucket, scope_name="family")
    target_pool_control = _derive_scope_control(target_pool_bucket, scope_name="target_pool")
    holding_bucket_control = _derive_scope_control(
        holding_bucket_bucket,
        scope_name="holding_bucket",
    )
    generator_mode_control = _derive_scope_control(generator_bucket, scope_name="generator_mode")
    legacy_scope_controls = (
        family_control,
        target_pool_control,
        holding_bucket_control,
        generator_mode_control,
    )
    skill_family_control = _derive_skill_scope_control(family_bucket, scope_name="family")
    skill_target_pool_control = _derive_skill_scope_control(
        target_pool_bucket,
        scope_name="target_pool",
    )
    skill_holding_bucket_control = _derive_skill_scope_control(
        holding_bucket_bucket,
        scope_name="holding_bucket",
    )
    skill_generator_mode_control = _derive_skill_scope_control(
        generator_bucket,
        scope_name="generator_mode",
    )
    skill_scope_controls = (
        skill_family_control,
        skill_target_pool_control,
        skill_holding_bucket_control,
        skill_generator_mode_control,
    )
    resolved: dict[str, Any] = {
        "family": normalize_text(family) or "unknown",
        "target_pool_id": str(target_pool_id or "").strip() or None,
        "holding_bucket": normalize_text(holding_bucket) or None,
        "generator_mode": normalize_text(generator_mode) or None,
        "family_feedback_available": bool(family_bucket),
        "target_pool_feedback_available": bool(target_pool_bucket),
        "holding_bucket_feedback_available": bool(holding_bucket_bucket),
        "generator_mode_feedback_available": bool(generator_bucket),
    }
    defaults = {
        "ema_submit_count": 0.0,
        "paper_hit_ratio": 0.5,
        "paper_skill_lcb": 0.0,
        "paper_recent_skill_lcb": 0.0,
        "paper_stability_gap": 0.0,
        "paper_coverage_ratio": 1.0,
        "runtime_alert_pressure": 0.0,
        "realized_turnover": 0.0,
        "capacity_crowding": 0.0,
        "zero_signal_ratio": 0.0,
        "low_signal_ratio": 0.0,
        "forward_window_coverage_ratio": 1.0,
        "promotion_ready_ratio": 1.0,
        "promotion_review_coverage_ratio": 1.0,
        "evidence_debt_ratio": 0.0,
        "raw_validation_a_rate": 0.0,
        "raw_validation_b_rate": 0.0,
        "raw_validation_c_rate": 0.0,
        "raw_validation_d_rate": 0.0,
        "raw_validation_total_score_mean": 0.0,
        "strict_incubation_ready_rate": 0.0,
        "live_candidate_ready_rate": 0.0,
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
    legacy_budget_multiplier = compute_budget_multiplier(resolved)
    legacy_priority_adjustment = compute_priority_adjustment(resolved)
    legacy_failure_penalty_adjustment = compute_failure_penalty_adjustment(resolved)
    skill_budget_multiplier = compute_skill_budget_multiplier(resolved)
    skill_priority_adjustment = compute_skill_priority_adjustment(resolved)
    skill_failure_penalty_adjustment = compute_skill_failure_penalty_adjustment(resolved)
    highest_control = max(legacy_scope_controls, key=lambda item: int(item.get("severity") or 0))
    skill_highest_control = max(skill_scope_controls, key=lambda item: int(item.get("severity") or 0))
    control_reasons: list[str] = []
    for scope_control in legacy_scope_controls:
        for reason in list(scope_control.get("reasons") or []):
            if reason not in control_reasons:
                control_reasons.append(reason)
    skill_control_reasons: list[str] = []
    for scope_control in skill_scope_controls:
        for reason in list(scope_control.get("reasons") or []):
            if reason not in skill_control_reasons:
                skill_control_reasons.append(reason)
    legacy_control_mode = highest_control.get("mode") or "normal"
    skill_control_mode = skill_highest_control.get("mode") or "normal"
    (
        legacy_budget_multiplier,
        legacy_priority_adjustment,
        legacy_failure_penalty_adjustment,
    ) = _apply_control_mode_caps(
        control_mode=legacy_control_mode,
        budget_multiplier=legacy_budget_multiplier,
        priority_adjustment=legacy_priority_adjustment,
        failure_penalty_adjustment=legacy_failure_penalty_adjustment,
    )
    (
        skill_budget_multiplier,
        skill_priority_adjustment,
        skill_failure_penalty_adjustment,
    ) = _apply_control_mode_caps(
        control_mode=skill_control_mode,
        budget_multiplier=skill_budget_multiplier,
        priority_adjustment=skill_priority_adjustment,
        failure_penalty_adjustment=skill_failure_penalty_adjustment,
    )
    resolved["family_control_mode"] = family_control.get("mode")
    resolved["target_pool_control_mode"] = target_pool_control.get("mode")
    resolved["holding_bucket_control_mode"] = holding_bucket_control.get("mode")
    resolved["generator_mode_control_mode"] = generator_mode_control.get("mode")
    resolved["legacy_family_control_mode"] = family_control.get("mode")
    resolved["legacy_target_pool_control_mode"] = target_pool_control.get("mode")
    resolved["legacy_holding_bucket_control_mode"] = holding_bucket_control.get("mode")
    resolved["legacy_generator_mode_control_mode"] = generator_mode_control.get("mode")
    resolved["skill_family_control_mode"] = skill_family_control.get("mode")
    resolved["skill_target_pool_control_mode"] = skill_target_pool_control.get("mode")
    resolved["skill_holding_bucket_control_mode"] = skill_holding_bucket_control.get("mode")
    resolved["skill_generator_mode_control_mode"] = skill_generator_mode_control.get("mode")
    resolved["legacy_control_mode"] = legacy_control_mode
    resolved["skill_control_mode"] = skill_control_mode
    resolved["control_mode"] = legacy_control_mode
    resolved["effective_feedback_signal"] = "legacy_paper_hit_ratio"
    resolved["cooldown_active"] = bool(highest_control.get("severity", 0) >= 1)
    resolved["suppressed"] = bool(highest_control.get("severity", 0) >= 2)
    resolved["family_freeze_active"] = bool(family_control.get("freeze_active"))
    resolved["target_pool_freeze_active"] = bool(target_pool_control.get("freeze_active"))
    resolved["holding_bucket_freeze_active"] = bool(holding_bucket_control.get("freeze_active"))
    resolved["generator_mode_freeze_active"] = bool(generator_mode_control.get("freeze_active"))
    resolved["legacy_cooldown_active"] = bool(highest_control.get("severity", 0) >= 1)
    resolved["legacy_suppressed"] = bool(highest_control.get("severity", 0) >= 2)
    resolved["legacy_family_freeze_active"] = bool(family_control.get("freeze_active"))
    resolved["legacy_target_pool_freeze_active"] = bool(target_pool_control.get("freeze_active"))
    resolved["legacy_holding_bucket_freeze_active"] = bool(holding_bucket_control.get("freeze_active"))
    resolved["legacy_generator_mode_freeze_active"] = bool(generator_mode_control.get("freeze_active"))
    resolved["skill_cooldown_active"] = bool(skill_highest_control.get("severity", 0) >= 1)
    resolved["skill_suppressed"] = bool(skill_highest_control.get("severity", 0) >= 2)
    resolved["skill_family_freeze_active"] = bool(skill_family_control.get("freeze_active"))
    resolved["skill_target_pool_freeze_active"] = bool(skill_target_pool_control.get("freeze_active"))
    resolved["skill_holding_bucket_freeze_active"] = bool(
        skill_holding_bucket_control.get("freeze_active")
    )
    resolved["skill_generator_mode_freeze_active"] = bool(
        skill_generator_mode_control.get("freeze_active")
    )
    resolved["control_reasons"] = control_reasons
    resolved["legacy_control_reasons"] = control_reasons
    resolved["skill_control_reasons"] = skill_control_reasons
    resolved["budget_multiplier"] = legacy_budget_multiplier
    resolved["priority_adjustment"] = legacy_priority_adjustment
    resolved["failure_penalty_adjustment"] = legacy_failure_penalty_adjustment
    resolved["legacy_budget_multiplier"] = legacy_budget_multiplier
    resolved["legacy_priority_adjustment"] = legacy_priority_adjustment
    resolved["legacy_failure_penalty_adjustment"] = legacy_failure_penalty_adjustment
    resolved["skill_budget_multiplier"] = skill_budget_multiplier
    resolved["skill_priority_adjustment"] = skill_priority_adjustment
    resolved["skill_failure_penalty_adjustment"] = skill_failure_penalty_adjustment
    resolved["promotion_review_count"] = max(
        _safe_int(family_bucket.get("promotion_review_count")),
        _safe_int(target_pool_bucket.get("promotion_review_count")),
        _safe_int(holding_bucket_bucket.get("promotion_review_count")),
        _safe_int(generator_bucket.get("promotion_review_count")),
    )
    resolved["promotion_review_status"] = (
        normalize_text(generator_bucket.get("promotion_review_status"))
        or normalize_text(holding_bucket_bucket.get("promotion_review_status"))
        or normalize_text(target_pool_bucket.get("promotion_review_status"))
        or normalize_text(family_bucket.get("promotion_review_status"))
        or None
    )
    resolved["promotion_review_recommendation"] = (
        normalize_text(generator_bucket.get("promotion_review_recommendation"))
        or normalize_text(holding_bucket_bucket.get("promotion_review_recommendation"))
        or normalize_text(target_pool_bucket.get("promotion_review_recommendation"))
        or normalize_text(family_bucket.get("promotion_review_recommendation"))
        or None
    )
    resolved["promotion_review_score"] = round(
        max(
            safe_float(family_bucket.get("promotion_review_score"), 0.0),
            safe_float(target_pool_bucket.get("promotion_review_score"), 0.0),
            safe_float(holding_bucket_bucket.get("promotion_review_score"), 0.0),
            safe_float(generator_bucket.get("promotion_review_score"), 0.0),
        ),
        4,
    )
    return resolved


def resolve_task_feedback_metrics(
    snapshot_or_feedback: Any,
    *,
    task: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(task or {})
    family_candidates = extract_feedback_families(payload)
    target_pool_id = derive_target_pool_id(payload)
    holding_bucket = extract_holding_bucket(payload)
    generator_mode = extract_generator_mode(payload)
    if not family_candidates:
        family_candidates = ["unknown"]

    resolved_candidates = [
        resolve_feedback_metrics(
            snapshot_or_feedback,
            family=family,
            target_pool_id=target_pool_id,
            holding_bucket=holding_bucket,
            generator_mode=generator_mode,
        )
        for family in family_candidates
    ]
    resolved_candidates.sort(
        key=lambda item: (
            CONTROL_MODE_SEVERITY.get(normalize_text(item.get("control_mode")), 0),
            -safe_float(item.get("budget_multiplier"), 1.0),
            -safe_float(item.get("priority_adjustment"), 0.0),
            str(item.get("family") or ""),
        ),
        reverse=True,
    )
    selected = dict(resolved_candidates[0] or {})
    selected["family_candidates"] = list(family_candidates)
    selected["holding_bucket"] = selected.get("holding_bucket") or holding_bucket
    selected["family_control_modes"] = {
        str(item.get("family") or "unknown"): str(item.get("control_mode") or "normal")
        for item in resolved_candidates
    }
    return selected


def apply_feedback_controls_to_task(
    task: dict[str, Any] | None,
    snapshot_or_feedback: Any,
) -> dict[str, Any]:
    payload = dict(task or {})
    if not payload:
        return {}

    feedback = resolve_task_feedback_metrics(snapshot_or_feedback, task=payload)
    control_mode = normalize_text(feedback.get("control_mode")) or "normal"
    target_pool_control_mode = normalize_text(feedback.get("target_pool_control_mode")) or "normal"
    holding_bucket_control_mode = normalize_text(feedback.get("holding_bucket_control_mode")) or "normal"
    generator_mode_control_mode = normalize_text(feedback.get("generator_mode_control_mode")) or "normal"

    enriched = {
        **payload,
        "feedback_family": feedback.get("family"),
        "feedback_family_candidates": list(feedback.get("family_candidates") or []),
        "target_pool_id": feedback.get("target_pool_id") or derive_target_pool_id(payload),
        "holding_period_bucket": feedback.get("holding_bucket") or extract_holding_bucket(payload),
        "generator_mode": feedback.get("generator_mode") or extract_generator_mode(payload),
        "feedback_control_mode": control_mode,
        "feedback_legacy_control_mode": normalize_text(feedback.get("legacy_control_mode")) or control_mode,
        "feedback_skill_control_mode": normalize_text(feedback.get("skill_control_mode")) or "normal",
        "feedback_target_pool_control_mode": target_pool_control_mode,
        "feedback_holding_bucket_control_mode": holding_bucket_control_mode,
        "feedback_generator_mode_control_mode": generator_mode_control_mode,
        "feedback_skill_target_pool_control_mode": normalize_text(
            feedback.get("skill_target_pool_control_mode")
        )
        or "normal",
        "feedback_skill_holding_bucket_control_mode": normalize_text(
            feedback.get("skill_holding_bucket_control_mode")
        )
        or "normal",
        "feedback_skill_generator_mode_control_mode": normalize_text(
            feedback.get("skill_generator_mode_control_mode")
        )
        or "normal",
        "feedback_control_reasons": list(feedback.get("control_reasons") or []),
        "feedback_legacy_control_reasons": list(feedback.get("legacy_control_reasons") or []),
        "feedback_skill_control_reasons": list(feedback.get("skill_control_reasons") or []),
        "feedback_cooldown_active": bool(feedback.get("cooldown_active")),
        "feedback_suppressed": bool(feedback.get("suppressed")),
        "feedback_family_freeze_active": bool(feedback.get("family_freeze_active")),
        "feedback_target_pool_freeze_active": bool(feedback.get("target_pool_freeze_active")),
        "feedback_holding_bucket_freeze_active": bool(feedback.get("holding_bucket_freeze_active")),
        "feedback_generator_mode_freeze_active": bool(feedback.get("generator_mode_freeze_active")),
        "feedback_skill_cooldown_active": bool(feedback.get("skill_cooldown_active")),
        "feedback_skill_suppressed": bool(feedback.get("skill_suppressed")),
        "feedback_skill_family_freeze_active": bool(feedback.get("skill_family_freeze_active")),
        "feedback_skill_target_pool_freeze_active": bool(
            feedback.get("skill_target_pool_freeze_active")
        ),
        "feedback_skill_holding_bucket_freeze_active": bool(
            feedback.get("skill_holding_bucket_freeze_active")
        ),
        "feedback_skill_generator_mode_freeze_active": bool(
            feedback.get("skill_generator_mode_freeze_active")
        ),
        "feedback_budget_multiplier": safe_float(feedback.get("legacy_budget_multiplier"), 1.0),
        "feedback_priority_adjustment": safe_float(feedback.get("legacy_priority_adjustment")),
        "feedback_failure_penalty_adjustment": safe_float(
            feedback.get("legacy_failure_penalty_adjustment")
        ),
        "feedback_legacy_budget_multiplier": safe_float(
            feedback.get("legacy_budget_multiplier"),
            1.0,
        ),
        "feedback_legacy_priority_adjustment": safe_float(
            feedback.get("legacy_priority_adjustment")
        ),
        "feedback_skill_budget_multiplier": safe_float(
            feedback.get("skill_budget_multiplier"),
            1.0,
        ),
        "feedback_skill_priority_adjustment": safe_float(
            feedback.get("skill_priority_adjustment")
        ),
        "feedback_skill_failure_penalty_adjustment": safe_float(
            feedback.get("skill_failure_penalty_adjustment")
        ),
        "feedback_effective_signal": feedback.get("effective_feedback_signal") or "legacy_paper_hit_ratio",
        "feedback_metrics": feedback,
    }

    try:
        original_priority = int(enriched.get("priority") or 0)
    except Exception:
        original_priority = 0
    try:
        original_generation_limit = int(enriched.get("generation_limit") or 0)
    except Exception:
        original_generation_limit = 0

    if control_mode == "cooldown":
        adjusted_priority = original_priority + int(round(safe_float(feedback.get("priority_adjustment"), -6.0)))
        enriched["priority"] = max(1, adjusted_priority) if original_priority > 0 else max(1, adjusted_priority)
        if original_generation_limit > 0:
            enriched["generation_limit"] = max(1, min(original_generation_limit, 1))
        enriched["feedback_generation_limited"] = True
    elif control_mode in {"suppress", "freeze"}:
        enriched["feedback_generation_blocked"] = True
        enriched["feedback_generation_block_reason"] = control_mode

    return enriched


def _extract_control_reasons(payload: dict[str, Any] | None) -> list[str]:
    item = dict(payload or {})
    raw_reasons = item.get("feedback_control_reasons")
    if raw_reasons is None:
        raw_reasons = item.get("control_reasons")
    return [
        normalize_text(reason)
        for reason in list(raw_reasons or [])
        if normalize_text(reason)
    ]


def _uses_bulk_matrix_plan(payload: dict[str, Any] | None) -> bool:
    item = dict(payload or {})
    if normalize_text(item.get("task_source")) != "bulk_stock_matrix":
        return False
    for key in (
        "matrix_budget_slot",
        "matrix_plan_slot",
        "matrix_allocation_pass",
        "matrix_family_rank",
        "matrix_stock_rank",
        "matrix_shard_id",
        "matrix_batch_id",
    ):
        try:
            if int(item.get(key) or 0) > 0:
                return True
        except Exception:
            continue
    if safe_float(item.get("stock_family_priority"), 0.0) > 0.0:
        return True
    return bool(item.get("stock_family_allocation_source"))


def _resolve_research_task_source(payload: dict[str, Any] | None) -> str:
    item = dict(payload or {})
    research_task = dict(item.get("research_task") or {})
    return normalize_text(item.get("task_source") or research_task.get("task_source"))


def _supports_relaxed_research_backlog_control(payload: dict[str, Any] | None) -> bool:
    task_source = _resolve_research_task_source(payload)
    return task_source in {"bulk_stock_matrix", "snapshot"}


def resolve_relaxed_research_control_mode(payload: dict[str, Any] | None = None) -> str:
    item = dict(payload or {})
    if _resolve_research_task_source(item) in {"bulk_stock_matrix", "snapshot"}:
        return "normal"
    if _uses_bulk_matrix_plan(payload):
        return "normal"
    return "cooldown"


def _resolve_research_control_relax_reason(
    payload: dict[str, Any] | None,
    *,
    relaxed_mode: str,
) -> str:
    task_source = _resolve_research_task_source(payload)
    lane = "snapshot_research" if task_source == "snapshot" else "bulk_research"
    return (
        f"{lane}_backlog_normal_throttle"
        if relaxed_mode == "normal"
        else f"{lane}_backlog_cooldown"
    )


def is_relaxable_feedback_backlog_control(payload: dict[str, Any] | None) -> bool:
    reasons = _extract_control_reasons(payload)
    if not reasons:
        return False
    if any(
        any(marker in reason for marker in HARD_RESEARCH_CONTROL_REASON_MARKERS)
        for reason in reasons
    ):
        return False
    return all(
        any(marker in reason for marker in RELAXABLE_RESEARCH_CONTROL_REASON_MARKERS)
        for reason in reasons
    )


def relax_feedback_control_for_research_task(
    task: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(task or {})
    if not payload:
        return {}
    if not FACTORY_BACKLOG_RELAX_ENABLED:
        return payload

    if not _supports_relaxed_research_backlog_control(payload):
        return payload

    control_mode = normalize_text(payload.get("feedback_control_mode")) or "normal"
    if control_mode not in {"suppress", "freeze"}:
        return payload
    if not is_relaxable_feedback_backlog_control(payload):
        return payload

    relaxed = dict(payload)
    relaxed_mode = resolve_relaxed_research_control_mode(relaxed)
    relaxed["feedback_control_original_mode"] = control_mode
    relaxed["feedback_control_mode"] = relaxed_mode
    relaxed["feedback_generation_blocked"] = False
    relaxed.pop("feedback_generation_block_reason", None)
    relaxed["feedback_generation_limited"] = True
    relaxed["feedback_relaxed_throttle_active"] = True
    relaxed["feedback_control_relaxed"] = True
    relaxed["feedback_control_relaxed_mode"] = relaxed_mode
    relaxed["feedback_control_relax_reason"] = _resolve_research_control_relax_reason(
        relaxed,
        relaxed_mode=relaxed_mode,
    )

    try:
        generation_limit = int(relaxed.get("generation_limit") or 0)
    except Exception:
        generation_limit = 0
    relaxed["generation_limit"] = 1 if generation_limit <= 0 else max(1, min(generation_limit, 1))

    try:
        priority = int(relaxed.get("priority") or 0)
    except Exception:
        priority = 0
    if priority > 0:
        relaxed["priority"] = max(1, priority - int(FACTORY_BACKLOG_RELAX_PRIORITY_PENALTY))

    feedback_metrics = dict(relaxed.get("feedback_metrics") or {})
    if feedback_metrics:
        feedback_metrics["control_mode"] = relaxed_mode
        feedback_metrics["cooldown_active"] = relaxed_mode == "cooldown"
        feedback_metrics["suppressed"] = False
        feedback_metrics["relaxed_throttle_active"] = True
        relaxed["feedback_metrics"] = feedback_metrics

    reasons = _extract_control_reasons(relaxed)
    relax_reason = str(relaxed.get("feedback_control_relax_reason") or "").strip()
    if relax_reason and relax_reason not in reasons:
        reasons.append(relax_reason)
    relaxed["feedback_control_reasons"] = reasons
    return relaxed


def summarize_task_feedback_controls(tasks: list[dict[str, Any]] | None) -> dict[str, Any]:
    control_mode_counts: dict[str, int] = {}
    legacy_control_mode_counts: dict[str, int] = {}
    skill_control_mode_counts: dict[str, int] = {}
    target_pool_control_mode_counts: dict[str, int] = {}
    holding_bucket_control_mode_counts: dict[str, int] = {}
    generator_mode_control_mode_counts: dict[str, int] = {}
    skill_target_pool_control_mode_counts: dict[str, int] = {}
    skill_holding_bucket_control_mode_counts: dict[str, int] = {}
    skill_generator_mode_control_mode_counts: dict[str, int] = {}
    suppressed_families: list[str] = []
    suppressed_target_pools: list[str] = []
    suppressed_holding_buckets: list[str] = []
    suppressed_generator_modes: list[str] = []
    blocked_task_count = 0
    cooldown_task_count = 0
    limited_task_count = 0
    relaxed_task_count = 0

    def _append_unique(bucket: list[str], value: Any) -> None:
        token = str(value or "").strip()
        if token and token not in bucket:
            bucket.append(token)

    for item in list(tasks or []):
        task = dict(item or {})
        control_mode = normalize_text(task.get("feedback_control_mode")) or "normal"
        legacy_control_mode = (
            normalize_text(task.get("feedback_legacy_control_mode")) or control_mode
        )
        skill_control_mode = normalize_text(task.get("feedback_skill_control_mode")) or "normal"
        target_pool_control_mode = normalize_text(task.get("feedback_target_pool_control_mode")) or "normal"
        holding_bucket_control_mode = (
            normalize_text(task.get("feedback_holding_bucket_control_mode")) or "normal"
        )
        generator_mode_control_mode = normalize_text(task.get("feedback_generator_mode_control_mode")) or "normal"
        skill_target_pool_control_mode = (
            normalize_text(task.get("feedback_skill_target_pool_control_mode")) or "normal"
        )
        skill_holding_bucket_control_mode = (
            normalize_text(task.get("feedback_skill_holding_bucket_control_mode")) or "normal"
        )
        skill_generator_mode_control_mode = (
            normalize_text(task.get("feedback_skill_generator_mode_control_mode")) or "normal"
        )
        control_mode_counts[control_mode] = control_mode_counts.get(control_mode, 0) + 1
        legacy_control_mode_counts[legacy_control_mode] = (
            legacy_control_mode_counts.get(legacy_control_mode, 0) + 1
        )
        skill_control_mode_counts[skill_control_mode] = (
            skill_control_mode_counts.get(skill_control_mode, 0) + 1
        )
        target_pool_control_mode_counts[target_pool_control_mode] = (
            target_pool_control_mode_counts.get(target_pool_control_mode, 0) + 1
        )
        holding_bucket_control_mode_counts[holding_bucket_control_mode] = (
            holding_bucket_control_mode_counts.get(holding_bucket_control_mode, 0) + 1
        )
        generator_mode_control_mode_counts[generator_mode_control_mode] = (
            generator_mode_control_mode_counts.get(generator_mode_control_mode, 0) + 1
        )
        skill_target_pool_control_mode_counts[skill_target_pool_control_mode] = (
            skill_target_pool_control_mode_counts.get(skill_target_pool_control_mode, 0) + 1
        )
        skill_holding_bucket_control_mode_counts[skill_holding_bucket_control_mode] = (
            skill_holding_bucket_control_mode_counts.get(skill_holding_bucket_control_mode, 0) + 1
        )
        skill_generator_mode_control_mode_counts[skill_generator_mode_control_mode] = (
            skill_generator_mode_control_mode_counts.get(skill_generator_mode_control_mode, 0) + 1
        )
        if control_mode == "cooldown":
            cooldown_task_count += 1
        if bool(task.get("feedback_generation_limited")):
            limited_task_count += 1
        if bool(task.get("feedback_control_relaxed")):
            relaxed_task_count += 1
        if control_mode in {"suppress", "freeze"} or bool(task.get("feedback_generation_blocked")):
            blocked_task_count += 1
            _append_unique(
                suppressed_families,
                task.get("feedback_family")
                or (task.get("feedback_family_candidates") or [None])[0],
            )
            _append_unique(suppressed_target_pools, task.get("target_pool_id"))
            _append_unique(suppressed_holding_buckets, task.get("holding_period_bucket"))
            _append_unique(suppressed_generator_modes, task.get("generator_mode"))

    return {
        "feedback_control_mode_counts": control_mode_counts,
        "feedback_legacy_control_mode_counts": legacy_control_mode_counts,
        "feedback_skill_control_mode_counts": skill_control_mode_counts,
        "feedback_target_pool_control_mode_counts": target_pool_control_mode_counts,
        "feedback_holding_bucket_control_mode_counts": holding_bucket_control_mode_counts,
        "feedback_generator_mode_control_mode_counts": generator_mode_control_mode_counts,
        "feedback_skill_target_pool_control_mode_counts": skill_target_pool_control_mode_counts,
        "feedback_skill_holding_bucket_control_mode_counts": skill_holding_bucket_control_mode_counts,
        "feedback_skill_generator_mode_control_mode_counts": (
            skill_generator_mode_control_mode_counts
        ),
        "feedback_cooldown_task_count": cooldown_task_count,
        "feedback_limited_task_count": limited_task_count,
        "feedback_relaxed_task_count": relaxed_task_count,
        "feedback_blocked_task_count": blocked_task_count,
        "suppressed_families": suppressed_families,
        "suppressed_target_pools": suppressed_target_pools,
        "suppressed_holding_buckets": suppressed_holding_buckets,
        "suppressed_generator_modes": suppressed_generator_modes,
    }


def collect_generator_mode_feedback_controls(
    snapshot_or_feedback: Any,
) -> dict[str, dict[str, Any]]:
    feedback_root = extract_feedback_root(snapshot_or_feedback)
    controls: dict[str, dict[str, Any]] = {}
    for family_name, raw_bucket in feedback_root.items():
        normalized_family = normalize_text(family_name) or "unknown"
        family_bucket = dict(raw_bucket or {})
        generator_scope = dict(family_bucket.get("generator_mode_feedback") or {})
        for mode_name, mode_bucket in generator_scope.items():
            normalized_mode = normalize_text(mode_name)
            if not normalized_mode:
                continue
            scope_control = _derive_scope_control(
                dict(mode_bucket or {}),
                scope_name="generator_mode",
            )
            incoming_severity = int(scope_control.get("severity") or 0)
            existing = dict(controls.get(normalized_mode) or {})
            existing_mode = normalize_text(existing.get("control_mode")) or "normal"
            existing_severity = CONTROL_MODE_SEVERITY.get(existing_mode, 0)
            merged_reasons: list[str] = []
            for reason in [*list(existing.get("control_reasons") or []), *list(scope_control.get("reasons") or [])]:
                token = str(reason or "").strip()
                if token and token not in merged_reasons:
                    merged_reasons.append(token)
            families: list[str] = []
            for value in [*list(existing.get("families") or []), normalized_family]:
                token = normalize_text(value)
                if token and token not in families:
                    families.append(token)
            winner_mode = existing_mode
            if incoming_severity >= existing_severity:
                winner_mode = normalize_text(scope_control.get("mode")) or winner_mode
            skill_scope_control = _derive_skill_scope_control(
                dict(mode_bucket or {}),
                scope_name="generator_mode",
            )
            controls[normalized_mode] = {
                "control_mode": winner_mode or "normal",
                "legacy_control_mode": winner_mode or "normal",
                "skill_control_mode": normalize_text(skill_scope_control.get("mode")) or "normal",
                "control_reasons": merged_reasons,
                "legacy_control_reasons": merged_reasons,
                "skill_control_reasons": list(skill_scope_control.get("reasons") or []),
                "families": families,
                "feedback_observed_count": int(existing.get("feedback_observed_count") or 0) + 1,
                "source": "lifecycle_feedback",
            }
    return controls


def _apply_control_mode_caps(
    *,
    control_mode: str,
    budget_multiplier: float,
    priority_adjustment: float,
    failure_penalty_adjustment: float,
) -> tuple[float, float, float]:
    resolved_budget_multiplier = round(float(budget_multiplier), 4)
    resolved_priority_adjustment = round(float(priority_adjustment), 4)
    resolved_failure_penalty_adjustment = round(float(failure_penalty_adjustment), 4)
    normalized_mode = normalize_text(control_mode) or "normal"
    if normalized_mode == "cooldown":
        resolved_budget_multiplier = round(min(resolved_budget_multiplier, 0.55), 4)
        resolved_priority_adjustment = round(min(resolved_priority_adjustment, -6.0), 4)
        resolved_failure_penalty_adjustment = round(
            max(resolved_failure_penalty_adjustment, 0.12),
            4,
        )
    elif normalized_mode == "suppress":
        resolved_budget_multiplier = 0.0
        resolved_priority_adjustment = round(min(resolved_priority_adjustment, -18.0), 4)
        resolved_failure_penalty_adjustment = round(
            max(resolved_failure_penalty_adjustment, 0.22),
            4,
        )
    elif normalized_mode == "freeze":
        resolved_budget_multiplier = 0.0
        resolved_priority_adjustment = round(min(resolved_priority_adjustment, -24.0), 4)
        resolved_failure_penalty_adjustment = round(
            max(resolved_failure_penalty_adjustment, 0.3),
            4,
        )
    return (
        resolved_budget_multiplier,
        resolved_priority_adjustment,
        resolved_failure_penalty_adjustment,
    )


def _build_skill_feedback_proxy(metrics: dict[str, Any]) -> dict[str, Any]:
    proxy = dict(metrics or {})
    paper_skill_lcb = _clamp(safe_float(metrics.get("paper_skill_lcb"), 0.0), -1.0, 1.0)
    paper_coverage_ratio = _clamp(
        safe_float(metrics.get("paper_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    forward_window_coverage_ratio = _clamp(
        safe_float(metrics.get("forward_window_coverage_ratio"), 1.0),
        0.0,
        1.0,
    )
    proxy["paper_hit_ratio"] = _clamp(0.5 + paper_skill_lcb, 0.0, 1.0)
    proxy["forward_window_coverage_ratio"] = min(
        forward_window_coverage_ratio,
        paper_coverage_ratio,
    )
    return proxy


def compute_budget_multiplier(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    zero_signal_ratio = max(0.0, min(safe_float(metrics.get("zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(metrics.get("low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(0.0, min(safe_float(metrics.get("evidence_debt_ratio"), 0.0), 1.0))
    raw_validation_a_rate = max(0.0, min(safe_float(metrics.get("raw_validation_a_rate"), 0.0), 1.0))
    raw_validation_b_rate = max(0.0, min(safe_float(metrics.get("raw_validation_b_rate"), 0.0), 1.0))
    raw_validation_d_rate = max(0.0, min(safe_float(metrics.get("raw_validation_d_rate"), 1.0), 1.0))
    raw_validation_total_score_mean = max(
        0.0,
        min(safe_float(metrics.get("raw_validation_total_score_mean"), 0.0), 100.0),
    )
    strict_incubation_ready_rate = max(
        0.0,
        min(safe_float(metrics.get("strict_incubation_ready_rate"), 0.0), 1.0),
    )
    ema_submit_count = max(0.0, min(safe_float(metrics.get("ema_submit_count"), 0.0), 8.0))
    promotion_review_count = _safe_int(metrics.get("promotion_review_count"))
    promotion_review_score = max(0.0, min(safe_float(metrics.get("promotion_review_score"), 0.5), 1.0))
    promotion_review_status = normalize_text(metrics.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(metrics.get("promotion_review_recommendation"))

    paper_bonus = (paper_hit_ratio - 0.5) * 0.7
    turnover_penalty = max(realized_turnover - 0.55, 0.0) * 0.25
    crowding_penalty = max(capacity_crowding - 0.45, 0.0) * 0.22
    evidence_penalty = (
        zero_signal_ratio * 0.28
        + low_signal_ratio * 0.08
        + max(0.55 - forward_window_coverage_ratio, 0.0) * 0.30
        + max(0.45 - promotion_ready_ratio, 0.0) * 0.18
        + max(0.30 - promotion_review_coverage_ratio, 0.0) * 0.12
        + evidence_debt_ratio * 0.22
    )
    ab_quality_bonus = (
        raw_validation_a_rate * 0.28
        + raw_validation_b_rate * 0.18
        + strict_incubation_ready_rate * 0.16
        + max(raw_validation_total_score_mean - 55.0, 0.0) / 45.0 * 0.18
    )
    low_quality_penalty = (
        raw_validation_d_rate * 0.24
        + max(0.30 - (raw_validation_a_rate + raw_validation_b_rate), 0.0) * 0.22
    )
    submit_bonus = min(ema_submit_count / 10.0, 0.12)
    promotion_review_adjustment = 0.0
    if promotion_review_count > 0:
        promotion_review_adjustment += (promotion_review_score - 0.5) * 0.18
        if promotion_review_status == "approved" or promotion_review_recommendation == "promote":
            promotion_review_adjustment += 0.05
        elif promotion_review_status == "watch" or promotion_review_recommendation == "observe":
            promotion_review_adjustment -= 0.06
        elif promotion_review_status == "rejected" or promotion_review_recommendation == "deprecate":
            promotion_review_adjustment -= 0.18
    multiplier = (
        1.0
        + paper_bonus
        - runtime_alert_pressure * 0.42
        - turnover_penalty
        - crowding_penalty
        - evidence_penalty
        + ab_quality_bonus
        - low_quality_penalty
        + submit_bonus
        + promotion_review_adjustment
    )
    return round(min(max(multiplier, 0.4), 1.75), 4)


def compute_skill_budget_multiplier(metrics: dict[str, Any]) -> float:
    proxy = _build_skill_feedback_proxy(metrics)
    paper_recent_skill_lcb = _clamp(
        safe_float(metrics.get("paper_recent_skill_lcb"), metrics.get("paper_skill_lcb")),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(safe_float(metrics.get("paper_stability_gap"), 0.0), 0.0, 1.0)
    paper_coverage_ratio = _clamp(safe_float(metrics.get("paper_coverage_ratio"), 1.0), 0.0, 1.0)
    multiplier = compute_budget_multiplier(proxy)
    multiplier += paper_recent_skill_lcb * 0.45
    multiplier -= max(paper_stability_gap - 0.05, 0.0) * 1.15
    multiplier -= max(0.60 - paper_coverage_ratio, 0.0) * 0.32
    return round(min(max(multiplier, 0.3), 1.75), 4)


def compute_priority_adjustment(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    zero_signal_ratio = max(0.0, min(safe_float(metrics.get("zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(metrics.get("low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(0.0, min(safe_float(metrics.get("evidence_debt_ratio"), 0.0), 1.0))
    raw_validation_a_rate = max(0.0, min(safe_float(metrics.get("raw_validation_a_rate"), 0.0), 1.0))
    raw_validation_b_rate = max(0.0, min(safe_float(metrics.get("raw_validation_b_rate"), 0.0), 1.0))
    raw_validation_d_rate = max(0.0, min(safe_float(metrics.get("raw_validation_d_rate"), 1.0), 1.0))
    raw_validation_total_score_mean = max(
        0.0,
        min(safe_float(metrics.get("raw_validation_total_score_mean"), 0.0), 100.0),
    )
    strict_incubation_ready_rate = max(
        0.0,
        min(safe_float(metrics.get("strict_incubation_ready_rate"), 0.0), 1.0),
    )
    ema_submit_count = max(0.0, min(safe_float(metrics.get("ema_submit_count"), 0.0), 8.0))
    promotion_review_count = _safe_int(metrics.get("promotion_review_count"))
    promotion_review_score = max(0.0, min(safe_float(metrics.get("promotion_review_score"), 0.5), 1.0))
    promotion_review_status = normalize_text(metrics.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(metrics.get("promotion_review_recommendation"))

    turnover_penalty = max(realized_turnover - 0.55, 0.0)
    crowding_penalty = max(capacity_crowding - 0.45, 0.0)
    promotion_review_adjustment = 0.0
    if promotion_review_count > 0:
        promotion_review_adjustment += (promotion_review_score - 0.5) * 6.0
        if promotion_review_status == "approved" or promotion_review_recommendation == "promote":
            promotion_review_adjustment += 3.0
        elif promotion_review_status == "watch" or promotion_review_recommendation == "observe":
            promotion_review_adjustment -= 5.0
        elif promotion_review_status == "rejected" or promotion_review_recommendation == "deprecate":
            promotion_review_adjustment -= 10.0
    adjustment = (
        (paper_hit_ratio - 0.5) * 14.0
        - runtime_alert_pressure * 8.5
        - turnover_penalty * 5.0
        - crowding_penalty * 4.5
        - zero_signal_ratio * 10.0
        - low_signal_ratio * 3.0
        - max(0.55 - forward_window_coverage_ratio, 0.0) * 8.0
        - max(0.40 - promotion_ready_ratio, 0.0) * 6.0
        - max(0.25 - promotion_review_coverage_ratio, 0.0) * 4.0
        - evidence_debt_ratio * 7.0
        + raw_validation_a_rate * 11.0
        + raw_validation_b_rate * 7.0
        + strict_incubation_ready_rate * 6.0
        + max(raw_validation_total_score_mean - 55.0, 0.0) / 45.0 * 5.0
        - raw_validation_d_rate * 9.0
        - max(0.30 - (raw_validation_a_rate + raw_validation_b_rate), 0.0) * 8.0
        + min(ema_submit_count, 6.0) * 0.75
        + promotion_review_adjustment
    )
    return round(adjustment, 4)


def compute_skill_priority_adjustment(metrics: dict[str, Any]) -> float:
    proxy = _build_skill_feedback_proxy(metrics)
    paper_recent_skill_lcb = _clamp(
        safe_float(metrics.get("paper_recent_skill_lcb"), metrics.get("paper_skill_lcb")),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(safe_float(metrics.get("paper_stability_gap"), 0.0), 0.0, 1.0)
    paper_coverage_ratio = _clamp(safe_float(metrics.get("paper_coverage_ratio"), 1.0), 0.0, 1.0)
    adjustment = compute_priority_adjustment(proxy)
    adjustment += paper_recent_skill_lcb * 9.0
    adjustment -= max(paper_stability_gap - 0.05, 0.0) * 24.0
    adjustment -= max(0.60 - paper_coverage_ratio, 0.0) * 7.0
    return round(adjustment, 4)


def compute_failure_penalty_adjustment(metrics: dict[str, Any]) -> float:
    paper_hit_ratio = max(0.0, min(safe_float(metrics.get("paper_hit_ratio"), 0.5), 1.0))
    runtime_alert_pressure = max(0.0, min(safe_float(metrics.get("runtime_alert_pressure"), 0.0), 1.0))
    realized_turnover = max(0.0, min(safe_float(metrics.get("realized_turnover"), 0.0), 2.0))
    capacity_crowding = max(0.0, min(safe_float(metrics.get("capacity_crowding"), 0.0), 2.0))
    zero_signal_ratio = max(0.0, min(safe_float(metrics.get("zero_signal_ratio"), 0.0), 1.0))
    low_signal_ratio = max(0.0, min(safe_float(metrics.get("low_signal_ratio"), 0.0), 1.0))
    forward_window_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("forward_window_coverage_ratio"), 1.0), 1.0),
    )
    promotion_ready_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_ready_ratio"), 1.0), 1.0),
    )
    promotion_review_coverage_ratio = max(
        0.0,
        min(safe_float(metrics.get("promotion_review_coverage_ratio"), 1.0), 1.0),
    )
    evidence_debt_ratio = max(0.0, min(safe_float(metrics.get("evidence_debt_ratio"), 0.0), 1.0))
    raw_validation_a_rate = max(0.0, min(safe_float(metrics.get("raw_validation_a_rate"), 0.0), 1.0))
    raw_validation_b_rate = max(0.0, min(safe_float(metrics.get("raw_validation_b_rate"), 0.0), 1.0))
    raw_validation_d_rate = max(0.0, min(safe_float(metrics.get("raw_validation_d_rate"), 1.0), 1.0))
    raw_validation_total_score_mean = max(
        0.0,
        min(safe_float(metrics.get("raw_validation_total_score_mean"), 0.0), 100.0),
    )
    strict_incubation_ready_rate = max(
        0.0,
        min(safe_float(metrics.get("strict_incubation_ready_rate"), 0.0), 1.0),
    )
    promotion_review_count = _safe_int(metrics.get("promotion_review_count"))
    promotion_review_score = max(0.0, min(safe_float(metrics.get("promotion_review_score"), 0.5), 1.0))
    promotion_review_status = normalize_text(metrics.get("promotion_review_status"))
    promotion_review_recommendation = normalize_text(metrics.get("promotion_review_recommendation"))

    turnover_penalty = max(realized_turnover - 0.55, 0.0) * 0.08
    crowding_penalty = max(capacity_crowding - 0.45, 0.0) * 0.06
    paper_credit = max(paper_hit_ratio - 0.55, 0.0) * 0.08
    promotion_review_penalty = 0.0
    if promotion_review_count > 0:
        promotion_review_penalty += max(0.5 - promotion_review_score, 0.0) * 0.12
        if promotion_review_status == "watch" or promotion_review_recommendation == "observe":
            promotion_review_penalty += 0.08
        elif promotion_review_status == "rejected" or promotion_review_recommendation == "deprecate":
            promotion_review_penalty += 0.14
        elif promotion_review_status == "approved" or promotion_review_recommendation == "promote":
            promotion_review_penalty -= 0.03
    adjustment = (
        runtime_alert_pressure * 0.12
        + turnover_penalty
        + crowding_penalty
        + zero_signal_ratio * 0.06
        + low_signal_ratio * 0.03
        + max(0.55 - forward_window_coverage_ratio, 0.0) * 0.08
        + max(0.40 - promotion_ready_ratio, 0.0) * 0.06
        + max(0.25 - promotion_review_coverage_ratio, 0.0) * 0.04
        + evidence_debt_ratio * 0.05
        + raw_validation_d_rate * 0.12
        + max(0.25 - (raw_validation_a_rate + raw_validation_b_rate), 0.0) * 0.08
        + max(50.0 - raw_validation_total_score_mean, 0.0) / 50.0 * 0.07
        - paper_credit
        - raw_validation_a_rate * 0.04
        - raw_validation_b_rate * 0.03
        - strict_incubation_ready_rate * 0.04
        + promotion_review_penalty
    )
    return round(min(max(adjustment, -0.06), 0.22), 4)


def compute_skill_failure_penalty_adjustment(metrics: dict[str, Any]) -> float:
    proxy = _build_skill_feedback_proxy(metrics)
    paper_skill_lcb = _clamp(safe_float(metrics.get("paper_skill_lcb"), 0.0), -1.0, 1.0)
    paper_recent_skill_lcb = _clamp(
        safe_float(metrics.get("paper_recent_skill_lcb"), paper_skill_lcb),
        -1.0,
        1.0,
    )
    paper_stability_gap = _clamp(safe_float(metrics.get("paper_stability_gap"), 0.0), 0.0, 1.0)
    paper_coverage_ratio = _clamp(safe_float(metrics.get("paper_coverage_ratio"), 1.0), 0.0, 1.0)
    adjustment = compute_failure_penalty_adjustment(proxy)
    adjustment += max(0.0 - paper_recent_skill_lcb, 0.0) * 0.14
    adjustment += max(paper_stability_gap - 0.05, 0.0) * 0.28
    adjustment += max(0.60 - paper_coverage_ratio, 0.0) * 0.08
    adjustment -= max(paper_skill_lcb, 0.0) * 0.05
    return round(min(max(adjustment, -0.06), 0.24), 4)


__all__ = [
    "CONTROL_MODE_SEVERITY",
    "LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION",
    "apply_feedback_controls_to_task",
    "FEEDBACK_METRIC_KEYS",
    "compute_budget_multiplier",
    "compute_failure_penalty_adjustment",
    "compute_priority_adjustment",
    "compute_skill_budget_multiplier",
    "compute_skill_failure_penalty_adjustment",
    "compute_skill_priority_adjustment",
    "collect_generator_mode_feedback_controls",
    "derive_target_pool_id",
    "extract_feedback_root",
    "extract_feedback_families",
    "extract_generator_mode",
    "extract_holding_bucket",
    "extract_target_pool_id",
    "is_relaxable_feedback_backlog_control",
    "normalize_feedback_input_contract",
    "normalize_text",
    "relax_feedback_control_for_research_task",
    "resolve_feedback_metrics",
    "resolve_task_feedback_metrics",
    "safe_float",
    "summarize_task_feedback_controls",
]
