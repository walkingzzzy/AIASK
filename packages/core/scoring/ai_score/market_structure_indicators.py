"""
市场微观结构指标模块
包含：买卖价差、委托不平衡、市场深度、市场广度、板块轮动等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class BidAskSpreadIndicator(IndicatorBase):
    """买卖价差指标"""
    name = "bid_ask_spread"
    display_name = "买卖价差"
    category = IndicatorCategory.TECHNICAL
    description = "流动性指标，价差越小流动性越好"

    def calculate(self, bid: float = None, ask: float = None, **kwargs) -> Dict[str, Any]:
        if bid is None or ask is None or bid == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        spread = (ask - bid) / bid
        if spread < 0.001:
            score = 90
            desc = f"流动性极佳 (价差: {spread:.4%})"
        elif spread < 0.005:
            score = 70
            desc = f"流动性良好 (价差: {spread:.4%})"
        else:
            score = 40
            desc = f"流动性一般 (价差: {spread:.4%})"

        return {'value': spread, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 0.001:
            return 90.0
        elif value < 0.005:
            return 70.0
        else:
            return 40.0


@auto_register
class OrderImbalanceIndicator(IndicatorBase):
    """委托单不平衡指标"""
    name = "order_imbalance"
    display_name = "委托不平衡"
    category = IndicatorCategory.TECHNICAL
    description = "买卖盘力量对比"

    def calculate(self, bid_volume: float = None, ask_volume: float = None, **kwargs) -> Dict[str, Any]:
        if bid_volume is None or ask_volume is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        total = bid_volume + ask_volume
        if total == 0:
            return {'value': 0, 'score': 50, 'description': '无委托'}

        imbalance = (bid_volume - ask_volume) / total

        if imbalance > 0.3:
            score = 85
            desc = f"买盘占优 (不平衡度: {imbalance:.2%})"
        elif imbalance > 0.1:
            score = 65
            desc = f"买盘略强 (不平衡度: {imbalance:.2%})"
        elif imbalance > -0.1:
            score = 50
            desc = f"买卖平衡 (不平衡度: {imbalance:.2%})"
        elif imbalance > -0.3:
            score = 35
            desc = f"卖盘略强 (不平衡度: {imbalance:.2%})"
        else:
            score = 15
            desc = f"卖盘占优 (不平衡度: {imbalance:.2%})"

        return {'value': imbalance, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.3:
            return 85.0
        elif value > 0.1:
            return 65.0
        elif value > -0.1:
            return 50.0
        elif value > -0.3:
            return 35.0
        else:
            return 15.0


@auto_register
class MarketDepthIndicator(IndicatorBase):
    """市场深度指标"""
    name = "market_depth"
    display_name = "市场深度"
    category = IndicatorCategory.TECHNICAL
    description = "五档买卖盘深度"

    def calculate(self, bid_volumes: List[float] = None, ask_volumes: List[float] = None, **kwargs) -> Dict[str, Any]:
        if not bid_volumes or not ask_volumes:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        total_bid = sum(bid_volumes[:5])
        total_ask = sum(ask_volumes[:5])
        depth_ratio = total_bid / (total_ask + 1)

        if depth_ratio > 1.5:
            score = 85
            desc = f"买盘深度强 (比率: {depth_ratio:.2f})"
        elif depth_ratio > 1.1:
            score = 65
            desc = f"买盘深度略强 (比率: {depth_ratio:.2f})"
        elif depth_ratio > 0.9:
            score = 50
            desc = f"深度平衡 (比率: {depth_ratio:.2f})"
        else:
            score = 35
            desc = f"卖盘深度强 (比率: {depth_ratio:.2f})"

        return {'value': depth_ratio, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 1.5:
            return 85.0
        elif value > 1.1:
            return 65.0
        elif value > 0.9:
            return 50.0
        else:
            return 35.0


@auto_register
class MarketBreadthIndicator(IndicatorBase):
    """市场广度指标"""
    name = "market_breadth"
    display_name = "市场广度"
    category = IndicatorCategory.TECHNICAL
    description = "上涨股票数量占比"

    def calculate(self, advancing_stocks: int = None, declining_stocks: int = None, **kwargs) -> Dict[str, Any]:
        if advancing_stocks is None or declining_stocks is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        total = advancing_stocks + declining_stocks
        if total == 0:
            return {'value': 0.5, 'score': 50, 'description': '无交易'}

        breadth = advancing_stocks / total
        score = breadth * 100
        desc = f"市场广度: {breadth:.1%} ({'强势' if breadth > 0.6 else '弱势' if breadth < 0.4 else '中性'})"
        return {'value': breadth, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return value * 100


@auto_register
class SectorRotationIndicator(IndicatorBase):
    """板块轮动指标"""
    name = "sector_rotation"
    display_name = "板块轮动"
    category = IndicatorCategory.TECHNICAL
    description = "板块资金轮动情况"

    def calculate(self, sector_performance: Dict[str, float] = None, **kwargs) -> Dict[str, Any]:
        if not sector_performance:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        performances = list(sector_performance.values())
        if not performances:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        rotation_intensity = np.std(performances)
        score = min(100, rotation_intensity * 200)
        desc = f"轮动强度: {'高' if rotation_intensity > 0.05 else '中' if rotation_intensity > 0.02 else '低'}"
        return {'value': rotation_intensity, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, value * 200)


# 指标列表
MARKET_STRUCTURE_INDICATORS = [
    'bid_ask_spread',
    'order_imbalance',
    'market_depth',
    'market_breadth',
    'sector_rotation',
]


def get_all_market_structure_indicators():
    """获取所有市场结构指标名称列表"""
    return MARKET_STRUCTURE_INDICATORS.copy()
