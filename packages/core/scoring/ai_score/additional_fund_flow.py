"""
补充资金面指标模块
包含：ETF资金流向、QFII持仓变化、换手率分位数等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class ETFFundFlowIndicator(IndicatorBase):
    """ETF资金流向指标

    追踪ETF对个股的买卖情况
    """
    name = "etf_fund_flow"
    display_name = "ETF资金流向"
    category = IndicatorCategory.FUND_FLOW
    description = "ETF资金净流入情况"

    def calculate(self, etf_inflow: float = None, etf_outflow: float = None, **kwargs) -> Dict[str, Any]:
        if etf_inflow is None or etf_outflow is None:
            return {'value': None, 'description': 'ETF数据不足'}

        net_flow = etf_inflow - etf_outflow
        flow_ratio = net_flow / (etf_inflow + etf_outflow + 1) if (etf_inflow + etf_outflow) > 0 else 0

        if flow_ratio > 0.3:
            desc = f"ETF大幅净流入 ({net_flow/1e8:.2f}亿)"
            score = 90
        elif flow_ratio > 0.1:
            desc = f"ETF净流入 ({net_flow/1e8:.2f}亿)"
            score = 70
        elif flow_ratio > -0.1:
            desc = f"ETF资金平衡 ({net_flow/1e8:.2f}亿)"
            score = 50
        else:
            desc = f"ETF净流出 ({net_flow/1e8:.2f}亿)"
            score = 30

        return {
            'value': net_flow,
            'score': score,
            'flow_ratio': flow_ratio,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 100000000:
            return 90.0
        elif value > 50000000:
            return 70.0
        elif value > -50000000:
            return 50.0
        else:
            return 30.0


@auto_register
class QFIIHoldingChangeIndicator(IndicatorBase):
    """QFII持仓变化指标"""
    name = "qfii_holding_change"
    display_name = "QFII持仓变化"
    category = IndicatorCategory.FUND_FLOW
    description = "QFII持仓变化趋势"

    def calculate(self, qfii_holding_current: float = None, qfii_holding_previous: float = None,
                  **kwargs) -> Dict[str, Any]:
        if qfii_holding_current is None or qfii_holding_previous is None or qfii_holding_previous == 0:
            return {'value': None, 'score': 5.0, 'description': '数据不足'}

        change_rate = (qfii_holding_current - qfii_holding_previous) / qfii_holding_previous

        if change_rate > 0.10:
            score = 80
            desc = f"QFII大幅增持 ({change_rate:.1%})"
        elif change_rate > 0.05:
            score = 65
            desc = f"QFII增持 ({change_rate:.1%})"
        elif change_rate < -0.10:
            score = 25
            desc = f"QFII大幅减持 ({change_rate:.1%})"
        elif change_rate < -0.05:
            score = 40
            desc = f"QFII减持 ({change_rate:.1%})"
        else:
            score = 50
            desc = f"QFII持仓稳定 ({change_rate:.1%})"

        return {
            'value': change_rate,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.10:
            return 80.0
        elif value > 0.05:
            return 65.0
        elif value < -0.10:
            return 25.0
        elif value < -0.05:
            return 40.0
        else:
            return 50.0


@auto_register
class TurnoverRatePercentileIndicator(IndicatorBase):
    """换手率分位数指标"""
    name = "turnover_rate_percentile"
    display_name = "换手率分位数"
    category = IndicatorCategory.FUND_FLOW
    description = "换手率历史分位数"

    def calculate(self, turnover_rate: float = None, turnover_history: List[float] = None,
                  **kwargs) -> Dict[str, Any]:
        if turnover_rate is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        if not turnover_history:
            if turnover_rate > 10:
                score = 70
                desc = f"换手率高 ({turnover_rate:.1f}%)"
            elif turnover_rate > 5:
                score = 60
                desc = f"换手率适中 ({turnover_rate:.1f}%)"
            else:
                score = 40
                desc = f"换手率低 ({turnover_rate:.1f}%)"
        else:
            percentile = sum(1 for x in turnover_history if x <= turnover_rate) / len(turnover_history)

            if percentile > 0.8:
                score = 75
                desc = f"换手率处于高位 (分位数: {percentile:.0%})"
            elif percentile > 0.5:
                score = 60
                desc = f"换手率适中 (分位数: {percentile:.0%})"
            else:
                score = 45
                desc = f"换手率较低 (分位数: {percentile:.0%})"

        return {
            'value': turnover_rate,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 10:
            return 70.0
        elif value > 5:
            return 60.0
        else:
            return 40.0


# 指标列表
ADDITIONAL_FUND_FLOW_INDICATORS = [
    'etf_fund_flow',
    'qfii_holding_change',
    'turnover_rate_percentile',
]


def get_all_additional_fund_flow_indicators():
    """获取所有补充资金面指标名称列表"""
    return ADDITIONAL_FUND_FLOW_INDICATORS.copy()
