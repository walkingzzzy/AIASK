"""
情绪分析模块测试
"""
import pytest
from unittest.mock import Mock, patch

# 导入被测试模块
from packages.core.sentiment.news_crawler import NewsCrawler, NewsArticle
from packages.core.sentiment.sentiment_analyzer import SentimentAnalyzer, SentimentResult
from packages.core.sentiment.event_detector import EventDetector, StockEvent, EventType


class TestNewsCrawler:
    """新闻爬虫测试"""
    
    def test_init(self):
        """测试初始化"""
        crawler = NewsCrawler()
        assert crawler is not None
    
    def test_extract_stock_codes(self):
        """测试股票代码提取"""
        crawler = NewsCrawler()
        
        text = "贵州茅台(600519)今日涨停，比亚迪(002594)跟涨"
        codes = crawler.extract_stock_codes(text)
        
        assert '600519' in codes
        assert '002594' in codes
    
    def test_extract_keywords(self):
        """测试关键词提取"""
        crawler = NewsCrawler()
        
        text = "公司业绩大增，利好消息刺激涨停"
        keywords = crawler.extract_keywords(text)
        
        assert '业绩' in keywords or '利好' in keywords or '涨停' in keywords
    
    def test_get_stock_news(self):
        """测试获取股票新闻"""
        crawler = NewsCrawler()
        
        # 获取新闻（可能返回模拟数据）
        news_list = crawler.get_stock_news("600519", days=7, limit=5)
        
        # 验证返回类型
        assert isinstance(news_list, list)
        
        # 如果有数据，验证结构
        if news_list:
            assert isinstance(news_list[0], NewsArticle)
            assert news_list[0].title
    
    def test_get_market_news(self):
        """测试获取市场新闻"""
        crawler = NewsCrawler()
        
        news_list = crawler.get_market_news(limit=5)
        
        assert isinstance(news_list, list)
        assert len(news_list) <= 5


class TestSentimentAnalyzer:
    """情绪分析器测试"""
    
    def test_init(self):
        """测试初始化"""
        analyzer = SentimentAnalyzer()
        assert analyzer is not None
    
    def test_analyze_text_positive(self):
        """测试正面文本分析"""
        analyzer = SentimentAnalyzer()
        
        text = "公司业绩大增，利好消息刺激股价涨停"
        score, keywords = analyzer.analyze_text(text)
        
        assert score > 0  # 正面情绪
        assert len(keywords) > 0
    
    def test_analyze_text_negative(self):
        """测试负面文本分析"""
        analyzer = SentimentAnalyzer()
        
        text = "公司业绩亏损，利空消息导致股价跌停"
        score, keywords = analyzer.analyze_text(text)
        
        assert score < 0  # 负面情绪
        assert len(keywords) > 0
    
    def test_analyze_text_neutral(self):
        """测试中性文本分析"""
        analyzer = SentimentAnalyzer()
        
        text = "公司发布公告，召开股东大会"
        score, keywords = analyzer.analyze_text(text)
        
        # 中性文本分数接近0
        assert -0.3 <= score <= 0.3
    
    def test_analyze_stock(self):
        """测试个股情绪分析"""
        analyzer = SentimentAnalyzer()
        
        result = analyzer.analyze_stock("600519", "贵州茅台")
        
        assert isinstance(result, SentimentResult)
        assert result.stock_code == "600519"
        assert -1 <= result.overall_score <= 1
        assert result.sentiment_level in ['极度看多', '偏多', '中性', '偏空', '极度看空']
    
    def test_sentiment_level_mapping(self):
        """测试情绪级别映射"""
        analyzer = SentimentAnalyzer()
        
        # 测试不同分数对应的级别
        assert analyzer._get_sentiment_level(0.6) == "极度看多"
        assert analyzer._get_sentiment_level(0.3) == "偏多"
        assert analyzer._get_sentiment_level(0.0) == "中性"
        assert analyzer._get_sentiment_level(-0.3) == "偏空"
        assert analyzer._get_sentiment_level(-0.6) == "极度看空"


class TestEventDetector:
    """事件检测器测试"""
    
    def test_init(self):
        """测试初始化"""
        detector = EventDetector()
        assert detector is not None
    
    def test_detect_earnings_event(self):
        """测试业绩事件检测"""
        detector = EventDetector()
        
        article = NewsArticle(
            title="公司业绩预增100%，超出市场预期",
            content="公司发布业绩预告，净利润同比增长100%",
            source="announcement",
            publish_time="2024-12-09"
        )
        
        event = detector.detect_single_event(article, "600519", "贵州茅台")
        
        assert event is not None
        assert event.impact_score > 0  # 正面影响
    
    def test_detect_negative_event(self):
        """测试负面事件检测"""
        detector = EventDetector()
        
        article = NewsArticle(
            title="公司收到监管处罚通知",
            content="公司因违规操作被证监会处罚",
            source="announcement",
            publish_time="2024-12-09"
        )
        
        event = detector.detect_single_event(article, "600519", "贵州茅台")
        
        assert event is not None
        assert event.impact_score < 0  # 负面影响
    
    def test_detect_events_batch(self):
        """测试批量事件检测"""
        detector = EventDetector()
        
        articles = [
            NewsArticle(
                title="公司业绩大增",
                content="净利润增长50%",
                source="news",
                publish_time="2024-12-09"
            ),
            NewsArticle(
                title="公司获得重大合同",
                content="签订10亿元订单",
                source="announcement",
                publish_time="2024-12-08"
            ),
        ]
        
        events = detector.detect_events(articles, "600519", "贵州茅台")
        
        assert isinstance(events, list)
    
    def test_get_event_summary(self):
        """测试事件摘要"""
        detector = EventDetector()
        
        events = [
            StockEvent(
                stock_code="600519",
                stock_name="贵州茅台",
                event_type="业绩超预期",
                event_title="业绩大增",
                impact="利好",
                impact_score=0.8
            ),
            StockEvent(
                stock_code="600519",
                stock_name="贵州茅台",
                event_type="监管处罚",
                event_title="收到警示函",
                impact="利空",
                impact_score=-0.5
            ),
        ]
        
        summary = detector.get_event_summary(events)
        
        assert summary['total_events'] == 2
        assert summary['positive_events'] == 1
        assert summary['negative_events'] == 1


class TestSentimentIntegration:
    """情绪分析集成测试"""
    
    def test_full_sentiment_analysis_flow(self):
        """测试完整情绪分析流程"""
        analyzer = SentimentAnalyzer()
        
        # 执行完整分析
        result = analyzer.analyze_stock("600519", "贵州茅台")
        
        # 验证结果完整性
        assert result.stock_code == "600519"
        assert result.stock_name == "贵州茅台"
        assert isinstance(result.overall_score, float)
        assert isinstance(result.news_sentiment, dict)
        assert isinstance(result.announcement_sentiment, dict)
        assert isinstance(result.research_sentiment, dict)
        assert isinstance(result.key_events, list)
        assert result.updated_at


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
