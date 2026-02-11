"""JIT优化的回测策略函数"""

import numpy as np
from numba import jit


@jit(nopython=True)
def _backtest_ma_cross_jit(
    closes: np.ndarray,
    short_period: int,
    long_period: int,
    initial_capital: float,
    total_cost_rate: float
) -> tuple:
    """Numba优化的均线交叉回测核心"""
    n = len(closes)

    short_ma = np.zeros(n)
    long_ma = np.zeros(n)

    for i in range(short_period - 1, n):
        short_ma[i] = np.mean(closes[i-short_period+1:i+1])

    for i in range(long_period - 1, n):
        long_ma[i] = np.mean(closes[i-long_period+1:i+1])

    cash = initial_capital
    shares = 0
    equity = np.zeros(n)
    trades = 0
    wins = 0

    for i in range(long_period, n):
        if short_ma[i-1] <= long_ma[i-1] and short_ma[i] > long_ma[i] and cash > 0:
            buy_price = closes[i] * (1 + total_cost_rate)
            shares = int(cash / buy_price)
            cash -= shares * buy_price
            trades += 1
        elif short_ma[i-1] >= long_ma[i-1] and short_ma[i] < long_ma[i] and shares > 0:
            sell_price = closes[i] * (1 - total_cost_rate)
            profit = shares * sell_price - shares * closes[i-1]
            if profit > 0:
                wins += 1
            cash += shares * sell_price
            shares = 0

        equity[i] = cash + shares * closes[i]

    if shares > 0:
        cash += shares * closes[-1] * (1 - total_cost_rate)
        shares = 0

    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital

    max_dd = 0.0
    peak = equity[long_period]
    for i in range(long_period, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    returns = np.diff(equity[long_period:]) / equity[long_period:-1]
    returns = returns[returns != 0]
    sharpe = 0.0
    if len(returns) > 0:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return > 0:
            sharpe = (mean_return * 252) / (std_return * np.sqrt(252))

    win_rate = wins / trades if trades > 0 else 0.0

    return final_capital, total_return, max_dd, sharpe, trades, win_rate, equity


@jit(nopython=True)
def _backtest_ma_cross_with_trades_jit(
    closes: np.ndarray,
    short_period: int,
    long_period: int,
    initial_capital: float,
    total_cost_rate: float,
    max_trades: int = 1000
) -> tuple:
    """带交易记录的均线交叉回测 (Numba JIT 优化版本)"""
    n = len(closes)

    trade_indices = np.zeros(max_trades, dtype=np.int64)
    trade_types = np.zeros(max_trades, dtype=np.int64)
    trade_prices = np.zeros(max_trades, dtype=np.float64)
    trade_shares = np.zeros(max_trades, dtype=np.int64)
    trade_profits = np.zeros(max_trades, dtype=np.float64)
    trade_count = 0

    short_ma = np.zeros(n, dtype=np.float64)
    long_ma = np.zeros(n, dtype=np.float64)

    for i in range(short_period - 1, n):
        short_ma[i] = np.mean(closes[i-short_period+1:i+1])

    for i in range(long_period - 1, n):
        long_ma[i] = np.mean(closes[i-long_period+1:i+1])

    cash = initial_capital
    shares = 0
    buy_price = 0.0
    equity = np.zeros(n, dtype=np.float64)
    wins = 0

    for i in range(long_period, n):
        if short_ma[i-1] <= long_ma[i-1] and short_ma[i] > long_ma[i] and cash > 0:
            buy_price = closes[i] * (1 + total_cost_rate)
            buy_shares = int(cash / buy_price)
            if buy_shares > 0:
                cost = buy_shares * buy_price
                cash -= cost
                shares = buy_shares
                if trade_count < max_trades:
                    trade_indices[trade_count] = i
                    trade_types[trade_count] = 1
                    trade_prices[trade_count] = buy_price
                    trade_shares[trade_count] = buy_shares
                    trade_profits[trade_count] = 0.0
                    trade_count += 1

        elif short_ma[i-1] >= long_ma[i-1] and short_ma[i] < long_ma[i] and shares > 0:
            sell_price = closes[i] * (1 - total_cost_rate)
            revenue = shares * sell_price
            profit = revenue - shares * buy_price
            if profit > 0:
                wins += 1
            if trade_count < max_trades:
                trade_indices[trade_count] = i
                trade_types[trade_count] = -1
                trade_prices[trade_count] = sell_price
                trade_shares[trade_count] = shares
                trade_profits[trade_count] = profit
                trade_count += 1
            cash += revenue
            shares = 0

        equity[i] = cash + shares * closes[i]

    if shares > 0:
        sell_price = closes[-1] * (1 - total_cost_rate)
        revenue = shares * sell_price
        profit = revenue - shares * buy_price
        if trade_count < max_trades:
            trade_indices[trade_count] = n - 1
            trade_types[trade_count] = -1
            trade_prices[trade_count] = sell_price
            trade_shares[trade_count] = shares
            trade_profits[trade_count] = profit
            trade_count += 1
        cash += revenue
        shares = 0

    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital

    max_dd = 0.0
    peak = equity[long_period]
    for i in range(long_period, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    returns = np.diff(equity[long_period:]) / equity[long_period:-1]
    returns = returns[returns != 0]
    sharpe = 0.0
    if len(returns) > 0:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return > 0:
            sharpe = (mean_return * 252) / (std_return * np.sqrt(252))

    total_trades = trade_count
    win_rate = wins / (trade_count // 2) if trade_count > 0 else 0.0

    return (
        final_capital, total_return, max_dd, sharpe, total_trades, win_rate, equity,
        trade_count, trade_indices[:trade_count], trade_types[:trade_count],
        trade_prices[:trade_count], trade_shares[:trade_count], trade_profits[:trade_count]
    )



@jit(nopython=True)
def _backtest_momentum_jit(
    closes: np.ndarray,
    lookback: int,
    threshold: float,
    initial_capital: float,
    total_cost_rate: float
) -> tuple:
    """Numba优化的动量策略回测"""
    n = len(closes)
    cash = initial_capital
    shares = 0
    equity = np.full(n, initial_capital)
    trades = 0
    wins = 0

    for i in range(lookback, n):
        momentum = (closes[i] - closes[i-lookback]) / closes[i-lookback]

        if momentum > threshold and shares == 0:
            buy_price = closes[i] * (1 + total_cost_rate)
            max_shares = int(cash / buy_price)
            if max_shares > 0:
                cost = max_shares * buy_price
                shares = max_shares
                cash -= cost
                trades += 1

        elif momentum < -threshold and shares > 0:
            sell_price = closes[i] * (1 - total_cost_rate)
            revenue = shares * sell_price
            profit = revenue - (shares * buy_price)
            if profit > 0:
                wins += 1
            cash += revenue
            shares = 0
            trades += 1

        equity[i] = cash + shares * closes[i]

    if shares > 0:
        sell_price = closes[-1] * (1 - total_cost_rate)
        revenue = shares * sell_price
        cash += revenue
        shares = 0
        trades += 1

    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital

    max_dd = 0.0
    peak = equity[lookback]
    for i in range(lookback, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    returns = np.diff(equity[lookback:]) / equity[lookback:-1]
    returns = returns[returns != 0]
    sharpe = 0.0
    if len(returns) > 0:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return > 0:
            sharpe = (mean_return * 252) / (std_return * np.sqrt(252))

    win_rate = wins / trades if trades > 0 else 0.0

    return final_capital, total_return, max_dd, sharpe, trades, win_rate, equity


@jit(nopython=True)
def _backtest_rsi_jit(
    closes: np.ndarray,
    rsi_period: int,
    oversold: float,
    overbought: float,
    initial_capital: float,
    total_cost_rate: float
) -> tuple:
    """Numba优化的RSI策略回测"""
    n = len(closes)

    rsi = np.zeros(n)
    for i in range(rsi_period, n):
        gains = 0.0
        losses = 0.0
        for j in range(i - rsi_period + 1, i + 1):
            change = closes[j] - closes[j-1]
            if change > 0:
                gains += change
            else:
                losses -= change

        avg_gain = gains / rsi_period
        avg_loss = losses / rsi_period

        if avg_loss == 0:
            rsi[i] = 100
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))

    cash = initial_capital
    shares = 0
    equity = np.full(n, initial_capital)
    trades = 0
    wins = 0
    buy_price = 0.0

    for i in range(rsi_period, n):
        if rsi[i] < oversold and shares == 0:
            buy_price = closes[i] * (1 + total_cost_rate)
            max_shares = int(cash / buy_price)
            if max_shares > 0:
                cost = max_shares * buy_price
                shares = max_shares
                cash -= cost
                trades += 1

        elif rsi[i] > overbought and shares > 0:
            sell_price = closes[i] * (1 - total_cost_rate)
            revenue = shares * sell_price
            profit = revenue - (shares * buy_price)
            if profit > 0:
                wins += 1
            cash += revenue
            shares = 0
            trades += 1

        equity[i] = cash + shares * closes[i]

    if shares > 0:
        sell_price = closes[-1] * (1 - total_cost_rate)
        revenue = shares * sell_price
        cash += revenue
        shares = 0
        trades += 1

    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital

    max_dd = 0.0
    peak = equity[rsi_period]
    for i in range(rsi_period, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    returns = np.diff(equity[rsi_period:]) / equity[rsi_period:-1]
    returns = returns[returns != 0]
    sharpe = 0.0
    if len(returns) > 0:
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        if std_return > 0:
            sharpe = (mean_return * 252) / (std_return * np.sqrt(252))

    win_rate = wins / trades if trades > 0 else 0.0

    return final_capital, total_return, max_dd, sharpe, trades, win_rate, equity
