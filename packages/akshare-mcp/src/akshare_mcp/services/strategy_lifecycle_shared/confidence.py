"""Confidence and execution-audit gates.

Execution hard-gate ownership lives in strategy_factory.contracts.hard_gate.
This module re-exports evaluate_execution_audit_gate for host call sites.
"""

from __future__ import annotations

from typing import Any, Optional

from strategy_factory.contracts.hard_gate import (
    EXECUTION_CONVERSION_EFFICIENCY_MIN,
    HARD_GATE_STATUSES,
    PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE,
    PRODUCTION_TRADE_FLOOR_DEFAULT,
    TRADE_EXPECTANCY_MIN_EXCLUSIVE,
    evaluate_execution_audit_gate,
)

from .common import _contract_version_stable, _safe_float, _safe_int, _string

# Re-export hard-gate symbols so existing imports keep working.
__all__ = [
    "EVALUATE_EXECUTION_AUDIT_GATE_OWNER",
    "EXECUTION_CONVERSION_EFFICIENCY_MIN",
    "EXECUTION_FILLED_ORDER_STRONG",
    "EXECUTION_FILLED_ORDER_WEAK",
    "EXECUTION_NAV_CONVERSION_STRONG",
    "EXECUTION_NAV_CONVERSION_WEAK",
    "EXECUTION_NAV_RETURN_STRONG",
    "EXECUTION_SIGNAL_TO_FILL_STRONG",
    "EXECUTION_SIGNAL_TO_FILL_WEAK",
    "EXPECTED_FORWARD_DAYS",
    "HARD_GATE_STATUSES",
    "PNL_CONVERSION_EFFICIENCY_MIN_EXCLUSIVE",
    "PRODUCTION_TRADE_FLOOR_DEFAULT",
    "SIGNAL_QUALITY_OVERLAP_FACTORS",
    "SIGNAL_QUALITY_PRIMARY_DEFAULT",
    "TRADE_EXPECTANCY_MIN_EXCLUSIVE",
    "evaluate_confidence_contract",
    "evaluate_execution_audit_gate",
]

EVALUATE_EXECUTION_AUDIT_GATE_OWNER = "strategy_factory.contracts.hard_gate"

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
