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
) -> Dict[str, Any]:
    """按 entry/exit 掩码执行交易仿真，支持逐笔滑点与可交易过滤。"""
    n = len(closes)
    cash = float(initial_capital)
    shares = 0
    buy_price = 0.0
    trades = 0
    wins = 0
    equity = np.full(n, float(initial_capital), dtype=np.float64)
    trades_detail: List[Dict[str, Any]] = []

    for i in range(n):
        tradable = True if tradability_mask is None else bool(tradability_mask[i])
        if entry_mask[i] and shares == 0 and cash > 0 and tradable:
            exec_price = float(closes[i])
            if slippage_calc is not None:
                approx_price = exec_price * (1 + commission_rate)
                est_shares = int(cash / approx_price) if approx_price > 0 else 0
                if est_shares <= 0:
                    equity[i] = cash
                    continue
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes[i]) if i < len(volumes) else 0.0,
                    order_size=float(est_shares),
                    is_buy=True,
                )
                exec_price = float(slip.get("execution_price", exec_price))

            buy_price = exec_price * (1 + commission_rate)
            max_shares = int(cash / buy_price) if buy_price > 0 else 0
            if max_shares > 0:
                shares = max_shares
                cash -= shares * buy_price
                trades += 1
                if return_trades:
                    trade_time = ""
                    if klines is not None and i < len(klines):
                        row = klines[i]
                        trade_time = str(row.get("date", row.get("trade_date", row.get("time", ""))))
                    trades_detail.append(
                        {
                            "index": int(i),
                            "time": trade_time,
                            "price": float(buy_price),
                            "signal": 1,
                            "shares": int(shares),
                            "profit": 0.0,
                        }
                    )

        elif exit_mask[i] and shares > 0 and tradable:
            exec_price = float(closes[i])
            if slippage_calc is not None:
                slip = slippage_calc.calculate(
                    price=exec_price,
                    volume=float(volumes[i]) if i < len(volumes) else 0.0,
                    order_size=float(shares),
                    is_buy=False,
                )
                exec_price = float(slip.get("execution_price", exec_price))

            sell_price = exec_price * (1 - commission_rate)
            revenue = shares * sell_price
            profit = revenue - (shares * buy_price)
            if profit > 0:
                wins += 1
            cash += revenue
            trades += 1
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
                    }
                )
            shares = 0

        equity[i] = cash + shares * closes[i]

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
        sell_price = exec_price * (1 - commission_rate)
        revenue = shares * sell_price
        profit = revenue - (shares * buy_price)
        if profit > 0:
            wins += 1
        cash += revenue
        trades += 1
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
                }
            )
        shares = 0

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
                    sharpe = float((np.mean(rets) * 252.0) / (std * np.sqrt(252.0)))

    win_rate = wins / trades if trades > 0 else 0.0
    return {
        "final_capital": final_capital,
        "total_return": float(total_return),
        "max_drawdown": float(max_dd),
        "sharpe_ratio": float(sharpe),
        "trades_count": int(trades),
        "win_rate": float(win_rate),
        "equity": equity,
        "trades": trades_detail if return_trades else None,
    }


