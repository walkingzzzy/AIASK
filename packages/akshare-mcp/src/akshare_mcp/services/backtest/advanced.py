"""高级回测引擎 - 动态止损、仓位管理、多策略组合"""

from typing import List, Dict, Any, Optional
import numpy as np

from .utils import _compute_slippage_rate
from .engine import backtest_engine


class AdvancedBacktestEngine:
    """高级回测引擎 - 动态止损、仓位管理、多策略组合"""

    @staticmethod
    def backtest_with_dynamic_stops(
        code: str,
        klines: List[Dict[str, Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        stop_loss: float = 0.05,
        take_profit: float = 0.10,
        trailing_stop: float = 0.03
    ) -> Dict[str, Any]:
        """带动态止损的回测"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        params = params or {}
        initial_capital = params.get('initial_capital', 100000)
        commission = params.get('commission', 0.0003)

        closes = np.array([k['close'] for k in klines])
        volumes = np.array([k.get('volume', 0.0) for k in klines])

        slippage_rate = _compute_slippage_rate(closes, volumes, params, 0.0)
        total_cost_rate = commission + slippage_rate

        base_result = backtest_engine.run_backtest(code, klines, strategy, params)
        if not base_result['success']:
            return base_result

        cash = initial_capital
        shares = 0
        buy_price = 0.0
        highest_price = 0.0
        trades = 0
        wins = 0
        equity = []

        for close in closes:
            if shares > 0:
                if close > highest_price:
                    highest_price = close
                if close <= buy_price * (1 - stop_loss):
                    sell_price = close * (1 - total_cost_rate)
                    cash += shares * sell_price
                    if sell_price > buy_price:
                        wins += 1
                    shares = 0
                    trades += 1
                elif close >= buy_price * (1 + take_profit):
                    sell_price = close * (1 - total_cost_rate)
                    cash += shares * sell_price
                    wins += 1
                    shares = 0
                    trades += 1
                elif close <= highest_price * (1 - trailing_stop):
                    sell_price = close * (1 - total_cost_rate)
                    cash += shares * sell_price
                    if sell_price > buy_price:
                        wins += 1
                    shares = 0
                    trades += 1
            equity.append(cash + shares * close)

        if shares > 0:
            cash += shares * closes[-1] * (1 - total_cost_rate)
            shares = 0

        final_capital = cash
        total_return = (final_capital - initial_capital) / initial_capital

        equity = np.array(equity)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_dd = float(np.max(drawdown))

        return {
            'success': True,
            'data': {
                'code': code,
                'strategy': f'{strategy}_dynamic_stops',
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': max_dd,
                'trades_count': trades,
                'win_rate': wins / trades if trades > 0 else 0.0,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'trailing_stop': trailing_stop,
            }
        }

    @staticmethod
    def backtest_with_position_sizing(
        code: str,
        klines: List[Dict[str, Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        sizing_method: str = 'fixed',
        risk_per_trade: float = 0.02
    ) -> Dict[str, Any]:
        """带仓位管理的回测"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        params = params or {}
        initial_capital = params.get('initial_capital', 100000)

        result = backtest_engine.run_backtest(code, klines, strategy, params)
        if not result['success']:
            return result

        if sizing_method == 'fixed':
            position_size = 1.0
        elif sizing_method == 'kelly':
            win_rate = result['data'].get('win_rate', 0.5)
            avg_win = 0.05
            avg_loss = 0.03
            kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
            position_size = max(0.1, min(kelly, 1.0))
        elif sizing_method == 'volatility':
            closes = np.array([k['close'] for k in klines])
            returns = np.diff(closes) / closes[:-1]
            volatility = np.std(returns)
            position_size = risk_per_trade / volatility if volatility > 0 else 0.5
        else:
            position_size = 1.0

        adjusted_return = result['data']['total_return'] * position_size
        adjusted_capital = initial_capital * (1 + adjusted_return)

        return {
            'success': True,
            'data': {
                **result['data'],
                'sizing_method': sizing_method,
                'position_size': float(position_size),
                'adjusted_capital': float(adjusted_capital),
                'adjusted_return': float(adjusted_return),
            }
        }

    @staticmethod
    def multi_strategy_backtest(
        code: str,
        klines: List[Dict[str, Any]],
        strategies: List[Dict[str, Any]],
        allocation: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """多策略组合回测"""
        if not klines or not strategies:
            return {'success': False, 'error': 'Invalid input'}

        n_strategies = len(strategies)
        if allocation is None:
            allocation = [1.0 / n_strategies] * n_strategies
        if len(allocation) != n_strategies:
            return {'success': False, 'error': 'Allocation length mismatch'}

        results = []
        total_return = 0.0

        for i, strategy_config in enumerate(strategies):
            strategy_name = strategy_config['name']
            strategy_params = strategy_config.get('params', {})
            result = backtest_engine.run_backtest(code, klines, strategy_name, strategy_params)

            if result['success']:
                strategy_return = result['data']['total_return']
                weighted_return = strategy_return * allocation[i]
                total_return += weighted_return
                results.append({
                    'strategy': strategy_name,
                    'allocation': allocation[i],
                    'return': strategy_return,
                    'weighted_return': weighted_return,
                })

        return {
            'success': True,
            'data': {
                'code': code,
                'strategies': results,
                'total_return': float(total_return),
                'n_strategies': n_strategies,
            }
        }


advanced_backtest_engine = AdvancedBacktestEngine()
