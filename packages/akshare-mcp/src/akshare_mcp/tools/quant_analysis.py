"""Quant factor analysis: IC, grouped backtest, OOS validation, robustness check."""

import time
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import stats

from ..services.factor_analysis import FactorAnalyzer as ICFactorAnalyzer
from ..services.slippage import SlippageCalculator
from ..services.validation import FactorValidationPipeline, bootstrap_ic_ci
from ..storage import get_db
from ..utils import fail, ok

from .quant_definitions import (
    DEFAULT_FACTOR_LOOKBACK,
    SUPPORTED_FACTORS,
    _QUANT_PERF_BREAKDOWN_ENABLED,
    _normalize_factor_name,
    _to_bool,
)
from .quant_engine import (
    _SLIPPAGE_MODEL_MAP,
    _build_perf_breakdown,
    _build_tradability_mask_local,
    _calculate_factor_value,
    _compute_trade_return_with_costs,
    _extract_style_exposures,
    _get_or_build_market_panel,
    _new_perf_tracker,
    _new_run_cache,
    _perf_add,
    _prefetch_market_data,
)


# ---------------------------------------------------------------------------
# IC Analysis
# ---------------------------------------------------------------------------

async def run_factor_ic_analysis(
    codes: list,
    factor: str,
    period: int = 20,
    enable_neutralization: bool = True,
    bootstrap_n: int = 1000,
    bootstrap_confidence: float = 0.95,
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    lookback_period = max(2, int(period))
    db = get_db()
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]

    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=lookback_period + 30,
    )
    _perf_add(perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    prefetch_meta = prefetch_resp.get("meta", {})

    factor_values = []
    future_returns = []
    industries = []
    market_caps = []
    betas = []
    stats_counter = {
        "input_codes": len(codes),
        "processed": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_no_factor_value": 0,
        "skipped_invalid_return": 0,
        "style_info_available": 0,
    }

    factor_stage_start = time.perf_counter()
    for code in codes:
        code_key = str(code or "").strip()
        code_data = prefetched.get(code_key, {})
        klines = code_data.get("klines") or []
        if not klines or len(klines) < lookback_period + 5:
            stats_counter["skipped_no_kline"] += 1
            continue

        panel = _get_or_build_market_panel(
            run_cache=run_cache,
            code=code_key,
            klines=klines,
            chronological=False,
            include_volume=False,
            include_returns=True,
        )
        closes = panel.get("closes") or []
        if len(closes) < lookback_period + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        financial = code_data.get("financial")
        if requires_financials and not financial:
            stats_counter["skipped_no_financials"] += 1
            continue

        stock_info = code_data.get("stock_info")

        factor_value = _calculate_factor_value(
            factor_name,
            closes[:lookback_period],
            financial=financial,
            stock_info=stock_info,
            period=min(lookback_period, len(closes[:lookback_period])),
        )
        if factor_value is None or np.isnan(factor_value):
            stats_counter["skipped_no_factor_value"] += 1
            continue

        current_idx = min(lookback_period - 1, len(closes) - 2)
        future_idx = min(current_idx + lookback_period, len(closes) - 1)
        if future_idx <= current_idx:
            stats_counter["skipped_invalid_return"] += 1
            continue

        current_price = closes[current_idx]
        future_price = closes[future_idx]
        if current_price <= 0:
            stats_counter["skipped_invalid_return"] += 1
            continue

        future_return = (future_price - current_price) / current_price
        styles = _extract_style_exposures(stock_info, financial)
        factor_values.append(float(factor_value))
        future_returns.append(float(future_return))
        industries.append(styles.get("industry"))
        market_caps.append(styles.get("market_cap"))
        betas.append(styles.get("beta"))

        if (
            styles.get("industry") is not None
            or styles.get("market_cap") is not None
            or styles.get("beta") is not None
        ):
            stats_counter["style_info_available"] += 1
        stats_counter["processed"] += 1
    _perf_add(perf, "factor", time.perf_counter() - factor_stage_start)

    sample_size = len(factor_values)
    if sample_size < 10:
        return fail(
            f"Not enough valid data for IC calculation: sample_size={sample_size}, "
            f"required>=10, stats={stats_counter}"
        )

    ic_stage_start = time.perf_counter()
    dual_ic = ICFactorAnalyzer.calculate_ic_dual(
        factor_values=factor_values,
        forward_returns=future_returns,
        industry=industries,
        market_cap=market_caps,
        beta=betas,
        enable_neutralization=bool(enable_neutralization),
    )
    rank_ic = float(dual_ic.get("rank_ic", 0.0))
    rank_p_value = float(dual_ic.get("rank_p_value", 1.0))
    bootstrap_n = max(200, min(10_000, int(bootstrap_n or 1000)))
    bootstrap_confidence = max(0.80, min(0.999, float(bootstrap_confidence or 0.95)))

    # --- P0-B: Bootstrap IC 置信区间 ---
    fv_arr = np.array(factor_values, dtype=np.float64)
    fr_arr = np.array(future_returns, dtype=np.float64)
    try:
        boot_rank = bootstrap_ic_ci(
            fv_arr,
            fr_arr,
            method="spearman",
            n_bootstrap=bootstrap_n,
            confidence=bootstrap_confidence,
            seed=42,
        )
        boot_normal = bootstrap_ic_ci(
            fv_arr,
            fr_arr,
            method="pearson",
            n_bootstrap=bootstrap_n,
            confidence=bootstrap_confidence,
            seed=42,
        )
    except Exception:
        boot_rank = {
            "ic": rank_ic,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "se": 0.0,
            "n_bootstrap": 0,
            "sample_size": sample_size,
            "confidence": bootstrap_confidence,
        }
        boot_normal = {
            "ic": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "se": 0.0,
            "n_bootstrap": 0,
            "sample_size": sample_size,
            "confidence": bootstrap_confidence,
        }
    _perf_add(perf, "ic", time.perf_counter() - ic_stage_start)

    # --- P0-B: 改进 IC_IR ---
    boot_se = boot_rank.get("se", 0.0)
    if boot_se > 1e-10:
        ic_ir = float(rank_ic / boot_se)
    else:
        ic_ir = float(rank_ic * np.sqrt(sample_size))

    win_count = sum(
        1
        for factor_value, future_return in zip(factor_values, future_returns)
        if (factor_value >= 0 and future_return >= 0) or (factor_value < 0 and future_return < 0)
    )
    win_rate = win_count / sample_size if sample_size > 0 else 0.0

    serialize_start = time.perf_counter()
    payload = {
        "factor": factor_name,
        # backward compatible fields
        "ic": rank_ic,
        "ic_ir": ic_ir,
        "p_value": rank_p_value,
        "significant": bool(rank_p_value < 0.05),
        # dual IC fields
        "normal_ic": float(dual_ic.get("normal_ic", 0.0)),
        "rank_ic": rank_ic,
        "normal_p_value": float(dual_ic.get("normal_p_value", 1.0)),
        "rank_p_value": rank_p_value,
        "sample_size": sample_size,
        "period": lookback_period,
        "win_rate": float(win_rate),
        # P0-B: Bootstrap 置信区间
        "bootstrap_ci": {
            "rank_ic": {
                "ic": boot_rank.get("ic", rank_ic),
                "ci_lower": boot_rank.get("ci_lower", 0.0),
                "ci_upper": boot_rank.get("ci_upper", 0.0),
                "se": boot_rank.get("se", 0.0),
                "confidence": boot_rank.get("confidence", 0.95),
            },
            "normal_ic": {
                "ic": boot_normal.get("ic", 0.0),
                "ci_lower": boot_normal.get("ci_lower", 0.0),
                "ci_upper": boot_normal.get("ci_upper", 0.0),
                "se": boot_normal.get("se", 0.0),
                "confidence": boot_normal.get("confidence", 0.95),
            },
            "n_bootstrap": boot_rank.get("n_bootstrap", 0),
            "ic_ir_method": "bootstrap_se" if boot_se > 1e-10 else "cross_sectional_proxy",
        },
        "data_window": {
            "lookback_bars": lookback_period + 30,
            "forward_period": lookback_period,
        },
        "stats": stats_counter,
        "prefetch": prefetch_meta,
        "neutralization": dual_ic.get("neutralization", {}),
        "source_chain": [
            "quant.prefetch_market_data",
            "db.get_klines_batch(optional)",
            "db.get_klines(fallback)",
            "db.get_financials(optional)",
            "db.get_stock_info",
            "factor_analysis.calculate_ic_dual",
            "validation.bootstrap_ic_ci",
        ],
        "params": {
            "enable_neutralization": bool(enable_neutralization),
            "bootstrap_n": bootstrap_n,
            "bootstrap_confidence": bootstrap_confidence,
        },
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=prefetch_meta,
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


# ---------------------------------------------------------------------------
# Grouped Factor Backtest
# ---------------------------------------------------------------------------

async def run_factor_group_backtest(
    codes: list,
    factor: str,
    groups: int = 5,
    holding_days: int = 20,
    factor_lookback: int = DEFAULT_FACTOR_LOOKBACK,
    commission: float = 0.0003,
    slippage: float = 0.0,
    slippage_model: str = "",
    tradability_filter: bool = False,
    is_st: bool = False,
    rebalance_step: int = 0,
    max_periods: int = 0,
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")

    if not codes:
        return fail("codes is required")

    groups = max(2, int(groups))
    holding_days = max(1, int(holding_days))
    factor_lookback = max(2, int(factor_lookback))
    commission = max(0.0, float(commission or 0.0))
    slippage = max(0.0, float(slippage or 0.0))
    tradability_filter = _to_bool(tradability_filter, False)
    is_st = _to_bool(is_st, False)
    rebalance_step = max(1, int(rebalance_step or holding_days))
    max_periods = max(0, int(max_periods or 0))

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    db = get_db()
    per_code_data: Dict[str, Dict[str, Any]] = {}
    period_results: List[Dict[str, Any]] = []
    long_short_returns: List[float] = []
    group_return_series: Dict[int, List[float]] = {i + 1: [] for i in range(groups)}
    group_stock_counts: Dict[int, List[int]] = {i + 1: [] for i in range(groups)}
    impact_cost_rates: List[float] = []
    transaction_cost_rates: List[float] = []

    slippage_model_name = str(slippage_model or "").strip().lower()
    slippage_calc = None
    if slippage_model_name in _SLIPPAGE_MODEL_MAP:
        slippage_calc = SlippageCalculator(_SLIPPAGE_MODEL_MAP[slippage_model_name])

    stats_counter = {
        "input_codes": len(codes),
        "processed_codes": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_no_future_window": 0,
        "skipped_no_factor_value": 0,
        "skipped_invalid_return": 0,
        "skipped_untradable": 0,
        "periods_total": 0,
        "periods_effective": 0,
        "candidate_signals": 0,
        "filled_signals": 0,
    }
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    fetch_bars = max(factor_lookback + holding_days * 8 + 5, 120)
    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=fetch_bars,
    )
    _perf_add(perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    prefetch_meta = prefetch_resp.get("meta", {})

    factor_stage_start = time.perf_counter()
    for code in codes:
        code_key = str(code or "").strip()
        code_data = prefetched.get(code_key, {})
        klines = code_data.get("klines") or []
        if not klines or len(klines) < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue

        panel = _get_or_build_market_panel(
            run_cache=run_cache,
            code=code_key,
            klines=klines,
            chronological=True,
            include_volume=True,
            include_returns=True,
        )
        closes_arr = panel.get("closes_arr")
        volumes_arr = panel.get("volumes_arr")
        if not isinstance(closes_arr, np.ndarray) or closes_arr.shape[0] < factor_lookback + 2:
            stats_counter["skipped_no_kline"] += 1
            continue
        if not isinstance(volumes_arr, np.ndarray) or volumes_arr.shape[0] != closes_arr.shape[0]:
            volumes_arr = np.zeros(closes_arr.shape[0], dtype=np.float64)

        financial = code_data.get("financial")
        if requires_financials and not financial:
            stats_counter["skipped_no_financials"] += 1
            continue

        stock_info = code_data.get("stock_info")

        tradability_mask = None
        if tradability_filter:
            tradability_mask = _build_tradability_mask_local(
                closes_arr,
                volumes_arr,
                code=code_key,
                is_st=is_st,
            )

        per_code_data[code_key] = {
            "closes_arr": closes_arr,
            "volumes_arr": volumes_arr,
            "financial": financial,
            "stock_info": stock_info,
            "tradability_mask": tradability_mask,
        }
        stats_counter["processed_codes"] += 1
    _perf_add(perf, "factor", time.perf_counter() - factor_stage_start)

    if len(per_code_data) < groups * 2:
        return fail(
            f"Not enough stocks for grouping: valid_codes={len(per_code_data)}, required>={groups * 2}, stats={stats_counter}"
        )

    min_series_len = min(int(v["closes_arr"].shape[0]) for v in per_code_data.values())
    start_t = factor_lookback - 1
    end_t = min_series_len - 1 - holding_days
    if end_t <= start_t:
        return fail(
            f"Not enough history for rolling grouped backtest: start_t={start_t}, end_t={end_t}, stats={stats_counter}"
        )

    period_indices = list(range(start_t, end_t + 1, rebalance_step))
    if max_periods > 0:
        period_indices = period_indices[-max_periods:]
    stats_counter["periods_total"] = len(period_indices)

    backtest_stage_start = time.perf_counter()
    for t in period_indices:
        period_stock_data = []
        for code, pdata in per_code_data.items():
            closes = pdata["closes_arr"]
            volumes = pdata["volumes_arr"]
            financial = pdata["financial"]
            stock_info = pdata["stock_info"]

            if len(closes) <= t + holding_days:
                stats_counter["skipped_no_future_window"] += 1
                continue

            window = closes[t - factor_lookback + 1 : t + 1]
            factor_value = _calculate_factor_value(
                factor_name,
                window,
                financial=financial,
                stock_info=stock_info,
                period=min(factor_lookback, int(window.shape[0])),
            )
            if factor_value is None or np.isnan(factor_value):
                stats_counter["skipped_no_factor_value"] += 1
                continue

            entry_idx = t
            exit_idx = t + holding_days
            entry_price = float(closes[entry_idx])
            exit_price = float(closes[exit_idx])
            if entry_price <= 0 or exit_price <= 0:
                stats_counter["skipped_invalid_return"] += 1
                continue

            stats_counter["candidate_signals"] += 1
            tradability_mask = pdata.get("tradability_mask")
            if tradability_filter and isinstance(tradability_mask, np.ndarray):
                entry_tradable = bool(tradability_mask[entry_idx]) if entry_idx < len(tradability_mask) else False
                exit_tradable = bool(tradability_mask[exit_idx]) if exit_idx < len(tradability_mask) else False
                if not (entry_tradable and exit_tradable):
                    stats_counter["skipped_untradable"] += 1
                    continue

            costed = _compute_trade_return_with_costs(
                entry_price=entry_price,
                exit_price=exit_price,
                entry_volume=float(volumes[entry_idx]) if entry_idx < int(volumes.shape[0]) else 0.0,
                exit_volume=float(volumes[exit_idx]) if exit_idx < int(volumes.shape[0]) else 0.0,
                commission=commission,
                slippage=slippage,
                slippage_calc=slippage_calc,
            )
            if not costed:
                stats_counter["skipped_invalid_return"] += 1
                continue

            stats_counter["filled_signals"] += 1
            impact_cost_rates.append(float(costed["impact_cost_rate"]))
            transaction_cost_rates.append(float(costed["transaction_cost_rate"]))
            period_stock_data.append(
                {
                    "code": code,
                    "factor_value": float(factor_value),
                    "return": float(costed["net_return"]),
                }
            )

        if len(period_stock_data) < groups * 2:
            continue

        period_stock_data.sort(key=lambda x: x["factor_value"])
        group_size = max(1, len(period_stock_data) // groups)
        period_group_returns = []
        for i in range(groups):
            start_idx = i * group_size
            end_idx = start_idx + group_size if i < groups - 1 else len(period_stock_data)
            group_stocks = period_stock_data[start_idx:end_idx]
            if not group_stocks:
                period_group_returns.append({"group": i + 1, "avg_return": 0.0, "stock_count": 0})
                continue

            avg_return = float(np.mean([s["return"] for s in group_stocks]))
            period_group_returns.append({"group": i + 1, "avg_return": avg_return, "stock_count": len(group_stocks)})
            group_return_series[i + 1].append(avg_return)
            group_stock_counts[i + 1].append(len(group_stocks))

        period_long_short = float(period_group_returns[-1]["avg_return"] - period_group_returns[0]["avg_return"])
        long_short_returns.append(period_long_short)
        period_results.append(
            {
                "period_index": int(t),
                "rebalance_window": {"entry_index": int(t), "exit_index": int(t + holding_days)},
                "long_short_return": period_long_short,
                "group_returns": period_group_returns,
                "stock_count": len(period_stock_data),
            }
        )
        stats_counter["periods_effective"] += 1
    _perf_add(perf, "backtest", time.perf_counter() - backtest_stage_start)

    if not long_short_returns:
        return fail(f"No effective rebalance periods generated, stats={stats_counter}")

    equity_curve = [1.0]
    for period_ret in long_short_returns:
        equity_curve.append(float(equity_curve[-1] * (1.0 + period_ret)))

    equity_arr = np.array(equity_curve, dtype=np.float64)
    peak = np.maximum.accumulate(equity_arr)
    drawdown = (peak - equity_arr) / np.where(peak > 0, peak, 1.0)
    max_drawdown = float(np.max(drawdown)) if drawdown.size > 0 else 0.0

    total_return = float(equity_curve[-1] - 1.0)
    total_days = max(1, holding_days * len(long_short_returns))
    annual_return = float((1.0 + total_return) ** (252.0 / total_days) - 1.0) if (1.0 + total_return) > 0 else -1.0

    returns_arr = np.array(long_short_returns, dtype=np.float64)
    mean_ret = float(np.mean(returns_arr)) if returns_arr.size > 0 else 0.0
    std_ret = float(np.std(returns_arr, ddof=1)) if returns_arr.size > 1 else 0.0
    sharpe_ratio = float((mean_ret / std_ret) * np.sqrt(252.0 / holding_days)) if std_ret > 0 else 0.0
    win_rate = float(np.sum(returns_arr > 0) / returns_arr.size) if returns_arr.size > 0 else 0.0

    group_returns = []
    for i in range(1, groups + 1):
        grets = group_return_series.get(i, [])
        gcounts = group_stock_counts.get(i, [])
        group_returns.append(
            {
                "group": i,
                "avg_return": float(np.mean(grets)) if grets else 0.0,
                "stock_count": int(np.mean(gcounts)) if gcounts else 0,
            }
        )

    candidate_signals = int(stats_counter.get("candidate_signals", 0))
    filled_signals = int(stats_counter.get("filled_signals", 0))
    fill_ratio = float(filled_signals / candidate_signals) if candidate_signals > 0 else 0.0
    untradable_ratio = float(
        stats_counter.get("skipped_untradable", 0) / candidate_signals
    ) if candidate_signals > 0 else 0.0

    serialize_start = time.perf_counter()
    payload = {
            "factor": factor_name,
            "groups": groups,
            "holding_days": holding_days,
            "factor_lookback": factor_lookback,
            "group_returns": group_returns,
            "period_group_results": period_results,
            "period_long_short_returns": [float(v) for v in long_short_returns],
            "equity_curve": [float(v) for v in equity_curve],
            "long_short_return": float(mean_ret),
            "period_long_short_mean": float(mean_ret),
            "total_stocks": len(per_code_data),
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "costs": {
                "commission": float(commission),
                "slippage": float(slippage),
                "slippage_model": slippage_model_name if slippage_calc is not None else "",
                "avg_transaction_cost_rate": float(np.mean(transaction_cost_rates)) if transaction_cost_rates else 0.0,
                "avg_impact_cost_rate": float(np.mean(impact_cost_rates)) if impact_cost_rates else 0.0,
            },
            "tradability": {
                "enabled": bool(tradability_filter),
                "candidate_signals": candidate_signals,
                "filled_signals": filled_signals,
                "fill_ratio": fill_ratio,
                "untradable_ratio": untradable_ratio,
            },
            "stats": stats_counter,
            "prefetch": prefetch_meta,
            "source_chain": [
                "quant.prefetch_market_data",
                "db.get_klines_batch(optional)",
                "db.get_klines(fallback)",
                "db.get_financials(optional)",
                "db.get_stock_info",
                "slippage(optional)",
                "tradability_filter(optional)",
                "numpy-grouping",
            ],
            "notes": "Grouped factor backtest uses rolling rebalances; max_drawdown is computed from the realized long-short equity curve.",
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=prefetch_meta,
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


# ---------------------------------------------------------------------------
# Factor-Return Panel Builder (used by OOS validation)
# ---------------------------------------------------------------------------

async def _build_factor_return_panels(
    codes: List[str],
    factor_name: str,
    db,
    *,
    factor_lookback: int,
    forward_period: int,
    panel_periods: int,
    run_cache: Optional[Dict[str, Any]] = None,
    perf: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建 OOS 验证所需的二维面板：factor_panel / return_panel。"""
    local_run_cache = run_cache if isinstance(run_cache, dict) else _new_run_cache()
    local_perf = perf if isinstance(perf, dict) else _new_perf_tracker(False)
    per_code_factors: Dict[str, List[float]] = {}
    per_code_returns: Dict[str, List[float]] = {}
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    stats_info = {
        "input_codes": len(codes),
        "processed_codes": 0,
        "skipped_no_kline": 0,
        "skipped_no_financials": 0,
        "skipped_short_series": 0,
    }

    fetch_bars = max(80, panel_periods + factor_lookback + forward_period + 20)
    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=fetch_bars,
    )
    _perf_add(local_perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    factor_stage_start = time.perf_counter()

    for code in codes:
        code_key = str(code or "").strip()
        code_data = prefetched.get(code_key, {})
        klines = code_data.get("klines") or []
        if not klines or len(klines) < (factor_lookback + forward_period + 5):
            stats_info["skipped_no_kline"] += 1
            continue

        panel = _get_or_build_market_panel(
            run_cache=local_run_cache,
            code=code_key,
            klines=klines,
            chronological=True,
            include_volume=False,
            include_returns=True,
        )
        closes_arr = panel.get("closes_arr")
        if not isinstance(closes_arr, np.ndarray) or closes_arr.shape[0] < (factor_lookback + forward_period + 5):
            stats_info["skipped_no_kline"] += 1
            continue

        financial = code_data.get("financial")
        if requires_financials and not financial:
            stats_info["skipped_no_financials"] += 1
            continue

        stock_info = code_data.get("stock_info")

        factors_one: List[float] = []
        returns_one: List[float] = []

        start_t = factor_lookback - 1
        end_t = int(closes_arr.shape[0]) - 1 - forward_period
        for t in range(start_t, end_t + 1):
            window = closes_arr[t - factor_lookback + 1 : t + 1]
            fv = _calculate_factor_value(
                factor_name,
                window,
                financial=financial,
                stock_info=stock_info,
                period=min(factor_lookback, int(window.shape[0])),
            )
            p0 = float(closes_arr[t])
            p1 = float(closes_arr[t + forward_period])
            if fv is None or np.isnan(fv) or p0 <= 0:
                continue
            ret = (p1 - p0) / p0
            if not np.isfinite(ret):
                continue
            factors_one.append(float(fv))
            returns_one.append(float(ret))

        if len(factors_one) < max(30, panel_periods // 2):
            stats_info["skipped_short_series"] += 1
            continue

        per_code_factors[code_key] = factors_one
        per_code_returns[code_key] = returns_one
        stats_info["processed_codes"] += 1
    _perf_add(local_perf, "factor", time.perf_counter() - factor_stage_start)

    if len(per_code_factors) < 5:
        return fail(f"Not enough valid codes for panel build, stats={stats_info}")

    common_len = min(len(v) for v in per_code_factors.values())
    common_len = min(common_len, panel_periods)
    if common_len < 30:
        return fail(f"Panel periods too short after alignment: {common_len}, stats={stats_info}")

    used_codes = sorted(per_code_factors.keys())
    factor_panel = np.array([per_code_factors[c][-common_len:] for c in used_codes], dtype=np.float64).T
    return_panel = np.array([per_code_returns[c][-common_len:] for c in used_codes], dtype=np.float64).T

    return ok(
        {
            "factor_panel": factor_panel,
            "return_panel": return_panel,
            "codes": used_codes,
            "periods": int(common_len),
            "stats": stats_info,
            "prefetch": prefetch_resp.get("meta", {}),
        }
    )


# ---------------------------------------------------------------------------
# OOS Validation (Walk-Forward + Purged KFold + Bootstrap CI)
# ---------------------------------------------------------------------------

async def run_factor_oos_validation(
    codes: List[str],
    factor: str,
    *,
    factor_lookback: int = 20,
    forward_period: int = 20,
    panel_periods: int = 180,
    wf_train_window: int = 60,
    wf_test_window: int = 20,
    wf_step: Optional[int] = None,
    kfold_n_folds: int = 5,
    kfold_purge_gap: int = 5,
    bootstrap_n: int = 1000,
    bootstrap_confidence: float = 0.95,
    validation_parallel: bool = True,
    max_workers: Optional[int] = None,
    bootstrap_mode: str = "",
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    """P0-A: 统一样本外验证工具（Walk-Forward + Purged KFold + Bootstrap CI）。"""
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}. Supported: {', '.join(sorted(SUPPORTED_FACTORS.keys()))}")
    if not codes:
        return fail("codes is required")

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    db = get_db()
    panel_resp = await _build_factor_return_panels(
        codes=codes,
        factor_name=factor_name,
        db=db,
        factor_lookback=max(2, int(factor_lookback)),
        forward_period=max(1, int(forward_period)),
        panel_periods=max(60, int(panel_periods)),
        run_cache=run_cache,
        perf=perf,
    )
    if not panel_resp.get("success"):
        return panel_resp

    pdata = panel_resp.get("data", {})
    factor_panel = pdata["factor_panel"]
    return_panel = pdata["return_panel"]

    bootstrap_mode_norm = str(bootstrap_mode or "").strip().lower()
    pipeline_bootstrap_n: Optional[int]
    if bootstrap_mode_norm in {"fast", "full"}:
        pipeline_bootstrap_n = None
    else:
        pipeline_bootstrap_n = max(200, int(bootstrap_n))

    pipeline = FactorValidationPipeline(
        wf_train_window=max(20, int(wf_train_window)),
        wf_test_window=max(5, int(wf_test_window)),
        wf_step=(None if wf_step in (None, 0) else int(wf_step)),
        kfold_n_folds=max(3, int(kfold_n_folds)),
        kfold_purge_gap=max(0, int(kfold_purge_gap)),
        bootstrap_n=pipeline_bootstrap_n,
        bootstrap_confidence=max(0.80, min(0.999, float(bootstrap_confidence))),
        validation_parallel=bool(validation_parallel),
        max_workers=max_workers,
        bootstrap_mode=bootstrap_mode_norm or None,
    )
    oos_stage_start = time.perf_counter()
    report = pipeline.run(
        factor_panel=factor_panel,
        return_panel=return_panel,
        factor_name=factor_name,
        validation_parallel=bool(validation_parallel),
        max_workers=max_workers,
        bootstrap_mode=bootstrap_mode_norm or None,
    )
    _perf_add(perf, "oos", time.perf_counter() - oos_stage_start)

    serialize_start = time.perf_counter()
    payload = {
            "factor": factor_name,
            "validation_report": report,
            "panel_info": {
                "n_periods": int(pdata.get("periods", 0)),
                "n_stocks": int(len(pdata.get("codes", []))),
                "codes": pdata.get("codes", []),
                "factor_lookback": int(factor_lookback),
                "forward_period": int(forward_period),
            },
            "stats": pdata.get("stats", {}),
            "prefetch": pdata.get("prefetch", {}),
            "source_chain": [
                "quant.prefetch_market_data",
                "db.get_klines_batch(optional)",
                "db.get_klines(fallback)",
                "db.get_financials(optional)",
                "db.get_stock_info",
                "validation.FactorValidationPipeline.run",
            ],
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=pdata.get("prefetch", {}),
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)


# ---------------------------------------------------------------------------
# Robustness Check
# ---------------------------------------------------------------------------

async def run_factor_robustness_check(
    codes: List[str],
    factor: str,
    windows: Optional[List[int]] = None,
    param_variations: Optional[List[int]] = None,
    include_perf_breakdown: bool = True,
) -> Dict[str, Any]:
    """P2-2: 多窗口 IC 稳定性 + 参数敏感性 + 子样本一致性。"""
    factor_name = _normalize_factor_name(factor)
    if factor_name not in SUPPORTED_FACTORS:
        return fail(f"Unsupported factor: {factor_name}")
    if not codes:
        return fail("codes is required")

    run_cache = _new_run_cache()
    perf = _new_perf_tracker(_to_bool(include_perf_breakdown, _QUANT_PERF_BREAKDOWN_ENABLED))
    windows = windows or [5, 10, 20, 60]
    param_variations = param_variations or [10, 20, 40, 60]
    db = get_db()
    requires_financials = SUPPORTED_FACTORS[factor_name]["requires_financials"]
    max_lookback = max([20] + [int(w) for w in windows] + [int(p) for p in param_variations])
    fetch_start = time.perf_counter()
    prefetch_resp = await _prefetch_market_data(
        db=db,
        codes=codes,
        need_financials=requires_financials,
        kline_limit=max_lookback + 30,
    )
    _perf_add(perf, "fetch", time.perf_counter() - fetch_start)
    prefetched = prefetch_resp.get("data", {})
    prefetch_meta = prefetch_resp.get("meta", {})

    # ── 辅助：单窗口截面 IC（复用预取数据） ──
    def _cross_section_ic(sub_codes: List[str], lookback: int) -> Dict[str, Any]:
        fv: List[float] = []
        fr: List[float] = []
        lb = max(2, int(lookback))
        for code in sub_codes:
            code_key = str(code or "").strip()
            code_data = prefetched.get(code_key, {})
            klines = code_data.get("klines") or []
            if not klines or len(klines) < lb + 5:
                continue
            panel = _get_or_build_market_panel(
                run_cache=run_cache,
                code=code_key,
                klines=klines,
                chronological=False,
                include_volume=False,
                include_returns=True,
            )
            closes_arr = panel.get("closes_arr")
            if not isinstance(closes_arr, np.ndarray) or closes_arr.shape[0] < lb + 2:
                continue
            financial = code_data.get("financial")
            if requires_financials and not financial:
                continue
            stock_info = code_data.get("stock_info")
            val = _calculate_factor_value(
                factor_name,
                closes_arr[:lb],
                financial=financial,
                stock_info=stock_info,
                period=lb,
            )
            if val is None or np.isnan(val):
                continue
            ci = min(lb - 1, int(closes_arr.shape[0]) - 2)
            fi = min(ci + lb, int(closes_arr.shape[0]) - 1)
            p0 = float(closes_arr[ci]) if ci >= 0 else 0.0
            if fi <= ci or p0 <= 0:
                continue
            fv.append(float(val))
            fr.append(float((float(closes_arr[fi]) - p0) / p0))

        n = len(fv)
        if n < 10:
            return {"ic": 0.0, "rank_ic": 0.0, "sample_size": n, "significant": False}
        ic = float(np.corrcoef(fv, fr)[0, 1])
        rank_ic = float(stats.spearmanr(fv, fr).statistic)
        p_val = float(stats.spearmanr(fv, fr).pvalue)
        return {
            "ic": ic,
            "rank_ic": rank_ic,
            "p_value": p_val,
            "sample_size": n,
            "significant": bool(p_val < 0.05),
        }

    robust_stage_start = time.perf_counter()
    # ── 1) 多窗口 IC 稳定性 ──
    multi_window_results = {}
    for w in windows:
        multi_window_results[str(w)] = _cross_section_ic(codes, int(w))

    ic_values = [v["rank_ic"] for v in multi_window_results.values() if v["sample_size"] >= 10]
    window_stability = (
        float(1.0 - (np.std(ic_values) / (abs(np.mean(ic_values)) + 1e-9)))
        if len(ic_values) >= 2
        else 0.0
    )
    window_stability = max(0.0, min(1.0, window_stability))

    # ── 2) 参数敏感性 ──
    param_results = {}
    for p in param_variations:
        param_results[str(p)] = _cross_section_ic(codes, int(p))

    param_ics = [v["rank_ic"] for v in param_results.values() if v["sample_size"] >= 10]
    param_stability = (
        float(1.0 - (np.std(param_ics) / (abs(np.mean(param_ics)) + 1e-9)))
        if len(param_ics) >= 2
        else 0.0
    )
    param_stability = max(0.0, min(1.0, param_stability))

    # ── 3) 子样本一致性（前半 vs 后半） ──
    half = len(codes) // 2
    if half >= 5:
        codes_a, codes_b = codes[:half], codes[half:]
        sub_a = _cross_section_ic(codes_a, 20)
        sub_b = _cross_section_ic(codes_b, 20)
        same_sign = (sub_a.get("rank_ic", 0.0) * sub_b.get("rank_ic", 0.0)) > 0
        diff = abs(float(sub_a.get("rank_ic", 0.0)) - float(sub_b.get("rank_ic", 0.0)))
        subsample_consistency = 1.0 if same_sign and diff < 0.05 else (0.5 if same_sign else 0.0)
        subsample_detail = {
            "sub_a": {"rank_ic": float(sub_a.get("rank_ic", 0.0)), "sample_size": int(sub_a.get("sample_size", 0))},
            "sub_b": {"rank_ic": float(sub_b.get("rank_ic", 0.0)), "sample_size": int(sub_b.get("sample_size", 0))},
            "same_sign": bool(same_sign),
            "ic_diff": round(diff, 4),
        }
    else:
        subsample_consistency = 0.0
        subsample_detail = {"note": "insufficient codes for sub-sample split (need >= 10)"}

    robustness_score = round((window_stability * 0.4 + param_stability * 0.3 + subsample_consistency * 0.3), 4)
    grade = "strong" if robustness_score >= 0.7 else ("moderate" if robustness_score >= 0.4 else "weak")
    _perf_add(perf, "robust", time.perf_counter() - robust_stage_start)

    serialize_start = time.perf_counter()
    payload = {
        "factor": factor_name,
        "robustness_score": robustness_score,
        "grade": grade,
        "multi_window_ic": {"results": multi_window_results, "stability": round(window_stability, 4)},
        "param_sensitivity": {"results": param_results, "stability": round(param_stability, 4)},
        "subsample_consistency": {"score": subsample_consistency, "detail": subsample_detail},
        "weights": {"multi_window": 0.4, "param_sensitivity": 0.3, "subsample": 0.3},
        "prefetch": prefetch_meta,
    }
    _perf_add(perf, "serialize", time.perf_counter() - serialize_start)
    perf_breakdown = _build_perf_breakdown(
        perf,
        prefetch_meta=prefetch_meta,
        run_cache=run_cache,
    )
    if perf_breakdown is not None:
        payload["perf_breakdown"] = perf_breakdown
    return ok(payload)
