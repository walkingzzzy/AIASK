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

from ._engine_support import (
    _build_strategy_masks,
    _build_tradability_mask,
    _finalize_backtest_payload,
    _simulate_trades_from_masks,
)

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
                masks = _build_strategy_masks(strategy, closes, params, volumes=volumes)
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
                    'avg_holding_days': float(sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(sim.get('turnover_proxy') or 0.0),
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
                _finalize_backtest_payload(payload, sim['equity'], params=params, closes=closes, volumes=volumes)
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

                data = {
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
                _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': data}

            result = _backtest_ma_cross_jit(
                closes, short_period, long_period, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            data = {
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
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': data}

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
                'avg_holding_days': float(max(1, exit_idx - entry_idx)),
                'turnover_proxy': float(((shares * buy_price) + (shares * exit_price)) / initial_capital) if initial_capital > 0 else 0.0,
            }
            if tradability_mask is not None:
                data['tradability_filter'] = True
                data['entry_index'] = entry_idx
                data['exit_index'] = exit_idx
            if slippage_calc is not None:
                data['slippage_model'] = str(slippage_model_raw).strip().lower()
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {
                'success': True,
                'data': data
            }

        elif strategy == 'momentum':
            lookback = params.get('lookback', 20)
            threshold = params.get('threshold', 0.02)
            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params, volumes=volumes)
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
                    'avg_holding_days': float(sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(sim.get('turnover_proxy') or 0.0),
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
                _finalize_backtest_payload(payload, sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': payload}

            result = _backtest_momentum_jit(
                closes, lookback, threshold, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            data = {
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
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': data}

        elif strategy == 'rsi':
            rsi_period = params.get('rsi_period', 14)
            oversold = params.get('oversold', 30)
            overbought = params.get('overbought', 70)
            if advanced_exec_enabled:
                masks = _build_strategy_masks(strategy, closes, params, volumes=volumes)
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
                    'avg_holding_days': float(sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(sim.get('turnover_proxy') or 0.0),
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
                _finalize_backtest_payload(payload, sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': payload}

            result = _backtest_rsi_jit(
                closes, rsi_period, oversold, overbought, initial_capital, total_cost_rate
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            data = {
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
            _finalize_backtest_payload(data, equity, params=params, closes=closes, volumes=volumes)
            return {'success': True, 'data': data}

        # Generic registry fallback for custom/factory strategies
        from .strategy_registry import StrategyRegistry as _Reg
        _klass = _Reg.get(strategy)
        if _klass is not None:
            _inst = _klass()
            _inst.set_parameters(params)
            if hasattr(_inst, 'generate_entry_exit_masks_from_klines'):
                _masks = _inst.generate_entry_exit_masks_from_klines(klines)
            else:
                _masks = _inst.generate_entry_exit_masks(closes, volumes)
            if _masks is not None and _masks[0] is not None:
                _entry, _exit = _masks
                _sim = _simulate_trades_from_masks(
                    closes=closes, volumes=volumes,
                    entry_mask=_entry, exit_mask=_exit,
                    initial_capital=initial_capital,
                    commission_rate=commission,
                    slippage_calc=slippage_calc,
                    tradability_mask=tradability_mask,
                    return_trades=return_trades,
                    klines=klines,
                )
                _payload = {
                    'code': code, 'strategy': strategy,
                    'initial_capital': initial_capital,
                    'final_capital': float(_sim['final_capital']),
                    'total_return': float(_sim['total_return']),
                    'max_drawdown': float(_sim['max_drawdown']),
                    'sharpe_ratio': float(_sim['sharpe_ratio']),
                    'trades_count': int(_sim['trades_count']),
                    'win_rate': float(_sim['win_rate']),
                    'avg_holding_days': float(_sim.get('avg_holding_days') or 0.0),
                    'turnover_proxy': float(_sim.get('turnover_proxy') or 0.0),
                    'params': params,
                }
                if return_trades:
                    _payload['trades'] = _sim.get('trades') or []
                _finalize_backtest_payload(_payload, _sim['equity'], params=params, closes=closes, volumes=volumes)
                return {'success': True, 'data': _payload}

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
        runs: int = 1000,
        bootstrap_method: str = 'normal',
    ) -> Dict[str, Any]:
        """蒙特卡洛模拟

        Args:
            bootstrap_method: 'normal' (正态分布) 或 'block' (Block Bootstrap，保留序列自相关)
        """
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        klines = _ensure_dict_list(klines)
        params = params or {}
        closes = np.array([k['close'] for k in klines])

        returns = np.diff(closes) / closes[:-1]
        mean_return = np.mean(returns)
        std_return = np.std(returns)

        # Block Bootstrap 参数
        block_size = max(5, int(params.get('block_size', 20)))

        final_capitals = []
        max_drawdowns = []

        for _ in range(runs):
            if bootstrap_method == 'block' and len(returns) >= block_size:
                # Block Bootstrap: 随机抽取连续块拼接，保留序列自相关
                n_blocks = max(1, len(returns) // block_size + 1)
                sim_parts = []
                for _ in range(n_blocks):
                    start = np.random.randint(0, max(1, len(returns) - block_size + 1))
                    sim_parts.append(returns[start:start + block_size])
                simulated_returns = np.concatenate(sim_parts)[:len(returns)]
            else:
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
                'bootstrap_method': bootstrap_method,
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
