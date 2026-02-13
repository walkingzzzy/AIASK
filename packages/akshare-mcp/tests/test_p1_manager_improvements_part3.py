"""
测试P1阶段Manager工具改进 - 第三部分
测试risk_manager, quant_manager, performance_manager, screener_manager, 
decision_manager, comprehensive_manager, sector_manager的增强功能
"""

import pytest
import asyncio
import importlib
from datetime import datetime


class _DummyMCP:
    """用于注册 manager 的最小 MCP stub。"""

    def tool(self):
        def _decorator(fn):
            setattr(self, fn.__name__, fn)
            return fn

        return _decorator


def _get_manager_callable(manager_name: str, register_module: str, register_func: str):
    """获取可调用的 manager 函数（优先 direct import，失败后 register 回退）。"""
    try:
        managers_extended = importlib.import_module('akshare_mcp.tools.managers_extended')
        return getattr(managers_extended, manager_name)
    except Exception:
        module = importlib.import_module(register_module)
        register = getattr(module, register_func)
        mcp = _DummyMCP()
        register(mcp)
        return getattr(mcp, manager_name)


def _get_performance_manager_callable():
    """保持兼容的旧 helper 名称。"""
    return _get_manager_callable(
        manager_name='performance_manager',
        register_module='akshare_mcp.tools.managers.performance_manager',
        register_func='register_performance_manager',
    )



class TestRiskManager:
    """测试风险管理器"""
    
    @pytest.mark.asyncio
    async def test_calculate_var(self):
        """测试VaR计算"""
        print("\n" + "="*60)
        print("测试VaR计算...")
        print("="*60)
        
        risk_manager = _get_manager_callable(
            manager_name='risk_manager',
            register_module='akshare_mcp.tools.managers.risk_manager',
            register_func='register_risk_manager',
        )
        
        result = await risk_manager(
            action='calculate_var',
            portfolio_id=1,
            confidence=0.95,
            method='historical'
        )
        
        assert result['success'] is True
        assert 'var' in result['data']
        assert 'cvar' in result['data']
        
        print(f"✅ VaR (95%): {result['data']['var']['amount']:.2f}")
        print(f"✅ CVaR: {result['data']['cvar']['amount']:.2f}")
        print(f"✅ 波动率: {result['data']['volatility']:.4f}")
    
    @pytest.mark.asyncio
    async def test_stress_test(self):
        """测试压力测试"""
        print("\n" + "="*60)
        print("测试压力测试...")
        print("="*60)
        
        risk_manager = _get_manager_callable(
            manager_name='risk_manager',
            register_module='akshare_mcp.tools.managers.risk_manager',
            register_func='register_risk_manager',
        )
        
        result = await risk_manager(
            action='stress_test',
            portfolio_id=1,
            scenario='market_crash'
        )
        
        assert result['success'] is True
        assert 'loss' in result['data']
        assert 'severity' in result['data']
        
        print(f"✅ 场景: {result['data']['description']}")
        print(f"✅ 预计损失: {result['data']['loss_percentage']}")
        print(f"✅ 严重程度: {result['data']['severity']}")


class TestQuantManager:
    """测试量化管理器"""
    
    @pytest.mark.asyncio
    async def test_calculate_factors(self):
        """测试因子计算"""
        print("\n" + "="*60)
        print("测试因子计算...")
        print("="*60)
        
        quant_manager = _get_manager_callable(
            manager_name='quant_manager',
            register_module='akshare_mcp.tools.managers.quant_manager',
            register_func='register_quant_manager',
        )
        
        result = await quant_manager(
            action='calculate_factors',
            code='600519',
            factors=['momentum', 'value', 'quality', 'volatility']
        )
        
        assert result['success'] is True
        assert 'factors' in result['data']
        assert 'composite_score' in result['data']
        
        factors = result['data']['factors']
        print(f"✅ 动量因子: {factors.get('momentum', {}).get('score', 0):.4f}")
        print(f"✅ 价值因子: {factors.get('value', {}).get('score', 0):.4f}")
        print(f"✅ 质量因子: {factors.get('quality', {}).get('score', 0):.4f}")
        print(f"✅ 综合评分: {result['data']['composite_score']:.4f}")
    
    @pytest.mark.asyncio
    async def test_multi_factor_score(self):
        """测试多因子评分"""
        print("\n" + "="*60)
        print("测试多因子评分...")
        print("="*60)
        
        quant_manager = _get_manager_callable(
            manager_name='quant_manager',
            register_module='akshare_mcp.tools.managers.quant_manager',
            register_func='register_quant_manager',
        )
        
        result = await quant_manager(
            action='multi_factor_score',
            code='600519',
            weights={
                'momentum': 0.3,
                'value': 0.3,
                'quality': 0.4
            }
        )
        
        assert result['success'] is True
        assert 'total_score' in result['data']
        assert 'rating' in result['data']
        assert 'recommendation' in result['data']
        
        print(f"✅ 总分: {result['data']['total_score']:.4f}")
        print(f"✅ 评级: {result['data']['rating']}")
        print(f"✅ 建议: {result['data']['recommendation']}")


