"""
量价关系指标模块
包含：成交量加权动量、价量相关性、累积派发、蔡金资金流等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class VolumeWeightedMomentumIndicator(IndicatorBase):
    """成交量加权动量指标"""
    name = "volume_weighted_momentum"
    display_name = "量价动量"
    category = IndicatorCategory.TECHNICAL
    description = "结合成交量的动量指标"

    def calculate(self, close: pd.Series = None, volume: pd.Series = None,
                  period: int = 20, **kwargs) -> Dict[str, Any]:
        if close is None or volume is None or len(close) < period:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        returns = close.pct_change()
        vwm = (returns * volume).rolling(period).sum() / volume.rolling(period).sum()

        score = min(100, max(0, 50 + vwm.iloc[-1] * 1000))
        desc = f"量价动量: {vwm.iloc[-1]:.4f}"

        return {'value': vwm.iloc[-1], 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, 50 + value * 1000))


@auto_register
class PriceVolumeCorrelationIndicator(IndicatorBase):
    """价量相关性指标"""
    name = "price_volume_correlation"
    display_name = "价量相关性"
    category = IndicatorCategory.TECHNICAL
    description = "价格与成交量的相关性"

    def calculate(self, close: pd.Series = None, volume: pd.Series = None,
                  period: int = 20, **kwargs) -> Dict[str, Any]:
        if close is None or volume is None or len(close) < period:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        corr = close.rolling(period).corr(volume).iloc[-1]

        if corr > 0.5:
            score = 80
            desc = f"价量同步上涨 (相关性: {corr:.2f})"
        elif corr < -0.5:
            score = 30
            desc = f"价量背离 (相关性: {corr:.2f})"
        else:
            score = 50
            desc = f"价量关系一般 (相关性: {corr:.2f})"

        return {'value': corr, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.5:
            return 80.0
        elif value < -0.5:
            return 30.0
        else:
            return 50.0


@auto_register
class AccumulationDistributionIndicator(IndicatorBase):
    """累积派发指标 (A/D Line)"""
    name = "accumulation_distribution"
    display_name = "累积派发"
    category = IndicatorCategory.TECHNICAL
    description = "资金流入流出累积指标"

    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, volume: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if None in [high, low, close, volume] or len(close) < 2:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        mfm = ((close - low) - (high - close)) / (high - low + 0.0001)
        mfv = mfm * volume
        ad_line = mfv.cumsum()

        trend = ad_line.iloc[-1] - ad_line.iloc[-20] if len(ad_line) >= 20 else 0
        score = min(100, max(0, 50 + trend / abs(ad_line.iloc[-1] + 1) * 100))

        desc = f"A/D趋势: {'上升' if trend > 0 else '下降'}"
        return {'value': ad_line.iloc[-1], 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        return 50.0


@auto_register
class ChaikinMoneyFlowIndicator(IndicatorBase):
    """蔡金资金流量指标 (CMF)"""
    name = "chaikin_money_flow"
    display_name = "蔡金资金流"
    category = IndicatorCategory.TECHNICAL
    description = "衡量资金流入流出强度"

    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, volume: pd.Series = None,
                  period: int = 20, **kwargs) -> Dict[str, Any]:
        if None in [high, low, close, volume] or len(close) < period:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        mfm = ((close - low) - (high - close)) / (high - low + 0.0001)
        mfv = mfm * volume
        cmf = mfv.rolling(period).sum() / volume.rolling(period).sum()

        current_cmf = cmf.iloc[-1]
        if current_cmf > 0.2:
            score = 85
            desc = f"强势资金流入 (CMF: {current_cmf:.3f})"
        elif current_cmf > 0:
            score = 65
            desc = f"资金流入 (CMF: {current_cmf:.3f})"
        elif current_cmf > -0.2:
            score = 35
            desc = f"资金流出 (CMF: {current_cmf:.3f})"
        else:
            score = 15
            desc = f"强势资金流出 (CMF: {current_cmf:.3f})"

        return {'value': current_cmf, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.2:
            return 85.0
        elif value > 0:
            return 65.0
        elif value > -0.2:
            return 35.0
        else:
            return 15.0


# 指标列表
VOLUME_PRICE_INDICATORS = [
    'volume_weighted_momentum',
    'price_volume_correlation',
    'accumulation_distribution',
    'chaikin_money_flow',
]


def get_all_volume_price_indicators():
    """获取所有量价关系指标名称列表"""
    return VOLUME_PRICE_INDICATORS.copy()
