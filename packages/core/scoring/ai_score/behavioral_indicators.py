"""
行为金融与情绪指标模块
包含：羊群行为、投资者情绪、认沽认购比率、融券比率、内部人交易等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class HerdingBehaviorIndicator(IndicatorBase):
    """羊群行为指标"""
    name = "herding_behavior"
    display_name = "羊群行为"
    category = IndicatorCategory.SENTIMENT
    description = "市场羊群效应强度"

    def calculate(self, stock_return: float = None, market_return: float = None,
                  sector_dispersion: float = None, **kwargs) -> Dict[str, Any]:
        if None in [stock_return, market_return]:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        deviation = abs(stock_return - market_return)
        if sector_dispersion and sector_dispersion > 0:
            herding_score = 1 - (deviation / sector_dispersion)
        else:
            herding_score = 0.5

        score = 50 + herding_score * 30
        desc = f"羊群效应: {'强' if herding_score > 0.7 else '中' if herding_score > 0.4 else '弱'}"
        return {'value': herding_score, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return 50 + value * 30


@auto_register
class InvestorSentimentIndexIndicator(IndicatorBase):
    """投资者情绪指数"""
    name = "investor_sentiment_index"
    display_name = "投资者情绪"
    category = IndicatorCategory.SENTIMENT
    description = "综合投资者情绪指标"

    def calculate(self, new_accounts: int = None, turnover_rate: float = None,
                  advance_decline_ratio: float = None, **kwargs) -> Dict[str, Any]:
        if None in [turnover_rate, advance_decline_ratio]:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        sentiment = (turnover_rate * 0.4 + advance_decline_ratio * 0.6)
        score = min(100, max(0, sentiment * 100))
        desc = f"市场情绪: {'乐观' if sentiment > 0.6 else '中性' if sentiment > 0.4 else '悲观'}"
        return {'value': sentiment, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, value * 100))


@auto_register
class PutCallRatioIndicator(IndicatorBase):
    """认沽认购比率"""
    name = "put_call_ratio"
    display_name = "PCR比率"
    category = IndicatorCategory.SENTIMENT
    description = "期权市场情绪指标"

    def calculate(self, put_volume: float = None, call_volume: float = None, **kwargs) -> Dict[str, Any]:
        if put_volume is None or call_volume is None or call_volume == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        pcr = put_volume / call_volume

        if pcr > 1.2:
            score = 70
            desc = f"看跌情绪浓厚 (PCR={pcr:.2f})，可能反转"
        elif pcr > 0.8:
            score = 50
            desc = f"情绪中性 (PCR={pcr:.2f})"
        else:
            score = 30
            desc = f"看涨情绪浓厚 (PCR={pcr:.2f})，警惕回调"

        return {'value': pcr, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 1.2:
            return 70.0
        elif value > 0.8:
            return 50.0
        else:
            return 30.0


@auto_register
class ShortInterestRatioIndicator(IndicatorBase):
    """融券比率指标"""
    name = "short_interest_ratio"
    display_name = "融券比率"
    category = IndicatorCategory.SENTIMENT
    description = "做空力量强度"

    def calculate(self, short_interest: float = None, avg_daily_volume: float = None, **kwargs) -> Dict[str, Any]:
        if short_interest is None or avg_daily_volume is None or avg_daily_volume == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        days_to_cover = short_interest / avg_daily_volume

        if days_to_cover > 10:
            score = 70
            desc = f"做空压力大 ({days_to_cover:.1f}天)，可能轧空"
        elif days_to_cover > 5:
            score = 50
            desc = f"做空压力中等 ({days_to_cover:.1f}天)"
        else:
            score = 40
            desc = f"做空压力小 ({days_to_cover:.1f}天)"

        return {'value': days_to_cover, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 10:
            return 70.0
        elif value > 5:
            return 50.0
        else:
            return 40.0


@auto_register
class InsiderTradingIndicator(IndicatorBase):
    """内部人交易指标"""
    name = "insider_trading"
    display_name = "内部人交易"
    category = IndicatorCategory.SENTIMENT
    description = "高管增减持情况"

    def calculate(self, insider_buy: float = None, insider_sell: float = None, **kwargs) -> Dict[str, Any]:
        if insider_buy is None or insider_sell is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        net_insider = insider_buy - insider_sell
        total = insider_buy + insider_sell

        if total == 0:
            return {'value': 0, 'score': 50, 'description': '无内部人交易'}

        insider_ratio = net_insider / total

        if insider_ratio > 0.5:
            score = 85
            desc = f"内部人大量增持 ({insider_ratio:.1%})"
        elif insider_ratio > 0.2:
            score = 70
            desc = f"内部人增持 ({insider_ratio:.1%})"
        elif insider_ratio > -0.2:
            score = 50
            desc = f"内部人交易平衡 ({insider_ratio:.1%})"
        else:
            score = 30
            desc = f"内部人减持 ({insider_ratio:.1%})"

        return {'value': insider_ratio, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.5:
            return 85.0
        elif value > 0.2:
            return 70.0
        elif value > -0.2:
            return 50.0
        else:
            return 30.0


# 指标列表
BEHAVIORAL_INDICATORS = [
    'herding_behavior',
    'investor_sentiment_index',
    'put_call_ratio',
    'short_interest_ratio',
    'insider_trading',
]


def get_all_behavioral_indicators():
    """获取所有行为金融指标名称列表"""
    return BEHAVIORAL_INDICATORS.copy()
