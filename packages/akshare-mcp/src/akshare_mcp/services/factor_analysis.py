"""
因子分析服务 - IC计算、分组回测、因子评估
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from scipy import stats
from numba import jit


class FactorAnalyzer:
    """因子分析器"""
    
    @staticmethod
    def calculate_ic(
        factor_values: List[float],
        forward_returns: List[float],
        method: str = 'pearson'
    ) -> Dict[str, float]:
        """
        计算因子IC (Information Coefficient)
        
        Args:
            factor_values: 因子值列表
            forward_returns: 未来收益率列表
            method: 相关系数方法 ('pearson' 或 'spearman')
        
        Returns:
            IC统计信息
        """
        if len(factor_values) != len(forward_returns):
            raise ValueError("Factor values and returns must have same length")
        
        factor_values = np.array(factor_values)
        forward_returns = np.array(forward_returns)
        
        # 移除NaN值
        mask = ~(np.isnan(factor_values) | np.isnan(forward_returns))
        factor_values = factor_values[mask]
        forward_returns = forward_returns[mask]
        
        if len(factor_values) < 2:
            return {'ic': 0.0, 'ic_ir': 0.0, 'p_value': 1.0}
        
        # 计算IC
        if method == 'pearson':
            ic, p_value = stats.pearsonr(factor_values, forward_returns)
        elif method == 'spearman':
            ic, p_value = stats.spearmanr(factor_values, forward_returns)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return {
            'ic': float(ic),
            'p_value': float(p_value),
            'sample_size': len(factor_values),
        }
    
    @staticmethod
    def calculate_ic_series(
        factor_df: pd.DataFrame,
        return_df: pd.DataFrame,
        periods: List[int] = [1, 5, 10, 20]
    ) -> Dict[str, Any]:
        """
        计算IC时间序列
        
        Args:
            factor_df: 因子DataFrame (index=date, columns=codes)
            return_df: 收益率DataFrame (index=date, columns=codes)
            periods: 预测周期列表
        
        Returns:
            IC统计信息
        """
        ic_series = {}
        
        for period in periods:
            ics = []
            dates = []
            
            for date in factor_df.index[:-period]:
                factor_values = factor_df.loc[date].values
                forward_returns = return_df.loc[date:].iloc[period].values
                
                # 计算当期IC
                mask = ~(np.isnan(factor_values) | np.isnan(forward_returns))
                if np.sum(mask) >= 10:  # 至少10个样本
                    ic, _ = stats.spearmanr(
                        factor_values[mask],
                        forward_returns[mask]
                    )
                    ics.append(ic)
                    dates.append(date)
            
            if ics:
                ic_series[f'period_{period}'] = {
                    'mean_ic': float(np.mean(ics)),
                    'std_ic': float(np.std(ics)),
                    'ic_ir': float(np.mean(ics) / np.std(ics)) if np.std(ics) > 0 else 0.0,
                    'positive_ratio': float(np.sum(np.array(ics) > 0) / len(ics)),
                    'ic_series': ics,
                    'dates': dates,
                }
        
        return ic_series
    
    @staticmethod
    def factor_group_backtest(
        factor_values: np.ndarray,
        returns: np.ndarray,
        n_groups: int = 5
    ) -> Dict[str, Any]:
        """
        因子分组回测
        
        Args:
            factor_values: 因子值数组 (n_stocks,)
            returns: 收益率数组 (n_stocks,)
            n_groups: 分组数量
        
        Returns:
            分组回测结果
        """
        # 移除NaN
        mask = ~(np.isnan(factor_values) | np.isnan(returns))
        factor_values = factor_values[mask]
        returns = returns[mask]
        
        if len(factor_values) < n_groups:
            return {'error': 'Insufficient data for grouping'}
        
        # 按因子值分组
        sorted_indices = np.argsort(factor_values)
        group_size = len(sorted_indices) // n_groups
        
        group_returns = []
        for i in range(n_groups):
            start_idx = i * group_size
            end_idx = (i + 1) * group_size if i < n_groups - 1 else len(sorted_indices)
            group_indices = sorted_indices[start_idx:end_idx]
            group_return = np.mean(returns[group_indices])
            group_returns.append(float(group_return))
        
        # 多空组合收益（最高组 - 最低组）
        long_short_return = group_returns[-1] - group_returns[0]
        
        return {
            'group_returns': group_returns,
            'long_short_return': float(long_short_return),
            'monotonicity': FactorAnalyzer._calculate_monotonicity(group_returns),
        }
    
    @staticmethod
    def _calculate_monotonicity(group_returns: List[float]) -> float:
        """计算单调性（组间收益是否单调递增）"""
        if len(group_returns) < 2:
            return 0.0
        
        increasing = sum(1 for i in range(len(group_returns) - 1) if group_returns[i+1] > group_returns[i])
        return increasing / (len(group_returns) - 1)
    
    @staticmethod
    def factor_turnover(
        factor_df: pd.DataFrame,
        top_n: int = 50
    ) -> Dict[str, float]:
        """
        计算因子换手率
        
        Args:
            factor_df: 因子DataFrame (index=date, columns=codes)
            top_n: 选取前N只股票
        
        Returns:
            换手率统计
        """
        turnovers = []
        
        for i in range(1, len(factor_df)):
            prev_top = set(factor_df.iloc[i-1].nlargest(top_n).index)
            curr_top = set(factor_df.iloc[i].nlargest(top_n).index)
            
            # 换手率 = 变化的股票数 / 总数
            turnover = len(prev_top.symmetric_difference(curr_top)) / top_n
            turnovers.append(turnover)
        
        return {
            'mean_turnover': float(np.mean(turnovers)),
            'std_turnover': float(np.std(turnovers)),
            'max_turnover': float(np.max(turnovers)),
        }
    
    @staticmethod
    def factor_decay(
        factor_values: np.ndarray,
        returns_matrix: np.ndarray,
        max_period: int = 20
    ) -> Dict[str, List[float]]:
        """
        因子衰减分析
        
        Args:
            factor_values: 因子值 (n_stocks,)
            returns_matrix: 收益率矩阵 (n_periods, n_stocks)
            max_period: 最大预测周期
        
        Returns:
            各周期的IC值
        """
        ics = []
        
        for period in range(1, min(max_period + 1, len(returns_matrix))):
            forward_returns = returns_matrix[period]
            
            mask = ~(np.isnan(factor_values) | np.isnan(forward_returns))
            if np.sum(mask) >= 10:
                ic, _ = stats.spearmanr(
                    factor_values[mask],
                    forward_returns[mask]
                )
                ics.append(float(ic))
            else:
                ics.append(0.0)
        
        return {
            'periods': list(range(1, len(ics) + 1)),
            'ics': ics,
            'half_life': FactorAnalyzer._calculate_half_life(ics),
        }
    
    @staticmethod
    def _calculate_half_life(ics: List[float]) -> int:
        """计算因子半衰期（IC降至初始值一半的周期）"""
        if not ics or ics[0] == 0:
            return 0
        
        initial_ic = abs(ics[0])
        half_ic = initial_ic / 2
        
        for i, ic in enumerate(ics):
            if abs(ic) <= half_ic:
                return i + 1
        
        return len(ics)
    
    @staticmethod
    def factor_correlation_matrix(
        factors_dict: Dict[str, np.ndarray]
    ) -> pd.DataFrame:
        """
        计算因子相关系数矩阵
        
        Args:
            factors_dict: 因子字典 {factor_name: factor_values}
        
        Returns:
            相关系数矩阵
        """
        factor_names = list(factors_dict.keys())
        n_factors = len(factor_names)
        
        corr_matrix = np.zeros((n_factors, n_factors))
        
        for i, name1 in enumerate(factor_names):
            for j, name2 in enumerate(factor_names):
                if i == j:
                    corr_matrix[i, j] = 1.0
                elif i < j:
                    values1 = factors_dict[name1]
                    values2 = factors_dict[name2]
                    
                    mask = ~(np.isnan(values1) | np.isnan(values2))
                    if np.sum(mask) >= 10:
                        corr, _ = stats.pearsonr(values1[mask], values2[mask])
                        corr_matrix[i, j] = corr
                        corr_matrix[j, i] = corr
        
        return pd.DataFrame(
            corr_matrix,
            index=factor_names,
            columns=factor_names
        )
    
    @staticmethod
    def factor_importance(
        factors_dict: Dict[str, np.ndarray],
        returns: np.ndarray,
        method: str = 'ic'
    ) -> Dict[str, float]:
        """
        计算因子重要性
        
        Args:
            factors_dict: 因子字典
            returns: 收益率数组
            method: 评估方法 ('ic' 或 'regression')
        
        Returns:
            因子重要性得分
        """
        importance = {}
        
        if method == 'ic':
            for name, values in factors_dict.items():
                mask = ~(np.isnan(values) | np.isnan(returns))
                if np.sum(mask) >= 10:
                    ic, _ = stats.spearmanr(values[mask], returns[mask])
                    importance[name] = abs(float(ic))
                else:
                    importance[name] = 0.0
        
        elif method == 'regression':
            # 简化的回归重要性（实际应使用多元回归）
            for name, values in factors_dict.items():
                mask = ~(np.isnan(values) | np.isnan(returns))
                if np.sum(mask) >= 10:
                    slope, _, r_value, _, _ = stats.linregress(values[mask], returns[mask])
                    importance[name] = abs(float(r_value))
                else:
                    importance[name] = 0.0
        
        # 归一化
        total = sum(importance.values())
        if total > 0:
            importance = {k: v / total for k, v in importance.items()}
        
        return importance
    
    @staticmethod
    def factor_performance_summary(
        factor_name: str,
        ic_stats: Dict[str, float],
        group_backtest: Dict[str, Any],
        turnover: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        因子表现综合评估
        
        Returns:
            综合评估结果
        """
        # 计算综合得分
        ic_score = abs(ic_stats.get('ic', 0)) * 100
        ir_score = abs(ic_stats.get('ic_ir', 0)) * 50
        ls_score = abs(group_backtest.get('long_short_return', 0)) * 1000
        mono_score = group_backtest.get('monotonicity', 0) * 50
        turnover_penalty = turnover.get('mean_turnover', 0) * 20
        
        total_score = ic_score + ir_score + ls_score + mono_score - turnover_penalty
        
        # 评级
        if total_score >= 80:
            rating = 'A'
        elif total_score >= 60:
            rating = 'B'
        elif total_score >= 40:
            rating = 'C'
        else:
            rating = 'D'
        
        return {
            'factor_name': factor_name,
            'rating': rating,
            'total_score': float(total_score),
            'ic_stats': ic_stats,
            'group_backtest': group_backtest,
            'turnover': turnover,
            'recommendation': 'Strong' if rating in ['A', 'B'] else 'Weak',
        }


# 全局实例
factor_analyzer = FactorAnalyzer()
