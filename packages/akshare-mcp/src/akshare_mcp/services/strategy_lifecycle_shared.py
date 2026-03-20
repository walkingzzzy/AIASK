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
    signal_stats = await db.get_signal_stats(strategy["id"])

    sharpe = float((all_m or backtest_m).get("sharpe_ratio") or 0)
    mdd = abs(float((all_m or backtest_m).get("max_drawdown") or 0))
    total_signals = int(signal_stats.get("total_signals") or 0)
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
    if sharpe <= PROMOTION_THRESHOLDS["sharpe_min"]:
        blockers.append(f"Sharpe {sharpe:.2f} \u2264 {PROMOTION_THRESHOLDS['sharpe_min']:.2f}")
    if mdd >= PROMOTION_THRESHOLDS["mdd_max"]:
        blockers.append(f"\u6700\u5927\u56de\u64a4 {mdd:.1%} \u2265 {PROMOTION_THRESHOLDS['mdd_max']:.0%}")
    if total_signals < min_signal_count:
        blockers.append(f"\u6709\u6548\u4fe1\u53f7\u6570 {total_signals} < {min_signal_count}")
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
        if total_signals >= min_signal_count and days in (5, 10, 20) and hit_rate is not None and hit_rate < PROMOTION_THRESHOLDS["hit_rate_blocker"]:
            period_blockers.append(f"{label}\u547d\u4e2d\u7387 {hit_rate:.1%} < {PROMOTION_THRESHOLDS['hit_rate_blocker']:.0%}")
        if total_signals >= min_signal_count and days in (5, 10, 20) and hit_rate is not None and hit_rate < PROMOTION_THRESHOLDS["hit_rate_risk_flag"]:
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
    if total_signals >= min_signal_count and missing_forward_days:
        blockers.append("\u7f3a\u5c11\u524d\u5411\u6536\u76ca\u89c2\u5bdf\u7a97\u53e3: " + ", ".join(f"{days}D" for days in missing_forward_days))

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
        "minimum_signal_count": min_signal_count,
        "hit_rate_5d": hit_rate_5d,
        "forward_ic_5d": forward_ic_5d,
        "forward_sharpe_5d": forward_sharpe_5d,
        "promotion_ready": promotion_ready,
        "deprecation_risk": deprecation_risk,
        "blockers": blockers,
        "risk_flags": risk_flags,
        "observed_forward_days": observed_forward_days,
        "missing_forward_days": missing_forward_days,
        "forward_returns": forward_returns,
        "blockers_by_period": blockers_by_period,
        "risk_flags_by_period": risk_flags_by_period,
        "quality_passed": bool((quality_report or {}).get("passed")),
        "validation_grade": ((quality_report or {}).get("summary") or {}).get("validation_grade"),
    }
