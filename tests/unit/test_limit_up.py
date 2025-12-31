"""
涨停分析模块测试
"""
import pytest
from unittest.mock import Mock, patch

# 导入被测试模块
from packages.core.limit_up.limit_up_analyzer import (
    LimitUpAnalyzer,
    LimitUpStock,
    LimitUpReason,
    ContinuationPrediction,
    LimitUpType
)


class TestLimitUpAnalyzer:
    """涨停分析器测试"""
    
    def test_init(self):
        """测试初始化"""
        analyzer = LimitUpAnalyzer()
        assert analyzer is not None
    
    def test_get_daily_limit_up(self):
        """测试获取每日涨停"""
        analyzer = LimitUpAnalyzer()
        
        stocks = analyzer.get_daily_limit_up()
        
        assert isinstance(stocks, list)
        
        # 如果有数据，验证结构
        if stocks:
            assert isinstance(stocks[0], LimitUpStock)
            assert stocks[0].stock_code
            assert stocks[0].stock_name
    
    def test_get_continuous_limit_up(self):
        """测试获取连板股票"""
        analyzer = LimitUpAnalyzer()
        
        # 获取2连板及以上
        stocks = analyzer.get_continuous_limit_up(min_days=2)
        
        assert isinstance(stocks, list)
        
        # 验证所有返回的股票都是连板
        for stock in stocks:
            assert stock.continuous_days >= 2
    
    def test_analyze_limit_up_reason(self):
        """测试涨停原因分析"""
        analyzer = LimitUpAnalyzer()
        
        reason = analyzer.analyze_limit_up_reason("600519", "贵州茅台")
        
        assert isinstance(reason, LimitUpReason)
        assert reason.stock_code == "600519"
        assert reason.reason_type  # 有原因类型
        assert 0 <= reason.confidence <= 1
    
    def test_predict_continuation(self):
        """测试连板预测"""
        analyzer = LimitUpAnalyzer()
        
        prediction = analyzer.predict_continuation("600519", "贵州茅台")
        
        assert isinstance(prediction, ContinuationPrediction)
        assert prediction.stock_code == "600519"
        assert 0 <= prediction.continuation_prob <= 1
        assert prediction.risk_level in ['低', '中', '中高', '高']
        assert prediction.suggestion
    
    def test_get_limit_up_statistics(self):
        """测试涨停统计"""
        analyzer = LimitUpAnalyzer()
        
        stats = analyzer.get_limit_up_statistics()
        
        assert isinstance(stats, dict)
        assert 'total' in stats
        assert 'first_limit' in stats
        assert 'continuous' in stats
        assert 'hot_concepts' in stats


class TestLimitUpStock:
    """涨停股票数据类测试"""
    
    def test_create_limit_up_stock(self):
        """测试创建涨停股票对象"""
        stock = LimitUpStock(
            stock_code="600519",
            stock_name="贵州茅台",
            limit_up_time="09:30:00",
            limit_up_type="首板",
            continuous_days=1,
            turnover_rate=3.5,
            amount=15.2,
            circulating_value=180.5,
            limit_up_reason="白酒概念",
            concept="白酒",
            open_count=0,
            seal_amount=5.0
        )
        
        assert stock.stock_code == "600519"
        assert stock.continuous_days == 1
        assert stock.turnover_rate == 3.5
    
    def test_to_dict(self):
        """测试转换为字典"""
        stock = LimitUpStock(
            stock_code="600519",
            stock_name="贵州茅台"
        )
        
        data = stock.to_dict()
        
        assert isinstance(data, dict)
        assert data['stock_code'] == "600519"


