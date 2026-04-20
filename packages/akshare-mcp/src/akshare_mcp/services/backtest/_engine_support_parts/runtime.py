
from typing import List, Dict, Any, Optional, Union, Tuple
import numpy as np

from akshare_mcp.services.slippage import SlippageCalculator
from .utils import _ensure_dict_list, _compute_slippage_rate, _resolve_slippage_model
from .strategy_base import StrategySignalEvent
from .strategies import (
    _backtest_ma_cross_jit,
    _backtest_ma_cross_with_trades_jit,
    _backtest_momentum_jit,
    _backtest_rsi_jit,
)


_SLIPPAGE_NOTE = "JIT路径使用均值化滑点估算，实际交易成本可能偏高"
_ARRIVAL_PRICE_POLICY_BPS = {
    "close_proxy": 1.0,
    "close": 1.0,
    "same_close_proxy": 1.2,
    "twap_proxy": 1.2,
    "twap": 1.2,
    "vwap_proxy": 0.8,
    "vwap": 0.8,
    "next_open_proxy": 2.0,
    "next_open": 2.0,
    "event_open_proxy": 2.5,
}
_CAPACITY_BUCKET_BPS = {
    "mega": -2.0,
    "large": 0.0,
    "mid": 2.0,
    "small": 5.0,
    "micro": 8.0,
}
_POSITION_ASSUMPTION_PCT = {
    "single_name_full_notional": 1.0,
    "single_name": 1.0,
    "equal_weight_proxy": 0.2,
    "equal_weight": 0.2,
    "half_notional": 0.5,
}
_A_SHARE_MARKET_RULESETS = {"cn_equity", "a_share", "ashare", "cn_stock", "china_equity"}

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return float(result) if np.isfinite(result) else float(default)

def _resolve_market_ruleset(args: Dict[str, Any]) -> str:
    return str(args.get("market_ruleset") or "").strip().lower()

def _is_a_share_ruleset(args: Dict[str, Any]) -> bool:
    return _resolve_market_ruleset(args) in _A_SHARE_MARKET_RULESETS

def _resolve_position_pct(args: Dict[str, Any]) -> float:
    explicit_max_position = _safe_float(args.get("max_position_pct"), 0.0)
    if explicit_max_position > 0:
        return max(0.01, min(explicit_max_position, 1.0))

    position_assumption = str(args.get("position_assumption") or "").strip().lower()
    target_weight_scheme = str(args.get("target_weight_scheme") or "").strip().lower()
    if position_assumption in _POSITION_ASSUMPTION_PCT:
        return _POSITION_ASSUMPTION_PCT[position_assumption]
    if target_weight_scheme in _POSITION_ASSUMPTION_PCT:
        return _POSITION_ASSUMPTION_PCT[target_weight_scheme]
    if target_weight_scheme == "equal_weight":
        return 0.2
    return 1.0

