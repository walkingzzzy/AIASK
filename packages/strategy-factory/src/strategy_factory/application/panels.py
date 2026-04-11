"""策略工厂面板、验证与风险报告。"""

from __future__ import annotations

from typing import List

import numpy as np

from ..domain.targets import _resolve_strategy_sample_selection, _resolve_validation_focus_layer
from ..infrastructure.mcp_services import (
    get_normalize_klines,
    get_risk_model_class,
    get_strategy_registry,
    get_validation_runtime,
)


def _generate_strategy_signal_series(klass, params: dict, closes: np.ndarray, volumes: np.ndarray) -> np.ndarray:
    instance = klass()
    instance.set_parameters(params or {})
    try:
        signals = np.asarray(instance.generate_signals(closes, volumes), dtype=np.float64)
    except TypeError:
        signals = np.asarray(instance.generate_signals(closes), dtype=np.float64)
    return signals


def _resolve_validation_focus(params: dict) -> str:
    payload = dict(params or {})
    validation_profile = dict(payload.get("validation_profile") or {})
    research_task = dict(payload.get("research_task") or {})
    return str(
        validation_profile.get("validation_focus")
        or research_task.get("validation_focus")
        or ""
    ).strip().lower()


def _annualized_sharpe_ratio(returns: np.ndarray, periods_per_year: float = 252.0) -> float:
    series = np.asarray(returns, dtype=np.float64)
    if series.size == 0:
        return 0.0
    series = series[np.isfinite(series)]
    if series.size < 8:
        return 0.0
    std = float(np.std(series))
    if std <= 1e-12:
        return 0.0
    return float(np.mean(series) / std * np.sqrt(periods_per_year))


def _grade_for_total_score(total_score: float) -> str:
    total = float(total_score or 0.0)
    if total >= 70.0:
        return "A"
    if total >= 55.0:
        return "B"
    if total >= 40.0:
        return "C"
    return "D"


def _threshold_score(value: float, thresholds: list[tuple[float, float]]) -> float:
    for threshold, score in thresholds:
        if value >= threshold:
            return float(score)
    return 0.0


def _reverse_threshold_score(value: float, thresholds: list[tuple[float, float]]) -> float:
    for threshold, score in thresholds:
        if value <= threshold:
            return float(score)
    return 0.0


def _build_validation_focus_annotation(
    validation_focus: str,
    validation_focus_layer: str,
) -> dict:
    layer = str(validation_focus_layer or "broad_market").strip().lower() or "broad_market"
    focus = str(validation_focus or "").strip().lower() or None
    defaults = {
        "target_only": {
            "interpretation": "单目标或强目标约束 cohort，优先衡量策略在目标样本上的交易稳健性。",
            "threshold_note": "更强调 target-layer 一致性与 family 对齐，不应与宽市场因子候选直接横向比较。",
        },
        "family_peer": {
            "interpretation": "目标样本加 family peer cohort，优先衡量相近 family 样本上的可迁移性。",
            "threshold_note": "允许适度跨样本验证，但仍以 family 对齐为主，不按 broad market 口径解读。",
        },
        "sector_peer": {
            "interpretation": "目标样本加 sector peer proxy cohort，优先衡量近行业/近结构样本上的泛化。",
            "threshold_note": "比 family_peer 更宽，但仍应避免与全市场宽面板因子直接混评。",
        },
        "broad_market": {
            "interpretation": "宽市场代表样本 cohort，优先衡量一般化的样本外稳定性。",
            "threshold_note": "适合宽面板因子或无明确 target 的策略，不应用来否定 target-only 交易候选的局部有效性。",
        },
    }
    annotation = dict(defaults.get(layer) or defaults["broad_market"])
    annotation["validation_focus"] = focus
    annotation["validation_focus_layer"] = layer
    return annotation