class BacktestEngine:
    """回测引擎"""

    @staticmethod
    def run_backtest(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        return_trades: bool = False
    ) -> Dict[str, Any]:
        """运行回测"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        params = params or {}
        initial_capital = float(params.get("initial_capital", 100000) or 100000)
        commission = float(params.get("commission", 0.0003) or 0.0)

        closes = np.array([k['close'] for k in klines])
        volumes = np.array([k.get('volume', 0.0) for k in klines])

        # 兼容两种成本口径：
        # 1) 显式 slippage（费率）参数
        # 2) slippage_model 推导费率（旧口径）
        explicit_slippage = float(params.get("slippage", 0.0) or 0.0)
        model_slippage_rate = _compute_slippage_rate(closes, volumes, params, 0.0)
        slippage_rate = explicit_slippage if explicit_slippage > 0 else model_slippage_rate
        total_cost_rate = max(0.0, commission + slippage_rate)

        slippage_model_raw = params.get("slippage_model")
        slippage_calc: Optional[SlippageCalculator] = None
        if slippage_model_raw:
            normalized = str(slippage_model_raw).strip().lower()
            if normalized in {"fixed", "volume_based", "market_impact"}:
                slippage_calc = SlippageCalculator(
                    model_type=_resolve_slippage_model(normalized)
                )

        tradability_mask: Optional[np.ndarray] = None
        if bool(params.get("tradability_filter", False)):
            tradability_mask = _build_tradability_mask(
                closes=closes,
                volumes=volumes,
                code=code,
                is_st=bool(params.get("is_st", False)),
            )

        advanced_exec_enabled = (slippage_calc is not None) or (tradability_mask is not None)

        if strategy == 'ma_cross':
            short_period = params.get('short_period', 5)
            long_period = params.get('long_period', 20)

            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params)
                if masks is None:
                    return {'success': False, 'error': 'Insufficient data for strategy signals'}
                entry_mask, exit_mask = masks
                sim = _simulate_trades_from_masks(
                    closes=closes,
                    volumes=volumes,
                    entry_mask=entry_mask,
                    exit_mask=exit_mask,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                )
                payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(sim['final_capital']),
                    'total_return': float(sim['total_return']),
                    'max_drawdown': float(sim['max_drawdown']),
                    'sharpe_ratio': float(sim['sharpe_ratio']),
                    'trades_count': int(sim['trades_count']),
                    'win_rate': float(sim['win_rate']),
                    'params': params,
                }
                if return_trades:
                    payload['trades'] = sim.get('trades') or []
                if slippage_calc is not None:
                    payload['slippage_model'] = str(slippage_model_raw).strip().lower()
                if tradability_mask is not None:
                    payload['tradability_filter'] = True
                    payload['tradable_days'] = int(np.sum(tradability_mask))
                    payload['total_days'] = int(len(tradability_mask))
                return {'success': True, 'data': payload}

            if return_trades:
                result = _backtest_ma_cross_with_trades_jit(
                    closes, short_period, long_period, initial_capital, total_cost_rate
                )
                (final_capital, total_return, max_dd, sharpe, total_trades, win_rate, equity,
                 trade_count, trade_indices, trade_types, trade_prices, trade_shares, trade_profits) = result

                trades_detail = []
                for i in range(trade_count):
                    idx = int(trade_indices[i])
                    trades_detail.append({
                        'index': idx,
                        'time': klines[idx].get('date', klines[idx].get('trade_date', '')),
                        'price': float(trade_prices[i]),
                        'signal': int(trade_types[i]),
                        'shares': int(trade_shares[i]),
                        'profit': float(trade_profits[i])
                    })

                return {
                    'success': True,
                    'data': {
                        'code': code, 'strategy': strategy,
                        'initial_capital': initial_capital,
                        'final_capital': float(final_capital),
                        'total_return': float(total_return),
                        'max_drawdown': float(max_dd),
                        'sharpe_ratio': float(sharpe),
                        'trades_count': int(total_trades),
                        'win_rate': float(win_rate),
                        'params': params,
                        'trades': trades_detail
                    }
                }

            result = _backtest_ma_cross_jit(
                closes, short_period, long_period, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            return {
                'success': True,
                'data': {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(final_capital),
                    'total_return': float(total_return),
                    'max_drawdown': float(max_dd),
                    'sharpe_ratio': float(sharpe),
                    'trades_count': int(trades),
                    'win_rate': float(win_rate),
                    'params': params,
                }
            }

        elif strategy == 'buy_and_hold':
            entry_idx = 0
            exit_idx = len(closes) - 1
            if tradability_mask is not None:
                tradable_idx = np.where(tradability_mask)[0]
                if len(tradable_idx) < 2:
                    return {'success': False, 'error': 'No enough tradable days for buy_and_hold'}
                entry_idx = int(tradable_idx[0])
                exit_idx = int(tradable_idx[-1])

            entry_price = float(closes[entry_idx])
            exit_price = float(closes[exit_idx])
            if slippage_calc is not None:
                buy_slip = slippage_calc.calculate(
                    price=entry_price,
                    volume=float(volumes[entry_idx]) if entry_idx < len(volumes) else 0.0,
                    order_size=float(initial_capital / max(entry_price, 1e-8)),
                    is_buy=True,
                )
                entry_price = float(buy_slip.get("execution_price", entry_price))
                sell_slip = slippage_calc.calculate(
                    price=exit_price,
                    volume=float(volumes[exit_idx]) if exit_idx < len(volumes) else 0.0,
                    order_size=float(initial_capital / max(entry_price, 1e-8)),
                    is_buy=False,
                )
                exit_price = float(sell_slip.get("execution_price", exit_price))

            buy_price = entry_price * (1 + total_cost_rate)
            shares = initial_capital / buy_price if buy_price > 0 else 0.0
            final_capital = shares * exit_price * (1 - total_cost_rate)
            total_return = (final_capital - initial_capital) / initial_capital

            equity = shares * closes
            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak
            max_dd = float(np.max(drawdown))

            data = {
                'code': code, 'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': max_dd,
                'sharpe_ratio': 0.0,
                'trades_count': 1,
                'win_rate': 1.0 if total_return > 0 else 0.0,
            }
            if tradability_mask is not None:
                data['tradability_filter'] = True
                data['entry_index'] = entry_idx
                data['exit_index'] = exit_idx
            if slippage_calc is not None:
                data['slippage_model'] = str(slippage_model_raw).strip().lower()
            return {
                'success': True,
                'data': data
            }

        elif strategy == 'momentum':
            lookback = params.get('lookback', 20)
            threshold = params.get('threshold', 0.02)
            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params)
                if masks is None:
                    return {'success': False, 'error': 'Insufficient data for strategy signals'}
                entry_mask, exit_mask = masks
                sim = _simulate_trades_from_masks(
                    closes=closes,
                    volumes=volumes,
                    entry_mask=entry_mask,
                    exit_mask=exit_mask,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                )
                payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(sim['final_capital']),
                    'total_return': float(sim['total_return']),
                    'max_drawdown': float(sim['max_drawdown']),
                    'sharpe_ratio': float(sim['sharpe_ratio']),
                    'trades_count': int(sim['trades_count']),
                    'win_rate': float(sim['win_rate']),
                    'params': params,
                }
                if return_trades:
                    payload['trades'] = sim.get('trades') or []
                if slippage_calc is not None:
                    payload['slippage_model'] = str(slippage_model_raw).strip().lower()
                if tradability_mask is not None:
                    payload['tradability_filter'] = True
                    payload['tradable_days'] = int(np.sum(tradability_mask))
                    payload['total_days'] = int(len(tradability_mask))
                return {'success': True, 'data': payload}

            result = _backtest_momentum_jit(
                closes, lookback, threshold, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            return {
                'success': True,
                'data': {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(final_capital),
                    'total_return': float(total_return),
                    'max_drawdown': float(max_dd),
                    'sharpe_ratio': float(sharpe),
                    'trades_count': int(trades),
                    'win_rate': float(win_rate),
                    'params': params,
                }
            }

        elif strategy == 'rsi':
            rsi_period = params.get('rsi_period', 14)
            oversold = params.get('oversold', 30)
            overbought = params.get('overbought', 70)
            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params)
                if masks is None:
                    return {'success': False, 'error': 'Insufficient data for strategy signals'}
                entry_mask, exit_mask = masks
                sim = _simulate_trades_from_masks(
                    closes=closes,
                    volumes=volumes,
                    entry_mask=entry_mask,
                    exit_mask=exit_mask,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                )
                payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(sim['final_capital']),
                    'total_return': float(sim['total_return']),
                    'max_drawdown': float(sim['max_drawdown']),
                    'sharpe_ratio': float(sim['sharpe_ratio']),
                    'trades_count': int(sim['trades_count']),
                    'win_rate': float(sim['win_rate']),
                    'params': params,
                }
                if return_trades:
                    payload['trades'] = sim.get('trades') or []
                if slippage_calc is not None:
                    payload['slippage_model'] = str(slippage_model_raw).strip().lower()
                if tradability_mask is not None:
                    payload['tradability_filter'] = True
                    payload['tradable_days'] = int(np.sum(tradability_mask))
                    payload['total_days'] = int(len(tradability_mask))
                return {'success': True, 'data': payload}

            result = _backtest_rsi_jit(
                closes, rsi_period, oversold, overbought, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            return {
                'success': True,
                'data': {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(final_capital),
                    'total_return': float(total_return),
                    'max_drawdown': float(max_dd),
                    'sharpe_ratio': float(sharpe),
                    'trades_count': int(trades),
                    'win_rate': float(win_rate),
                    'params': params,
                }
            }

        return {'success': False, 'error': f'Unknown strategy: {strategy}'}

    @staticmethod
    def optimize_parameters(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        param_ranges: Optional[Dict[str, List]] = None
    ) -> Dict[str, Any]:
        """参数优化（网格搜索）"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        param_ranges = param_ranges or {}

        if strategy == 'ma_cross':
            short_periods = param_ranges.get('short_period', [5, 10, 15])
            long_periods = param_ranges.get('long_period', [20, 30, 40])

            best_params = None
            best_metric = -float('inf')
            all_results = []

            for short in short_periods:
                for long in long_periods:
                    if short >= long:
                        continue
                    params = {
                        'initial_capital': 100000, 'commission': 0.0003,
                        'short_period': short, 'long_period': long,
                    }
                    result = BacktestEngine.run_backtest(code, klines, strategy, params)
                    if result['success']:
                        data = result['data']
                        metric = data['sharpe_ratio'] * (1 - data['max_drawdown'])
                        all_results.append({
                            'params': params, 'metric': metric,
                            'total_return': data['total_return'],
                            'sharpe_ratio': data['sharpe_ratio'],
                            'max_drawdown': data['max_drawdown'],
                        })
                        if metric > best_metric:
                            best_metric = metric
                            best_params = params

            return {
                'success': True,
                'data': {
                    'best_params': best_params,
                    'best_metric': best_metric,
                    'all_results': all_results,
                }
            }

        return {'success': False, 'error': f'Parameter optimization not supported for strategy: {strategy}'}

    @staticmethod
    def monte_carlo_simulation(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        runs: int = 1000
    ) -> Dict[str, Any]:
        """蒙特卡洛模拟"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        params = params or {}
        closes = np.array([k['close'] for k in klines])

        returns = np.diff(closes) / closes[:-1]
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        final_capitals = []
        max_drawdowns = []

        for _ in range(runs):
            simulated_returns = np.random.normal(mean_return, std_return, len(returns))
            simulated_closes = closes[0] * np.cumprod(1 + simulated_returns)
            simulated_closes = np.insert(simulated_closes, 0, closes[0])

            simulated_klines = [
                {'close': float(c), 'date': klines[i]['date']}
                for i, c in enumerate(simulated_closes)
            ]

            result = BacktestEngine.run_backtest(code, simulated_klines, strategy, params)
            if result['success']:
                final_capitals.append(result['data']['final_capital'])
                max_drawdowns.append(result['data']['max_drawdown'])

        if not final_capitals:
            return {'success': False, 'error': 'Simulation failed'}

        final_capitals = np.array(final_capitals)
        max_drawdowns = np.array(max_drawdowns)

        return {
            'success': True,
            'data': {
                'runs': runs,
                'best_case': float(np.max(final_capitals)),
                'worst_case': float(np.min(final_capitals)),
                'average': float(np.mean(final_capitals)),
                'median': float(np.median(final_capitals)),
                'confidence_95': float(np.percentile(final_capitals, 5)),
                'avg_drawdown': float(np.mean(max_drawdowns)),
                'max_drawdown': float(np.max(max_drawdowns)),
            }
        }

    @staticmethod
    def walk_forward_analysis(
        code: str,
        klines: List[Union[Dict[str, Any], Any]],
        strategy: str = 'ma_cross',
        param_ranges: Optional[Dict[str, List]] = None,
        train_window: int = 250,
        test_window: int = 60
    ) -> Dict[str, Any]:
        """Walk-Forward分析"""
        klines = _ensure_dict_list(klines)

        if len(klines) < train_window + test_window:
            return {'success': False, 'error': 'Insufficient data for walk-forward analysis'}

        segments = []
        capital = 100000

        i = 0
        while i + train_window + test_window <= len(klines):
            train_klines = klines[i:i+train_window]
            opt_result = BacktestEngine.optimize_parameters(
                code, train_klines, strategy, param_ranges
            )
            if not opt_result['success']:
                break

            best_params = opt_result['data']['best_params']
            test_klines = klines[i+train_window:i+train_window+test_window]
            test_result = BacktestEngine.run_backtest(code, test_klines, strategy, best_params)

            if test_result['success']:
                data = test_result['data']
                segments.append({
                    'period': f"{test_klines[0]['date']} to {test_klines[-1]['date']}",
                    'params': best_params,
                    'return': data['total_return'],
                    'sharpe': data['sharpe_ratio'],
                    'max_drawdown': data['max_drawdown'],
                })
                capital *= (1 + data['total_return'])

            i += test_window

        if not segments:
            return {'success': False, 'error': 'Walk-forward analysis failed'}

        overall_return = (capital - 100000) / 100000

        return {
            'success': True,
            'data': {
                'segments': segments,
                'overall_return': overall_return,
                'final_capital': capital,
            }
        }


backtest_engine = BacktestEngine()
