"""回测引擎测试"""

import pytest
import numpy as np
from akshare_mcp.services.backtest import backtest_engine


def test_buy_and_hold():
    """测试买入持有策略"""
    klines = [
        {'date': f'2024-01-{i:02d}', 'open': 100+i, 'high': 101+i, 
         'low': 99+i, 'close': 100+i, 'volume': 1000}
        for i in range(1, 31)
    ]
    
    result = backtest_engine.run_backtest('TEST', klines, 'buy_and_hold')
    
    assert result['success'] == True
    assert 'total_return' in result['data']
    assert result['data']['trades_count'] == 1


def test_ma_cross_strategy():
    """测试均线交叉策略"""
    # 生成趋势数据
    closes = np.linspace(100, 120, 100)
    klines = [
        {'date': f'2024-{i//30+1:02d}-{i%30+1:02d}', 
         'open': c, 'high': c+1, 'low': c-1, 'close': c, 'volume': 1000}
        for i, c in enumerate(closes)
    ]
    
    result = backtest_engine.run_backtest('TEST', klines, 'ma_cross', {
        'short_period': 5,
        'long_period': 20,
        'initial_capital': 100000,
        'commission': 0.0003
    })
    
    assert result['success'] == True
    assert 'sharpe_ratio' in result['data']
    assert result['data']['trades_count'] >= 0


@pytest.mark.benchmark
def test_backtest_performance(benchmark):
    """回测性能测试"""
    closes = np.random.randn(250).cumsum() + 100
    klines = [
        {'date': f'2024-{i//30+1:02d}-{i%30+1:02d}',
         'open': c, 'high': c+1, 'low': c-1, 'close': c, 'volume': 1000}
        for i, c in enumerate(closes)
    ]
    
    result = benchmark(backtest_engine.run_backtest, 'TEST', klines, 'ma_cross')
    
    assert result['success'] == True
