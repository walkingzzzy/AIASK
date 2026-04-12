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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


EXPECTED_FORWARD_DAYS = (1, 5, 10, 20)
SIGNAL_QUALITY_PRIMARY_DEFAULT = (5, 10)
SIGNAL_QUALITY_OVERLAP_FACTORS = {
    1: 1.0,
    5: 3.0,
    10: 5.0,
    20: 8.0,
}
EXECUTION_SIGNAL_TO_FILL_WEAK = 0.30
EXECUTION_SIGNAL_TO_FILL_STRONG = 0.60
EXECUTION_FILLED_ORDER_WEAK = 0.50
EXECUTION_FILLED_ORDER_STRONG = 0.70
EXECUTION_NAV_RETURN_STRONG = 0.01
EXECUTION_NAV_CONVERSION_WEAK = 0.10
EXECUTION_NAV_CONVERSION_STRONG = 0.20


def resolve_signal_quality_horizons(holding_period_bucket: Optional[str]) -> tuple[int, int]:
    bucket = str(holding_period_bucket or "").strip().lower()
    if bucket in {"intraday", "short", "short_term", "fast", "event"}:
        return (1, 5)
    if bucket in {"position", "long", "long_term", "slow", "trend"}:
        return (10, 20)
    return SIGNAL_QUALITY_PRIMARY_DEFAULT


def _fallback_effective_n(sample_count: int, horizon: int) -> int:
    sample_n = max(int(sample_count or 0), 0)
    if sample_n <= 0:
        return 0
    factor = float(SIGNAL_QUALITY_OVERLAP_FACTORS.get(int(horizon or 0), max(int(horizon or 1), 1)))
    if factor <= 0:
        factor = 1.0
    return max(1, min(sample_n, int(sample_n / factor)))


