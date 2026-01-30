"""组合管理工具"""

from typing import List, Dict, Any, Optional
from ..services.portfolio_optimizer import portfolio_optimizer
from ..services.risk_model import risk_model
from ..storage import get_db
from ..utils import ok, fail
import numpy as np


def register(mcp):
    """注册组合管理工具"""
    
    @mcp.tool()
    async def optimize_portfolio(
        stocks: List[str],
        method: str = 'equal_weight',
        lookback_days: int = 252,
        risk_aversion: float = 1.0,
        risk_free_rate: float = 0.03,
        market_weights: Optional[List[float]] = None,
        views: Optional[List[Dict[str, Any]]] = None,
        risk_budgets: Optional[List[float]] = None
    ):
        """
        组合优化
        
        Args:
            stocks: 股票代码列表
            method: 优化方法
                - 'equal_weight': 等权重
                - 'risk_parity': 风险平价
                - 'mean_variance': 均值方差优化
                - 'black_litterman': Black-Litterman模型
                - 'risk_budget': 风险预算优化
                - 'max_sharpe': 最大夏普比率
            lookback_days: 回溯天数
            risk_aversion: 风险厌恶系数（用于均值方差和Black-Litterman）
            risk_free_rate: 无风险利率（用于夏普比率计算）
            market_weights: 市场权重（用于Black-Litterman）
            views: 主观观点（用于Black-Litterman）
                [{'type': 'absolute', 'asset': 0, 'return': 0.10},
                 {'type': 'relative', 'assets': [0, 1], 'return': 0.05}]
            risk_budgets: 风险预算（用于风险预算优化）
        
        Returns:
            最优权重和组合指标
        """
        try:
            if method == 'equal_weight':
                weights = portfolio_optimizer.optimize_equal_weight(stocks)
                return ok({
                    'weights': weights,
                    'method': method,
                })
            
            # 获取历史数据
            db = get_db()
            returns_list = []
            
            for code in stocks:
                klines = await db.get_klines(code, limit=lookback_days)
                if klines:
                    closes = [k['close'] for k in klines]
                    returns = np.diff(closes) / closes[:-1]
                    returns_list.append(returns)
            
            if not returns_list:
                return fail('No data available')
            
            # 对齐长度
            min_len = min(len(r) for r in returns_list)
            returns_matrix = np.array([r[:min_len] for r in returns_list])
            
            # 计算预期收益率（历史平均）
            expected_returns = np.mean(returns_matrix, axis=1)
            
            # 根据方法选择优化器
            if method == 'risk_parity':
                weights = portfolio_optimizer.optimize_risk_parity(stocks, returns_matrix)
                return ok({
                    'weights': weights,
                    'method': method,
                })
            
            elif method == 'mean_variance':
                weights = portfolio_optimizer.optimize_mean_variance(
                    stocks, 
                    returns_matrix, 
                    expected_returns,
                    risk_aversion=risk_aversion
                )
                return ok({
                    'weights': weights,
                    'method': method,
                    'risk_aversion': risk_aversion,
                })
            
            elif method == 'black_litterman':
                # 默认市场权重为等权
                if market_weights is None:
                    market_weights = np.array([1.0 / len(stocks)] * len(stocks))
                else:
                    market_weights = np.array(market_weights)
                
                # 默认观点为空
                if views is None:
                    views = []
                
                result = portfolio_optimizer.optimize_black_litterman(
                    stocks,
                    returns_matrix,
                    market_weights,
                    views,
                    risk_aversion=risk_aversion
                )
                
                return ok({
                    'weights': result['weights'],
                    'posterior_returns': result['posterior_returns'],
                    'expected_return': f"{result['expected_return']*100:.2f}%",
                    'volatility': f"{result['volatility']*100:.2f}%",
                    'sharpe_ratio': f"{result['sharpe_ratio']:.2f}",
                    'method': method,
                })
            
            elif method == 'risk_budget':
                result = portfolio_optimizer.optimize_risk_budget(
                    stocks,
                    returns_matrix,
                    risk_budgets=risk_budgets
                )
                
                return ok({
                    'weights': result['weights'],
                    'risk_contributions': result['risk_contributions'],
                    'portfolio_volatility': f"{result['portfolio_volatility']*100:.2f}%",
                    'method': method,
                })
            
            elif method == 'max_sharpe':
                result = portfolio_optimizer.optimize_max_sharpe(
                    stocks,
                    returns_matrix,
                    expected_returns,
                    risk_free_rate=risk_free_rate
                )
                
                return ok({
                    'weights': result['weights'],
                    'expected_return': f"{result['expected_return']*100:.2f}%",
                    'volatility': f"{result['volatility']*100:.2f}%",
                    'sharpe_ratio': f"{result['sharpe_ratio']:.2f}",
                    'method': method,
                })
            
            else:
                return fail(f'Unknown method: {method}. Supported: equal_weight, risk_parity, mean_variance, black_litterman, risk_budget, max_sharpe')
        
        except Exception as e:
            return fail(str(e))
    
    @mcp.tool()
    async def analyze_portfolio_risk(
        holdings: List[Dict[str, Any]],
        lookback_days: int = 252
    ):
        """
        分析组合风险
        
        Args:
            holdings: 持仓列表 [{'code': '600519', 'weight': 0.3}, ...]
            lookback_days: 回溯天数
        """
        try:
            db = get_db()
            returns_list = []
            
            for holding in holdings:
                code = holding['code']
                klines = await db.get_klines(code, limit=lookback_days)
                if klines:
                    closes = [k['close'] for k in klines]
                    returns = np.diff(closes) / closes[:-1]
                    returns_list.append(returns)
            
            if not returns_list:
                return fail('No data available')
            
            min_len = min(len(r) for r in returns_list)
            returns_matrix = np.array([r[:min_len] for r in returns_list])
            
            # 计算组合收益率
            weights = np.array([h['weight'] for h in holdings])
            portfolio_returns = np.dot(weights, returns_matrix)
            
            # 计算VaR
            var_result = risk_model.calculate_var(portfolio_returns.tolist())
            
            # 计算组合风险
            risk_result = risk_model.calculate_portfolio_risk(holdings, returns_matrix)
            
            return ok({
                'var': var_result,
                'risk': risk_result,
            })
        
        except Exception as e:
            return fail(str(e))

    @mcp.tool()
    async def stress_test_portfolio(
        holdings: List[Dict[str, Any]],
        scenarios: Optional[List[str]] = None
    ):
        """
        组合压力测试
        
        Args:
            holdings: 持仓列表 [{'code': '600519', 'weight': 0.3}, ...]
            scenarios: 压力场景 ['market_crash', 'sector_rotation']
        """
        try:
            if not scenarios:
                scenarios = ['market_crash', 'sector_rotation']
            
            results = {}
            
            for scenario in scenarios:
                if scenario == 'market_crash':
                    # 模拟市场暴跌-30%
                    loss = sum(h['weight'] * 0.30 for h in holdings)
                    results['market_crash'] = {
                        'scenario': '市场暴跌-30%',
                        'portfolio_loss': f'{loss * 100:.1f}%',
                        'impact': 'severe' if loss > 0.25 else 'moderate',
                    }
                
                elif scenario == 'sector_rotation':
                    # 模拟板块轮动
                    results['sector_rotation'] = {
                        'scenario': '板块轮动',
                        'impact': 'moderate',
                        'recommendation': '建议分散投资不同板块',
                    }
            
            return ok({
                'holdings_count': len(holdings),
                'stress_tests': results,
            })
        
        except Exception as e:
            return fail(str(e))
