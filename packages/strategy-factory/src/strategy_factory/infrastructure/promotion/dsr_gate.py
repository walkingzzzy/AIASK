"""Layer-3 DSR promotion gate pure evaluator (forward returns).

Host packages may wrap DB I/O; this module owns thresholds + evaluate().
Default OFF via STRATEGY_FACTORY_PROMOTION_DSR_ENABLED.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence


PROMOTION_DSR_MIN_DEFAULT: float = 0.60
PROMOTION_DSR_MIN_SAMPLE_SIZE: int = 30
PROMOTION_DSR_PERIODS_PER_YEAR: float = 252.0


def promotion_dsr_gate_enabled() -> bool:
    return str(os.getenv("STRATEGY_FACTORY_PROMOTION_DSR_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


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


@dataclass(slots=True)
class PromotionGateVerdict:
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
    dsr_min: float = PROMOTION_DSR_MIN_DEFAULT
    min_sample_size: int = PROMOTION_DSR_MIN_SAMPLE_SIZE
    periods_per_year: float = PROMOTION_DSR_PERIODS_PER_YEAR

    def evaluate(
        self,
        forward_returns: Sequence[float],
        *,
        n_trials: int = 1,
        benchmark_sharpe: float = 0.0,
        dsr_fn: Optional[Any] = None,
    ) -> PromotionGateVerdict:
        series: list[float] = []
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
        except Exception as exc:
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
                passed=False,
                eligible=False,
                reasons=reasons,
                dsr=dsr,
                observed_sharpe=observed_sharpe,
                effective_trials=effective_trials,
                sample_size=n,
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
            from aiask_quant_core.validation import deflated_sharpe_ratio

            return deflated_sharpe_ratio
        except Exception:
            try:
                from aiask_quant_core._validation_support import deflated_sharpe_ratio

                return deflated_sharpe_ratio
            except Exception:
                return None


__all__ = [
    "PROMOTION_DSR_MIN_DEFAULT",
    "PROMOTION_DSR_MIN_SAMPLE_SIZE",
    "PROMOTION_DSR_PERIODS_PER_YEAR",
    "PromotionGate",
    "PromotionGateVerdict",
    "promotion_dsr_gate_enabled",
]
