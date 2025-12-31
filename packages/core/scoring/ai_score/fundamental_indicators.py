"""
高级基本面指标计算模块
扩展AI评分系统的基本面指标维度
"""
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class FundamentalIndicatorResult:
    """基本面指标结果"""
    value: float
    score: float  # 0-10分
    level: str  # 'excellent', 'good', 'fair', 'poor'
    description: str


class AdvancedFundamentalIndicators:
    """高级基本面指标计算器"""

    @staticmethod
    def calculate_piotroski_f_score(financial_data: Dict[str, Any]) -> FundamentalIndicatorResult:
        """
        Piotroski F-Score (0-9分)
        衡量公司财务健康度的综合指标

        Args:
            financial_data: 财务数据字典

        Returns:
            指标结果
        """
        score = 0

        # 盈利能力 (4分)
        if financial_data.get('net_profit', 0) > 0:
            score += 1
        if financial_data.get('operating_cash_flow', 0) > 0:
            score += 1
        if financial_data.get('roa_change', 0) > 0:
            score += 1
        if financial_data.get('operating_cash_flow', 0) > financial_data.get('net_profit', 0):
            score += 1

        # 杠杆、流动性 (3分)
        if financial_data.get('leverage_change', 0) < 0:
            score += 1
        if financial_data.get('current_ratio_change', 0) > 0:
            score += 1
        if financial_data.get('shares_outstanding_change', 0) <= 0:
            score += 1

        # 运营效率 (2分)
        if financial_data.get('gross_margin_change', 0) > 0:
            score += 1
        if financial_data.get('asset_turnover_change', 0) > 0:
            score += 1

        # 转换为0-10分
        normalized_score = score / 9 * 10

        if score >= 7:
            level = 'excellent'
            desc = f"财务健康度优秀 (F-Score: {score}/9)"
        elif score >= 5:
            level = 'good'
            desc = f"财务健康度良好 (F-Score: {score}/9)"
        elif score >= 3:
            level = 'fair'
            desc = f"财务健康度一般 (F-Score: {score}/9)"
        else:
            level = 'poor'
            desc = f"财务健康度较差 (F-Score: {score}/9)"

        return FundamentalIndicatorResult(
            value=score,
            score=normalized_score,
            level=level,
            description=desc
        )

    @staticmethod
    def calculate_altman_z_score(financial_data: Dict[str, Any]) -> FundamentalIndicatorResult:
        """
        Altman Z-Score
        预测企业破产风险

        Args:
            financial_data: 财务数据字典

        Returns:
            指标结果
        """
        # Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
        x1 = financial_data.get('working_capital', 0) / financial_data.get('total_assets', 1)
        x2 = financial_data.get('retained_earnings', 0) / financial_data.get('total_assets', 1)
        x3 = financial_data.get('ebit', 0) / financial_data.get('total_assets', 1)
        x4 = financial_data.get('market_cap', 0) / financial_data.get('total_liabilities', 1)
        x5 = financial_data.get('revenue', 0) / financial_data.get('total_assets', 1)

        z_score = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5

        if z_score > 2.99:
            level = 'excellent'
            score = 9.0
            desc = f"破产风险极低 (Z-Score: {z_score:.2f})"
        elif z_score > 1.81:
            level = 'good'
            score = 6.0
            desc = f"破产风险较低 (Z-Score: {z_score:.2f})"
        else:
            level = 'poor'
            score = 3.0
            desc = f"破产风险较高 (Z-Score: {z_score:.2f})"

        return FundamentalIndicatorResult(
            value=z_score,
            score=score,
            level=level,
            description=desc
        )

    @staticmethod
    def calculate_dupont_analysis(financial_data: Dict[str, Any]) -> FundamentalIndicatorResult:
        """
        杜邦分析 - ROE分解
        ROE = 净利率 × 资产周转率 × 权益乘数

        Args:
            financial_data: 财务数据字典

        Returns:
            指标结果
        """
        net_margin = financial_data.get('net_profit', 0) / financial_data.get('revenue', 1)
        asset_turnover = financial_data.get('revenue', 0) / financial_data.get('total_assets', 1)
        equity_multiplier = financial_data.get('total_assets', 1) / financial_data.get('equity', 1)

        roe = net_margin * asset_turnover * equity_multiplier * 100

        if roe > 20:
            level = 'excellent'
            score = 9.0
            desc = f"ROE优秀 ({roe:.1f}%)"
        elif roe > 15:
            level = 'good'
            score = 7.5
            desc = f"ROE良好 ({roe:.1f}%)"
        elif roe > 10:
            level = 'fair'
            score = 6.0
            desc = f"ROE一般 ({roe:.1f}%)"
        else:
            level = 'poor'
            score = 4.0
            desc = f"ROE较低 ({roe:.1f}%)"

        return FundamentalIndicatorResult(
            value=roe,
            score=score,
            level=level,
            description=desc
        )

    @staticmethod
    def calculate_cash_conversion_cycle(financial_data: Dict[str, Any]) -> FundamentalIndicatorResult:
        """
        现金转换周期
        CCC = DSO + DIO - DPO

        Args:
            financial_data: 财务数据字典

        Returns:
            指标结果
        """
        dso = financial_data.get('accounts_receivable', 0) / financial_data.get('revenue', 1) * 365
        dio = financial_data.get('inventory', 0) / financial_data.get('cogs', 1) * 365
        dpo = financial_data.get('accounts_payable', 0) / financial_data.get('cogs', 1) * 365

        ccc = dso + dio - dpo

        if ccc < 30:
            level = 'excellent'
            score = 9.0
            desc = f"现金周转极快 ({ccc:.0f}天)"
        elif ccc < 60:
            level = 'good'
            score = 7.0
            desc = f"现金周转良好 ({ccc:.0f}天)"
        elif ccc < 90:
            level = 'fair'
            score = 5.0
            desc = f"现金周转一般 ({ccc:.0f}天)"
        else:
            level = 'poor'
            score = 3.0
            desc = f"现金周转较慢 ({ccc:.0f}天)"

        return FundamentalIndicatorResult(
            value=ccc,
            score=score,
            level=level,
            description=desc
        )

    @staticmethod
    def calculate_free_cash_flow_yield(financial_data: Dict[str, Any]) -> FundamentalIndicatorResult:
        """
        自由现金流收益率
        FCF Yield = FCF / Market Cap

        Args:
            financial_data: 财务数据字典

        Returns:
            指标结果
        """
        fcf = financial_data.get('operating_cash_flow', 0) - financial_data.get('capex', 0)
        market_cap = financial_data.get('market_cap', 1)

        fcf_yield = fcf / market_cap * 100

        if fcf_yield > 8:
            level = 'excellent'
            score = 9.0
            desc = f"FCF收益率优秀 ({fcf_yield:.1f}%)"
        elif fcf_yield > 5:
            level = 'good'
            score = 7.0
            desc = f"FCF收益率良好 ({fcf_yield:.1f}%)"
        elif fcf_yield > 2:
            level = 'fair'
            score = 5.0
            desc = f"FCF收益率一般 ({fcf_yield:.1f}%)"
        else:
            level = 'poor'
            score = 3.0
            desc = f"FCF收益率较低 ({fcf_yield:.1f}%)"

        return FundamentalIndicatorResult(
            value=fcf_yield,
            score=score,
            level=level,
            description=desc
        )