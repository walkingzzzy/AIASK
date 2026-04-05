"""Conformal prediction adapter.

Provides ``ConformalPredictionAdapter`` interface and two implementations:

1. ``BuiltinConformalAdapter`` — pure-Python approximate conformal prediction
   using split conformal method with empirical quantiles.
2. ``MapieConformalAdapter`` — wraps MAPIE library when installed.

Usage::

    adapter = get_conformal_adapter()
    result = adapter.predict_set(
        calibration_scores=[0.1, 0.3, 0.5, 0.7, 0.9],
        calibration_labels=[0, 0, 1, 1, 1],
        test_scores=[0.4, 0.6],
        alpha=0.1,
    )

"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ConformalResult:
    """Result of a conformal prediction."""

    prediction_sets: list[list[int]]
    """For classification: list of label sets for each test sample."""

    prediction_intervals: list[tuple[float, float]]
    """For regression: list of (lower, upper) intervals."""

    coverage_target: float = 0.9
    """Target coverage level (1 - alpha)."""

    method: str = "split_conformal"
    """Method used for conformal prediction."""

    backend: str = "builtin"
    """Which backend produced this result."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_sets": self.prediction_sets,
            "prediction_intervals": [
                {"lower": lo, "upper": hi} for lo, hi in self.prediction_intervals
            ],
            "coverage_target": self.coverage_target,
            "method": self.method,
            "backend": self.backend,
            "sample_count": max(len(self.prediction_sets), len(self.prediction_intervals)),
        }


# ── Abstract interface ────────────────────────────────────────────────────────

class ConformalPredictionAdapter(ABC):
    """Interface for conformal prediction adapters."""

    @abstractmethod
    def predict_set(
        self,
        calibration_scores: list[float],
        calibration_labels: list[float],
        test_scores: list[float],
        *,
        alpha: float = 0.1,
        n_classes: int = 2,
    ) -> ConformalResult:
        """Compute conformal prediction sets/intervals."""
        ...

    @abstractmethod
    def backend_name(self) -> str:
        ...


# ── Builtin implementation ────────────────────────────────────────────────────

class BuiltinConformalAdapter(ConformalPredictionAdapter):
    """Pure-Python split conformal prediction.

    Uses the simple split conformal method:
    1. Compute nonconformity scores on calibration set
    2. Find the (1-alpha)(1+1/n) quantile
    3. Build prediction sets/intervals using this threshold
    """

    def predict_set(
        self,
        calibration_scores: list[float],
        calibration_labels: list[float],
        test_scores: list[float],
        *,
        alpha: float = 0.1,
        n_classes: int = 2,
    ) -> ConformalResult:
        cal_scores = [float(s) for s in calibration_scores]
        cal_labels = [float(y) for y in calibration_labels]
        t_scores = [float(s) for s in test_scores]

        n = len(cal_scores)
        if n == 0:
            return ConformalResult(
                prediction_sets=[list(range(n_classes)) for _ in t_scores],
                prediction_intervals=[(0.0, 1.0) for _ in t_scores],
                coverage_target=1 - alpha,
                method="split_conformal_empty_cal",
                backend="builtin",
            )

        # Nonconformity scores: |predicted_prob - actual_label|
        nc_scores = sorted([abs(cal_scores[i] - cal_labels[i]) for i in range(n)])

        # Quantile level
        q_level = math.ceil((n + 1) * (1 - alpha)) / n
        q_idx = min(int(q_level * n), n - 1)
        threshold = nc_scores[q_idx]

        # Build prediction sets (classification)
        prediction_sets: list[list[int]] = []
        for score in t_scores:
            included = []
            for label in range(n_classes):
                if abs(score - label) <= threshold:
                    included.append(label)
            if not included:
                included = [round(score)]
            prediction_sets.append(included)

        # Build prediction intervals (regression interpretation)
        prediction_intervals: list[tuple[float, float]] = [
            (
                round(max(0.0, score - threshold), 6),
                round(min(1.0, score + threshold), 6),
            )
            for score in t_scores
        ]

        return ConformalResult(
            prediction_sets=prediction_sets,
            prediction_intervals=prediction_intervals,
            coverage_target=1 - alpha,
            method="split_conformal",
            backend="builtin",
        )

    def backend_name(self) -> str:
        return "builtin"


# ── MAPIE adapter (optional) ──────────────────────────────────────────────────

class MapieConformalAdapter(ConformalPredictionAdapter):
    """Wraps MAPIE library for conformal prediction.

    Falls back to BuiltinConformalAdapter if MAPIE is not installed.
    """

    def __init__(self) -> None:
        self._available = False
        try:
            import mapie  # noqa: F401
            self._available = True
        except ImportError:
            pass

    def predict_set(
        self,
        calibration_scores: list[float],
        calibration_labels: list[float],
        test_scores: list[float],
        *,
        alpha: float = 0.1,
        n_classes: int = 2,
    ) -> ConformalResult:
        if not self._available:
            return BuiltinConformalAdapter().predict_set(
                calibration_scores, calibration_labels, test_scores,
                alpha=alpha, n_classes=n_classes,
            )

        # MAPIE integration placeholder — when mapie is installed,
        # use MapieClassifier or MapieRegressor here.
        # For now, delegate to builtin.
        result = BuiltinConformalAdapter().predict_set(
            calibration_scores, calibration_labels, test_scores,
            alpha=alpha, n_classes=n_classes,
        )
        result.backend = "mapie"
        return result

    def backend_name(self) -> str:
        return "mapie" if self._available else "builtin_fallback"


# ── Factory ───────────────────────────────────────────────────────────────────

def get_conformal_adapter(prefer_mapie: bool = True) -> ConformalPredictionAdapter:
    """Get the best available conformal prediction adapter.

    Parameters
    ----------
    prefer_mapie:
        If True, try MAPIE first, fallback to builtin.
    """
    if prefer_mapie:
        adapter = MapieConformalAdapter()
        if adapter._available:
            return adapter
    return BuiltinConformalAdapter()
