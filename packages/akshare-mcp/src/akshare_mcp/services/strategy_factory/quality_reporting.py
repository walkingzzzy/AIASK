"""Shared quality-gate normalization and reporting helpers.

These helpers live in the strategy_factory service layer so both the
factory pipeline and strategy_manager lifecycle can share the same gate
report contract without creating reverse dependencies on manager helpers.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from .constants import PROVISIONAL_PASS_THRESHOLDS, QUALITY_GATE_THRESHOLDS, RISK_REPORT_THRESHOLDS

logger = logging.getLogger(__name__)


def quality_gate_reason_code(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "unknown"
    lowered = text.lower()
    overrides = {
        "insufficient kline data": "insufficient_kline_data",
        "validation_grade_d": "validation_grade_d",
    }
    for needle, code in overrides.items():
        if needle in lowered:
            return code
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return normalized or "unknown"


def normalize_quality_gate_result(result: Optional[dict]) -> dict:
    raw = dict(result or {})
    reasons: list[str] = []
    for item in raw.get("reasons") or []:
        text = str(item).strip()
        if text and text not in reasons:
            reasons.append(text)
    reason = str(raw.get("reason") or "").strip()
    if reason and reason not in reasons:
        reasons.append(reason)
    warnings: list[str] = []
    for item in raw.get("warnings") or []:
        text = str(item).strip()
        if text and text not in warnings:
            warnings.append(text)
    return {
        **raw,
        "passed": bool(raw.get("passed")),
        "reasons": reasons,
        "reason_codes": [quality_gate_reason_code(item) for item in reasons],
        "warnings": warnings,
        "warning_codes": [quality_gate_reason_code(item) for item in warnings],
    }


def is_factory_ai_prototype_strategy(strategy: Optional[dict]) -> bool:
    payload = dict(strategy or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in list(payload.get("tags") or [])}
    if "factory" not in tags and "auto_generated" not in tags:
        return False
    if "external_llm" in tags or "ai_generated" in tags:
        return True
    return strategy_type == "dsl_rule"


def has_only_statistical_gate_failures(gate_result: Optional[dict]) -> bool:
    gate = normalize_quality_gate_result(gate_result)
    codes = list(gate.get("reason_codes") or [])
    if not codes:
        return False
    allowed_prefixes = (
        "walk_forward_ic_ir",
        "purged_k_fold_ic",
        "bootstrap_ci_lower",
        "parameter_sensitivity",
        "multi_period_ic",
    )
    return all(any(str(code).startswith(prefix) for prefix in allowed_prefixes) for code in codes)


def safe_metric_value(payload: Optional[dict], *keys: str) -> float:
    data = dict(payload or {})
    for key in keys:
        if key in data and data.get(key) is not None:
            try:
                return float(data.get(key) or 0.0)
            except Exception:
                return 0.0
    return 0.0


def _count_statistical_checks_passed(gate: dict) -> tuple[int, list[str], list[str]]:
    check_map = {
        "walk_forward_ic_ir": ("wf_ic_ir", QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"], ">="),
        "purged_kfold_ic": ("pkf_ic", QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"], ">="),
        "bootstrap_ci_lower": ("bootstrap_ci_lower", QUALITY_GATE_THRESHOLDS["bootstrap_ci_lower_min"], ">="),
        "param_sensitivity": ("param_sensitivity", QUALITY_GATE_THRESHOLDS["param_sensitivity_max"], "<="),
    }
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    for check_name, (key, threshold, op) in check_map.items():
        value = gate.get(key)
        if value is None:
            failed_checks.append(check_name)
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            failed_checks.append(check_name)
            continue
        if op == ">=" and val >= threshold:
            passed_checks.append(check_name)
        elif op == "<=" and val <= threshold:
            passed_checks.append(check_name)
        else:
            failed_checks.append(check_name)

    period_robustness = gate.get("period_robustness") or {}
    first_ic = period_robustness.get("first_half_ic")
    second_ic = period_robustness.get("second_half_ic")
    if first_ic is not None and second_ic is not None:
        try:
            f_ic, s_ic = float(first_ic), float(second_ic)
            direction_consistent = not (f_ic > 0.01 and s_ic < -0.01) and not (f_ic < -0.01 and s_ic > 0.01)
            both_non_negative = f_ic >= -0.02 and s_ic >= -0.02
            if both_non_negative and direction_consistent:
                passed_checks.append("multi_period_robustness")
            else:
                failed_checks.append("multi_period_robustness")
        except (TypeError, ValueError):
            failed_checks.append("multi_period_robustness")

    return len(passed_checks), passed_checks, failed_checks


PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED = 2


def maybe_grant_provisional_incubation(
    strategy: Optional[dict],
    quality_gate: Optional[dict],
    *,
    validation_report: Optional[dict] = None,
    risk_report: Optional[dict] = None,
    backtest_metrics: Optional[dict] = None,
) -> dict:
    gate = normalize_quality_gate_result(quality_gate)
    if gate.get("passed"):
        return gate
    if not is_factory_ai_prototype_strategy(strategy):
        return gate
    if not has_only_statistical_gate_failures(gate):
        return gate
    if not risk_report:
        return gate

    checks_passed, passed_names, failed_names = _count_statistical_checks_passed(gate)
    if checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED:
        logger.info(
            "Provisional incubation denied: only %d/%d statistical checks passed (%s failed)",
            checks_passed,
            checks_passed + len(failed_names),
            ", ".join(failed_names),
        )
        return gate

    metrics = dict(backtest_metrics or {})
    sharpe_ratio = safe_metric_value(metrics, "sharpe_ratio")
    max_drawdown = abs(safe_metric_value(metrics, "max_drawdown"))
    trades_count = safe_metric_value(metrics, "trade_count", "trades_count")
    if (
        sharpe_ratio < PROVISIONAL_PASS_THRESHOLDS["sharpe_min"]
        or max_drawdown > PROVISIONAL_PASS_THRESHOLDS["mdd_max"]
        or trades_count < PROVISIONAL_PASS_THRESHOLDS["trades_min"]
    ):
        return gate

    risk = dict(risk_report or {})
    var_percent = safe_metric_value(risk, "var_percent")
    cvar_percent = safe_metric_value(risk, "cvar_percent")
    stress_loss_percent = safe_metric_value(risk, "stress_loss_percent")
    if (
        var_percent > RISK_REPORT_THRESHOLDS["var_percent_max"]
        or cvar_percent > RISK_REPORT_THRESHOLDS["cvar_percent_max"]
        or stress_loss_percent <= RISK_REPORT_THRESHOLDS["stress_loss_percent_min"]
    ):
        return gate

    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    validation_grade = str(rating.get("grade") or "").strip().upper()

    warnings = list(gate.get("reasons") or [])
    if validation_grade == "D" and "validation_grade_d" not in warnings:
        warnings.append("validation_grade_d")
    for failed_name in failed_names:
        tag = f"provisional_skip:{failed_name}"
        if tag not in warnings:
            warnings.append(tag)
    warnings = list(dict.fromkeys(warnings))
    return normalize_quality_gate_result({
        **gate,
        "passed": True,
        "passed_strict": False,
        "provisional_pass": True,
        "review_mode": "incubation_only",
        "reasons": [],
        "reason": "",
        "warnings": warnings,
        "original_reasons": gate.get("reasons") or [],
        "original_reason_codes": gate.get("reason_codes") or [],
        "statistical_checks_passed": checks_passed,
        "statistical_checks_passed_names": passed_names,
        "statistical_checks_failed_names": failed_names,
    })


def build_quality_report(
    strategy_id: str,
    strategy_type: Optional[str],
    quality_gate: Optional[dict],
    validation_report: Optional[dict],
    risk_report: Optional[dict],
    dedup_report: Optional[dict],
    backtest_metrics: Optional[dict],
    snapshot: Optional[dict],
    status_after_review: Optional[str],
    review_source: str,
    report_type: str,
    spawn_reason: Optional[str] = None,
) -> dict:
    normalized_gate = normalize_quality_gate_result(quality_gate)
    validation = dict(validation_report or {})
    rating = validation.get("rating") or {}
    summary = {
        "strategy_id": strategy_id,
        "strategy_type": strategy_type,
        "status_after_review": status_after_review,
        "validation_grade": rating.get("grade"),
        "review_source": review_source,
    }
    if spawn_reason:
        summary["spawn_reason"] = spawn_reason
    return {
        "report_type": report_type,
        "passed": bool(normalized_gate.get("passed")),
        "summary": summary,
        "quality_gate": normalized_gate,
        "validation_report": validation,
        "risk_report": dict(risk_report or {}),
        "dedup_report": dict(dedup_report or {}),
        "backtest_metrics": dict(backtest_metrics or {}),
        "snapshot": dict(snapshot or {}),
    }
