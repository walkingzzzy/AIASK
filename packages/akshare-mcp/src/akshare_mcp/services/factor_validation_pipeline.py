"""候选因子验证流水线：编译、横截面、OOS、稳健性、相似度、成本容量。"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..data_source import data_source
from .cost_model import build_cost_model
from .factor_analysis import FactorAnalyzer
from .factor_candidate_compiler import compile_factor_candidate, evaluate_compiled_factor
from .validation import (
    FactorValidationPipeline,
    deflated_sharpe_ratio,
    hansen_spa_test,
    probability_of_backtest_overfitting,
    white_reality_check,
)

_SIMILARITY_BASIS_DEFINITIONS = [
    {"name": "basis_momentum_20d", "family": "momentum", "inputs": ["close"], "expression_dsl": "momentum_20d"},
    {"name": "basis_momentum_60d", "family": "momentum", "inputs": ["close"], "expression_dsl": "momentum_60d"},
    {"name": "basis_reversal_5d", "family": "reversal", "inputs": ["close"], "expression_dsl": "-return_5d"},
    {"name": "basis_volatility_20d", "family": "volatility", "inputs": ["close"], "expression_dsl": "volatility_20d"},
    {"name": "basis_volume_ratio", "family": "liquidity", "inputs": ["volume"], "expression_dsl": "volume_ratio_5_20"},
]

_SIMILARITY_BASIS_CACHE: dict[str, dict[str, Any]] = {}

from ._factor_validation_pipeline_support import (
    _SIMILARITY_BASIS_DEFINITIONS,
    _SIMILARITY_BASIS_CACHE,
    _safe_float,
    _round_float,
    _clip01,
    _sort_frame,
    _load_validation_frame,
    _dedupe,
    _build_series,
    _build_panel,
    _cross_section_summary,
    _extract_latest_snapshot,
    _build_oos_validation_report,
    _build_horizon_return_panel,
    _date_index_health,
    _detect_suspicious_expression_tokens,
    _build_lookahead_audit,
    _build_long_short_return_series,
    _build_multiple_testing_report,
    _aggregate_rank_ic,
    _build_robustness_report,
    _basis_candidate,
    _get_similarity_basis,
    _safe_corr,
    _build_similarity_report,
    _build_turnover_report,
    _build_cost_capacity_report,
)

def _build_validation_rating(
    cross_section_summary: dict[str, Any],
    oos_report: dict[str, Any],
    robustness_report: dict[str, Any],
    similarity_report: dict[str, Any],
    cost_capacity_report: dict[str, Any],
    lookahead_audit: dict[str, Any],
    multiple_testing_report: dict[str, Any],
) -> dict[str, Any]:
    cross_score = min(20.0, abs(float(cross_section_summary.get("rank_ic_mean", 0.0))) * 100.0)

    oos_rating = (oos_report.get("rating") or {}) if oos_report.get("available") else {}
    oos_score = min(20.0, float(oos_rating.get("total_score", 0.0)) / 5.0)

    robustness_score = float(robustness_report.get("robustness_score", 0.0)) * 15.0 if robustness_report.get("available") else 0.0

    top_similarity = ((similarity_report.get("top_similar_basis") or [{}])[0] if similarity_report.get("available") else {})
    redundancy_penalty = min(8.0, max(0.0, abs(float(top_similarity.get("correlation", 0.0))) - 0.90) * 80.0)
    lookahead_risk = str(lookahead_audit.get("risk_level") or "low") if lookahead_audit.get("available") else "medium"
    lookahead_penalty = 20.0 if lookahead_risk == "high" else (8.0 if lookahead_risk == "medium" else 0.0)
    multiple_testing_risk = (
        str(multiple_testing_report.get("risk_level") or "medium")
        if multiple_testing_report.get("available")
        else "medium"
    )
    multiple_testing_penalty = 18.0 if multiple_testing_risk == "high" else (8.0 if multiple_testing_risk == "medium" else 0.0)

    cost_rate = float(cost_capacity_report.get("estimated_cost_rate", 0.0)) if cost_capacity_report.get("available") else 0.0
    execution_score = float(cost_capacity_report.get("execution_score", 0.0)) * 10.0 if cost_capacity_report.get("available") else 0.0

    walk_forward = dict(oos_report.get("walk_forward") or {}) if oos_report.get("available") else {}
    purged_kfold = dict(oos_report.get("purged_kfold") or {}) if oos_report.get("available") else {}
    avg_stability = (
        float(
            np.mean(
                [
                    _clip01(walk_forward.get("stability_ratio")),
                    _clip01(purged_kfold.get("stability_ratio")),
                ]
            )
        )
        if walk_forward or purged_kfold
        else 0.0
    )
    avg_degradation = (
        float(
            np.mean(
                [
                    max(0.0, _safe_float(walk_forward.get("degradation"), 0.0)),
                    max(0.0, _safe_float(purged_kfold.get("degradation"), 0.0)),
                ]
            )
        )
        if walk_forward or purged_kfold
        else 0.0
    )
    stability_score = avg_stability * 14.0
    degradation_score = max(0.0, 1.0 - (avg_degradation / 0.12)) * 8.0

    dsr_payload = dict(multiple_testing_report.get("deflated_sharpe") or {}) if multiple_testing_report.get("available") else {}
    pbo_payload = dict(multiple_testing_report.get("pbo") or {}) if multiple_testing_report.get("available") else {}
    white_rc_payload = (
        dict(multiple_testing_report.get("white_reality_check") or {})
        if multiple_testing_report.get("available")
        else {}
    )
    hansen_spa_payload = (
        dict(multiple_testing_report.get("hansen_spa") or {})
        if multiple_testing_report.get("available")
        else {}
    )
    dsr_value = _safe_float(dsr_payload.get("dsr"), np.nan)
    pbo_value = _safe_float(pbo_payload.get("pbo"), np.nan)
    white_rc_p = _safe_float(white_rc_payload.get("p_value"), np.nan)
    hansen_spa_p = _safe_float(hansen_spa_payload.get("p_value"), np.nan)

    dsr_score = _clip01(dsr_value / 0.20) * 6.0 if np.isfinite(dsr_value) else 0.0
    pbo_score = _clip01((0.50 - pbo_value) / 0.50) * 6.0 if np.isfinite(pbo_value) else 0.0
    reality_checks = []
    if np.isfinite(white_rc_p):
        reality_checks.append(_clip01((0.20 - white_rc_p) / 0.20))
    if np.isfinite(hansen_spa_p):
        reality_checks.append(_clip01((0.20 - hansen_spa_p) / 0.20))
    reality_check_score = float(np.mean(reality_checks)) * 6.0 if reality_checks else 0.0
    governance_score = stability_score + degradation_score + dsr_score + pbo_score + reality_check_score

    admission_block_reasons: list[str] = []
    if lookahead_audit and not bool(lookahead_audit.get("available")):
        admission_block_reasons.append("lookahead_audit_unavailable")
    if multiple_testing_report and not bool(multiple_testing_report.get("available")):
        admission_block_reasons.append("multiple_testing_unavailable")
    if lookahead_risk == "high":
        admission_block_reasons.append("lookahead_risk_high")
    if multiple_testing_risk == "high":
        admission_block_reasons.append("multiple_testing_risk_high")
    admission_blocked = bool(admission_block_reasons)

    total_score = max(
        0.0,
        min(
            100.0,
            cross_score
            + oos_score
            + robustness_score
            + governance_score
            + execution_score
            - redundancy_penalty
            - lookahead_penalty
            - multiple_testing_penalty,
        ),
    )

    if total_score >= 75:
        grade = "A"
        recommendation = "promote"
    elif total_score >= 60:
        grade = "B"
        recommendation = "review"
    elif total_score >= 45:
        grade = "C"
        recommendation = "watch"
    else:
        grade = "D"
        recommendation = "reject"

    governance_grade = grade
    governance_recommendation = recommendation
    registry_stage = "validated"
    if not admission_blocked and recommendation in {"promote", "review"}:
        registry_stage = "governed"
    if admission_blocked:
        if governance_recommendation in {"promote", "review"}:
            governance_recommendation = "watch"
        if governance_grade in {"A", "B"}:
            governance_grade = "C"

    return {
        "grade": grade,
        "recommendation": recommendation,
        "total_score": _round_float(total_score, 4),
        "component_scores": {
            "cross_section": _round_float(cross_score, 4),
            "oos": _round_float(oos_score, 4),
            "robustness": _round_float(robustness_score, 4),
            "governance": _round_float(governance_score, 4),
            "execution": _round_float(execution_score, 4),
        },
        "penalties": {
            "similarity_redundancy": _round_float(redundancy_penalty, 4),
            "lookahead_risk": _round_float(lookahead_penalty, 4),
            "multiple_testing_risk": _round_float(multiple_testing_penalty, 4),
            "estimated_cost_rate": _round_float(cost_rate, 6),
        },
        "governance": {
            "research_grade": grade,
            "research_recommendation": recommendation,
            "governance_grade": governance_grade,
            "governance_recommendation": governance_recommendation,
            "registry_stage": registry_stage,
            "admission_blocked": admission_blocked,
            "admission_block_reasons": admission_block_reasons,
            "required_audits_complete": (
                bool(lookahead_audit.get("available")) if lookahead_audit else False
            ) and (
                bool(multiple_testing_report.get("available")) if multiple_testing_report else False
            ),
            "evidence_status": {
                "lookahead_available": bool(lookahead_audit.get("available")) if lookahead_audit else False,
                "multiple_testing_available": bool(multiple_testing_report.get("available")) if multiple_testing_report else False,
                "lookahead_risk_level": lookahead_risk,
                "multiple_testing_risk_level": multiple_testing_risk,
            },
            "subscores": {
                "stability": _round_float(stability_score, 4),
                "degradation_resilience": _round_float(degradation_score, 4),
                "deflated_sharpe": _round_float(dsr_score, 4),
                "pbo": _round_float(pbo_score, 4),
                "reality_checks": _round_float(reality_check_score, 4),
            },
            "raw_metrics": {
                "avg_stability_ratio": _round_float(avg_stability, 6),
                "avg_degradation": _round_float(avg_degradation, 6),
                "deflated_sharpe": _round_float(dsr_value, 6) if np.isfinite(dsr_value) else None,
                "pbo": _round_float(pbo_value, 6) if np.isfinite(pbo_value) else None,
                "white_reality_check_p_value": _round_float(white_rc_p, 6) if np.isfinite(white_rc_p) else None,
                "hansen_spa_p_value": _round_float(hansen_spa_p, 6) if np.isfinite(hansen_spa_p) else None,
            },
        },
    }

async def validate_factor_candidate_pipeline(
    db,
    candidate: dict[str, Any],
    *,
    codes: list[str],
    lookback_bars: int = 220,
    horizon_days: int = 10,
    max_dates: int = 60,
) -> dict[str, Any]:
    """对候选因子执行编译、验证并输出 P1 级治理报告。"""

    compiled = compile_factor_candidate(candidate)
    source_chain = ["services.factor_candidate_compiler"]
    validation_warnings = list(compiled.get("warnings") or [])
    skipped_codes: list[dict[str, Any]] = []

    if not compiled.get("valid"):
        return {
            "success": False,
            "stage": "compile",
            "compiled": compiled,
            "warnings": validation_warnings,
            "source_chain": source_chain,
            "error": "candidate failed compiler validation",
        }

    cross_section_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    per_code_stats = []
    frame_map: dict[str, pd.DataFrame] = {}
    factor_series_map: dict[str, pd.Series] = {}
    close_series_map: dict[str, pd.Series] = {}
    amount_series_map: dict[str, pd.Series] = {}

    for code in [str(item).strip() for item in list(codes or []) if str(item).strip()]:
        frame, one_source_chain, reason = await _load_validation_frame(db, code, lookback_bars)
        source_chain.extend(one_source_chain)
        if reason:
            validation_warnings.append(f"{code}: {reason}")
        if frame.empty or len(frame) < max(60, int(horizon_days) + 40):
            skipped_codes.append({"code": code, "reason": "insufficient_kline"})
            continue

        try:
            factor_series = evaluate_compiled_factor(compiled, frame)
        except Exception as exc:
            skipped_codes.append({"code": code, "reason": f"evaluation_failed: {exc}"})
            continue

        close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
        future_returns = (close.shift(-int(horizon_days)) - close) / close.replace(0.0, np.nan)
        date_index = frame["date"].astype(str)

        frame_map[code] = frame
        factor_series_map[code] = pd.Series(factor_series.values, index=date_index, dtype=float)
        close_series_map[code] = pd.Series(close.values, index=date_index, dtype=float)
        amount_series_map[code] = pd.Series(pd.to_numeric(frame["amount"], errors="coerce").astype(float).values, index=date_index, dtype=float)

        valid_rows = 0
        tail_start = max(20, len(frame) - max(int(max_dates), 20) - int(horizon_days))
        tail_end = max(0, len(frame) - int(horizon_days))
        for idx in range(tail_start, tail_end):
            factor_value = _safe_float(factor_series.iloc[idx], np.nan)
            future_return = _safe_float(future_returns.iloc[idx], np.nan)
            if not np.isfinite(factor_value) or not np.isfinite(future_return):
                continue
            date_key = str(frame.iloc[idx].get("date") or idx)
            cross_section_rows[date_key].append(
                {
                    "code": code,
                    "factor_value": factor_value,
                    "future_return": future_return,
                }
            )
            valid_rows += 1

        per_code_stats.append(
            {
                "code": code,
                "rows": int(len(frame)),
                "valid_points": int(valid_rows),
                "latest_factor_value": round(float(_safe_float(factor_series.iloc[-1], 0.0)), 6) if len(factor_series) else 0.0,
            }
        )

    cross_section = _cross_section_summary(cross_section_rows)
    latest_snapshot = _extract_latest_snapshot(cross_section_rows, cross_section)

    factor_df = _build_panel(factor_series_map)
    close_df = _build_panel(close_series_map)
    amount_df = _build_panel(amount_series_map)
    return_df = _build_horizon_return_panel(close_df, horizon_days) if not close_df.empty else pd.DataFrame()
    lookahead_audit = _build_lookahead_audit(
        compiled,
        frame_map,
        factor_df,
        return_df,
        horizon_days=horizon_days,
    )
    if lookahead_audit.get("available"):
        source_chain.append("services.factor_validation_pipeline.lookahead_audit")

    oos_report = _build_oos_validation_report(
        factor_df,
        return_df,
        factor_name=str((compiled.get("candidate") or {}).get("name") or "candidate_factor"),
    )
    if oos_report.get("available"):
        source_chain.append("services.validation.FactorValidationPipeline")

    robustness_report = _build_robustness_report(
        factor_df,
        close_df,
        base_horizon=horizon_days,
    )

    similarity_report = _build_similarity_report(
        compiled,
        frame_map,
        factor_df,
    )

    turnover_report = _build_turnover_report(factor_df)
    cost_capacity_report = _build_cost_capacity_report(
        factor_df,
        amount_df,
        turnover_report=turnover_report,
    )
    if cost_capacity_report.get("available"):
        source_chain.append("services.cost_model")

    multiple_testing_report = _build_multiple_testing_report(
        compiled,
        frame_map,
        factor_df,
        return_df,
    )
    if multiple_testing_report.get("available"):
        source_chain.append("services.factor_validation_pipeline.multiple_testing")

    rating = _build_validation_rating(
        cross_section.get("summary") or {},
        oos_report,
        robustness_report,
        similarity_report,
        cost_capacity_report,
        lookahead_audit,
        multiple_testing_report,
    )

    sample_dates = int((cross_section.get("summary") or {}).get("sample_dates", 0))
    if sample_dates < 5:
        validation_warnings.append("insufficient_cross_section_dates_for_stable_validation")
    if not oos_report.get("available"):
        validation_warnings.append(f"oos_validation_unavailable:{oos_report.get('reason', 'unknown')}")
    if not robustness_report.get("available"):
        validation_warnings.append(f"robustness_unavailable:{robustness_report.get('reason', 'unknown')}")
    if not lookahead_audit.get("available"):
        validation_warnings.append(f"lookahead_audit_unavailable:{lookahead_audit.get('reason', 'unknown')}")
    elif str(lookahead_audit.get("risk_level") or "low") == "high":
        validation_warnings.append("lookahead_audit_failed")
    elif str(lookahead_audit.get("risk_level") or "low") == "medium":
        validation_warnings.append("lookahead_risk_detected")
    for warning in list(lookahead_audit.get("warnings") or []):
        validation_warnings.append(f"lookahead:{warning}")
    if not multiple_testing_report.get("available"):
        validation_warnings.append(f"multiple_testing_unavailable:{multiple_testing_report.get('reason', 'unknown')}")
    elif str(multiple_testing_report.get("risk_level") or "low") == "high":
        validation_warnings.append("multiple_testing_failed")
    elif str(multiple_testing_report.get("risk_level") or "low") == "medium":
        validation_warnings.append("multiple_testing_risk_detected")
    for warning in list(multiple_testing_report.get("warnings") or []):
        validation_warnings.append(f"multiple_testing:{warning}")
    if similarity_report.get("redundancy_flag"):
        validation_warnings.append("high_similarity_with_basis_factor")
    if cost_capacity_report.get("available") and float(cost_capacity_report.get("estimated_cost_rate", 0.0)) > 0.005:
        validation_warnings.append("estimated_cost_rate_above_50bps")

    validation_report = {
        "compile": {
            key: value
            for key, value in compiled.items()
            if key != "compiled_code"
        },
        "cross_section": cross_section,
        "lookahead_audit": lookahead_audit,
        "multiple_testing": multiple_testing_report,
        "oos": oos_report,
        "robustness": robustness_report,
        "similarity": similarity_report,
        "turnover": turnover_report,
        "cost_capacity": cost_capacity_report,
        "rating": rating,
    }

    return {
        "success": True,
        "stage": "validated",
        "compiled": validation_report["compile"],
        "metrics": cross_section.get("summary") or {},
        "cross_section_dates": cross_section.get("dates") or [],
        "latest_snapshot": latest_snapshot,
        "coverage": {
            "input_codes": len(codes),
            "processed_codes": len(per_code_stats),
            "skipped_codes": skipped_codes,
            "per_code_stats": per_code_stats,
        },
        "lookahead_audit": lookahead_audit,
        "multiple_testing": multiple_testing_report,
        "oos_validation": oos_report,
        "robustness": robustness_report,
        "similarity": similarity_report,
        "turnover": turnover_report,
        "cost_capacity": cost_capacity_report,
        "rating": rating,
        "validation_report": validation_report,
        "factor_validation_report": validation_report,
        "warnings": _dedupe(validation_warnings)[:40],
        "source_chain": _dedupe(source_chain),
    }
