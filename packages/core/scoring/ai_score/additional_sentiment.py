"""
补充情绪面指标模块
包含：分析师一致预期变化、新闻情绪趋势、概念板块热度排名等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class AnalystConsensusChangeIndicator(IndicatorBase):
    """分析师一致预期变化"""
    name = "analyst_consensus_change"
    display_name = "分析师一致预期变化"
    category = IndicatorCategory.SENTIMENT
    description = "分析师评级变化趋势"

    def calculate(self, rating_current: float = None, rating_previous: float = None,
                  **kwargs) -> Dict[str, Any]:
        if rating_current is None or rating_previous is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        change = rating_current - rating_previous

        if change > 0.5:
            score = 80
            desc = f"分析师评级大幅上调 (+{change:.1f})"
        elif change > 0.2:
            score = 65
            desc = f"分析师评级上调 (+{change:.1f})"
        elif change < -0.5:
            score = 25
            desc = f"分析师评级大幅下调 ({change:.1f})"
        elif change < -0.2:
            score = 40
            desc = f"分析师评级下调 ({change:.1f})"
        else:
            score = 50
            desc = f"分析师评级稳定 ({change:+.1f})"

        return {
            'value': change,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.5:
            return 80.0
        elif value > 0.2:
            return 65.0
        elif value < -0.5:
            return 25.0
        elif value < -0.2:
            return 40.0
        else:
            return 50.0


@auto_register
class NewsSentimentTrendIndicator(IndicatorBase):
    """新闻情绪变化趋势"""
    name = "news_sentiment_trend"
    display_name = "新闻情绪趋势"
    category = IndicatorCategory.SENTIMENT
    description = "新闻情绪变化趋势"

    def calculate(self, sentiment_recent: float = None, sentiment_previous: float = None,
                  **kwargs) -> Dict[str, Any]:
        if sentiment_recent is None or sentiment_previous is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        trend = sentiment_recent - sentiment_previous

        if trend > 0.3:
            score = 75
            desc = f"新闻情绪显著改善 (+{trend:.2f})"
        elif trend > 0.1:
            score = 60
            desc = f"新闻情绪改善 (+{trend:.2f})"
        elif trend < -0.3:
            score = 30
            desc = f"新闻情绪显著恶化 ({trend:.2f})"
        elif trend < -0.1:
            score = 45
            desc = f"新闻情绪恶化 ({trend:.2f})"
        else:
            score = 50
            desc = f"新闻情绪稳定 ({trend:+.2f})"

        return {
            'value': trend,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.3:
            return 75.0
        elif value > 0.1:
            return 60.0
        elif value < -0.3:
            return 30.0
        elif value < -0.1:
            return 45.0
        else:
            return 50.0


@auto_register
class ConceptHotRankIndicator(IndicatorBase):
    """概念板块热度排名"""
    name = "concept_hot_rank"
    display_name = "概念热度排名"
    category = IndicatorCategory.SENTIMENT
    description = "所属概念板块热度排名"

    def calculate(self, concept_rank: int = None, total_concepts: int = 100, **kwargs) -> Dict[str, Any]:
        if concept_rank is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        percentile = 1 - (concept_rank / total_concepts)

        if percentile > 0.9:
            score = 85
            desc = f"概念板块极热 (排名: {concept_rank}/{total_concepts})"
        elif percentile > 0.7:
            score = 70
            desc = f"概念板块较热 (排名: {concept_rank}/{total_concepts})"
        elif percentile > 0.5:
            score = 55
            desc = f"概念板块一般 (排名: {concept_rank}/{total_concepts})"
        else:
            score = 40
            desc = f"概念板块冷门 (排名: {concept_rank}/{total_concepts})"

        return {
            'value': concept_rank,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 排名越小越好
        if value <= 10:
            return 85.0
        elif value <= 30:
            return 70.0
        elif value <= 50:
            return 55.0
        else:
            return 40.0


# 指标列表
ADDITIONAL_SENTIMENT_INDICATORS = [
    'analyst_consensus_change',
    'news_sentiment_trend',
    'concept_hot_rank',
]


def get_all_additional_sentiment_indicators():
    """获取所有补充情绪面指标名称列表"""
    return ADDITIONAL_SENTIMENT_INDICATORS.copy()