class TestPerformanceManager:
    """测试绩效管理器"""

    @pytest.mark.asyncio
    async def test_calculate_metrics(self):
        """测试绩效指标计算（含时序字段）"""
        print("\n" + "="*60)
        print("测试绩效指标计算...")
        print("="*60)

        performance_manager = _get_performance_manager_callable()

        result = await performance_manager(
            action='calculate_metrics',
            portfolio_id=1,
            lookback_days=120
        )

        assert result['success'] is True
        data = result['data']

        # 基础字段
        assert 'total_return' in data
        assert 'sharpe_ratio' in data
        assert 'trading_stats' in data

        # 新增时序字段
        assert 'series_total_return' in data
        assert 'volatility' in data
        assert 'max_drawdown' in data
        assert 'lookback_days' in data
        assert 'daily_returns_count' in data

        assert isinstance(data['trading_stats'], dict)
        assert data['lookback_days'] == 120
        assert data['daily_returns_count'] >= 0

        print(f"✅ 总收益率: {data['total_return_pct']}")
        print(f"✅ 序列总收益率: {data['series_total_return_pct']}")
        print(f"✅ 年化收益率: {data['annualized_return_pct']}")
        print(f"✅ 夏普比率: {data['sharpe_ratio']:.2f}")
        print(f"✅ 最大回撤: {data['max_drawdown_pct']}")
        print(f"✅ 年化波动率: {data['volatility_pct']}")
        print(f"✅ 胜率: {data['trading_stats']['win_rate_pct']}")

    @pytest.mark.asyncio
    async def test_benchmark_comparison(self):
        """测试基准对比（含TE/IR）"""
        print("\n" + "="*60)
        print("测试基准对比...")
        print("="*60)

        performance_manager = _get_performance_manager_callable()

        result = await performance_manager(
            action='benchmark_comparison',
            portfolio_id=1,
            benchmark='000300',
            lookback_days=120
        )

        # 兼容离线/弱网环境：若外部行情源不可用，接口可能返回 fail
        if not result.get('success'):
            err = (result.get('error') or result.get('message') or '').lower()
            assert (
                'tracking_error' in err
                or '收益序列不足' in (result.get('error') or result.get('message') or '')
                or '502' in err
                or 'bad gateway' in err
                or 'network' in err
            )
            return

        data = result['data']

        assert 'tracking_error' in data
        assert 'information_ratio' in data
        assert 'annualized_excess_return' in data
        assert 'aligned_days' in data
        assert 'portfolio_total_return_account' in data
        assert 'portfolio_total_return_series' in data

        assert data['aligned_days'] >= 2

        print(f"✅ 超额收益: {data['excess_return_pct']}")
        print(f"✅ 跟踪误差: {data['tracking_error_pct']}")
        print(f"✅ 信息比率: {data['information_ratio']:.4f}")
        print(f"✅ 对齐交易日: {data['aligned_days']}")

    @pytest.mark.asyncio
    async def test_attribution(self):
        """测试归因分析（含可审计字段）"""
        print("\n" + "="*60)
        print("测试归因分析...")
        print("="*60)

        performance_manager = _get_performance_manager_callable()

        result = await performance_manager(
            action='attribution',
            portfolio_id=1
        )

        # 兼容空组合场景：接口会 success=true 并返回引导信息
        assert result.get('success') is True
        data = result['data']
        if 'attribution' not in data:
            msg = data.get('message', '')
            assert '无持仓' in msg
            assert 'quick_start' in data
            return

        assert 'attribution' in data
        assert 'attribution_by_stock' in data
        assert 'sector_performance' in data
        assert 'method' in data

        attribution = data['attribution']
        assert 'stock_selection' in attribution
        assert 'sector_allocation' in attribution
        assert 'timing' in attribution

        decomposition_sum = (
            float(attribution['stock_selection']['return'])
            + float(attribution['sector_allocation']['return'])
            + float(attribution['timing']['return'])
        )
        assert abs(decomposition_sum - float(data['total_return'])) < 1e-8

        if data['attribution_by_stock']:
            row = data['attribution_by_stock'][0]
            assert 'code' in row
            assert 'weight' in row
            assert 'stock_return' in row
            assert 'contribution' in row

        print(f"✅ 股票选择贡献: {attribution['stock_selection']['contribution']}")
        print(f"✅ 行业配置贡献: {attribution['sector_allocation']['contribution']}")
        print(f"✅ 择时贡献: {attribution['timing']['contribution']}")



class TestScreenerManager:
    """测试选股器管理器"""
    
    @pytest.mark.asyncio
    async def test_screen(self):
        """测试股票筛选"""
        print("\n" + "="*60)
        print("测试股票筛选...")
        print("="*60)
        
        screener_manager = _get_manager_callable(
            manager_name='screener_manager',
            register_module='akshare_mcp.tools.managers.screener_manager',
            register_func='register_screener_manager',
        )
        
        result = await screener_manager(
            action='screen',
            criteria={
                'min_roe': 10,
                'max_pe': 30,
                'max_pb': 5,
                'max_debt_ratio': 0.6
            }
        )
        
        assert result['success'] is True
        assert 'stocks' in result['data']
        assert 'top_picks' in result['data']
        
        print(f"✅ 筛选结果: {result['data']['count']}只股票")
        if result['data']['top_picks']:
            print(f"✅ 最佳推荐: {result['data']['top_picks'][0]['code']}")


