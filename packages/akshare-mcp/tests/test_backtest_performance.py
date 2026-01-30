"""
回测性能测试 - 验证Ray并行优化效果
"""

import pytest
import asyncio
import time
from datetime import datetime


class TestBacktestPerformance:
    """测试回测性能"""
    
    @pytest.mark.asyncio
    async def test_sequential_vs_parallel(self):
        """对比顺序执行和并行执行的性能"""
        print("\n" + "="*60)
        print("回测性能对比测试")
        print("="*60)
        
        from akshare_mcp.tools.backtest import run_batch_backtest
        
        # 测试股票列表
        test_codes = ['600519', '000858', '002304']
        
        # 1. 顺序执行
        print("\n1. 顺序执行测试...")
        start_time = time.time()
        
        result_seq = await run_batch_backtest(
            codes=test_codes,
            strategy='ma_cross',
            initial_capital=100000,
            use_parallel=False
        )
        
        seq_time = time.time() - start_time
        
        assert result_seq['success'] is True
        print(f"✅ 顺序执行完成")
        print(f"   执行时间: {seq_time:.2f}秒")
        print(f"   成功数量: {result_seq['data']['successful_count']}/{len(test_codes)}")
        
        if 'summary' in result_seq['data']:
            summary = result_seq['data']['summary']
            print(f"   平均收益: {summary['avg_return_pct']}")
            print(f"   平均夏普: {summary['avg_sharpe_ratio']:.2f}")
        
        # 2. 并行执行
        print("\n2. 并行执行测试（Ray优化版）...")
        start_time = time.time()
        
        result_par = await run_batch_backtest(
            codes=test_codes,
            strategy='ma_cross',
            initial_capital=100000,
            use_parallel=True
        )
        
        par_time = time.time() - start_time
        
        assert result_par['success'] is True
        print(f"✅ 并行执行完成")
        print(f"   执行时间: {par_time:.2f}秒")
        print(f"   成功数量: {result_par['data']['successful_count']}/{len(test_codes)}")
        
        if 'summary' in result_par['data']:
            summary = result_par['data']['summary']
            print(f"   平均收益: {summary['avg_return_pct']}")
            print(f"   平均夏普: {summary['avg_sharpe_ratio']:.2f}")
        
        # 3. 性能对比
        print("\n" + "="*60)
        print("性能对比结果")
        print("="*60)
        print(f"顺序执行: {seq_time:.2f}秒")
        print(f"并行执行: {par_time:.2f}秒")
        
        if par_time > 0:
            speedup = seq_time / par_time
            print(f"加速比: {speedup:.2f}x")
            
            if speedup > 1.5:
                print("✅ 并行优化效果显著")
            elif speedup > 1.0:
                print("⚠️  并行有加速，但不明显")
            else:
                print("❌ 并行反而更慢，需要进一步优化")
        
        # 性能目标检查
        print("\n" + "="*60)
        print("性能目标检查")
        print("="*60)
        
        target_time = 3.0  # 目标：3股票<3秒
        
        if par_time < target_time:
            print(f"✅ 达到性能目标！({par_time:.2f}s < {target_time}s)")
        else:
            print(f"⚠️  未达到性能目标 ({par_time:.2f}s > {target_time}s)")
            print(f"   还需优化: {par_time - target_time:.2f}秒")
    
    @pytest.mark.asyncio
    async def test_scalability(self):
        """测试可扩展性 - 不同股票数量的性能"""
        print("\n" + "="*60)
        print("可扩展性测试")
        print("="*60)
        
        from akshare_mcp.tools.backtest import run_batch_backtest
        
        # 测试不同数量的股票
        test_cases = [
            (['600519'], "1只股票"),
            (['600519', '000858'], "2只股票"),
            (['600519', '000858', '002304'], "3只股票"),
            (['600519', '000858', '002304', '000001', '600036'], "5只股票"),
        ]
        
        results = []
        
        for codes, desc in test_cases:
            print(f"\n测试 {desc}...")
            start_time = time.time()
            
            result = await run_batch_backtest(
                codes=codes,
                strategy='ma_cross',
                initial_capital=100000,
                use_parallel=True
            )
            
            elapsed = time.time() - start_time
            
            if result['success']:
                results.append({
                    'count': len(codes),
                    'time': elapsed,
                    'desc': desc
                })
                print(f"✅ {desc}: {elapsed:.2f}秒")
        
        # 分析可扩展性
        print("\n" + "="*60)
        print("可扩展性分析")
        print("="*60)
        
        for r in results:
            time_per_stock = r['time'] / r['count']
            print(f"{r['desc']}: {r['time']:.2f}秒 (平均 {time_per_stock:.2f}秒/股)")
        
        # 检查是否接近线性扩展
        if len(results) >= 2:
            first_time_per_stock = results[0]['time'] / results[0]['count']
            last_time_per_stock = results[-1]['time'] / results[-1]['count']
            
            if last_time_per_stock < first_time_per_stock * 1.5:
                print("\n✅ 扩展性良好，接近线性扩展")
            else:
                print("\n⚠️  扩展性一般，随股票数量增加性能下降")
    
    @pytest.mark.asyncio
    async def test_different_strategies(self):
        """测试不同策略的性能"""
        print("\n" + "="*60)
        print("不同策略性能测试")
        print("="*60)
        
        from akshare_mcp.tools.backtest import run_batch_backtest
        
        test_codes = ['600519', '000858', '002304']
        strategies = ['ma_cross', 'momentum', 'rsi']
        
        for strategy in strategies:
            print(f"\n测试策略: {strategy}")
            start_time = time.time()
            
            result = await run_batch_backtest(
                codes=test_codes,
                strategy=strategy,
                initial_capital=100000,
                use_parallel=True
            )
            
            elapsed = time.time() - start_time
            
            if result['success']:
                print(f"✅ {strategy}: {elapsed:.2f}秒")
                if 'summary' in result['data']:
                    summary = result['data']['summary']
                    print(f"   平均收益: {summary['avg_return_pct']}")
                    print(f"   平均夏普: {summary['avg_sharpe_ratio']:.2f}")


@pytest.mark.asyncio
async def test_all_performance():
    """运行所有性能测试"""
    print("\n" + "="*60)
    print("回测性能完整测试套件")
    print("="*60)
    
    perf_tests = TestBacktestPerformance()
    
    # 1. 顺序vs并行对比
    await perf_tests.test_sequential_vs_parallel()
    
    # 2. 可扩展性测试
    await perf_tests.test_scalability()
    
    # 3. 不同策略性能
    await perf_tests.test_different_strategies()
    
    print("\n" + "="*60)
    print("✅ 所有性能测试完成！")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(test_all_performance())
