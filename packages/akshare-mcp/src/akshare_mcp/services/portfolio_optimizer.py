"""组合优化 - 均值方差优化、Black-Litterman、风险预算"""

from typing import List, Dict, Any
import numpy as np

# 导入完整的优化器
from .portfolio_optimization import portfolio_optimizer as advanced_optimizer


class PortfolioOptimizer:
    """组合优化器（简化接口）"""
    
    @staticmethod
    def optimize_equal_weight(stocks: List[str]) -> Dict[str, float]:
        """等权重优化"""
        n = len(stocks)
        weight = 1.0 / n
        return {code: weight for code in stocks}
    
    @staticmethod
    def optimize_risk_parity(
        stocks: List[str],
        returns_matrix: np.ndarray
    ) -> Dict[str, float]:
        """
        风险平价优化
        
        Args:
            stocks: 股票代码列表
            returns_matrix: 收益率矩阵 (n_stocks, n_periods)
        
        Returns:
            风险平价权重
        """
        cov_matrix = np.cov(returns_matrix)
        
        # 使用高级优化器
        result = advanced_optimizer.risk_parity(cov_matrix)
        
        if result['success']:
            weights = result['weights']
            return {code: float(w) for code, w in zip(stocks, weights)}
        else:
            # Fallback：简化实现（逆波动率加权）
            variances = np.diag(cov_matrix)
            inv_vol = 1.0 / np.sqrt(variances)
            weights = inv_vol / np.sum(inv_vol)
            return {code: float(w) for code, w in zip(stocks, weights)}
    
    @staticmethod
    def optimize_mean_variance(
        stocks: List[str],
        returns_matrix: np.ndarray,
        expected_returns: np.ndarray,
        risk_aversion: float = 1.0
    ) -> Dict[str, float]:
        """
        均值方差优化（马科维茨模型）
        
        Args:
            stocks: 股票代码列表
            returns_matrix: 收益率矩阵 (n_stocks, n_periods)
            expected_returns: 预期收益率 (n_stocks,)
            risk_aversion: 风险厌恶系数
        
        Returns:
            最优权重
        """
        cov_matrix = np.cov(returns_matrix)
        
        # 使用高级优化器
        result = advanced_optimizer.mean_variance_optimization(
            expected_returns=expected_returns,
            cov_matrix=cov_matrix,
            risk_aversion=risk_aversion
        )
        
        if result['success']:
            weights = result['weights']
            return {code: float(w) for code, w in zip(stocks, weights)}
        else:
            # Fallback：最小方差组合
            inv_cov = np.linalg.inv(cov_matrix)
            ones = np.ones(len(stocks))
            weights = np.dot(inv_cov, ones) / np.dot(ones, np.dot(inv_cov, ones))
            weights = weights / np.sum(weights)
            return {code: float(w) for code, w in zip(stocks, weights)}
    
    @staticmethod
    def optimize_black_litterman(
        stocks: List[str],
        returns_matrix: np.ndarray,
        market_weights: np.ndarray,
        views: List[Dict[str, Any]],
        risk_aversion: float = 2.5,
        tau: float = 0.05
    ) -> Dict[str, Any]:
        """
        Black-Litterman模型优化
        
        Args:
            stocks: 股票代码列表
            returns_matrix: 收益率矩阵 (n_stocks, n_periods)
            market_weights: 市场权重 (n_stocks,)
            views: 主观观点列表
                [{'type': 'absolute', 'asset': 0, 'return': 0.10},
                 {'type': 'relative', 'assets': [0, 1], 'return': 0.05}]
            risk_aversion: 风险厌恶系数
            tau: 不确定性参数
        
        Returns:
            后验预期收益和最优权重
        """
        cov_matrix = np.cov(returns_matrix)
        
        # 使用高级优化器
        result = advanced_optimizer.black_litterman(
            market_weights=market_weights,
            cov_matrix=cov_matrix,
            views=views,
            risk_aversion=risk_aversion,
            tau=tau
        )
        
        weights = result['optimal_weights']
        
        return {
            'weights': {code: float(w) for code, w in zip(stocks, weights)},
            'posterior_returns': result['posterior_returns'],
            'expected_return': result['expected_return'],
            'volatility': result['volatility'],
            'sharpe_ratio': result['sharpe_ratio'],
        }
    
    @staticmethod
    def optimize_risk_budget(
        stocks: List[str],
        returns_matrix: np.ndarray,
        risk_budgets: List[float] = None
    ) -> Dict[str, Any]:
        """
        风险预算优化
        
        Args:
            stocks: 股票代码列表
            returns_matrix: 收益率矩阵 (n_stocks, n_periods)
            risk_budgets: 风险预算（默认等权）
        
        Returns:
            风险预算权重
        """
        cov_matrix = np.cov(returns_matrix)
        
        # 默认等权风险预算
        if risk_budgets is None:
            risk_budgets = [1.0 / len(stocks)] * len(stocks)
        
        target_risk_contributions = np.array(risk_budgets)
        
        # 使用高级优化器的风险平价方法
        result = advanced_optimizer.risk_parity(
            cov_matrix=cov_matrix,
            target_risk_contributions=target_risk_contributions
        )
        
        if result['success']:
            weights = result['weights']
            return {
                'weights': {code: float(w) for code, w in zip(stocks, weights)},
                'risk_contributions': result['risk_contributions'],
                'portfolio_volatility': result['portfolio_volatility'],
            }
        else:
            # Fallback：等权
            return {
                'weights': {code: 1.0 / len(stocks) for code in stocks},
                'risk_contributions': risk_budgets,
                'portfolio_volatility': 0.0,
            }
    
    @staticmethod
    def optimize_max_sharpe(
        stocks: List[str],
        returns_matrix: np.ndarray,
        expected_returns: np.ndarray,
        risk_free_rate: float = 0.03
    ) -> Dict[str, Any]:
        """
        最大化夏普比率
        
        Args:
            stocks: 股票代码列表
            returns_matrix: 收益率矩阵 (n_stocks, n_periods)
            expected_returns: 预期收益率 (n_stocks,)
            risk_free_rate: 无风险利率
        
        Returns:
            最大夏普比率组合
        """
        cov_matrix = np.cov(returns_matrix)
        
        # 使用高级优化器
        result = advanced_optimizer.max_sharpe_ratio(
            expected_returns=expected_returns,
            cov_matrix=cov_matrix,
            risk_free_rate=risk_free_rate
        )
        
        if result['success']:
            weights = result['weights']
            return {
                'weights': {code: float(w) for code, w in zip(stocks, weights)},
                'expected_return': result['expected_return'],
                'volatility': result['volatility'],
                'sharpe_ratio': result['sharpe_ratio'],
            }
        else:
            # Fallback：等权
            return {
                'weights': {code: 1.0 / len(stocks) for code in stocks},
                'expected_return': 0.0,
                'volatility': 0.0,
                'sharpe_ratio': 0.0,
            }


portfolio_optimizer = PortfolioOptimizer()

