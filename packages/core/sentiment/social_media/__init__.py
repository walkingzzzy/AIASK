"""
社交媒体情绪数据采集模块

本模块提供多平台社交媒体情绪数据采集和分析功能：
- 东方财富股吧爬虫：采集散户讨论数据
- 雪球爬虫：采集投资者讨论数据
- 微博爬虫：采集财经话题数据
- 百度指数爬虫：采集搜索热度数据
- 情绪聚合器：整合多平台数据，计算综合情绪指数

使用示例：
    # 使用聚合器获取综合情绪
    from a_stock_analysis.sentiment.social_media import SentimentAggregator
    aggregator = SentimentAggregator()
    result = aggregator.get_stock_sentiment("600519", "贵州茅台")
    print(f"情绪分数: {result.overall_score}")
    print(f"情绪等级: {result.sentiment_level.value}")
    
    # 使用单个爬虫
    from a_stock_analysis.sentiment.social_media import GubaCrawler
    
    guba = GubaCrawler()
    posts = guba.get_stock_posts("600519")
    sentiment = guba.get_post_sentiment(posts)
    print(f"股吧情绪: {sentiment}")
    # 快速获取情绪
    from a_stock_analysis.sentiment.social_media import get_stock_sentiment_quick
    result = get_stock_sentiment_quick("600519", "贵州茅台")
    print(result)
"""

from typing import Dict, Any, List

# 导入爬虫类
from .guba_crawler import GubaCrawler, GubaPost
from .xueqiu_crawler import XueqiuCrawler, XueqiuPost
from .weibo_crawler import WeiboCrawler, WeiboPost
from .baidu_index import BaiduIndexCrawler, BaiduIndexData

# 导入聚合器
from .sentiment_aggregator import (
    SentimentAggregator,
    SentimentResult,
    SentimentLevel,
    get_stock_sentiment_quick,
    compare_stocks,
)


class SocialMediaAggregator:
    """社交媒体数据聚合器（兼容旧接口）
    
    保持与旧代码的兼容性，推荐使用新的 SentimentAggregator 类。
    """

    def __init__(self):
        """初始化聚合器"""
        self.guba = GubaCrawler()
        self.xueqiu = XueqiuCrawler()
        self.weibo = WeiboCrawler()
        self.baidu = BaiduIndexCrawler()
        self._aggregator = SentimentAggregator()

    def get_stock_sentiment(self, stock_code: str, stock_name: str = None) -> Dict[str, Any]:
        """
        获取股票社交媒体情绪
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称（可选）
            
        Returns:
            综合情绪数据
        """
        if not stock_name:
            stock_name = stock_code
            
        # 获取股吧数据
        guba_posts = self.guba.get_stock_posts(stock_code, page=1)
        guba_sentiment = self.guba.get_post_sentiment(guba_posts)

        # 获取雪球数据
        xueqiu_posts = self.xueqiu.get_stock_discussions(stock_code)
        xueqiu_sentiment = self.xueqiu.analyze_posts_sentiment(xueqiu_posts)
        xueqiu_mentions = len(xueqiu_posts)
        
        # 获取微博数据
        weibo_posts = self.weibo.search_stock_posts(stock_name)
        weibo_sentiment = self.weibo.analyze_posts_sentiment(weibo_posts)
        
        # 获取百度指数
        baidu_data = self.baidu.get_stock_heat_index(stock_name)

        # 综合情绪评分
        overall_sentiment = self._calculate_overall_sentiment(
            guba_sentiment,
            xueqiu_sentiment,
            weibo_sentiment,
            baidu_data
        )

        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "guba": guba_sentiment,
            "xueqiu": {
                "mentions": xueqiu_mentions,
                "sentiment": xueqiu_sentiment
            },
            "weibo": weibo_sentiment,
            "baidu": baidu_data,
            "overall_sentiment": overall_sentiment
        }

    def _calculate_overall_sentiment(
        self,
        guba_sentiment: Dict[str, Any],
        xueqiu_sentiment: Dict[str, Any],
        weibo_sentiment: Dict[str, Any],
        baidu_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """计算综合情绪"""
        # 获取各平台情绪分数
        guba_score = guba_sentiment.get("sentiment_score", 0.0)
        xueqiu_score = xueqiu_sentiment.get("sentiment_score", 0.0)
        weibo_score = weibo_sentiment.get("sentiment_score", 0.0)
        
        # 百度指数转换为情绪分数
        trend_direction = baidu_data.get("trend_direction", "数据不足")
        trend_to_score = {
            "大幅上升": 0.5,
            "小幅上升": 0.2,
            "基本持平": 0.0,
            "小幅下降": -0.2,
            "大幅下降": -0.5,
            "数据不足": 0.0
        }
        baidu_score = trend_to_score.get(trend_direction, 0.0)
        
        # 加权计算
        weights = {
            "guba": 0.35,
            "xueqiu": 0.30,
            "weibo": 0.20,
            "baidu": 0.15
        }
        
        overall_score = (
            guba_score * weights["guba"] +
            xueqiu_score * weights["xueqiu"] +
            weibo_score * weights["weibo"] +
            baidu_score * weights["baidu"]
        )

        # 确定信号
        if overall_score > 0.3:
            signal = "bullish"
        elif overall_score < -0.3:
            signal = "bearish"
        else:
            signal = "neutral"

        return {
            "score": round(overall_score, 4),
            "signal": signal,
            "confidence": min(abs(overall_score) + 0.3, 1.0),
            "components": {
                "guba": guba_score,
                "xueqiu": xueqiu_score,
                "weibo": weibo_score,
                "baidu": baidu_score
            }
        }


# 模块级别的便捷函数
def get_sentiment(stock_code: str, stock_name: str = None) -> Dict[str, Any]:
    """
    获取股票情绪的便捷函数
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        
    Returns:
        情绪分析结果
    """
    return get_stock_sentiment_quick(stock_code, stock_name)


def get_market_mood() -> Dict[str, Any]:
    """
    获取市场整体情绪的便捷函数
    
    Returns:
        市场情绪数据
    """
    aggregator = SentimentAggregator()
    return aggregator.get_market_sentiment()


# 导出所有公开接口
__all__ = [
    # 爬虫类
    "GubaCrawler",
    "GubaPost",
    "XueqiuCrawler", 
    "XueqiuPost",
    "WeiboCrawler",
    "WeiboPost",
    "BaiduIndexCrawler",
    "BaiduIndexData",
    
    # 聚合器
    "SentimentAggregator",
    "SentimentResult",
    "SentimentLevel",
    "SocialMediaAggregator",  # 兼容旧接口
    
    # 便捷函数
    "get_stock_sentiment_quick",
    "compare_stocks",
    "get_sentiment",
    "get_market_mood",
]