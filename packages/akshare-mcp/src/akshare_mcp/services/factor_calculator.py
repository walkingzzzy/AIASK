"""因子计算器 - 完整实现"""
import numpy as np
from typing import List, Dict, Any, Optional
from numba import jit


class FactorCalculator:
    """因子计算器 - 支持技术因子、基本面因子、风格因子"""
    
    # ========== 技术因子 ==========
    
    @staticmethod
    def calculate_momentum(closes: List[float], period: int = 20) -> float:
        """动量因子"""
        if len(closes) < period:
            return 0.0
        return (closes[-1] - closes[-period]) / closes[-period]
    
    @staticmethod
    def calculate_reversal(closes: List[float], period: int = 5) -> float:
        """反转因子（短期）"""
        if len(closes) < period:
            return 0.0
        return -(closes[-1] - closes[-period]) / closes[-period]
    
    @staticmethod
    def calculate_volatility(closes: List[float], period: int = 20) -> float:
        """波动率因子"""
        if len(closes) < period:
            return 0.0
        returns = np.diff(closes[-period:]) / closes[-period-1:-1]
        return float(np.std(returns) * np.sqrt(252))
    
    @staticmethod
    def calculate_volume_factor(volumes: List[float], period: int = 20) -> float:
        """成交量因子"""
        if len(volumes) < period:
            return 0.0
        recent_avg = np.mean(volumes[-period:])
        long_avg = np.mean(volumes[-period*2:-period]) if len(volumes) >= period*2 else recent_avg
        return (recent_avg - long_avg) / long_avg if long_avg > 0 else 0.0
    
    @staticmethod
    def calculate_price_factor(closes: List[float], highs: List[float], lows: List[float]) -> float:
        """价格位置因子（当前价格在区间中的位置）"""
        if not closes or not highs or not lows:
            return 0.5
        high_max = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        low_min = min(lows[-20:]) if len(lows) >= 20 else min(lows)
        if high_max == low_min:
            return 0.5
        return (closes[-1] - low_min) / (high_max - low_min)
    
    @staticmethod
    def calculate_trend_factor(closes: List[float], period: int = 60) -> float:
        """趋势因子（线性回归斜率）"""
        if len(closes) < period:
            return 0.0
        y = np.array(closes[-period:])
        x = np.arange(len(y))
        # 线性回归
        slope = np.polyfit(x, y, 1)[0]
        return slope / np.mean(y) if np.mean(y) > 0 else 0.0
    
    # ========== 基本面因子 ==========
    
    @staticmethod
    def calculate_value_factor(pe: float, pb: float, ps: float = None) -> float:
        """价值因子（综合PE、PB、PS）"""
        score = 0.0
        count = 0
        
        if pe > 0:
            score += 1.0 / pe
            count += 1
        if pb > 0:
            score += 1.0 / pb
            count += 1
        if ps and ps > 0:
            score += 1.0 / ps
            count += 1
        
        return score / count if count > 0 else 0.0
    
    @staticmethod
    def calculate_quality_factor(roe: float, debt_ratio: float, profit_growth: float = None) -> float:
        """质量因子（ROE、负债率、利润增长）"""
        score = 0.0
        
        # ROE越高越好
        if roe:
            score += min(roe / 20.0, 1.0)  # 归一化到0-1
        
        # 负债率越低越好
        if debt_ratio:
            score += max(1.0 - debt_ratio, 0.0)
        
        # 利润增长越高越好
        if profit_growth:
            score += min(profit_growth / 50.0, 1.0)  # 归一化
        
        return score / 3.0
    
    @staticmethod
    def calculate_growth_factor(revenue_growth: float, profit_growth: float) -> float:
        """成长因子"""
        score = 0.0
        count = 0
        
        if revenue_growth is not None:
            score += min(revenue_growth / 30.0, 1.0)  # 归一化
            count += 1
        if profit_growth is not None:
            score += min(profit_growth / 30.0, 1.0)
            count += 1
        
        return score / count if count > 0 else 0.0
    
    @staticmethod
    def calculate_profitability_factor(
        net_profit_margin: float,
        roe: float,
        roa: float = None
    ) -> float:
        """盈利能力因子"""
        score = 0.0
        count = 0
        
        if net_profit_margin:
            score += min(net_profit_margin / 20.0, 1.0)
            count += 1
        if roe:
            score += min(roe / 20.0, 1.0)
            count += 1
        if roa:
            score += min(roa / 10.0, 1.0)
            count += 1
        
        return score / count if count > 0 else 0.0
    
    @staticmethod
    def calculate_leverage_factor(debt_ratio: float, current_ratio: float = None) -> float:
        """杠杆因子"""
        score = 0.0
        count = 0
        
        if debt_ratio is not None:
            # 负债率适中最好（30-60%）
            if 0.3 <= debt_ratio <= 0.6:
                score += 1.0
            elif debt_ratio < 0.3:
                score += 0.7
            else:
                score += max(0, 1.0 - (debt_ratio - 0.6) / 0.4)
            count += 1
        
        if current_ratio:
            # 流动比率>1.5较好
            score += min(current_ratio / 2.0, 1.0)
            count += 1
        
        return score / count if count > 0 else 0.0
    
    # ========== 风格因子 ==========
    
    @staticmethod
    def calculate_size_factor(market_cap: float) -> float:
        """规模因子（市值）"""
        if not market_cap or market_cap <= 0:
            return 0.0
        # 对数市值
        return np.log(market_cap)
    
    @staticmethod
    def calculate_beta_factor(
        stock_returns: List[float],
        market_returns: List[float]
    ) -> float:
        """Beta因子"""
        if len(stock_returns) < 20 or len(market_returns) < 20:
            return 1.0
        
        # 对齐长度
        min_len = min(len(stock_returns), len(market_returns))
        stock_ret = np.array(stock_returns[-min_len:])
        market_ret = np.array(market_returns[-min_len:])
        
        # 计算协方差和方差
        covariance = np.cov(stock_ret, market_ret)[0, 1]
        market_variance = np.var(market_ret)
        
        if market_variance == 0:
            return 1.0
        
        return covariance / market_variance
    
    @staticmethod
    def calculate_liquidity_factor(volumes: List[float], market_caps: List[float]) -> float:
        """流动性因子（换手率）"""
        if not volumes or not market_caps:
            return 0.0
        
        # 平均换手率
        turnover_rates = []
        for vol, cap in zip(volumes[-20:], market_caps[-20:]):
            if cap > 0:
                turnover_rates.append(vol / cap)
        
        return np.mean(turnover_rates) if turnover_rates else 0.0
    
    # ========== 因子IC计算 ==========
    
    @staticmethod
    def calculate_factor_ic(
        factor_values: List[float],
        future_returns: List[float]
    ) -> Dict[str, float]:
        """计算因子IC（信息系数）"""
        if len(factor_values) != len(future_returns):
            return {'ic': 0.0, 'rank_ic': 0.0}
        
        factor_arr = np.array(factor_values)
        returns_arr = np.array(future_returns)
        
        # 去除NaN
        mask = ~(np.isnan(factor_arr) | np.isnan(returns_arr))
        factor_arr = factor_arr[mask]
        returns_arr = returns_arr[mask]
        
        if len(factor_arr) < 10:
            return {'ic': 0.0, 'rank_ic': 0.0}
        
        # Pearson相关系数（IC）
        ic = np.corrcoef(factor_arr, returns_arr)[0, 1]
        
        # Spearman秩相关系数（Rank IC）
        from scipy.stats import spearmanr
        rank_ic, _ = spearmanr(factor_arr, returns_arr)
        
        return {
            'ic': float(ic) if not np.isnan(ic) else 0.0,
            'rank_ic': float(rank_ic) if not np.isnan(rank_ic) else 0.0,
        }
    
    # ========== 因子分组回测 ==========
    
    @staticmethod
    def backtest_factor(
        codes: List[str],
        factor_values: Dict[str, float],
        returns_dict: Dict[str, List[float]],
        groups: int = 5,
        holding_days: int = 20
    ) -> Dict[str, Any]:
        """因子分组回测"""
        # 按因子值分组
        sorted_codes = sorted(codes, key=lambda c: factor_values.get(c, 0))
        group_size = len(sorted_codes) // groups
        
        group_returns = []
        
        for i in range(groups):
            start_idx = i * group_size
            end_idx = start_idx + group_size if i < groups - 1 else len(sorted_codes)
            group_codes = sorted_codes[start_idx:end_idx]
            
            # 计算组合收益
            group_ret = []
            for code in group_codes:
                if code in returns_dict:
                    rets = returns_dict[code][:holding_days]
                    if rets:
                        group_ret.append(np.mean(rets))
            
            avg_return = np.mean(group_ret) if group_ret else 0.0
            group_returns.append(avg_return)
        
        # 多空组合收益
        long_short_return = group_returns[-1] - group_returns[0] if len(group_returns) >= 2 else 0.0
        
        return {
            'group_returns': group_returns,
            'long_short_return': long_short_return,
            'monotonicity': _check_monotonicity(group_returns),
        }


def _check_monotonicity(values: List[float]) -> float:
    """检查单调性（1表示完全单调递增，-1表示完全单调递减）"""
    if len(values) < 2:
        return 0.0
    
    increasing = sum(1 for i in range(len(values)-1) if values[i+1] > values[i])
    decreasing = sum(1 for i in range(len(values)-1) if values[i+1] < values[i])
    
    total = len(values) - 1
    return (increasing - decreasing) / total if total > 0 else 0.0


factor_calculator = FactorCalculator()
