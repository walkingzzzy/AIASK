"""技术分析测试"""

import pytest
import numpy as np
from akshare_mcp.services.technical_analysis import technical_analysis


def test_sma_calculation():
    """测试SMA计算"""
    closes = [10, 11, 12, 13, 14, 15]
    result = technical_analysis.calculate_sma(closes, 3)
    
    assert len(result) == len(closes)
    assert result[2] == pytest.approx(11.0, rel=0.01)
    assert result[3] == pytest.approx(12.0, rel=0.01)


def test_rsi_calculation():
    """测试RSI计算"""
    closes = list(range(100, 120)) + list(range(120, 100, -1))
    result = technical_analysis.calculate_rsi(closes)
    
    assert 'value' in result
    assert 'signal' in result
    assert 0 <= result['value'] <= 100


def test_macd_calculation():
    """测试MACD计算"""
    closes = list(range(100, 150))
    result = technical_analysis.calculate_macd(closes)
    
    assert 'macd' in result
    assert 'signal' in result
    assert 'histogram' in result
    assert len(result['macd']) == len(closes)


@pytest.mark.benchmark
def test_indicator_performance(benchmark):
    """性能基准测试"""
    closes = np.random.randn(1000).cumsum() + 100
    closes = closes.tolist()
    
    result = benchmark(technical_analysis.calculate_all_indicators, 
                      [{'close': c, 'open': c, 'high': c, 'low': c, 'volume': 1000} 
                       for c in closes],
                      ['MA', 'RSI', 'MACD'])
    
    assert 'ma' in result or 'rsi' in result
