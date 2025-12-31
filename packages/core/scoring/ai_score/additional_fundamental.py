"""
补充基本面指标模块
包含：Altman Z-Score、杜邦分析、自由现金流收益率、资产周转率、Piotroski F-Score等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class AltmanZScoreIndicator(IndicatorBase):
    """Altman Z-Score破产风险指标

    评估企业破产风险，Z>2.99为安全区，Z<1.81为危险区
    """
    name = "altman_z_score"
    display_name = "Altman Z-Score"
    category = IndicatorCategory.FUNDAMENTAL
    description = "企业破产风险评估，Z值越高越安全"

    def calculate(self, total_assets: float = None, current_assets: float = None,
                  current_liabilities: float = None, retained_earnings: float = None,
                  ebit: float = None, market_cap: float = None,
                  total_liabilities: float = None, revenue: float = None, **kwargs) -> Dict[str, Any]:
        if None in [total_assets, current_assets, current_liabilities, retained_earnings, ebit]:
            return {'value': None, 'description': '财务数据不足'}

        if total_assets == 0:
            return {'value': None, 'description': '总资产为零'}

        # Altman Z-Score公式（制造业版本）
        x1 = (current_assets - current_liabilities) / total_assets
        x2 = retained_earnings / total_assets
        x3 = ebit / total_assets
        x4 = market_cap / total_liabilities if total_liabilities and total_liabilities > 0 else 0
        x5 = revenue / total_assets if revenue else 0

        z_score = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5

        if z_score > 2.99:
            desc = f"财务安全 (Z={z_score:.2f})"
            signal = "safe"
            score = 90
        elif z_score > 1.81:
            desc = f"灰色地带 (Z={z_score:.2f})"
            signal = "warning"
            score = 50
        else:
            desc = f"破产风险高 (Z={z_score:.2f})"
            signal = "danger"
            score = 20

        return {
            'value': z_score,
            'score': score,
            'signal': signal,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 2.99:
            return 90.0
        elif value > 1.81:
            return 50.0
        else:
            return 20.0


@auto_register
class DuPontROEIndicator(IndicatorBase):
    """杜邦分析ROE指标

    将ROE分解为销售净利率、资产周转率、权益乘数三个因子
    """
    name = "dupont_roe"
    display_name = "杜邦ROE分析"
    category = IndicatorCategory.FUNDAMENTAL
    description = "ROE分解分析，识别盈利能力来源"

    def calculate(self, net_profit: float = None, revenue: float = None,
                  total_assets: float = None, equity: float = None, **kwargs) -> Dict[str, Any]:
        if None in [net_profit, revenue, total_assets, equity] or equity == 0:
            return {'value': None, 'description': '财务数据不足'}

        if revenue == 0 or total_assets == 0:
            return {'value': None, 'description': '收入或资产为零'}

        npm = net_profit / revenue
        ato = revenue / total_assets
        em = total_assets / equity

        roe = npm * ato * em

        factors = []
        if npm > 0.15:
            factors.append("高净利率")
        if ato > 0.8:
            factors.append("高周转")
        if em > 2:
            factors.append("高杠杆")

        desc = f"ROE={roe*100:.2f}% (净利率{npm*100:.1f}% × 周转{ato:.2f} × 杠杆{em:.2f})"
        if factors:
            desc += f" [{','.join(factors)}]"

        score = min(100, max(0, roe * 500))

        return {
            'value': roe,
            'score': score,
            'npm': npm,
            'ato': ato,
            'em': em,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, value * 500))


@auto_register
class FreeCashFlowYieldIndicator(IndicatorBase):
    """自由现金流收益率指标

    自由现金流/市值，衡量现金创造能力
    """
    name = "fcf_yield"
    display_name = "自由现金流收益率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "自由现金流/市值，越高越好"

    def calculate(self, operating_cash_flow: float = None, capex: float = None,
                  market_cap: float = None, **kwargs) -> Dict[str, Any]:
        if None in [operating_cash_flow, capex, market_cap] or market_cap == 0:
            return {'value': None, 'description': '数据不足'}

        fcf = operating_cash_flow - capex
        fcf_yield = fcf / market_cap

        if fcf_yield > 0.08:
            desc = f"现金流充沛 ({fcf_yield*100:.2f}%)"
            score = 90
        elif fcf_yield > 0.05:
            desc = f"现金流良好 ({fcf_yield*100:.2f}%)"
            score = 70
        elif fcf_yield > 0:
            desc = f"现金流一般 ({fcf_yield*100:.2f}%)"
            score = 50
        else:
            desc = f"现金流为负 ({fcf_yield*100:.2f}%)"
            score = 20

        return {
            'value': fcf_yield,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0.08:
            return 90.0
        elif value > 0.05:
            return 70.0
        elif value > 0:
            return 50.0
        else:
            return 20.0


@auto_register
class AssetTurnoverRatioIndicator(IndicatorBase):
    """资产周转率指标

    收入/总资产，衡量资产使用效率
    """
    name = "asset_turnover"
    display_name = "资产周转率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "资产使用效率，周转越快越好"

    def calculate(self, revenue: float = None, total_assets: float = None, **kwargs) -> Dict[str, Any]:
        if None in [revenue, total_assets] or total_assets == 0:
            return {'value': None, 'description': '数据不足'}

        turnover = revenue / total_assets

        if turnover > 1.5:
            desc = f"周转快速 ({turnover:.2f}次/年)"
            score = 90
        elif turnover > 1.0:
            desc = f"周转良好 ({turnover:.2f}次/年)"
            score = 70
        elif turnover > 0.5:
            desc = f"周转一般 ({turnover:.2f}次/年)"
            score = 50
        else:
            desc = f"周转缓慢 ({turnover:.2f}次/年)"
            score = 30

        return {
            'value': turnover,
            'score': score,
            'description': desc
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 1.5:
            return 90.0
        elif value > 1.0:
            return 70.0
        elif value > 0.5:
            return 50.0
        else:
            return 30.0


@auto_register
class PiotroskiFScoreIndicator(IndicatorBase):
    """Piotroski F-Score指标

    9分制财务健康评分
    """
    name = "piotroski_f_score"
    display_name = "Piotroski F-Score"
    category = IndicatorCategory.FUNDAMENTAL
    description = "9分制财务健康评分"

    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}

        score = 0
        details = []

        # 1. ROA > 0
        roa = financial_data.get('roa', 0)
        if roa > 0:
            score += 1
            details.append("ROA为正")

        # 2. 经营现金流 > 0
        ocf = financial_data.get('operating_cash_flow', 0)
        if ocf > 0:
            score += 1
            details.append("经营现金流为正")

        # 3. ROA增长
        roa_change = financial_data.get('roa_change', 0)
        if roa_change > 0:
            score += 1
            details.append("ROA增长")

        # 4. 经营现金流 > 净利润
        net_profit = financial_data.get('net_profit', 0)
        if ocf > net_profit:
            score += 1
            details.append("现金流质量好")

        # 5. 长期负债减少
        debt_change = financial_data.get('long_term_debt_change', 0)
        if debt_change < 0:
            score += 1
            details.append("长期负债减少")

        # 6. 流动比率提高
        current_ratio_change = financial_data.get('current_ratio_change', 0)
        if current_ratio_change > 0:
            score += 1
            details.append("流动性改善")

        # 7. 无新股发行
        shares_issued = financial_data.get('shares_issued', 0)
        if shares_issued <= 0:
            score += 1
            details.append("无稀释")

        # 8. 毛利率提高
        gross_margin_change = financial_data.get('gross_margin_change', 0)
        if gross_margin_change > 0:
            score += 1
            details.append("毛利率提高")

        # 9. 资产周转率提高
        asset_turnover_change = financial_data.get('asset_turnover_change', 0)
        if asset_turnover_change > 0:
            score += 1
            details.append("周转率提高")

        if score >= 7:
            desc = f"财务健康优秀 (F-Score: {score}/9)"
        elif score >= 5:
            desc = f"财务健康良好 (F-Score: {score}/9)"
        elif score >= 3:
            desc = f"财务健康一般 (F-Score: {score}/9)"
        else:
            desc = f"财务健康较差 (F-Score: {score}/9)"

        return {
            'value': score,
            'score': score / 9 * 100,
            'description': desc,
            'extra_data': {'details': details}
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return value / 9 * 100


# 指标列表
ADDITIONAL_FUNDAMENTAL_INDICATORS = [
    'altman_z_score',
    'dupont_roe',
    'fcf_yield',
    'asset_turnover',
    'piotroski_f_score',
]


def get_all_additional_fundamental_indicators():
    """获取所有补充基本面指标名称列表"""
    return ADDITIONAL_FUNDAMENTAL_INDICATORS.copy()
