#!/usr/bin/env python3
"""
快速性能测试脚本
无需数据库连接，使用模拟数据快速验证性能
"""

import sys
import time
import numpy as np
from datetime import datetime

# 添加项目路径
sys.path.insert(0, 'src')


def test_numba_jit():
    """测试Numba JIT优化"""
    print("\n" + "="*80)
    print("  测试1：Numba JIT优化（回测引擎）")
    print("="*80)
    
    try:
        from akshare_mcp.services.backtest import _backtest_ma_cross_jit
        
        # 生成测试数据（250天K线）
        np.random.seed(42)
        closes = np.cumsum(np.random.randn(250)) + 100
        
        # 预热JIT编译
        print("   预热JIT编译...")
        _backtest_ma_cross_jit(closes[:50], 5, 20, 100000, 0.0003)
        
        # 性能测试
        print("   运行性能测试（250天K线）...")
        times = []
        for i in range(10):
            start = time.time()
            result = _backtest_ma_cross_jit(closes, 5, 20, 100000, 0.0003)
            elapsed = time.time() - start
            times.append(elapsed)
        
        avg_time = np.mean(times)
        
        print(f"\n   平均执行时间: {avg_time*1000:.2f}ms")
        print(f"   性能要求: < 1000ms")
        print(f"   结果: {'✅ 通过' if avg_time < 1.0 else '❌ 未通过'}")
        
        return avg_time < 1.0
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False


def test_technical_indicators():
    """测试技术指标计算"""
    print("\n" + "="*80)
    print("  测试2：技术指标计算（NumPy向量化）")
    print("="*80)
    
    try:
        from akshare_mcp.services.technical_analysis import TechnicalAnalysis
        
        # 生成测试数据（1000天K线）
        np.random.seed(42)
        closes = (np.cumsum(np.random.randn(1000)) + 100).tolist()
        
        print("   运行性能测试（1000天数据）...")
        times = []
        for i in range(10):
            start = time.time()
            
            # 计算多个指标
            sma = TechnicalAnalysis.calculate_sma(closes, 20)
            ema = TechnicalAnalysis.calculate_ema(closes, 20)
            rsi = TechnicalAnalysis.calculate_rsi(closes, 14)
            
            elapsed = time.time() - start
            times.append(elapsed)
        
        avg_time = np.mean(times)
        
        print(f"\n   平均执行时间: {avg_time*1000:.2f}ms")
        print(f"   性能要求: < 100ms")
        print(f"   结果: {'✅ 通过' if avg_time < 0.1 else '❌ 未通过'}")
        
        return avg_time < 0.1
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False


def test_portfolio_optimization():
    """测试组合优化"""
    print("\n" + "="*80)
    print("  测试3：组合优化（NumPy/SciPy矩阵运算）")
    print("="*80)
    
    try:
        from akshare_mcp.services.portfolio_optimizer import PortfolioOptimizer
        
        # 生成测试数据（50股×252天）
        np.random.seed(42)
        num_stocks = 50
        num_days = 252
        
        returns = np.random.randn(num_stocks, num_days) * 0.01  # 注意：转置了维度
        stocks = [f'TEST{i:04d}' for i in range(num_stocks)]
        
        print(f"   运行性能测试（{num_stocks}股×{num_days}天）...")
        times = []
        for i in range(5):
            start = time.time()
            
            # 均值-方差优化
            expected_returns = np.mean(returns, axis=1)
            optimizer = PortfolioOptimizer()
            weights = optimizer.optimize_mean_variance(
                stocks=stocks,
                returns_matrix=returns,
                expected_returns=expected_returns
            )
            
            elapsed = time.time() - start
            times.append(elapsed)
        
        avg_time = np.mean(times)
        
        print(f"\n   平均执行时间: {avg_time*1000:.2f}ms")
        print(f"   性能要求: < 500ms")
        print(f"   结果: {'✅ 通过' if avg_time < 0.5 else '❌ 未通过'}")
        
        return avg_time < 0.5
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False


def test_pattern_recognition():
    """测试K线形态识别"""
    print("\n" + "="*80)
    print("  测试4：K线形态识别（TA-Lib）")
    print("="*80)
    
    try:
        from akshare_mcp.services.pattern_recognition import PatternRecognition
        
        # 生成测试数据（250天K线）
        np.random.seed(42)
        closes = np.cumsum(np.random.randn(250)) + 100
        opens = closes * 0.99
        highs = closes * 1.02
        lows = closes * 0.98
        
        klines = []
        for i in range(len(closes)):
            klines.append({
                'open': opens[i],
                'high': highs[i],
                'low': lows[i],
                'close': closes[i],
                'volume': 1000000
            })
        
        print("   运行性能测试（250天数据，61种形态）...")
        times = []
        for i in range(10):
            start = time.time()
            
            # 检测所有形态
            patterns = PatternRecognition.detect_patterns(klines)
            
            elapsed = time.time() - start
            times.append(elapsed)
        
        avg_time = np.mean(times)
        
        print(f"\n   平均执行时间: {avg_time*1000:.2f}ms")
        print(f"   性能要求: < 300ms")
        print(f"   结果: {'✅ 通过' if avg_time < 0.3 else '❌ 未通过'}")
        
        return avg_time < 0.3
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False


def test_ray_parallel():
    """测试Ray并行计算"""
    print("\n" + "="*80)
    print("  测试5：Ray并行计算（可选）")
    print("="*80)
    
    try:
        import ray
        
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True)
        
        @ray.remote
        def compute_task(x):
            return x * x
        
        print("   运行性能测试（100个并行任务）...")
        start = time.time()
        
        futures = [compute_task.remote(i) for i in range(100)]
        results = ray.get(futures)
        
        elapsed = time.time() - start
        
        print(f"\n   执行时间: {elapsed*1000:.2f}ms")
        print(f"   结果: ✅ Ray可用")
        
        ray.shutdown()
        return True
    except ImportError:
        print("   ⚠️  Ray未安装，跳过测试")
        print("   安装命令: pip install ray[default]")
        return None
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        return False


def main():
    """主函数"""
    print("="*80)
    print("  MCP Python版本快速性能测试")
    print("  测试日期:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*80)
    
    results = {}
    
    # 运行所有测试
    results['Numba JIT'] = test_numba_jit()
    results['技术指标'] = test_technical_indicators()
    results['组合优化'] = test_portfolio_optimization()
    results['形态识别'] = test_pattern_recognition()
    results['Ray并行'] = test_ray_parallel()
    
    # 打印总结
    print("\n" + "="*80)
    print("  测试总结")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    total = len(results)
    
    print(f"\n总测试数: {total}")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"跳过: {skipped}")
    
    print("\n详细结果:")
    for name, result in results.items():
        if result is True:
            status = "✅ 通过"
        elif result is False:
            status = "❌ 失败"
        else:
            status = "⚠️  跳过"
        print(f"  {name:<15} {status}")
    
    if failed == 0:
        print("\n🎉 所有测试通过！Python版本性能优化有效。")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，需要检查。")
        return 1


if __name__ == '__main__':
    sys.exit(main())
