"""Data validation adapter.

Provides ``DataValidationAdapter`` interface and two implementations:

1. ``BuiltinValidationAdapter`` — uses existing ``data_quality.py`` logic
   to validate datasets, create checkpoints, and produce validation results.
2. ``GreatExpectationsAdapter`` — wraps GX library when installed.

Usage::

    adapter = get_data_validation_adapter()
    result = adapter.validate_dataset(
        records=[{"close": 10.5, "volume": 1000}],
        expectations={"required_fields": ["close", "volume"]},
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


# ── Result dataclass ──────────────────────────────────────────────────────────


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _resolve_min_quality_threshold(expectations: dict[str, Any]) -> float:
    raw_value = expectations.get("minimum_quality_threshold")
    if raw_value is None:
        raw_value = expectations.get("min_quality_threshold", 0.95)
    return float(raw_value)

class ValidationResult:
    """Result of a data validation run."""

    def __init__(
        self,
        passed: bool,
        stats: dict[str, Any],
        *,
        validation_id: str = "",
        method: str = "builtin",
        backend: str = "builtin",
        expectations_evaluated: int = 0,
        expectations_passed: int = 0,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.passed = passed
        self.stats = stats
        self.validation_id = validation_id or f"val-{uuid4().hex[:12]}"
        self.method = method
        self.backend = backend
        self.expectations_evaluated = expectations_evaluated
        self.expectations_passed = expectations_passed
        self.details = details or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "passed": self.passed,
            "method": self.method,
            "backend": self.backend,
            "expectations_evaluated": self.expectations_evaluated,
            "expectations_passed": self.expectations_passed,
            "stats": self.stats,
            "details": self.details,
        }


# ── Abstract interface ────────────────────────────────────────────────────────

class DataValidationAdapter(ABC):
    """Interface for data validation adapters."""

    @abstractmethod
    def validate_dataset(
        self,
        records: list[dict[str, Any]],
        expectations: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """Validate a dataset against expectations."""
        ...

    @abstractmethod
    def create_checkpoint(
        self,
        checkpoint_name: str,
        validation_results: list[ValidationResult],
    ) -> dict[str, Any]:
        """Create a checkpoint from multiple validation results."""
        ...

    @abstractmethod
    def backend_name(self) -> str:
        ...


# ── Builtin implementation ────────────────────────────────────────────────────

class BuiltinValidationAdapter(DataValidationAdapter):
    """Pure-Python dataset validation using conventions from data_quality.py.

    Supports expectations:
    - required_fields: list of field names that must be present
    - min_record_count: minimum number of records
    - max_null_ratio: maximum allowed null ratio per field
    - min_quality_threshold: minimum quality score
    """

    def validate_dataset(
        self,
        records: list[dict[str, Any]],
        expectations: dict[str, Any] | None = None,
    ) -> ValidationResult:
        exp = dict(expectations or {})
        details: list[dict[str, Any]] = []
        total_checks = 0
        passed_checks = 0

        # Check 1: min_record_count
        min_count = int(exp.get("min_record_count", 0))
        if min_count > 0:
            total_checks += 1
            ok = len(records) >= min_count
            if ok:
                passed_checks += 1
            details.append({
                "expectation": "min_record_count",
                "passed": ok,
                "expected": min_count,
                "actual": len(records),
            })

        # Check 2: required_fields
        required = list(exp.get("required_fields", []))
        if required:
            total_checks += 1
            invalid_records: list[dict[str, Any]] = []
            for index, row in enumerate(records):
                missing = [
                    field
                    for field in required
                    if field not in row or _is_missing_value(row.get(field))
                ]
                if missing:
                    invalid_records.append(
                        {
                            "index": index,
                            "missing": missing,
                        }
                    )
            ok = len(invalid_records) == 0
            if ok:
                passed_checks += 1
            details.append({
                "expectation": "required_fields",
                "passed": ok,
                "expected": required,
                "invalid_records": invalid_records,
            })

        # Check 3: max_null_ratio (per field)
        max_null = float(exp.get("max_null_ratio", 1.0))
        if records and max_null < 1.0:
            all_fields = set()
            for r in records:
                all_fields.update(r.keys())
            for fld in sorted(all_fields):
                total_checks += 1
                null_count = sum(1 for r in records if r.get(fld) is None)
                null_ratio = null_count / max(len(records), 1)
                ok = null_ratio <= max_null
                if ok:
                    passed_checks += 1
                details.append({
                    "expectation": f"max_null_ratio:{fld}",
                    "passed": ok,
                    "threshold": max_null,
                    "actual_ratio": round(null_ratio, 4),
                    "null_count": null_count,
                    "total_count": len(records),
                })

        # Overall stats
        if total_checks == 0:
            total_checks = 1
            passed_checks = 1
            details.append({
                "expectation": "no_expectations_defined",
                "passed": True,
                "note": "No expectations provided; trivially passed.",
            })

        quality_score = round(passed_checks / max(total_checks, 1), 4)
        min_threshold = _resolve_min_quality_threshold(exp)
        overall_passed = quality_score >= min_threshold

        return ValidationResult(
            passed=overall_passed,
            stats={
                "record_count": len(records),
                "quality_score": quality_score,
                "min_quality_threshold": min_threshold,
                "minimum_quality_threshold": min_threshold,
            },
            method="builtin_expectations",
            backend="builtin",
            expectations_evaluated=total_checks,
            expectations_passed=passed_checks,
            details=details,
        )

    def create_checkpoint(
        self,
        checkpoint_name: str,
        validation_results: list[ValidationResult],
    ) -> dict[str, Any]:
        all_passed = all(r.passed for r in validation_results)
        return {
            "checkpoint_name": checkpoint_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "backend": "builtin",
            "all_passed": all_passed,
            "validation_count": len(validation_results),
            "passed_count": sum(1 for r in validation_results if r.passed),
            "failed_count": sum(1 for r in validation_results if not r.passed),
            "validations": [r.to_dict() for r in validation_results],
        }

    def backend_name(self) -> str:
        return "builtin"


# ── Great Expectations adapter (optional) ─────────────────────────────────────

class GreatExpectationsAdapter(DataValidationAdapter):
    """Wraps Great Expectations library when installed.

    Falls back to BuiltinValidationAdapter if GX is not available.
    """

    def __init__(self) -> None:
        self._available = False
        self._fallback = BuiltinValidationAdapter()
        try:
            import great_expectations  # noqa: F401
            self._available = True
        except ImportError:
            pass

    def validate_dataset(
        self,
        records: list[dict[str, Any]],
        expectations: dict[str, Any] | None = None,
    ) -> ValidationResult:
        if not self._available:
            return self._fallback.validate_dataset(records, expectations)

        # GX integration placeholder:
        # 1. Create an ephemeral data context
        # 2. Build a BatchRequest from records
        # 3. Apply expectations
        # 4. Run validation
        # For now, delegate to builtin
        result = self._fallback.validate_dataset(records, expectations)
        result.backend = "great_expectations"
        return result

    def create_checkpoint(
        self,
        checkpoint_name: str,
        validation_results: list[ValidationResult],
    ) -> dict[str, Any]:
        if not self._available:
            return self._fallback.create_checkpoint(checkpoint_name, validation_results)

        cp = self._fallback.create_checkpoint(checkpoint_name, validation_results)
        cp["backend"] = "great_expectations"
        return cp

    def backend_name(self) -> str:
        return "great_expectations" if self._available else "builtin_fallback"


# ── Factory ───────────────────────────────────────────────────────────────────

def get_data_validation_adapter(prefer_gx: bool = True) -> DataValidationAdapter:
    """Get the best available data validation adapter.

    Parameters
    ----------
    prefer_gx:
        If True, try Great Expectations first, fallback to builtin.
    """
    if prefer_gx:
        adapter = GreatExpectationsAdapter()
        if adapter._available:
            return adapter
    return BuiltinValidationAdapter()
