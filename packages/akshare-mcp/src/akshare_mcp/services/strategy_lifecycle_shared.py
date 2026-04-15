"""Shared strategy lifecycle primitives used by both services and tools layers.

This module exists to break the circular dependency where services
(promotion_pipeline, incubation, runtime_control) imported from the
tools layer (tools.managers.strategy_manager).  Now both sides import
from this services-level module instead.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from strategy_factory import (
    DEPRECATION_THRESHOLDS,
    PROMOTION_THRESHOLDS,
    STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED,
    STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED,
)

logger = logging.getLogger(__name__)

_EARLY_SIGNAL_STAGES = {"warmup", "observe"}
_EXECUTION_AUDIT_PROMOTION_BLOCKING_STAGES = {"candidate", "graduation_ready"}
_EARLY_STAGE_PROMOTION_MDD_TOLERANCE = 0.03
_TREND_EXECUTABLE_DSL_TYPES = {"ma_cross", "momentum", "volatility_breakout"}


def _confidence_diagnostics_enabled() -> bool:
    return bool(STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED)


def _execution_audit_enabled() -> bool:
    return bool(STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED)

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


def _string(value: Any) -> str:
    return str(value or "").strip()


def _contract_version_stable(value: Any, explicit_flag: Any = None) -> bool:
    if explicit_flag is not None:
        return bool(explicit_flag)
    version = _string(value).lower()
    if not version:
        return False
    unstable_tokens = ("draft", "unstable", "experimental", "preview", "beta", "alpha")
    return not any(token in version for token in unstable_tokens)


def evaluate_confidence_contract(
    confidence_contract: Optional[dict[str, Any]],
    *,
    signal_quality: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    contract = dict(confidence_contract or {})
    prediction_quality = dict(
        contract.get("prediction_quality")
        or contract.get("probability_quality")
        or {}
    )
    prediction_interval = dict(contract.get("prediction_interval") or {})
    support_samples = _safe_int(
        prediction_quality.get("support_samples")
        or prediction_quality.get("sample_size")
        or contract.get("support_samples")
        or contract.get("sample_size"),
        _safe_int(dict(signal_quality or {}).get("primary_effective_n")),
    )
    brier_score = _safe_float(
        prediction_quality.get("brier_score")
        if prediction_quality.get("brier_score") is not None
        else contract.get("brier_score")
    )
    ece = _safe_float(
        prediction_quality.get("ece")
        if prediction_quality.get("ece") is not None
        else contract.get("ece")
    )
    calibration_gap = _safe_float(
        prediction_quality.get("calibration_gap")
        if prediction_quality.get("calibration_gap") is not None
        else contract.get("calibration_gap")
    )
    coverage_proxy = _safe_float(
        prediction_interval.get("coverage_proxy")
        if prediction_interval.get("coverage_proxy") is not None
        else contract.get("coverage_proxy")
    )
    observed_coverage = _safe_float(
        prediction_interval.get("observed_coverage")
        if prediction_interval.get("observed_coverage") is not None
        else contract.get("observed_coverage")
    )
    coverage_gap = _safe_float(
        prediction_interval.get("coverage_gap")
        if prediction_interval.get("coverage_gap") is not None
        else contract.get("coverage_gap")
    )
    quality_label = _string(
        prediction_quality.get("quality")
        or contract.get("quality")
    ).lower() or None
    contract_version = (
        _string(
            prediction_quality.get("contract_version")
            or contract.get("contract_version")
            or prediction_quality.get("version")
            or contract.get("version")
        )
        or None
    )
    contract_version_stable = _contract_version_stable(
        contract_version,
        explicit_flag=(
            prediction_quality.get("contract_version_stable")
            if prediction_quality.get("contract_version_stable") is not None
            else contract.get("contract_version_stable")
        ),
    )

    diagnostics = {
        "contract_present": bool(contract),
        "sample_size": support_samples,
        "support_samples": support_samples,
        "brier_score": brier_score,
        "ece": ece,
        "calibration_gap": calibration_gap,
        "quality": quality_label,
        "contract_version": contract_version,
        "contract_version_stable": contract_version_stable,
        "prediction_interval": {
            "coverage_proxy": coverage_proxy,
            "observed_coverage": observed_coverage,
            "coverage_gap": coverage_gap,
        },
        "diagnostic_only": True,
    }

    if not contract:
        status = "missing"
    elif support_samples < 50:
        status = "insufficient"
    elif support_samples < 100:
        status = "diagnostic_ready"
    elif contract_version_stable:
        status = "comparable_ready"
        diagnostics["diagnostic_only"] = False
    else:
        status = "diagnostic_ready"
    diagnostics["status"] = status
    return status, diagnostics


def evaluate_execution_audit_gate(
    audit_summary: Optional[dict[str, Any]],
) -> tuple[str, list[str], dict[str, bool], dict[str, float | int | None]]:
    summary = dict(audit_summary or {})
    realized_trade_count = _safe_int(summary.get("realized_trade_count"))
    mapped_position_count = _safe_int(summary.get("mapped_position_count"))
    incomplete_position_count = _safe_int(summary.get("incomplete_position_count"))
    order_count = _safe_int(summary.get("order_count"))
    filled_order_count = _safe_int(summary.get("filled_order_count"))
    trade_count = _safe_int(summary.get("trade_count"))
    nav_observation_days = _safe_int(summary.get("nav_observation_days"))
    evidence_status = _string(summary.get("evidence_status")) or None
    runtime_evidence_present = bool(
        mapped_position_count > 0
        or incomplete_position_count > 0
        or order_count > 0
        or filled_order_count > 0
        or trade_count > 0
        or nav_observation_days > 0
        or evidence_status in {"ready", "empty", "bootstrap_pending"}
        or _string(summary.get("account_id"))
        or _string(summary.get("paper_account_id"))
    )
    trade_expectancy = _safe_float(summary.get("trade_expectancy"))
    pnl_conversion_efficiency = _safe_float(summary.get("pnl_conversion_efficiency"))
    execution_conversion_efficiency = _safe_float(summary.get("execution_conversion_efficiency"))
    hard_gate_metrics = {
        "realized_trade_count": realized_trade_count,
        "trade_expectancy": trade_expectancy,
        "pnl_conversion_efficiency": pnl_conversion_efficiency,
        "execution_conversion_efficiency": execution_conversion_efficiency,
    }
    hard_gate_metric_passes = {
        "realized_trade_count": realized_trade_count >= 20,
        "trade_expectancy": trade_expectancy is not None and trade_expectancy > 0.0,
        "pnl_conversion_efficiency": (
            pnl_conversion_efficiency is not None and pnl_conversion_efficiency > 0.0
        ),
        "execution_conversion_efficiency": (
            execution_conversion_efficiency is not None
            and execution_conversion_efficiency >= 0.20
        ),
    }
    reasons: list[str] = []
    if not summary or (realized_trade_count <= 0 and not runtime_evidence_present):
        status = "missing"
        reasons.append("execution_audit_missing")
    elif realized_trade_count <= 0:
        status = "bootstrap_pending"
        reasons.append("execution_audit_bootstrap_pending")
    elif realized_trade_count < 20:
        status = "insufficient_samples"
        reasons.append(f"realized_trade_count<{20}")
    else:
        if not hard_gate_metric_passes["trade_expectancy"]:
            reasons.append("trade_expectancy<=0")
        if not hard_gate_metric_passes["pnl_conversion_efficiency"]:
            reasons.append("pnl_conversion_efficiency<=0")
        if not hard_gate_metric_passes["execution_conversion_efficiency"]:
            reasons.append("execution_conversion_efficiency<0.20")
        status = "failed_metrics" if reasons else "passed"
    return status, reasons, hard_gate_metric_passes, hard_gate_metrics


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


def _build_confidence_diagnostics(
    strategy: Optional[dict],
    quality_report: Optional[dict],
    signal_quality: Optional[dict],
) -> tuple[str, dict[str, Any]]:
    strategy_payload = dict(strategy or {})
    params = dict(strategy_payload.get("params") or {})
    report_payload = dict(quality_report or {})
    confidence_contract = dict(
        report_payload.get("confidence_contract")
        or params.get("confidence_contract")
        or {}
    )
    return evaluate_confidence_contract(
        confidence_contract,
        signal_quality=signal_quality,
    )


def _normalize_execution_quality_for_contract(execution_quality: Optional[dict]) -> dict[str, Any]:
    payload = dict(execution_quality or {})
    if _confidence_diagnostics_enabled():
        return payload
    for field_name in (
        "prediction_quality_label",
        "prediction_reasons",
        "execution_quality_label",
        "execution_reasons",
        "diagnosis",
        "diagnosis_reasons",
    ):
        payload.pop(field_name, None)
    return payload


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

    audit_summary: dict[str, Any] = {}
    if _execution_audit_enabled():
        get_audit_summary = getattr(db, "get_strategy_trade_audit_summary", None)
        if callable(get_audit_summary):
            try:
                audit_summary = dict(await get_audit_summary(str(strategy.get("id") or "")) or {})
            except Exception:
                audit_summary = {}

    evidence_status = "missing_account"
    if account_id:
        evidence_status = "ready" if (total_orders > 0 or total_trades > 0 or nav_observation_days > 0) else "empty"

    result = {
        "approximate": True,
        "audit_grade": bool(audit_summary.get("audit_grade")) if audit_summary else False,
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
    gate_context = {
        **dict(audit_summary or {}),
        "account_id": account_id,
        "evidence_status": evidence_status,
        "order_count": total_orders,
        "filled_order_count": filled_orders,
        "trade_count": total_trades,
        "nav_observation_days": nav_observation_days,
    }
    if audit_summary:
        gate_status, gate_reasons, metric_passes, hard_gate_metrics = evaluate_execution_audit_gate(
            gate_context
        )
        result.update(
            {
                "audit": audit_summary,
                "audit_source_tables": list(audit_summary.get("source_tables") or []),
                "realized_trade_count": _safe_int(audit_summary.get("realized_trade_count")),
                "trade_expectancy": _safe_float(audit_summary.get("trade_expectancy")),
                "pnl_conversion_efficiency": _safe_float(
                    audit_summary.get("pnl_conversion_efficiency")
                ),
                "execution_conversion_efficiency": _safe_float(
                    audit_summary.get("execution_conversion_efficiency")
                ),
                "execution_win_rate": _safe_float(audit_summary.get("execution_win_rate")),
                "avg_win_loss_ratio": _safe_float(audit_summary.get("avg_win_loss_ratio")),
                "audit_ready_for_hard_gate": bool(
                    audit_summary.get("audit_ready_for_hard_gate")
                ),
                "execution_audit_gate_status": gate_status,
                "execution_audit_gate_reasons": gate_reasons,
                "execution_hard_gate_passed": gate_status == "passed",
                "hard_gate_metric_passes": metric_passes,
                "hard_gate_metrics": hard_gate_metrics,
                "note": (
                    "Execution metrics include proxy conversion plus additive audit round-trip metrics "
                    "based on position_id-complete samples."
                ),
            }
        )
    else:
        gate_status, gate_reasons, metric_passes, hard_gate_metrics = evaluate_execution_audit_gate(
            gate_context
        )
        result.update(
            {
                "execution_audit_gate_status": gate_status,
                "execution_audit_gate_reasons": gate_reasons,
                "execution_hard_gate_passed": False,
                "hard_gate_metric_passes": metric_passes,
                "hard_gate_metrics": hard_gate_metrics,
            }
        )
    return result


def resolve_incubation_pipeline_stage(
    signal_quality: Optional[dict],
    *,
    open_risk_count: int = 0,
    audit_summary: Optional[dict[str, Any]] = None,
    execution_audit_gate_status: Optional[str] = None,
) -> str:
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
        signal_stage_without_execution_gate = "warmup"
    elif (recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03) or (
        stability_gap is not None and stability_gap > 0.10
    ) or open_risk_count >= 3:
        signal_stage_without_execution_gate = "failed"
    elif (
        primary_effective_n >= 60
        and secondary_effective_n >= 30
        and (primary_skill_lcb or 0.0) > 0.0
        and (secondary_skill_lcb or 0.0) > 0.0
        and (recent_primary_skill_lcb or 0.0) > 0.0
        and coverage_ratio >= 0.75
        and (stability_gap is None or stability_gap <= 0.05)
        and open_risk_count == 0
    ):
        signal_stage_without_execution_gate = "graduation_ready"
    elif (
        primary_skill_lcb is None
        or primary_skill_lcb <= 0.0
        or coverage_ratio < 0.5
        or (stability_gap is not None and stability_gap > 0.08)
        or open_risk_count > 1
    ):
        signal_stage_without_execution_gate = "observe"
    else:
        signal_stage_without_execution_gate = "candidate"

    if signal_stage_without_execution_gate == "warmup":
        return "warmup"

    gate_status = execution_audit_gate_status
    if not gate_status:
        gate_status, _reasons, _passes, _metrics = evaluate_execution_audit_gate(audit_summary)
    if gate_status == "failed_metrics":
        return "failed"
    if signal_stage_without_execution_gate == "failed":
        return "failed"
    if signal_stage_without_execution_gate == "graduation_ready" and gate_status == "passed":
        return "graduation_ready"
    if signal_stage_without_execution_gate == "candidate" and gate_status == "passed":
        return "candidate"
    return "observe"


def _parse_time(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.fromisoformat(f"{text}T00:00:00+00:00")
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_date(value: Any) -> Optional[date]:
    dt = _parse_time(value)
    return dt.date() if dt is not None else None


def _estimate_stage_clock_days(
    strategy: Optional[dict[str, Any]],
    quality_report: Optional[dict[str, Any]],
    incubation_metrics: list[dict[str, Any]],
) -> int:
    strategy_payload = dict(strategy or {})
    report_payload = dict(quality_report or {})
    metric_times = [
        _parse_time(dict(item or {}).get("metric_date"))
        for item in list(incubation_metrics or [])
    ]
    metric_times = [item for item in metric_times if item is not None]
    if metric_times:
        return max(0, (max(metric_times).date() - min(metric_times).date()).days)
    start = (
        _parse_time(report_payload.get("created_at"))
        or _parse_time(report_payload.get("updated_at"))
        or _parse_time(strategy_payload.get("created_at"))
        or _parse_time(strategy_payload.get("updated_at"))
    )
    if start is None:
        return 0
    return max(0, (datetime.now(timezone.utc).date() - start.date()).days)


def _metric_signal_value(item: dict[str, Any], key: str) -> Optional[float]:
    payload = dict(item or {})
    value = payload.get(key)
    if value is None:
        value = dict(payload.get("signal_quality") or {}).get(key)
    return _safe_float(value)


def _recent_negative_skill_streak(incubation_metrics: list[dict[str, Any]]) -> int:
    streak = 0
    for metric in list(incubation_metrics or []):
        recent_skill_lcb = _metric_signal_value(metric, "recent_primary_skill_lcb")
        if recent_skill_lcb is None or recent_skill_lcb >= 0:
            break
        streak += 1
    return streak


async def resolve_incubation_action_plan(
    db,
    strategy: dict[str, Any],
    *,
    pipeline_stage: str,
    signal_quality: Optional[dict[str, Any]] = None,
    execution_quality: Optional[dict[str, Any]] = None,
    total_signals: int = 0,
    validation_grade: Optional[str] = None,
    quality_report: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    signal_payload = dict(signal_quality or {})
    execution_payload = dict(execution_quality or {})
    strategy_id = str(dict(strategy or {}).get("id") or "").strip()
    incubation_metrics: list[dict[str, Any]] = []
    list_metrics = getattr(db, "list_strategy_incubation_metrics", None)
    if callable(list_metrics) and strategy_id:
        try:
            incubation_metrics = list(await list_metrics(strategy_id, limit=10) or [])
        except Exception:
            incubation_metrics = []

    stage_clock_days = _estimate_stage_clock_days(strategy, quality_report, incubation_metrics)
    signal_vacuum_days = stage_clock_days if pipeline_stage == "warmup" and int(total_signals or 0) <= 0 else 0
    recent_primary_skill_lcb = _safe_float(signal_payload.get("recent_primary_skill_lcb"))
    stability_gap = _safe_float(signal_payload.get("stability_gap"))
    prediction_quality_label = _string(execution_payload.get("prediction_quality_label")) or "insufficient_evidence"
    execution_quality_label = _string(execution_payload.get("execution_quality_label")) or "insufficient_evidence"
    negative_skill_streak = _recent_negative_skill_streak(incubation_metrics)

    remediation_action = "continue_observe"
    remediation_reason = "stage_progression_normal"
    budget_action = "keep_bootstrap"
    runtime_control_mode = "observe_only"
    revision_required = False
    cleanup_recommended = False

    normalized_grade = _string(validation_grade).upper() or None
    if normalized_grade == "D":
        remediation_action = "cleanup_low_confidence_candidate"
        remediation_reason = "validation_grade_d_not_allowed_for_runtime"
        budget_action = "stop_runtime"
        runtime_control_mode = "research_only"
        cleanup_recommended = True
    elif (
        recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03
    ) or (
        stability_gap is not None and stability_gap > 0.10
    ) or pipeline_stage == "failed":
        remediation_action = "freeze_and_revise"
        remediation_reason = (
            "prediction_skill_negative"
            if recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03
            else "stability_break"
            if stability_gap is not None and stability_gap > 0.10
            else "pipeline_failed"
        )
        budget_action = "freeze_new_budget"
        runtime_control_mode = "exit_only"
        revision_required = True
    elif pipeline_stage == "warmup" and int(total_signals or 0) <= 0:
        remediation_reason = "signal_vacuum"
        if signal_vacuum_days >= 30:
            remediation_action = "return_to_research"
            budget_action = "stop_runtime"
            runtime_control_mode = "exit_only"
            revision_required = True
        elif signal_vacuum_days >= 20:
            remediation_action = "freeze_and_revise"
            budget_action = "freeze_new_budget"
            runtime_control_mode = "exit_only"
            revision_required = True
        elif signal_vacuum_days >= 5:
            remediation_action = "signal_vacuum_warning"
        else:
            remediation_action = "continue_observe"
    elif negative_skill_streak >= 5:
        remediation_action = "freeze_and_revise_signal_logic"
        remediation_reason = "prediction_skill_negative"
        budget_action = "freeze_new_budget"
        runtime_control_mode = "freeze_new_entries"
        revision_required = True
    elif prediction_quality_label in {"strong", "mixed"} and execution_quality_label == "weak":
        remediation_action = "execution_template_adjustment"
        remediation_reason = "execution_conversion_failure"
        budget_action = "budget_cut_50"
        runtime_control_mode = "marketable_limit_keep_observe"
        revision_required = True
    elif prediction_quality_label == "weak" and execution_quality_label != "weak":
        remediation_action = "freeze_and_revise_signal_logic"
        remediation_reason = "prediction_skill_negative"
        budget_action = "freeze_new_budget"
        runtime_control_mode = "freeze_new_entries"
        revision_required = True
    elif pipeline_stage == "candidate":
        remediation_action = "candidate_keep_observe"
        remediation_reason = "candidate_waiting_for_more_signal_and_execution_evidence"
    elif pipeline_stage == "graduation_ready":
        remediation_action = "ready_for_promotion_review"
        remediation_reason = "signal_and_execution_quality_ready"
        budget_action = "promote_budget"
        runtime_control_mode = "monitor"

    return {
        "stage_clock_days": stage_clock_days,
        "signal_vacuum_days": signal_vacuum_days,
        "remediation_action": remediation_action,
        "remediation_reason": remediation_reason,
        "budget_action": budget_action,
        "runtime_control_mode": runtime_control_mode,
        "revision_required": revision_required,
        "cleanup_recommended": cleanup_recommended,
        "negative_skill_metric_streak": negative_skill_streak,
    }


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


def _extract_runtime_playbook_provenance(strategy: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    runtime_playbook = dict(payload.get("runtime_playbook") or params.get("runtime_playbook") or {})
    provenance = dict(runtime_playbook.get("_provenance") or {})
    source_claim_ids = [
        _string(item)
        for item in list(runtime_playbook.get("source_claim_ids") or provenance.get("source_claim_ids") or [])
        if _string(item)
    ]
    source_trade_step_ids = [
        _string(item)
        for item in list(runtime_playbook.get("source_trade_step_ids") or provenance.get("source_trade_step_ids") or [])
        if _string(item)
    ]
    derivation_labels = [
        _string(item)
        for item in list(runtime_playbook.get("derivation_labels") or provenance.get("derivation_labels") or [])
        if _string(item)
    ]
    if not (source_claim_ids or source_trade_step_ids or derivation_labels or runtime_playbook):
        return {}
    derived_from_defaults = runtime_playbook.get("derived_from_defaults")
    if derived_from_defaults is None:
        derived_from_defaults = provenance.get("derived_from_defaults")
    return {
        "source_claim_ids": source_claim_ids,
        "source_trade_step_ids": source_trade_step_ids,
        "derived_from_defaults": bool(derived_from_defaults) if derived_from_defaults is not None else None,
        "derivation_labels": derivation_labels,
        "source_priority": dict(provenance.get("source_priority") or {}),
        "runtime_playbook_source": _string(provenance.get("runtime_playbook_source")) or None,
    }


def _extract_semantic_lineage(strategy: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    claim_to_trade_plan_map = dict(
        payload.get("claim_to_trade_plan_map") or params.get("claim_to_trade_plan_map") or {}
    )
    trade_plan_to_dsl_map = dict(
        payload.get("trade_plan_to_dsl_map") or params.get("trade_plan_to_dsl_map") or {}
    )
    evidence_alignment_audit = dict(
        payload.get("evidence_alignment_audit") or params.get("evidence_alignment_audit") or {}
    )
    runtime_playbook_provenance = _extract_runtime_playbook_provenance(payload)
    if not (claim_to_trade_plan_map or trade_plan_to_dsl_map or evidence_alignment_audit or runtime_playbook_provenance):
        return {}
    trade_step_sections = dict(trade_plan_to_dsl_map.get("trade_step_to_dsl_sections") or {})
    return {
        "claim_to_trade_plan_map": claim_to_trade_plan_map,
        "trade_plan_to_dsl_map": trade_plan_to_dsl_map,
        "runtime_playbook_provenance": runtime_playbook_provenance,
        "evidence_alignment_status": _string(
            evidence_alignment_audit.get("evidence_alignment_status")
            or evidence_alignment_audit.get("alignment_status")
        ) or None,
        "evidence_alignment_score": _safe_float(evidence_alignment_audit.get("evidence_alignment_score")),
        "semantic_integrity_score": _safe_float(evidence_alignment_audit.get("semantic_integrity_score")),
        "hard_fail_reasons": [
            _string(item)
            for item in list(evidence_alignment_audit.get("hard_fail_reasons") or [])
            if _string(item)
        ],
        "claim_count": len(dict(claim_to_trade_plan_map.get("claim_to_trade_step_ids") or {})),
        "mapped_trade_step_count": sum(1 for value in trade_step_sections.values() if list(value or [])),
    }


async def _build_execution_lineage(db, strategy_id: str) -> dict[str, Any]:
    list_method = getattr(db, "list_strategy_signal_evidence", None)
    if not callable(list_method):
        return {}

    try:
        rows = await list_method(strategy_id=strategy_id, limit=500)
    except TypeError:
        rows = await list_method(strategy_id=strategy_id)
    except Exception:
        return {}

    evidence_rows = [dict(item or {}) for item in list(rows or []) if isinstance(item, dict)]
    if not evidence_rows:
        return {}

    def _lineage_status(row: dict[str, Any]) -> str:
        payload = dict(row.get("payload") or {})
        explicit = _string(row.get("lineage_status") or payload.get("lineage_status"))
        if explicit:
            return explicit
        if _string(row.get("runtime_action_reason")) or _string(row.get("runtime_action_source")):
            return "mapped_runtime_action" if _string(row.get("applied_trade_step_id")) else "unmapped_runtime_action"
        if _string(row.get("applied_trade_step_id")):
            return "mapped_trade_step"
        if _string(row.get("applied_claim_id")):
            return "claim_only"
        return "missing"

    ordered_rows = sorted(
        evidence_rows,
        key=lambda item: (
            _string(item.get("signal_date")),
            _string(item.get("signal_ts")),
            _string(item.get("created_at")),
            _string(item.get("evidence_id")),
            _string(item.get("applied_trade_step_id")),
        ),
        reverse=True,
    )
    runtime_rows = [
        item
        for item in ordered_rows
        if _string(item.get("runtime_action_reason")) or _string(item.get("runtime_action_source"))
    ]
    preview_rows = runtime_rows[:8] if runtime_rows else ordered_rows[:8]
    runtime_action_reason_counts: dict[str, int] = {}
    runtime_action_source_counts: dict[str, int] = {}
    lineage_status_counts: dict[str, int] = {}
    for item in ordered_rows:
        status = _lineage_status(item)
        lineage_status_counts[status] = lineage_status_counts.get(status, 0) + 1
        reason = _string(item.get("runtime_action_reason"))
        if reason:
            runtime_action_reason_counts[reason] = runtime_action_reason_counts.get(reason, 0) + 1
        source = _string(item.get("runtime_action_source"))
        if source:
            runtime_action_source_counts[source] = runtime_action_source_counts.get(source, 0) + 1

    return {
        "signal_evidence_count": len(ordered_rows),
        "claim_count": len({_string(item.get("applied_claim_id")) for item in ordered_rows if _string(item.get("applied_claim_id"))}),
        "trade_step_count": len({_string(item.get("applied_trade_step_id")) for item in ordered_rows if _string(item.get("applied_trade_step_id"))}),
        "mapped_trade_step_count": sum(
            1 for item in ordered_rows if _string(item.get("applied_trade_step_id"))
        ),
        "runtime_action_count": len(runtime_rows),
        "unmapped_runtime_action_count": sum(
            1 for item in runtime_rows if _lineage_status(item) == "unmapped_runtime_action"
        ),
        "lineage_status_counts": lineage_status_counts,
        "runtime_action_reason_counts": runtime_action_reason_counts,
        "runtime_action_source_counts": runtime_action_source_counts,
        "recent_runtime_actions": [
            {
                "signal_id": _string(item.get("signal_id")) or None,
                "signal_date": _string(item.get("signal_date")) or None,
                "code": _string(item.get("code")) or _string(dict(item.get("payload") or {}).get("code")) or None,
                "applied_claim_id": _string(item.get("applied_claim_id")) or None,
                "applied_trade_step_id": _string(item.get("applied_trade_step_id")) or None,
                "runtime_action_reason": _string(item.get("runtime_action_reason")) or None,
                "runtime_action_source": _string(item.get("runtime_action_source")) or None,
                "lineage_status": _lineage_status(item),
            }
            for item in preview_rows
        ],
    }


# ── Incubation overview builder ──────────────────────────────────────────────

def _resolve_risk_hard_gate(
    strategy: dict,
    *,
    max_drawdown: float,
) -> dict[str, Any]:
    params = dict(strategy.get("params") or {})
    drawdown_contract = dict(
        strategy.get("drawdown_invalidation_contract")
        or params.get("drawdown_invalidation_contract")
        or {}
    )
    parameter_coherence_audit = dict(
        strategy.get("parameter_coherence_audit")
        or params.get("parameter_coherence_audit")
        or {}
    )
    reasons: list[str] = []
    status = "passed"
    apply_as_hard_gate = bool(drawdown_contract.get("apply_as_hard_gate"))
    review_drawdown_pct = _safe_float(drawdown_contract.get("review_drawdown_pct"))
    kill_drawdown_pct = _safe_float(drawdown_contract.get("kill_drawdown_pct"))
    coherence_blockers = [
        _string(item)
        for item in list(parameter_coherence_audit.get("blockers") or [])
        if _string(item)
    ]
    if coherence_blockers:
        status = "failed_parameters"
        reasons.extend(f"parameter_coherence:{item}" for item in coherence_blockers)
    if apply_as_hard_gate and kill_drawdown_pct is not None and kill_drawdown_pct > 0 and max_drawdown >= kill_drawdown_pct:
        status = "kill_switch"
        reasons.append(f"max_drawdown>={kill_drawdown_pct:.0%}")
    elif apply_as_hard_gate and review_drawdown_pct is not None and review_drawdown_pct > 0 and max_drawdown >= review_drawdown_pct and status == "passed":
        status = "forced_review"
        reasons.append(f"max_drawdown>={review_drawdown_pct:.0%}")
    return {
        "status": status,
        "reasons": list(dict.fromkeys(reasons)),
        "drawdown_invalidation_contract": drawdown_contract,
        "parameter_coherence_audit": parameter_coherence_audit,
    }


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
    runtime_bootstrap_eligible = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "runtime_bootstrap_eligible",
    )
    runtime_bootstrap_reason = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "runtime_bootstrap_reason") or ""
    ).strip() or None
    runtime_bootstrap_budget_tier = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "runtime_bootstrap_budget_tier") or ""
    ).strip().lower() or None
    runtime_playbook_present = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "runtime_playbook_present",
    )
    if runtime_playbook_present is None:
        runtime_playbook_present = bool(dict(strategy.get("params") or {}).get("runtime_playbook"))
    execution_semantic_mode = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "execution_semantic_mode")
        or dict(strategy.get("params") or {}).get("execution_semantic_mode")
        or ""
    ).strip().lower() or None
    execution_semantic_gap = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "execution_semantic_gap",
    )
    if execution_semantic_gap is None:
        execution_semantic_gap = bool(dict(strategy.get("params") or {}).get("execution_semantic_gap"))
    execution_semantic_gap_reasons = [
        _string(item)
        for item in list(
            _quality_report_field(quality_report, quality_gate, quality_summary, "execution_semantic_gap_reasons")
            or dict(strategy.get("params") or {}).get("execution_semantic_gap_reasons")
            or []
        )
        if _string(item)
    ]
    dsl_required = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "dsl_required",
    )
    if dsl_required is None:
        dsl_required = bool(dict(strategy.get("params") or {}).get("dsl_required"))
    dsl_compiled = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "dsl_compiled",
    )
    if dsl_compiled is None:
        dsl_compiled = bool(dict(strategy.get("params") or {}).get("dsl_compiled"))
    instrument_profile = dict(
        strategy.get("instrument_profile")
        or dict(strategy.get("params") or {}).get("instrument_profile")
        or {}
    )
    regime_filter_contract = dict(
        strategy.get("regime_filter_contract")
        or dict(strategy.get("params") or {}).get("regime_filter_contract")
        or {}
    )
    parameter_coherence_audit = dict(
        strategy.get("parameter_coherence_audit")
        or dict(strategy.get("params") or {}).get("parameter_coherence_audit")
        or {}
    )
    thesis_invalidation_contract = dict(
        strategy.get("thesis_invalidation_contract")
        or dict(strategy.get("params") or {}).get("thesis_invalidation_contract")
        or {}
    )
    drawdown_invalidation_contract = dict(
        strategy.get("drawdown_invalidation_contract")
        or dict(strategy.get("params") or {}).get("drawdown_invalidation_contract")
        or {}
    )
    semantic_runtime_match = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "semantic_runtime_match",
    )
    if semantic_runtime_match is None:
        semantic_runtime_match = bool(
            dict(strategy.get("params") or {}).get("semantic_runtime_match")
            if dict(strategy.get("params") or {}).get("semantic_runtime_match") is not None
            else True
        )
    runtime_family_data_source = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "runtime_family_data_source")
        or dict(strategy.get("params") or {}).get("runtime_family_data_source")
        or ""
    ).strip().lower() or None
    proxy_runtime_used = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "proxy_runtime_used",
    )
    if proxy_runtime_used is None:
        proxy_runtime_used = bool(dict(strategy.get("params") or {}).get("proxy_runtime_used"))
    strategy_type_token = str(strategy.get("strategy_type") or "").strip().lower()
    if not proxy_runtime_used and strategy_type_token in {"quality_factor", "value_factor", "growth_factor"} and runtime_family_data_source != "fundamental_runtime":
        proxy_runtime_used = True
    diagnostic_only = _quality_report_bool(
        quality_report,
        quality_gate,
        quality_summary,
        "diagnostic_only",
    )
    if diagnostic_only is None:
        diagnostic_only = bool(dict(strategy.get("params") or {}).get("diagnostic_only"))
    execution_readiness_tier = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "execution_readiness_tier")
        or dict(strategy.get("params") or {}).get("execution_readiness_tier")
        or ""
    ).strip().lower() or None
    semantic_contract_missing_fields = [
        _string(item)
        for item in list(
            _quality_report_field(quality_report, quality_gate, quality_summary, "semantic_contract_missing_fields")
            or dict(strategy.get("params") or {}).get("semantic_contract_missing_fields")
            or []
        )
        if _string(item)
    ]
    target_symbols = list(
        strategy.get("target_symbols")
        or dict(strategy.get("params") or {}).get("target_symbols")
        or []
    )
    candidate_family = str(
        _quality_report_field(quality_report, quality_gate, quality_summary, "candidate_family")
        or strategy.get("strategy_type")
        or ""
    ).strip().lower() or None
    single_name_trend = candidate_family in _TREND_EXECUTABLE_DSL_TYPES and len(target_symbols) == 1
    if not diagnostic_only and (
        proxy_runtime_used
        or (single_name_trend and (
            str(instrument_profile.get("measurement_source") or "default_board_profile").strip().lower() == "default_board_profile"
            or not bool(instrument_profile.get("measured_profile_complete"))
        ))
        or semantic_contract_missing_fields
    ):
        diagnostic_only = True
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
    execution_quality_contract = _normalize_execution_quality_for_contract(execution_quality)
    confidence_contract_status, confidence_diagnostics = _build_confidence_diagnostics(
        strategy,
        quality_report,
        signal_quality,
    )
    audit_summary = dict(execution_quality.get("audit") or {})
    execution_audit_gate_status = _string(
        execution_quality.get("execution_audit_gate_status")
    ) or None
    execution_audit_gate_reasons = [
        _string(item)
        for item in list(execution_quality.get("execution_audit_gate_reasons") or [])
        if _string(item)
    ]
    execution_hard_gate_passed = bool(execution_quality.get("execution_hard_gate_passed"))
    signal_stage_without_execution_gate = resolve_incubation_pipeline_stage(
        signal_quality,
        open_risk_count=0,
        execution_audit_gate_status="passed",
    )
    pipeline_stage = resolve_incubation_pipeline_stage(
        signal_quality,
        open_risk_count=0,
        audit_summary=audit_summary,
        execution_audit_gate_status=execution_audit_gate_status,
    )
    action_plan = await resolve_incubation_action_plan(
        db,
        strategy,
        pipeline_stage=pipeline_stage,
        signal_quality=signal_quality,
        execution_quality=execution_quality,
        total_signals=total_signals,
        validation_grade=validation_grade,
        quality_report=quality_report,
    )
    runtime_playbook_provenance = _extract_runtime_playbook_provenance(strategy)
    semantic_lineage = _extract_semantic_lineage(strategy)
    execution_lineage = await _build_execution_lineage(db, strategy["id"])
    latest_signal_snapshot = None
    get_latest_snapshot = getattr(db, "get_latest_strategy_signal_event_snapshot", None)
    if callable(get_latest_snapshot):
        try:
            latest_signal_snapshot = await get_latest_snapshot(strategy["id"])
        except Exception:
            latest_signal_snapshot = None
    if latest_signal_snapshot is None:
        list_snapshots = getattr(db, "list_strategy_signal_event_snapshots", None)
        if callable(list_snapshots):
            try:
                rows = await list_snapshots(strategy_id=strategy["id"], latest_only=True, limit=1)
                latest_signal_snapshot = dict(rows[0]) if rows else None
            except Exception:
                latest_signal_snapshot = None
    latest_signal_snapshot = dict(latest_signal_snapshot or {})
    latest_snapshot_metadata = dict(latest_signal_snapshot.get("metadata") or {})
    latest_snapshot_as_of = _coerce_date(latest_signal_snapshot.get("as_of_date"))
    latest_nonzero_signal_date = _coerce_date(
        latest_snapshot_metadata.get("latest_nonzero_signal_date")
    )
    runtime_cycle_seen_today = bool(latest_snapshot_as_of == date.today()) if latest_snapshot_as_of else False
    risk_hard_gate = _resolve_risk_hard_gate(strategy, max_drawdown=mdd)
    risk_hard_gate_status = _string(risk_hard_gate.get("status")) or "passed"
    risk_hard_gate_reasons = [
        _string(item)
        for item in list(risk_hard_gate.get("reasons") or [])
        if _string(item)
    ]
    execution_diagnostics = {
        "execution_audit_gate_status": execution_audit_gate_status,
        "execution_audit_gate_reasons": execution_audit_gate_reasons,
        "execution_hard_gate_passed": execution_hard_gate_passed,
        "diagnosis": execution_quality.get("diagnosis"),
        "diagnosis_reasons": list(execution_quality.get("diagnosis_reasons") or []),
        "signal_to_fill_ratio": execution_quality_contract.get("signal_to_fill_ratio"),
        "filled_order_ratio": execution_quality_contract.get("filled_order_ratio"),
        "nav_conversion_proxy": execution_quality_contract.get("nav_conversion_proxy"),
        "execution_conversion_efficiency": execution_quality_contract.get("execution_conversion_efficiency"),
        "remediation_action": action_plan.get("remediation_action"),
        "remediation_reason": action_plan.get("remediation_reason"),
        "diagnostic_only": bool(diagnostic_only or dict(confidence_diagnostics or {}).get("diagnostic_only")),
        "semantic_runtime_match": semantic_runtime_match,
        "runtime_family_data_source": runtime_family_data_source,
        "proxy_runtime_used": bool(proxy_runtime_used),
        "execution_readiness_tier": execution_readiness_tier,
        "semantic_contract_missing_fields": semantic_contract_missing_fields,
    }
    early_signal_stage = signal_stage_without_execution_gate in _EARLY_SIGNAL_STAGES
    if risk_hard_gate_status == "kill_switch":
        blockers.extend(item for item in risk_hard_gate_reasons if item not in blockers)
    elif risk_hard_gate_status in {"forced_review", "failed_parameters"}:
        risk_flags.extend(
            item if item.startswith("risk_hard_gate:") else f"risk_hard_gate:{item}"
            for item in risk_hard_gate_reasons
            if (item if item.startswith("risk_hard_gate:") else f"risk_hard_gate:{item}") not in risk_flags
        )
    if sharpe <= PROMOTION_THRESHOLDS["sharpe_min"]:
        sharpe_message = f"Sharpe {sharpe:.2f} \u2264 {PROMOTION_THRESHOLDS['sharpe_min']:.2f}"
        if early_signal_stage:
            risk_flags.append(f"{sharpe_message}\uff08warmup/observe \u89c2\u5bdf\u9879\uff09")
        else:
            blockers.append(sharpe_message)
    if mdd >= PROMOTION_THRESHOLDS["mdd_max"]:
        mdd_message = f"\u6700\u5927\u56de\u64a4 {mdd:.1%} \u2265 {PROMOTION_THRESHOLDS['mdd_max']:.0%}"
        mdd_excess = mdd - PROMOTION_THRESHOLDS["mdd_max"]
        if early_signal_stage and mdd_excess <= _EARLY_STAGE_PROMOTION_MDD_TOLERANCE:
            risk_flags.append(f"{mdd_message}\uff08warmup/observe \u89c2\u5bdf\u5e26\uff09")
        else:
            blockers.append(mdd_message)
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
        and execution_hard_gate_passed
        and risk_hard_gate_status == "passed"
        and not blockers
    )
    if not execution_hard_gate_passed and execution_audit_gate_status in {
        "missing",
        "insufficient_samples",
        "failed_metrics",
    }:
        execution_gate_reason = f"execution_audit_gate:{execution_audit_gate_status}"
        execution_gate_blocks_promotion = (
            execution_audit_gate_status == "failed_metrics"
            or signal_stage_without_execution_gate in _EXECUTION_AUDIT_PROMOTION_BLOCKING_STAGES
        )
        if execution_gate_blocks_promotion:
            gate_blockers.append(execution_gate_reason)
            blockers.extend(item for item in gate_blockers if item not in blockers)
        else:
            risk_flags.append(execution_gate_reason)
    if execution_semantic_gap:
        risk_flags.append(
            f"execution_semantic_gap:{execution_semantic_mode or 'missing_executable_contract'}"
        )
    promotion_gate_status = "passed" if promotion_ready else (
        execution_audit_gate_status or "missing"
    )
    deprecation_risk = bool(
        (recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03)
        or (stability_gap is not None and stability_gap > 0.10)
        or sharpe < DEPRECATION_THRESHOLDS["sharpe_negative"]
        or mdd > DEPRECATION_THRESHOLDS["mdd_critical"]
    )
    hard_gate_result = {
        "pipeline_stage": pipeline_stage,
        "signal_stage_without_execution_gate": signal_stage_without_execution_gate,
        "execution_audit_gate_status": execution_audit_gate_status or "missing",
        "execution_hard_gate_passed": execution_hard_gate_passed,
        "risk_hard_gate_status": risk_hard_gate_status,
        "risk_hard_gate_reasons": risk_hard_gate_reasons,
        "promotion_ready": promotion_ready,
        "passed": pipeline_stage in {"candidate", "graduation_ready", "promoted"} and risk_hard_gate_status == "passed",
        "reasons": list(dict.fromkeys([*gate_blockers, *execution_audit_gate_reasons, *risk_hard_gate_reasons])),
    }

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
        "execution_quality": execution_quality_contract,
        "execution_diagnostics": execution_diagnostics,
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
        "signal_to_fill_ratio": execution_quality_contract.get("signal_to_fill_ratio"),
        "filled_order_ratio": execution_quality_contract.get("filled_order_ratio"),
        "nav_conversion_proxy": execution_quality_contract.get("nav_conversion_proxy"),
        "paper_nav_return": execution_quality_contract.get("paper_nav_return"),
        **(
            {
                "prediction_quality_label": execution_quality.get("prediction_quality_label"),
                "execution_quality_label": execution_quality.get("execution_quality_label"),
                "quality_diagnosis": execution_quality.get("diagnosis"),
                "quality_diagnosis_reasons": execution_quality.get("diagnosis_reasons"),
                "signal_stage_without_execution_gate": signal_stage_without_execution_gate,
                "execution_audit_gate_status": execution_audit_gate_status,
                "execution_audit_gate_reasons": execution_audit_gate_reasons,
                "execution_hard_gate_passed": execution_hard_gate_passed,
                "promotion_gate_status": promotion_gate_status,
                "confidence_contract_status": confidence_contract_status,
                "confidence_diagnostics": confidence_diagnostics,
            }
            if _confidence_diagnostics_enabled()
            else {}
        ),
        "signal_stage_without_execution_gate": signal_stage_without_execution_gate,
        "execution_audit_gate_status": execution_audit_gate_status,
        "execution_audit_gate_reasons": execution_audit_gate_reasons,
        "execution_hard_gate_passed": execution_hard_gate_passed,
        "promotion_gate_status": promotion_gate_status,
        "pipeline_stage": pipeline_stage,
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
        "runtime_bootstrap_eligible": runtime_bootstrap_eligible,
        "runtime_bootstrap_reason": runtime_bootstrap_reason,
        "runtime_bootstrap_budget_tier": runtime_bootstrap_budget_tier,
        "runtime_playbook_present": runtime_playbook_present,
        "execution_semantic_mode": execution_semantic_mode,
        "execution_semantic_gap": execution_semantic_gap,
        "execution_semantic_gap_reasons": execution_semantic_gap_reasons,
        "semantic_runtime_match": semantic_runtime_match,
        "runtime_family_data_source": runtime_family_data_source,
        "proxy_runtime_used": bool(proxy_runtime_used),
        "diagnostic_only": bool(diagnostic_only),
        "execution_readiness_tier": execution_readiness_tier,
        "semantic_contract_missing_fields": semantic_contract_missing_fields,
        "dsl_required": dsl_required,
        "dsl_compiled": dsl_compiled,
        "instrument_profile": instrument_profile,
        "regime_filter_contract": regime_filter_contract,
        "parameter_coherence_audit": parameter_coherence_audit,
        "thesis_invalidation_contract": thesis_invalidation_contract,
        "drawdown_invalidation_contract": drawdown_invalidation_contract,
        "risk_hard_gate_status": risk_hard_gate_status,
        "risk_hard_gate_reasons": risk_hard_gate_reasons,
        "runtime_playbook_provenance": runtime_playbook_provenance,
        "semantic_lineage": semantic_lineage,
        "execution_lineage": execution_lineage,
        "latest_bar_signal": int(latest_signal_snapshot.get("latest_bar_signal") or 0) if latest_signal_snapshot else 0,
        "latest_event_action": _string(latest_signal_snapshot.get("latest_event_action")) or None,
        "latest_event_date": _string(latest_signal_snapshot.get("latest_event_date")) or None,
        "latest_nonzero_signal_date": latest_nonzero_signal_date.isoformat() if latest_nonzero_signal_date else None,
        "latest_event_action_source": _string(latest_signal_snapshot.get("latest_event_action_source")) or None,
        "recent_events": list(latest_signal_snapshot.get("recent_events") or []),
        "runtime_cycle_seen_today": runtime_cycle_seen_today,
        "latest_signal_snapshot": latest_signal_snapshot or None,
        "hard_gate_result": hard_gate_result,
        "signal_vacuum_days": _safe_int(action_plan.get("signal_vacuum_days")) if action_plan.get("signal_vacuum_days") is not None else None,
        "stage_clock_days": _safe_int(action_plan.get("stage_clock_days")) if action_plan.get("stage_clock_days") is not None else None,
        "remediation_action": action_plan.get("remediation_action"),
        "remediation_reason": action_plan.get("remediation_reason"),
        "budget_action": action_plan.get("budget_action"),
        "runtime_control_mode": action_plan.get("runtime_control_mode"),
        "revision_required": bool(action_plan.get("revision_required")),
        "cleanup_recommended": bool(action_plan.get("cleanup_recommended")),
    }
