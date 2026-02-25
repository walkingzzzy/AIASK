"""
回测引擎 - 使用Numba JIT优化 + Ray并行计算
"""

from typing import List, Dict, Any, Optional
import numpy as np
from numba import jit
import os
import json

from .cost_model import build_cost_model, effective_cost_rate
from .signal_dsl import evaluate_signal
from .slippage import SlippageCalculator, SlippageModelType

# 可选的Ray支持
RAY_AVAILABLE = False
try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    pass

@jit(nopython=True)
def _backtest_ma_cross_jit(
    closes: np.ndarray,
    short_period: int,
    long_period: int,
    initial_capital: float,
    commission: float
) -> tuple:
    """Numba优化的均线交叉回测核心"""
    n = len(closes)
    
    # 计算均线
    short_ma = np.zeros(n)
    long_ma = np.zeros(n)
    
    for i in range(short_period - 1, n):
        short_ma[i] = np.mean(closes[i-short_period+1:i+1])
    
    for i in range(long_period - 1, n):
        long_ma[i] = np.mean(closes[i-long_period+1:i+1])
    
    # 回测
    cash = initial_capital
    shares = 0
    equity = np.zeros(n)
    trades = 0
    wins = 0
    
    for i in range(long_period, n):
        # 金叉买入
        if short_ma[i-1] <= long_ma[i-1] and short_ma[i] > long_ma[i] and cash > 0:
            buy_price = closes[i] * (1 + commission)
            shares = int(cash / buy_price)
            cash -= shares * buy_price
            trades += 1
        
        # 死叉卖出
        elif short_ma[i-1] >= long_ma[i-1] and short_ma[i] < long_ma[i] and shares > 0:
            sell_price = closes[i] * (1 - commission)
            profit = shares * sell_price - shares * closes[i-1]
            if profit > 0:
                wins += 1
            cash += shares * sell_price
            shares = 0
        
        equity[i] = cash + shares * closes[i]
    
    # 最终清仓
    if shares > 0:
        cash += shares * closes[-1] * (1 - commission)
        shares = 0
    
    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital
    
    # 计算最大回撤
    max_dd = 0.0
    peak = equity[long_period]
    for i in range(long_period, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # 计算夏普比率
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
def _backtest_momentum_jit(
    closes: np.ndarray,
    lookback: int,
    threshold: float,
    initial_capital: float,
    commission: float
) -> tuple:
    """Numba优化的动量策略回测"""
    n = len(closes)
    cash = initial_capital
    shares = 0
    equity = np.full(n, initial_capital)
    trades = 0
    wins = 0
    
    for i in range(lookback, n):
        # 计算动量
        momentum = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        
        # 买入信号：动量超过阈值且未持仓
        if momentum > threshold and shares == 0:
            buy_price = closes[i] * 1.0001  # 滑点
            max_shares = int(cash / (buy_price * (1 + commission)))
            if max_shares > 0:
                cost = max_shares * buy_price * (1 + commission)
                shares = max_shares
                cash -= cost
                trades += 1
        
        # 卖出信号：动量低于负阈值且持仓
        elif momentum < -threshold and shares > 0:
            sell_price = closes[i] * 0.9999  # 滑点
            revenue = shares * sell_price * (1 - commission)
            profit = revenue - (shares * buy_price * (1 + commission))
            if profit > 0:
                wins += 1
            cash += revenue
            shares = 0
            trades += 1
        
        # 更新权益
        equity[i] = cash + shares * closes[i]
    
    # 最后平仓
    if shares > 0:
        sell_price = closes[-1] * 0.9999
        revenue = shares * sell_price * (1 - commission)
        cash += revenue
        shares = 0
        trades += 1
    
    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital
    
    # 计算最大回撤
    max_dd = 0.0
    peak = equity[lookback]
    for i in range(lookback, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # 计算夏普比率
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
    commission: float
) -> tuple:
    """Numba优化的RSI策略回测"""
    n = len(closes)
    
    # 计算RSI
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
    
    # 回测逻辑
    cash = initial_capital
    shares = 0
    equity = np.full(n, initial_capital)
    trades = 0
    wins = 0
    buy_price = 0.0
    
    for i in range(rsi_period, n):
        # 买入信号：RSI超卖且未持仓
        if rsi[i] < oversold and shares == 0:
            buy_price = closes[i] * 1.0001
            max_shares = int(cash / (buy_price * (1 + commission)))
            if max_shares > 0:
                cost = max_shares * buy_price * (1 + commission)
                shares = max_shares
                cash -= cost
                trades += 1
        
        # 卖出信号：RSI超买且持仓
        elif rsi[i] > overbought and shares > 0:
            sell_price = closes[i] * 0.9999
            revenue = shares * sell_price * (1 - commission)
            profit = revenue - (shares * buy_price * (1 + commission))
            if profit > 0:
                wins += 1
            cash += revenue
            shares = 0
            trades += 1
        
        equity[i] = cash + shares * closes[i]
    
    # 最后平仓
    if shares > 0:
        sell_price = closes[-1] * 0.9999
        revenue = shares * sell_price * (1 - commission)
        cash += revenue
        shares = 0
        trades += 1
    
    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital
    
    # 计算最大回撤
    max_dd = 0.0
    peak = equity[rsi_period]
    for i in range(rsi_period, n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    
    # 计算夏普比率
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


# ---------------------------------------------------------------------------
# A股可交易性过滤器（停牌 + 涨跌停检测）
# ---------------------------------------------------------------------------

def _get_limit_ratio(code: str) -> float:
    """根据股票代码判断涨跌停幅度。

    - 主板（60xxxx / 00xxxx）: ±10%
    - 创业板（300xxx）/ 科创板（688xxx）: ±20%
    - ST 股票由调用方通过 is_st 参数单独处理
    """
    c = str(code).strip()
    # 去掉可能的市场前缀 (sh/sz/bj)
    for prefix in ('sh', 'sz', 'bj', 'SH', 'SZ', 'BJ'):
        if c.startswith(prefix):
            c = c[len(prefix):]
            break
    if c.startswith('300') or c.startswith('301') or c.startswith('688'):
        return 0.20
    return 0.10


def build_tradability_mask(
    closes: np.ndarray,
    volumes: Optional[np.ndarray] = None,
    code: str = '',
    is_st: bool = False,
) -> np.ndarray:
    """构建可交易性布尔掩码。

    不可交易的情况:
    1. 停牌: volume == 0
    2. 涨停: close >= prev_close * (1 + limit_ratio) - 容差  → 买入受限
    3. 跌停: close <= prev_close * (1 - limit_ratio) + 容差  → 卖出受限

    为简化处理，涨停和跌停日均标记为不可交易（保守策略）。

    Returns
    -------
    np.ndarray[bool] — True 表示当日可交易
    """
    n = len(closes)
    mask = np.ones(n, dtype=bool)

    # 停牌检测
    if volumes is not None and len(volumes) == n:
        mask &= (volumes > 0)

    # 涨跌停检测
    limit_ratio = 0.05 if is_st else _get_limit_ratio(code)
    tolerance = 0.002  # 0.2% 容差，避免浮点误差
    for i in range(1, n):
        prev = closes[i - 1]
        if prev <= 0:
            continue
        change = (closes[i] - prev) / prev
        # 涨停或跌停
        if change >= limit_ratio - tolerance or change <= -(limit_ratio - tolerance):
            mask[i] = False

    return mask


# ---------------------------------------------------------------------------
# 通用信号驱动交易模拟器（配合 DSL evaluate_signal 使用）
# ---------------------------------------------------------------------------

def _simulate_trades_from_signals(
    closes: np.ndarray,
    entry_mask: np.ndarray,
    exit_mask: np.ndarray,
    initial_capital: float,
    cost_rate: float,
    volumes: Optional[np.ndarray] = None,
    slippage_calc: Optional[SlippageCalculator] = None,
    tradability_mask: Optional[np.ndarray] = None,
) -> tuple:
    """根据 entry/exit 布尔掩码模拟交易，返回与 JIT 函数相同的 7 元组。

    新增参数
    ----------
    volumes : 成交量数组，用于动态滑点模型
    slippage_calc : SlippageCalculator 实例，None 时退化为 cost_rate 模式
    tradability_mask : 可交易性掩码，False 的日期跳过交易

    Returns
    -------
    (final_capital, total_return, max_drawdown, sharpe, trades, win_rate, equity)
    """
    n = len(closes)
    cash = initial_capital
    shares = 0
    buy_price = 0.0
    trades = 0
    wins = 0
    equity = np.full(n, initial_capital, dtype=np.float64)

    use_slippage_model = slippage_calc is not None
    vols = volumes if volumes is not None else np.zeros(n)

    for i in range(n):
        # 可交易性检查
        tradable = True if tradability_mask is None else bool(tradability_mask[i])

        if entry_mask[i] and shares == 0 and cash > 0 and tradable:
            if use_slippage_model:
                # 先估算可买股数（用 cost_rate 近似），再计算精确滑点
                approx_price = closes[i] * (1 + cost_rate)
                est_shares = int(cash / approx_price) if approx_price > 0 else 0
                if est_shares > 0:
                    slip_info = slippage_calc.calculate(
                        price=closes[i],
                        volume=float(vols[i]),
                        order_size=float(est_shares),
                        is_buy=True,
                    )
                    buy_price = slip_info['execution_price'] * (1 + cost_rate)
                    max_shares = int(cash / buy_price) if buy_price > 0 else 0
                    if max_shares > 0:
                        shares = max_shares
                        cash -= shares * buy_price
                        trades += 1
            else:
                buy_price = closes[i] * (1 + cost_rate)
                max_shares = int(cash / buy_price)
                if max_shares > 0:
                    shares = max_shares
                    cash -= shares * buy_price
                    trades += 1

        elif exit_mask[i] and shares > 0 and tradable:
            if use_slippage_model:
                slip_info = slippage_calc.calculate(
                    price=closes[i],
                    volume=float(vols[i]),
                    order_size=float(shares),
                    is_buy=False,
                )
                sell_price = slip_info['execution_price'] * (1 - cost_rate)
            else:
                sell_price = closes[i] * (1 - cost_rate)
            revenue = shares * sell_price
            if revenue > shares * buy_price:
                wins += 1
            cash += revenue
            shares = 0

        equity[i] = cash + shares * closes[i]

    # 期末清仓
    if shares > 0:
        if use_slippage_model:
            slip_info = slippage_calc.calculate(
                price=closes[-1],
                volume=float(vols[-1]) if len(vols) > 0 else 0.0,
                order_size=float(shares),
                is_buy=False,
            )
            sell_price = slip_info['execution_price'] * (1 - cost_rate)
        else:
            sell_price = closes[-1] * (1 - cost_rate)
        revenue = shares * sell_price
        if revenue > shares * buy_price:
            wins += 1
        cash += revenue
        shares = 0

    final_capital = cash
    total_return = (final_capital - initial_capital) / initial_capital

    # 最大回撤
    max_dd = 0.0
    peak = equity[0]
    for i in range(n):
        if equity[i] > peak:
            peak = equity[i]
        dd = (peak - equity[i]) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # 夏普比率
    valid = equity[equity > 0]
    sharpe = 0.0
    if len(valid) > 1:
        rets = np.diff(valid) / valid[:-1]
        rets = rets[rets != 0]
        if len(rets) > 0:
            mean_r = np.mean(rets)
            std_r = np.std(rets)
            if std_r > 0:
                sharpe = (mean_r * 252) / (std_r * np.sqrt(252))

    win_rate = wins / trades if trades > 0 else 0.0
    return final_capital, total_return, max_dd, sharpe, trades, win_rate, equity


# ---------------------------------------------------------------------------
# 交易记录提取 & 盈亏比计算
# ---------------------------------------------------------------------------

def _calc_profit_factor(trade_list: List[Dict[str, Any]]) -> float:
    gross_profit = sum(t['profit'] for t in trade_list if t.get('profit', 0) > 0)
    gross_loss = abs(sum(t['profit'] for t in trade_list if t.get('profit', 0) < 0))
    if gross_loss == 0:
        return round(gross_profit, 2) if gross_profit > 0 else 0.0
    return round(gross_profit / gross_loss, 4)


def _build_trade_list(
    klines: List[Dict[str, Any]],
    closes: np.ndarray,
    strategy: str,
    params: Dict[str, Any],
    cost_rate: float,
) -> List[Dict[str, Any]]:
    """Replay strategy in pure Python to extract trade records."""
    n = len(closes)
    trades: List[Dict[str, Any]] = []
    initial_capital = float(params.get('initial_capital', 100000) or 100000)

    def _date(idx: int) -> str:
        return str(klines[idx].get('date', ''))[:10] if idx < len(klines) else ''

    def _record(entry_i, exit_i, ep, xp, sh):
        pnl = sh * (xp - ep)
        trades.append({
            'date': _date(entry_i), 'type': 'buy',
            'price': round(float(ep), 2), 'exit_price': round(float(xp), 2),
            'shares': int(sh), 'profit': round(float(pnl), 2),
            'holding_days': exit_i - entry_i,
        })

    if strategy == 'ma_cross':
        sp = int(params.get('short_period', 5))
        lp = int(params.get('long_period', 20))
        sma = np.zeros(n)
        lma = np.zeros(n)
        for i in range(sp - 1, n):
            sma[i] = np.mean(closes[i - sp + 1:i + 1])
        for i in range(lp - 1, n):
            lma[i] = np.mean(closes[i - lp + 1:i + 1])
        cash, shares, ep, ei = initial_capital, 0, 0.0, 0
        for i in range(lp, n):
            if sma[i - 1] <= lma[i - 1] and sma[i] > lma[i] and cash > 0 and shares == 0:
                ep = closes[i] * (1 + cost_rate)
                shares = int(cash / ep)
                cash -= shares * ep
                ei = i
            elif sma[i - 1] >= lma[i - 1] and sma[i] < lma[i] and shares > 0:
                xp = closes[i] * (1 - cost_rate)
                _record(ei, i, ep, xp, shares)
                cash += shares * xp
                shares = 0
        if shares > 0:
            xp = closes[-1] * (1 - cost_rate)
            _record(ei, n - 1, ep, xp, shares)

    elif strategy == 'momentum':
        lb = int(params.get('lookback', 20))
        th = float(params.get('threshold', 0.02))
        cash, shares, ep, ei = initial_capital, 0, 0.0, 0
        for i in range(lb, n):
            mom = (closes[i] - closes[i - lb]) / closes[i - lb]
            if mom > th and shares == 0 and cash > 0:
                ep = closes[i] * 1.0001 * (1 + cost_rate)
                shares = int(cash / ep)
                if shares > 0:
                    cash -= shares * ep
                    ei = i
            elif mom < -th and shares > 0:
                xp = closes[i] * 0.9999 * (1 - cost_rate)
                _record(ei, i, ep, xp, shares)
                cash += shares * xp
                shares = 0
        if shares > 0:
            xp = closes[-1] * 0.9999 * (1 - cost_rate)
            _record(ei, n - 1, ep, xp, shares)

    elif strategy == 'rsi':
        rp = int(params.get('rsi_period', 14))
        os_val = float(params.get('oversold', 30))
        ob_val = float(params.get('overbought', 70))
        rsi = np.zeros(n)
        for i in range(rp, n):
            g = l = 0.0
            for j in range(i - rp + 1, i + 1):
                c = closes[j] - closes[j - 1]
                if c > 0: g += c
                else: l -= c
            ag, al = g / rp, l / rp
            rsi[i] = 100.0 if al == 0 else 100.0 - (100.0 / (1 + ag / al))
        cash, shares, ep, ei = initial_capital, 0, 0.0, 0
        for i in range(rp, n):
            if rsi[i] < os_val and shares == 0:
                ep = closes[i] * 1.0001 * (1 + cost_rate)
                shares = int(cash / ep)
                if shares > 0:
                    cash -= shares * ep
                    ei = i
            elif rsi[i] > ob_val and shares > 0:
                xp = closes[i] * 0.9999 * (1 - cost_rate)
                _record(ei, i, ep, xp, shares)
                cash += shares * xp
                shares = 0
        if shares > 0:
            xp = closes[-1] * 0.9999 * (1 - cost_rate)
            _record(ei, n - 1, ep, xp, shares)

    elif strategy == 'buy_and_hold':
        ep = float(closes[0])
        shares = int(initial_capital / ep)
        xp = float(closes[-1])
        _record(0, n - 1, ep, xp, shares)

    return trades


class BacktestEngine:
    """回测引擎"""
    
    @staticmethod
    def run_backtest(
        code: str,
        klines: List[Dict[str, Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """运行回测"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}

        params = params or {}
        initial_capital = float(params.get('initial_capital', 100000) or 100000)

        input_cost_model = params.get('cost_model') if isinstance(params.get('cost_model'), dict) else None
        if input_cost_model:
            cost_model = input_cost_model
        else:
            cost_model = build_cost_model(
                params,
                notional=float(initial_capital),
                default_mode='backtest',
                reference_price_fallback=float((klines[-1] or {}).get('close') or 0.0) if klines else 0.0,
            )

        commission = float(params.get('commission', 0.0003) or 0.0)
        slippage = float(params.get('slippage', 0.0) or 0.0)
        total_cost_rate = max(
            0.0,
            effective_cost_rate(
                cost_model,
                fallback_commission=commission,
                fallback_slippage=slippage,
            ),
        )

        benchmark = str(params.get('benchmark') or '')
        benchmark_klines = params.get('benchmark_klines') or []
        benchmark_return: Optional[float] = None
        if isinstance(benchmark_klines, list) and benchmark_klines:
            try:
                bm_closes = [
                    float(row.get('close'))
                    for row in benchmark_klines
                    if isinstance(row, dict) and row.get('close') is not None
                ]
                if len(bm_closes) >= 2 and bm_closes[0] != 0:
                    benchmark_return = (bm_closes[-1] - bm_closes[0]) / bm_closes[0]
            except Exception:
                benchmark_return = None

        # ---- 滑点模型构建 ----
        slippage_model_type = str(params.get('slippage_model', '') or '').lower()
        slippage_calc: Optional[SlippageCalculator] = None
        if slippage_model_type in ('fixed', 'volume_based', 'market_impact'):
            type_map = {
                'fixed': SlippageModelType.FIXED,
                'volume_based': SlippageModelType.VOLUME_BASED,
                'market_impact': SlippageModelType.MARKET_IMPACT,
            }
            slippage_calc = SlippageCalculator(type_map[slippage_model_type])

        def _finalize_payload(payload: Dict[str, Any], equity: Any = None, trade_list: Any = None) -> Dict[str, Any]:
            enriched = dict(payload)
            enriched['commission'] = float(commission)
            enriched['slippage'] = float(slippage)
            enriched['total_cost_rate'] = float(total_cost_rate)
            enriched['cost_model'] = cost_model
            if slippage_calc is not None:
                enriched['slippage_model'] = slippage_model_type
            if benchmark:
                enriched['benchmark'] = benchmark
            if benchmark_return is not None:
                enriched['benchmark_return'] = float(benchmark_return)
                enriched['excess_return'] = float(enriched.get('total_return', 0.0) - benchmark_return)
            if equity is not None:
                curve = equity.tolist() if hasattr(equity, 'tolist') else list(equity)
                enriched['equity_curve'] = [round(v, 2) for v in curve]
            enriched['dates'] = [str(k.get('date', ''))[:10] for k in klines]
            if trade_list is not None:
                enriched['trades'] = trade_list
                enriched['profit_factor'] = _calc_profit_factor(trade_list)
            return enriched

        closes = np.array([k['close'] for k in klines])

        # ---- 成交量数组 & 可交易性掩码 ----
        volumes = np.array([
            float(k.get('volume', 0) or 0) for k in klines
        ], dtype=np.float64)
        is_st = bool(params.get('is_st', False))
        enable_tradability = bool(params.get('tradability_filter', False))
        tradability_mask: Optional[np.ndarray] = None
        if enable_tradability:
            tradability_mask = build_tradability_mask(
                closes, volumes=volumes, code=code, is_st=is_st,
            )

        # ---- DSL 求值路径：当 params 携带 signal_definition 时优先使用 ----
        signal_def = params.get('signal_definition')
        if signal_def and isinstance(signal_def, dict) and signal_def.get('expression'):
            import pandas as _pd
            df = _pd.DataFrame(klines)
            signals = evaluate_signal(signal_def, df, close_col='close')
            entry_arr = signals['entry'].values.astype(bool)
            exit_arr = signals['exit'].values.astype(bool)

            result = _simulate_trades_from_signals(
                closes, entry_arr, exit_arr, initial_capital, total_cost_rate,
                volumes=volumes, slippage_calc=slippage_calc,
                tradability_mask=tradability_mask,
            )
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            payload = {
                'code': code,
                'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
                'signal_dsl_version': signal_def.get('schema_version', 'unknown'),
            }
            return {'success': True, 'data': _finalize_payload(payload, equity=equity)}

        if strategy == 'ma_cross':
            short_period = params.get('short_period', 5)
            long_period = params.get('long_period', 20)

            result = _backtest_ma_cross_jit(
                closes, short_period, long_period, initial_capital, total_cost_rate
            )

            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            payload = {
                'code': code,
                'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
            }
            trade_list = _build_trade_list(klines, closes, 'ma_cross', {**params, 'initial_capital': initial_capital}, total_cost_rate)
            return {'success': True, 'data': _finalize_payload(payload, equity=equity, trade_list=trade_list)}

        elif strategy == 'buy_and_hold':
            final_capital = initial_capital * (closes[-1] / closes[0])
            total_return = (final_capital - initial_capital) / initial_capital

            equity = initial_capital * (closes / closes[0])
            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak
            max_dd = float(np.max(drawdown))

            payload = {
                'code': code,
                'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': max_dd,
                'sharpe_ratio': 0.0,
                'trades_count': 1,
                'win_rate': 1.0 if total_return > 0 else 0.0,
                'params': params,
            }
            trade_list = _build_trade_list(klines, closes, 'buy_and_hold', {**params, 'initial_capital': initial_capital}, total_cost_rate)
            return {'success': True, 'data': _finalize_payload(payload, equity=equity, trade_list=trade_list)}

        elif strategy == 'momentum':
            lookback = params.get('lookback', 20)
            threshold = params.get('threshold', 0.02)

            result = _backtest_momentum_jit(
                closes, lookback, threshold, initial_capital, total_cost_rate
            )

            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            payload = {
                'code': code,
                'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
            }
            trade_list = _build_trade_list(klines, closes, 'momentum', {**params, 'initial_capital': initial_capital}, total_cost_rate)
            return {'success': True, 'data': _finalize_payload(payload, equity=equity, trade_list=trade_list)}

        elif strategy == 'rsi':
            rsi_period = params.get('rsi_period', 14)
            oversold = params.get('oversold', 30)
            overbought = params.get('overbought', 70)

            result = _backtest_rsi_jit(
                closes, rsi_period, oversold, overbought, initial_capital, total_cost_rate
            )

            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result

            payload = {
                'code': code,
                'strategy': strategy,
                'initial_capital': initial_capital,
                'final_capital': float(final_capital),
                'total_return': float(total_return),
                'max_drawdown': float(max_dd),
                'sharpe_ratio': float(sharpe),
                'trades_count': int(trades),
                'win_rate': float(win_rate),
                'params': params,
            }
            trade_list = _build_trade_list(klines, closes, 'rsi', {**params, 'initial_capital': initial_capital}, total_cost_rate)
            return {'success': True, 'data': _finalize_payload(payload, equity=equity, trade_list=trade_list)}

        return {'success': False, 'error': f'Unknown strategy: {strategy}'}
    
    @staticmethod
    def optimize_parameters(
        code: str,
        klines: List[Dict[str, Any]],
        strategy: str = 'ma_cross',
        param_ranges: Optional[Dict[str, List]] = None
    ) -> Dict[str, Any]:
        """参数优化（网格搜索）"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}
        
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
                        'initial_capital': 100000,
                        'commission': 0.0003,
                        'short_period': short,
                        'long_period': long,
                    }
                    
                    result = BacktestEngine.run_backtest(code, klines, strategy, params)
                    
                    if result['success']:
                        data = result['data']
                        # 优化目标：夏普比率 * (1 - 最大回撤)
                        metric = data['sharpe_ratio'] * (1 - data['max_drawdown'])
                        
                        all_results.append({
                            'params': params,
                            'metric': metric,
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
        klines: List[Dict[str, Any]],
        strategy: str = 'ma_cross',
        params: Optional[Dict[str, Any]] = None,
        runs: int = 1000
    ) -> Dict[str, Any]:
        """蒙特卡洛模拟"""
        if not klines:
            return {'success': False, 'error': 'No kline data'}
        
        params = params or {}
        closes = np.array([k['close'] for k in klines])
        
        # 计算历史收益率
        returns = np.diff(closes) / closes[:-1]
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        # 运行模拟
        final_capitals = []
        max_drawdowns = []
        
        for _ in range(runs):
            # 生成随机收益率序列
            simulated_returns = np.random.normal(mean_return, std_return, len(returns))
            simulated_closes = closes[0] * np.cumprod(1 + simulated_returns)
            simulated_closes = np.insert(simulated_closes, 0, closes[0])
            
            # 构造模拟K线
            simulated_klines = [
                {'close': float(c), 'date': klines[i]['date']}
                for i, c in enumerate(simulated_closes)
            ]
            
            # 运行回测
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
        klines: List[Dict[str, Any]],
        strategy: str = 'ma_cross',
        param_ranges: Optional[Dict[str, List]] = None,
        train_window: int = 250,
        test_window: int = 60
    ) -> Dict[str, Any]:
        """Walk-Forward分析"""
        if len(klines) < train_window + test_window:
            return {'success': False, 'error': 'Insufficient data for walk-forward analysis'}
        
        segments = []
        capital = 100000
        
        i = 0
        while i + train_window + test_window <= len(klines):
            # 训练集
            train_klines = klines[i:i+train_window]
            
            # 优化参数
            opt_result = BacktestEngine.optimize_parameters(
                code, train_klines, strategy, param_ranges
            )
            
            if not opt_result['success']:
                break
            
            best_params = opt_result['data']['best_params']
            
            # 测试集
            test_klines = klines[i+train_window:i+train_window+test_window]
            
            # 在测试集上运行
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


# Ray并行回测支持
if RAY_AVAILABLE:
    @ray.remote
    def _parallel_backtest_task(code, klines, strategy, params):
        """Ray远程任务"""
        return backtest_engine.run_backtest(code, klines, strategy, params)
    
    class ParallelBacktestEngine:
        """并行回测引擎（使用Ray）- 性能优化版"""
        
        @staticmethod
        def batch_backtest(
            codes: List[str],
            klines_dict: Dict[str, List[Dict[str, Any]]],
            strategy: str = 'ma_cross',
            params: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            """批量并行回测 - 优化版"""
            if not ray.is_initialized():
                # 优化Ray配置
                ray.init(
                    ignore_reinit_error=True,
                    num_cpus=os.cpu_count(),
                    object_store_memory=2 * 1024 * 1024 * 1024,  # 2GB
                    _system_config={
                        "max_io_workers": 4,
                        "object_spilling_config": json.dumps({
                            "type": "filesystem",
                            "params": {"directory_path": "/tmp/ray_spill"}
                        })
                    }
                )
            
            params = params or {}
            
            # 优化1：预处理K线数据为NumPy数组，减少序列化开销
            processed_data = {}
            for code in codes:
                if code in klines_dict and klines_dict[code]:
                    klines = klines_dict[code]
                    processed_data[code] = {
                        'closes': np.array([k['close'] for k in klines]),
                        'volumes': np.array([k['volume'] for k in klines]),
                        'highs': np.array([k['high'] for k in klines]),
                        'lows': np.array([k['low'] for k in klines]),
                    }
            
            # 优化2：将数据放入Ray对象存储，避免重复序列化
            data_ref = ray.put(processed_data)
            params_ref = ray.put(params)
            
            # 优化3：批量提交任务
            futures = [
                _parallel_backtest_task_optimized.remote(code, data_ref, strategy, params_ref)
                for code in codes if code in processed_data
            ]
            
            # 优化4：使用ray.wait进行流式处理，避免阻塞
            results = []
            remaining = futures
            
            while remaining:
                # 每次等待最多10个任务完成
                ready, remaining = ray.wait(remaining, num_returns=min(10, len(remaining)), timeout=30)
                
                if ready:
                    batch_results = ray.get(ready)
                    results.extend(batch_results)
            
            return {
                'success': True,
                'data': {
                    'results': results,
                    'count': len(results),
                }
            }
        
        @staticmethod
        def batch_backtest_sequential(
            codes: List[str],
            klines_dict: Dict[str, List[Dict[str, Any]]],
            strategy: str = 'ma_cross',
            params: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            """批量顺序回测（不使用Ray）- 作为对比"""
            params = params or {}
            results = []
            
            for code in codes:
                if code in klines_dict:
                    result = backtest_engine.run_backtest(code, klines_dict[code], strategy, params)
                    if result['success']:
                        results.append(result['data'])
            
            return {
                'success': True,
                'data': {
                    'results': results,
                    'count': len(results),
                }
            }


# Ray远程函数 - 优化版
@ray.remote
def _parallel_backtest_task_optimized(
    code: str,
    data_ref,  # Ray对象引用
    strategy: str,
    params_ref  # Ray对象引用
):
    """优化的并行回测任务 - 使用对象引用减少序列化"""
    try:
        # 从对象存储获取数据
        processed_data = ray.get(data_ref)
        params = ray.get(params_ref)
        
        if code not in processed_data:
            return {
                'code': code,
                'success': False,
                'error': 'No data for code'
            }
        
        data = processed_data[code]
        closes = data['closes']
        volumes = data.get('volumes', np.zeros_like(closes))

        # 使用Numba优化的回测函数
        initial_capital = params.get('initial_capital', 100000)
        commission = params.get('commission', 0.0003)

        # 滑点模型 & 可交易性掩码
        slippage_model_type = str(params.get('slippage_model', '') or '').lower()
        slippage_calc_ray: Optional[SlippageCalculator] = None
        if slippage_model_type in ('fixed', 'volume_based', 'market_impact'):
            _type_map = {
                'fixed': SlippageModelType.FIXED,
                'volume_based': SlippageModelType.VOLUME_BASED,
                'market_impact': SlippageModelType.MARKET_IMPACT,
            }
            slippage_calc_ray = SlippageCalculator(_type_map[slippage_model_type])

        tradability_mask_ray: Optional[np.ndarray] = None
        if bool(params.get('tradability_filter', False)):
            tradability_mask_ray = build_tradability_mask(
                closes, volumes=volumes, code=code,
                is_st=bool(params.get('is_st', False)),
            )

        # DSL 求值路径
        signal_def = params.get('signal_definition')
        if signal_def and isinstance(signal_def, dict) and signal_def.get('expression'):
            import pandas as _pd
            df = _pd.DataFrame({'close': closes})
            signals = evaluate_signal(signal_def, df, close_col='close')
            entry_arr = signals['entry'].values.astype(bool)
            exit_arr = signals['exit'].values.astype(bool)
            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = \
                _simulate_trades_from_signals(
                    closes, entry_arr, exit_arr, initial_capital, commission,
                    volumes=volumes, slippage_calc=slippage_calc_ray,
                    tradability_mask=tradability_mask_ray,
                )
        elif strategy == 'ma_cross':
            short_period = params.get('short_period', 5)
            long_period = params.get('long_period', 20)

            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = _backtest_ma_cross_jit(
                closes, short_period, long_period, initial_capital, commission
            )

        elif strategy == 'momentum':
            period = params.get('period', 20)
            threshold = params.get('threshold', 0.02)

            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = _backtest_momentum_jit(
                closes, period, threshold, initial_capital, commission
            )

        elif strategy == 'rsi':
            rsi_period = params.get('rsi_period', 14)
            oversold = params.get('oversold', 30)
            overbought = params.get('overbought', 70)

            final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = _backtest_rsi_jit(
                closes, rsi_period, oversold, overbought, initial_capital, commission
            )

        else:
            return {
                'code': code,
                'success': False,
                'error': f'Unknown strategy: {strategy}'
            }
        
        return {
            'code': code,
            'strategy': strategy,
            'initial_capital': float(initial_capital),
            'final_capital': float(final_capital),
            'total_return': float(total_return),
            'total_return_pct': f"{total_return*100:.2f}%",
            'max_drawdown': float(max_dd),
            'max_drawdown_pct': f"{max_dd*100:.2f}%",
            'sharpe_ratio': float(sharpe),
            'trades_count': int(trades),
            'win_rate': float(win_rate),
            'win_rate_pct': f"{win_rate*100:.2f}%",
            'success': True
        }
    
    except Exception as e:
        return {
            'code': code,
            'success': False,
            'error': str(e)
        }


backtest_engine = BacktestEngine()


# ========== 高级回测功能 ==========

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
        """
        带动态止损的回测
        
        Args:
            stop_loss: 止损比例
            take_profit: 止盈比例
            trailing_stop: 移动止损比例
        """
        if not klines:
            return {'success': False, 'error': 'No kline data'}
        
        params = params or {}
        initial_capital = params.get('initial_capital', 100000)
        commission = params.get('commission', 0.0003)
        
        closes = np.array([k['close'] for k in klines])
        
        # 先运行基础策略获取信号
        base_result = backtest_engine.run_backtest(code, klines, strategy, params)
        
        if not base_result['success']:
            return base_result
        
        # 应用动态止损逻辑
        cash = initial_capital
        shares = 0
        buy_price = 0.0
        highest_price = 0.0
        trades = 0
        wins = 0
        
        equity = []
        
        for i, close in enumerate(closes):
            # 持仓时检查止损止盈
            if shares > 0:
                # 更新最高价
                if close > highest_price:
                    highest_price = close
                
                # 止损
                if close <= buy_price * (1 - stop_loss):
                    sell_price = close * (1 - commission)
                    cash += shares * sell_price
                    if sell_price > buy_price:
                        wins += 1
                    shares = 0
                    trades += 1
                
                # 止盈
                elif close >= buy_price * (1 + take_profit):
                    sell_price = close * (1 - commission)
                    cash += shares * sell_price
                    wins += 1
                    shares = 0
                    trades += 1
                
                # 移动止损
                elif close <= highest_price * (1 - trailing_stop):
                    sell_price = close * (1 - commission)
                    cash += shares * sell_price
                    if sell_price > buy_price:
                        wins += 1
                    shares = 0
                    trades += 1
            
            equity.append(cash + shares * close)
        
        # 最终清仓
        if shares > 0:
            cash += shares * closes[-1] * (1 - commission)
            shares = 0
        
        final_capital = cash
        total_return = (final_capital - initial_capital) / initial_capital
        
        # 计算最大回撤
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
        """
        带仓位管理的回测
        
        Args:
            sizing_method: 仓位管理方法 ('fixed', 'kelly', 'volatility')
            risk_per_trade: 每笔交易风险比例
        """
        if not klines:
            return {'success': False, 'error': 'No kline data'}
        
        params = params or {}
        initial_capital = params.get('initial_capital', 100000)
        
        # 运行基础回测
        result = backtest_engine.run_backtest(code, klines, strategy, params)
        
        if not result['success']:
            return result
        
        # 根据仓位管理方法调整
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
        
        # 调整收益
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
        """
        多策略组合回测
        
        Args:
            strategies: 策略列表 [{'name': 'ma_cross', 'params': {...}}, ...]
            allocation: 资金分配比例
        """
        if not klines or not strategies:
            return {'success': False, 'error': 'Invalid input'}
        
        n_strategies = len(strategies)
        
        if allocation is None:
            allocation = [1.0 / n_strategies] * n_strategies
        
        if len(allocation) != n_strategies:
            return {'success': False, 'error': 'Allocation length mismatch'}
        
        # 运行各策略
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
