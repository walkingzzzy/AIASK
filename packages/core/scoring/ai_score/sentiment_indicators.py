"""
高级情绪指标计算模块
扩展AI评分系统的情绪指标维度
"""
from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class SentimentIndicatorResult:
    """情绪指标结果"""
    value: float
    sentiment: str  # 'bullish', 'bearish', 'neutral'
    confidence: float  # 0-1
    description: str


class AdvancedSentimentIndicators:
    """高级情绪指标计算器"""

    @staticmethod
    def calculate_forum_sentiment(posts: List[Dict[str, Any]]) -> SentimentIndicatorResult:
        """
        论坛情绪分析（东方财富股吧等）

        Args:
            posts: 帖子列表

        Returns:
            指标结果
        """
        if not posts:
            return SentimentIndicatorResult(
                value=0.0,
                sentiment='neutral',
                confidence=0.0,
                description="无论坛数据"
            )

        # 统计正负面情绪
        bullish_count = sum(1 for p in posts if p.get('sentiment', 0) > 0.3)
        bearish_count = sum(1 for p in posts if p.get('sentiment', 0) < -0.3)
        total_count = len(posts)

        sentiment_score = (bullish_count - bearish_count) / total_count

        if sentiment_score > 0.3:
            sentiment = 'bullish'
            confidence = min(sentiment_score, 1.0)
            desc = f"论坛情绪偏多 ({bullish_count}/{total_count}看多)"
        elif sentiment_score < -0.3:
            sentiment = 'bearish'
            confidence = min(abs(sentiment_score), 1.0)
            desc = f"论坛情绪偏空 ({bearish_count}/{total_count}看空)"
        else:
            sentiment = 'neutral'
            confidence = 0.3
            desc = "论坛情绪中性"

        return SentimentIndicatorResult(
            value=sentiment_score,
            sentiment=sentiment,
            confidence=confidence,
            description=desc
        )

    @staticmethod
    def calculate_social_media_buzz(mentions: int, avg_mentions: float) -> SentimentIndicatorResult:
        """
        社交媒体热度（微博、雪球等）

        Args:
            mentions: 当前提及次数
            avg_mentions: 平均提及次数

        Returns:
            指标结果
        """
        buzz_ratio = mentions / avg_mentions if avg_mentions > 0 else 1.0

        if buzz_ratio > 3:
            sentiment = 'bullish'
            confidence = min((buzz_ratio - 1) / 5, 1.0)
            desc = f"社交媒体热度爆发 ({buzz_ratio:.1f}x)"
        elif buzz_ratio > 1.5:
            sentiment = 'bullish'
            confidence = (buzz_ratio - 1) / 2
            desc = f"社交媒体热度上升 ({buzz_ratio:.1f}x)"
        elif buzz_ratio < 0.5:
            sentiment = 'bearish'
            confidence = (1 - buzz_ratio) / 2
            desc = f"社交媒体热度下降 ({buzz_ratio:.1f}x)"
        else:
            sentiment = 'neutral'
            confidence = 0.3
            desc = "社交媒体热度正常"

        return SentimentIndicatorResult(
            value=buzz_ratio,
            sentiment=sentiment,
            confidence=confidence,
            description=desc
        )

    @staticmethod
    def calculate_search_trend(search_index: float, baseline: float) -> SentimentIndicatorResult:
        """
        搜索趋势（百度指数等）

        Args:
            search_index: 当前搜索指数
            baseline: 基准搜索指数

        Returns:
            指标结果
        """
        trend_ratio = search_index / baseline if baseline > 0 else 1.0

        if trend_ratio > 2:
            sentiment = 'bullish'
            confidence = min((trend_ratio - 1) / 3, 1.0)
            desc = f"搜索热度激增 ({trend_ratio:.1f}x)"
        elif trend_ratio > 1.3:
            sentiment = 'bullish'
            confidence = (trend_ratio - 1) / 2
            desc = f"搜索热度上升 ({trend_ratio:.1f}x)"
        elif trend_ratio < 0.7:
            sentiment = 'bearish'
            confidence = (1 - trend_ratio) / 2
            desc = f"搜索热度下降 ({trend_ratio:.1f}x)"
        else:
            sentiment = 'neutral'
            confidence = 0.3
            desc = "搜索热度稳定"

        return SentimentIndicatorResult(
            value=trend_ratio,
            sentiment=sentiment,
            confidence=confidence,
            description=desc
        )