"""孵化工厂 · Layer 3 晋升门（INVERT-DESIGN P3 改动B）。

把 Gate-3 的统计武器（Deflated Sharpe Ratio / 多重检验校正）从"准入前置门"
搬迁为"晋升资本门"，且**作用于前向真实数据**而非回测内数据。

输入：策略累积的**前向收益序列**（来自 signal_forward_returns，经 db.get_signal_stats
或直接前向序列获取）+ 观察池规模 n_trials（用于选择偏差校正，DSR 的核心）。

输出：是否够格从 observe 晋升到 candidate/资本候选。

判定（与设计方案 §4 改动B / §6.1 一致）：
- DSR（喂前向序列 + n_trials）≥ 阈值：真实 Sharpe>0 在多重检验下显著。
- 前向 skill_lcb 显著正（由 ObservationLifecyclePolicy / overview 把关，本门聚焦统计校正）。
- 样本不足时不晋升也不阻断（passed=False, eligible=False，交时间继续累积）。

默认 OFF（toggle 控制），ON 时才把 DSR 校正纳入晋升判定，保证零行为变化。
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)


def _finite_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _safe_float(value: Any, default: float = 0.0) -> float:
    numeric = _finite_float(value)
    if numeric is not None:
        return numeric
    fallback = _finite_float(default)
    return fallback if fallback is not None else 0.0


def _safe_int(value: Any, default: int = 0) -> int:
    numeric = _finite_float(value)
    if numeric is not None:
        return int(numeric)
    fallback = _finite_float(default)
    return int(fallback if fallback is not None else 0)


def _promotion_gate_enabled() -> bool:
    """INVERT-DESIGN P3：是否把 DSR 校正纳入晋升判定（默认 OFF，零变化）。"""
    return str(
        os.getenv("STRATEGY_FACTORY_PROMOTION_DSR_ENABLED") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class PromotionGateVerdict:
    """晋升门判定结果 + 可解释证据。"""

    passed: bool
    eligible: bool
    reasons: list[str]
    dsr: Optional[float] = None
    observed_sharpe: Optional[float] = None
    effective_trials: Optional[float] = None
    sample_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "eligible": bool(self.eligible),
            "reasons": list(self.reasons),
            "dsr": self.dsr,
            "observed_sharpe": self.observed_sharpe,
            "effective_trials": self.effective_trials,
            "sample_size": int(self.sample_size),
        }


@dataclass(slots=True)
class PromotionGate:
    """Layer 3 晋升门：用前向序列跑 DSR，做多重检验校正。"""

    # DSR 下界：真实 Sharpe>0 概率达到此值才算通过（López de Prado/Bailey 范式）。
    dsr_min: float = 0.60
    # 前向序列最小样本量（低于此值不评估，交时间累积）。
    min_sample_size: int = 30
    # 年化系数（前向收益按交易日序列计）。
    periods_per_year: float = 252.0

    def evaluate(
        self,
        forward_returns: Sequence[float],
        *,
        n_trials: int = 1,
        benchmark_sharpe: float = 0.0,
        dsr_fn: Optional[Any] = None,
    ) -> PromotionGateVerdict:
        """对前向收益序列跑 DSR。

        Args:
            forward_returns: 策略累积的前向收益序列（主窗口）。
            n_trials: 同期被观察/海选的策略数量，用于选择偏差校正（DSR 核心输入）。
            benchmark_sharpe: 基准 Sharpe（默认 0）。
            dsr_fn: 可注入的 deflated_sharpe_ratio 实现；缺省时惰性 import 生产实现。
        """
        series = []
        for item in forward_returns or []:
            numeric = _finite_float(item)
            if numeric is not None:
                series.append(numeric)
        n = len(series)
        reasons: list[str] = []

        if n < int(self.min_sample_size):
            reasons.append(f"insufficient_forward_samples:{n}<{self.min_sample_size}")
            return PromotionGateVerdict(
                passed=False, eligible=False, reasons=reasons, sample_size=n
            )

        fn = dsr_fn or self._resolve_dsr_fn()
        if fn is None:
            reasons.append("dsr_fn_unavailable")
            return PromotionGateVerdict(
                passed=False, eligible=False, reasons=reasons, sample_size=n
            )

        try:
            import numpy as np

            result = fn(
                np.asarray(series, dtype=float),
                n_trials=max(1, _safe_int(n_trials, 1)),
                benchmark_sharpe=_safe_float(benchmark_sharpe, 0.0),
                periods_per_year=max(1.0, _safe_float(self.periods_per_year, 252.0)),
            )
        except Exception as exc:  # 软降级：统计失败不误晋升
            reasons.append(f"dsr_exception:{type(exc).__name__}")
            return PromotionGateVerdict(
                passed=False, eligible=False, reasons=reasons, sample_size=n
            )

        result = dict(result or {})
        dsr = _safe_float(result.get("dsr"))
        observed_sharpe = _safe_float(result.get("observed_sharpe"))
        effective_trials = _safe_float(result.get("effective_trials"))
        available = bool(result.get("available"))

        if not available:
            reasons.append("dsr_not_available")
            return PromotionGateVerdict(
                passed=False, eligible=False, reasons=reasons,
                dsr=dsr, observed_sharpe=observed_sharpe,
                effective_trials=effective_trials, sample_size=n,
            )

        passed = dsr >= float(self.dsr_min)
        if passed:
            reasons.append(f"dsr_pass:{dsr:.4f}>={self.dsr_min}")
        else:
            reasons.append(f"dsr_below_min:{dsr:.4f}<{self.dsr_min}")
        return PromotionGateVerdict(
            passed=passed,
            eligible=True,
            reasons=reasons,
            dsr=dsr,
            observed_sharpe=observed_sharpe,
            effective_trials=effective_trials,
            sample_size=n,
        )

    @staticmethod
    def _resolve_dsr_fn() -> Optional[Any]:
        try:
            from ..validation import deflated_sharpe_ratio

            return deflated_sharpe_ratio
        except Exception:  # pragma: no cover - import 降级
            try:
                from .._validation_support import deflated_sharpe_ratio

                return deflated_sharpe_ratio
            except Exception:
                return None


async def fetch_forward_return_series(
    db: Any,
    strategy_id: str,
    *,
    horizon_days: int = 5,
    lookback_days: Optional[int] = None,
) -> list[float]:
    """从 signal_forward_returns 读取指定主窗口的前向收益序列。

    复用 db.get_signal_stats 已 JOIN 的逻辑不便（它聚合了），这里直接走
    list 接口；若 db 无专用方法，回退用 get_signals + 逐条读取（best-effort）。
    """
    # 优先：若 db 暴露了原始前向序列方法。
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
    # 回退：用 get_signal_stats 暴露的 per-horizon 序列（若有）。
    stats_getter = getattr(db, "get_signal_stats", None)
    if callable(stats_getter):
        try:
            stats = await stats_getter(strategy_id, lookback_days=lookback_days)
            series = dict(stats or {}).get("forward_return_series") or {}
            horizon_series = series.get(str(horizon_days)) or series.get(horizon_days)
            if horizon_series:
                values: list[float] = []
                for item in horizon_series:
                    numeric = _finite_float(item)
                    if numeric is not None:
                        values.append(numeric)
                return values
        except Exception as exc:
            logger.debug("fetch_forward_return_series: stats fallback failed: %s", exc)
    return []


__all__ = [
    "PromotionGate",
    "PromotionGateVerdict",
    "fetch_forward_return_series",
    "_promotion_gate_enabled",
]
