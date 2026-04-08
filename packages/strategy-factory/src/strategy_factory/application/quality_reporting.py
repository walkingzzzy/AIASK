"""Shared quality-gate normalization and reporting helpers.

These helpers live in the strategy_factory service layer so both the
factory pipeline and strategy_manager lifecycle can share the same gate
report contract without creating reverse dependencies on manager helpers.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from ..domain.constants import PROVISIONAL_PASS_THRESHOLDS, QUALITY_GATE_THRESHOLDS, RISK_REPORT_THRESHOLDS

logger = logging.getLogger(__name__)

PROVISIONAL_TECHNICAL_STRATEGY_TYPES = frozenset({
    "momentum",
    "ma_cross",
    "rsi",
    "macro_timing",
    "volatility_breakout",
    "gap_fill",
    "mean_reversion_short",
    "sector_rotation",
    "north_capital_track",
    "margin_divergence",
})

_DEGENERATE_STAT_EPSILON = 1e-9


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


def _normalize_attempt_adjustment(value: Optional[dict]) -> dict:
    raw = dict(value or {})

    def _safe_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    if not raw:
        return {}
    attempt_count = max(1, _safe_int(raw.get("attempt_count"), 1))
    selected_count = max(0, _safe_int(raw.get("selected_count"), 0))
    selection_ratio = raw.get("selection_ratio")
    if selection_ratio is None:
        selection_ratio = selected_count / max(attempt_count, 1)
    penalty = _safe_float(raw.get("penalty"), 0.0)
    applied = raw.get("applied")
    if applied is None:
        applied = penalty > 0.0
    return {
        **raw,
        "attempt_count": attempt_count,
        "selected_count": selected_count,
        "selection_ratio": round(_safe_float(selection_ratio, 0.0), 4),
        "penalty": round(penalty, 4),
        "applied": bool(applied),
    }


def _normalize_committee_review(value: Optional[dict]) -> dict:
    raw = dict(value or {})
    if not raw:
        return {}

    def _unique_strings(values: object) -> list[str]:
        items: list[str] = []
        for item in list(values or []):
            text = str(item or "").strip()
            if text and text not in items:
                items.append(text)
        return items

    normalized: dict[str, object] = {}
    for key in (
        "decision",
        "review_mode",
    ):
        text = str(raw.get(key) or "").strip()
        if text:
            normalized[key] = text
    for key in (
        "final_score",
        "planner_score",
        "risk_score",
        "feasibility_score",
        "execution_score",
        "capacity_score",
        "task_alignment_score",
        "novelty_score",
    ):
        if raw.get(key) is None:
            continue
        try:
            normalized[key] = round(float(raw.get(key) or 0.0), 4)
        except Exception:
            continue
    for key in ("rank",):
        if raw.get(key) is None:
            continue
        try:
            normalized[key] = int(raw.get(key) or 0)
        except Exception:
            continue
    for key in ("is_champion",):
        if raw.get(key) is None:
            continue
        normalized[key] = bool(raw.get(key))
    for key in (
        "alignment_issues",
        "execution_issues",
        "capacity_issues",
        "suggestions",
        "accept_blockers",
    ):
        values = _unique_strings(raw.get(key))
        if values:
            normalized[key] = values
    for key in ("planner_context", "task_alignment_context"):
        mapping = dict(raw.get(key) or {})
        if mapping:
            normalized[key] = mapping
    return normalized


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
        "attempt_adjustment": _normalize_attempt_adjustment(raw.get("attempt_adjustment")),
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


def is_factory_provisional_candidate(strategy: Optional[dict]) -> bool:
    payload = dict(strategy or {})
    tags = {str(tag).strip().lower() for tag in list(payload.get("tags") or [])}
    if "factory" not in tags and "auto_generated" not in tags:
        return False
    if is_provisional_technical_strategy(payload):
        return True
    return is_factory_ai_prototype_strategy(payload)


def is_provisional_technical_strategy(strategy: Optional[dict]) -> bool:
    payload = dict(strategy or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    return strategy_type in PROVISIONAL_TECHNICAL_STRATEGY_TYPES


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


def _is_near_zero(value: object, *, eps: float = _DEGENERATE_STAT_EPSILON) -> bool:
    try:
        return abs(float(value)) <= eps
    except Exception:
        return False


def has_degenerate_validation_statistics(validation_report: Optional[dict]) -> bool:
    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    walk_forward = dict(validation.get("walk_forward") or {})
    purged_kfold = dict(validation.get("purged_kfold") or {})
    bootstrap_ci = dict(validation.get("bootstrap_ci") or {})

    wf_n_folds = int(safe_metric_value(walk_forward, "n_folds"))
    pkf_n_folds = int(safe_metric_value(purged_kfold, "n_folds"))
    total_score = safe_metric_value(rating, "total_score")

    score_values: list[float] = []
    for value in dict(rating.get("scores") or {}).values():
        try:
            score_values.append(float(value or 0.0))
        except Exception:
            continue
    zero_score_map = bool(score_values) and all(_is_near_zero(value) for value in score_values)

    stat_surface = (
        safe_metric_value(walk_forward, "oos_rank_ic_mean", "oos_ic_mean"),
        safe_metric_value(walk_forward, "oos_rank_ic_ir", "oos_ic_ir"),
        safe_metric_value(purged_kfold, "oos_rank_ic_mean", "oos_ic_mean"),
        safe_metric_value(purged_kfold, "oos_rank_ic_ir", "oos_ic_ir"),
        safe_metric_value(bootstrap_ci, "ci_lower"),
        safe_metric_value(bootstrap_ci, "ci_upper"),
        safe_metric_value(bootstrap_ci, "sample_size"),
    )
    zero_stat_surface = all(_is_near_zero(value) for value in stat_surface)
    no_fold_evidence = wf_n_folds <= 0 and pkf_n_folds <= 0

    return no_fold_evidence or (
        total_score <= 0
        and zero_stat_surface
        and (not score_values or zero_score_map)
    )


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
    if not is_factory_provisional_candidate(strategy):
        return gate
    if not has_only_statistical_gate_failures(gate):
        return gate
    if not risk_report:
        return gate

    checks_passed, passed_names, failed_names = _count_statistical_checks_passed(gate)
    technical_validation_fallback = (
        checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED
        and is_provisional_technical_strategy(strategy)
        and has_degenerate_validation_statistics(validation_report)
    )
    if checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED and not technical_validation_fallback:
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
    if technical_validation_fallback:
        for extra_warning in (
            "validation_report_degenerate",
            "provisional_path:technical_validation_fallback",
        ):
            if extra_warning not in warnings:
                warnings.append(extra_warning)
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
    submission_audit: Optional[dict] = None,
) -> dict:
    normalized_gate = normalize_quality_gate_result(quality_gate)
    validation = dict(validation_report or {})
    rating = validation.get("rating") or {}
    dedup = dict(dedup_report or {})
    backtest = dict(backtest_metrics or {})
    audit = dict(submission_audit or {})
    candidate_provenance = dict(audit.get("candidate_provenance") or {})
    strategy_profile = dict(candidate_provenance.get("strategy_profile") or {})
    event_window_metrics = dict(backtest.get("event_window_metrics") or {})
    cost_assumptions = dict(backtest.get("cost_assumptions") or {})
    backtest_assumptions = dict(backtest.get("backtest_assumptions") or {})
    execution_reality = {
        "market_ruleset": cost_assumptions.get("market_ruleset") or backtest_assumptions.get("market_ruleset"),
        "sell_tax_rate": (
            cost_assumptions.get("sell_tax_rate")
            if cost_assumptions.get("sell_tax_rate") is not None
            else backtest_assumptions.get("sell_tax_rate")
        ),
        "min_trade_lot": (
            cost_assumptions.get("min_trade_lot")
            if cost_assumptions.get("min_trade_lot") is not None
            else backtest_assumptions.get("min_trade_lot")
        ),
        "t_plus_one": (
            cost_assumptions.get("t_plus_one")
            if cost_assumptions.get("t_plus_one") is not None
            else backtest_assumptions.get("t_plus_one")
        ),
        "arrival_price_policy": (
            cost_assumptions.get("arrival_price_policy")
            or backtest_assumptions.get("arrival_price_policy")
        ),
        "market_impact_bps": (
            cost_assumptions.get("market_impact_bps")
            if cost_assumptions.get("market_impact_bps") is not None
            else backtest_assumptions.get("market_impact_bps")
        ),
        "implementation_shortfall_proxy": (
            cost_assumptions.get("implementation_shortfall_proxy")
            if cost_assumptions.get("implementation_shortfall_proxy") is not None
            else backtest_assumptions.get("implementation_shortfall_proxy")
        ),
        "max_position_pct": backtest_assumptions.get("max_position_pct"),
        "target_weight_scheme": backtest_assumptions.get("target_weight_scheme"),
        "position_assumption": backtest.get("position_assumption") or backtest_assumptions.get("position_assumption"),
        "tradability_filter": backtest_assumptions.get("tradability_filter"),
    }
    submission_lane = audit.get("submission_lane")
    direct_trade_candidate = bool(audit.get("direct_trade_candidate"))
    live_review_ready = bool(audit.get("live_review_ready"))
    paper_lane_ready = bool(audit.get("paper_lane_ready"))
    paper_account_id = audit.get("paper_account_id") or audit.get("live_review_account_id")
    paper_account_status = audit.get("paper_account_status")
    runtime_control_mode = audit.get("runtime_control_mode")
    runtime_control_status = audit.get("runtime_control_status")
    promotion_review_id = audit.get("promotion_review_id")
    promotion_review_status = audit.get("promotion_review_status")
    promotion_review_recommendation = audit.get("promotion_review_recommendation")
    pool_admission_applied = bool(audit.get("pool_admission_applied"))
    promotion_applied_transition = dict(audit.get("promotion_applied_transition") or {})
    submission_action = dict(audit.get("submission_action") or {})
    submission_action_type = audit.get("submission_action_type")
    submission_action_trigger = audit.get("submission_action_trigger")
    submission_action_gaps = list(audit.get("submission_action_gaps") or [])
    submission_action_fallback_conditions = list(audit.get("submission_action_fallback_conditions") or [])
    submission_action_next_step = audit.get("submission_action_next_step")
    submission_action_completed = bool(audit.get("submission_action_completed"))
    committee_review = _normalize_committee_review(
        audit.get("committee_review") or snapshot.get("committee_review")
    )
    summary = {
        "strategy_id": strategy_id,
        "strategy_type": strategy_type,
        "status_after_review": status_after_review,
        "validation_grade": rating.get("grade"),
        "review_source": review_source,
        "primary_validation_layer": normalized_gate.get("primary_validation_layer"),
        "admission_stage": normalized_gate.get("admission_stage"),
        "incubation_pass_mode": normalized_gate.get("incubation_pass_mode"),
        "research_candidate_ready": bool(normalized_gate.get("research_candidate_ready")),
        "incubation_candidate_ready": bool(normalized_gate.get("incubation_candidate_ready")),
        "live_candidate_ready": bool(normalized_gate.get("live_candidate_ready")),
        "submission_lane": submission_lane,
        "direct_trade_candidate": direct_trade_candidate,
        "live_review_ready": live_review_ready,
        "paper_lane_ready": paper_lane_ready,
        "paper_account_id": paper_account_id,
        "paper_account_status": paper_account_status,
        "runtime_control_mode": runtime_control_mode,
        "runtime_control_status": runtime_control_status,
        "promotion_review_id": promotion_review_id,
        "promotion_review_status": promotion_review_status,
        "promotion_review_recommendation": promotion_review_recommendation,
        "pool_admission_applied": pool_admission_applied,
        "submission_action_type": submission_action_type,
        "submission_action_trigger": submission_action_trigger,
        "submission_action_gaps": submission_action_gaps,
        "submission_action_fallback_conditions": submission_action_fallback_conditions,
        "submission_action_next_step": submission_action_next_step,
        "submission_action_completed": submission_action_completed,
        "refresh_mode": audit.get("refresh_mode") or dedup.get("refresh_mode"),
        "source_candidate_artifact_id": candidate_provenance.get("source_candidate_artifact_id"),
        "candidate_family": candidate_provenance.get("candidate_family"),
        "candidate_family_id": candidate_provenance.get("candidate_family_id"),
        "holding_period_bucket": candidate_provenance.get("holding_period_bucket"),
        "alpha_source": candidate_provenance.get("alpha_source"),
        "risk_level": candidate_provenance.get("risk_level"),
        "regime_fit": candidate_provenance.get("regime_fit"),
        "generator_mode": candidate_provenance.get("generator_mode"),
        "market_ruleset": execution_reality.get("market_ruleset"),
        "target_weight_scheme": execution_reality.get("target_weight_scheme"),
        "position_assumption": execution_reality.get("position_assumption"),
        "committee_decision": committee_review.get("decision"),
        "committee_final_score": committee_review.get("final_score"),
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
        "dedup_report": dedup,
        "backtest_metrics": backtest,
        "constraint_check": dict(backtest.get("constraint_check") or {}),
        "validation_profile": {
            "profile": normalized_gate.get("profile"),
            "validation_focus": normalized_gate.get("validation_focus"),
            "primary_validation_layer": normalized_gate.get("primary_validation_layer"),
        },
        "admission_stage": normalized_gate.get("admission_stage"),
        "incubation_pass_mode": normalized_gate.get("incubation_pass_mode"),
        "research_candidate_ready": bool(normalized_gate.get("research_candidate_ready")),
        "incubation_candidate_ready": bool(normalized_gate.get("incubation_candidate_ready")),
        "live_candidate_ready": bool(normalized_gate.get("live_candidate_ready")),
        "submission_lane": submission_lane,
        "direct_trade_candidate": direct_trade_candidate,
        "live_review_ready": live_review_ready,
        "paper_lane_ready": paper_lane_ready,
        "paper_account_id": paper_account_id,
        "paper_account_status": paper_account_status,
        "runtime_control_mode": runtime_control_mode,
        "runtime_control_status": runtime_control_status,
        "promotion_review_id": promotion_review_id,
        "promotion_review_status": promotion_review_status,
        "promotion_review_recommendation": promotion_review_recommendation,
        "pool_admission_applied": pool_admission_applied,
        "promotion_applied_transition": promotion_applied_transition,
        "submission_action": submission_action,
        "submission_action_type": submission_action_type,
        "submission_action_trigger": submission_action_trigger,
        "submission_action_gaps": submission_action_gaps,
        "submission_action_fallback_conditions": submission_action_fallback_conditions,
        "submission_action_next_step": submission_action_next_step,
        "submission_action_completed": submission_action_completed,
        "admission_block_reasons": list(normalized_gate.get("admission_block_reasons") or []),
        "admission_evaluations": dict(normalized_gate.get("admission_evaluations") or {}),
        "event_window_config": dict(backtest.get("event_window_config") or {}),
        "event_window_metrics": event_window_metrics,
        "position_assumption": backtest.get("position_assumption"),
        "cost_assumptions": cost_assumptions,
        "explicit_cost_breakdown": dict(backtest.get("explicit_cost_breakdown") or {}),
        "implicit_cost_breakdown": dict(backtest.get("implicit_cost_breakdown") or {}),
        "tradability_summary": dict(backtest.get("tradability_summary") or {}),
        "capacity_summary": dict(backtest.get("capacity_summary") or {}),
        "implementation_shortfall_model_source": backtest.get("implementation_shortfall_model_source"),
        "implementation_shortfall_components": dict(backtest.get("implementation_shortfall_components") or {}),
        "backtest_assumptions": backtest_assumptions,
        "execution_reality": execution_reality,
        "attempt_adjustment": dict(normalized_gate.get("attempt_adjustment") or {}),
        "run_correction": {
            "mode": normalized_gate.get("run_correction_mode"),
            "raw_sharpe_proxy": normalized_gate.get("raw_sharpe_proxy"),
            "deflated_sharpe_proxy": normalized_gate.get("deflated_sharpe_proxy"),
            "pbo_proxy": normalized_gate.get("pbo_proxy"),
            "reality_check_pvalue_proxy": normalized_gate.get("reality_check_pvalue_proxy"),
            "spa_pvalue_proxy": normalized_gate.get("spa_pvalue_proxy"),
            "multiple_testing_mode": normalized_gate.get("multiple_testing_mode"),
            "deflated_sharpe_ratio": normalized_gate.get("deflated_sharpe_ratio"),
            "deflated_sharpe_reference_sharpe": normalized_gate.get("deflated_sharpe_reference_sharpe"),
            "deflated_sharpe_effective_trials": normalized_gate.get("deflated_sharpe_effective_trials"),
            "pbo": normalized_gate.get("pbo"),
            "white_reality_check_pvalue": normalized_gate.get("white_reality_check_pvalue"),
            "hansen_spa_pvalue": normalized_gate.get("hansen_spa_pvalue"),
            "multiple_testing": dict(normalized_gate.get("multiple_testing") or {}),
        },
        "multiple_testing_registry": dict(normalized_gate.get("multiple_testing_registry") or {}),
        "committee_review": committee_review,
        "task_signature": audit.get("task_signature"),
        "refresh_mode": audit.get("refresh_mode") or dedup.get("refresh_mode"),
        "task_preference": dict(audit.get("task_preference") or {}),
        "candidate_provenance": candidate_provenance,
        "strategy_profile": strategy_profile,
        "snapshot": dict(snapshot or {}),
    }