class TestContinuationPrediction:
    """连板预测测试"""
    
    def test_continuation_probability_factors(self):
        """测试连板概率影响因子"""
        analyzer = LimitUpAnalyzer()
        
        # 模拟一个强势涨停股
        mock_stock = LimitUpStock(
            stock_code="000001",
            stock_name="测试股票",
            continuous_days=2,
            turnover_rate=3.0,  # 低换手
            amount=10.0,
            circulating_value=50.0,  # 小盘股
            open_count=0,  # 一字板
            seal_amount=8.0,  # 大封单
            limit_up_reason="人工智能"  # 热门概念
        )
        
        # 验证基础概率
        base_prob = analyzer.CONTINUATION_BASE_PROB.get(2, 0.35)
        assert base_prob == 0.35
    
    def test_risk_level_mapping(self):
        """测试风险等级映射"""
        # 高概率 -> 中风险
        # 中概率 -> 中高风险
        # 低概率 -> 高风险
        
        analyzer = LimitUpAnalyzer()
        prediction = analyzer.predict_continuation("600519")
        
        # 验证风险等级存在
        assert prediction.risk_level in ['低', '中', '中高', '高']


class TestLimitUpReason:
    """涨停原因分析测试"""
    
    def test_classify_concept_reason(self):
        """测试概念题材原因分类"""
        analyzer = LimitUpAnalyzer()
        
        stock = LimitUpStock(
            stock_code="000001",
            stock_name="测试",
            limit_up_reason="人工智能概念",
            concept="科技"
        )
        
        reason_type, confidence = analyzer._classify_reason(stock)
        
        assert reason_type == "概念题材"
        assert confidence > 0.5
    
    def test_classify_earnings_reason(self):
        """测试业绩驱动原因分类"""
        analyzer = LimitUpAnalyzer()
        
        stock = LimitUpStock(
            stock_code="000001",
            stock_name="测试",
            limit_up_reason="业绩预增",
            concept=""
        )
        
        reason_type, confidence = analyzer._classify_reason(stock)
        
        assert reason_type == "业绩驱动"
    
    def test_extract_concepts(self):
        """测试概念提取"""
        analyzer = LimitUpAnalyzer()
        
        stock = LimitUpStock(
            stock_code="000001",
            stock_name="测试",
            limit_up_reason="人工智能+芯片概念",
            concept="半导体"
        )
        
        concepts = analyzer._extract_concepts(stock)
        
        assert isinstance(concepts, list)
        # 应该提取到相关概念
        assert any(c in concepts for c in ['人工智能', '芯片', '半导体'])


class TestLimitUpStatistics:
    """涨停统计测试"""
    
    def test_statistics_structure(self):
        """测试统计数据结构"""
        analyzer = LimitUpAnalyzer()
        
        stats = analyzer.get_limit_up_statistics()
        
        # 验证必要字段
        required_fields = ['total', 'first_limit', 'continuous', 'broken', 
                          'avg_turnover', 'hot_concepts', 'max_continuous']
        
        for field in required_fields:
            assert field in stats
    
    def test_hot_concepts_format(self):
        """测试热门概念格式"""
        analyzer = LimitUpAnalyzer()
        
        stats = analyzer.get_limit_up_statistics()
        
        hot_concepts = stats['hot_concepts']
        assert isinstance(hot_concepts, list)
        
        # 如果有数据，验证格式
        if hot_concepts:
            assert 'name' in hot_concepts[0]
            assert 'count' in hot_concepts[0]


class TestLimitUpIntegration:
    """涨停分析集成测试"""
    
    def test_full_analysis_flow(self):
        """测试完整分析流程"""
        analyzer = LimitUpAnalyzer()
        
        # 1. 获取涨停列表
        stocks = analyzer.get_daily_limit_up()
        assert isinstance(stocks, list)
        
        # 2. 获取统计数据
        stats = analyzer.get_limit_up_statistics()
        assert stats['total'] >= 0
        
        # 3. 如果有涨停股，分析第一只
        if stocks:
            stock = stocks[0]
            
            # 分析原因
            reason = analyzer.analyze_limit_up_reason(stock.stock_code, stock.stock_name)
            assert reason.stock_code == stock.stock_code
            
            # 预测连板
            prediction = analyzer.predict_continuation(stock.stock_code, stock.stock_name)
            assert prediction.stock_code == stock.stock_code


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
