"""
优先级3功能测试 - 向量搜索、NLP、组合优化、知识图谱
"""

import pytest
import numpy as np
from akshare_mcp.services.vector_search import vector_search_engine
from akshare_mcp.services.nlp_query_engine import nlp_query_engine
from akshare_mcp.services.portfolio_optimization import portfolio_optimizer
from akshare_mcp.services.industry_knowledge_graph import industry_kg


# ========== 向量搜索测试 ==========

class TestVectorSearch:
    """向量搜索测试"""
    
    def test_kline_to_vector_price_volume(self):
        """测试K线向量化 - 价格+成交量"""
        klines = [
            {'close': 10.0, 'volume': 1000},
            {'close': 10.5, 'volume': 1200},
            {'close': 11.0, 'volume': 1500},
        ]
        
        vector = vector_search_engine.kline_to_vector(klines, method='price_volume')
        
        assert len(vector) == 6  # 3个价格 + 3个成交量
        assert np.all(vector >= 0) and np.all(vector <= 1)  # 归一化到[0,1]
    
    def test_kline_to_vector_ohlc(self):
        """测试K线向量化 - OHLC"""
        klines = [
            {'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 1000},
            {'open': 10.2, 'high': 10.8, 'low': 10.0, 'close': 10.5, 'volume': 1200},
        ]
        
        vector = vector_search_engine.kline_to_vector(klines, method='ohlc')
        
        assert len(vector) == 8  # 2根K线 * 4个价格
    
    def test_calculate_similarity_cosine(self):
        """测试余弦相似度"""
        vector1 = np.array([1, 2, 3])
        vector2 = np.array([2, 4, 6])
        
        similarity = vector_search_engine.calculate_similarity(vector1, vector2, metric='cosine')
        
        assert 0 <= similarity <= 1
        assert similarity > 0.99  # 应该非常相似（方向相同）
    
    def test_calculate_similarity_euclidean(self):
        """测试欧氏距离相似度"""
        vector1 = np.array([1, 2, 3])
        vector2 = np.array([1, 2, 3])
        
        similarity = vector_search_engine.calculate_similarity(vector1, vector2, metric='euclidean')
        
        assert similarity == 1.0  # 完全相同
    
    def test_recognize_pattern(self):
        """测试形态识别"""
        # 上升趋势
        klines = [
            {'close': 10.0},
            {'close': 10.5},
            {'close': 11.0},
            {'close': 11.5},
            {'close': 12.0},
        ]
        
        result = vector_search_engine.recognize_pattern(klines)
        
        assert 'pattern' in result
        assert 'confidence' in result
        assert result['pattern'] in ['uptrend', 'downtrend', 'consolidation', 'unknown']
    
    def test_dtw_distance(self):
        """测试DTW距离"""
        series1 = np.array([1, 2, 3, 4, 5])
        series2 = np.array([1, 2, 3, 4, 5])
        
        distance = vector_search_engine.dtw_distance(series1, series2)
        
        assert distance == 0.0  # 完全相同


# ========== NLP查询测试 ==========

class TestNLPQuery:
    """NLP查询测试"""
    
    def test_detect_intent_query(self):
        """测试意图识别 - 查询"""
        queries = ['查询000001的价格', '看看今天的涨停股', '显示科技板块']
        
        for query in queries:
            intent = nlp_query_engine.detect_intent(query)
            assert intent == 'query'
    
    def test_detect_intent_analyze(self):
        """测试意图识别 - 分析"""
        queries = ['分析000001', '评估科技板块', '诊断这只股票']
        
        for query in queries:
            intent = nlp_query_engine.detect_intent(query)
            assert intent == 'analyze'
    
    def test_detect_intent_screen(self):
        """测试意图识别 - 选股"""
        queries = ['选股', '筛选高ROE股票', '过滤市盈率小于30的']
        
        for query in queries:
            intent = nlp_query_engine.detect_intent(query)
            assert intent == 'screen'
    
    def test_extract_entities_codes(self):
        """测试实体提取 - 股票代码"""
        query = '查询000001和000002的价格'
        
        entities = nlp_query_engine.extract_entities(query)
        
        assert '000001' in entities['codes']
        assert '000002' in entities['codes']
    
    def test_extract_entities_indicators(self):
        """测试实体提取 - 指标"""
        query = '查询市盈率和ROE'
        
        entities = nlp_query_engine.extract_entities(query)
        
        assert 'pe' in entities['indicators']
        assert 'roe' in entities['indicators']
    
    def test_extract_time_range(self):
        """测试时间范围提取"""
        query = '查询本周的数据'
        
        entities = nlp_query_engine.extract_entities(query)
        
        assert entities['time_range'] is not None
        assert 'start' in entities['time_range']
        assert 'end' in entities['time_range']
    
    def test_extract_conditions(self):
        """测试条件提取"""
        query = '选出市盈率小于30且ROE大于10的股票'
        
        entities = nlp_query_engine.extract_entities(query)
        
        assert len(entities['conditions']) >= 2
    
    def test_parse_query(self):
        """测试查询解析"""
        query = '查询000001的价格'
        
        parsed = nlp_query_engine.parse_query(query)
        
        assert 'intent' in parsed
        assert 'entities' in parsed
        assert 'action' in parsed
    
    def test_optimize_query(self):
        """测试查询优化"""
        query = '  帮我  看一下  000001  '
        
        optimized = nlp_query_engine.optimize_query(query)
        
        assert '帮我' not in optimized
        assert '  ' not in optimized


# ========== 组合优化测试 ==========

class TestPortfolioOptimization:
    """组合优化测试"""
    
    def test_mean_variance_optimization(self):
        """测试均值-方差优化"""
        expected_returns = np.array([0.10, 0.12, 0.08])
        cov_matrix = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.01],
            [0.02, 0.01, 0.03]
        ])
        
        result = portfolio_optimizer.mean_variance_optimization(
            expected_returns, cov_matrix, risk_aversion=1.0
        )
        
        assert 'weights' in result
        assert 'expected_return' in result
        assert 'volatility' in result
        assert 'sharpe_ratio' in result
        assert abs(sum(result['weights']) - 1.0) < 0.01  # 权重和为1
    
    def test_black_litterman(self):
        """测试Black-Litterman模型"""
        market_weights = np.array([0.4, 0.3, 0.3])
        cov_matrix = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.01],
            [0.02, 0.01, 0.03]
        ])
        views = [
            {'type': 'absolute', 'asset': 0, 'return': 0.12},
            {'type': 'relative', 'assets': [0, 1], 'return': 0.03}
        ]
        
        result = portfolio_optimizer.black_litterman(
            market_weights, cov_matrix, views
        )
        
        assert 'posterior_returns' in result
        assert 'optimal_weights' in result
        assert len(result['optimal_weights']) == 3
    
    def test_efficient_frontier(self):
        """测试有效前沿"""
        expected_returns = np.array([0.10, 0.12, 0.08])
        cov_matrix = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.01],
            [0.02, 0.01, 0.03]
        ])
        
        result = portfolio_optimizer.efficient_frontier(
            expected_returns, cov_matrix, n_points=10
        )
        
        assert 'frontier' in result
        assert 'max_sharpe_portfolio' in result
        assert len(result['frontier']) > 0
    
    def test_risk_parity(self):
        """测试风险平价"""
        cov_matrix = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.01],
            [0.02, 0.01, 0.03]
        ])
        
        result = portfolio_optimizer.risk_parity(cov_matrix)
        
        assert 'weights' in result
        assert 'risk_contributions' in result
        assert abs(sum(result['weights']) - 1.0) < 0.01
    
    def test_max_sharpe_ratio(self):
        """测试最大夏普比率"""
        expected_returns = np.array([0.10, 0.12, 0.08])
        cov_matrix = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.01],
            [0.02, 0.01, 0.03]
        ])
        
        result = portfolio_optimizer.max_sharpe_ratio(
            expected_returns, cov_matrix, risk_free_rate=0.03
        )
        
        assert 'weights' in result
        assert 'sharpe_ratio' in result
        assert result['sharpe_ratio'] > 0
    
    def test_min_variance(self):
        """测试最小方差"""
        cov_matrix = np.array([
            [0.04, 0.01, 0.02],
            [0.01, 0.05, 0.01],
            [0.02, 0.01, 0.03]
        ])
        
        result = portfolio_optimizer.min_variance(cov_matrix)
        
        assert 'weights' in result
        assert 'volatility' in result
        assert result['volatility'] > 0


