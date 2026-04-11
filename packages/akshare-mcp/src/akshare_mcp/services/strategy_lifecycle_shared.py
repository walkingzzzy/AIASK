"""Shared strategy lifecycle primitives used by both services and tools layers.

This module exists to break the circular dependency where services
(promotion_pipeline, incubation, runtime_control) imported from the
tools layer (tools.managers.strategy_manager).  Now both sides import
from this services-level module instead.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from strategy_factory import (
    DEPRECATION_THRESHOLDS,
    PROMOTION_THRESHOLDS,
)

logger = logging.getLogger(__name__)

# ── Lifecycle state machine ──────────────────────────────────────────────────

LIFECYCLE_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["submitted"],
    "submitted": ["incubating", "rejected"],
    "rejected": ["draft"],
    "incubating": ["listed", "deprecated", "suspended"],
    "listed": ["deprecated", "suspended", "archived"],
    "suspended": ["listed", "deprecated", "incubating"],
    "deprecated": [],
    "published": ["deprecated", "suspended", "archived", "listed"],
    "archived": [],
}


def normalize_status_alias(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    return "listed" if normalized == "published" else normalized


def validate_transition(current: str, target: str) -> bool:
    current_normalized = normalize_status_alias(current)
    target_normalized = normalize_status_alias(target)
    return target_normalized in LIFECYCLE_TRANSITIONS.get(current_normalized, [])


async def update_status(db, strategy_id: str, status: str, **kwargs) -> None:
    normalized = normalize_status_alias(status)
    try:
        await db.update_strategy_status(strategy_id, normalized, **kwargs)
    except TypeError:
        await db.update_strategy_status(strategy_id, normalized)


# ── Quality report helpers ───────────────────────────────────────────────────

def metric_bucket_value(metric: Optional[dict], key: int) -> Optional[float]:
    if not metric:
        return None
    value = metric.get(key)
    if value is None:
        value = metric.get(str(key))
    return None if value is None else float(value)


def _quality_report_field(
    quality_report: Optional[dict],
    quality_gate: Optional[dict],
    summary: Optional[dict],
    key: str,
) -> Any:
    for payload in (dict(quality_report or {}), dict(quality_gate or {}), dict(summary or {})):
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _quality_report_bool(
    quality_report: Optional[dict],
    quality_gate: Optional[dict],
    summary: Optional[dict],
    key: str,
) -> Optional[bool]:
    sentinel = object()
    value = sentinel
    for payload in (dict(quality_report or {}), dict(quality_gate or {}), dict(summary or {})):
        if key in payload and payload.get(key) is not None:
            value = payload.get(key)
            break
    if value is sentinel:
        return None
    return bool(value)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


async def list_quality_reports(db, strategy_id: str, limit: int = 10) -> list[dict]:
    if hasattr(db, "list_strategy_quality_reports"):
        return await db.list_strategy_quality_reports(strategy_id, limit=limit)
    latest = None
    if hasattr(db, "get_latest_strategy_quality_report"):
        latest = await db.get_latest_strategy_quality_report(strategy_id)
    elif hasattr(db, "get_strategy_quality_report"):
        latest = await db.get_strategy_quality_report(strategy_id)
    return [latest] if latest else []


async def get_latest_quality_report(db, strategy_id: str) -> Optional[dict]:
    rows = await list_quality_reports(db, strategy_id, limit=1)
    return rows[0] if rows else None


# ── Incubation overview builder ──────────────────────────────────────────────

async def build_incubation_overview(db, strategy: dict) -> dict:
    metrics = await db.get_strategy_metrics(strategy["id"])
    all_m = next((m for m in metrics if m.get("period") == "all"), {})
    backtest_m = next((m for m in metrics if m.get("period") == "backtest"), all_m)
    quality_report = await get_latest_quality_report(db, strategy["id"])
    quality_gate = dict((quality_report or {}).get("quality_gate") or {})
    quality_summary = dict((quality_report or {}).get("summary") or {})
    validation_report = dict((quality_report or {}).get("validation_report") or {})
    validation_rating = dict(validation_report.get("rating") or {})
    validation_profile = dict((quality_report or {}).get("validation_profile") or {})
    signal_stats = await db.get_signal_stats(strategy["id"])

    sharpe = float((all_m or backtest_m).get("sharpe_ratio") or 0)
    mdd = abs(float((all_m or backtest_m).get("max_drawdown") or 0))
    raw_signal_count = int(signal_stats.get("raw_signal_count") or signal_stats.get("total_signals") or 0)
    signals_with_forward_returns_count = int(signal_stats.get("signals_with_forward_returns_count") or 0)
    observed_forward_return_count = int(signal_stats.get("observed_forward_return_count") or 0)
    total_signals = raw_signal_count
    min_signal_count = 10
    hit_rate_5d = metric_bucket_value(signal_stats.get("hit_rate"), 5)
    forward_ic_5d = metric_bucket_value(signal_stats.get("forward_ic"), 5)
    forward_sharpe_5d = metric_bucket_value(signal_stats.get("forward_sharpe"), 5)

    blockers: list[str] = []
    risk_flags: list[str] = []
    blockers_by_period: dict[str, list[str]] = {}
    risk_flags_by_period: dict[str, list[str]] = {}
    observed_forward_days: list[int] = []
    forward_returns: list[dict] = []
    validation_grade = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "validation_grade") or ""
    ).strip().upper() or None
    raw_validation_grade = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "raw_validation_grade")
        or validation_grade
        or ""
    ).strip().upper() or None
    effective_validation_grade = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "effective_validation_grade")
        or validation_grade
        or ""
    ).strip().upper() or None
    validation_grade_adjustment_reason = str(
        _quality_report_field(
            quality_report,
            quality_gate,
            quality_summary,
            "validation_grade_adjustment_reason",
        ) or ""
    ).strip() or None
    raw_validation_total_score = _safe_float(
        _quality_report_field(quality_report, quality_gate, quality_summary, "raw_validation_total_score")
    )
    if raw_validation_total_score is None:
        raw_validation_total_score = _safe_float(
            validation_rating.get("base_total_score") if validation_rating else None
        )
    if raw_validation_total_score is None:
        raw_validation_total_score = _safe_float(validation_rating.get("total_score") if validation_rating else None)
    validation_total_score = _safe_float(
        _quality_report_field(quality_report, quality_gate, quality_summary, "validation_total_score")
    )
    if validation_total_score is None:
        validation_total_score = _safe_float(validation_rating.get("total_score") if validation_rating else None)
    strict_incubation_ready = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "strict_incubation_ready",
    )
    strict_incubation_blocked = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "strict_incubation_blocked",
    )
    incubation_candidate_ready = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "incubation_candidate_ready",
    )
    live_candidate_ready = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "live_candidate_ready",
    )
    admission_stage = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "admission_stage") or ""
    ).strip().lower() or None
    candidate_family = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "candidate_family")
        or strategy.get("strategy_type")
        or ""
    ).strip().lower() or None
    holding_period_bucket = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "holding_period_bucket") or ""
    ).strip().lower() or None
    validation_focus = str(
        _quality_report_field(quality_report, quality_gate, validation_profile, "validation_focus") or ""
    ).strip().lower() or None
    incubation_pass_mode = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "incubation_pass_mode") or ""
    ).strip().lower() or None
    admission_block_reasons = [
        str(item or "").strip()
        for item in list(
            _quality_report_field(quality_report, quality_gate, quality_summary, "admission_block_reasons") or []
        )
        if str(item or "").strip()
    ]
    has_strict_gate_signal = (
        strict_incubation_ready is not None
        or strict_incubation_blocked is not None
        or incubation_candidate_ready is not None
        or bool(incubation_pass_mode)
    )
    has_live_gate_signal = live_candidate_ready is not None or bool(admission_stage)
    if sharpe <= PROMOTION_THRESHOLDS["sharpe_min"]:
        blockers.append(f"Sharpe {sharpe:.2f} \u2264 {PROMOTION_THRESHOLDS['sharpe_min']:.2f}")
    if mdd >= PROMOTION_THRESHOLDS["mdd_max"]:
        blockers.append(f"\u6700\u5927\u56de\u64a4 {mdd:.1%} \u2265 {PROMOTION_THRESHOLDS['mdd_max']:.0%}")
    if raw_signal_count < min_signal_count:
        blockers.append(f"\u539f\u59cb\u4fe1\u53f7\u6570 {raw_signal_count} < {min_signal_count}")
    if sharpe < DEPRECATION_THRESHOLDS["sharpe_negative"]:
        risk_flags.append(f"Sharpe {sharpe:.2f} < 0")
    if mdd > DEPRECATION_THRESHOLDS["mdd_critical"]:
        risk_flags.append(f"\u6700\u5927\u56de\u64a4 {mdd:.1%} > {DEPRECATION_THRESHOLDS['mdd_critical']:.0%}")

    for days in (1, 5, 10, 20):
        label = f"{days}D"
        hit_rate = metric_bucket_value(signal_stats.get("hit_rate"), days)
        forward_ic = metric_bucket_value(signal_stats.get("forward_ic"), days)
        forward_sharpe = metric_bucket_value(signal_stats.get("forward_sharpe"), days)
        if hit_rate is None and forward_ic is None and forward_sharpe is None:
            continue
        observed_forward_days.append(days)
        period_blockers: list[str] = []
        period_risk_flags: list[str] = []
        if raw_signal_count >= min_signal_count and days in (5, 10, 20) and hit_rate is not None and hit_rate < PROMOTION_THRESHOLDS["hit_rate_blocker"]:
            period_blockers.append(f"{label}\u547d\u4e2d\u7387 {hit_rate:.1%} < {PROMOTION_THRESHOLDS['hit_rate_blocker']:.0%}")
        if raw_signal_count >= min_signal_count and days in (5, 10, 20) and hit_rate is not None and hit_rate < PROMOTION_THRESHOLDS["hit_rate_risk_flag"]:
            period_risk_flags.append(f"{label}\u547d\u4e2d\u7387 {hit_rate:.1%} < {PROMOTION_THRESHOLDS['hit_rate_risk_flag']:.0%}")
        if days >= 10 and forward_ic is not None and forward_ic < 0:
            period_risk_flags.append(f"{label}\u524d\u5411IC {forward_ic:.2f} < 0")
        if days >= 10 and forward_sharpe is not None and forward_sharpe < 0:
            period_risk_flags.append(f"{label}\u524d\u5411Sharpe {forward_sharpe:.2f} < 0")
        if period_blockers:
            blockers_by_period[label] = period_blockers
            blockers.extend(period_blockers)
        if period_risk_flags:
            risk_flags_by_period[label] = period_risk_flags
            risk_flags.extend(period_risk_flags)
        forward_returns.append({
            "forward_days": days,
            "label": label,
            "hit_rate": hit_rate,
            "forward_ic": forward_ic,
            "forward_sharpe": forward_sharpe,
            "blockers": period_blockers,
            "risk_flags": period_risk_flags,
        })

    missing_forward_days = [days for days in (1, 5, 10, 20) if days not in observed_forward_days]
    if raw_signal_count >= min_signal_count and missing_forward_days:
        blockers.append("\u7f3a\u5c11\u524d\u5411\u6536\u76ca\u89c2\u5bdf\u7a97\u53e3: " + ", ".join(f"{days}D" for days in missing_forward_days))

    gate_blockers: list[str] = []
    if validation_grade == "D":
        gate_blockers.append("validation_grade_d_not_allowed_for_promotion")
    if has_strict_gate_signal and (strict_incubation_ready is False or strict_incubation_blocked is True):
        gate_blockers.append("strict_incubation_gate_not_ready")
    if has_live_gate_signal and live_candidate_ready is False:
        gate_blockers.append("live_gate_not_ready")
    blockers.extend(item for item in gate_blockers if item not in blockers)

    strict_live_alignment_gap = bool(strict_incubation_ready) and live_candidate_ready is False
    if strict_incubation_ready is None and live_candidate_ready is None:
        strict_live_alignment_status = "unknown"
    elif bool(strict_incubation_ready) and bool(live_candidate_ready):
        strict_live_alignment_status = "aligned_live_ready"
    elif bool(strict_incubation_ready) and live_candidate_ready is False:
        strict_live_alignment_status = "strict_only_gap"
    elif strict_incubation_ready is False and live_candidate_ready is False:
        strict_live_alignment_status = "aligned_blocked"
    elif strict_incubation_ready is False and bool(live_candidate_ready):
        strict_live_alignment_status = "inconsistent_live_without_strict"
    else:
        strict_live_alignment_status = "unknown"

    promotion_ready = not blockers
    deprecation_risk = bool(risk_flags)

    return {
        "strategy_id": strategy["id"],
        "strategy_name": strategy.get("name"),
        "status": strategy.get("status"),
        "strategy_type": strategy.get("strategy_type"),
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
        "total_signals": total_signals,
        "raw_signal_count": raw_signal_count,
        "signals_with_forward_returns_count": signals_with_forward_returns_count,
        "observed_forward_return_count": observed_forward_return_count,
        "minimum_signal_count": min_signal_count,
        "hit_rate_5d": hit_rate_5d,
        "forward_ic_5d": forward_ic_5d,
        "forward_sharpe_5d": forward_sharpe_5d,
        "promotion_ready": promotion_ready,
        "deprecation_risk": deprecation_risk,
        "blockers": blockers,
        "risk_flags": risk_flags,
        "gate_blockers": gate_blockers,
        "admission_block_reasons": admission_block_reasons,
        "observed_forward_days": observed_forward_days,
        "missing_forward_days": missing_forward_days,
        "forward_returns": forward_returns,
        "blockers_by_period": blockers_by_period,
        "risk_flags_by_period": risk_flags_by_period,
        "quality_passed": bool((quality_report or {}).get("passed")),
        "validation_grade": validation_grade,
        "raw_validation_grade": raw_validation_grade,
        "effective_validation_grade": effective_validation_grade,
        "validation_grade_adjustment_reason": validation_grade_adjustment_reason,
        "raw_b_or_above": raw_validation_grade in {"A", "B"},
        "raw_validation_total_score": raw_validation_total_score,
        "validation_total_score": validation_total_score,
        "candidate_family": candidate_family,
        "holding_period_bucket": holding_period_bucket,
        "validation_focus": validation_focus,
        "trade_density": _safe_float(quality_gate.get("trade_density")),
        "post_cost_sharpe": _safe_float(quality_gate.get("post_cost_sharpe")),
        "deflated_sharpe_ratio": _safe_float(quality_gate.get("deflated_sharpe_ratio")),
        "pbo": _safe_float(quality_gate.get("pbo")),
        "strict_incubation_ready": strict_incubation_ready,
        "strict_incubation_blocked": strict_incubation_blocked,
        "incubation_candidate_ready": incubation_candidate_ready,
        "live_candidate_ready": live_candidate_ready,
        "admission_stage": admission_stage,
        "incubation_pass_mode": incubation_pass_mode,
        "strict_live_alignment_gap": strict_live_alignment_gap,
        "strict_live_alignment_status": strict_live_alignment_status,
    }
