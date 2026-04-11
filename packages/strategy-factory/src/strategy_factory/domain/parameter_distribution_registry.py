"""Historical parameter distribution sampling for strategy spawner."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping, Optional


class ParameterDistributionRegistry:
    """Build lightweight historical parameter distributions by strategy type.

    The registry is intentionally conservative:
    - only OOS-passing samples are retained;
    - a minimum sample size is required before sampling can override defaults;
    - sampled params stay close to the historical envelope instead of exploring
      arbitrarily large values around a single noisy winner.
    """

    MIN_SAMPLE_COUNT = 3
    MIN_TOTAL_SIGNALS = 10
    QUALIFYING_GRADES = frozenset({"A", "B", "C"})
    BASELINE_FORWARD_DAYS = frozenset({5, 10, 20})

    def __init__(self, samples: Optional[Iterable[Mapping[str, Any]]] = None):
        self._records_by_type: dict[str, list[dict[str, Any]]] = {}
        for item in list(samples or []):
            record = self._normalize_record(item)
            if not record:
                continue
            self._records_by_type.setdefault(record["strategy_type"], []).append(record)
        for strategy_type, records in list(self._records_by_type.items()):
            self._records_by_type[strategy_type] = sorted(
                records,
                key=lambda item: (
                    -float(item.get("sampling_weight") or 0.0),
                    -int(item.get("total_signals") or 0),
                    str(item.get("strategy_id") or ""),
                ),
            )

    @classmethod
    def from_snapshot(cls, snapshot: Optional[Mapping[str, Any]]) -> "ParameterDistributionRegistry":
        payload = dict(snapshot or {})
        samples = (
            payload.get("parameter_distribution_samples")
            or payload.get("historical_parameter_samples")
            or payload.get("parameter_distribution_registry")
            or []
        )
        if isinstance(samples, dict):
            samples = samples.get("items") or samples.get("samples") or []
        return cls(samples)

    @classmethod
    def _safe_int(cls, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @classmethod
    def _safe_float(cls, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    @classmethod
    def _is_number(cls, value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _normalize_record(cls, payload: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        raw = dict(payload or {})
        strategy_type = str(raw.get("strategy_type") or "").strip()
        params = dict(raw.get("params") or {})
        if not strategy_type or not params:
            return None

        validation_grade = str(raw.get("validation_grade") or "").strip().upper()
        total_signals = max(0, cls._safe_int(raw.get("total_signals"), 0))
        observed_forward_days = {
            cls._safe_int(item, 0)
            for item in list(raw.get("observed_forward_days") or [])
            if cls._safe_int(item, 0) > 0
        }
        quality_passed = bool(raw.get("quality_passed"))
        promotion_ready = bool(raw.get("promotion_ready"))
        explicit_oos = raw.get("oos_passed")
        if explicit_oos is None:
            explicit_oos = (
                quality_passed
                and validation_grade in cls.QUALIFYING_GRADES
                and total_signals >= cls.MIN_TOTAL_SIGNALS
                and bool(observed_forward_days & cls.BASELINE_FORWARD_DAYS)
            )
        if not explicit_oos:
            return None

        weight = cls._safe_float(raw.get("sampling_weight"), 0.0)
        if weight <= 0.0:
            grade_score = {"A": 1.0, "B": 0.85, "C": 0.7}.get(validation_grade, 0.55)
            coverage_score = min(len(observed_forward_days & cls.BASELINE_FORWARD_DAYS) / 3.0, 1.0)
            signal_score = min(total_signals / 20.0, 1.0)
            weight = round(
                grade_score
                + coverage_score * 0.4
                + signal_score * 0.3
                + (0.2 if promotion_ready else 0.0),
                4,
            )

        return {
            "strategy_id": str(raw.get("strategy_id") or "").strip(),
            "strategy_type": strategy_type,
            "params": deepcopy(params),
            "validation_grade": validation_grade or "UNKNOWN",
            "quality_passed": quality_passed,
            "promotion_ready": promotion_ready,
            "total_signals": total_signals,
            "observed_forward_days": sorted(observed_forward_days),
            "sampling_weight": weight,
        }

    def sample_count(self, strategy_type: str) -> int:
        return len(self._records_by_type.get(str(strategy_type or "").strip(), []))

    def has_distribution(self, strategy_type: str) -> bool:
        return self.sample_count(strategy_type) >= self.MIN_SAMPLE_COUNT

    def has_any_distribution(self) -> bool:
        return any(len(records) >= self.MIN_SAMPLE_COUNT for records in self._records_by_type.values())

    def sample(self, strategy_type: str, idx: int) -> Optional[dict[str, Any]]:
        strategy_key = str(strategy_type or "").strip()
        records = list(self._records_by_type.get(strategy_key) or [])
        if len(records) < self.MIN_SAMPLE_COUNT:
            return None
        anchor = dict(records[idx % len(records)] or {})
        params = self._sample_params(
            dict(anchor.get("params") or {}),
            [dict(item.get("params") or {}) for item in records],
            idx=max(0, int(idx or 0)),
        )
        return {
            "params": params,
            "source": "historical_distribution",
            "sample_count": len(records),
            "anchor_strategy_id": anchor.get("strategy_id"),
            "sampling_weight": anchor.get("sampling_weight"),
        }

    @classmethod
    def _sample_params(
        cls,
        anchor: dict[str, Any],
        cohort: list[dict[str, Any]],
        *,
        idx: int,
    ) -> dict[str, Any]:
        sampled: dict[str, Any] = {}
        for position, (key, value) in enumerate(anchor.items()):
            cohort_values = [item.get(key) for item in cohort if key in item]
            sampled[key] = cls._sample_value(value, cohort_values, idx=idx, position=position)
        return sampled

    @classmethod
    def _sample_value(
        cls,
        anchor_value: Any,
        cohort_values: list[Any],
        *,
        idx: int,
        position: int,
    ) -> Any:
        if cls._is_number(anchor_value):
            numeric_values = [
                float(value)
                for value in cohort_values
                if cls._is_number(value)
            ]
            if len(numeric_values) < cls.MIN_SAMPLE_COUNT:
                return anchor_value
            lo = min(numeric_values)
            hi = max(numeric_values)
            center = float(anchor_value)
            span = max(hi - lo, 0.0)
            if span <= 1e-9:
                return int(round(center)) if isinstance(anchor_value, int) else round(center, 4)
            direction = -1.0 if (idx + position) % 2 else 1.0
            step = min(span * 0.18, span / 2.0)
            candidate = max(lo, min(hi, center + direction * step))
            if isinstance(anchor_value, int):
                return int(round(candidate))
            return round(candidate, 4)

        if isinstance(anchor_value, dict):
            nested_keys = [
                str(key or "").strip()
                for key in anchor_value.keys()
                if str(key or "").strip()
            ]
            if not nested_keys:
                return deepcopy(anchor_value)
            nested_values: dict[str, list[float]] = {}
            numeric_only = True
            for key in nested_keys:
                values: list[float] = []
                for item in cohort_values:
                    nested = dict(item or {}) if isinstance(item, Mapping) else {}
                    value = nested.get(key)
                    if not cls._is_number(value):
                        numeric_only = False
                        break
                    values.append(float(value))
                if not numeric_only:
                    break
                nested_values[key] = values
            if not numeric_only:
                return deepcopy(anchor_value)

            sampled = {}
            for offset, key in enumerate(nested_keys):
                anchor_component = float(anchor_value.get(key) or 0.0)
                values = nested_values.get(key) or [anchor_component]
                mean_value = sum(values) / max(len(values), 1)
                blended = max(0.0, (anchor_component * 0.7) + (mean_value * 0.3))
                if len(values) >= cls.MIN_SAMPLE_COUNT:
                    lo = min(values)
                    hi = max(values)
                    span = max(hi - lo, 0.0)
                    if span > 1e-9:
                        direction = -1.0 if (idx + position + offset) % 2 else 1.0
                        blended = max(lo, min(hi, blended + direction * span * 0.08))
                sampled[key] = round(blended, 4)
            total = sum(sampled.values()) or 1.0
            return {key: round(value / total, 4) for key, value in sampled.items()}

        return deepcopy(anchor_value)


__all__ = ["ParameterDistributionRegistry"]
