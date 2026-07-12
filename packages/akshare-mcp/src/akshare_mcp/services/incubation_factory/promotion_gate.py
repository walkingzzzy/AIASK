"""孵化工厂 · Layer 3 晋升门（host adapter）。

纯判定归属 strategy_factory.infrastructure.promotion.dsr_gate。
本模块保留 DB 前向序列装载与 re-export，保证既有 import 路径兼容。
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from strategy_factory.infrastructure.promotion.dsr_gate import (
    PROMOTION_DSR_MIN_DEFAULT,
    PROMOTION_DSR_MIN_SAMPLE_SIZE,
    PromotionGate,
    PromotionGateVerdict,
    promotion_dsr_gate_enabled,
)

# Backward-compatible private name used by tests / call sites.
_promotion_gate_enabled = promotion_dsr_gate_enabled

logger = logging.getLogger(__name__)


def _finite_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


async def fetch_forward_return_series(
    db: Any,
    strategy_id: str,
    *,
    horizon_days: int = 5,
    lookback_days: Optional[int] = None,
) -> list[float]:
    """从 signal_forward_returns 读取指定主窗口的前向收益序列（host I/O）。"""
    getter = getattr(db, "list_signal_forward_returns", None)
    if callable(getter):
        try:
            rows = await getter(strategy_id, forward_days=horizon_days, lookback_days=lookback_days)
            values: list[float] = []
            for row in rows or []:
                numeric = _finite_float(dict(row or {}).get("actual_return"))
                if numeric is not None:
                    values.append(numeric)
            return values
        except Exception as exc:
            logger.debug("fetch_forward_return_series: list method failed: %s", exc)
    stats_getter = getattr(db, "get_signal_stats", None)
    if callable(stats_getter):
        try:
            stats = await stats_getter(strategy_id, lookback_days=lookback_days)
            series = dict(stats or {}).get("forward_return_series") or {}
            horizon_series = series.get(str(horizon_days)) or series.get(horizon_days)
            if horizon_series:
                values = []
                for item in horizon_series:
                    numeric = _finite_float(item)
                    if numeric is not None:
                        values.append(numeric)
                return values
        except Exception as exc:
            logger.debug("fetch_forward_return_series: stats fallback failed: %s", exc)
    return []


__all__ = [
    "PROMOTION_DSR_MIN_DEFAULT",
    "PROMOTION_DSR_MIN_SAMPLE_SIZE",
    "PromotionGate",
    "PromotionGateVerdict",
    "fetch_forward_return_series",
    "_promotion_gate_enabled",
    "promotion_dsr_gate_enabled",
]