def derive_signal_quality(
    signal_stats: Optional[dict],
    *,
    holding_period_bucket: Optional[str] = None,
) -> dict:
    stats = dict(signal_stats or {})
    raw_signal_count = _safe_int(stats.get("raw_signal_count") or stats.get("total_signals"))
    forward_signal_count = _safe_int(stats.get("signals_with_forward_returns_count"), raw_signal_count)
    observed_days = [
        days
        for days in EXPECTED_FORWARD_DAYS
        if any(
            metric_bucket_value(stats.get(field), days) is not None
            for field in (
                "hit_rate",
                "hit_rate_lcb",
                "skill_lcb",
                "sample_count",
                "forward_ic",
                "forward_sharpe",
            )
        )
    ]
    missing_days = [days for days in EXPECTED_FORWARD_DAYS if days not in observed_days]
    coverage_ratio = round(len(observed_days) / len(EXPECTED_FORWARD_DAYS), 4) if EXPECTED_FORWARD_DAYS else 0.0
    signal_coverage_ratio = round(forward_signal_count / raw_signal_count, 4) if raw_signal_count > 0 else 0.0
    primary_horizon, secondary_horizon = resolve_signal_quality_horizons(holding_period_bucket)

    by_horizon: dict[str, dict[str, Any]] = {}
    fallback_sample_count = max(forward_signal_count, raw_signal_count)

    for horizon in EXPECTED_FORWARD_DAYS:
        raw_hit_rate = metric_bucket_value(stats.get("hit_rate"), horizon)
        hit_rate_lcb = metric_bucket_value(stats.get("hit_rate_lcb"), horizon)
        null_hit_rate = metric_bucket_value(stats.get("null_hit_rate"), horizon)
        skill_lcb = metric_bucket_value(stats.get("skill_lcb"), horizon)
        recent_hit_rate = metric_bucket_value(stats.get("recent_hit_rate"), horizon)
        recent_hit_rate_lcb = metric_bucket_value(stats.get("recent_hit_rate_lcb"), horizon)
        recent_skill_lcb = metric_bucket_value(stats.get("recent_skill_lcb"), horizon)
        stability_gap = metric_bucket_value(stats.get("stability_gap"), horizon)
        sample_count = _safe_int(metric_bucket_value(stats.get("sample_count"), horizon), fallback_sample_count if raw_hit_rate is not None else 0)
        effective_n = _safe_int(metric_bucket_value(stats.get("effective_n"), horizon), _fallback_effective_n(sample_count, horizon))
        neutral_count = _safe_int(metric_bucket_value(stats.get("neutral_count"), horizon), 0)
        forward_ic = metric_bucket_value(stats.get("forward_ic"), horizon)
        forward_sharpe = metric_bucket_value(stats.get("forward_sharpe"), horizon)

        if hit_rate_lcb is None and raw_hit_rate is not None:
            hit_rate_lcb = raw_hit_rate
        if null_hit_rate is None and raw_hit_rate is not None:
            null_hit_rate = 0.5
        if skill_lcb is None and hit_rate_lcb is not None:
            skill_lcb = float(hit_rate_lcb) - float(null_hit_rate or 0.5)
        if recent_hit_rate is None and raw_hit_rate is not None:
            recent_hit_rate = raw_hit_rate
        if recent_hit_rate_lcb is None and recent_hit_rate is not None:
            recent_hit_rate_lcb = recent_hit_rate
        if recent_skill_lcb is None and recent_hit_rate_lcb is not None:
            recent_skill_lcb = float(recent_hit_rate_lcb) - float(null_hit_rate or 0.5)
        if stability_gap is None and raw_hit_rate is not None and recent_hit_rate is not None:
            stability_gap = abs(float(raw_hit_rate) - float(recent_hit_rate))

        by_horizon[str(horizon)] = {
            "horizon": horizon,
            "hit_rate": raw_hit_rate,
            "hit_rate_lcb": hit_rate_lcb,
            "null_hit_rate": null_hit_rate,
            "skill_lcb": skill_lcb,
            "recent_hit_rate": recent_hit_rate,
            "recent_hit_rate_lcb": recent_hit_rate_lcb,
            "recent_skill_lcb": recent_skill_lcb,
            "stability_gap": stability_gap,
            "sample_count": sample_count,
            "effective_n": effective_n,
            "neutral_count": neutral_count,
            "forward_ic": forward_ic,
            "forward_sharpe": forward_sharpe,
        }

    primary = dict(by_horizon.get(str(primary_horizon)) or {})
    secondary = dict(by_horizon.get(str(secondary_horizon)) or {})
    primary_skill_lcb = _safe_float(primary.get("skill_lcb"))
    secondary_skill_lcb = _safe_float(secondary.get("skill_lcb"))
    recent_primary_skill_lcb = _safe_float(primary.get("recent_skill_lcb"))
    recent_secondary_skill_lcb = _safe_float(secondary.get("recent_skill_lcb"))
    stability_gap = _safe_float(primary.get("stability_gap"))

    return {
        "primary_horizon": primary_horizon,
        "secondary_horizon": secondary_horizon,
        "observed_forward_days": observed_days,
        "missing_forward_days": missing_days,
        "coverage_ratio": coverage_ratio,
        "signal_coverage_ratio": signal_coverage_ratio,
        "primary_sample_count": _safe_int(primary.get("sample_count")),
        "secondary_sample_count": _safe_int(secondary.get("sample_count")),
        "primary_effective_n": _safe_int(primary.get("effective_n")),
        "secondary_effective_n": _safe_int(secondary.get("effective_n")),
        "primary_hit_rate": _safe_float(primary.get("hit_rate")),
        "primary_hit_rate_lcb": _safe_float(primary.get("hit_rate_lcb")),
        "secondary_hit_rate": _safe_float(secondary.get("hit_rate")),
        "secondary_hit_rate_lcb": _safe_float(secondary.get("hit_rate_lcb")),
        "primary_skill_lcb": primary_skill_lcb,
        "secondary_skill_lcb": secondary_skill_lcb,
        "primary_signal_skill_lcb": primary_skill_lcb,
        "secondary_signal_skill_lcb": secondary_skill_lcb,
        "recent_primary_hit_rate": _safe_float(primary.get("recent_hit_rate")),
        "recent_secondary_hit_rate": _safe_float(secondary.get("recent_hit_rate")),
        "recent_primary_skill_lcb": recent_primary_skill_lcb,
        "recent_secondary_skill_lcb": recent_secondary_skill_lcb,
        "stability_gap": stability_gap,
        "hit_rate_lcb_method": str(stats.get("hit_rate_lcb_method") or "wilson_ess_approx"),
        "effective_n_method": str(stats.get("effective_n_method") or "overlap_adjusted_ess_v1"),
        "recent_window_days": _safe_int(stats.get("recent_window_days"), 20),
        "neutral_band_epsilon": _safe_float(stats.get("neutral_band_epsilon")),
        "by_horizon": by_horizon,
    }


