"""候选因子验证流水线：编译、横截面、OOS、稳健性、相似度、成本容量。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..data_source import data_source
from .cost_model import build_cost_model
from .factor_analysis import FactorAnalyzer
from .factor_candidate_compiler import compile_factor_candidate, evaluate_compiled_factor
from .validation import FactorValidationPipeline

_SIMILARITY_BASIS_DEFINITIONS = [
    {"name": "basis_momentum_20d", "family": "momentum", "inputs": ["close"], "expression_dsl": "momentum_20d"},
    {"name": "basis_momentum_60d", "family": "momentum", "inputs": ["close"], "expression_dsl": "momentum_60d"},
    {"name": "basis_reversal_5d", "family": "reversal", "inputs": ["close"], "expression_dsl": "-return_5d"},
    {"name": "basis_volatility_20d", "family": "volatility", "inputs": ["close"], "expression_dsl": "volatility_20d"},
    {"name": "basis_volume_ratio", "family": "liquidity", "inputs": ["volume"], "expression_dsl": "volume_ratio_5_20"},
]

_SIMILARITY_BASIS_CACHE: dict[str, dict[str, Any]] = {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _round_float(value: Any, digits: int = 6, default: float = 0.0) -> float:
    return round(float(_safe_float(value, default)), digits)


def _sort_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows or []))
    if frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount", "turnover"])
    if "date" not in frame.columns:
        frame["date"] = ""
    frame = frame.copy()
    frame["_date_key"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.sort_values(by=["_date_key", "date"], ascending=[True, True]).drop(columns=["_date_key"])
    for column in ("open", "high", "low", "close", "volume", "amount", "turnover"):
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["date"] = frame["date"].astype(str)
    return frame.reset_index(drop=True)


async def _load_validation_frame(db, code: str, lookback_bars: int) -> tuple[pd.DataFrame, list[str], Optional[str]]:
    source_chain = []
    reason = None
    rows = []
    try:
        rows = await db.get_klines(code, limit=max(160, int(lookback_bars)))
        if rows:
            source_chain.append("db.get_klines")
    except Exception as exc:
        reason = f"db.get_klines failed: {exc}"
        rows = []
    if not rows:
        ds_rows = data_source.get_kline(code, period="daily", limit=max(160, int(lookback_bars)))
        if ds_rows:
            rows = [
                {
                    "date": row.get("date"),
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount", 0),
                    "turnover": row.get("turnover"),
                }
                for row in ds_rows
            ]
            source_chain.append("data_source.get_kline")
    return _sort_frame(rows), source_chain, reason


def _dedupe(seq: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item) for item in seq if str(item).strip()]))


def _build_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    series = pd.to_numeric(frame[column], errors="coerce").astype(float)
    return pd.Series(series.values, index=frame["date"].astype(str), dtype=float)


def _build_panel(series_map: dict[str, pd.Series]) -> pd.DataFrame:
    if not series_map:
        return pd.DataFrame()
    panel = pd.concat(series_map, axis=1)
    panel.index = panel.index.astype(str)
    try:
        panel = panel.sort_index(key=lambda idx: pd.to_datetime(idx, errors="coerce"))
    except Exception:
        panel = panel.sort_index()
    return panel


def _cross_section_summary(cs_rows: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    analyzer = FactorAnalyzer()
    date_metrics = []
    for date_key, rows in cs_rows.items():
        factor_values = [_safe_float(item.get("factor_value"), np.nan) for item in rows]
        future_returns = [_safe_float(item.get("future_return"), np.nan) for item in rows]
        if len(rows) < 3:
            continue
        dual = analyzer.calculate_ic_dual(
            factor_values=factor_values,
            forward_returns=future_returns,
            enable_neutralization=False,
        )
        date_metrics.append(
            {
                "date": date_key,
                "sample_size": len(rows),
                "normal_ic": float(dual.get("normal_ic", 0.0)),
                "rank_ic": float(dual.get("rank_ic", 0.0)),
                "normal_p_value": float(dual.get("normal_p_value", 1.0)),
                "rank_p_value": float(dual.get("rank_p_value", 1.0)),
            }
        )

    if not date_metrics:
        return {
            "dates": [],
            "summary": {
                "sample_dates": 0,
                "rank_ic_mean": 0.0,
                "rank_ic_std": 0.0,
                "rank_ic_ir": 0.0,
                "normal_ic_mean": 0.0,
                "positive_ratio": 0.0,
                "significant_ratio": 0.0,
            },
        }

    rank_ics = np.array([item["rank_ic"] for item in date_metrics], dtype=float)
    normal_ics = np.array([item["normal_ic"] for item in date_metrics], dtype=float)
    rank_std = float(np.std(rank_ics)) if len(rank_ics) > 1 else 0.0
    rank_ir = float(np.mean(rank_ics) / rank_std) if rank_std > 1e-12 else float(np.mean(rank_ics) * np.sqrt(max(len(rank_ics), 1)))
    significant_ratio = float(np.mean(np.array([item["rank_p_value"] < 0.05 for item in date_metrics], dtype=float)))
    return {
        "dates": date_metrics,
        "summary": {
            "sample_dates": len(date_metrics),
            "rank_ic_mean": round(float(np.mean(rank_ics)), 6),
            "rank_ic_std": round(rank_std, 6),
            "rank_ic_ir": round(rank_ir, 6),
            "normal_ic_mean": round(float(np.mean(normal_ics)), 6),
            "positive_ratio": round(float(np.mean(rank_ics > 0)), 6),
            "significant_ratio": round(significant_ratio, 6),
        },
    }


def _extract_latest_snapshot(cross_section_rows: dict[str, list[dict[str, Any]]], cross_section: dict[str, Any]) -> dict[str, Any]:
    if not cross_section.get("dates"):
        return {}
    latest_date = str(cross_section["dates"][-1]["date"])
    latest_rows = list(cross_section_rows.get(latest_date) or [])
    return {
        "date": latest_date,
        "sample_size": len(latest_rows),
        "top_codes": sorted(latest_rows, key=lambda item: item["factor_value"], reverse=True)[:5],
        "bottom_codes": sorted(latest_rows, key=lambda item: item["factor_value"])[:5],
    }


def _build_oos_validation_report(
    factor_df: pd.DataFrame,
    return_df: pd.DataFrame,
    *,
    factor_name: str,
) -> dict[str, Any]:
    if factor_df.empty or return_df.empty:
        return {"available": False, "reason": "empty_factor_or_return_panel"}

    common_index = factor_df.index.intersection(return_df.index)
    common_columns = factor_df.columns.intersection(return_df.columns)
    if len(common_index) < 30 or len(common_columns) < 3:
        return {
            "available": False,
            "reason": "insufficient_panel_shape",
            "n_periods": int(len(common_index)),
            "n_stocks": int(len(common_columns)),
        }

    factor_panel = factor_df.loc[common_index, common_columns].to_numpy(dtype=float)
    return_panel = return_df.loc[common_index, common_columns].to_numpy(dtype=float)
    min_samples = max(3, min(10, int(len(common_columns))))
    pipeline = FactorValidationPipeline(
        wf_train_window=max(20, min(60, int(len(common_index) * 0.45))),
        wf_test_window=max(5, min(20, int(len(common_index) * 0.2))),
        wf_step=max(5, min(20, int(len(common_index) * 0.2))),
        kfold_n_folds=max(3, min(5, int(len(common_index) // 20) or 3)),
        kfold_purge_gap=max(1, min(5, int(len(common_index) * 0.05) or 1)),
        min_samples=min_samples,
        validation_parallel=False,
        bootstrap_mode="fast",
    )
    report = pipeline.run(
        factor_panel=factor_panel,
        return_panel=return_panel,
        factor_name=factor_name,
        validation_parallel=False,
        max_workers=1,
        bootstrap_mode="fast",
    )
    return {"available": True, **report}


def _build_horizon_return_panel(close_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    horizon = max(1, int(horizon))
    shifted = close_df.shift(-horizon)
    denom = close_df.replace(0.0, np.nan)
    return (shifted - close_df) / denom


def _aggregate_rank_ic(factor_df: pd.DataFrame, return_df: pd.DataFrame) -> dict[str, Any]:
    analyzer = FactorAnalyzer()
    rows = []
    common_index = factor_df.index.intersection(return_df.index)
    common_columns = factor_df.columns.intersection(return_df.columns)
    if len(common_index) == 0 or len(common_columns) < 3:
        return {"sample_dates": 0, "rank_ic_mean": 0.0, "positive_ratio": 0.0, "significant_ratio": 0.0}

    for date_key in common_index:
        factor_values = factor_df.loc[date_key, common_columns].to_numpy(dtype=float)
        future_returns = return_df.loc[date_key, common_columns].to_numpy(dtype=float)
        dual = analyzer.calculate_ic_dual(
            factor_values=factor_values.tolist(),
            forward_returns=future_returns.tolist(),
            enable_neutralization=False,
        )
        if int(dual.get("sample_size", 0)) < 3:
            continue
        rows.append(
            {
                "rank_ic": float(dual.get("rank_ic", 0.0)),
                "rank_p_value": float(dual.get("rank_p_value", 1.0)),
            }
        )
    if not rows:
        return {"sample_dates": 0, "rank_ic_mean": 0.0, "positive_ratio": 0.0, "significant_ratio": 0.0}

    rank_ics = np.array([item["rank_ic"] for item in rows], dtype=float)
    return {
        "sample_dates": len(rows),
        "rank_ic_mean": _round_float(np.mean(rank_ics)),
        "rank_ic_std": _round_float(np.std(rank_ics)),
        "positive_ratio": _round_float(np.mean(rank_ics > 0)),
        "significant_ratio": _round_float(np.mean(np.array([item["rank_p_value"] < 0.05 for item in rows], dtype=float))),
    }


def _build_robustness_report(
    factor_df: pd.DataFrame,
    close_df: pd.DataFrame,
    *,
    base_horizon: int,
) -> dict[str, Any]:
    if factor_df.empty or close_df.empty:
        return {"available": False, "reason": "empty_factor_or_close_panel"}

    common_index = factor_df.index.intersection(close_df.index)
    common_columns = factor_df.columns.intersection(close_df.columns)
    if len(common_index) < 20 or len(common_columns) < 3:
        return {
            "available": False,
            "reason": "insufficient_panel_shape",
            "n_periods": int(len(common_index)),
            "n_stocks": int(len(common_columns)),
        }

    horizons = sorted({max(1, base_horizon // 2), max(1, int(base_horizon)), min(20, max(2, base_horizon * 2))})
    horizon_results = {}
    for horizon in horizons:
        one_return_df = _build_horizon_return_panel(close_df.loc[common_index, common_columns], horizon)
        horizon_results[str(horizon)] = _aggregate_rank_ic(
            factor_df.loc[common_index, common_columns],
            one_return_df,
        )

    eligible = [value["rank_ic_mean"] for value in horizon_results.values() if int(value.get("sample_dates", 0)) >= 5]
    horizon_stability = 0.0
    if len(eligible) >= 2:
        mean_val = float(np.mean(eligible))
        std_val = float(np.std(eligible))
        horizon_stability = max(0.0, min(1.0, 1.0 - (std_val / (abs(mean_val) + 1e-9))))

    base_return_df = _build_horizon_return_panel(close_df.loc[common_index, common_columns], base_horizon)
    base_dates = list(factor_df.loc[common_index, common_columns].index.intersection(base_return_df.index))
    split_detail: dict[str, Any]
    split_consistency = 0.0
    if len(base_dates) >= 10:
        half = len(base_dates) // 2
        first_dates = base_dates[:half]
        second_dates = base_dates[half:]
        first_res = _aggregate_rank_ic(
            factor_df.loc[first_dates, common_columns],
            base_return_df.loc[first_dates, common_columns],
        )
        second_res = _aggregate_rank_ic(
            factor_df.loc[second_dates, common_columns],
            base_return_df.loc[second_dates, common_columns],
        )
        same_sign = float(first_res.get("rank_ic_mean", 0.0)) * float(second_res.get("rank_ic_mean", 0.0)) >= 0
        diff = abs(float(first_res.get("rank_ic_mean", 0.0)) - float(second_res.get("rank_ic_mean", 0.0)))
        split_consistency = 1.0 if same_sign and diff < 0.05 else (0.5 if same_sign else 0.0)
        split_detail = {
            "first_half": first_res,
            "second_half": second_res,
            "same_sign": bool(same_sign),
            "rank_ic_diff": _round_float(diff, 4),
        }
    else:
        split_detail = {"note": "insufficient_dates_for_time_split"}

    base_stats = horizon_results.get(str(base_horizon), {})
    robustness_score = round(
        horizon_stability * 0.45
        + float(base_stats.get("positive_ratio", 0.0)) * 0.20
        + float(base_stats.get("significant_ratio", 0.0)) * 0.15
        + split_consistency * 0.20,
        4,
    )
    grade = "strong" if robustness_score >= 0.7 else ("moderate" if robustness_score >= 0.4 else "weak")
    return {
        "available": True,
        "base_horizon": int(base_horizon),
        "horizon_grid": horizons,
        "horizon_results": horizon_results,
        "time_split_consistency": {
            "score": split_consistency,
            "detail": split_detail,
        },
        "robustness_score": robustness_score,
        "grade": grade,
    }


def _basis_candidate(defn: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": defn["name"],
        "hypothesis": f"basis factor {defn['name']}",
        "family": defn["family"],
        "inputs": list(defn["inputs"]),
        "expression_dsl": defn["expression_dsl"],
        "expected_holding_period": 10,
        "expected_regime": [],
        "complexity_hint": "low",
        "novelty_rationale": "internal similarity basis",
    }


def _get_similarity_basis() -> dict[str, dict[str, Any]]:
    if _SIMILARITY_BASIS_CACHE:
        return _SIMILARITY_BASIS_CACHE
    for item in _SIMILARITY_BASIS_DEFINITIONS:
        compiled = compile_factor_candidate(_basis_candidate(item))
        _SIMILARITY_BASIS_CACHE[item["name"]] = compiled
    return _SIMILARITY_BASIS_CACHE


def _safe_corr(left: np.ndarray, right: np.ndarray) -> float:
    mask = np.isfinite(left) & np.isfinite(right)
    if int(mask.sum()) < 20:
        return 0.0
    lv = left[mask]
    rv = right[mask]
    if np.std(lv) < 1e-12 or np.std(rv) < 1e-12:
        return 0.0
    corr = np.corrcoef(lv, rv)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(corr)


def _build_similarity_report(
    compiled: dict[str, Any],
    frame_map: dict[str, pd.DataFrame],
    factor_df: pd.DataFrame,
) -> dict[str, Any]:
    if not frame_map or factor_df.empty:
        return {"available": False, "reason": "empty_frame_map_or_factor_panel"}

    basis_rows = []
    for basis_name, basis_compiled in _get_similarity_basis().items():
        basis_series_map: dict[str, pd.Series] = {}
        for code, frame in frame_map.items():
            try:
                basis_series = evaluate_compiled_factor(basis_compiled, frame)
                basis_series_map[code] = pd.Series(basis_series.values, index=frame["date"].astype(str), dtype=float)
            except Exception:
                continue

        basis_df = _build_panel(basis_series_map)
        common_index = factor_df.index.intersection(basis_df.index)
        common_columns = factor_df.columns.intersection(basis_df.columns)
        if len(common_index) == 0 or len(common_columns) == 0:
            corr = 0.0
            sample_size = 0
        else:
            left = factor_df.loc[common_index, common_columns].to_numpy(dtype=float).reshape(-1)
            right = basis_df.loc[common_index, common_columns].to_numpy(dtype=float).reshape(-1)
            mask = np.isfinite(left) & np.isfinite(right)
            sample_size = int(mask.sum())
            corr = _safe_corr(left, right)

        basis_rows.append(
            {
                "basis_factor": basis_name,
                "expression_dsl": basis_compiled.get("candidate", {}).get("expression_dsl"),
                "correlation": _round_float(corr, 6),
                "abs_correlation": _round_float(abs(corr), 6),
                "sample_size": sample_size,
            }
        )

    basis_rows.sort(key=lambda item: item.get("abs_correlation", 0.0), reverse=True)
    top_match = basis_rows[0] if basis_rows else None
    token_overlap = []
    candidate_fields = set(compiled.get("referenced_fields") or [])
    for basis_name, basis_compiled in _get_similarity_basis().items():
        basis_fields = set(basis_compiled.get("referenced_fields") or [])
        union = candidate_fields | basis_fields
        jaccard = (len(candidate_fields & basis_fields) / len(union)) if union else 0.0
        token_overlap.append(
            {
                "basis_factor": basis_name,
                "field_jaccard": _round_float(jaccard, 6),
            }
        )
    token_overlap.sort(key=lambda item: item["field_jaccard"], reverse=True)

    redundancy_flag = bool(top_match and abs(float(top_match.get("correlation", 0.0))) >= 0.95)
    return {
        "available": True,
        "top_similar_basis": basis_rows[:5],
        "field_overlap": token_overlap[:5],
        "redundancy_flag": redundancy_flag,
    }


def _build_turnover_report(factor_df: pd.DataFrame) -> dict[str, Any]:
    if factor_df.empty or len(factor_df.index) < 2 or len(factor_df.columns) < 2:
        return {"available": False, "reason": "insufficient_factor_panel_for_turnover"}
    top_n = max(1, min(len(factor_df.columns), max(3, len(factor_df.columns) // 3)))
    analyzer = FactorAnalyzer()
    turnover = analyzer.factor_turnover(factor_df, top_n=top_n)
    return {
        "available": True,
        "selection_size": int(top_n),
        "stats": {key: _round_float(value, 6) for key, value in turnover.items()},
    }


def _build_cost_capacity_report(
    factor_df: pd.DataFrame,
    amount_df: pd.DataFrame,
    *,
    turnover_report: dict[str, Any],
    hypothetical_notional: float = 1_000_000.0,
    max_participation_rate: float = 0.10,
) -> dict[str, Any]:
    if factor_df.empty or amount_df.empty or len(factor_df.columns) == 0:
        return {"available": False, "reason": "empty_factor_or_amount_panel"}

    common_index = factor_df.index.intersection(amount_df.index)
    common_columns = factor_df.columns.intersection(amount_df.columns)
    if len(common_index) == 0 or len(common_columns) == 0:
        return {"available": False, "reason": "no_common_factor_amount_panel"}

    top_n = max(1, min(len(common_columns), max(3, len(common_columns) // 3)))
    basket_amounts = []
    for date_key in common_index:
        factor_row = factor_df.loc[date_key, common_columns]
        amount_row = amount_df.loc[date_key, common_columns]
        ranked_codes = factor_row.dropna().sort_values(ascending=False).head(top_n).index
        if len(ranked_codes) == 0:
            continue
        basket_amount = pd.to_numeric(amount_row.loc[ranked_codes], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().sum()
        if np.isfinite(basket_amount) and basket_amount > 0:
            basket_amounts.append(float(basket_amount))

    avg_basket_amount = float(np.mean(basket_amounts)) if basket_amounts else 0.0
    deployable_notional_per_day = avg_basket_amount * max_participation_rate
    days_to_deploy = (
        float(hypothetical_notional / deployable_notional_per_day)
        if deployable_notional_per_day > 0
        else None
    )
    cost_model = build_cost_model(
        {
            "commission_rate": 0.0003,
            "slippage_bps": 5.0,
            "market_impact_bps": 3.0,
            "rebalance_frequency": "factor_rotation",
        },
        notional=float(hypothetical_notional),
        default_mode="execution",
        reference_price_fallback=1.0,
    )
    estimated_total = float((cost_model.get("estimated") or {}).get("total", 0.0))
    estimated_cost_rate = estimated_total / hypothetical_notional if hypothetical_notional > 0 else 0.0
    turnover_penalty = float((turnover_report.get("stats") or {}).get("mean_turnover", 0.0)) if turnover_report.get("available") else 0.0

    liquidity_score = 1.0
    if days_to_deploy is not None:
        liquidity_score = max(0.0, min(1.0, 1.0 / max(days_to_deploy, 1.0)))
    execution_score = round(
        max(0.0, 1.0 - estimated_cost_rate * 40.0) * 0.6
        + max(0.0, 1.0 - turnover_penalty) * 0.2
        + liquidity_score * 0.2,
        4,
    )
    return {
        "available": True,
        "selection_size": int(top_n),
        "hypothetical_notional": float(hypothetical_notional),
        "max_participation_rate": float(max_participation_rate),
        "avg_basket_amount": _round_float(avg_basket_amount, 2),
        "deployable_notional_per_day": _round_float(deployable_notional_per_day, 2),
        "days_to_deploy": _round_float(days_to_deploy, 4, 0.0) if days_to_deploy is not None else None,
        "estimated_cost_rate": _round_float(estimated_cost_rate, 6),
        "cost_model": cost_model,
        "execution_score": execution_score,
    }


def _build_validation_rating(
    cross_section_summary: dict[str, Any],
    oos_report: dict[str, Any],
    robustness_report: dict[str, Any],
    similarity_report: dict[str, Any],
    cost_capacity_report: dict[str, Any],
) -> dict[str, Any]:
    cross_score = min(25.0, abs(float(cross_section_summary.get("rank_ic_mean", 0.0))) * 100.0)

    oos_rating = (oos_report.get("rating") or {}) if oos_report.get("available") else {}
    oos_score = min(25.0, float(oos_rating.get("total_score", 0.0)) / 4.0)

    robustness_score = float(robustness_report.get("robustness_score", 0.0)) * 25.0 if robustness_report.get("available") else 0.0

    top_similarity = ((similarity_report.get("top_similar_basis") or [{}])[0] if similarity_report.get("available") else {})
    redundancy_penalty = min(12.0, max(0.0, abs(float(top_similarity.get("correlation", 0.0))) - 0.90) * 120.0)

    cost_rate = float(cost_capacity_report.get("estimated_cost_rate", 0.0)) if cost_capacity_report.get("available") else 0.0
    execution_score = float(cost_capacity_report.get("execution_score", 0.0)) * 15.0 if cost_capacity_report.get("available") else 0.0
    total_score = max(0.0, min(100.0, cross_score + oos_score + robustness_score + execution_score - redundancy_penalty))

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

    return {
        "grade": grade,
        "recommendation": recommendation,
        "total_score": _round_float(total_score, 4),
        "component_scores": {
            "cross_section": _round_float(cross_score, 4),
            "oos": _round_float(oos_score, 4),
            "robustness": _round_float(robustness_score, 4),
            "execution": _round_float(execution_score, 4),
        },
        "penalties": {
            "similarity_redundancy": _round_float(redundancy_penalty, 4),
            "estimated_cost_rate": _round_float(cost_rate, 6),
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

    rating = _build_validation_rating(
        cross_section.get("summary") or {},
        oos_report,
        robustness_report,
        similarity_report,
        cost_capacity_report,
    )

    sample_dates = int((cross_section.get("summary") or {}).get("sample_dates", 0))
    if sample_dates < 5:
        validation_warnings.append("insufficient_cross_section_dates_for_stable_validation")
    if not oos_report.get("available"):
        validation_warnings.append(f"oos_validation_unavailable:{oos_report.get('reason', 'unknown')}")
    if not robustness_report.get("available"):
        validation_warnings.append(f"robustness_unavailable:{robustness_report.get('reason', 'unknown')}")
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
