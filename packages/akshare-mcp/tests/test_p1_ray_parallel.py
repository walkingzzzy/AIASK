#!/usr/bin/env python3
"""
P1阶段 - Ray并行回测测试
"""

import pytest
import numpy as np
import time
from typing import List, Dict, Any

# 检查Ray是否可用
RAY_AVAILABLE = False
try:
    import ray
    RAY_AVAILABLE = True
except ImportError:
    pass


@pytest.fixture
def test_klines():
    """生成测试K线数据"""
    np.random.seed(42)
    n = 250
    closes = np.cumsum(np.random.randn(n) * 0.02) + 100
    
    klines = []
    for i in range(n):
        klines.append({
            'date': f'2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
            'open': closes[i] * 0.99,
            'high': closes[i] * 1.01,
            'low': closes[i] * 0.98,
            'close': closes[i],
            'volume': 1000000,
        })
    
    return klines


class TestRayParallelBacktest:
    """Ray并行回测测试"""
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_ray_import(self):
        """测试Ray导入"""
        import ray
        assert ray is not None
        print("✅ Ray导入成功")
    
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_parallel_backtest_engine_exists(self):
        """测试ParallelBacktestEngine是否存在"""
        from akshare_mcp.services.backtest import ParallelBacktestEngine
        
        assert ParallelBacktestEngine is not None
        assert hasattr(ParallelBacktestEngine, 'batch_backtest')
        print("✅ ParallelBacktestEngine存在")
    
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_parallel_backtest_basic(self, test_klines):
        """测试基础并行回测功能"""
        from akshare_mcp.services.backtest import ParallelBacktestEngine
        
        codes = ['000001', '000002', '000003']
        klines_dict = {code: test_klines for code in codes}
        
        params = {
            'initial_capital': 100000,
            'commission': 0.0003,
            'short_period': 5,
            'long_period': 20,
        }
        
        result = ParallelBacktestEngine.batch_backtest(
            codes=codes,
            klines_dict=klines_dict,
            strategy='ma_cross',
            params=params
        )
        
        assert result['success'] is True
        assert result['data']['count'] == 3
        assert len(result['data']['results']) == 3
        
        print(f"✅ 并行回测成功，处理了 {result['data']['count']} 只股票")
        
        # 验证每个结果
        for r in result['data']['results']:
            assert r.get('success') is True
            assert 'data' in r
            data = r['data']
            assert 'total_return' in data
            assert 'sharpe_ratio' in data
            assert 'max_drawdown' in data
            print(f"   股票 {data.get('code', 'N/A')}: 收益率={data['total_return']*100:.2f}%")
    
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_parallel_vs_sequential_performance(self, test_klines):
        """测试并行vs串行性能对比"""
        from akshare_mcp.services.backtest import ParallelBacktestEngine, backtest_engine
        
        codes = ['000001', '000002', '000003', '000004', '000005']
        klines_dict = {code: test_klines for code in codes}
        
        params = {
            'initial_capital': 100000,
            'commission': 0.0003,
            'short_period': 5,
            'long_period': 20,
        }
        
        # 串行回测
        start_sequential = time.time()
        sequential_results = []
        for code in codes:
            result = backtest_engine.run_backtest(code, klines_dict[code], 'ma_cross', params)
            sequential_results.append(result)
        sequential_time = time.time() - start_sequential
        
        # 并行回测
        start_parallel = time.time()
        parallel_result = ParallelBacktestEngine.batch_backtest(
            codes=codes,
            klines_dict=klines_dict,
            strategy='ma_cross',
            params=params
        )
        parallel_time = time.time() - start_parallel
        
        speedup = sequential_time / parallel_time if parallel_time > 0 else 0
        
        print(f"\n性能对比:")
        print(f"  串行时间: {sequential_time*1000:.2f}ms")
        print(f"  并行时间: {parallel_time*1000:.2f}ms")
        print(f"  加速比: {speedup:.2f}x")
        
        # 并行应该更快（至少不慢于串行）
        assert parallel_time <= sequential_time * 1.5, "并行回测性能不应该明显慢于串行"
        
        print(f"✅ 性能测试通过，加速比: {speedup:.2f}x")
    
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_parallel_backtest_large_batch(self, test_klines):
        """测试大批量并行回测（10只股票）"""
        from akshare_mcp.services.backtest import ParallelBacktestEngine
        
        codes = [f'{i:06d}' for i in range(1, 11)]  # 000001-000010
        klines_dict = {code: test_klines for code in codes}
        
        params = {
            'initial_capital': 100000,
            'commission': 0.0003,
            'short_period': 5,
            'long_period': 20,
        }
        
        start = time.time()
        result = ParallelBacktestEngine.batch_backtest(
            codes=codes,
            klines_dict=klines_dict,
            strategy='ma_cross',
            params=params
        )
        elapsed = time.time() - start
        
        assert result['success'] is True
        assert result['data']['count'] == 10
        
        print(f"\n大批量回测:")
        print(f"  股票数量: 10")
        print(f"  总耗时: {elapsed*1000:.2f}ms")
        print(f"  平均每股: {elapsed*1000/10:.2f}ms")
        
        # 性能目标：10只股票 < 1秒
        assert elapsed < 1.0, f"10只股票回测耗时 {elapsed:.2f}s，超过1秒目标"
        
        print(f"✅ 大批量回测通过，10只股票耗时 {elapsed*1000:.2f}ms")
    
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_parallel_backtest_multiple_strategies(self, test_klines):
        """测试多种策略的并行回测"""
        from akshare_mcp.services.backtest import ParallelBacktestEngine
        
        codes = ['000001', '000002']
        klines_dict = {code: test_klines for code in codes}
        
        strategies = ['ma_cross', 'momentum', 'rsi']
        
        for strategy in strategies:
            params = {
                'initial_capital': 100000,
                'commission': 0.0003,
                'short_period': 5,
                'long_period': 20,
            }
            
            result = ParallelBacktestEngine.batch_backtest(
                codes=codes,
                klines_dict=klines_dict,
                strategy=strategy,
                params=params
            )
            
            assert result['success'] is True
            assert result['data']['count'] == 2
            
            print(f"✅ 策略 {strategy} 并行回测成功")
    
    
    @pytest.mark.skipif(not RAY_AVAILABLE, reason="Ray not installed")
    def test_ray_initialization(self):
        """测试Ray初始化和清理"""
        import ray
        
        # 初始化Ray
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)
        
        assert ray.is_initialized()
        print("✅ Ray初始化成功")
        
        # 清理（可选）
        # ray.shutdown()


