"""
LLM Alpha挖掘模块

使用LLM生成和评估因子候选：
- 因子候选生成
- 因子有效性评估
- Alpha衰减检测
- 因子组合优化

Author: AKShare MCP Server
Version: 2.0
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import json


class LLMAlphaMiner:
    """LLM Alpha挖掘器"""
    
    def __init__(self):
        """初始化LLM Alpha挖掘器"""
        self.factor_candidates = []
        self.evaluation_results = {}
    
    def generate_factor_candidates(
        self,
        market_data: pd.DataFrame,
        news_data: Optional[List[Dict]] = None,
        num_candidates: int = 10
    ) -> List[Dict[str, Any]]:
        """
        使用LLM生成候选因子
        
        Args:
            market_data: 市场数据（包含价格、成交量等）
            news_data: 新闻数据（可选）
            num_candidates: 生成候选因子数量
            
        Returns:
            候选因子列表，每个因子包含：
            {
                'factor_id': 因子ID,
                'name': 因子名称,
                'description': 因子描述,
                'formula': 因子计算公式,
                'category': 因子类别（momentum/reversal/value等）
            }
        """
        # 模拟LLM生成因子候选
        # 实际应用中，这里会调用LLM API
        
        candidates = []
        
        # 示例：生成一些基于技术指标的因子候选
        factor_templates = [
            {
                'name': 'Enhanced_Momentum',
                'description': '增强动量因子：结合价格动量和成交量动量',
                'formula': '(close/close.shift(20) - 1) * (volume/volume.shift(20))',
                'category': 'momentum'
            },
            {
                'name': 'Volatility_Adjusted_Return',
                'description': '波动率调整收益：收益率除以波动率',
                'formula': '(close/close.shift(20) - 1) / close.rolling(20).std()',
                'category': 'risk_adjusted'
            },
            {
                'name': 'Volume_Price_Divergence',
                'description': '量价背离因子：价格变化与成交量变化的差异',
                'formula': '(close/close.shift(5) - 1) - (volume/volume.shift(5) - 1)',
                'category': 'divergence'
            },
            {
                'name': 'Trend_Strength',
                'description': '趋势强度因子：价格相对于移动平均线的位置',
                'formula': '(close - close.rolling(20).mean()) / close.rolling(20).std()',
                'category': 'trend'
            },
            {
                'name': 'Liquidity_Premium',
                'description': '流动性溢价因子：成交额相对于市值的比例',
                'formula': '(volume * close) / market_cap',
                'category': 'liquidity'
            }
        ]
        
        for i, template in enumerate(factor_templates[:num_candidates]):
            candidate = {
                'factor_id': f'LLM_FACTOR_{i+1:03d}',
                'name': template['name'],
                'description': template['description'],
                'formula': template['formula'],
                'category': template['category'],
                'created_at': datetime.now().isoformat()
            }
            candidates.append(candidate)
        
        self.factor_candidates.extend(candidates)
        return candidates
    
    def evaluate_factor(
        self,
        factor_values: pd.Series,
        returns: pd.Series,
        method: str = 'ic'
    ) -> Dict[str, float]:
        """
        评估因子有效性
        
        Args:
            factor_values: 因子值序列
            returns: 收益率序列
            method: 评估方法（ic/rank_ic/sharpe）
            
        Returns:
            {
                'ic': IC值,
                'rank_ic': Rank IC值,
                'ic_ir': IC信息比率,
                'positive_rate': IC为正的比例,
                't_stat': t统计量,
                'p_value': p值
            }
        """
        # 对齐数据
        aligned_data = pd.DataFrame({
            'factor': factor_values,
            'return': returns
        }).dropna()
        
        if len(aligned_data) < 10:
            return {
                'ic': 0.0,
                'rank_ic': 0.0,
                'ic_ir': 0.0,
                'positive_rate': 0.0,
                't_stat': 0.0,
                'p_value': 1.0
            }
        
        # 计算IC
        ic = aligned_data['factor'].corr(aligned_data['return'])
        
        # 计算Rank IC
        rank_ic = aligned_data['factor'].corr(aligned_data['return'], method='spearman')
        
        # 计算IC序列（滚动窗口）
        window = 20
        ic_series = []
        for i in range(window, len(aligned_data)):
            window_data = aligned_data.iloc[i-window:i]
            window_ic = window_data['factor'].corr(window_data['return'])
            ic_series.append(window_ic)
        
        ic_series = pd.Series(ic_series)
        
        # 计算IC IR
        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0.0
        
        # 计算IC为正的比例
        positive_rate = (ic_series > 0).sum() / len(ic_series) if len(ic_series) > 0 else 0.0
        
        # 计算t统计量
        t_stat = ic_mean / (ic_std / np.sqrt(len(ic_series))) if ic_std > 0 else 0.0
        
        # 计算p值（简化版）
        from scipy import stats
        p_value = 2 * (1 - stats.t.cdf(abs(t_stat), len(ic_series) - 1))
        
        return {
            'ic': float(ic),
            'rank_ic': float(rank_ic),
            'ic_ir': float(ic_ir),
            'positive_rate': float(positive_rate),
            't_stat': float(t_stat),
            'p_value': float(p_value)
        }

    def detect_alpha_decay(
        self,
        factor_values: pd.Series,
        returns: pd.Series,
        window: int = 60
    ) -> Dict[str, Any]:
        """
        检测因子Alpha衰减

        Args:
            factor_values: 因子值序列
            returns: 收益率序列
            window: 滚动窗口大小

        Returns:
            {
                'is_decaying': 是否衰减,
                'decay_rate': 衰减率,
                'half_life': 半衰期（天数）,
                'recent_ic': 最近IC,
                'historical_ic': 历史IC
            }
        """
        # 对齐数据
        aligned_data = pd.DataFrame({
            'factor': factor_values,
            'return': returns
        }).dropna()

        if len(aligned_data) < window * 2:
            return {
                'is_decaying': False,
                'decay_rate': 0.0,
                'half_life': np.inf,
                'recent_ic': 0.0,
                'historical_ic': 0.0
            }

        # 计算滚动IC
        ic_series = []
        for i in range(window, len(aligned_data)):
            window_data = aligned_data.iloc[i-window:i]
            window_ic = window_data['factor'].corr(window_data['return'])
            ic_series.append(window_ic)

        ic_series = pd.Series(ic_series)

        # 计算最近和历史IC
        recent_ic = ic_series.iloc[-window//2:].mean()
        historical_ic = ic_series.iloc[:window//2].mean()

        # 计算衰减率
        if historical_ic != 0:
            decay_rate = (historical_ic - recent_ic) / abs(historical_ic)
        else:
            decay_rate = 0.0

        # 判断是否衰减（最近IC显著低于历史IC）
        is_decaying = decay_rate > 0.3  # 衰减超过30%

        # 计算半衰期（简化版：假设指数衰减）
        if decay_rate > 0:
            half_life = np.log(2) / np.log(1 + decay_rate) * window
        else:
            half_life = np.inf

        return {
            'is_decaying': bool(is_decaying),
            'decay_rate': float(decay_rate),
            'half_life': float(half_life),
            'recent_ic': float(recent_ic),
            'historical_ic': float(historical_ic)
        }

    def optimize_factor_combination(
        self,
        factors: Dict[str, pd.Series],
        returns: pd.Series,
        method: str = 'ic_weight'
    ) -> Dict[str, float]:
        """
        优化因子组合权重

        Args:
            factors: 因子字典 {factor_name: factor_values}
            returns: 收益率序列
            method: 优化方法（ic_weight/equal_weight/max_sharpe）

        Returns:
            因子权重字典 {factor_name: weight}
        """
        if method == 'equal_weight':
            # 等权重
            n = len(factors)
            return {name: 1.0/n for name in factors.keys()}

        elif method == 'ic_weight':
            # IC加权
            ic_values = {}
            for name, factor_values in factors.items():
                evaluation = self.evaluate_factor(factor_values, returns)
                ic_values[name] = abs(evaluation['ic'])

            # 归一化
            total_ic = sum(ic_values.values())
            if total_ic > 0:
                return {name: ic/total_ic for name, ic in ic_values.items()}
            else:
                n = len(factors)
                return {name: 1.0/n for name in factors.keys()}

        elif method == 'max_sharpe':
            # 最大化夏普比率（简化版）
            from scipy.optimize import minimize

            # 计算因子收益矩阵
            factor_returns = pd.DataFrame({
                name: factor_values * returns
                for name, factor_values in factors.items()
            }).dropna()

            if len(factor_returns) < 10:
                n = len(factors)
                return {name: 1.0/n for name in factors.keys()}

            # 计算协方差矩阵
            cov_matrix = factor_returns.cov()
            mean_returns = factor_returns.mean()

            # 优化目标：最大化夏普比率
            def neg_sharpe(weights):
                portfolio_return = np.dot(weights, mean_returns)
                portfolio_vol = np.sqrt(np.dot(weights, np.dot(cov_matrix, weights)))
                return -portfolio_return / portfolio_vol if portfolio_vol > 0 else 0

            # 约束条件
            n = len(factors)
            constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
            bounds = tuple((0, 1) for _ in range(n))
            initial_weights = np.array([1.0/n] * n)

            # 优化
            result = minimize(
                neg_sharpe,
                initial_weights,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints
            )

            if result.success:
                return {name: float(weight) for name, weight in zip(factors.keys(), result.x)}
            else:
                n = len(factors)
                return {name: 1.0/n for name in factors.keys()}

        else:
            raise ValueError(f"Unknown method: {method}")

    def get_top_factors(
        self,
        factors: Dict[str, pd.Series],
        returns: pd.Series,
        top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取表现最好的因子

        Args:
            factors: 因子字典
            returns: 收益率序列
            top_n: 返回前N个因子

        Returns:
            排序后的因子列表
        """
        factor_scores = []

        for name, factor_values in factors.items():
            evaluation = self.evaluate_factor(factor_values, returns)
            decay = self.detect_alpha_decay(factor_values, returns)

            # 综合评分：IC * IC_IR * (1 - decay_rate)
            score = abs(evaluation['ic']) * evaluation['ic_ir'] * (1 - decay['decay_rate'])

            factor_scores.append({
                'name': name,
                'score': float(score),
                'ic': evaluation['ic'],
                'ic_ir': evaluation['ic_ir'],
                'is_decaying': decay['is_decaying'],
                'decay_rate': decay['decay_rate']
            })

        # 按评分排序
        factor_scores.sort(key=lambda x: x['score'], reverse=True)

        return factor_scores[:top_n]


# 创建全局实例
llm_alpha_miner = LLMAlphaMiner()

