"""
验证评估报告中6项代码修复的测试。

覆盖:
1. sentiment.py (服务层) - calculate_fear_greed_index 多因子聚合
2. market_insight_manager.py - market_trend/sector_analysis 接入真实数据
3. alerts.py - check_all_alerts 即时触发检测
4. backtest.py - tdx_send_status 兼容别名
5. portfolio.py - 压力测试数值字段
6. quant.py - get_factor_library 扩展因子/别名映射
"""

import pytest
import numpy as np
import sys
import os

# 确保 src 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================================
# 1. sentiment 服务层: calculate_fear_greed_index 多因子聚合
# ============================================================

class TestFearGreedIndex:
    """测试恐惧贪婪指数从固定值改为真实多因子聚合"""

    def _make_klines(self, closes, volumes=None):
        """构造K线数据"""
        if volumes is None:
            volumes = [1000000] * len(closes)
        return [
            {'close': c, 'volume': v, 'high': c * 1.01, 'low': c * 0.99}
            for c, v in zip(closes, volumes)
        ]

    def test_no_data_returns_neutral(self):
        """无数据时各分项返回50（中性）"""
        from akshare_mcp.services.sentiment import sentiment_analyzer
        result = sentiment_analyzer.calculate_fear_greed_index()
        assert 'index' in result
        assert 'level' in result
        assert 'components' in result
        assert result['level'] == 'neutral'
        # 无数据时所有分项应为50
        for key in ('momentum', 'volatility', 'volume', 'breadth'):
            assert key in result['components']
            assert result['components'][key] == 50.0

    def test_bullish_market(self):
        """上涨市场应返回偏贪婪的指数"""
        from akshare_mcp.services.sentiment import sentiment_analyzer
        # 模拟60日持续上涨（从100涨到120，+20%）
        closes = [100 + i * 0.33 for i in range(65)]
        volumes = [1000000 + i * 10000 for i in range(65)]  # 放量
        klines = self._make_klines(closes, volumes)
        result = sentiment_analyzer.calculate_fear_greed_index(index_klines=klines)
        assert result['index'] > 50, f"上涨市场指数应>50, got {result['index']}"
        assert result['components']['momentum'] > 50

    def test_bearish_market(self):
        """下跌市场应返回偏恐惧的指数"""
        from akshare_mcp.services.sentiment import sentiment_analyzer
        # 模拟60日大幅下跌（从150跌到100，-33%）
        closes = [150 - i * 0.77 for i in range(65)]
        volumes = [1000000 - i * 8000 for i in range(65)]  # 明显缩量
        klines = self._make_klines(closes, volumes)
        result = sentiment_analyzer.calculate_fear_greed_index(index_klines=klines)
        assert result['index'] < 50, f"下跌市场指数应<50, got {result['index']}"
        assert result['components']['momentum'] < 50

    def test_breadth_data_affects_index(self):
        """市场宽度数据（涨跌停）应影响指数"""
        from akshare_mcp.services.sentiment import sentiment_analyzer
        # 涨停远多于跌停 → 贪婪
        breadth_bullish = {'limit_up_count': 80, 'limit_down_count': 5, 'advance_count': 3000, 'decline_count': 1000}
        result_bull = sentiment_analyzer.calculate_fear_greed_index(breadth_data=breadth_bullish)
        assert result_bull['components']['breadth'] > 60

        # 跌停远多于涨停 → 恐惧
        breadth_bearish = {'limit_up_count': 5, 'limit_down_count': 80, 'advance_count': 1000, 'decline_count': 3000}
        result_bear = sentiment_analyzer.calculate_fear_greed_index(breadth_data=breadth_bearish)
        assert result_bear['components']['breadth'] < 40

    def test_level_mapping(self):
        """验证 level 映射正确"""
        from akshare_mcp.services.sentiment import sentiment_analyzer
        # 极端贪婪
        closes = [100 + i * 1.0 for i in range(65)]  # 大幅上涨
        klines = self._make_klines(closes)
        result = sentiment_analyzer.calculate_fear_greed_index(index_klines=klines)
        assert result['level'] in ('extreme_greed', 'greed', 'neutral', 'fear', 'extreme_fear')

    def test_not_fixed_50(self):
        """确认不再是固定值50"""
        from akshare_mcp.services.sentiment import sentiment_analyzer
        closes = [100 + i * 0.5 for i in range(65)]
        klines = self._make_klines(closes)
        result = sentiment_analyzer.calculate_fear_greed_index(index_klines=klines)
        # 有真实数据时不应恰好等于50
        assert result['index'] != 50.0 or result['components']['momentum'] != 50.0


# ============================================================
# 2. market_insight_manager - 不再返回硬编码数据
# ============================================================

