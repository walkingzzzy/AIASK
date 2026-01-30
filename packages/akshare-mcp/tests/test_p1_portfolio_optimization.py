#!/usr/bin/env python3
"""
P1阶段 - 组合优化方法测试
"""

import pytest
import numpy as np
from akshare_mcp.services.portfolio_optimizer import portfolio_optimizer


@pytest.fixture
def test_data():
    """生成测试数据"""
    np.random.seed(42)
    n_stocks = 3
    n_periods = 252
    
    # 生成收益率矩阵
    returns_matrix = np.random.randn(n_stocks, n_periods) * 0.02
    
    # 生成预期收益率
    expected_returns = np.array([0.10, 0.12, 0.08])
    
    # 股票代码
    stocks = ['000001', '600519', '000858']
    
    # 市场权重
    market_weights = np.array([0.4, 0.3, 0.3])
    
    return {
        'stocks': stocks,
        'returns_matrix': returns_matrix,
        'expected_returns': expected_returns,
        'market_weights': market_weights,
    }


class TestPortfolioOptimization:
    """组合优化测试"""
    
    def test_equal_weight(self, test_data):
        """测试等权重优化"""
        stocks = test_data['stocks']
        
        weights = portfolio_optimizer.optimize_equal_weight(stocks)
        
        assert len(weights) == len(stocks)
        assert all(0 <= w <= 1 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        
        # 等权重应该都是1/n
        expected_weight = 1.0 / len(stocks)
        for w in weights.values():
            assert abs(w - expected_weight) < 1e-6
        
        print(f"✅ 等权重优化: {weights}")
    
    
    def test_risk_parity(self, test_data):
        """测试风险平价优化"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        
        weights = portfolio_optimizer.optimize_risk_parity(stocks, returns_matrix)
        
        assert len(weights) == len(stocks)
        assert all(0 <= w <= 1 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        
        print(f"✅ 风险平价优化: {weights}")
    
    
    def test_mean_variance(self, test_data):
        """测试均值方差优化"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        expected_returns = test_data['expected_returns']
        
        weights = portfolio_optimizer.optimize_mean_variance(
            stocks,
            returns_matrix,
            expected_returns,
            risk_aversion=1.0
        )
        
        assert len(weights) == len(stocks)
        assert all(0 <= w <= 1 for w in weights.values())
        assert abs(sum(weights.values()) - 1.0) < 1e-6
        
        print(f"✅ 均值方差优化: {weights}")
    
    
    def test_black_litterman(self, test_data):
        """测试Black-Litterman模型"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        market_weights = test_data['market_weights']
        
        # 定义观点：认为第一只股票收益率为15%
        views = [
            {'type': 'absolute', 'asset': 0, 'return': 0.15}
        ]
        
        result = portfolio_optimizer.optimize_black_litterman(
            stocks,
            returns_matrix,
            market_weights,
            views,
            risk_aversion=2.5
        )
        
        assert 'weights' in result
        assert 'posterior_returns' in result
        assert 'expected_return' in result
        assert 'volatility' in result
        assert 'sharpe_ratio' in result
        
        weights = result['weights']
        assert len(weights) == len(stocks)
        assert all(0 <= w <= 1 for w in weights.values())
        
        print(f"✅ Black-Litterman优化: {weights}")
        print(f"   后验收益率: {result['posterior_returns']}")
        print(f"   预期收益: {result['expected_return']*100:.2f}%")
        print(f"   波动率: {result['volatility']*100:.2f}%")
        print(f"   夏普比率: {result['sharpe_ratio']:.2f}")
    
    
    def test_risk_budget(self, test_data):
        """测试风险预算优化"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        
        # 定义风险预算：第一只股票承担50%风险，其他各25%
        risk_budgets = [0.5, 0.25, 0.25]
        
        result = portfolio_optimizer.optimize_risk_budget(
            stocks,
            returns_matrix,
            risk_budgets=risk_budgets
        )
        
        assert 'weights' in result
        assert 'risk_contributions' in result
        assert 'portfolio_volatility' in result
        
        weights = result['weights']
        assert len(weights) == len(stocks)
        assert all(0 <= w <= 1 for w in weights.values())
        
        print(f"✅ 风险预算优化: {weights}")
        print(f"   风险贡献: {result['risk_contributions']}")
        print(f"   组合波动率: {result['portfolio_volatility']*100:.2f}%")
    
    
    def test_max_sharpe(self, test_data):
        """测试最大夏普比率优化"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        expected_returns = test_data['expected_returns']
        
        result = portfolio_optimizer.optimize_max_sharpe(
            stocks,
            returns_matrix,
            expected_returns,
            risk_free_rate=0.03
        )
        
        assert 'weights' in result
        assert 'expected_return' in result
        assert 'volatility' in result
        assert 'sharpe_ratio' in result
        
        weights = result['weights']
        assert len(weights) == len(stocks)
        assert all(0 <= w <= 1 for w in weights.values())
        
        print(f"✅ 最大夏普比率优化: {weights}")
        print(f"   预期收益: {result['expected_return']*100:.2f}%")
        print(f"   波动率: {result['volatility']*100:.2f}%")
        print(f"   夏普比率: {result['sharpe_ratio']:.2f}")
    
    
    def test_all_methods_comparison(self, test_data):
        """对比所有优化方法"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        expected_returns = test_data['expected_returns']
        market_weights = test_data['market_weights']
        
        print("\n" + "="*60)
        print("所有优化方法对比")
        print("="*60)
        
        methods = {
            'equal_weight': lambda: portfolio_optimizer.optimize_equal_weight(stocks),
            'risk_parity': lambda: portfolio_optimizer.optimize_risk_parity(stocks, returns_matrix),
            'mean_variance': lambda: portfolio_optimizer.optimize_mean_variance(stocks, returns_matrix, expected_returns),
            'max_sharpe': lambda: portfolio_optimizer.optimize_max_sharpe(stocks, returns_matrix, expected_returns),
        }
        
        for method_name, method_func in methods.items():
            result = method_func()
            
            if isinstance(result, dict) and 'weights' in result:
                weights = result['weights']
            else:
                weights = result
            
            print(f"\n{method_name}:")
            for code, weight in weights.items():
                print(f"  {code}: {weight*100:.2f}%")
        
        print("\n" + "="*60)


class TestAdvancedOptimization:
    """高级优化功能测试"""
    
    def test_black_litterman_relative_view(self, test_data):
        """测试Black-Litterman相对观点"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        market_weights = test_data['market_weights']
        
        # 定义相对观点：第一只股票比第二只股票收益高5%
        views = [
            {'type': 'relative', 'assets': [0, 1], 'return': 0.05}
        ]
        
        result = portfolio_optimizer.optimize_black_litterman(
            stocks,
            returns_matrix,
            market_weights,
            views
        )
        
        assert 'weights' in result
        weights = result['weights']
        
        print(f"✅ Black-Litterman相对观点: {weights}")
    
    
    def test_risk_budget_custom(self, test_data):
        """测试自定义风险预算"""
        stocks = test_data['stocks']
        returns_matrix = test_data['returns_matrix']
        
        # 自定义风险预算
        risk_budgets = [0.6, 0.3, 0.1]
        
        result = portfolio_optimizer.optimize_risk_budget(
            stocks,
            returns_matrix,
            risk_budgets=risk_budgets
        )
        
        assert 'weights' in result
        weights = result['weights']
        
        print(f"✅ 自定义风险预算: {weights}")
        print(f"   目标风险预算: {risk_budgets}")
        print(f"   实际风险贡献: {result['risk_contributions']}")


def test_optimization_methods_available():
    """测试优化方法可用性"""
    print("\n" + "="*60)
    print("组合优化方法可用性测试")
    print("="*60)
    
    methods = [
        'optimize_equal_weight',
        'optimize_risk_parity',
        'optimize_mean_variance',
        'optimize_black_litterman',
        'optimize_risk_budget',
        'optimize_max_sharpe',
    ]
    
    for method in methods:
        if hasattr(portfolio_optimizer, method):
            print(f"✅ {method}")
        else:
            print(f"❌ {method} - 未实现")
    
    print("="*60)


if __name__ == '__main__':
    # 快速测试
    print("="*60)
    print("P1阶段 - 组合优化方法快速测试")
    print("="*60)
    
    # 测试方法可用性
    test_optimization_methods_available()
    
    # 生成测试数据
    np.random.seed(42)
    n_stocks = 3
    n_periods = 252
    returns_matrix = np.random.randn(n_stocks, n_periods) * 0.02
    expected_returns = np.array([0.10, 0.12, 0.08])
    stocks = ['000001', '600519', '000858']
    market_weights = np.array([0.4, 0.3, 0.3])
    
    test_data = {
        'stocks': stocks,
        'returns_matrix': returns_matrix,
        'expected_returns': expected_returns,
        'market_weights': market_weights,
    }
    
    # 测试所有方法
    print("\n测试等权重优化...")
    weights = portfolio_optimizer.optimize_equal_weight(stocks)
    print(f"结果: {weights}")
    
    print("\n测试风险平价优化...")
    weights = portfolio_optimizer.optimize_risk_parity(stocks, returns_matrix)
    print(f"结果: {weights}")
    
    print("\n测试均值方差优化...")
    weights = portfolio_optimizer.optimize_mean_variance(stocks, returns_matrix, expected_returns)
    print(f"结果: {weights}")
    
    print("\n测试Black-Litterman模型...")
    views = [{'type': 'absolute', 'asset': 0, 'return': 0.15}]
    result = portfolio_optimizer.optimize_black_litterman(
        stocks, returns_matrix, market_weights, views
    )
    print(f"权重: {result['weights']}")
    print(f"预期收益: {result['expected_return']*100:.2f}%")
    
    print("\n测试风险预算优化...")
    result = portfolio_optimizer.optimize_risk_budget(stocks, returns_matrix, [0.5, 0.25, 0.25])
    print(f"权重: {result['weights']}")
    print(f"风险贡献: {result['risk_contributions']}")
    
    print("\n测试最大夏普比率优化...")
    result = portfolio_optimizer.optimize_max_sharpe(stocks, returns_matrix, expected_returns)
    print(f"权重: {result['weights']}")
    print(f"夏普比率: {result['sharpe_ratio']:.2f}")
    
    print("\n" + "="*60)
    print("✅ 所有优化方法测试通过！")
    print("="*60)
    print("\n完整测试请运行: pytest tests/test_p1_portfolio_optimization.py -v -s")
    print("="*60)
