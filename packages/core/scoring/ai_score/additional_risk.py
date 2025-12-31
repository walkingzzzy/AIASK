"""
补充风险面指标模块
包含：VaR风险价值、CVaR条件风险价值、信息比率、波动率趋势等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class VaRIndicator(IndicatorBase):
    """VaR风险价值指标"""
    name = "var"
    display_name = "VaR风险价值"
    category = IndicatorCategory.RISK
    description = "95%置信度下的最大损失"

    def calculate(self, returns: pd.Series = None, confidence: float = 0.95, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        var = returns.quantile(1 - confidence)

        if var > -0.02:
            score = 80
            desc = f"VaR风险低 ({var:.2%})"
        elif var > -0.05:
            score = 60
            desc = f"VaR风险中等 ({var:.2%})"
        elif var > -0.08:
            score = 40
            desc = f"VaR风险较高 ({var:.2%})"
        else:
            score = 20
            desc = f"VaR风险高 ({var:.2%})"

        return {
            'value': var,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > -0.02:
            return 80.0
        elif value > -0.05:
            return 60.0
        elif value > -0.08:
            return 40.0
        else:
            return 20.0


@auto_register
class CVaRIndicator(IndicatorBase):
    """CVaR条件风险价值指标"""
    name = "cvar"
    display_name = "CVaR条件风险价值"
    category = IndicatorCategory.RISK
    description = "超过VaR的平均损失"

    def calculate(self, returns: pd.Series = None, confidence: float = 0.95, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        var = returns.quantile(1 - confidence)
        cvar = returns[returns <= var].mean()

        if cvar > -0.03:
            score = 80
            desc = f"CVaR风险低 ({cvar:.2%})"
        elif cvar > -0.06:
            score = 60
            desc = f"CVaR风险中等 ({cvar:.2%})"
        elif cvar > -0.10:
            score = 40
            desc = f"CVaR风险较高 ({cvar:.2%})"
        else:
            score = 20
            desc = f"CVaR风险高 ({cvar:.2%})"

        return {
            'value': cvar,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > -0.03:
            return 80.0
        elif value > -0.06:
            return 60.0
        elif value > -0.10:
            return 40.0
        else:
            return 20.0


@auto_register
class InformationRatioIndicator(IndicatorBase):
    """信息比率指标"""
    name = "information_ratio"
    display_name = "信息比率"
    category = IndicatorCategory.RISK
    description = "超额收益/跟踪误差"

    def calculate(self, returns: pd.Series = None, benchmark_returns: pd.Series = None,
                  **kwargs) -> Dict[str, Any]:
        if returns is None or benchmark_returns is None or len(returns) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        excess_returns = returns - benchmark_returns
        ir = excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0

        if ir > 0.5:
            score = 85
            desc = f"信息比率优秀 ({ir:.2f})"
        elif ir > 0.3:
            score = 70
            desc = f"信息比率良好 ({ir:.2f})"
        elif ir > 0:
            score = 55
            desc = f"信息比率一般 ({ir:.2f})"
        else:
            score = 35
            desc = f"信息比率较低 ({ir:.2f})"

        return {
            'value': ir,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.5:
            return 85.0
        elif value > 0.3:
            return 70.0
        elif value > 0:
            return 55.0
        else:
            return 35.0


@auto_register
class VolatilityTrendIndicator(IndicatorBase):
    """波动率趋势指标

    分析波动率的变化趋势
    """
    name = "volatility_trend"
    display_name = "波动率趋势"
    category = IndicatorCategory.RISK
    description = "波动率变化趋势分析"

    def calculate(self, returns: pd.Series = None, window: int = 20, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < window * 2:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        rolling_vol = returns.rolling(window=window).std()
        recent_vol = rolling_vol.iloc[-1]
        historical_vol = rolling_vol.mean()

        vol_change = (recent_vol - historical_vol) / historical_vol if historical_vol > 0 else 0

        if vol_change < -0.2:
            score = 80
            desc = f"波动率显著下降 ({vol_change:.1%})，风险降低"
        elif vol_change < -0.1:
            score = 65
            desc = f"波动率下降 ({vol_change:.1%})"
        elif vol_change > 0.2:
            score = 30
            desc = f"波动率显著上升 ({vol_change:.1%})，风险增加"
        elif vol_change > 0.1:
            score = 45
            desc = f"波动率上升 ({vol_change:.1%})"
        else:
            score = 55
            desc = f"波动率稳定 ({vol_change:+.1%})"

        return {
            'value': vol_change,
            'score': score,
            'description': desc,
            'extra_data': {'recent_vol': recent_vol, 'historical_vol': historical_vol}
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < -0.2:
            return 80.0
        elif value < -0.1:
            return 65.0
        elif value > 0.2:
            return 30.0
        elif value > 0.1:
            return 45.0
        else:
            return 55.0


# 指标列表
ADDITIONAL_RISK_INDICATORS = [
    'var',
    'cvar',
    'information_ratio',
    'volatility_trend',
]


def get_all_additional_risk_indicators():
    """获取所有补充风险面指标名称列表"""
    return ADDITIONAL_RISK_INDICATORS.copy()
