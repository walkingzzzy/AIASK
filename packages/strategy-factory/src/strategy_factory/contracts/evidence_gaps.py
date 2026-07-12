"""Pure evidence-gap schema helpers owned by Strategy Factory.

DB-backed collectors remain in host diagnostics services; these helpers
normalize coverage ratios and gap tokens so Desktop/Agent contracts stay
stable across packages.
"""

from __future__ import annotations

from typing import Any, Optional


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def evaluate_signal_id_coverage(
    *,
    order_count: Any = 0,
    orders_with_signal_id: Any = 0,
    required_coverage: float = 1.0,
) -> dict[str, Any]:
    """Compute signal_id coverage + gap tokens from aggregate counts."""
    total = max(0, _safe_int(order_count))
    with_id = max(0, _safe_int(orders_with_signal_id))
    if with_id > total:
        with_id = total
    coverage = (float(with_id) / float(total)) if total > 0 else None
    gaps: list[str] = []
    if total <= 0:
        gaps.append("no_orders_sampled")
    elif coverage is None:
        gaps.append("coverage_unknown")
    elif coverage < float(required_coverage):
        gaps.append("signal_id_coverage_below_required")
        missing = total - with_id
        if missing > 0:
            gaps.append(f"orders_missing_signal_id:{missing}")
    return {
        "order_count": total,
        "orders_with_signal_id": with_id,
        "orders_missing_signal_id": max(0, total - with_id),
        "signal_id_coverage": coverage,
        "order_signal_id_coverage": coverage,
        "required_coverage": float(required_coverage),
        "gaps": gaps,
        "complete": not gaps or gaps == ["no_orders_sampled"],
    }


def evaluate_evidence_gap_summary(
    *,
    order_count: Any = 0,
    orders_with_signal_id: Any = 0,
    trade_count: Any = 0,
    trades_with_position_link: Any = 0,
    hard_gate_status: str | None = None,
    required_signal_id_coverage: float = 1.0,
) -> dict[str, Any]:
    """Combine lineage coverage + optional hard-gate status into gap summary."""
    signal = evaluate_signal_id_coverage(
        order_count=order_count,
        orders_with_signal_id=orders_with_signal_id,
        required_coverage=required_signal_id_coverage,
    )
    trades = max(0, _safe_int(trade_count))
    linked = max(0, _safe_int(trades_with_position_link))
    if linked > trades:
        linked = trades
    position_link_coverage = (float(linked) / float(trades)) if trades > 0 else None
    gaps = list(signal["gaps"])
    if trades > 0 and position_link_coverage is not None and position_link_coverage < 1.0:
        gaps.append("trade_position_link_incomplete")
        gaps.append(f"trades_missing_position_link:{trades - linked}")
    status = str(hard_gate_status or "").strip() or None
    if status and status not in {"passed", "bootstrap_ready"}:
        gaps.append(f"hard_gate:{status}")
    return {
        **signal,
        "trade_count": trades,
        "trades_with_position_link": linked,
        "position_link_coverage": position_link_coverage,
        "hard_gate_status": status,
        "gaps": list(dict.fromkeys(gaps)),
        "evidence_complete": (
            signal.get("complete") is True
            and (trades <= 0 or position_link_coverage == 1.0)
            and (status in {None, "passed", "bootstrap_ready"})
        ),
    }


__all__ = [
    "evaluate_evidence_gap_summary",
    "evaluate_signal_id_coverage",
]
