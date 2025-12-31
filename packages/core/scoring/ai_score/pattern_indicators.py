"""
技术形态识别指标模块
包含：头肩形态、双顶双底、三角形态等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class HeadAndShouldersIndicator(IndicatorBase):
    """头肩形态识别"""
    name = "head_and_shoulders"
    display_name = "头肩形态"
    category = IndicatorCategory.TECHNICAL
    description = "识别头肩顶/底形态"

    def calculate(self, high: pd.Series = None, low: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if high is None or len(high) < 50:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        recent_highs = high.iloc[-50:].nlargest(3)
        if len(recent_highs) >= 3:
            left_shoulder = recent_highs.iloc[0]
            head = recent_highs.iloc[1]
            right_shoulder = recent_highs.iloc[2]

            if head > left_shoulder * 1.05 and head > right_shoulder * 1.05:
                score = 30
                desc = "疑似头肩顶形态，看跌"
            else:
                score = 50
                desc = "无明显头肩形态"
        else:
            score = 50
            desc = "数据不足以判断"

        return {'value': score, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return value


@auto_register
class DoubleTopBottomIndicator(IndicatorBase):
    """双顶双底形态"""
    name = "double_top_bottom"
    display_name = "双顶双底"
    category = IndicatorCategory.TECHNICAL
    description = "识别双顶/双底形态"

    def calculate(self, close: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < 30:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        recent_data = close.iloc[-30:]
        peaks = []
        for i in range(1, len(recent_data) - 1):
            if recent_data.iloc[i] > recent_data.iloc[i-1] and recent_data.iloc[i] > recent_data.iloc[i+1]:
                peaks.append(recent_data.iloc[i])

        if len(peaks) >= 2:
            if abs(peaks[-1] - peaks[-2]) / peaks[-1] < 0.03:
                score = 35
                desc = "疑似双顶形态，看跌"
            else:
                score = 50
                desc = "无明显双顶形态"
        else:
            score = 50
            desc = "数据不足"

        return {'value': score, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return value


@auto_register
class TrianglePatternIndicator(IndicatorBase):
    """三角形整理形态"""
    name = "triangle_pattern"
    display_name = "三角形态"
    category = IndicatorCategory.TECHNICAL
    description = "识别三角形整理形态"

    def calculate(self, high: pd.Series = None, low: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or len(high) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        recent_high = high.iloc[-20:]
        recent_low = low.iloc[-20:]

        high_slope = (recent_high.iloc[-1] - recent_high.iloc[0]) / 20
        low_slope = (recent_low.iloc[-1] - recent_low.iloc[0]) / 20

        if abs(high_slope) < 0.01 and abs(low_slope) < 0.01:
            score = 55
            desc = "对称三角形，等待突破"
        elif high_slope < 0 and low_slope > 0:
            score = 60
            desc = "收敛三角形，蓄势待发"
        else:
            score = 50
            desc = "无明显三角形态"

        return {'value': score, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return value


# 指标列表
PATTERN_INDICATORS = [
    'head_and_shoulders',
    'double_top_bottom',
    'triangle_pattern',
]


def get_all_pattern_indicators():
    """获取所有形态识别指标名称列表"""
    return PATTERN_INDICATORS.copy()
