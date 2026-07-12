"""Canonical execution hard-gate contract owned by Strategy Factory.

Pure-function ownership for production trade floors and audit-gate status.
Host packages (akshare-mcp) must re-export / delegate here so threshold
semantics cannot drift across packages.

Locked production semantics (DoD / regression snapshot):
- production_trade_floor default == 20
- trade_expectancy must be > 0
- pnl_conversion_efficiency must be > 0
- execution_conversion_efficiency must be >= 0.20

Statuses (ordered progression):
missing -> bootstrap_pending -> insufficient_samples
  -> failed_metrics | bootstrap_ready | passed
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from strategy_factory.domain.constants import (
    BACKTEST_TYPE_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
)


# ---------------------------------------------------------------------------
# Locked threshold snapshot (importable by tests; do not silently change)
# ---------------------------------------------------------------------------
PRODUCTION_TRADE_FLOOR_DEFAULT: int = 20
TRADE_EXPECTANCY_MIN_EXCLUSIVE: float = 0.0
PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE: float = 0.0
EXECUTION_CONVERSION_EFFICIENCY_MIN: float = 0.20

HARD_GATE_STATUSES: tuple[str, ...] = (
    "missing",
    "bootstrap_pending",
    "insufficient_samples",
    "failed_metrics",
    "bootstrap_ready",
    "passed",
)


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


def evaluate_execution_audit_gate(
    audit_summary: Optional[Mapping[str, Any] | dict[str, Any]],
    *,
    strategy_type: Optional[str] = None,
    bootstrap_trade_floor: Optional[int] = None,
    production_trade_floor: int = PRODUCTION_TRADE_FLOOR_DEFAULT,
) -> tuple[str, list[str], dict[str, bool], dict[str, float | int | None]]:
    """Evaluate paper/live execution audit against production hard gates.

    Returns:
        status: one of HARD_GATE_STATUSES
        reasons: human/machine readable blocker tokens
        hard_gate_metric_passes: per-metric booleans
        hard_gate_metrics: numeric snapshot used by diagnostics
    """
    summary = dict(audit_summary or {})
    normalized_strategy_type = _string(
        summary.get("strategy_type") or strategy_type
    ).lower()
    resolved_bootstrap_trade_floor = max(
        1,
        _safe_int(
            bootstrap_trade_floor,
            max(
                _safe_int(PROVISIONAL_PASS_THRESHOLDS.get("trades_min"), 2),
                _safe_int(
                    dict(BACKTEST_TYPE_THRESHOLDS.get(normalized_strategy_type) or {}).get(
                        "trades_min"
                    ),
                    0,
                ),
            ),
        ),
    )
    resolved_production_trade_floor = max(
        int(production_trade_floor or PRODUCTION_TRADE_FLOOR_DEFAULT),
        resolved_bootstrap_trade_floor,
    )
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
    execution_conversion_efficiency = _safe_float(
        summary.get("execution_conversion_efficiency")
    )
    hard_gate_metrics: dict[str, float | int | None] = {
        "realized_trade_count": realized_trade_count,
        "trade_expectancy": trade_expectancy,
        "pnl_conversion_efficiency": pnl_conversion_efficiency,
        "execution_conversion_efficiency": execution_conversion_efficiency,
        "bootstrap_trade_floor": resolved_bootstrap_trade_floor,
        "required_trade_count": resolved_production_trade_floor,
    }
    hard_gate_metric_passes = {
        "bootstrap_trade_count": realized_trade_count >= resolved_bootstrap_trade_floor,
        "realized_trade_count": realized_trade_count >= resolved_production_trade_floor,
        "trade_expectancy": (
            trade_expectancy is not None
            and trade_expectancy > TRADE_EXPECTANCY_MIN_EXCLUSIVE
        ),
        "pnl_conversion_efficiency": (
            pnl_conversion_efficiency is not None
            and pnl_conversion_efficiency > PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE
        ),
        "execution_conversion_efficiency": (
            execution_conversion_efficiency is not None
            and execution_conversion_efficiency >= EXECUTION_CONVERSION_EFFICIENCY_MIN
        ),
    }
    reasons: list[str] = []
    if not summary or (realized_trade_count <= 0 and not runtime_evidence_present):
        status = "missing"
        reasons.append("execution_audit_missing")
    elif realized_trade_count <= 0:
        status = "bootstrap_pending"
        reasons.append("execution_audit_bootstrap_pending")
    elif realized_trade_count < resolved_bootstrap_trade_floor:
        status = "insufficient_samples"
        reasons.append(f"realized_trade_count<{resolved_bootstrap_trade_floor}")
    else:
        if not hard_gate_metric_passes["trade_expectancy"]:
            reasons.append("trade_expectancy<=0")
        if not hard_gate_metric_passes["pnl_conversion_efficiency"]:
            reasons.append("pnl_conversion_efficiency<=0")
        if not hard_gate_metric_passes["execution_conversion_efficiency"]:
            reasons.append("execution_conversion_efficiency<0.20")
        if reasons:
            status = "failed_metrics"
        elif realized_trade_count < resolved_production_trade_floor:
            status = "bootstrap_ready"
            reasons.append(f"realized_trade_count<{resolved_production_trade_floor}")
        else:
            status = "passed"
    return status, reasons, hard_gate_metric_passes, hard_gate_metrics


__all__ = [
    "EXECUTION_CONVERSION_EFFICIENCY_MIN",
    "HARD_GATE_STATUSES",
    "PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE",
    "PRODUCTION_TRADE_FLOOR_DEFAULT",
    "TRADE_EXPECTANCY_MIN_EXCLUSIVE",
    "evaluate_execution_audit_gate",
]