def _round_metric(value: Optional[float], digits: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _safe_ratio(numerator: Any, denominator: Any, *, digits: int = 6) -> Optional[float]:
    denom = _safe_float(denominator)
    if denom is None or abs(denom) <= 1e-12:
        return None
    num = _safe_float(numerator) or 0.0
    return _round_metric(num / denom, digits)


def _default_execution_order_summary() -> dict:
    return {
        "total_orders": 0,
        "filled_orders": 0,
        "total_trades": 0,
        "trade_amount": 0.0,
    }


async def _load_execution_quality_inputs(db, strategy_id: str, *, nav_limit: int = 60) -> dict:
    account = None
    if hasattr(db, "get_paper_account_by_strategy"):
        account = await db.get_paper_account_by_strategy(strategy_id)
    elif hasattr(db, "acquire"):
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_accounts WHERE strategy_id = $1 ORDER BY created_at LIMIT 1",
                strategy_id,
            )
        account = dict(row) if row else None

    if not account:
        return {
            "account": None,
            "order_summary": _default_execution_order_summary(),
            "nav_rows": [],
        }

    account_id = str(account.get("id") or "").strip()
    order_summary = _default_execution_order_summary()
    if account_id and hasattr(db, "get_paper_order_summary"):
        order_summary.update(dict(await db.get_paper_order_summary(account_id) or {}))
    elif account_id and hasattr(db, "acquire"):
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE((SELECT COUNT(*) FROM paper_orders WHERE account_id = $1), 0)::int AS total_orders,
                    COALESCE((SELECT COUNT(*) FROM paper_orders WHERE account_id = $1 AND status = 'filled'), 0)::int AS filled_orders,
                    COALESCE((SELECT COUNT(*) FROM paper_trades WHERE account_id = $1), 0)::int AS total_trades,
                    COALESCE((SELECT SUM(amount) FROM paper_trades WHERE account_id = $1), 0)::float AS trade_amount
                """,
                account_id,
            )
        order_summary.update(dict(row or {}))

    nav_rows = []
    if account_id and hasattr(db, "get_paper_nav_rows"):
        nav_rows = await db.get_paper_nav_rows(account_id, limit=nav_limit)
    elif account_id and hasattr(db, "acquire"):
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_nav WHERE account_id = $1 ORDER BY nav_date DESC LIMIT $2",
                account_id,
                max(1, min(int(nav_limit or 60), 365)),
            )
        nav_rows = [dict(row) for row in rows]

    return {
        "account": dict(account),
        "order_summary": {
            "total_orders": _safe_int(order_summary.get("total_orders")),
            "filled_orders": _safe_int(order_summary.get("filled_orders"), _safe_int(order_summary.get("total_trades"))),
            "total_trades": _safe_int(order_summary.get("total_trades")),
            "trade_amount": _safe_float(order_summary.get("trade_amount")) or 0.0,
        },
        "nav_rows": [dict(row) for row in list(nav_rows or [])],
    }


def _classify_prediction_quality(signal_quality: Optional[dict]) -> tuple[str, list[str]]:
    quality = dict(signal_quality or {})
    primary_horizon = _safe_int(quality.get("primary_horizon"), 5)
    primary_skill_lcb = _safe_float(quality.get("primary_skill_lcb"))
    recent_primary_skill_lcb = _safe_float(quality.get("recent_primary_skill_lcb"))
    primary_effective_n = _safe_int(quality.get("primary_effective_n"))
    coverage_ratio = _safe_float(quality.get("coverage_ratio")) or 0.0

    weak_reasons: list[str] = []
    if primary_skill_lcb is not None and primary_skill_lcb <= 0:
        weak_reasons.append(f"{primary_horizon}D skill LCB {(primary_skill_lcb or 0.0):+.2%} <= 0")
    if recent_primary_skill_lcb is not None and recent_primary_skill_lcb < 0:
        weak_reasons.append(f"recent {primary_horizon}D skill LCB {recent_primary_skill_lcb:+.2%} < 0")
    if weak_reasons:
        return "weak", weak_reasons

    insufficient_reasons: list[str] = []
    if primary_effective_n < 20:
        insufficient_reasons.append(f"{primary_horizon}D effective_n {primary_effective_n} < 20")
    if coverage_ratio < 0.5:
        insufficient_reasons.append(f"forward coverage {coverage_ratio:.0%} < 50%")
    if insufficient_reasons:
        return "insufficient_evidence", insufficient_reasons

    strong_reasons: list[str] = []
    if primary_skill_lcb is not None and primary_skill_lcb >= 0.03:
        strong_reasons.append(f"{primary_horizon}D skill LCB {primary_skill_lcb:+.2%} >= 3%")
    if recent_primary_skill_lcb is not None and recent_primary_skill_lcb >= 0.01:
        strong_reasons.append(f"recent {primary_horizon}D skill LCB {recent_primary_skill_lcb:+.2%} >= 1%")
    if primary_effective_n >= 60:
        strong_reasons.append(f"{primary_horizon}D effective_n {primary_effective_n} >= 60")
    if coverage_ratio >= 0.75:
        strong_reasons.append(f"forward coverage {coverage_ratio:.0%} >= 75%")
    if len(strong_reasons) >= 3:
        return "strong", strong_reasons
    return "mixed", strong_reasons or [f"{primary_horizon}D signal edge remains positive but not yet strong"]


def _classify_execution_quality(
    *,
    total_signals: int,
    order_count: int,
    filled_order_count: int,
    trade_count: int,
    nav_observation_days: int,
    signal_to_fill_ratio: Optional[float],
    filled_order_ratio: Optional[float],
    paper_nav_return: Optional[float],
    nav_conversion_proxy: Optional[float],
) -> tuple[str, list[str]]:
    weak_reasons: list[str] = []
    strong_reasons: list[str] = []

    if signal_to_fill_ratio is not None and total_signals >= 10:
        if signal_to_fill_ratio < EXECUTION_SIGNAL_TO_FILL_WEAK:
            weak_reasons.append(
                f"signal_to_fill_ratio {signal_to_fill_ratio:.2f} < {EXECUTION_SIGNAL_TO_FILL_WEAK:.2f}"
            )
        elif signal_to_fill_ratio >= EXECUTION_SIGNAL_TO_FILL_STRONG:
            strong_reasons.append(
                f"signal_to_fill_ratio {signal_to_fill_ratio:.2f} >= {EXECUTION_SIGNAL_TO_FILL_STRONG:.2f}"
            )

    if filled_order_ratio is not None and order_count >= 3:
        if filled_order_ratio < EXECUTION_FILLED_ORDER_WEAK:
            weak_reasons.append(
                f"filled_order_ratio {filled_order_ratio:.2f} < {EXECUTION_FILLED_ORDER_WEAK:.2f}"
            )
        elif filled_order_ratio >= EXECUTION_FILLED_ORDER_STRONG:
            strong_reasons.append(
                f"filled_order_ratio {filled_order_ratio:.2f} >= {EXECUTION_FILLED_ORDER_STRONG:.2f}"
            )

    if paper_nav_return is not None and nav_observation_days >= 2:
        if paper_nav_return <= 0:
            weak_reasons.append(f"paper_nav_return {paper_nav_return:+.2%} <= 0")
        elif paper_nav_return >= EXECUTION_NAV_RETURN_STRONG:
            strong_reasons.append(f"paper_nav_return {paper_nav_return:+.2%} >= {EXECUTION_NAV_RETURN_STRONG:.0%}")

    if nav_conversion_proxy is not None and nav_observation_days >= 2:
        if nav_conversion_proxy < EXECUTION_NAV_CONVERSION_WEAK:
            weak_reasons.append(
                f"nav_conversion_proxy {nav_conversion_proxy:.2f} < {EXECUTION_NAV_CONVERSION_WEAK:.2f}"
            )
        elif nav_conversion_proxy >= EXECUTION_NAV_CONVERSION_STRONG:
            strong_reasons.append(
                f"nav_conversion_proxy {nav_conversion_proxy:.2f} >= {EXECUTION_NAV_CONVERSION_STRONG:.2f}"
            )

    has_execution_evidence = order_count > 0 or filled_order_count > 0 or trade_count > 0 or nav_observation_days > 0
    sufficient_execution_evidence = (
        order_count >= 5
        or filled_order_count >= 3
        or trade_count >= 3
        or nav_observation_days >= 5
    )

    if weak_reasons:
        return "weak", weak_reasons
    if not has_execution_evidence:
        return "insufficient_evidence", ["paper_orders / paper_trades / paper_nav evidence is not available yet"]
    if not sufficient_execution_evidence:
        return "insufficient_evidence", ["paper execution evidence is still too shallow for a stable label"]
    if len(strong_reasons) >= 2:
        return "strong", strong_reasons
    return "mixed", strong_reasons or ["paper execution conversion is visible but not yet decisive"]


def _combine_quality_diagnosis(
    prediction_quality_label: str,
    execution_quality_label: str,
    *,
    prediction_reasons: list[str],
    execution_reasons: list[str],
) -> tuple[str, list[str]]:
    if prediction_quality_label == "weak" and execution_quality_label == "weak":
        return "prediction_and_execution_weak", prediction_reasons + execution_reasons
    if prediction_quality_label == "weak":
        return "prediction_weak", prediction_reasons
    if execution_quality_label == "weak":
        return "execution_conversion_weak", execution_reasons
    if prediction_quality_label == "insufficient_evidence" and execution_quality_label == "insufficient_evidence":
        return "await_more_evidence", prediction_reasons + execution_reasons
    if prediction_quality_label == "insufficient_evidence":
        return "await_prediction_evidence", prediction_reasons
    if execution_quality_label == "insufficient_evidence":
        return "await_execution_evidence", execution_reasons
    return (
        "balanced",
        prediction_reasons
        + execution_reasons
        + ["signal quality and execution conversion are not flagging a primary weakness"],
    )


async def build_execution_quality(
    db,
    strategy: dict,
    *,
    signal_quality: Optional[dict] = None,
    total_signals: int = 0,
) -> dict:
    quality = dict(signal_quality or {})
    paper_inputs = await _load_execution_quality_inputs(db, str(strategy.get("id") or ""))
    account = dict(paper_inputs.get("account") or {})
    order_summary = dict(paper_inputs.get("order_summary") or _default_execution_order_summary())
    nav_rows = list(paper_inputs.get("nav_rows") or [])

    account_id = str(account.get("id") or "").strip() or None
    total_orders = _safe_int(order_summary.get("total_orders"))
    filled_orders = _safe_int(order_summary.get("filled_orders"), _safe_int(order_summary.get("total_trades")))
    total_trades = _safe_int(order_summary.get("total_trades"))
    trade_amount = _safe_float(order_summary.get("trade_amount")) or 0.0
    nav_observation_days = len(nav_rows)

    latest_nav = dict(nav_rows[0]) if nav_rows else {}
    earliest_nav = dict(nav_rows[-1]) if nav_rows else {}
    initial_capital = _safe_float(account.get("initial_capital"))
    latest_total_value = _safe_float(latest_nav.get("total_value"))
    if latest_total_value is None:
        latest_total_value = _safe_float(account.get("total_value"))
    nav_reference_value = _safe_float(earliest_nav.get("total_value"))
    nav_reference_source = "earliest_nav"
    if nav_reference_value is None:
        nav_reference_value = initial_capital if initial_capital and initial_capital > 0 else latest_total_value
        nav_reference_source = "initial_capital" if initial_capital and initial_capital > 0 else "latest_nav"

    paper_nav_change = None
    if latest_total_value is not None and nav_reference_value is not None:
        paper_nav_change = latest_total_value - nav_reference_value
    paper_nav_return = _safe_ratio(paper_nav_change, nav_reference_value)

    signal_count_reference = max(_safe_int(total_signals), 0)
    if account_id:
        signal_to_fill_ratio = _safe_ratio(filled_orders, signal_count_reference) if signal_count_reference > 0 else None
    else:
        signal_to_fill_ratio = None
    filled_order_ratio = _safe_ratio(filled_orders, total_orders) if total_orders > 0 else None
    turnover_base = latest_total_value if latest_total_value and latest_total_value > 0 else initial_capital
    turnover_rate = _safe_ratio(trade_amount, turnover_base)

    signal_edge_reference = _safe_float(quality.get("primary_skill_lcb"))
    if signal_edge_reference is not None and signal_edge_reference <= 0:
        signal_edge_reference = None
    nav_conversion_proxy = (
        _safe_ratio(paper_nav_return, signal_edge_reference)
        if paper_nav_return is not None and signal_edge_reference is not None
        else None
    )

    prediction_quality_label, prediction_reasons = _classify_prediction_quality(quality)
    execution_quality_label, execution_reasons = _classify_execution_quality(
        total_signals=signal_count_reference,
        order_count=total_orders,
        filled_order_count=filled_orders,
        trade_count=total_trades,
        nav_observation_days=nav_observation_days,
        signal_to_fill_ratio=signal_to_fill_ratio,
        filled_order_ratio=filled_order_ratio,
        paper_nav_return=paper_nav_return,
        nav_conversion_proxy=nav_conversion_proxy,
    )
    diagnosis, diagnosis_reasons = _combine_quality_diagnosis(
        prediction_quality_label,
        execution_quality_label,
        prediction_reasons=prediction_reasons,
        execution_reasons=execution_reasons,
    )

    evidence_status = "missing_account"
    if account_id:
        evidence_status = "ready" if (total_orders > 0 or total_trades > 0 or nav_observation_days > 0) else "empty"

    return {
        "approximate": True,
        "audit_grade": False,
        "method": "paper_orders_trades_nav_proxy_v1",
        "source_tables": ["paper_orders", "paper_trades", "paper_nav"],
        "approximate_metrics": [
            "signal_to_fill_ratio",
            "filled_order_ratio",
            "turnover_rate",
            "nav_conversion_proxy",
        ],
        "audit_only_metrics": [
            "execution_win_rate",
            "avg_win_loss_ratio",
            "trade_expectancy",
            "pnl_conversion_efficiency",
        ],
        "note": "Execution metrics are V2 approximate proxies until round-trip matching and realized PnL semantics are available.",
        "account_id": account_id,
        "evidence_status": evidence_status,
        "signal_count_reference": signal_count_reference,
        "order_count": total_orders,
        "filled_order_count": filled_orders,
        "trade_count": total_trades,
        "trade_amount": _round_metric(trade_amount, 4),
        "turnover_rate": turnover_rate,
        "nav_observation_days": nav_observation_days,
        "paper_nav_reference_source": nav_reference_source,
        "paper_nav_start_value": _round_metric(nav_reference_value, 4),
        "paper_nav_latest_value": _round_metric(latest_total_value, 4),
        "paper_nav_change": _round_metric(paper_nav_change, 4),
        "paper_nav_return": paper_nav_return,
        "signal_edge_reference": signal_edge_reference,
        "signal_edge_reference_label": (
            f"{_safe_int(quality.get('primary_horizon'), 5)}D_skill_lcb" if signal_edge_reference is not None else None
        ),
        "signal_to_fill_ratio": signal_to_fill_ratio,
        "filled_order_ratio": filled_order_ratio,
        "nav_conversion_proxy": nav_conversion_proxy,
        "prediction_quality_label": prediction_quality_label,
        "prediction_reasons": prediction_reasons,
        "execution_quality_label": execution_quality_label,
        "execution_reasons": execution_reasons,
        "diagnosis": diagnosis,
        "diagnosis_reasons": diagnosis_reasons,
    }


def resolve_incubation_pipeline_stage(signal_quality: Optional[dict], *, open_risk_count: int = 0) -> str:
    quality = dict(signal_quality or {})
    primary_effective_n = _safe_int(quality.get("primary_effective_n"))
    secondary_effective_n = _safe_int(quality.get("secondary_effective_n"))
    primary_skill_lcb = _safe_float(
        quality.get("primary_skill_lcb") if quality.get("primary_skill_lcb") is not None else quality.get("primary_signal_skill_lcb")
    )
    secondary_skill_lcb = _safe_float(
        quality.get("secondary_skill_lcb") if quality.get("secondary_skill_lcb") is not None else quality.get("secondary_signal_skill_lcb")
    )
    recent_primary_skill_lcb = _safe_float(quality.get("recent_primary_skill_lcb"))
    coverage_ratio = _safe_float(quality.get("coverage_ratio")) or 0.0
    stability_gap = _safe_float(quality.get("stability_gap"))

    if primary_effective_n < 20 or coverage_ratio < 0.25:
        return "warmup"
    if (recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03) or (
        stability_gap is not None and stability_gap > 0.10
    ) or open_risk_count >= 3:
        return "failed"
    if (
        primary_effective_n >= 60
        and secondary_effective_n >= 30
        and (primary_skill_lcb or 0.0) > 0.0
        and (secondary_skill_lcb or 0.0) > 0.0
        and (recent_primary_skill_lcb or 0.0) > 0.0
        and coverage_ratio >= 0.75
        and (stability_gap is None or stability_gap <= 0.05)
        and open_risk_count == 0
    ):
        return "graduation_ready"
    if (
        primary_skill_lcb is None
        or primary_skill_lcb <= 0.0
        or coverage_ratio < 0.5
        or (stability_gap is not None and stability_gap > 0.08)
        or open_risk_count > 1
    ):
        return "observe"
    return "candidate"


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
    signal_quality = derive_signal_quality(signal_stats, holding_period_bucket=holding_period_bucket)
    primary_horizon = _safe_int(signal_quality.get("primary_horizon"), 5)
    secondary_horizon = _safe_int(signal_quality.get("secondary_horizon"), 10)
    primary_effective_n = _safe_int(signal_quality.get("primary_effective_n"))
    secondary_effective_n = _safe_int(signal_quality.get("secondary_effective_n"))
    primary_skill_lcb = _safe_float(signal_quality.get("primary_skill_lcb"))
    secondary_skill_lcb = _safe_float(signal_quality.get("secondary_skill_lcb"))
    recent_primary_skill_lcb = _safe_float(signal_quality.get("recent_primary_skill_lcb"))
    stability_gap = _safe_float(signal_quality.get("stability_gap"))
    coverage_ratio = _safe_float(signal_quality.get("coverage_ratio")) or 0.0
    signal_coverage_ratio = _safe_float(signal_quality.get("signal_coverage_ratio")) or 0.0
    observed_forward_days = list(signal_quality.get("observed_forward_days") or [])
    missing_forward_days = list(signal_quality.get("missing_forward_days") or [])
    execution_quality = await build_execution_quality(
        db,
        strategy,
        signal_quality=signal_quality,
        total_signals=total_signals,
    )
    if sharpe <= PROMOTION_THRESHOLDS["sharpe_min"]:
        blockers.append(f"Sharpe {sharpe:.2f} \u2264 {PROMOTION_THRESHOLDS['sharpe_min']:.2f}")
    if mdd >= PROMOTION_THRESHOLDS["mdd_max"]:
        blockers.append(f"\u6700\u5927\u56de\u64a4 {mdd:.1%} \u2265 {PROMOTION_THRESHOLDS['mdd_max']:.0%}")
    if sharpe < DEPRECATION_THRESHOLDS["sharpe_negative"]:
        risk_flags.append(f"Sharpe {sharpe:.2f} < 0")
    if mdd > DEPRECATION_THRESHOLDS["mdd_critical"]:
        risk_flags.append(f"\u6700\u5927\u56de\u64a4 {mdd:.1%} > {DEPRECATION_THRESHOLDS['mdd_critical']:.0%}")
    if primary_effective_n < 20:
        blockers.append(f"\u4e3b\u7a97\u53e3{primary_horizon}D\u6709\u6548\u6837\u672c {primary_effective_n} < 20")
    if primary_skill_lcb is None or primary_skill_lcb <= 0:
        blockers.append(
            f"\u4e3b\u7a97\u53e3{primary_horizon}D skill LCB "
            f"{(primary_skill_lcb or 0.0):+.2%} \u2264 0"
        )
    if coverage_ratio < 0.5:
        blockers.append(f"\u524d\u5411\u7a97\u53e3\u8986\u76d6\u7387 {coverage_ratio:.0%} < 50%")
    if secondary_effective_n >= 30 and secondary_skill_lcb is not None and secondary_skill_lcb <= 0:
        blockers.append(
            f"\u6b21\u7a97\u53e3{secondary_horizon}D skill LCB "
            f"{secondary_skill_lcb:+.2%} \u2264 0"
        )
    if raw_signal_count < min_signal_count:
        risk_flags.append(f"\u539f\u59cb\u4fe1\u53f7\u6570 {raw_signal_count} < {min_signal_count}")
    if signal_coverage_ratio < 0.35 and raw_signal_count >= min_signal_count:
        risk_flags.append(f"\u524d\u5411\u6837\u672c\u8986\u76d6\u7387 {signal_coverage_ratio:.0%} < 35%")
    if stability_gap is not None and stability_gap > 0.08:
        risk_flags.append(f"\u4e3b\u7a97\u53e3\u547d\u4e2d\u7387\u7a33\u5b9a\u6027\u7f3a\u53e3 {stability_gap:.1%} > 8%")
    if recent_primary_skill_lcb is not None and recent_primary_skill_lcb <= 0:
        risk_flags.append(
            f"\u8fd1\u671f\u4e3b\u7a97\u53e3{primary_horizon}D skill LCB "
            f"{recent_primary_skill_lcb:+.2%} \u2264 0"
        )
    if recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03:
        risk_flags.append(
            f"\u8fd1\u671f\u4e3b\u7a97\u53e3{primary_horizon}D skill LCB "
            f"{recent_primary_skill_lcb:+.2%} < -3%"
        )
    if stability_gap is not None and stability_gap > 0.10:
        risk_flags.append(f"\u4e3b\u7a97\u53e3\u7a33\u5b9a\u6027\u65ad\u88c2 {stability_gap:.1%} > 10%")

    for days in EXPECTED_FORWARD_DAYS:
        label = f"{days}D"
        bucket = dict((signal_quality.get("by_horizon") or {}).get(str(days)) or {})
        hit_rate = _safe_float(bucket.get("hit_rate"))
        hit_rate_lcb = _safe_float(bucket.get("hit_rate_lcb"))
        skill_lcb = _safe_float(bucket.get("skill_lcb"))
        recent_hit_rate = _safe_float(bucket.get("recent_hit_rate"))
        recent_skill_lcb = _safe_float(bucket.get("recent_skill_lcb"))
        stability_gap_bucket = _safe_float(bucket.get("stability_gap"))
        sample_count = _safe_int(bucket.get("sample_count"))
        effective_n = _safe_int(bucket.get("effective_n"))
        neutral_count = _safe_int(bucket.get("neutral_count"))
        forward_ic = _safe_float(bucket.get("forward_ic"))
        forward_sharpe = _safe_float(bucket.get("forward_sharpe"))
        if all(
            value is None or value == 0
            for value in (hit_rate, hit_rate_lcb, skill_lcb, recent_hit_rate, recent_skill_lcb, forward_ic, forward_sharpe)
        ) and sample_count <= 0:
            continue
        period_blockers: list[str] = []
        period_risk_flags: list[str] = []
        if days == primary_horizon and primary_effective_n < 20:
            period_blockers.append(f"{label}\u6709\u6548\u6837\u672c {effective_n} < 20")
        if days == primary_horizon and (skill_lcb is None or skill_lcb <= 0):
            period_blockers.append(f"{label} skill LCB {(skill_lcb or 0.0):+.2%} \u2264 0")
        if days == secondary_horizon and secondary_effective_n >= 30 and skill_lcb is not None and skill_lcb <= 0:
            period_blockers.append(f"{label} skill LCB {skill_lcb:+.2%} \u2264 0")
        if stability_gap_bucket is not None and stability_gap_bucket > 0.08:
            period_risk_flags.append(f"{label}\u547d\u4e2d\u7387\u7a33\u5b9a\u6027\u7f3a\u53e3 {stability_gap_bucket:.1%} > 8%")
        if recent_skill_lcb is not None and recent_skill_lcb <= 0:
            period_risk_flags.append(f"{label}\u8fd1\u671f skill LCB {recent_skill_lcb:+.2%} \u2264 0")
        if days >= 10 and forward_ic is not None and forward_ic < 0:
            period_risk_flags.append(f"{label}\u524d\u5411IC {forward_ic:.2f} < 0")
        if days >= 10 and forward_sharpe is not None and forward_sharpe < 0:
            period_risk_flags.append(f"{label}\u524d\u5411Sharpe {forward_sharpe:.2f} < 0")
        if period_blockers:
            blockers_by_period[label] = period_blockers
            blockers.extend(item for item in period_blockers if item not in blockers)
        if period_risk_flags:
            risk_flags_by_period[label] = period_risk_flags
            risk_flags.extend(item for item in period_risk_flags if item not in risk_flags)
        forward_returns.append({
            "forward_days": days,
            "label": label,
            "hit_rate": hit_rate,
            "hit_rate_lcb": hit_rate_lcb,
            "skill_lcb": skill_lcb,
            "recent_hit_rate": recent_hit_rate,
            "recent_skill_lcb": recent_skill_lcb,
            "stability_gap": stability_gap_bucket,
            "sample_count": sample_count,
            "effective_n": effective_n,
            "neutral_count": neutral_count,
            "forward_ic": forward_ic,
            "forward_sharpe": forward_sharpe,
            "blockers": period_blockers,
            "risk_flags": period_risk_flags,
        })

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

    promotion_ready = (
        primary_effective_n >= 60
        and secondary_effective_n >= 30
        and (primary_skill_lcb or 0.0) > 0.0
        and (secondary_skill_lcb or 0.0) > 0.0
        and (recent_primary_skill_lcb or 0.0) > 0.0
        and coverage_ratio >= 0.75
        and (stability_gap is None or stability_gap <= 0.05)
        and not blockers
    )
    deprecation_risk = bool(
        (recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03)
        or (stability_gap is not None and stability_gap > 0.10)
        or sharpe < DEPRECATION_THRESHOLDS["sharpe_negative"]
        or mdd > DEPRECATION_THRESHOLDS["mdd_critical"]
    )

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
        "signal_quality": signal_quality,
        "execution_quality": execution_quality,
        "primary_horizon": primary_horizon,
        "secondary_horizon": secondary_horizon,
        "sample_count": _safe_int(signal_quality.get("primary_sample_count")),
        "effective_n": primary_effective_n,
        "hit_rate_lcb": _safe_float(signal_quality.get("primary_hit_rate_lcb")),
        "skill_lcb": primary_skill_lcb,
        "recent_hit_rate": _safe_float(signal_quality.get("recent_primary_hit_rate")),
        "recent_skill_lcb": recent_primary_skill_lcb,
        "stability_gap": stability_gap,
        "coverage_ratio": coverage_ratio,
        "signal_coverage_ratio": signal_coverage_ratio,
        "hit_rate_lcb_method": signal_quality.get("hit_rate_lcb_method"),
        "effective_n_method": signal_quality.get("effective_n_method"),
        "signal_to_fill_ratio": execution_quality.get("signal_to_fill_ratio"),
        "filled_order_ratio": execution_quality.get("filled_order_ratio"),
        "nav_conversion_proxy": execution_quality.get("nav_conversion_proxy"),
        "paper_nav_return": execution_quality.get("paper_nav_return"),
        "prediction_quality_label": execution_quality.get("prediction_quality_label"),
        "execution_quality_label": execution_quality.get("execution_quality_label"),
        "quality_diagnosis": execution_quality.get("diagnosis"),
        "quality_diagnosis_reasons": execution_quality.get("diagnosis_reasons"),
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