def _estimate_implementation_shortfall(
    payload: Dict[str, Any],
    args: Dict[str, Any],
    *,
    closes: Optional[np.ndarray] = None,
    volumes: Optional[np.ndarray] = None,
    explicit_slippage_rate: float = 0.0,
    model_slippage_rate: float = 0.0,
    market_impact_bps: float = 0.0,
) -> tuple[float, str, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    price_arr = np.asarray(closes if closes is not None else [], dtype=float)
    volume_arr = np.asarray(volumes if volumes is not None else [], dtype=float)
    positive_prices = price_arr[np.isfinite(price_arr) & (price_arr > 0)]
    positive_volumes = volume_arr[np.isfinite(volume_arr) & (volume_arr > 0)]

    average_price = float(np.mean(positive_prices)) if positive_prices.size else 0.0
    average_volume_20 = float(np.mean(positive_volumes[-20:])) if positive_volumes.size else 0.0
    initial_capital = _safe_float(args.get("initial_capital"), 100000.0)
    position_pct = _resolve_position_pct(args)
    estimated_order_notional = max(0.0, initial_capital * position_pct)
    estimated_order_shares = estimated_order_notional / average_price if average_price > 0 else 0.0

    estimated_participation_rate = (
        estimated_order_shares / average_volume_20
        if average_volume_20 > 0
        else 0.0
    )
    configured_participation_rate = _safe_float(args.get("capacity_participation_rate"), 0.0)
    effective_participation_rate = max(estimated_participation_rate, configured_participation_rate)
    adv_ratio_limit = _safe_float(args.get("adv_ratio_limit"), 0.0)
    adv_utilization = (effective_participation_rate / adv_ratio_limit) if adv_ratio_limit > 0 else None

    arrival_policy = str(args.get("arrival_price_policy") or "next_open_proxy").strip().lower()
    arrival_bps = _ARRIVAL_PRICE_POLICY_BPS.get(arrival_policy)
    if arrival_bps is None:
        arrival_bps = 2.0 if "open" in arrival_policy else 1.0

    effective_slippage_bps = max(0.0, explicit_slippage_rate if explicit_slippage_rate > 0 else model_slippage_rate) * 10000.0
    tradability_filter = bool(args.get("tradability_filter", False) or payload.get("tradability_filter"))
    total_days = int(payload.get("total_days") or len(price_arr) or 0)
    if total_days and payload.get("tradable_days") is not None:
        tradable_days = int(payload.get("tradable_days") or 0)
    elif total_days:
        tradable_days = int(np.sum(volume_arr > 0)) if volume_arr.size else total_days
    else:
        tradable_days = 0
    tradable_ratio = (tradable_days / total_days) if total_days else 1.0

    tradability_bps = 0.0
    if tradability_filter:
        tradability_bps += max(0.0, (0.98 - tradable_ratio) * 150.0)
    elif tradable_ratio < 0.95:
        tradability_bps += max(0.0, (0.95 - tradable_ratio) * 60.0)
    if average_volume_20 <= 0:
        tradability_bps = max(tradability_bps, 12.0)

    capacity_bps = 0.0
    if effective_participation_rate > 0:
        capacity_bps += min(45.0, effective_participation_rate * 2500.0)
    if adv_utilization is not None and adv_utilization > 1.0:
        capacity_bps += min(60.0, (adv_utilization - 1.0) * 25.0)
    capacity_bucket = str(args.get("capacity_bucket") or "").strip().lower()
    if capacity_bucket:
        capacity_bps += _CAPACITY_BUCKET_BPS.get(capacity_bucket, 0.0)
    capacity_bps = max(0.0, capacity_bps)

    estimated_total_bps = effective_slippage_bps + max(0.0, market_impact_bps) + arrival_bps + tradability_bps + capacity_bps
    explicit_override = _safe_float(args.get("implementation_shortfall_proxy"), 0.0)
    if explicit_override > 0:
        source = "explicit_input"
        final_total_bps = explicit_override
    else:
        source = "estimated"
        final_total_bps = estimated_total_bps

    components = {
        "override_input_bps": round(explicit_override, 4) if explicit_override > 0 else None,
        "estimated_total_bps": round(estimated_total_bps, 4),
        "effective_total_bps": round(final_total_bps, 4),
        "effective_slippage_bps": round(effective_slippage_bps, 4),
        "market_impact_bps": round(max(0.0, market_impact_bps), 4),
        "arrival_bps": round(arrival_bps, 4),
        "tradability_bps": round(tradability_bps, 4),
        "capacity_bps": round(capacity_bps, 4),
        "arrival_price_policy": arrival_policy,
    }
    tradability_summary = {
        "tradability_filter": tradability_filter,
        "tradable_days": tradable_days if total_days else None,
        "total_days": total_days or None,
        "tradable_ratio": round(tradable_ratio, 4) if total_days else None,
        "tradability_penalty_bps": round(tradability_bps, 4),
    }
    capacity_summary = {
        "capacity_participation_rate": round(configured_participation_rate, 6) if configured_participation_rate else None,
        "adv_ratio_limit": round(adv_ratio_limit, 6) if adv_ratio_limit else None,
        "average_volume_20": round(average_volume_20, 4) if average_volume_20 > 0 else None,
        "capacity_bucket": capacity_bucket or None,
        "estimated_position_pct": round(position_pct, 4),
        "estimated_order_notional": round(estimated_order_notional, 4),
        "estimated_order_shares": round(estimated_order_shares, 4) if estimated_order_shares > 0 else None,
        "estimated_participation_rate": round(estimated_participation_rate, 6) if estimated_participation_rate > 0 else 0.0,
        "effective_participation_rate": round(effective_participation_rate, 6) if effective_participation_rate > 0 else 0.0,
        "adv_utilization": round(adv_utilization, 4) if adv_utilization is not None else None,
        "capacity_penalty_bps": round(capacity_bps, 4),
    }
    return round(final_total_bps, 4), source, components, tradability_summary, capacity_summary

def _attach_equity_curve(payload: Dict[str, Any], equity: np.ndarray) -> None:
    """将权益曲线（降采样至最多500点）和滑点标注附加到回测结果"""
    eq = equity.tolist()
    step = max(1, len(eq) // 500)
    payload['equity_curve'] = eq[::step]
    payload['slippage_model_note'] = _SLIPPAGE_NOTE

def _extract_benchmark_returns(params: Optional[Dict[str, Any]], expected_len: int) -> Optional[np.ndarray]:
    if not params or expected_len <= 0:
        return None
    raw = params.get('benchmark_returns')
    if isinstance(raw, (list, tuple, np.ndarray)):
        arr = np.asarray(raw, dtype=float)
        arr = arr[np.isfinite(arr)]
        return arr[-expected_len:] if arr.size else None

    bench_klines = params.get('benchmark_klines')
    if isinstance(bench_klines, list) and bench_klines:
        items = _ensure_dict_list(bench_klines)
        closes = np.array([float(k.get('close', 0) or 0) for k in items], dtype=float)
        if closes.size >= 2:
            prev = closes[:-1]
            curr = closes[1:]
            mask = prev > 0
            returns = np.zeros(curr.shape[0], dtype=float)
            returns[mask] = (curr[mask] - prev[mask]) / prev[mask]
            returns = returns[np.isfinite(returns)]
            return returns[-expected_len:] if returns.size else None
    return None

def _attach_advanced_metrics(payload: Dict[str, Any], equity: np.ndarray, params: Optional[Dict[str, Any]] = None) -> None:
    eq = np.asarray(equity, dtype=float)
    if eq.size < 2:
        payload.setdefault('annual_return', 0.0)
        payload.setdefault('annual_volatility', 0.0)
        payload.setdefault('sortino_ratio', 0.0)
        payload.setdefault('calmar_ratio', 0.0)
        payload.setdefault('omega_ratio', 0.0)
        payload.setdefault('benchmark_return', None)
        payload.setdefault('excess_return', None)
        payload.setdefault('information_ratio', None)
        return

    valid_prev = eq[:-1] > 0
    daily_returns = np.array([], dtype=float)
    if np.any(valid_prev):
        daily_returns = (eq[1:][valid_prev] - eq[:-1][valid_prev]) / eq[:-1][valid_prev]
        daily_returns = daily_returns[np.isfinite(daily_returns)]

    annual_return = 0.0
    final_capital = float(payload.get('final_capital') or 0.0)
    initial_capital = float(payload.get('initial_capital') or 0.0)
    if daily_returns.size > 0 and initial_capital > 0 and final_capital > 0:
        annual_return = float((final_capital / initial_capital) ** (252 / daily_returns.size) - 1)

    annual_volatility = float(np.std(daily_returns) * np.sqrt(252)) if daily_returns.size > 1 else 0.0
    risk_free_rate = 0.02
    downside = daily_returns[daily_returns < 0]
    downside_volatility = float(np.std(downside) * np.sqrt(252)) if downside.size > 0 else 0.0
    if downside_volatility > 0:
        sortino_ratio = (annual_return - risk_free_rate) / downside_volatility
    else:
        sortino_ratio = 999.0 if annual_return > risk_free_rate else 0.0

    max_drawdown = abs(float(payload.get('max_drawdown') or 0.0))
    calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else (999.0 if annual_return > 0 else 0.0)

    gains = float(np.clip(daily_returns, 0, None).sum()) if daily_returns.size > 0 else 0.0
    losses = float(np.clip(-daily_returns, 0, None).sum()) if daily_returns.size > 0 else 0.0
    omega_ratio = gains / losses if losses > 0 else (999.0 if gains > 0 else 0.0)

    payload['annual_return'] = round(float(annual_return), 6)
    payload['annual_volatility'] = round(float(annual_volatility), 6)
    payload['sortino_ratio'] = round(float(sortino_ratio), 6)
    payload['calmar_ratio'] = round(float(calmar_ratio), 6)
    payload['omega_ratio'] = round(float(omega_ratio), 6)

    benchmark_returns = _extract_benchmark_returns(params, daily_returns.size)
    if benchmark_returns is not None and benchmark_returns.size > 0 and daily_returns.size > 0:
        aligned = min(int(benchmark_returns.size), int(daily_returns.size))
        strat_slice = daily_returns[-aligned:]
        bench_slice = benchmark_returns[-aligned:]
        benchmark_return = float(np.prod(1 + bench_slice) - 1)
        strategy_return = float(np.prod(1 + strat_slice) - 1)
        excess_returns = strat_slice - bench_slice
        tracking_error = float(np.std(excess_returns) * np.sqrt(252)) if aligned > 1 else 0.0
        information_ratio = ((float(np.mean(excess_returns)) * 252) / tracking_error) if tracking_error > 0 else 0.0
        payload['benchmark_return'] = round(benchmark_return, 6)
        payload['excess_return'] = round(strategy_return - benchmark_return, 6)
        payload['information_ratio'] = round(float(information_ratio), 6)
    else:
        payload['benchmark_return'] = None
        payload['excess_return'] = None
        payload['information_ratio'] = None

def _attach_execution_audit(
    payload: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
    *,
    closes: Optional[np.ndarray] = None,
    volumes: Optional[np.ndarray] = None,
) -> None:
    args = dict(params or {})
    explicit_commission = _safe_float(args.get("commission", 0.0003), 0.0)
    explicit_slippage = _safe_float(args.get("slippage", 0.0), 0.0)
    model_slippage = _compute_slippage_rate(
        np.asarray(closes if closes is not None else [], dtype=float),
        np.asarray(volumes if volumes is not None else [], dtype=float),
        args,
        0.0,
    ) if closes is not None and volumes is not None else 0.0
    market_impact_bps = _safe_float(args.get("market_impact_bps", 0.0), 0.0)
    implementation_shortfall_proxy, implementation_source, shortfall_components, tradability_summary, capacity_summary = _estimate_implementation_shortfall(
        payload,
        args,
        closes=closes,
        volumes=volumes,
        explicit_slippage_rate=explicit_slippage,
        model_slippage_rate=model_slippage,
        market_impact_bps=market_impact_bps,
    )
    position_assumption = str(
        args.get("position_assumption")
        or ("equal_weight_proxy" if str(args.get("target_weight_scheme") or "").strip().lower() == "equal_weight" else "single_name_full_notional")
    ).strip() or "single_name_full_notional"
    market_ruleset = _resolve_market_ruleset(args)
    a_share_rules = _is_a_share_ruleset(args)
    sell_tax_rate = _safe_float(args.get("sell_tax_rate"), 0.001 if a_share_rules else 0.0)
    min_trade_lot = max(1, int(args.get("min_trade_lot", 100 if a_share_rules else 1) or (100 if a_share_rules else 1)))
    t_plus_one = bool(args.get("t_plus_one", a_share_rules))

    payload["cost_assumptions"] = {
        "commission_rate": round(explicit_commission, 8),
        "slippage_rate": round(explicit_slippage if explicit_slippage > 0 else model_slippage, 8),
        "slippage_model": args.get("slippage_model"),
        "arrival_price_policy": str(args.get("arrival_price_policy") or "next_open_proxy"),
        "market_impact_bps": round(market_impact_bps, 4),
        "implementation_shortfall_proxy": round(implementation_shortfall_proxy, 4),
        "implementation_shortfall_model_source": implementation_source,
        "market_ruleset": market_ruleset or None,
        "sell_tax_rate": round(sell_tax_rate, 6),
        "min_trade_lot": int(min_trade_lot),
        "t_plus_one": bool(t_plus_one),
    }
    payload["explicit_cost_breakdown"] = {
        "commission_rate": round(explicit_commission, 8),
        "sell_tax_rate": round(sell_tax_rate, 6),
    }
    payload["implicit_cost_breakdown"] = {
        "slippage_rate": round(explicit_slippage if explicit_slippage > 0 else model_slippage, 8),
        "market_impact_bps": round(market_impact_bps, 4),
        "implementation_shortfall_proxy": round(implementation_shortfall_proxy, 4),
        "implementation_shortfall_model_source": implementation_source,
        "market_ruleset": market_ruleset or None,
    }
    payload["implementation_shortfall_proxy"] = round(implementation_shortfall_proxy, 4)
    payload["implementation_shortfall_model_source"] = implementation_source
    payload["implementation_shortfall_components"] = shortfall_components
    payload["tradability_summary"] = tradability_summary
    payload["capacity_summary"] = capacity_summary
    payload["position_assumption"] = position_assumption
    payload["market_ruleset"] = market_ruleset or None
    payload["sell_tax_rate"] = round(sell_tax_rate, 6)
    payload["min_trade_lot"] = int(min_trade_lot)
    payload["t_plus_one"] = bool(t_plus_one)

def _finalize_backtest_payload(
    payload: Dict[str, Any],
    equity: np.ndarray,
    params: Optional[Dict[str, Any]] = None,
    *,
    closes: Optional[np.ndarray] = None,
    volumes: Optional[np.ndarray] = None,
) -> None:
    _attach_equity_curve(payload, equity)
    _attach_advanced_metrics(payload, equity, params=params)
    _attach_execution_audit(payload, params=params, closes=closes, volumes=volumes)

def _get_limit_ratio(code: str) -> float:
    """根据股票代码判断涨跌停幅度。"""
    c = str(code).strip()
    for prefix in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if c.startswith(prefix):
            c = c[len(prefix):]
            break
    if c.startswith("300") or c.startswith("301") or c.startswith("688"):
        return 0.20
    return 0.10

def _build_tradability_mask(
    closes: np.ndarray,
    volumes: Optional[np.ndarray] = None,
    code: str = "",
    is_st: bool = False,
) -> np.ndarray:
    """构建可交易性掩码（停牌 + 涨跌停保守过滤）。"""
    n = len(closes)
    mask = np.ones(n, dtype=bool)

    if volumes is not None and len(volumes) == n:
        mask &= volumes > 0

    limit_ratio = 0.05 if is_st else _get_limit_ratio(code)
    tolerance = 0.002
    for i in range(1, n):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        change = (closes[i] - prev) / prev
        if change >= limit_ratio - tolerance or change <= -(limit_ratio - tolerance):
            mask[i] = False
    return mask

def _round_down_lot(shares: int, lot_size: int) -> int:
    normalized_shares = max(0, int(shares or 0))
    normalized_lot = max(1, int(lot_size or 1))
    if normalized_lot <= 1:
        return normalized_shares
    return (normalized_shares // normalized_lot) * normalized_lot

def _rolling_average_volume(volumes: np.ndarray, index: int, window: int = 20) -> float:
    if index < 0:
        return 0.0
    start = max(0, int(index) - max(1, int(window or 20)) + 1)
    slice_ = np.asarray(volumes[start : int(index) + 1], dtype=float)
    positive = slice_[np.isfinite(slice_) & (slice_ > 0)]
    if positive.size == 0:
        return 0.0
    return float(np.mean(positive))

def _estimate_capacity_penalty_bps(
    args: Dict[str, Any],
    *,
    actual_participation_rate: float,
    adv_utilization: Optional[float],
) -> float:
    capacity_bps = 0.0
    if actual_participation_rate > 0:
        capacity_bps += min(45.0, actual_participation_rate * 2500.0)
    if adv_utilization is not None and adv_utilization > 1.0:
        capacity_bps += min(60.0, (adv_utilization - 1.0) * 25.0)
    capacity_bucket = str(args.get("capacity_bucket") or "").strip().lower()
    if capacity_bucket:
        capacity_bps += _CAPACITY_BUCKET_BPS.get(capacity_bucket, 0.0)
    return max(0.0, capacity_bps)