# ========== 知识图谱测试 ==========

class TestIndustryKnowledgeGraph:
    """产业链知识图谱测试"""
    
    def test_get_upstream(self):
        """测试获取上游"""
        upstream = industry_kg.get_upstream('battery_cell', max_depth=2)
        
        assert len(upstream) > 0
        assert any(node['id'] == 'cathode_material' for node in upstream)
    
    def test_get_downstream(self):
        """测试获取下游"""
        downstream = industry_kg.get_downstream('battery_cell', max_depth=2)
        
        assert len(downstream) > 0
        assert any(node['id'] == 'battery_pack' for node in downstream)
    
    def test_get_full_chain(self):
        """测试获取完整产业链"""
        chain = industry_kg.get_full_chain('battery_cell')
        
        assert 'current' in chain
        assert 'upstream' in chain
        assert 'downstream' in chain
        assert chain['total_nodes'] > 1
    
    def test_find_path(self):
        """测试路径查找"""
        path = industry_kg.find_path('lithium_mining', 'ev_manufacturing')
        
        assert path is not None
        assert path[0] == 'lithium_mining'
        assert path[-1] == 'ev_manufacturing'
    
    def test_find_key_nodes(self):
        """测试关键节点识别"""
        key_nodes = industry_kg.find_key_nodes()
        
        assert len(key_nodes) > 0
        assert 'total_degree' in key_nodes[0]
    
    def test_analyze_chain(self):
        """测试产业链分析"""
        result = industry_kg.analyze_chain('电池')
        
        assert 'related_nodes' in result
        assert 'chains' in result
        assert len(result['related_nodes']) > 0
    
    def test_analyze_impact_propagation(self):
        """测试影响传导分析"""
        result = industry_kg.analyze_impact_propagation(
            'lithium_mining',
            impact_type='positive'
        )
        
        assert 'source_node' in result
        assert 'affected_nodes' in result
        assert len(result['affected_nodes']) > 0
    
    def test_identify_bottlenecks(self):
        """测试瓶颈识别"""
        bottlenecks = industry_kg.identify_bottlenecks()
        
        assert isinstance(bottlenecks, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
