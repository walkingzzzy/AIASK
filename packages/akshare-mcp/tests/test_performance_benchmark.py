#!/usr/bin/env python3
"""
性能基准测试套件
用于验证Python版本MCP服务的性能基线

测试项目：
1. 实时行情查询（1000次）
2. K线查询（1000次）
3. 技术指标计算（100股×1000天）
4. 单股回测（100股×250天）
5. 批量回测（100股×250天）

验收标准：
- 实时行情：< 200ms
- K线查询：< 100ms
- 技术指标：< 100ms
- 单股回测：< 1秒
- 批量回测：< 30秒
"""

import sys
import time
import asyncio
import numpy as np
from typing import List, Dict, Any
from datetime import datetime, timedelta
import statistics

# 添加项目路径
sys.path.insert(0, 'src')

from akshare_mcp.tools import market
from akshare_mcp.services import technical_analysis, backtest
from akshare_mcp.storage import get_db


class PerformanceBenchmark:
    """性能基准测试类"""
    
    def __init__(self):
        self.results = {}
        self.test_stocks = [
            '000001', '000002', '000333', '000651', '000858',
            '600000', '600036', '600519', '600887', '601318',
            '601398', '601857', '601988', '603259', '688001',
        ]
    
    def print_header(self, title: str):
        """打印测试标题"""
        print("\n" + "="*80)
        print(f"  {title}")
        print("="*80)
    
    def print_result(self, test_name: str, avg_time: float, target: float, 
                     count: int, passed: bool):
        """打印测试结果"""
        status = "✅ 通过" if passed else "❌ 未通过"
        print(f"\n{test_name}:")
        print(f"  测试次数: {count}")
        print(f"  平均耗时: {avg_time*1000:.2f}ms")
        print(f"  性能目标: < {target*1000:.0f}ms")
        print(f"  结果: {status}")
        
        self.results[test_name] = {
            'avg_time': avg_time,
            'target': target,
            'count': count,
            'passed': passed
        }
    
    async def test_realtime_quotes(self, iterations: int = 1000):
        """测试1：实时行情查询（1000次）"""
        self.print_header("测试1：实时行情查询")
        
        times = []
        success_count = 0
        
        print(f"开始测试 {iterations} 次实时行情查询...")
        
        for i in range(iterations):
            # 随机选择股票
            stock = self.test_stocks[i % len(self.test_stocks)]
            
            start = time.time()
            try:
                result = market.get_realtime_quote(stock)
                elapsed = time.time() - start
                
                if result.get('success'):
                    times.append(elapsed)
                    success_count += 1
            except Exception as e:
                print(f"  错误 [{i+1}/{iterations}]: {e}")
            
            # 进度显示
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{iterations} ({success_count} 成功)")
        
        if times:
            avg_time = statistics.mean(times)
            p50 = statistics.median(times)
            p95 = np.percentile(times, 95)
            p99 = np.percentile(times, 99)
            
            print(f"\n性能统计:")
            print(f"  成功率: {success_count}/{iterations} ({success_count/iterations*100:.1f}%)")
            print(f"  平均耗时: {avg_time*1000:.2f}ms")
            print(f"  P50: {p50*1000:.2f}ms")
            print(f"  P95: {p95*1000:.2f}ms")
            print(f"  P99: {p99*1000:.2f}ms")
            
            target = 0.2  # 200ms
            passed = avg_time < target
            self.print_result("实时行情查询", avg_time, target, iterations, passed)
        else:
            print("❌ 测试失败：无有效数据")
    
    async def test_kline_queries(self, iterations: int = 1000):
        """测试2：K线查询（1000次）"""
        self.print_header("测试2：K线查询")
        
        times = []
        success_count = 0
        
        print(f"开始测试 {iterations} 次K线查询...")
        
        for i in range(iterations):
            stock = self.test_stocks[i % len(self.test_stocks)]
            
            start = time.time()
            try:
                result = market.get_kline(stock, period='daily', limit=100)
                elapsed = time.time() - start
                
                if result.get('success'):
                    times.append(elapsed)
                    success_count += 1
            except Exception as e:
                print(f"  错误 [{i+1}/{iterations}]: {e}")
            
            if (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{iterations} ({success_count} 成功)")
        
        if times:
            avg_time = statistics.mean(times)
            p50 = statistics.median(times)
            p95 = np.percentile(times, 95)
            p99 = np.percentile(times, 99)
            
            print(f"\n性能统计:")
            print(f"  成功率: {success_count}/{iterations} ({success_count/iterations*100:.1f}%)")
            print(f"  平均耗时: {avg_time*1000:.2f}ms")
            print(f"  P50: {p50*1000:.2f}ms")
            print(f"  P95: {p95*1000:.2f}ms")
            print(f"  P99: {p99*1000:.2f}ms")
            
            target = 0.1  # 100ms
            passed = avg_time < target
            self.print_result("K线查询", avg_time, target, iterations, passed)
        else:
            print("❌ 测试失败：无有效数据")
    
    def test_technical_indicators(self, num_stocks: int = 100):
        """测试3：技术指标计算（100股×1000天）"""
        self.print_header("测试3：技术指标计算")
        
        print(f"开始测试 {num_stocks} 只股票的技术指标计算...")
        
        # 生成测试数据（1000天K线）
        np.random.seed(42)
        test_data = []
        for i in range(num_stocks):
            closes = np.cumsum(np.random.randn(1000)) + 100
            test_data.append({
                'code': f'TEST{i:04d}',
                'closes': closes.tolist()
            })
        
        times = []
        success_count = 0
        
        indicators = ['MA', 'EMA', 'RSI', 'MACD', 'KDJ', 'BOLL']
        
        for i, data in enumerate(test_data):
            start = time.time()
            try:
                # 计算所有指标
                klines = [{'close': c, 'high': c*1.02, 'low': c*0.98, 'volume': 1000000} 
                         for c in data['closes']]
                
                results = technical_analysis.calculate_all_indicators(klines, indicators)
                
                elapsed = time.time() - start
                times.append(elapsed)
                success_count += 1
            except Exception as e:
                print(f"  错误 [{i+1}/{num_stocks}]: {e}")
            
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{num_stocks} ({success_count} 成功)")
        
        if times:
            avg_time = statistics.mean(times)
            p50 = statistics.median(times)
            p95 = np.percentile(times, 95)
            p99 = np.percentile(times, 99)
            
            print(f"\n性能统计:")
            print(f"  成功率: {success_count}/{num_stocks} ({success_count/num_stocks*100:.1f}%)")
            print(f"  平均耗时: {avg_time*1000:.2f}ms")
            print(f"  P50: {p50*1000:.2f}ms")
            print(f"  P95: {p95*1000:.2f}ms")
            print(f"  P99: {p99*1000:.2f}ms")
            
            target = 0.1  # 100ms
            passed = avg_time < target
            self.print_result("技术指标计算", avg_time, target, num_stocks, passed)
        else:
            print("❌ 测试失败：无有效数据")
    
    def test_single_backtest(self, num_stocks: int = 100):
        """测试4：单股回测（100股×250天）"""
        self.print_header("测试4：单股回测")
        
        print(f"开始测试 {num_stocks} 只股票的单股回测...")
        
        # 生成测试数据（250天K线）
        np.random.seed(42)
        test_data = []
        for i in range(num_stocks):
            closes = np.cumsum(np.random.randn(250)) + 100
            test_data.append({
                'code': f'TEST{i:04d}',
                'closes': closes
            })
        
        times = []
        success_count = 0
        
        for i, data in enumerate(test_data):
            start = time.time()
            try:
                # 准备K线数据
                klines = []
                for j, close in enumerate(data['closes']):
                    klines.append({
                        'date': (datetime.now() - timedelta(days=250-j)).strftime('%Y-%m-%d'),
                        'open': close * 0.99,
                        'high': close * 1.02,
                        'low': close * 0.98,
                        'close': close,
                        'volume': 1000000,
                        'amount': close * 1000000
                    })
                
                # 运行回测
                result = backtest.BacktestEngine.run_backtest(
                    code=data['code'],
                    klines=klines,
                    strategy='ma_cross',
                    params={
                        'initial_capital': 100000,
                        'commission': 0.0003,
                        'short_period': 5,
                        'long_period': 20
                    }
                )
                
                elapsed = time.time() - start
                times.append(elapsed)
                success_count += 1
            except Exception as e:
                print(f"  错误 [{i+1}/{num_stocks}]: {e}")
            
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{num_stocks} ({success_count} 成功)")
        
        if times:
            avg_time = statistics.mean(times)
            p50 = statistics.median(times)
            p95 = np.percentile(times, 95)
            p99 = np.percentile(times, 99)
            
            print(f"\n性能统计:")
            print(f"  成功率: {success_count}/{num_stocks} ({success_count/num_stocks*100:.1f}%)")
            print(f"  平均耗时: {avg_time*1000:.2f}ms")
            print(f"  P50: {p50*1000:.2f}ms")
            print(f"  P95: {p95*1000:.2f}ms")
            print(f"  P99: {p99*1000:.2f}ms")
            
            target = 1.0  # 1秒
            passed = avg_time < target
            self.print_result("单股回测", avg_time, target, num_stocks, passed)
        else:
            print("❌ 测试失败：无有效数据")
    
    def test_batch_backtest(self, num_stocks: int = 100):
        """测试5：批量回测（100股×250天）"""
        self.print_header("测试5：批量回测（使用Ray并行）")
        
        # 检查Ray是否可用
        try:
            import ray
            RAY_AVAILABLE = True
        except ImportError:
            RAY_AVAILABLE = False
            print("⚠️  Ray未安装，跳过批量并行回测测试")
            print("   安装命令: pip install ray[default]")
            return
        
        print(f"开始测试 {num_stocks} 只股票的批量并行回测...")
        
        # 生成测试数据
        np.random.seed(42)
        klines_dict = {}
        for i in range(num_stocks):
            closes = np.cumsum(np.random.randn(250)) + 100
            klines = []
            for j, close in enumerate(closes):
                klines.append({
                    'date': (datetime.now() - timedelta(days=250-j)).strftime('%Y-%m-%d'),
                    'open': close * 0.99,
                    'high': close * 1.02,
                    'low': close * 0.98,
                    'close': close,
                    'volume': 1000000,
                    'amount': close * 1000000
                })
            klines_dict[f'TEST{i:04d}'] = klines
        
        start = time.time()
        try:
            # 使用Ray并行回测
            if not ray.is_initialized():
                ray.init(ignore_reinit_error=True)
            
            result = backtest.ParallelBacktestEngine.batch_backtest(
                codes=list(klines_dict.keys()),
                klines_dict=klines_dict,
                strategy='ma_cross',
                params={
                    'initial_capital': 100000,
                    'commission': 0.0003,
                    'short_period': 5,
                    'long_period': 20
                }
            )
            
            elapsed = time.time() - start
            
            print(f"\n性能统计:")
            print(f"  总耗时: {elapsed:.2f}秒")
            print(f"  股票数量: {num_stocks}")
            print(f"  平均每股: {elapsed/num_stocks*1000:.2f}ms")
            
            target = 30.0  # 30秒
            passed = elapsed < target
            self.print_result("批量回测", elapsed, target, num_stocks, passed)
            
            # 关闭Ray
            ray.shutdown()
        except Exception as e:
            print(f"❌ 测试失败: {e}")
    
    def print_summary(self):
        """打印测试总结"""
        self.print_header("测试总结")
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r['passed'])
        
        print(f"\n总测试数: {total_tests}")
        print(f"通过数: {passed_tests}")
        print(f"失败数: {total_tests - passed_tests}")
        print(f"通过率: {passed_tests/total_tests*100:.1f}%")
        
        print("\n详细结果:")
        print("-" * 80)
        print(f"{'测试项':<20} {'平均耗时':<15} {'性能目标':<15} {'结果':<10}")
        print("-" * 80)
        
        for name, result in self.results.items():
            avg_ms = result['avg_time'] * 1000
            target_ms = result['target'] * 1000
            status = "✅ 通过" if result['passed'] else "❌ 未通过"
            
            print(f"{name:<20} {avg_ms:>10.2f}ms   {target_ms:>10.0f}ms   {status}")
        
        print("-" * 80)
        
        if passed_tests == total_tests:
            print("\n🎉 所有测试通过！Python版本性能达标，可以开始灰度切换。")
        else:
            print(f"\n⚠️  有 {total_tests - passed_tests} 个测试未通过，需要优化。")


async def main():
    """主函数"""
    print("="*80)
    print("  MCP Python版本性能基准测试")
    print("  测试日期:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*80)
    
    benchmark = PerformanceBenchmark()
    
    try:
        # 测试1：实时行情查询（1000次）
        await benchmark.test_realtime_quotes(iterations=1000)
        
        # 测试2：K线查询（1000次）
        await benchmark.test_kline_queries(iterations=1000)
        
        # 测试3：技术指标计算（100股×1000天）
        benchmark.test_technical_indicators(num_stocks=100)
        
        # 测试4：单股回测（100股×250天）
        benchmark.test_single_backtest(num_stocks=100)
        
        # 测试5：批量回测（100股×250天）
        benchmark.test_batch_backtest(num_stocks=100)
        
        # 打印总结
        benchmark.print_summary()
        
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