def _apply_trade_quality_rating_adjustment(
    report: dict,
    *,
    strategy_type: str,
    params: dict,
    strategy_returns: np.ndarray | None,
    sample_codes: List[str],
    sample_selection: dict | None = None,
) -> dict:
    rating = dict(report.get("rating") or {})
    if not rating:
        return report
    normalized_strategy_type = str(strategy_type or "").strip().lower()
    if normalized_strategy_type not in {"momentum", "quality_factor", "ma_cross"}:
        return report
    validation_focus = _resolve_validation_focus(params)
    sample_meta = dict(sample_selection or {})
    validation_focus_layer = str(
        sample_meta.get("validation_focus_layer")
        or _resolve_validation_focus_layer(validation_focus)
        or "broad_market"
    ).strip().lower()
    sample_selection_mode = str(sample_meta.get("sample_selection_mode") or "").strip().lower()
    if validation_focus_layer not in {"target_only", "family_peer"}:
        return report
    baseline_total = float(rating.get("total_score") or 0.0)
    baseline_grade = str(rating.get("grade") or "").strip().upper() or _grade_for_total_score(baseline_total)
    returns = np.asarray(strategy_returns if strategy_returns is not None else [], dtype=np.float64)
    returns = returns[np.isfinite(returns)]
    if returns.size < 60:
        return report

    realized_sharpe = _annualized_sharpe_ratio(returns)
    positive_ratio = float(np.mean(returns > 0.0)) if returns.size else 0.0
    multiple_testing = dict(report.get("multiple_testing") or {})
    dsr = float(dict(multiple_testing.get("deflated_sharpe") or {}).get("dsr") or 0.0)
    pbo = float(dict(multiple_testing.get("pbo") or {}).get("pbo") or 1.0)
    rc_pvalue = float(dict(multiple_testing.get("white_reality_check") or {}).get("p_value") or 1.0)
    spa_pvalue = float(dict(multiple_testing.get("hansen_spa") or {}).get("p_value") or 1.0)
    holding_horizon = dict(params.get("holding_horizon") or {})
    rebalance_rule = dict(params.get("rebalance_rule") or {})
    market_regime_assumption = dict(params.get("market_regime_assumption") or {})
    family_specialization = dict(
        params.get("family_specialization")
        or params.get("family_specific_hypothesis")
        or {}
    )
    expected_turnover_band = str(
        params.get("expected_turnover_band")
        or holding_horizon.get("expected_turnover_band")
        or rebalance_rule.get("expected_turnover_band")
        or ""
    ).strip().lower()
    rebalance_frequency_days = int(rebalance_rule.get("frequency_days") or 0)
    max_holding_days = int(holding_horizon.get("max_days") or 0)
    aligned_dynamic_panel = sample_selection_mode in {
        "target_plus_dynamic_family_peer",
        "family_peer_dynamic_panel",
    }

    bonus_breakdown: dict[str, float] = {}
    trade_score_breakdown: dict[str, float] = {}
    if normalized_strategy_type == "momentum":
        trade_score_breakdown["realized_sharpe"] = _threshold_score(
            realized_sharpe,
            [(1.5, 24.0), (1.15, 20.0), (0.9, 16.0), (0.65, 12.0)],
        )
        trade_score_breakdown["positive_ratio"] = _threshold_score(
            positive_ratio,
            [(0.56, 8.0), (0.53, 6.0), (0.5, 4.0)],
        )
        trade_score_breakdown["deflated_sharpe"] = _threshold_score(
            dsr,
            [(0.1, 10.0), (0.05, 6.0), (0.0, 2.0)],
        )
        trade_score_breakdown["pbo"] = _reverse_threshold_score(
            pbo,
            [(0.4, 10.0), (0.6, 8.0), (0.8, 5.0), (0.9, 3.0)],
        )
        trade_score_breakdown["multiple_testing_consensus"] = (
            8.0 if rc_pvalue <= 0.2 and spa_pvalue <= 0.2
            else 5.0 if rc_pvalue <= 0.35 and spa_pvalue <= 0.35
            else 2.0 if rc_pvalue <= 0.5 and spa_pvalue <= 0.5
            else 0.0
        )
        trade_score_breakdown["trend_persistence_holding"] = (
            7.0 if max_holding_days >= 36
            else 5.0 if max_holding_days >= 24
            else 2.0 if max_holding_days >= 18
            else 0.0
        )
        trade_score_breakdown["rebalance_pacing"] = (
            5.0 if rebalance_frequency_days >= 14
            else 4.0 if rebalance_frequency_days >= 10
            else 2.0 if rebalance_frequency_days >= 7
            else 0.0
        )
        trade_score_breakdown["turnover_discipline"] = (
            4.0 if expected_turnover_band == "low"
            else 2.0 if expected_turnover_band == "medium"
            else 0.0
        )
        trade_score_breakdown["aligned_dynamic_panel"] = 5.0 if aligned_dynamic_panel else 0.0
        trade_score_breakdown["regime_alignment"] = (
            6.0 if "trend_expansion" in str(market_regime_assumption.get("preferred_regime") or "")
            else 0.0
        )
        trade_score_breakdown["false_breakout_filter"] = 6.0 if family_specialization.get("false_breakout_filter") else 0.0
        trade_score_breakdown["target_cohort_consensus"] = (
            10.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.2
            and rc_pvalue <= 0.35
            and spa_pvalue <= 0.35
            else 7.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.35
            and rc_pvalue <= 0.5
            and spa_pvalue <= 0.5
            else 4.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.5
            and rc_pvalue <= 0.65
            and spa_pvalue <= 0.65
            else 0.0
        )
        trade_score_breakdown["target_cohort_trade_alignment"] = (
            6.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 20
            and rebalance_frequency_days >= 14
            and "trend_expansion" in str(market_regime_assumption.get("preferred_regime") or "")
            and bool(family_specialization.get("false_breakout_filter"))
            else 0.0
        )
        trade_score_breakdown["target_cohort_low_turnover_consensus"] = (
            1.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.25
            and expected_turnover_band == "low"
            and max_holding_days >= 20
            and rebalance_frequency_days >= 14
            else 0.0
        )
        if realized_sharpe >= 1.0:
            bonus_breakdown["realized_sharpe"] = 7.0
        elif realized_sharpe >= 0.7:
            bonus_breakdown["realized_sharpe"] = 4.0
        if positive_ratio >= 0.53:
            bonus_breakdown["positive_ratio"] = 2.0
        elif positive_ratio >= 0.51:
            bonus_breakdown["positive_ratio"] = 1.0
        if dsr >= 0.12:
            bonus_breakdown["deflated_sharpe"] = 4.0
        elif dsr >= 0.06:
            bonus_breakdown["deflated_sharpe"] = 2.0
        if pbo <= 0.75:
            bonus_breakdown["pbo"] = 3.0
        elif pbo <= 0.88:
            bonus_breakdown["pbo"] = 1.5
        if rc_pvalue <= 0.25 and spa_pvalue <= 0.2:
            bonus_breakdown["multiple_testing_consensus"] = 2.0
        if max_holding_days >= 20:
            bonus_breakdown["trend_persistence_holding"] = 1.5
        if rebalance_frequency_days >= 6:
            bonus_breakdown["rebalance_pacing"] = 1.0
        if expected_turnover_band == "low":
            bonus_breakdown["turnover_discipline"] = 1.5
        elif expected_turnover_band == "medium":
            bonus_breakdown["turnover_discipline"] = 0.5
        if aligned_dynamic_panel:
            bonus_breakdown["aligned_dynamic_panel"] = 1.0
        if "trend_expansion" in str(market_regime_assumption.get("preferred_regime") or ""):
            bonus_breakdown["regime_alignment"] = 1.5
        if family_specialization.get("false_breakout_filter"):
            bonus_breakdown["false_breakout_filter"] = 1.5
        if (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.35
            and rc_pvalue <= 0.5
            and spa_pvalue <= 0.5
        ):
            bonus_breakdown["target_cohort_consensus"] = 1.5
        if (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 20
            and rebalance_frequency_days >= 14
            and "trend_expansion" in str(market_regime_assumption.get("preferred_regime") or "")
            and bool(family_specialization.get("false_breakout_filter"))
        ):
            bonus_breakdown["target_cohort_trade_alignment"] = 1.0
    elif normalized_strategy_type == "quality_factor":
        trade_score_breakdown["realized_sharpe"] = _threshold_score(
            realized_sharpe,
            [(1.4, 24.0), (1.1, 20.0), (0.85, 16.0), (0.65, 12.0)],
        )
        trade_score_breakdown["positive_ratio"] = _threshold_score(
            positive_ratio,
            [(0.57, 8.0), (0.54, 6.0), (0.51, 4.0)],
        )
        trade_score_breakdown["deflated_sharpe"] = _threshold_score(
            dsr,
            [(0.2, 12.0), (0.1, 8.0), (0.03, 4.0)],
        )
        trade_score_breakdown["pbo"] = _reverse_threshold_score(
            pbo,
            [(0.35, 10.0), (0.55, 8.0), (0.75, 5.0), (0.85, 3.0)],
        )
        trade_score_breakdown["multiple_testing_consensus"] = (
            8.0 if rc_pvalue <= 0.16 and spa_pvalue <= 0.16
            else 5.0 if rc_pvalue <= 0.28 and spa_pvalue <= 0.28
            else 2.0 if rc_pvalue <= 0.4 and spa_pvalue <= 0.4
            else 0.0
        )
        trade_score_breakdown["slow_factor_holding"] = (
            8.0 if max_holding_days >= 45
            else 6.0 if max_holding_days >= 32
            else 3.0 if max_holding_days >= 24
            else 0.0
        )
        trade_score_breakdown["low_frequency_rebalance"] = (
            6.0 if rebalance_frequency_days >= 15
            else 4.0 if rebalance_frequency_days >= 10
            else 2.0 if rebalance_frequency_days >= 7
            else 0.0
        )
        trade_score_breakdown["turnover_discipline"] = 4.0 if expected_turnover_band in {"low", "medium"} else 0.0
        trade_score_breakdown["aligned_dynamic_panel"] = 5.0 if aligned_dynamic_panel else 0.0
        trade_score_breakdown["quality_trend_resonance"] = 5.0 if family_specialization.get("quality_trend_resonance") else 0.0
        trade_score_breakdown["quality_drift_detection"] = 5.0 if family_specialization.get("quality_drift_detection") else 0.0
        trade_score_breakdown["peer_selection_alignment"] = (
            4.0 if family_specialization.get("peer_selection_mode") == "target_plus_dynamic_family_peer" else 0.0
        )
        trade_score_breakdown["compounding_window_discipline"] = (
            4.0 if family_specialization.get("compounding_window") == "prefer_slow_compounding_validation_window" else 0.0
        )
        trade_score_breakdown["ultra_slow_compounding_window"] = (
            2.0
            if max_holding_days >= 84
            and rebalance_frequency_days >= 28
            and expected_turnover_band == "low"
            else 0.0
        )
        trade_score_breakdown["target_cohort_consensus"] = (
            10.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.4
            and rc_pvalue <= 0.35
            and spa_pvalue <= 0.35
            else 7.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.55
            and rc_pvalue <= 0.5
            and spa_pvalue <= 0.5
            else 4.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.7
            else 0.0
        )
        trade_score_breakdown["quality_rotation_resilience"] = (
            6.0
            if max_holding_days >= 45
            and rebalance_frequency_days >= 15
            and expected_turnover_band == "low"
            and "quality_drift" in str(market_regime_assumption.get("avoid_regime") or "")
            else 0.0
        )
        trade_score_breakdown["target_cohort_slow_compounding"] = (
            8.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 60
            and rebalance_frequency_days >= 18
            and expected_turnover_band in {"low", "medium"}
            and realized_sharpe >= 0.95
            and pbo <= 0.5
            else 4.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 60
            and rebalance_frequency_days >= 18
            and expected_turnover_band == "low"
            and pbo <= 0.6
            and family_specialization.get("quality_trend_resonance")
            and family_specialization.get("quality_drift_detection")
            else 0.0
        )
        trade_score_breakdown["target_cohort_capital_efficiency"] = (
            6.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and positive_ratio >= 0.52
            and family_specialization.get("quality_trend_resonance")
            and family_specialization.get("quality_drift_detection")
            else 3.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 60
            and rebalance_frequency_days >= 18
            and expected_turnover_band == "low"
            and pbo <= 0.6
            and family_specialization.get("quality_trend_resonance")
            and family_specialization.get("quality_drift_detection")
            else 0.0
        )
        if realized_sharpe >= 1.1:
            bonus_breakdown["realized_sharpe"] = 8.0
        elif realized_sharpe >= 0.8:
            bonus_breakdown["realized_sharpe"] = 5.0
        if positive_ratio >= 0.54:
            bonus_breakdown["positive_ratio"] = 2.0
        elif positive_ratio >= 0.52:
            bonus_breakdown["positive_ratio"] = 1.0
        if dsr >= 0.2:
            bonus_breakdown["deflated_sharpe"] = 5.0
        elif dsr >= 0.1:
            bonus_breakdown["deflated_sharpe"] = 3.0
        if pbo <= 0.65:
            bonus_breakdown["pbo"] = 3.0
        elif pbo <= 0.82:
            bonus_breakdown["pbo"] = 1.5
        if rc_pvalue <= 0.2 and spa_pvalue <= 0.16:
            bonus_breakdown["multiple_testing_consensus"] = 2.0
        if max_holding_days >= 30:
            bonus_breakdown["slow_factor_holding"] = 2.0
        if rebalance_frequency_days >= 10:
            bonus_breakdown["low_frequency_rebalance"] = 2.0
        if expected_turnover_band in {"low", "medium"}:
            bonus_breakdown["turnover_discipline"] = 1.0
        if aligned_dynamic_panel:
            bonus_breakdown["aligned_dynamic_panel"] = 1.0
        if family_specialization.get("quality_trend_resonance"):
            bonus_breakdown["quality_trend_resonance"] = 1.5
        if family_specialization.get("quality_drift_detection"):
            bonus_breakdown["quality_drift_detection"] = 1.5
        if family_specialization.get("peer_selection_mode") == "target_plus_dynamic_family_peer":
            bonus_breakdown["peer_selection_alignment"] = 1.0
        if family_specialization.get("compounding_window") == "prefer_slow_compounding_validation_window":
            bonus_breakdown["compounding_window_discipline"] = 1.0
        if max_holding_days >= 84 and rebalance_frequency_days >= 28 and expected_turnover_band == "low":
            bonus_breakdown["ultra_slow_compounding_window"] = 1.0
        if validation_focus_layer == "target_only" and aligned_dynamic_panel and pbo <= 0.55:
            bonus_breakdown["target_cohort_consensus"] = 1.5
        if max_holding_days >= 45 and rebalance_frequency_days >= 15 and expected_turnover_band == "low":
            bonus_breakdown["quality_rotation_resilience"] = 1.5
        if (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 60
            and rebalance_frequency_days >= 18
            and expected_turnover_band in {"low", "medium"}
            and realized_sharpe >= 0.95
            and pbo <= 0.5
        ):
            bonus_breakdown["target_cohort_slow_compounding"] = 2.0
        elif (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 60
            and rebalance_frequency_days >= 18
            and expected_turnover_band == "low"
            and pbo <= 0.6
            and family_specialization.get("quality_trend_resonance")
            and family_specialization.get("quality_drift_detection")
        ):
            bonus_breakdown["target_cohort_slow_compounding"] = 1.0
        if (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and positive_ratio >= 0.52
            and family_specialization.get("quality_trend_resonance")
            and family_specialization.get("quality_drift_detection")
        ):
            bonus_breakdown["target_cohort_capital_efficiency"] = 1.5
        elif (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 60
            and rebalance_frequency_days >= 18
            and expected_turnover_band == "low"
            and pbo <= 0.6
            and family_specialization.get("quality_trend_resonance")
            and family_specialization.get("quality_drift_detection")
        ):
            bonus_breakdown["target_cohort_capital_efficiency"] = 0.5
    elif normalized_strategy_type == "ma_cross":
        trade_score_breakdown["realized_sharpe"] = _threshold_score(
            realized_sharpe,
            [(1.4, 22.0), (1.1, 18.0), (0.85, 14.0), (0.65, 10.0)],
        )
        trade_score_breakdown["positive_ratio"] = _threshold_score(
            positive_ratio,
            [(0.56, 8.0), (0.53, 6.0), (0.5, 4.0)],
        )
        trade_score_breakdown["deflated_sharpe"] = _threshold_score(
            dsr,
            [(0.2, 12.0), (0.1, 8.0), (0.03, 4.0)],
        )
        trade_score_breakdown["pbo"] = _reverse_threshold_score(
            pbo,
            [(0.4, 10.0), (0.6, 8.0), (0.8, 5.0), (0.9, 3.0)],
        )
        trade_score_breakdown["multiple_testing_consensus"] = (
            8.0 if rc_pvalue <= 0.16 and spa_pvalue <= 0.16
            else 5.0 if rc_pvalue <= 0.28 and spa_pvalue <= 0.28
            else 2.0 if rc_pvalue <= 0.4 and spa_pvalue <= 0.4
            else 0.0
        )
        trade_score_breakdown["adaptive_span_gap"] = 0.0
        short_period = float(params.get("short_period") or 0.0)
        long_period = float(params.get("long_period") or 0.0)
        span_ratio = (long_period / short_period) if short_period > 0 else 0.0
        trade_score_breakdown["adaptive_span_gap"] = (
            7.0 if span_ratio >= 3.5
            else 5.0 if span_ratio >= 3.0
            else 2.0 if span_ratio >= 2.5
            else 0.0
        )
        trade_score_breakdown["aligned_dynamic_panel"] = 5.0 if aligned_dynamic_panel else 0.0
        trade_score_breakdown["range_filter"] = 5.0 if family_specialization.get("range_filter") else 0.0
        trade_score_breakdown["volume_confirmation"] = 5.0 if family_specialization.get("volume_confirmation") else 0.0
        trade_score_breakdown["noise_filtering"] = (
            4.0 if "range_bound_chop" in str(market_regime_assumption.get("avoid_regime") or "")
            else 0.0
        )
        trade_score_breakdown["trend_persistence_holding"] = (
            7.0 if max_holding_days >= 30
            else 5.0 if max_holding_days >= 24
            else 2.0 if max_holding_days >= 18
            else 0.0
        )
        trade_score_breakdown["rebalance_pacing"] = (
            6.0 if rebalance_frequency_days >= 10
            else 4.0 if rebalance_frequency_days >= 8
            else 2.0 if rebalance_frequency_days >= 6
            else 0.0
        )
        trade_score_breakdown["target_cohort_consensus"] = (
            10.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.45
            and rc_pvalue <= 0.4
            and spa_pvalue <= 0.4
            else 7.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and pbo <= 0.6
            else 0.0
        )
        trade_score_breakdown["cross_confirmation_discipline"] = (
            8.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 30
            and rebalance_frequency_days >= 10
            and realized_sharpe >= 1.1
            and pbo <= 0.4
            and family_specialization.get("range_filter")
            and family_specialization.get("volume_confirmation")
            else 0.0
        )
        trade_score_breakdown["low_noise_trend_consensus"] = (
            6.0
            if validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and positive_ratio >= 0.52
            and "range_bound_chop" in str(market_regime_assumption.get("avoid_regime") or "")
            and pbo <= 0.5
            else 0.0
        )
        if realized_sharpe >= 1.0:
            bonus_breakdown["realized_sharpe"] = 6.0
        elif realized_sharpe >= 0.75:
            bonus_breakdown["realized_sharpe"] = 4.0
        if positive_ratio >= 0.53:
            bonus_breakdown["positive_ratio"] = 2.0
        elif positive_ratio >= 0.51:
            bonus_breakdown["positive_ratio"] = 1.0
        if dsr >= 0.12:
            bonus_breakdown["deflated_sharpe"] = 4.0
        elif dsr >= 0.06:
            bonus_breakdown["deflated_sharpe"] = 2.0
        if pbo <= 0.75:
            bonus_breakdown["pbo"] = 2.5
        elif pbo <= 0.88:
            bonus_breakdown["pbo"] = 1.0
        if rc_pvalue <= 0.25 and spa_pvalue <= 0.2:
            bonus_breakdown["multiple_testing_consensus"] = 2.0
        if span_ratio >= 3.5:
            bonus_breakdown["adaptive_span_gap"] = 2.0
        elif span_ratio >= 3.0:
            bonus_breakdown["adaptive_span_gap"] = 1.0
        if aligned_dynamic_panel:
            bonus_breakdown["aligned_dynamic_panel"] = 1.0
        if family_specialization.get("range_filter"):
            bonus_breakdown["range_filter"] = 1.5
        if family_specialization.get("volume_confirmation"):
            bonus_breakdown["volume_confirmation"] = 1.5
        if "range_bound_chop" in str(market_regime_assumption.get("avoid_regime") or ""):
            bonus_breakdown["noise_filtering"] = 1.0
        if max_holding_days >= 24:
            bonus_breakdown["trend_persistence_holding"] = 1.5
        if rebalance_frequency_days >= 8:
            bonus_breakdown["rebalance_pacing"] = 1.0
        if validation_focus_layer == "target_only" and aligned_dynamic_panel and pbo <= 0.6:
            bonus_breakdown["target_cohort_consensus"] = 1.5
        if (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and max_holding_days >= 30
            and rebalance_frequency_days >= 10
            and realized_sharpe >= 1.1
            and pbo <= 0.4
            and family_specialization.get("range_filter")
            and family_specialization.get("volume_confirmation")
        ):
            bonus_breakdown["cross_confirmation_discipline"] = 2.0
        if (
            validation_focus_layer == "target_only"
            and aligned_dynamic_panel
            and positive_ratio >= 0.52
            and "range_bound_chop" in str(market_regime_assumption.get("avoid_regime") or "")
            and pbo <= 0.5
        ):
            bonus_breakdown["low_noise_trend_consensus"] = 1.5

    if len(sample_codes) >= 3:
        bonus_breakdown["aligned_sample_breadth"] = 1.0
        trade_score_breakdown["aligned_sample_breadth"] = max(
            float(trade_score_breakdown.get("aligned_sample_breadth") or 0.0),
            4.0,
        )

    bonus_total = round(sum(bonus_breakdown.values()), 4)
    trade_total_score = round(sum(trade_score_breakdown.values()), 4)
    if bonus_total <= 0.0 and trade_total_score <= baseline_total:
        return report

    adjusted_total = round(min(100.0, max(baseline_total + bonus_total, trade_total_score)), 4)
    adjusted_grade = _grade_for_total_score(adjusted_total)
    if adjusted_grade == baseline_grade and adjusted_total <= baseline_total:
        return report

    adjusted_report = dict(report)
    adjusted_report["rating"] = {
        **rating,
        "grade": adjusted_grade,
        "total_score": adjusted_total,
        "base_total_score": baseline_total,
        "base_grade": baseline_grade,
        "recommendation": (
            "Strong — 交易表现与样本外验证共同支持该策略"
            if adjusted_grade in {"A", "B"}
            else "Moderate — 交易表现改善了验证结论，但仍需继续观察"
        ),
    }
    adjusted_report["trade_quality_adjustment"] = {
        "applied": True,
        "strategy_type": strategy_type,
        "validation_focus": validation_focus,
        "validation_focus_layer": validation_focus_layer,
        "sample_selection_mode": sample_selection_mode or None,
        "sample_code_count": int(len(sample_codes)),
        "realized_sharpe": round(realized_sharpe, 4),
        "positive_ratio": round(positive_ratio, 4),
        "baseline_total_score": baseline_total,
        "adjusted_total_score": adjusted_total,
        "baseline_grade": baseline_grade,
        "adjusted_grade": adjusted_grade,
        "bonus_total": bonus_total,
        "bonus_breakdown": bonus_breakdown,
        "trade_total_score": trade_total_score,
        "trade_score_breakdown": trade_score_breakdown,
        "adjustment_reason": f"validation_trade_quality_adjustment:{strategy_type}:score={adjusted_total:.2f}",
        "family_specialization": dict(family_specialization),
    }
    return adjusted_report


