"""回测引擎 - BacktestEngine 核心类"""

from typing import List, Dict, Any, Optional, Union, Tuple
import numpy as np

from akshare_mcp.services.slippage import SlippageCalculator
from .utils import _ensure_dict_list, _compute_slippage_rate, _resolve_slippage_model
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

def _build_strategy_masks(
    strategy: str,
    closes: np.ndarray,
    params: Dict[str, Any],
    volumes: Optional[np.ndarray] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """为策略构建 entry/exit 掩码。"""
    n = len(closes)
    strategy = str(strategy or "").strip().lower()

    if strategy == "ma_cross":
        short_period = max(2, int(params.get("short_period", 5)))
        long_period = max(short_period + 1, int(params.get("long_period", 20)))
        if n < long_period + 2:
            return None

        short_ma = np.full(n, np.nan, dtype=np.float64)
        long_ma = np.full(n, np.nan, dtype=np.float64)
        for i in range(short_period - 1, n):
            short_ma[i] = float(np.mean(closes[i - short_period + 1 : i + 1]))
        for i in range(long_period - 1, n):
            long_ma[i] = float(np.mean(closes[i - long_period + 1 : i + 1]))

        entry = np.zeros(n, dtype=bool)
        exit_ = np.zeros(n, dtype=bool)
        for i in range(long_period, n):
            if (
                short_ma[i - 1] <= long_ma[i - 1]
                and short_ma[i] > long_ma[i]
            ):
                entry[i] = True
            elif (
                short_ma[i - 1] >= long_ma[i - 1]
                and short_ma[i] < long_ma[i]
            ):
                exit_[i] = True
        return entry, exit_

    if strategy == "momentum":
        lookback = max(2, int(params.get("lookback", params.get("period", 20))))
        threshold = float(params.get("threshold", 0.02) or 0.02)
        if n < lookback + 2:
            return None

        momentum = np.zeros(n, dtype=np.float64)
        for i in range(lookback, n):
            base = closes[i - lookback]
            if base > 0:
                momentum[i] = (closes[i] - base) / base

        entry = momentum > threshold
        exit_ = momentum < -threshold
        entry[:lookback] = False
        exit_[:lookback] = False
        return entry, exit_

    if strategy == "rsi":
        rsi_period = max(2, int(params.get("rsi_period", 14)))
        oversold = float(params.get("oversold", 30) or 30)
        overbought = float(params.get("overbought", 70) or 70)
        if n < rsi_period + 2:
            return None

        rsi = np.full(n, np.nan, dtype=np.float64)
        for i in range(rsi_period, n):
            gains = 0.0
            losses = 0.0
            for j in range(i - rsi_period + 1, i + 1):
                change = closes[j] - closes[j - 1]
                if change > 0:
                    gains += change
                else:
                    losses -= change
            avg_gain = gains / rsi_period
            avg_loss = losses / rsi_period
            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))

        entry = rsi < oversold
        exit_ = rsi > overbought
        entry[:rsi_period] = False
        exit_[:rsi_period] = False
        return entry, exit_

    # Fallback: try StrategyRegistry for user-submitted strategies
    from .strategy_registry import StrategyRegistry
    klass = StrategyRegistry.get(strategy)
    if klass is not None:
        instance = klass()
        instance.set_parameters(params)
        return instance.generate_entry_exit_masks(closes, volumes)

    return None

