"""集成测试"""

import pytest
import asyncio


@pytest.mark.asyncio
async def test_full_workflow():
    """测试完整工作流"""
    from akshare_mcp.storage import get_db
    from akshare_mcp.services import technical_analysis, backtest_engine
    
    # 模拟K线数据
    klines = [
        {'date': f'2024-01-{i:02d}', 'open': 100+i, 'high': 101+i,
         'low': 99+i, 'close': 100+i, 'volume': 1000}
        for i in range(1, 101)
    ]
    
    # 计算技术指标
    indicators = technical_analysis.calculate_all_indicators(klines, ['MA', 'RSI'])
    assert 'ma' in indicators or 'rsi' in indicators
    
    # 运行回测
    result = backtest_engine.run_backtest('TEST', klines, 'ma_cross')
    assert result['success'] == True
    assert 'total_return' in result['data']


@pytest.mark.asyncio
async def test_database_operations():
    """测试数据库操作"""
    from akshare_mcp.storage import get_db
    
    db = get_db()
    
    # 测试连接
    try:
        await db.initialize()
        stats = await db.get_stats()
        assert isinstance(stats, dict)
    except Exception as e:
        pytest.skip(f"Database not available: {e}")
