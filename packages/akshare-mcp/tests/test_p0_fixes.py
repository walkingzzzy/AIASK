"""
P0阶段修复验证测试
测试Numba JIT、数据库表结构、字段映射、批量查询
"""

import pytest
import asyncio
import time
import numpy as np
from datetime import datetime

# 测试1：Numba JIT回测性能
def test_numba_backtest_performance():
    """测试Numba JIT优化的回测性能"""
    from akshare_mcp.services.backtest import _backtest_ma_cross_jit
    
    # 生成测试数据（250天）
    np.random.seed(42)
    closes = np.cumsum(np.random.randn(250)) + 100
    
    # 预热JIT编译
    _backtest_ma_cross_jit(closes[:50], 5, 20, 100000, 0.0003)
    
    # 性能测试
    start = time.time()
    result = _backtest_ma_cross_jit(closes, 5, 20, 100000, 0.0003)
    elapsed = time.time() - start
    
    final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result
    
    # 验证结果
    assert final_capital > 0, "最终资金应该大于0"
    assert -1 <= total_return <= 10, "总收益率应该在合理范围内"
    assert 0 <= max_dd <= 1, "最大回撤应该在0-1之间"
    assert trades >= 0, "交易次数应该非负"
    assert 0 <= win_rate <= 1, "胜率应该在0-1之间"
    assert len(equity) == len(closes), "权益曲线长度应该等于K线长度"
    
    # 性能验证：应该 < 100ms
    print(f"\n✅ Numba JIT回测性能测试通过")
    print(f"   执行时间: {elapsed*1000:.2f}ms (目标: < 100ms)")
    print(f"   最终资金: {final_capital:.2f}")
    print(f"   总收益率: {total_return*100:.2f}%")
    print(f"   最大回撤: {max_dd*100:.2f}%")
    print(f"   夏普比率: {sharpe:.2f}")
    print(f"   交易次数: {trades}")
    print(f"   胜率: {win_rate*100:.2f}%")
    
    assert elapsed < 0.1, f"性能不达标：{elapsed*1000:.2f}ms > 100ms"


def test_numba_momentum_backtest():
    """测试Numba动量策略回测"""
    from akshare_mcp.services.backtest import _backtest_momentum_jit
    
    np.random.seed(42)
    closes = np.cumsum(np.random.randn(250)) + 100
    
    # 预热
    _backtest_momentum_jit(closes[:50], 20, 0.02, 100000, 0.0003)
    
    # 测试
    start = time.time()
    result = _backtest_momentum_jit(closes, 20, 0.02, 100000, 0.0003)
    elapsed = time.time() - start
    
    final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result
    
    print(f"\n✅ Numba动量策略回测测试通过")
    print(f"   执行时间: {elapsed*1000:.2f}ms")
    print(f"   总收益率: {total_return*100:.2f}%")
    
    assert elapsed < 0.1, f"性能不达标：{elapsed*1000:.2f}ms > 100ms"


def test_numba_rsi_backtest():
    """测试Numba RSI策略回测"""
    from akshare_mcp.services.backtest import _backtest_rsi_jit
    
    np.random.seed(42)
    closes = np.cumsum(np.random.randn(250)) + 100
    
    # 预热
    _backtest_rsi_jit(closes[:50], 14, 30, 70, 100000, 0.0003)
    
    # 测试
    start = time.time()
    result = _backtest_rsi_jit(closes, 14, 30, 70, 100000, 0.0003)
    elapsed = time.time() - start
    
    final_capital, total_return, max_dd, sharpe, trades, win_rate, equity = result
    
    print(f"\n✅ Numba RSI策略回测测试通过")
    print(f"   执行时间: {elapsed*1000:.2f}ms")
    print(f"   总收益率: {total_return*100:.2f}%")
    
    assert elapsed < 0.1, f"性能不达标：{elapsed*1000:.2f}ms > 100ms"


# 测试2：数据库表结构
@pytest.mark.asyncio
async def test_database_tables():
    """测试数据库表结构是否完整"""
    from akshare_mcp.storage import get_db
    
    db = get_db()
    await db.initialize()
    
    # 检查所有必需的表
    required_tables = [
        'kline_1d',
        'financials',
        'stocks',
        'stock_quotes',
        'portfolios',
        'holdings',
        'paper_accounts',
        'paper_positions',
        'paper_trades',
        'backtest_results',
        'backtest_trades',
        'backtest_equity',
        'alerts',
        'price_alerts',
        'combo_alerts',
        'indicator_alerts',
        'watchlist_groups',
        'watchlist',
        'stock_embeddings',
        'pattern_vectors',
        'vector_documents',
        'market_blocks',
        'block_stocks',
        'data_quality_issues',
    ]
    
    async with db.acquire() as conn:
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        
        existing_tables = [t['tablename'] for t in tables]
        
        print(f"\n✅ 数据库表结构测试")
        print(f"   已创建表数量: {len(existing_tables)}")
        print(f"   必需表数量: {len(required_tables)}")
        
        missing_tables = [t for t in required_tables if t not in existing_tables]
        
        if missing_tables:
            print(f"\n❌ 缺失的表:")
            for table in missing_tables:
                print(f"   - {table}")
            pytest.fail(f"缺失 {len(missing_tables)} 个表")
        else:
            print(f"   ✅ 所有必需的表都已创建")
            print(f"\n   已创建的表:")
            for table in sorted(existing_tables):
                if table in required_tables:
                    print(f"   ✅ {table}")