def _simulate_trades_from_masks(
    closes: np.ndarray,
    volumes: np.ndarray,
    entry_mask: np.ndarray,
    exit_mask: np.ndarray,
    initial_capital: float,
    commission_rate: float,
    slippage_calc: Optional[SlippageCalculator] = None,
    tradability_mask: Optional[np.ndarray] = None,
    return_trades: bool = False,
    klines: Optional[List[Dict[str, Any]]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按 entry/exit 掩码执行交易仿真，支持逐笔滑点与可交易过滤。"""
    n = len(closes)
    args = dict(params or {})
    a_share_rules = _is_a_share_ruleset(args)
    lot_size = max(1, int(args.get("min_trade_lot", 100 if a_share_rules else 1) or (100 if a_share_rules else 1)))
    sell_tax_rate = _safe_float(args.get("sell_tax_rate"), 0.001 if a_share_rules else 0.0)
    t_plus_one = bool(args.get("t_plus_one", a_share_rules))
    position_pct = _resolve_position_pct(args)
    payload_context = {
        "tradable_days": int(np.sum(tradability_mask)) if tradability_mask is not None else int(np.sum(volumes > 0)),
        "total_days": int(n),
        "tradability_filter": bool(tradability_mask is not None),
    }
    explicit_slippage = _safe_float(args.get("slippage", 0.0), 0.0)
    model_slippage = _compute_slippage_rate(closes, volumes, args, 0.0)
    market_impact_bps = _safe_float(args.get("market_impact_bps", 0.0), 0.0)
    implementation_shortfall_proxy, _shortfall_source, shortfall_components, _tradability_summary, _capacity_summary = _estimate_implementation_shortfall(
        payload_context,
        args,
        closes=closes,
        volumes=volumes,
        explicit_slippage_rate=explicit_slippage,
        model_slippage_rate=model_slippage,
        market_impact_bps=market_impact_bps,
    )
    execution_total_bps = float(shortfall_components.get("effective_total_bps") or implementation_shortfall_proxy or 0.0)
    if slippage_calc is not None:
        execution_total_bps = max(0.0, execution_total_bps - float(shortfall_components.get("effective_slippage_bps") or 0.0))
    per_side_extra_cost_rate = max(0.0, execution_total_bps / 10000.0 / 2.0)
    cash = float(initial_capital)
    shares = 0
    buy_price = 0.0
    buy_index = -1
    trades = 0
    wins = 0
    equity = np.full(n, float(initial_capital), dtype=np.float64)
    trades_detail: List[Dict[str, Any]] = []
    total_traded_notional = 0.0
    holding_periods: List[int] = []

    for i in range(n - 1):
        tradable = True if tradability_mask is None else bool(tradability_mask[i])
        # Next-bar execution: signal on bar i, execute at bar i+1 close (proxy for next open)
        next_tradable = True if tradability_mask is None else bool(tradability_mask[i + 1])
        if entry_mask[i] and shares == 0 and cash > 0 and tradable and next_tradable:
            exec_price = float(closes[i + 1])
            if slippage_calc is not None:
                approx_price = exec_price * (1 + commission_rate + per_side_extra_cost_rate)
                max_entry_notional = max(0.0, (cash + shares * closes[i]) * position_pct)
                affordable_cash = min(cash, max_entry_notional) if max_entry_notional > 0 else cash
                est_shares = int(affordable_cash / approx_price) if approx_price > 0 else 0
                if lot_size > 1:
                    est_shares = (est_shares // lot_size) * lot_size
                if est_shares <= 0:
                    equity[i] = cash
                    continue
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes[i + 1]) if i + 1 < len(volumes) else 0.0,
                    order_size=float(est_shares),
                    is_buy=True,
                )
                exec_price = float(slip.get("execution_price", exec_price))

            buy_price = exec_price * (1 + commission_rate + per_side_extra_cost_rate)
            max_entry_notional = max(0.0, (cash + shares * closes[i]) * position_pct)
            affordable_cash = min(cash, max_entry_notional) if max_entry_notional > 0 else cash
            max_shares = int(affordable_cash / buy_price) if buy_price > 0 else 0
            if lot_size > 1:
                max_shares = (max_shares // lot_size) * lot_size
            if max_shares > 0:
                shares = max_shares
                cash -= shares * buy_price
                trades += 1
                buy_index = int(i + 1)
                total_traded_notional += float(shares * buy_price)
                if return_trades:
                    trade_time = ""
                    if klines is not None and i + 1 < len(klines):
                        row = klines[i + 1]
                        trade_time = str(row.get("date", row.get("trade_date", row.get("time", ""))))
                    trades_detail.append(
                        {
                            "index": int(i + 1),
                            "time": trade_time,
                            "price": float(buy_price),
                            "signal": 1,
                            "shares": int(shares),
                            "profit": 0.0,
                        }
                    )

        elif exit_mask[i] and shares > 0 and tradable and next_tradable:
            if t_plus_one and buy_index >= 0 and (i + 1) <= buy_index:
                equity[i] = cash + shares * closes[i]
                continue
            exec_price = float(closes[i + 1])
            if slippage_calc is not None:
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes[i + 1]) if i + 1 < len(volumes) else 0.0,
                    order_size=float(shares),
                    is_buy=False,
                )
                exec_price = float(slip.get("execution_price", exec_price))

            sell_price = exec_price * (1 - commission_rate - per_side_extra_cost_rate - sell_tax_rate)
            sell_price = max(0.0, sell_price)
            revenue = shares * sell_price
            profit = revenue - (shares * buy_price)
            if profit > 0:
                wins += 1
            cash += revenue
            trades += 1
            total_traded_notional += float(revenue)
            if buy_index >= 0:
                holding_periods.append(max(1, int(i + 1 - buy_index)))
            if return_trades:
                trade_time = ""
                if klines is not None and i + 1 < len(klines):
                    row = klines[i + 1]
                    trade_time = str(row.get("date", row.get("trade_date", row.get("time", ""))))
                trades_detail.append(
                    {
                        "index": int(i + 1),
                        "time": trade_time,
                        "price": float(sell_price),
                        "signal": -1,
                        "shares": int(shares),
                        "profit": float(profit),
                        "holding_days": max(1, int(i + 1 - buy_index)) if buy_index >= 0 else 0,
                    }
                )
            shares = 0
            buy_index = -1

        equity[i] = cash + shares * closes[i]
    equity[n - 1] = cash + shares * float(closes[n - 1])

    if shares > 0:
        i = n - 1
        exec_price = float(closes[i])
        if slippage_calc is not None:
            slip = slippage_calc.calculate(
                price=exec_price,
                volume=float(volumes[i]) if i < len(volumes) else 0.0,
                order_size=float(shares),
                is_buy=False,
            )
            exec_price = float(slip.get("execution_price", exec_price))
        sell_price = exec_price * (1 - commission_rate - per_side_extra_cost_rate - sell_tax_rate)
        sell_price = max(0.0, sell_price)
        revenue = shares * sell_price
        profit = revenue - (shares * buy_price)
        if profit > 0:
            wins += 1
        cash += revenue
        trades += 1
        total_traded_notional += float(revenue)
        if buy_index >= 0:
            holding_periods.append(max(1, int(i - buy_index)))
        if return_trades:
            trade_time = ""
            if klines is not None and i < len(klines):
                row = klines[i]
                trade_time = str(row.get("date", row.get("trade_date", row.get("time", ""))))
            trades_detail.append(
                {
                    "index": int(i),
                    "time": trade_time,
                    "price": float(sell_price),
                    "signal": -1,
                    "shares": int(shares),
                    "profit": float(profit),
                    "holding_days": max(1, int(i - buy_index)) if buy_index >= 0 else 0,
                }
            )
        shares = 0
        buy_index = -1

    final_capital = float(cash)
    total_return = (final_capital - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    max_dd = 0.0
    peak = float(equity[0]) if len(equity) else float(initial_capital)
    for val in equity:
        if val > peak:
            peak = float(val)
        if peak > 0:
            dd = (peak - float(val)) / peak
            if dd > max_dd:
                max_dd = dd

    sharpe = 0.0
    if len(equity) > 1:
        eq_prev = equity[:-1]
        eq_next = equity[1:]
        valid = eq_prev > 0
        if np.any(valid):
            rets = (eq_next[valid] - eq_prev[valid]) / eq_prev[valid]
            if len(rets) > 1:
                std = float(np.std(rets))
                if std > 0:
                    annual_ret = float(np.mean(rets)) * 252.0
                    annual_std = std * np.sqrt(252.0)
                    risk_free_rate = 0.02  # 年化无风险利率
                    sharpe = float((annual_ret - risk_free_rate) / annual_std)

    win_rate = wins / max(1, trades // 2) if trades > 0 else 0.0  # round-trip = trades//2
    avg_holding_days = float(np.mean(holding_periods)) if holding_periods else 0.0
    turnover_proxy = (total_traded_notional / initial_capital) if initial_capital > 0 else 0.0
    return {
        "final_capital": final_capital,
        "total_return": float(total_return),
        "max_drawdown": float(max_dd),
        "sharpe_ratio": float(sharpe),
        "trades_count": int(trades),
        "win_rate": float(win_rate),
        "avg_holding_days": float(avg_holding_days),
        "turnover_proxy": float(turnover_proxy),
        "equity": equity,
        "trades": trades_detail if return_trades else None,
    }
