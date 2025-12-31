"""
情绪数据聚合器

实现功能：
1. 整合所有数据源的情绪数据（股吧、雪球、微博、百度指数）
2. 计算综合情绪指数
3. 提供统一的API接口
4. 情绪趋势分析
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

from .guba_crawler import GubaCrawler
from .xueqiu_crawler import XueqiuCrawler
from .weibo_crawler import WeiboCrawler
from .baidu_index import BaiduIndexCrawler

# 配置日志
logger = logging.getLogger(__name__)


class SentimentLevel(Enum):
    """情绪等级"""
    VERY_BULLISH = "极度乐观"
    BULLISH = "乐观"
    SLIGHTLY_BULLISH = "偏乐观"
    NEUTRAL = "中性"
    SLIGHTLY_BEARISH = "偏悲观"
    BEARISH = "悲观"
    VERY_BEARISH = "极度悲观"


@dataclass
class SentimentResult:
    """情绪分析结果"""
    stock_code: str
    stock_name: str
    overall_score: float  # 综合情绪分数 [-1, 1]
    sentiment_level: SentimentLevel
    confidence: float  # 置信度 [0, 1]
    sources: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class SentimentAggregator:
    """情绪数据聚合器
    
    整合多个社交媒体平台的情绪数据，计算综合情绪指数。Attributes:
        guba:股吧爬虫
        xueqiu: 雪球爬虫
        weibo: 微博爬虫
        baidu: 百度指数爬虫
        weights: 各数据源权重
        
    Example:
        >>> aggregator = SentimentAggregator()
        >>> result = aggregator.get_stock_sentiment("600519", "贵州茅台")
        >>> print(result.sentiment_level)
        >>> print(result.overall_score)
    """

    # 默认数据源权重
    DEFAULT_WEIGHTS = {
        "guba": 0.35,      # 股吧权重最高，直接反映散户情绪
        "xueqiu": 0.30,    # 雪球用户质量较高
        "weibo": 0.20,     # 微博覆盖面广但噪音多
        "baidu": 0.15,     # 百度指数反映关注度
    }

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        enable_parallel: bool = True,
        timeout: int = 30
    ):
        """
        初始化情绪聚合器
        
        Args:
            weights: 各数据源权重配置，默认使用DEFAULT_WEIGHTS
            enable_parallel: 是否启用并行获取
            timeout: 单个数据源超时时间（秒）
        """
        # 初始化各爬虫
        self.guba = GubaCrawler()
        self.xueqiu = XueqiuCrawler()
        self.weibo = WeiboCrawler()
        self.baidu = BaiduIndexCrawler()
        
        # 设置权重
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._normalize_weights()
        
        self.enable_parallel = enable_parallel
        self.timeout = timeout
        logger.info(f"情绪聚合器初始化完成，权重配置: {self.weights}")

    def _normalize_weights(self) -> None:
        """归一化权重，确保总和为1"""
        total = sum(self.weights.values())
        if total > 0:
            for key in self.weights:
                self.weights[key] /= total

    def set_weights(self, weights: Dict[str, float]) -> None:
        """
        设置数据源权重
        
        Args:
            weights: 权重配置字典
        """
        self.weights.update(weights)
        self._normalize_weights()
        logger.info(f"权重已更新: {self.weights}")

    def set_baidu_cookie(self, cookie: str) -> None:
        """
        设置百度指数Cookie
        
        Args:
            cookie: 百度登录Cookie
        """
        self.baidu.set_cookie(cookie)

    def get_stock_sentiment(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        include_sources: Optional[List[str]] = None
    ) -> SentimentResult:
        """
        获取股票综合情绪
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称（用于微博和百度搜索）
            include_sources: 要包含的数据源列表，默认全部
            
        Returns:
            SentimentResult: 综合情绪分析结果
        """
        if not stock_name:
            stock_name = stock_code
        sources = include_sources or ["guba", "xueqiu", "weibo", "baidu"]
        
        # 获取各平台数据
        if self.enable_parallel:
            source_data = self._get_data_parallel(stock_code, stock_name, sources)
        else:
            source_data = self._get_data_sequential(stock_code, stock_name, sources)
            
        # 计算综合情绪
        overall_score, confidence = self._calculate_overall_sentiment(source_data)
        
        # 确定情绪等级
        sentiment_level = self._get_sentiment_level(overall_score)
        
        return SentimentResult(
            stock_code=stock_code,
            stock_name=stock_name,
            overall_score=round(overall_score, 4),
            sentiment_level=sentiment_level,
            confidence=round(confidence, 4),
            sources=source_data
        )

    def _get_data_parallel(
        self,
        stock_code: str,
        stock_name: str,
        sources: List[str]
    ) -> Dict[str, Any]:
        """并行获取各平台数据"""
        source_data = {}
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            
            if "guba" in sources:
                futures[executor.submit(self._get_guba_sentiment, stock_code)] = "guba"
            if "xueqiu" in sources:
                futures[executor.submit(self._get_xueqiu_sentiment, stock_code)] = "xueqiu"
            if "weibo" in sources:
                futures[executor.submit(self._get_weibo_sentiment, stock_name)] = "weibo"
            if "baidu" in sources:
                futures[executor.submit(self._get_baidu_sentiment, stock_name)] = "baidu"
                
            for future in as_completed(futures, timeout=self.timeout):
                source_name = futures[future]
                try:
                    source_data[source_name] = future.result()
                except Exception as e:
                    logger.error(f"获取{source_name}数据失败: {e}")
                    source_data[source_name] = {"error": str(e), "score": 0}    
        return source_data

    def _get_data_sequential(
        self,
        stock_code: str,
        stock_name: str,
        sources: List[str]
    ) -> Dict[str, Any]:
        """顺序获取各平台数据"""
        source_data = {}
        
        if "guba" in sources:
            try:
                source_data["guba"] = self._get_guba_sentiment(stock_code)
            except Exception as e:
                logger.error(f"获取股吧数据失败: {e}")
                source_data["guba"] = {"error": str(e), "score": 0}
                
        if "xueqiu" in sources:
            try:
                source_data["xueqiu"] = self._get_xueqiu_sentiment(stock_code)
            except Exception as e:
                logger.error(f"获取雪球数据失败: {e}")
                source_data["xueqiu"] = {"error": str(e), "score": 0}
                
        if "weibo" in sources:
            try:
                source_data["weibo"] = self._get_weibo_sentiment(stock_name)
            except Exception as e:
                logger.error(f"获取微博数据失败: {e}")
                source_data["weibo"] = {"error": str(e), "score": 0}
                
        if "baidu" in sources:
            try:
                source_data["baidu"] = self._get_baidu_sentiment(stock_name)
            except Exception as e:
                logger.error(f"获取百度指数失败: {e}")
                source_data["baidu"] = {"error": str(e), "score": 0}
                
        return source_data

    def _get_guba_sentiment(self, stock_code: str) -> Dict[str, Any]:
        """获取股吧情绪数据"""
        posts = self.guba.get_stock_posts(stock_code, page=1, page_size=30)
        sentiment = self.guba.get_post_sentiment(posts)
        return {
            "source": "guba",
            "score": sentiment.get("sentiment_score", 0),
            "total_posts": sentiment.get("total_posts", 0),
            "bullish_count": sentiment.get("bullish_count", 0),
            "bearish_count": sentiment.get("bearish_count", 0),
            "neutral_count": sentiment.get("neutral_count", 0),
            "avg_read_count": sentiment.get("avg_read_count", 0),
            "sample_posts": [
                {"title": p.get("title", ""), "sentiment": p.get("sentiment", 0)}
                for p in posts[:3]
            ] if posts else []
        }

    def _get_xueqiu_sentiment(self, stock_code: str) -> Dict[str, Any]:
        """获取雪球情绪数据"""
        posts = self.xueqiu.get_stock_discussions(stock_code, count=30)
        sentiment = self.xueqiu.analyze_posts_sentiment(posts)
        
        return {
            "source": "xueqiu",
            "score": sentiment.get("sentiment_score", 0),
            "total_posts": sentiment.get("total_posts", 0),
            "bullish_count": sentiment.get("bullish_count", 0),
            "bearish_count": sentiment.get("bearish_count", 0),
            "neutral_count": sentiment.get("neutral_count", 0),
            "engagement_score": sentiment.get("engagement_score", 0),
            "sample_posts": [
                {"text": p.get("text", "")[:100], "sentiment": p.get("sentiment", 0)}
                for p in posts[:3]
            ] if posts else []
        }

    def _get_weibo_sentiment(self, stock_name: str) -> Dict[str, Any]:
        """获取微博情绪数据"""
        posts = self.weibo.search_stock_posts(stock_name, page=1, count=20)
        sentiment = self.weibo.analyze_posts_sentiment(posts)
        
        return {
            "source": "weibo",
            "score": sentiment.get("sentiment_score", 0),
            "total_posts": sentiment.get("total_posts", 0),
            "bullish_count": sentiment.get("bullish_count", 0),
            "bearish_count": sentiment.get("bearish_count", 0),
            "neutral_count": sentiment.get("neutral_count", 0),
            "engagement_score": sentiment.get("engagement_score", 0),
            "sample_posts": [
                {"text": p.get("text", "")[:100], "sentiment": p.get("sentiment", 0)}
                for p in posts[:3]
            ] if posts else []
        }

    def _get_baidu_sentiment(self, stock_name: str) -> Dict[str, Any]:
        """获取百度指数数据并转换为情绪分数"""
        heat_data = self.baidu.get_stock_heat_index(stock_name)
        
        # 根据热度趋势计算情绪分数
        trend_direction = heat_data.get("trend_direction", "数据不足")
        #趋势方向映射到情绪分数
        trend_to_score = {
            "大幅上升": 0.5,
            "小幅上升": 0.2,
            "基本持平": 0.0,
            "小幅下降": -0.2,
            "大幅下降": -0.5,
            "数据不足": 0.0
        }
        
        score = trend_to_score.get(trend_direction, 0.0)
        
        return {
            "source": "baidu",
            "score": score,
            "avg_index": heat_data.get("avg_index", 0),
            "max_index": heat_data.get("max_index", 0),
            "heat_level": heat_data.get("heat_level", "未知"),
            "trend_direction": trend_direction,
            "is_mock": heat_data.get("is_mock", False)
        }

    def _calculate_overall_sentiment(
        self,
        source_data: Dict[str, Any]
    ) -> tuple:
        """
        计算综合情绪分数
        
        Args:
            source_data: 各数据源的情绪数据
            
        Returns:
            (综合分数, 置信度)
        """
        weighted_sum = 0.0
        total_weight = 0.0
        valid_sources = 0
        
        for source, data in source_data.items():
            if "error" in data:
                continue
                
            score = data.get("score", 0)
            weight = self.weights.get(source, 0)
            
            # 根据数据量调整权重
            posts_count = data.get("total_posts", 0)
            if posts_count > 0:
                # 数据量越多，权重越高（但有上限）
                quantity_factor = min(1.0 + posts_count / 50, 1.5)
                adjusted_weight = weight * quantity_factorelse:
                adjusted_weight = weight * 0.5
            weighted_sum += score * adjusted_weight
            total_weight += adjusted_weight
            valid_sources += 1
            
        # 计算综合分数
        if total_weight > 0:
            overall_score = weighted_sum / total_weight
        else:
            overall_score = 0.0
            
        # 计算置信度
        # 基于有效数据源数量和数据量
        base_confidence = valid_sources / len(self.weights) if self.weights else 0
        
        # 考虑数据一致性
        scores = [
            data.get("score", 0) 
            for data in source_data.values() 
            if "error" not in data
        ]
        
        if len(scores) >= 2:
            # 计算分数的标准差，标准差越小，一致性越高
            avg = sum(scores) / len(scores)
            variance = sum((s - avg) ** 2 for s in scores) / len(scores)
            std_dev = variance ** 0.5
            consistency_factor = max(0, 1 - std_dev)
        else:
            consistency_factor = 0.5
            
        confidence = base_confidence * 0.6 + consistency_factor * 0.4
        confidence = max(0, min(1, confidence))
        
        return overall_score, confidence

    def _get_sentiment_level(self, score: float) -> SentimentLevel:
        """根据分数确定情绪等级"""
        if score >= 0.6:
            return SentimentLevel.VERY_BULLISH
        elif score >= 0.3:
            return SentimentLevel.BULLISH
        elif score >= 0.1:
            return SentimentLevel.SLIGHTLY_BULLISH
        elif score >= -0.1:
            return SentimentLevel.NEUTRAL
        elif score >= -0.3:
            return SentimentLevel.SLIGHTLY_BEARISH
        elif score >= -0.6:
            return SentimentLevel.BEARISH
        else:
            return SentimentLevel.VERY_BEARISH

    def get_market_sentiment(self) -> Dict[str, Any]:
        """
        获取整体市场情绪
        
        Returns:
            市场情绪数据
        """
        # 获取热门话题和热门股票
        hot_topics = []
        # 从微博获取财经热搜
        try:
            weibo_hot = self.weibo.get_finance_hot_search()
            for item in weibo_hot[:5]:
                hot_topics.append({
                    "source": "weibo",
                    "keyword": item.get("keyword", ""),
                    "hot": item.get("hot", 0)
                })
        except Exception as e:
            logger.error(f"获取微博热搜失败: {e}")
            
        # 从雪球获取热门股票
        try:
            xueqiu_hot = self.xueqiu.get_hot_stocks(count=10)
            hot_stocks = [
                {
                    "symbol": s.get("symbol", ""),
                    "name": s.get("name", ""),
                    "tweet": s.get("tweet", 0)
                }
                for s in xueqiu_hot
            ]except Exception as e:
            logger.error(f"获取雪球热门股票失败: {e}")
            hot_stocks = []
            
        return {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "hot_topics": hot_topics,
            "hot_stocks": hot_stocks
        }

    def compare_stocks_sentiment(
        self,
        stock_list: List[Dict[str, str]]
    ) -> List[SentimentResult]:
        """
        比较多只股票的情绪
        
        Args:
            stock_list: 股票列表，每项包含code和name
            
        Returns:
            情绪结果列表
        """
        results = []
        
        for stock in stock_list:
            code = stock.get("code", "")
            name = stock.get("name", code)
            
            try:
                result = self.get_stock_sentiment(code, name)
                results.append(result)
            except Exception as e:
                logger.error(f"获取{name}({code})情绪失败: {e}")
                
        # 按情绪分数排序
        results.sort(key=lambda x: x.overall_score, reverse=True)
        
        return results

    def get_sentiment_report(
        self,
        stock_code: str,
        stock_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成详细情绪分析报告
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            
        Returns:
            详细报告
        """
        result = self.get_stock_sentiment(stock_code, stock_name)
        
        # 生成投资建议
        if result.overall_score >= 0.3and result.confidence >= 0.5:
            suggestion = "市场情绪较为乐观，可适当关注"
        elif result.overall_score <= -0.3 and result.confidence >= 0.5:
            suggestion = "市场情绪较为悲观，建议谨慎"
        else:
            suggestion = "市场情绪中性或数据不足，建议综合其他因素判断"
            
        # 分析各平台差异
        source_analysis = []
        for source, data in result.sources.items():
            if "error" not in data:
                source_analysis.append({
                    "source": source,
                    "score": data.get("score", 0),
                    "weight": self.weights.get(source, 0),
                    "data_count": data.get("total_posts", 0) or data.get("avg_index", 0)
                })
        return {
            "stock_code": stock_code,
            "stock_name": stock_name or stock_code,
            "timestamp": result.timestamp,
            "summary": {
                "overall_score": result.overall_score,
                "sentiment_level": result.sentiment_level.value,
                "confidence": result.confidence,
                "suggestion": suggestion
            },
            "source_analysis": source_analysis,
            "detailed_data": result.sources
        }

    def to_dict(self, result: SentimentResult) -> Dict[str, Any]:
        """将SentimentResult转换为字典"""
        return {
            "stock_code": result.stock_code,
            "stock_name": result.stock_name,
            "overall_score": result.overall_score,
            "sentiment_level": result.sentiment_level.value,
            "confidence": result.confidence,
            "sources": result.sources,
            "timestamp": result.timestamp
        }


# 便捷函数
def get_stock_sentiment_quick(
    stock_code: str,
    stock_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    快速获取股票情绪（便捷函数）
    
    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        
    Returns:
        情绪分析结果字典
    """
    aggregator = SentimentAggregator()
    result = aggregator.get_stock_sentiment(stock_code, stock_name)
    return aggregator.to_dict(result)


def compare_stocks(
    stocks: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """
    比较多只股票情绪（便捷函数）
    
    Args:
        stocks: 股票列表 [{"code": "600519", "name": "贵州茅台"}, ...]
        
    Returns:
        排序后的情绪结果列表
    """
    aggregator = SentimentAggregator()
    results = aggregator.compare_stocks_sentiment(stocks)
    return [aggregator.to_dict(r) for r in results]