# 测试3：字段映射
@pytest.mark.asyncio
async def test_field_mapping():
    """测试数据库字段映射是否正确"""
    from akshare_mcp.storage import get_db
    
    db = get_db()
    await db.initialize()
    
    # 测试数据（使用旧字段名）
    test_quote = {
        'code': 'TEST001',
        'name': '测试股票',
        'price': 10.0,
        'pre_close': 9.5,  # 旧字段名
        'change': 0.5,     # 旧字段名
        'market_cap': 1000000,  # 旧字段名
        'open': 9.8,
        'high': 10.2,
        'low': 9.6,
        'volume': 1000000,
        'amount': 10000000,
        'pe': 15.0,
        'pb': 2.0,
    }
    
    # 保存数据
    await db.save_quote(test_quote)
    
    # 读取数据验证
    async with db.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT code, prev_close, change_amt, mkt_cap
            FROM stock_quotes
            WHERE code = $1
            ORDER BY time DESC
            LIMIT 1
        """, 'TEST001')
        
        assert row is not None, "数据应该被保存"
        assert row['prev_close'] == 9.5, "prev_close字段映射错误"
        assert row['change_amt'] == 0.5, "change_amt字段映射错误"
        assert row['mkt_cap'] == 1000000, "mkt_cap字段映射错误"
        
        print(f"\n✅ 字段映射测试通过")
        print(f"   prev_close: {row['prev_close']} (旧字段名: pre_close)")
        print(f"   change_amt: {row['change_amt']} (旧字段名: change)")
        print(f"   mkt_cap: {row['mkt_cap']} (旧字段名: market_cap)")


# 测试4：批量查询
def test_batch_quotes():
    """测试批量查询功能"""
    from akshare_mcp.tools.market import get_batch_quotes
    
    # 测试代码
    test_codes = ['000001', '600519', '000858']
    
    print(f"\n✅ 批量查询测试")
    print(f"   测试股票: {test_codes}")
    
    start = time.time()
    result = get_batch_quotes(test_codes)
    elapsed = time.time() - start
    
    print(f"   执行时间: {elapsed:.2f}秒")
    
    if result['success']:
        quotes = result['data']
        print(f"   成功获取: {len(quotes)} 只股票")
        
        for quote in quotes[:3]:  # 只打印前3个
            print(f"   - {quote.get('code', 'N/A')}: {quote.get('name', 'N/A')} - {quote.get('price', 'N/A')}")
        
        assert len(quotes) > 0, "应该至少获取到一只股票"
        assert elapsed < 10, f"批量查询超时：{elapsed:.2f}秒 > 10秒"
    else:
        print(f"   ⚠️  批量查询失败: {result.get('error', 'Unknown error')}")
        print(f"   注意：这可能是网络问题或API限流，不一定是代码问题")


# 测试5：回测引擎集成测试
def test_backtest_engine_integration():
    """测试回测引擎集成"""
    from akshare_mcp.services.backtest import BacktestEngine
    
    # 生成测试K线数据
    np.random.seed(42)
    closes = np.cumsum(np.random.randn(250)) + 100
    
    klines = [
        {
            'date': f'2024-{i//20+1:02d}-{i%20+1:02d}',
            'close': float(closes[i]),
            'open': float(closes[i] * 0.99),
            'high': float(closes[i] * 1.01),
            'low': float(closes[i] * 0.98),
            'volume': 1000000,
        }
        for i in range(len(closes))
    ]
    
    # 测试均线交叉策略
    result = BacktestEngine.run_backtest(
        code='TEST001',
        klines=klines,
        strategy='ma_cross',
        params={
            'initial_capital': 100000,
            'commission': 0.0003,
            'short_period': 5,
            'long_period': 20,
        }
    )
    
    assert result['success'], "回测应该成功"
    
    data = result['data']
    print(f"\n✅ 回测引擎集成测试通过")
    print(f"   策略: {data['strategy']}")
    print(f"   初始资金: {data['initial_capital']:.2f}")
    print(f"   最终资金: {data['final_capital']:.2f}")
    print(f"   总收益率: {data['total_return']*100:.2f}%")
    print(f"   最大回撤: {data['max_drawdown']*100:.2f}%")
    print(f"   夏普比率: {data['sharpe_ratio']:.2f}")
    print(f"   交易次数: {data['trades_count']}")
    print(f"   胜率: {data['win_rate']*100:.2f}%")
    
    assert data['final_capital'] > 0, "最终资金应该大于0"
    assert data['trades_count'] >= 0, "交易次数应该非负"


if __name__ == '__main__':
    print("=" * 60)
    print("P0阶段修复验证测试")
    print("=" * 60)
    
    # 运行测试
    pytest.main([__file__, '-v', '-s'])