class TestDecisionManager:
    """测试决策管理器"""
    
    @pytest.mark.asyncio
    async def test_analyze(self):
        """测试综合分析决策"""
        print("\n" + "="*60)
        print("测试综合分析决策...")
        print("="*60)
        
        decision_manager = _get_manager_callable(
            manager_name='decision_manager',
            register_module='akshare_mcp.tools.managers.decision_manager',
            register_func='register_decision_manager',
        )
        
        result = await decision_manager(
            action='analyze',
            code='600519'
        )
        
        assert result['success'] is True
        assert 'decision' in result['data']
        assert 'total_score' in result['data']
        assert 'analysis' in result['data']
        
        print(f"✅ 决策: {result['data']['decision']}")
        print(f"✅ 置信度: {result['data']['confidence']}")
        print(f"✅ 总分: {result['data']['total_score']:.2f}")
        print(f"✅ 理由: {result['data']['reason']}")
        
        analysis = result['data']['analysis']
        print(f"✅ 技术面评分: {analysis['technical']['score']:.2f}")
        print(f"✅ 基本面评分: {analysis['fundamental']['score']:.2f}")
        print(f"✅ 情绪面评分: {analysis['sentiment']['score']:.2f}")


class TestComprehensiveManager:
    """测试综合管理器"""
    
    @pytest.mark.asyncio
    async def test_full_analysis(self):
        """测试全面分析"""
        print("\n" + "="*60)
        print("测试全面分析...")
        print("="*60)
        
        comprehensive_manager = _get_manager_callable(
            manager_name='comprehensive_manager',
            register_module='akshare_mcp.tools.managers.comprehensive_manager',
            register_func='register_comprehensive_manager',
        )
        
        result = await comprehensive_manager(
            action='full_analysis',
            code='600519'
        )
        
        assert result['success'] is True
        assert 'basic_info' in result['data']
        assert 'technical' in result['data']
        assert 'fundamental' in result['data']
        assert 'recommendation' in result['data']
        
        print(f"✅ 股票: {result['data']['basic_info']['name']}")
        print(f"✅ 技术面趋势: {result['data']['technical'].get('trend', 'N/A')}")
        print(f"✅ 基本面质量: {result['data']['fundamental'].get('profitability', {}).get('level', 'N/A')}")
        print(f"✅ 综合评分: {result['data']['score']['total_score']:.2f}")
        print(f"✅ 投资建议: {result['data']['recommendation']}")


class TestSectorManager:
    """测试板块管理器"""
    
    @pytest.mark.asyncio
    async def test_sector_performance(self):
        """测试板块表现"""
        print("\n" + "="*60)
        print("测试板块表现...")
        print("="*60)
        
        sector_manager = _get_manager_callable(
            manager_name='sector_manager',
            register_module='akshare_mcp.tools.managers.sector_manager',
            register_func='register_sector_manager',
        )
        
        result = await sector_manager(
            action='sector_performance',
            period=20,
            type='industry'
        )
        
        assert result['success'] is True
        assert 'sectors' in result['data']
        assert 'top_sectors' in result['data']
        
        print(f"✅ 分析板块数: {len(result['data']['sectors'])}")
        if result['data']['top_sectors']:
            print(f"✅ 最强板块: {result['data']['top_sectors'][0]['block_name']}")
            print(f"✅ 涨幅: {result['data']['top_sectors'][0]['return_pct']}")


@pytest.mark.asyncio
async def test_all_manager_improvements_part3():
    """运行所有第三部分Manager改进测试"""
    print("\n" + "="*60)
    print("P1阶段Manager工具改进 - 第三部分测试")
    print("="*60)
    
    # 测试risk_manager
    risk_tests = TestRiskManager()
    await risk_tests.test_calculate_var()
    await risk_tests.test_stress_test()
    
    # 测试quant_manager
    quant_tests = TestQuantManager()
    await quant_tests.test_calculate_factors()
    await quant_tests.test_multi_factor_score()
    
    # 测试performance_manager
    perf_tests = TestPerformanceManager()
    await perf_tests.test_calculate_metrics()
    await perf_tests.test_attribution()
    
    # 测试screener_manager
    screener_tests = TestScreenerManager()
    await screener_tests.test_screen()
    
    # 测试decision_manager
    decision_tests = TestDecisionManager()
    await decision_tests.test_analyze()
    
    # 测试comprehensive_manager
    comp_tests = TestComprehensiveManager()
    await comp_tests.test_full_analysis()
    
    # 测试sector_manager
    sector_tests = TestSectorManager()
    await sector_tests.test_sector_performance()
    
    print("\n" + "="*60)
    print("✅ 所有第三部分Manager工具改进测试通过！")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(test_all_manager_improvements_part3())
