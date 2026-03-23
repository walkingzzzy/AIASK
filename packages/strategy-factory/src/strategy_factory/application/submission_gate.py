"""Shared submission-stage quality gate evaluation.

This module centralizes the Gate-3 quality evaluation used by both
strategy_manager submit/recheck flows and strategy_factory submitter.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from ..domain.constants import QUALITY_GATE_THRESHOLDS, TRADE_GATE_PROFILE_THRESHOLDS
from ..domain.targets import _extract_target_codes_from_payload, _normalize_research_task_contract
from ..infrastructure.mcp_services import get_normalize_klines, get_strategy_registry, get_validation_runtime
from .quality_reporting import maybe_grant_provisional_incubation, normalize_quality_gate_result, safe_metric_value


_FACTOR_VALIDATION_TYPES = {"value_factor", "quality_factor", "growth_factor", "multi_factor"}
_TRADE_VALIDATION_TYPES = {"momentum", "ma_cross", "rsi", "macro_timing", "dsl_rule"}


def _strategy_payload_value(strategy: dict, key: str, default: Any = None) -> Any:
    if key in strategy and strategy.get(key) is not None:
        return strategy.get(key)
    params = dict(strategy.get("params") or {})
    if key in params and params.get(key) is not None:
        return params.get(key)
    return default


def _resolve_validation_profile(strategy: dict) -> dict[str, Any]:
    strategy_type = str(strategy.get("strategy_type") or "").strip().lower()
    research_task = _normalize_research_task_contract(
        _strategy_payload_value(strategy, "research_task") or strategy.get("research_task") or {}
    )
    explicit_profile = dict(_strategy_payload_value(strategy, "validation_profile") or strategy.get("validation_profile") or {})
    profile_name = str(explicit_profile.get("profile") or "").strip().lower()
    validation_focus = str(
        explicit_profile.get("validation_focus")
        or research_task.get("validation_focus")
        or ("event_target_only" if research_task.get("task_source") == "event_driven" else "target_plus_representative")
    ).strip().lower()
    if not profile_name:
        if strategy_type in _FACTOR_VALIDATION_TYPES:
            profile_name = "factor_rank_validation"
        elif strategy_type == "macro_timing":
            profile_name = "macro_regime_validation"
        elif research_task.get("task_source") == "event_driven" or validation_focus == "event_target_only":
            profile_name = "event_trade_validation"
        else:
            profile_name = "trade_rule_validation"
    if explicit_profile.get("primary_validation_layer"):
        _raw_layer = str(explicit_profile["primary_validation_layer"])
    elif validation_focus == "event_target_only":
        _raw_layer = "target"
    elif validation_focus == "broad_generalization":
        _raw_layer = "combined"
    elif profile_name == "factor_rank_validation":
        _raw_layer = "combined"
    else:
        _raw_layer = "target"
    primary_validation_layer = _raw_layer.strip().lower()
    return {
        "profile": profile_name,
        "validation_focus": validation_focus,
        "primary_validation_layer": primary_validation_layer,
        "research_task": research_task,
    }


def _build_attempt_adjustment(strategy: dict) -> dict[str, Any]:
    factory_attempt_count = int(_strategy_payload_value(strategy, "factory_attempt_count", 0) or 0)
    factory_selected_count = int(_strategy_payload_value(strategy, "factory_selected_count", 0) or 0)
    task_attempt_count = int(_strategy_payload_value(strategy, "task_attempt_count", 0) or 0)
    task_selected_count = int(_strategy_payload_value(strategy, "task_selected_count", 0) or 0)
    external_attempt_count = int(_strategy_payload_value(strategy, "external_llm_attempt_count", 0) or 0)
    external_selected_count = int(_strategy_payload_value(strategy, "external_llm_selected_count", 0) or 0)
    attempt_count = max(factory_attempt_count, task_attempt_count, external_attempt_count, 1)
    selected_count = max(factory_selected_count, task_selected_count, external_selected_count, 0)
    selection_ratio = selected_count / max(attempt_count, 1)
    penalty = 0.0
    if attempt_count >= 10:
        penalty += 0.03
    if attempt_count >= 25:
        penalty += 0.05
    if attempt_count >= 50:
        penalty += 0.05
    if selected_count > 0 and selection_ratio < 0.2:
        penalty += 0.03
    return {
        "attempt_count": attempt_count,
        "selected_count": selected_count,
        "selection_ratio": round(selection_ratio, 4),
        "penalty": round(penalty, 4),
        "applied": penalty > 0,
    }


def _observed_sharpe_proxy(series: Optional[np.ndarray], fallback_score: float) -> float:
    arr = np.asarray(series if series is not None else [], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size >= 3:
        std = float(np.std(arr, ddof=1))
        if std > 1e-9:
            return float(np.mean(arr) / std * np.sqrt(252.0))
    return float(fallback_score or 0.0)


def _strategy_return_series_for_params(
    klass,
    params: dict[str, Any],
    close_panels: list[np.ndarray],
    *,
    min_len: int,
) -> Optional[np.ndarray]:
    series_list: list[np.ndarray] = []
    for closes in close_panels:
        window = np.asarray(closes[:min_len], dtype=float)
        if window.size < min_len:
            continue
        instance = klass()
        instance.set_parameters(params or {})
        signals = np.asarray(instance.generate_signals(window), dtype=float)
        if signals.size < min_len:
            continue
        aligned = signals[:min_len]
        forward_returns = np.zeros(min_len, dtype=float)
        valid_prev = np.maximum(window[:-1], 1e-12)
        forward_returns[:-1] = (window[1:] - window[:-1]) / valid_prev
        series_list.append((aligned * forward_returns).astype(float))
    if not series_list:
        return None
    return np.mean(np.column_stack(series_list), axis=1).astype(float)


def _build_strategy_family_returns(
    klass,
    strategy_params: dict[str, Any],
    close_panels: list[np.ndarray],
    *,
    min_len: int,
) -> Optional[np.ndarray]:
    if min_len < 24 or not close_panels:
        return None
    family_series: list[np.ndarray] = []

    base_series = _strategy_return_series_for_params(klass, strategy_params, close_panels, min_len=min_len)
    if base_series is None:
        return None
    family_series.append(base_series)

    for key, value in sorted((strategy_params or {}).items()):
        if not isinstance(value, (int, float)) or value == 0:
            continue
        for mult in (0.8, 1.2):
            varied_params = dict(strategy_params or {})
            varied_value = float(value) * mult
            if isinstance(value, int):
                varied_params[key] = max(1, int(round(varied_value)))
            else:
                varied_params[key] = float(varied_value)
            varied_series = _strategy_return_series_for_params(klass, varied_params, close_panels, min_len=min_len)
            if varied_series is None:
                continue
            if any(np.allclose(varied_series, existing, atol=1e-9, rtol=1e-6) for existing in family_series):
                continue
            family_series.append(varied_series)

    if len(family_series) < 2:
        return np.column_stack(family_series)
    return np.column_stack(family_series)


def _estimate_run_correction_metrics(
    attempt_adjustment: dict[str, Any],
    *,
    observed_score: float,
    score_series: Optional[np.ndarray] = None,
    family_returns: Optional[np.ndarray] = None,
    validation_runtime: Any = None,
) -> dict[str, Any]:
    attempt_count = max(1, int(attempt_adjustment.get("attempt_count") or 1))
    selection_ratio = float(attempt_adjustment.get("selection_ratio") or 0.0)
    penalty = float(attempt_adjustment.get("penalty") or 0.0)
    observed_score = float(observed_score or 0.0)

    arr = np.asarray(score_series if score_series is not None else [], dtype=float)
    arr = arr[np.isfinite(arr)]
    raw_sharpe_proxy = _observed_sharpe_proxy(arr, observed_score)
    sample_size = int(arr.size)
    dsr_hurdle = float(np.sqrt(max(0.0, 2.0 * np.log(max(attempt_count, 1)) / max(sample_size, 1)))) if sample_size else penalty
    deflated_sharpe_proxy = float(raw_sharpe_proxy - dsr_hurdle)

    # PBO 的正式实现需要 CSCV / family-level ranking；当前先给出 run-level proxy，
    # 明确把 selection_ratio 与 deflated score 合并为过拟合风险信号。
    logistic_term = 1.0 / (1.0 + np.exp(max(-8.0, min(8.0, deflated_sharpe_proxy * 2.0))))
    pbo_proxy = float(min(0.99, max(0.01, (1.0 - min(selection_ratio, 1.0)) * logistic_term + penalty)))

    reality_check_pvalue_proxy = float(min(0.99, max(0.01, 0.05 + penalty)))
    spa_pvalue_proxy = float(min(0.99, max(0.01, 0.05 + penalty * 0.8)))
    mode = "attempt_only_proxy"

    if sample_size >= 24:
        rng = np.random.default_rng(42)
        centered = arr - float(np.mean(arr))
        observed_mean = float(np.mean(arr))
        observed_std = float(np.std(arr, ddof=1))
        observed_t = observed_mean / (observed_std / np.sqrt(sample_size)) if observed_std > 1e-9 else 0.0
        bootstrap_rounds = min(96, max(32, attempt_count * 4))
        candidate_family = min(16, max(2, attempt_count))
        rc_samples: list[float] = []
        spa_samples: list[float] = []
        for _ in range(bootstrap_rounds):
            max_mean = -np.inf
            max_t = -np.inf
            for _ in range(candidate_family):
                sample = centered[rng.integers(0, sample_size, size=sample_size)]
                sample_mean = float(np.mean(sample))
                sample_std = float(np.std(sample, ddof=1))
                sample_t = sample_mean / (sample_std / np.sqrt(sample_size)) if sample_std > 1e-9 else 0.0
                if sample_mean > max_mean:
                    max_mean = sample_mean
                if max(0.0, sample_t) > max_t:
                    max_t = max(0.0, sample_t)
            rc_samples.append(max_mean)
            spa_samples.append(max_t)
        rc_arr = np.asarray(rc_samples, dtype=float)
        spa_arr = np.asarray(spa_samples, dtype=float)
        reality_check_pvalue_proxy = float(np.mean(rc_arr >= observed_mean))
        spa_pvalue_proxy = float(np.mean(spa_arr >= max(0.0, observed_t)))
        mode = "bootstrap_family_proxy"

    warnings: list[str] = []
    formal_fields: dict[str, Any] = {}
    runtime_dsr = getattr(validation_runtime, "deflated_sharpe_ratio", None) if validation_runtime else None
    runtime_pbo = getattr(validation_runtime, "probability_of_backtest_overfitting", None) if validation_runtime else None
    runtime_rc = getattr(validation_runtime, "white_reality_check", None) if validation_runtime else None
    runtime_spa = getattr(validation_runtime, "hansen_spa_test", None) if validation_runtime else None

    family_arr = np.asarray(family_returns if family_returns is not None else [], dtype=float)
    if family_arr.ndim == 1 and family_arr.size:
        family_arr = family_arr.reshape(-1, 1)
    if family_arr.ndim != 2:
        family_arr = np.zeros((0, 0), dtype=float)

    if callable(runtime_dsr) and sample_size >= 3:
        try:
            trial_sharpes = None
            if family_arr.size and family_arr.shape[1] >= 1:
                trial_sharpes = np.asarray(
                    [_observed_sharpe_proxy(family_arr[:, j], 0.0) for j in range(family_arr.shape[1])],
                    dtype=float,
                )
            dsr_result = runtime_dsr(
                arr,
                observed_sharpe=raw_sharpe_proxy,
                n_trials=max(attempt_count, int(family_arr.shape[1] or 1)),
                sharpe_trials=trial_sharpes,
                periods_per_year=252.0,
            )
            formal_fields.update(
                {
                    "multiple_testing_mode": "formal_runtime",
                    "deflated_sharpe_ratio": round(float(dsr_result.get("dsr", 0.0) or 0.0), 4),
                    "deflated_sharpe_reference_sharpe": round(float(dsr_result.get("reference_sharpe", 0.0) or 0.0), 4),
                    "deflated_sharpe_effective_trials": round(float(dsr_result.get("effective_trials", 0.0) or 0.0), 4),
                }
            )
            formal_fields.setdefault("multiple_testing", {})["deflated_sharpe"] = dict(dsr_result or {})
        except Exception as exc:
            warnings.append(f"run_correction:formal_dsr_failed:{type(exc).__name__}")

    if callable(runtime_pbo) and callable(runtime_rc) and callable(runtime_spa) and family_arr.shape[0] >= 12 and family_arr.shape[1] >= 2:
        try:
            pbo_result = runtime_pbo(family_arr, n_splits=8, metric="sharpe", periods_per_year=252.0, seed=42)
            rc_result = runtime_rc(family_arr, n_bootstrap=min(512, max(200, attempt_count * 8)), stationary_bootstrap_p=0.1, seed=42)
            spa_result = runtime_spa(
                family_arr,
                n_bootstrap=min(512, max(200, attempt_count * 8)),
                stationary_bootstrap_p=0.1,
                seed=42,
                center="consistent",
            )
            formal_fields.update(
                {
                    "multiple_testing_mode": "formal_runtime",
                    "pbo": round(float(pbo_result.get("pbo", 0.0) or 0.0), 4),
                    "white_reality_check_pvalue": round(float(rc_result.get("p_value", 0.0) or 0.0), 4),
                    "hansen_spa_pvalue": round(float(spa_result.get("p_value", 0.0) or 0.0), 4),
                }
            )
            mt_bucket = formal_fields.setdefault("multiple_testing", {})
            mt_bucket["pbo"] = dict(pbo_result or {})
            mt_bucket["white_reality_check"] = dict(rc_result or {})
            mt_bucket["hansen_spa"] = dict(spa_result or {})
        except Exception as exc:
            warnings.append(f"run_correction:formal_family_tests_failed:{type(exc).__name__}")

    if deflated_sharpe_proxy < 0:
        warnings.append("run_correction:deflated_sharpe_proxy_negative")
    if pbo_proxy > 0.55:
        warnings.append("run_correction:pbo_proxy_high")
    if reality_check_pvalue_proxy > 0.2:
        warnings.append("run_correction:reality_check_pvalue_proxy_weak")
    if spa_pvalue_proxy > 0.2:
        warnings.append("run_correction:spa_pvalue_proxy_weak")

    return {
        "run_correction_mode": mode,
        "raw_sharpe_proxy": round(raw_sharpe_proxy, 4),
        "deflated_sharpe_proxy": round(deflated_sharpe_proxy, 4),
        "pbo_proxy": round(pbo_proxy, 4),
        "reality_check_pvalue_proxy": round(reality_check_pvalue_proxy, 4),
        "spa_pvalue_proxy": round(spa_pvalue_proxy, 4),
        **formal_fields,
        "warnings": warnings,
    }


def _trade_gate_thresholds(profile: dict[str, Any], attempt_adjustment: dict[str, Any]) -> dict[str, float]:
    penalty = float(attempt_adjustment.get("penalty") or 0.0)
    validation_focus = str(profile.get("validation_focus") or "target_plus_representative")
    is_event = str(profile.get("profile") or "") == "event_trade_validation" or validation_focus == "event_target_only"
    base = dict(
        TRADE_GATE_PROFILE_THRESHOLDS["event_trade_validation" if is_event else "default"]
    )
    return {
        "post_cost_sharpe_min": float(base.get("post_cost_sharpe_min", 0.10)) + penalty,
        "trade_count_min": float(base.get("trade_count_min", 4.0)),
        "total_return_min": float(base.get("total_return_min", -0.02)),
        "target_layer_oos_return_min": float(base.get("target_layer_oos_return_min", -0.01)),
        "max_drawdown_max": float(base.get("max_drawdown_max", 0.45)),
        "event_window_hit_ratio_min": float(base.get("event_window_hit_ratio_min", 0.0)),
        "post_event_decay_min": float(base.get("post_event_decay_min", -1.0)),
        "trade_density_max": float(base.get("trade_density_max", 1.2)),
        "parameter_perturbation_trade_stability_min": float(
            base.get("parameter_perturbation_trade_stability_min", 0.25)
        ),
    }


def _has_trade_validation_audit(backtest_metrics: Optional[dict]) -> bool:
    metrics = dict(backtest_metrics or {})
    required_markers = {
        "post_cost_sharpe",
        "target_layer_oos_return",
        "target_layer_abnormal_return",
        "event_window_hit_ratio",
        "post_event_decay",
        "trade_density",
        "parameter_perturbation_trade_stability",
        "primary_validation_layer",
    }
    return any(key in metrics and metrics.get(key) is not None for key in required_markers)


def _evaluate_trade_profile(
    strategy: dict,
    profile: dict[str, Any],
    backtest_metrics: Optional[dict],
    risk_report: Optional[dict],
) -> dict[str, Any]:
    metrics = dict(backtest_metrics or {})
    attempt_adjustment = _build_attempt_adjustment(strategy)
    thresholds = _trade_gate_thresholds(profile, attempt_adjustment)
    reasons: list[str] = []
    warnings: list[str] = []

    post_cost_sharpe = safe_metric_value(metrics, "post_cost_sharpe", "sharpe_ratio")
    total_return = safe_metric_value(metrics, "target_layer_oos_return", "total_return")
    target_layer_oos_return = safe_metric_value(metrics, "target_layer_oos_return", "total_return")
    target_layer_abnormal_return = safe_metric_value(metrics, "target_layer_abnormal_return", "target_layer_oos_return", "total_return")
    trade_count = safe_metric_value(metrics, "trade_count", "trades_count")
    max_drawdown = abs(safe_metric_value(metrics, "max_drawdown"))
    avg_holding_days = safe_metric_value(metrics, "avg_holding_days")
    turnover_proxy = safe_metric_value(metrics, "turnover_proxy")
    if turnover_proxy <= 0 and trade_count > 0:
        turnover_proxy = round(trade_count / max(avg_holding_days, 5.0), 4) if avg_holding_days > 0 else float(trade_count)
    event_window_hit_ratio = safe_metric_value(metrics, "event_window_hit_ratio")
    post_event_decay = safe_metric_value(metrics, "post_event_decay")
    trade_density = safe_metric_value(metrics, "trade_density")
    parameter_stability = safe_metric_value(metrics, "parameter_perturbation_trade_stability")

    if post_cost_sharpe < thresholds["post_cost_sharpe_min"]:
        reasons.append(f"post_cost_sharpe {post_cost_sharpe:.3f} < {thresholds['post_cost_sharpe_min']:.3f}")
    if trade_count < thresholds["trade_count_min"]:
        reasons.append(f"trade_count {trade_count:.0f} < {thresholds['trade_count_min']:.0f}")
    if total_return < thresholds["total_return_min"]:
        reasons.append(f"total_return {total_return:.3f} < {thresholds['total_return_min']:.3f}")
    if target_layer_oos_return < thresholds["target_layer_oos_return_min"]:
        reasons.append(
            f"target_layer_oos_return {target_layer_oos_return:.3f} < {thresholds['target_layer_oos_return_min']:.3f}"
        )
    if max_drawdown > thresholds["max_drawdown_max"]:
        reasons.append(f"max_drawdown {max_drawdown:.3f} > {thresholds['max_drawdown_max']:.3f}")
    if thresholds["event_window_hit_ratio_min"] > 0 and event_window_hit_ratio and event_window_hit_ratio < thresholds["event_window_hit_ratio_min"]:
        reasons.append(
            f"event_window_hit_ratio {event_window_hit_ratio:.3f} < {thresholds['event_window_hit_ratio_min']:.3f}"
        )
    if post_event_decay < thresholds["post_event_decay_min"]:
        warnings.append(
            f"post_event_decay {post_event_decay:.3f} < {thresholds['post_event_decay_min']:.3f}"
        )
    if trade_density > thresholds["trade_density_max"]:
        warnings.append(
            f"trade_density {trade_density:.3f} > {thresholds['trade_density_max']:.3f}"
        )
    if parameter_stability and parameter_stability < thresholds["parameter_perturbation_trade_stability_min"]:
        warnings.append(
            "parameter_perturbation_trade_stability "
            f"{parameter_stability:.3f} < {thresholds['parameter_perturbation_trade_stability_min']:.3f}"
        )

    risk = dict(risk_report or {})
    stress_loss_percent = safe_metric_value(risk, "stress_loss_percent")
    if stress_loss_percent and stress_loss_percent <= -25.0:
        reasons.append(f"stress_loss_percent {stress_loss_percent:.2f} <= -25.00")

    return normalize_quality_gate_result(
        {
            "passed": len(reasons) == 0,
            "passed_strict": len(reasons) == 0,
            "profile": profile.get("profile"),
            "validation_focus": profile.get("validation_focus"),
            "primary_validation_layer": profile.get("primary_validation_layer"),
            "attempt_adjustment": attempt_adjustment,
            "thresholds": thresholds,
            "reasons": reasons,
            "warnings": warnings,
            "trade_count": round(trade_count, 4),
            "avg_holding_days": round(avg_holding_days, 4),
            "turnover_proxy": round(turnover_proxy, 4),
            "post_cost_sharpe": round(post_cost_sharpe, 4),
            "target_layer_oos_return": round(target_layer_oos_return, 4),
            "target_layer_abnormal_return": round(target_layer_abnormal_return, 4),
            "event_window_hit_ratio": round(event_window_hit_ratio, 4),
            "post_event_decay": round(post_event_decay, 4),
            "trade_density": round(trade_density, 4),
            "parameter_perturbation_trade_stability": round(parameter_stability, 4),
        }
    )


def _merge_text_items(*groups: Optional[list[str]]) -> list[str]:
    items: list[str] = []
    for group in groups:
        for item in group or []:
            text = str(item or "").strip()
            if text and text not in items:
                items.append(text)
    return items


async def _run_statistical_gate(
    db,
    strategy: dict,
    *,
    profile: dict[str, Any],
    klass,
) -> dict[str, Any]:
    normalize_klines = get_normalize_klines()
    validation_runtime = get_validation_runtime()

    instance = klass()
    strategy_params = strategy.get("params") or {}
    instance.set_parameters(strategy_params)

    target_codes = _extract_target_codes_from_payload(strategy)
    if profile.get("validation_focus") == "event_target_only" and target_codes:
        codes = list(target_codes)
    else:
        codes = list(dict.fromkeys([*target_codes, "600519", "000858", "601318", "600036", "000333"]))
    all_closes = []
    for code in codes:
        klines = await db.get_klines(code, limit=500)
        if klines and len(klines) >= 100:
            ordered = normalize_klines(klines)
            closes = np.array([float(k.get("close", 0)) for k in ordered], dtype=float)
            all_closes.append(closes)

    if not all_closes:
        return normalize_quality_gate_result({"passed": False, "reason": "Insufficient kline data for quality gate"})

    min_len = min(len(c) for c in all_closes)
    n_stocks = len(all_closes)
    factor_panel = np.zeros((min_len, n_stocks))
    return_panel = np.zeros((min_len, n_stocks))
    for j, closes in enumerate(all_closes):
        closes = closes[:min_len]
        signals = instance.generate_signals(closes)
        factor_panel[:, j] = signals[:min_len].astype(float)
        for i in range(min_len - 1):
            return_panel[i, j] = (closes[i + 1] - closes[i]) / closes[i] if closes[i] > 0 else 0

    flat_factors = factor_panel.flatten()
    flat_returns = return_panel.flatten()
    strategy_return_series = np.nanmean(factor_panel * return_panel, axis=1)
    family_returns = _build_strategy_family_returns(
        klass,
        strategy_params,
        [np.asarray(c[:min_len], dtype=float) for c in all_closes],
        min_len=min_len,
    )

    reasons = []
    attempt_adjustment = _build_attempt_adjustment(strategy)

    _wf_min = QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"] + float(attempt_adjustment.get("penalty") or 0.0)
    try:
        wf = validation_runtime.WalkForwardValidator(train_window=60, test_window=20, step=20)
        wf_summary = wf.validate(factor_panel, return_panel)
        wf_sharpe = wf_summary.oos_ic_ir
        if wf_sharpe < _wf_min:
            reasons.append(f"Walk-Forward IC IR {wf_sharpe:.3f} < {_wf_min}")
    except Exception as e:
        reasons.append(f"Walk-Forward error: {e}")
        wf_sharpe = 0

    _pkf_min = QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"] + float(attempt_adjustment.get("penalty") or 0.0) / 2.0
    try:
        pkf = validation_runtime.PurgedKFoldCV(n_folds=5, purge_gap=5)
        pkf_summary = pkf.validate(factor_panel, return_panel)
        pkf_ic = pkf_summary.oos_ic_mean
        if pkf_ic < _pkf_min:
            reasons.append(f"Purged K-Fold IC {pkf_ic:.4f} < {_pkf_min}")
    except Exception as e:
        reasons.append(f"Purged K-Fold error: {e}")
        pkf_ic = 0

    _bs_min = QUALITY_GATE_THRESHOLDS["bootstrap_ci_lower_min"] + float(attempt_adjustment.get("penalty") or 0.0) / 3.0
    try:
        bs = validation_runtime.bootstrap_ic_ci(flat_factors, flat_returns)
        ci_lower = bs.get("ci_lower", 0)
        if ci_lower < _bs_min:
            reasons.append(f"Bootstrap CI lower {ci_lower:.4f} < {_bs_min}")
    except Exception as e:
        reasons.append(f"Bootstrap error: {e}")
        ci_lower = 0

    _sens_max = QUALITY_GATE_THRESHOLDS["param_sensitivity_max"]
    sensitivity = 0.0
    try:
        ref_closes = all_closes[0][:min_len]
        ref_returns = return_panel[:, 0]
        base_signals = instance.generate_signals(ref_closes)[:min_len]
        base_ic = float(np.corrcoef(base_signals.astype(float), ref_returns)[0, 1])
        if not np.isnan(base_ic) and abs(base_ic) > 0.001:
            variations = []
            for key, val in strategy_params.items():
                if isinstance(val, (int, float)) and val != 0:
                    for mult in [0.8, 1.2]:
                        test_params = {**strategy_params, key: type(val)(val * mult)}
                        test_instance = klass()
                        test_instance.set_parameters(test_params)
                        test_signals = test_instance.generate_signals(ref_closes)[:min_len]
                        test_ic = float(np.corrcoef(test_signals.astype(float), ref_returns)[0, 1])
                        if not np.isnan(test_ic):
                            variations.append(abs(test_ic - base_ic) / abs(base_ic))
            if variations:
                sensitivity = float(np.mean(variations))
        if sensitivity > _sens_max:
            reasons.append(f"Parameter sensitivity {sensitivity:.2%} > {_sens_max:.0%}")
    except Exception as e:
        reasons.append(f"Sensitivity error: {e}")

    period_robustness = {"first_half_ic": 0.0, "second_half_ic": 0.0, "ic_consistency": 0.0}
    try:
        half = min_len // 2
        if half >= 50:
            first_factors = factor_panel[:half, :].flatten()
            first_returns = return_panel[:half, :].flatten()
            second_factors = factor_panel[half:, :].flatten()
            second_returns = return_panel[half:, :].flatten()
            ic_first = float(np.corrcoef(first_factors, first_returns)[0, 1])
            ic_second = float(np.corrcoef(second_factors, second_returns)[0, 1])
            if np.isnan(ic_first):
                ic_first = 0.0
            if np.isnan(ic_second):
                ic_second = 0.0
            period_robustness = {
                "first_half_ic": round(ic_first, 4),
                "second_half_ic": round(ic_second, 4),
                "ic_consistency": round(min(ic_first, ic_second), 4),
            }
            if ic_first < -0.02 or ic_second < -0.02:
                reasons.append(
                    f"Multi-period IC inconsistent: first_half={ic_first:.4f}, second_half={ic_second:.4f} (both must be >= -0.02)"
                )
            elif ic_first > 0.01 and ic_second < -0.01:
                reasons.append(
                    f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                )
            elif ic_first < -0.01 and ic_second > 0.01:
                reasons.append(
                    f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                )
    except Exception as e:
        reasons.append(f"Multi-period robustness error: {e}")

    observed_score = max(wf_sharpe, pkf_ic, ci_lower)
    run_correction = _estimate_run_correction_metrics(
        attempt_adjustment,
        observed_score=observed_score,
        score_series=strategy_return_series,
        family_returns=family_returns,
        validation_runtime=validation_runtime,
    )
    warnings = list(run_correction.pop("warnings", []))

    passed = len(reasons) == 0
    return normalize_quality_gate_result(
        {
            "passed": passed,
            "passed_strict": passed,
            "profile": profile.get("profile"),
            "validation_focus": profile.get("validation_focus"),
            "primary_validation_layer": profile.get("primary_validation_layer"),
            "attempt_adjustment": attempt_adjustment,
            "wf_ic_ir": round(wf_sharpe, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(ci_lower, 4),
            "param_sensitivity": round(sensitivity, 4),
            "period_robustness": period_robustness,
            "reasons": reasons,
            "warnings": warnings,
            **run_correction,
        }
    )


async def run_submission_quality_gate(
    db,
    strategy: dict,
    *,
    validation_report: dict | None = None,
    risk_report: dict | None = None,
    backtest_metrics: dict | None = None,
) -> Dict[str, Any]:
    """Run the submission-stage quality gate and return the final authority result."""
    try:
        profile = _resolve_validation_profile(strategy)
        strategy_type = str(strategy.get("strategy_type", "") or "").strip().lower()
        strategy_registry = get_strategy_registry()
        klass = strategy_registry.get(strategy_type) if strategy_type else None
        if klass is None:
            return normalize_quality_gate_result({"passed": False, "reason": f"Strategy type not in registry: {strategy_type}"})

        statistical_gate = await _run_statistical_gate(
            db,
            strategy,
            profile=profile,
            klass=klass,
        )
        uses_trade_profile = (
            profile["profile"] != "factor_rank_validation"
            and strategy_type in _TRADE_VALIDATION_TYPES
            and _has_trade_validation_audit(backtest_metrics)
        )
        normalized = statistical_gate
        if uses_trade_profile:
            trade_gate = _evaluate_trade_profile(strategy, profile, backtest_metrics, risk_report)
            trade_failed = not bool(trade_gate.get("passed"))
            merged_reasons = _merge_text_items(
                statistical_gate.get("reasons"),
                trade_gate.get("reasons") if trade_failed else [],
            )
            merged_warnings = _merge_text_items(
                statistical_gate.get("warnings"),
                trade_gate.get("warnings"),
            )
            normalized = normalize_quality_gate_result(
                {
                    **statistical_gate,
                    **{
                        key: value
                        for key, value in trade_gate.items()
                        if key
                        not in {"passed", "passed_strict", "reason", "reasons", "warnings", "reason_codes", "warning_codes"}
                    },
                    "passed": bool(statistical_gate.get("passed")) and bool(trade_gate.get("passed")),
                    "passed_strict": bool(statistical_gate.get("passed_strict", statistical_gate.get("passed")))
                    and bool(trade_gate.get("passed_strict", trade_gate.get("passed"))),
                    "reason": merged_reasons[0] if merged_reasons else "",
                    "reasons": merged_reasons,
                    "warnings": merged_warnings,
                }
            )
        return maybe_grant_provisional_incubation(
            strategy,
            normalized,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics=backtest_metrics,
        )
    except Exception as e:
        return normalize_quality_gate_result({"passed": False, "reason": str(e)})
