"""
估值与财务比率指标模块
包含：PEG比率、PB增长率、流动比率、速动比率、现金比率、营运资本周转率等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class InterestRateSensitivityIndicator(IndicatorBase):
    """利率敏感度指标"""
    name = "interest_rate_sensitivity"
    display_name = "利率敏感度"
    category = IndicatorCategory.FUNDAMENTAL
    description = "对利率变化的敏感程度"

    def calculate(self, beta_to_rate: float = None, debt_ratio: float = None, **kwargs) -> Dict[str, Any]:
        if beta_to_rate is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        sensitivity = abs(beta_to_rate)
        if sensitivity < 0.5:
            score = 70
            desc = f"利率敏感度低 ({sensitivity:.2f})"
        elif sensitivity < 1.0:
            score = 50
            desc = f"利率敏感度中等 ({sensitivity:.2f})"
        else:
            score = 30
            desc = f"利率敏感度高 ({sensitivity:.2f})"

        return {'value': sensitivity, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 0.5:
            return 70.0
        elif value < 1.0:
            return 50.0
        else:
            return 30.0


@auto_register
class InflationHedgeIndicator(IndicatorBase):
    """通胀对冲指标"""
    name = "inflation_hedge"
    display_name = "通胀对冲"
    category = IndicatorCategory.FUNDAMENTAL
    description = "抵御通胀能力"

    def calculate(self, pricing_power: float = None, inventory_turnover: float = None, **kwargs) -> Dict[str, Any]:
        if pricing_power is None:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        hedge_score = pricing_power * 0.7 + (inventory_turnover or 0) * 0.3
        score = min(100, max(0, hedge_score * 100))
        desc = f"通胀对冲能力: {'强' if hedge_score > 0.7 else '中' if hedge_score > 0.4 else '弱'}"
        return {'value': hedge_score, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, value * 100))


@auto_register
class PEGRatioIndicator(IndicatorBase):
    """PEG比率指标"""
    name = "peg_ratio"
    display_name = "PEG比率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "市盈率相对增长率"

    def calculate(self, pe_ratio: float = None, growth_rate: float = None, **kwargs) -> Dict[str, Any]:
        if pe_ratio is None or growth_rate is None or growth_rate == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        peg = pe_ratio / (growth_rate * 100)

        if peg < 1:
            score = 85
            desc = f"估值合理偏低 (PEG={peg:.2f})"
        elif peg < 1.5:
            score = 65
            desc = f"估值合理 (PEG={peg:.2f})"
        elif peg < 2:
            score = 45
            desc = f"估值偏高 (PEG={peg:.2f})"
        else:
            score = 25
            desc = f"估值过高 (PEG={peg:.2f})"

        return {'value': peg, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 1:
            return 85.0
        elif value < 1.5:
            return 65.0
        elif value < 2:
            return 45.0
        else:
            return 25.0


@auto_register
class PriceToBookGrowthIndicator(IndicatorBase):
    """市净率增长指标"""
    name = "pb_growth"
    display_name = "PB增长率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "市净率变化趋势"

    def calculate(self, current_pb: float = None, historical_pb: float = None, **kwargs) -> Dict[str, Any]:
        if current_pb is None or historical_pb is None or historical_pb == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        pb_growth = (current_pb - historical_pb) / historical_pb

        if pb_growth < -0.2:
            score = 80
            desc = f"PB显著下降 ({pb_growth:.1%})，估值修复空间大"
        elif pb_growth < 0:
            score = 65
            desc = f"PB下降 ({pb_growth:.1%})"
        elif pb_growth < 0.2:
            score = 50
            desc = f"PB小幅上升 ({pb_growth:.1%})"
        else:
            score = 30
            desc = f"PB大幅上升 ({pb_growth:.1%})，估值偏高"

        return {'value': pb_growth, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < -0.2:
            return 80.0
        elif value < 0:
            return 65.0
        elif value < 0.2:
            return 50.0
        else:
            return 30.0


@auto_register
class LiquidityRatioIndicator(IndicatorBase):
    """流动比率指标"""
    name = "liquidity_ratio"
    display_name = "流动比率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "流动资产/流动负债"

    def calculate(self, current_assets: float = None, current_liabilities: float = None, **kwargs) -> Dict[str, Any]:
        if current_assets is None or current_liabilities is None or current_liabilities == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        ratio = current_assets / current_liabilities

        if ratio > 2:
            score = 85
            desc = f"流动性充裕 (比率: {ratio:.2f})"
        elif ratio > 1.5:
            score = 70
            desc = f"流动性良好 (比率: {ratio:.2f})"
        elif ratio > 1:
            score = 55
            desc = f"流动性一般 (比率: {ratio:.2f})"
        else:
            score = 30
            desc = f"流动性不足 (比率: {ratio:.2f})"

        return {'value': ratio, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 2:
            return 85.0
        elif value > 1.5:
            return 70.0
        elif value > 1:
            return 55.0
        else:
            return 30.0


@auto_register
class QuickRatioIndicator(IndicatorBase):
    """速动比率指标"""
    name = "quick_ratio"
    display_name = "速动比率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "(流动资产-存货)/流动负债"

    def calculate(self, current_assets: float = None, inventory: float = None,
                  current_liabilities: float = None, **kwargs) -> Dict[str, Any]:
        if None in [current_assets, current_liabilities] or current_liabilities == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        quick_assets = current_assets - (inventory or 0)
        ratio = quick_assets / current_liabilities

        if ratio > 1.5:
            score = 85
            desc = f"速动性强 (比率: {ratio:.2f})"
        elif ratio > 1:
            score = 70
            desc = f"速动性良好 (比率: {ratio:.2f})"
        elif ratio > 0.8:
            score = 55
            desc = f"速动性一般 (比率: {ratio:.2f})"
        else:
            score = 30
            desc = f"速动性不足 (比率: {ratio:.2f})"

        return {'value': ratio, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 1.5:
            return 85.0
        elif value > 1:
            return 70.0
        elif value > 0.8:
            return 55.0
        else:
            return 30.0


@auto_register
class CashRatioIndicator(IndicatorBase):
    """现金比率指标"""
    name = "cash_ratio"
    display_name = "现金比率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "现金及等价物/流动负债"

    def calculate(self, cash: float = None, current_liabilities: float = None, **kwargs) -> Dict[str, Any]:
        if cash is None or current_liabilities is None or current_liabilities == 0:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        ratio = cash / current_liabilities

        if ratio > 0.5:
            score = 85
            desc = f"现金充裕 (比率: {ratio:.2f})"
        elif ratio > 0.3:
            score = 70
            desc = f"现金良好 (比率: {ratio:.2f})"
        elif ratio > 0.2:
            score = 55
            desc = f"现金一般 (比率: {ratio:.2f})"
        else:
            score = 35
            desc = f"现金紧张 (比率: {ratio:.2f})"

        return {'value': ratio, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.5:
            return 85.0
        elif value > 0.3:
            return 70.0
        elif value > 0.2:
            return 55.0
        else:
            return 35.0


@auto_register
class WorkingCapitalTurnoverIndicator(IndicatorBase):
    """营运资本周转率"""
    name = "working_capital_turnover"
    display_name = "营运资本周转率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "收入/营运资本"

    def calculate(self, revenue: float = None, current_assets: float = None,
                  current_liabilities: float = None, **kwargs) -> Dict[str, Any]:
        if None in [revenue, current_assets, current_liabilities]:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        working_capital = current_assets - current_liabilities
        if working_capital <= 0:
            return {'value': None, 'score': 30, 'description': '营运资本为负'}

        turnover = revenue / working_capital

        if turnover > 5:
            score = 85
            desc = f"周转极快 ({turnover:.2f}次)"
        elif turnover > 3:
            score = 70
            desc = f"周转良好 ({turnover:.2f}次)"
        elif turnover > 1:
            score = 55
            desc = f"周转一般 ({turnover:.2f}次)"
        else:
            score = 40
            desc = f"周转缓慢 ({turnover:.2f}次)"

        return {'value': turnover, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 5:
            return 85.0
        elif value > 3:
            return 70.0
        elif value > 1:
            return 55.0
        else:
            return 40.0


# 指标列表
VALUATION_INDICATORS = [
    'interest_rate_sensitivity',
    'inflation_hedge',
    'peg_ratio',
    'pb_growth',
    'liquidity_ratio',
    'quick_ratio',
    'cash_ratio',
    'working_capital_turnover',
]


def get_all_valuation_indicators():
    """获取所有估值指标名称列表"""
    return VALUATION_INDICATORS.copy()