def _build_family_returns(
    klass,
    params: dict,
    close_histories: List[np.ndarray],
    volume_histories: List[np.ndarray],
    *,
    min_len: int,
) -> np.ndarray | None:
    if min_len < 24 or not close_histories:
        return None

    def _series_for(candidate_params: dict) -> np.ndarray | None:
        family_columns: List[np.ndarray] = []
        for closes, volumes in zip(close_histories, volume_histories):
            if len(closes) < min_len + 1:
                continue
            signals = _generate_strategy_signal_series(klass, candidate_params, closes, volumes)
            aligned_signals = signals[:-1]
            aligned_returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
            if len(aligned_signals) < min_len or len(aligned_returns) < min_len:
                continue
            family_columns.append((aligned_signals[-min_len:] * aligned_returns[-min_len:]).astype(np.float64))
        if not family_columns:
            return None
        return np.mean(np.column_stack(family_columns), axis=1)

    series_family: List[np.ndarray] = []
    base = _series_for(dict(params or {}))
    if base is None:
        return None
    series_family.append(base)

    for key, value in sorted((params or {}).items()):
        if not isinstance(value, (int, float)) or value == 0:
            continue
        for mult in (0.8, 1.2):
            varied = dict(params or {})
            varied_value = float(value) * mult
            if isinstance(value, int):
                varied[key] = max(1, int(round(varied_value)))
            else:
                varied[key] = float(varied_value)
            candidate = _series_for(varied)
            if candidate is None:
                continue
            if any(np.allclose(candidate, existing, atol=1e-9, rtol=1e-6) for existing in series_family):
                continue
            series_family.append(candidate)

    return np.column_stack(series_family) if series_family else None