class TestRayNotAvailable:
    """Ray不可用时的测试"""
    
    @pytest.mark.skipif(RAY_AVAILABLE, reason="Ray is installed")
    def test_fallback_to_sequential(self, test_klines):
        """测试Ray不可用时回退到串行模式"""
        from akshare_mcp.services.backtest import backtest_engine
        
        codes = ['000001', '000002']
        klines_dict = {code: test_klines for code in codes}
        
        params = {
            'initial_capital': 100000,
            'commission': 0.0003,
            'short_period': 5,
            'long_period': 20,
        }
        
        # 串行回测
        results = []
        for code in codes:
            result = backtest_engine.run_backtest(code, klines_dict[code], 'ma_cross', params)
            results.append(result)
        
        assert len(results) == 2
        for r in results:
            assert r.get('success') is True
        
        print("✅ 串行回测（Ray不可用时的fallback）成功")


def test_ray_availability():
    """测试Ray可用性"""
    if RAY_AVAILABLE:
        print("\n✅ Ray已安装并可用")
        import ray
        print(f"   Ray版本: {ray.__version__}")
    else:
        print("\n⚠️  Ray未安装")
        print("   安装命令: pip install ray")
        print("   或: pip install 'ray[default]'")


if __name__ == '__main__':
    # 快速测试
    print("="*60)
    print("P1阶段 - Ray并行回测快速测试")
    print("="*60)
    
    test_ray_availability()
    
    if RAY_AVAILABLE:
        print("\n运行基础测试...")
        
        # 生成测试数据
        np.random.seed(42)
        n = 250
        closes = np.cumsum(np.random.randn(n) * 0.02) + 100
        test_klines = []
        for i in range(n):
            test_klines.append({
                'date': f'2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}',
                'open': closes[i] * 0.99,
                'high': closes[i] * 1.01,
                'low': closes[i] * 0.98,
                'close': closes[i],
                'volume': 1000000,
            })
        
        # 测试并行回测
        from akshare_mcp.services.backtest import ParallelBacktestEngine
        
        codes = ['000001', '000002', '000003']
        klines_dict = {code: test_klines for code in codes}
        
        params = {
            'initial_capital': 100000,
            'commission': 0.0003,
            'short_period': 5,
            'long_period': 20,
        }
        
        print(f"\n测试 {len(codes)} 只股票的并行回测...")
        start = time.time()
        result = ParallelBacktestEngine.batch_backtest(
            codes=codes,
            klines_dict=klines_dict,
            strategy='ma_cross',
            params=params
        )
        elapsed = time.time() - start
        
        if result['success']:
            print(f"✅ 并行回测成功")
            print(f"   耗时: {elapsed*1000:.2f}ms")
            print(f"   处理股票数: {result['data']['count']}")
            
            for r in result['data']['results']:
                if r.get('success'):
                    data = r['data']
                    print(f"   {data.get('code', 'N/A')}: 收益率={data['total_return']*100:.2f}%")
        else:
            print(f"❌ 并行回测失败: {result.get('error')}")
    
    else:
        print("\n跳过测试（Ray未安装）")
    
    print("\n" + "="*60)
    print("完整测试请运行: pytest tests/test_p1_ray_parallel.py -v -s")
    print("="*60)