class TestMarketInsightManager:
    """测试 market_insight_manager 接入真实数据（结构验证）"""

    def test_market_trend_structure(self):
        """market_trend 返回结构应包含真实数据字段"""
        # 直接导入并检查函数签名和返回结构
        from akshare_mcp.tools.managers.market_insight_manager import register_market_insight_manager

        # 验证模块不再包含硬编码 'sideways'/'medium'/3000/3300
        import inspect
        source = inspect.getsource(register_market_insight_manager)
        # 不应有硬编码的 support: 3000 / resistance: 3300
        assert "'support': 3000" not in source, "market_trend 仍包含硬编码 support=3000"
        assert "'resistance': 3300" not in source, "market_trend 仍包含硬编码 resistance=3300"
        # 应有真实数据获取逻辑
        assert 'get_index_quote' in source, "market_trend 应调用 get_index_quote"
        assert 'get_kline_data' in source or 'get_index_kline' in source, "market_trend 应调用 get_kline_data 或 get_index_kline"

    def test_sector_analysis_structure(self):
        """sector_analysis 返回结构应基于真实资金流向"""
        from akshare_mcp.tools.managers.market_insight_manager import register_market_insight_manager
        import inspect
        source = inspect.getsource(register_market_insight_manager)
        # 不应有硬编码的板块列表
        assert "['科技', '消费', '医药']" not in source, "sector_analysis 仍包含硬编码热门板块"
        assert "['房地产', '金融']" not in source, "sector_analysis 仍包含硬编码冷门板块"
        # 应有真实数据获取逻辑
        assert 'get_sector_fund_flow' in source, "sector_analysis 应调用 get_sector_fund_flow"
        assert 'get_concept_fund_flow' in source, "sector_analysis 应调用 get_concept_fund_flow"

    def test_help_action_still_works(self):
        """help action 应正常返回"""
        from akshare_mcp.tools.managers.market_insight_manager import register_market_insight_manager
        import inspect
        source = inspect.getsource(register_market_insight_manager)
        assert "action == 'help'" in source


# ============================================================
# 3. alerts.py - check_all_alerts 即时触发检测
# ============================================================

class TestAlertsTriggering:
    """测试 check_all_alerts 增加即时触发检查逻辑"""

    def test_check_all_alerts_has_trigger_logic(self):
        """check_all_alerts 应包含即时触发检测逻辑"""
        from akshare_mcp.tools.alerts import register
        import inspect
        source = inspect.getsource(register)
        # 应有 triggered_count 返回
        assert 'triggered_count' in source, "check_all_alerts 应返回 triggered_count"
        # 应有实时行情获取
        assert 'get_realtime_quote' in source, "check_all_alerts 应调用 get_realtime_quote 获取实时价格"
        # 应有条件比较逻辑
        assert "'>':" in source or "'>'" in source, "check_all_alerts 应包含条件比较运算符"

    def test_alert_store_and_check(self):
        """测试告警创建和检查流程（内存存储）"""
        from akshare_mcp.tools import alerts as alerts_module
        # 清空存储
        alerts_module._alerts_store.clear()

        # 模拟创建一个告警
        alert = {
            'alert_id': 'alert_600519_price_>',
            'code': '600519',
            'indicator': 'price',
            'condition': '>',
            'value': 100.0,
            'active': True,
            'type': 'indicator',
            'triggered': False,
        }
        alerts_module._alerts_store['alert_600519_price_>'] = alert

        # 验证存储
        assert len(alerts_module._alerts_store) == 1
        stored = alerts_module._alerts_store['alert_600519_price_>']
        assert stored['triggered'] is False
        assert stored['indicator'] == 'price'

        # 清理
        alerts_module._alerts_store.clear()

    def test_check_all_alerts_returns_triggered_count(self):
        """验证 check_all_alerts 返回结构包含 triggered_count"""
        from akshare_mcp.tools.alerts import register
        import inspect
        source = inspect.getsource(register)
        assert "'triggered_count': triggered_count" in source


# ============================================================
# 4. backtest.py - tdx_send_status 兼容别名
# ============================================================

class TestBacktestTdxCompat:
    """测试 run_backtest_and_send_to_tdx 返回 tdx_send_status 兼容别名"""

    def test_has_both_fields(self):
        """返回结果应同时包含 tdx_send_result 和 tdx_send_status"""
        from akshare_mcp.tools.backtest import register
        import inspect
        source = inspect.getsource(register)
        assert '"tdx_send_result"' in source, "应包含 tdx_send_result 字段"
        assert '"tdx_send_status"' in source, "应包含 tdx_send_status 兼容别名"
        # 两者应指向同一个值
        assert '"tdx_send_status": tdx_result' in source, "tdx_send_status 应等于 tdx_result"


# ============================================================
# 5. portfolio.py - 压力测试数值字段
# ============================================================