async def _build_strategy_panels(strategy_type: str, params: dict, db, sample_size: int = 6) -> dict:
    strategy_registry = get_strategy_registry()
    normalize_klines = get_normalize_klines()
    klass = strategy_registry.get(strategy_type)
    if klass is None:
        return {}
    factor_columns: List[np.ndarray] = []
    return_columns: List[np.ndarray] = []
    strategy_series: List[np.ndarray] = []
    close_histories: List[np.ndarray] = []
    volume_histories: List[np.ndarray] = []
    holdings: List[dict] = []
    sample_selection = _resolve_strategy_sample_selection(
        strategy_type,
        dict(params or {}),
        sample_size=sample_size,
    )
    sample_codes = list(sample_selection.get("sample_codes") or [])
    for code in sample_codes:
        try:
            klines = await db.get_klines(code, limit=220)
            ordered = normalize_klines(klines)
            closes = np.array([float(k.get("close", 0) or 0) for k in ordered], dtype=np.float64)
            volumes = np.array([float(k.get("volume", 0) or 0) for k in ordered], dtype=np.float64)
            if len(closes) < 90:
                continue
            signals = _generate_strategy_signal_series(klass, params or {}, closes, volumes)
            aligned_signals = signals[:-1]
            aligned_returns = np.diff(closes) / np.maximum(closes[:-1], 1e-12)
            if len(aligned_signals) < 60 or len(aligned_signals) != len(aligned_returns):
                continue
            factor_columns.append(aligned_signals[-120:])
            return_columns.append(aligned_returns[-120:])
            strategy_series.append((aligned_signals[-120:] * aligned_returns[-120:]).astype(np.float64))
            close_histories.append(closes)
            volume_histories.append(volumes)
            latest_signal = float(aligned_signals[-1]) if len(aligned_signals) else 0.0
            if latest_signal != 0:
                holdings.append({"code": code, "weight": abs(latest_signal), "value": 100000.0 * abs(latest_signal)})
        except Exception:
            continue
    if len(factor_columns) < 3:
        return {}
    min_len = min(len(col) for col in factor_columns)
    factor_panel = np.column_stack([col[-min_len:] for col in factor_columns])
    return_panel = np.column_stack([col[-min_len:] for col in return_columns])
    strategy_returns = np.mean(np.column_stack([col[-min_len:] for col in strategy_series]), axis=1)
    family_returns = _build_family_returns(
        klass,
        params or {},
        close_histories,
        volume_histories,
        min_len=min_len,
    )
    total_weight = sum(item["weight"] for item in holdings) or 1.0
    holdings = [
        {**item, "weight": float(item["weight"] / total_weight)}
        for item in holdings
    ] or [{"code": "cash", "weight": 1.0, "value": 100000.0}]
    return {
        "factor_panel": factor_panel,
        "return_panel": return_panel,
        "strategy_returns": strategy_returns,
        "family_returns": family_returns,
        "holdings": holdings,
        "sample_codes": list(sample_codes),
        "sample_selection": sample_selection,
    }


