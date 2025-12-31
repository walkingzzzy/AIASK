"""
情绪分析模块
包含新闻爬虫、情绪分析、事件检测等功能
"""
from .news_crawler import NewsCrawler, NewsArticle
from .sentiment_analyzer import SentimentAnalyzer, SentimentResult
from .event_detector import EventDetector, StockEvent

__all__ = [
    'NewsCrawler',
    'NewsArticle',
    'SentimentAnalyzer', 
    'SentimentResult',
    'EventDetector',
    'StockEvent'
]