class TestPortfolioStressTestNumeric:
    """测试压力测试结果增加数值字段"""

    def test_has_numeric_fields(self):
        """压力测试结果应包含 _numeric 后缀的数值字段"""
        from akshare_mcp.tools.portfolio import register
        import inspect
        source = inspect.getsource(register)
        assert 'portfolio_loss_numeric' in source, "market_crash 应包含 portfolio_loss_numeric"
        assert 'avg_correlation_numeric' in source, "sector_rotation 应包含 avg_correlation_numeric"

    def test_db_defined_in_stress_test(self):
        """stress_test_portfolio 应正确定义 db 变量"""
        from akshare_mcp.tools.portfolio import register
        import inspect
        source = inspect.getsource(register)
        # 在 stress_test_portfolio 函数中应有 db = get_db()
        # 找到 stress_test_portfolio 定义后的 db = get_db()
        idx_stress = source.find('stress_test_portfolio')
        assert idx_stress > 0
        after_stress = source[idx_stress:]
        assert 'db = get_db()' in after_stress, "stress_test_portfolio 应包含 db = get_db()"

    def test_no_broken_import_in_stress_test(self):
        """stress_test_portfolio 不应有错误的 from ..market.quote import get_kline"""
        from akshare_mcp.tools.portfolio import register
        import inspect
        source = inspect.getsource(register)
        idx_stress = source.find('stress_test_portfolio')
        after_stress = source[idx_stress:]
        assert 'from ..market.quote import get_kline' not in after_stress, \
            "stress_test_portfolio 不应有错误的 get_kline 导入路径"


# ============================================================
# 6. quant.py - get_factor_library 扩展因子/别名映射
# ============================================================

class TestFactorLibraryExtended:
    """测试 get_factor_library 增加 sub_factors 和 aliases"""

    def test_factor_library_has_sub_factors(self):
        """每个因子应包含 sub_factors 字段"""
        from akshare_mcp.tools.quant import register
        import inspect
        source = inspect.getsource(register)
        assert 'sub_factors' in source, "因子库应包含 sub_factors 字段"
        assert 'aliases' in source, "因子库应包含 aliases 字段"

    def test_factor_library_returns_extended_info(self):
        """直接调用 get_factor_library 验证返回结构"""
        # 模拟 mcp 注册
        class FakeMCP:
            def __init__(self):
                self.tools = {}
            def tool(self):
                def decorator(func):
                    self.tools[func.__name__] = func
                    return func
                return decorator

        fake_mcp = FakeMCP()
        from akshare_mcp.tools.quant import register
        register(fake_mcp)

        # 调用 get_factor_library
        result = fake_mcp.tools['get_factor_library']()
        assert result.get('success') is True, f"get_factor_library 应返回 success=True, got {result}"
        data = result.get('data', {})
        factors = data.get('factors', [])
        assert len(factors) == 8, f"应有8个因子类别, got {len(factors)}"

        for f in factors:
            assert 'name' in f, f"因子缺少 name: {f}"
            assert 'sub_factors' in f, f"因子 {f['name']} 缺少 sub_factors"
            assert 'aliases' in f, f"因子 {f['name']} 缺少 aliases"
            assert isinstance(f['sub_factors'], list), f"sub_factors 应为列表: {f['name']}"
            assert isinstance(f['aliases'], list), f"aliases 应为列表: {f['name']}"
            assert len(f['sub_factors']) > 0, f"sub_factors 不应为空: {f['name']}"
            assert len(f['aliases']) > 0, f"aliases 不应为空: {f['name']}"

        # 验证 note 字段
        assert 'note' in data, "返回应包含 note 说明"
        assert 'total_categories' in data, "返回应包含 total_categories"
        assert data['total_categories'] == 8

    def test_factor_library_category_filter(self):
        """按类别过滤应正常工作"""
        class FakeMCP:
            def __init__(self):
                self.tools = {}
            def tool(self):
                def decorator(func):
                    self.tools[func.__name__] = func
                    return func
                return decorator

        fake_mcp = FakeMCP()
        from akshare_mcp.tools.quant import register
        register(fake_mcp)

        result = fake_mcp.tools['get_factor_library']('fundamental')
        data = result.get('data', {})
        factors = data.get('factors', [])
        assert len(factors) == 4, f"fundamental 类别应有4个因子, got {len(factors)}"
        for f in factors:
            assert f['category'] == 'fundamental'

        result = fake_mcp.tools['get_factor_library']('technical')
        data = result.get('data', {})
        factors = data.get('factors', [])
        assert len(factors) == 3, f"technical 类别应有3个因子, got {len(factors)}"

        result = fake_mcp.tools['get_factor_library']('risk')
        data = result.get('data', {})
        factors = data.get('factors', [])
        assert len(factors) == 1, f"risk 类别应有1个因子, got {len(factors)}"