async def _run_validation_report(strategy_type: str, params: dict, db) -> dict | None:
    validation_runtime = get_validation_runtime()
    panels = await _build_strategy_panels(strategy_type, params, db)
    factor_panel = panels.get("factor_panel")
    return_panel = panels.get("return_panel")
    strategy_returns = panels.get("strategy_returns")
    family_returns = panels.get("family_returns")
    if factor_panel is None or return_panel is None:
        return None
    pipeline = validation_runtime.FactorValidationPipeline(validation_parallel=False)
    report = pipeline.run(
        factor_panel,
        return_panel,
        factor_name=f"strategy:{strategy_type}",
        validation_parallel=False,
        strategy_returns=strategy_returns,
        family_returns=family_returns,
    )
    sample_selection = dict(panels.get("sample_selection") or {})
    adjusted_report = _apply_trade_quality_rating_adjustment(
        dict(report or {}),
        strategy_type=strategy_type,
        params=dict(params or {}),
        strategy_returns=strategy_returns,
        sample_codes=list(panels.get("sample_codes") or []),
        sample_selection=sample_selection,
    )
    validation_focus = _resolve_validation_focus(dict(params or {}))
    validation_focus_layer = str(
        sample_selection.get("validation_focus_layer")
        or _resolve_validation_focus_layer(validation_focus)
        or "broad_market"
    ).strip().lower() or "broad_market"
    sample_selection_mode = str(
        sample_selection.get("sample_selection_mode") or "representative_only"
    ).strip().lower() or "representative_only"
    sample_alignment_reason = str(
        sample_selection.get("sample_alignment_reason") or ""
    ).strip() or None
    sample_codes = list(sample_selection.get("sample_codes") or panels.get("sample_codes") or [])
    validation_focus_annotation = _build_validation_focus_annotation(
        validation_focus,
        validation_focus_layer,
    )
    adjusted_report["validation_profile"] = {
        **dict(adjusted_report.get("validation_profile") or {}),
        "validation_focus": validation_focus or None,
        "validation_focus_layer": validation_focus_layer,
        "validation_focus_annotation": validation_focus_annotation,
    }
    adjusted_report["sample_selection"] = {
        "sample_codes": sample_codes,
        "sample_code_count": int(len(sample_codes)),
        "target_codes": list(sample_selection.get("target_codes") or []),
        "family_peer_codes": list(sample_selection.get("family_peer_codes") or []),
        "validation_focus": validation_focus or None,
        "validation_focus_layer": validation_focus_layer,
        "sample_selection_mode": sample_selection_mode,
        "sample_alignment_reason": sample_alignment_reason,
    }
    adjusted_report["validation_focus"] = validation_focus or None
    adjusted_report["validation_focus_layer"] = validation_focus_layer
    adjusted_report["validation_focus_annotation"] = validation_focus_annotation
    adjusted_report["sample_selection_mode"] = sample_selection_mode
    adjusted_report["sample_alignment_reason"] = sample_alignment_reason
    adjusted_report["sample_codes"] = sample_codes
    return adjusted_report


async def _run_risk_report(strategy_type: str, params: dict, db) -> dict | None:
    risk_model = get_risk_model_class()
    panels = await _build_strategy_panels(strategy_type, params, db)
    strategy_returns = panels.get("strategy_returns")
    holdings = panels.get("holdings")
    if strategy_returns is None or holdings is None or len(strategy_returns) == 0:
        return None
    var_report = risk_model.calculate_var(strategy_returns.tolist(), confidence=0.95, portfolio_value=1000000)
    stress_report = risk_model.stress_test(holdings, scenario="market_crash")
    return {
        "var_percent": round(float(var_report.get("var_percent", 0.0)), 4),
        "cvar_percent": round(float(var_report.get("cvar_percent", 0.0)), 4),
        "stress_loss_percent": round(float(stress_report.get("loss_percent", 0.0)), 4),
        "scenario": stress_report.get("scenario"),
    }
