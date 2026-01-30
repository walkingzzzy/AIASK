"""
测试P1阶段Manager工具改进 - 第二部分
测试data_sync_manager和fundamental_analysis_manager的增强功能
"""

import pytest
import asyncio
from datetime import datetime


class TestDataSyncManager:
    """测试数据同步管理器"""
    
    @pytest.mark.asyncio
    async def test_sync_status(self):
        """测试同步状态查询"""
        print("\n" + "="*60)
        print("测试数据同步状态查询...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import data_sync_manager
        
        result = await data_sync_manager(action='status')
        
        assert result['success'] is True
        assert 'last_sync' in result['data']
        assert 'status' in result['data']
        assert 'pending_tasks' in result['data']
        assert 'running_tasks' in result['data']
        
        print(f"✅ 同步状态: {result['data']['status']}")
        print(f"✅ 待处理任务: {result['data']['pending_tasks']}")
        print(f"✅ 运行中任务: {result['data']['running_tasks']}")
        print(f"✅ K线最后同步: {result['data']['last_sync'].get('kline', 'N/A')}")
    
    @pytest.mark.asyncio
    async def test_create_sync_task(self):
        """测试创建同步任务"""
        print("\n" + "="*60)
        print("测试创建同步任务...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import data_sync_manager
        
        result = await data_sync_manager(
            action='sync',
            type='kline',
            codes=['000001', '600519', '000858'],
            priority='high'
        )
        
        assert result['success'] is True
        assert 'task_id' in result['data']
        assert result['data']['codes_count'] == 3
        assert result['data']['priority'] == 'high'
        assert result['data']['status'] == 'pending'
        
        print(f"✅ 任务ID: {result['data']['task_id']}")
        print(f"✅ 任务类型: {result['data']['task_type']}")
        print(f"✅ 股票数量: {result['data']['codes_count']}")
        print(f"✅ 优先级: {result['data']['priority']}")
        
        return result['data']['task_id']
    
    @pytest.mark.asyncio
    async def test_list_tasks(self):
        """测试任务列表查询"""
        print("\n" + "="*60)
        print("测试任务列表查询...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import data_sync_manager
        
        # 先创建一个任务
        await data_sync_manager(
            action='sync',
            type='quote',
            codes=['000001'],
            priority='normal'
        )
        
        # 查询任务列表
        result = await data_sync_manager(
            action='list_tasks',
            status='pending',
            limit=10
        )
        
        assert result['success'] is True
        assert 'tasks' in result['data']
        assert 'count' in result['data']
        
        print(f"✅ 待处理任务数: {result['data']['count']}")
        if result['data']['tasks']:
            print(f"✅ 最新任务ID: {result['data']['tasks'][0]['task_id']}")
    
    @pytest.mark.asyncio
    async def test_schedule_task(self):
        """测试定时任务调度"""
        print("\n" + "="*60)
        print("测试定时任务调度...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import data_sync_manager
        
        result = await data_sync_manager(
            action='schedule',
            type='kline',
            codes=['000001', '600519'],
            schedule='daily'
        )
        
        assert result['success'] is True
        assert 'schedule_id' in result['data']
        assert result['data']['schedule'] == 'daily'
        assert result['data']['enabled'] is True
        
        print(f"✅ 调度ID: {result['data']['schedule_id']}")
        print(f"✅ 调度频率: {result['data']['schedule']}")
        print(f"✅ 股票数量: {result['data']['codes_count']}")


class TestFundamentalAnalysisManager:
    """测试基本面分析管理器"""
    
    @pytest.mark.asyncio
    async def test_basic_analyze(self):
        """测试基础分析"""
        print("\n" + "="*60)
        print("测试基本面基础分析...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import fundamental_analysis_manager
        
        result = await fundamental_analysis_manager(
            action='analyze',
            code='600519'
        )
        
        assert result['success'] is True
        assert 'code' in result['data']
        assert 'analysis' in result['data']
        
        analysis = result['data']['analysis']
        print(f"✅ 股票代码: {result['data']['code']}")
        print(f"✅ 营收趋势: {analysis.get('revenue_trend', 'N/A')}")
        print(f"✅ 盈利能力: {analysis.get('profitability', 'N/A')}")
        print(f"✅ ROE: {analysis.get('roe', 0):.2f}%")
    
    @pytest.mark.asyncio
    async def test_dupont_analysis(self):
        """测试杜邦分析"""
        print("\n" + "="*60)
        print("测试杜邦分析...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import fundamental_analysis_manager
        
        result = await fundamental_analysis_manager(
            action='dupont_analysis',
            code='600519'
        )
        
        assert result['success'] is True
        assert 'roe' in result['data']
        assert 'components' in result['data']
        assert 'strengths' in result['data']
        assert 'weaknesses' in result['data']
        
        roe = result['data']['roe']
        components = result['data']['components']
        
        print(f"✅ ROE: {roe['percentage']}")
        print(f"✅ 净利率: {components['net_profit_margin']['percentage']} ({components['net_profit_margin']['level']})")
        print(f"✅ 资产周转率: {components['asset_turnover']['value']:.2f} ({components['asset_turnover']['level']})")
        print(f"✅ 权益乘数: {components['equity_multiplier']['value']:.2f} ({components['equity_multiplier']['level']})")
        print(f"✅ 优势: {', '.join(result['data']['strengths'])}")
        if result['data']['weaknesses']:
            print(f"⚠️  劣势: {', '.join(result['data']['weaknesses'])}")
    
    @pytest.mark.asyncio
    async def test_peer_comparison(self):
        """测试同行对比"""
        print("\n" + "="*60)
        print("测试同行对比...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import fundamental_analysis_manager
        
        result = await fundamental_analysis_manager(
            action='compare',
            codes=['600519', '000858', '002304']
        )
        
        assert result['success'] is True
        assert 'comparison' in result['data']
        assert 'averages' in result['data']
        assert 'highlights' in result['data']
        
        print(f"✅ 对比股票数: {len(result['data']['comparison'])}")
        print(f"✅ 平均ROE: {result['data']['averages'].get('roe', 0):.2f}%")
        print(f"✅ 最佳ROE: {result['data']['highlights']['best_roe']['code']} ({result['data']['highlights']['best_roe']['value']:.2f}%)")
        
        # 打印对比表格
        print("\n对比结果:")
        for item in result['data']['comparison']:
            print(f"  {item['code']}: ROE={item['roe']:.2f}%, PE={item['pe_ratio']:.2f}, PB={item['pb_ratio']:.2f}")
    
    @pytest.mark.asyncio
    async def test_dcf_valuation(self):
        """测试DCF估值"""
        print("\n" + "="*60)
        print("测试DCF估值...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import fundamental_analysis_manager
        
        result = await fundamental_analysis_manager(
            action='intrinsic_value',
            code='600519',
            method='dcf',
            growth_rate=0.12,
            discount_rate=0.10,
            terminal_growth=0.03,
            years=5
        )
        
        assert result['success'] is True
        assert result['data']['method'] == 'DCF'
        assert 'intrinsic_value' in result['data']
        assert 'intrinsic_price_per_share' in result['data']
        assert 'assumptions' in result['data']
        assert 'components' in result['data']
        
        print(f"✅ 估值方法: {result['data']['method']}")
        print(f"✅ 企业价值: {result['data']['intrinsic_value']:,.0f}")
        print(f"✅ 每股内在价值: {result['data']['intrinsic_price_per_share']:.2f}")
        print(f"✅ 假设条件:")
        for key, value in result['data']['assumptions'].items():
            print(f"    {key}: {value}")
    
    @pytest.mark.asyncio
    async def test_pe_valuation(self):
        """测试PE估值"""
        print("\n" + "="*60)
        print("测试PE估值...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import fundamental_analysis_manager
        
        result = await fundamental_analysis_manager(
            action='intrinsic_value',
            code='600519',
            method='pe',
            industry_pe=25
        )
        
        assert result['success'] is True
        assert result['data']['method'] == 'PE'
        assert 'intrinsic_price_per_share' in result['data']
        assert 'eps' in result['data']
        assert 'industry_pe' in result['data']
        
        print(f"✅ 估值方法: {result['data']['method']}")
        print(f"✅ EPS: {result['data']['eps']:.2f}")
        print(f"✅ 行业PE: {result['data']['industry_pe']:.2f}")
        print(f"✅ 每股内在价值: {result['data']['intrinsic_price_per_share']:.2f}")
    
    @pytest.mark.asyncio
    async def test_pb_valuation(self):
        """测试PB估值"""
        print("\n" + "="*60)
        print("测试PB估值...")
        print("="*60)
        
        from akshare_mcp.tools.managers_complete import fundamental_analysis_manager
        
        result = await fundamental_analysis_manager(
            action='intrinsic_value',
            code='600519',
            method='pb',
            industry_pb=3.0
        )
        
        assert result['success'] is True
        assert result['data']['method'] == 'PB'
        assert 'intrinsic_price_per_share' in result['data']
        assert 'bvps' in result['data']
        assert 'industry_pb' in result['data']
        
        print(f"✅ 估值方法: {result['data']['method']}")
        print(f"✅ BVPS: {result['data']['bvps']:.2f}")
        print(f"✅ 行业PB: {result['data']['industry_pb']:.2f}")
        print(f"✅ 每股内在价值: {result['data']['intrinsic_price_per_share']:.2f}")


@pytest.mark.asyncio
async def test_all_manager_improvements_part2():
    """运行所有第二部分Manager改进测试"""
    print("\n" + "="*60)
    print("P1阶段Manager工具改进 - 第二部分测试")
    print("="*60)
    
    # 测试data_sync_manager
    sync_tests = TestDataSyncManager()
    await sync_tests.test_sync_status()
    await sync_tests.test_create_sync_task()
    await sync_tests.test_list_tasks()
    await sync_tests.test_schedule_task()
    
    # 测试fundamental_analysis_manager
    fundamental_tests = TestFundamentalAnalysisManager()
    await fundamental_tests.test_basic_analyze()
    await fundamental_tests.test_dupont_analysis()
    await fundamental_tests.test_peer_comparison()
    await fundamental_tests.test_dcf_valuation()
    await fundamental_tests.test_pe_valuation()
    await fundamental_tests.test_pb_valuation()
    
    print("\n" + "="*60)
    print("✅ 所有第二部分Manager工具改进测试通过！")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(test_all_manager_improvements_part2())
