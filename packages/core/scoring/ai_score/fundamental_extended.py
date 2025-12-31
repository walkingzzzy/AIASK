"""
扩展基本面指标计算模块
包含12个新增基本面指标：盈利能力、偿债能力、运营效率等
"""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (IndicatorBase,IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


#==================== 盈利能力指标 ====================

@auto_register
class EBITDAMarginIndicator(IndicatorBase):
    """EBITDA利润率指标EBITDA / 营业收入，衡量企业核心经营盈利能力
    """
    name = "ebitda_margin"
    display_name = "EBITDA利润率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "EBITDA除以营业收入，衡量核心盈利能力"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        revenue = financial_data.get('revenue', 0)
        net_profit = financial_data.get('net_profit', 0)
        depreciation = financial_data.get('depreciation', 0)
        amortization = financial_data.get('amortization', 0)
        interest_expense = financial_data.get('interest_expense', 0)
        tax = financial_data.get('income_tax', 0)
        
        # EBITDA = 净利润 + 利息 + 税 + 折旧 + 摊销
        ebitda = net_profit + interest_expense + tax + depreciation + amortization
        
        if revenue <= 0:
            return {'value': None, 'description': '营业收入无效'}
        
        margin = ebitda / revenue * 100
        
        if margin > 30:
            desc = f"EBITDA利润率优秀: {margin:.1f}%"
        elif margin > 20:
            desc = f"EBITDA利润率良好: {margin:.1f}%"
        elif margin > 10:
            desc = f"EBITDA利润率一般: {margin:.1f}%"
        else:
            desc = f"EBITDA利润率较低: {margin:.1f}%"
        
        return {
            'value': margin,
            'description': desc,
            'extra_data': {'ebitda': ebitda, 'revenue': revenue}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 30:
            return 90.0
        elif value >= 20:
            return 75.0
        elif value >= 10:
            return 55.0
        elif value >= 0:
            return 35.0
        else:
            return 15.0


@auto_register
class DividendYieldIndicator(IndicatorBase):
    """股息率指标
    
    每股股息 / 股价，衡量股票的股息回报
    """
    name = "dividend_yield"
    display_name = "股息率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "每股股息除以股价"
    
    def calculate(self, financial_data: Dict[str, Any] = None,stock_price: float = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None or stock_price is None or stock_price <= 0:
            return {'value': None, 'description': '数据不足'}
        dps = financial_data.get('dividend_per_share', 0)  # 每股股息
        
        dividend_yield = dps / stock_price * 100
        
        if dividend_yield > 5:
            desc = f"高股息率: {dividend_yield:.2f}%"
        elif dividend_yield > 3:
            desc = f"中等股息率: {dividend_yield:.2f}%"
        elif dividend_yield > 1:
            desc = f"较低股息率: {dividend_yield:.2f}%"
        else:
            desc = f"极低/无股息: {dividend_yield:.2f}%"
        
        return {'value': dividend_yield, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 5:
            return 85.0
        elif value >= 3:
            return 70.0
        elif value >= 1:
            return 55.0
        elif value > 0:
            return 40.0
        else:
            return 30.0


@auto_register
class DividendPayoutRatioIndicator(IndicatorBase):
    """股息支付率指标
    
    股息总额 / 净利润，衡量公司分红慷慨程度
    """
    name = "dividend_payout_ratio"
    display_name = "股息支付率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "股息除以净利润"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        dividends = financial_data.get('total_dividends', 0)
        net_profit = financial_data.get('net_profit', 0)
        
        if net_profit <= 0:
            if dividends > 0:
                desc = "亏损仍分红，需关注"
                return {'value': 100.0, 'description': desc}
            else:
                desc = "未盈利，无分红"
                return {'value': 0.0, 'description': desc}
        
        payout_ratio = dividends / net_profit * 100
        
        if payout_ratio > 80:
            desc = f"超高分红率: {payout_ratio:.1f}%，留存较少"
        elif payout_ratio > 50:
            desc = f"高分红率: {payout_ratio:.1f}%"
        elif payout_ratio > 30:
            desc = f"适中分红率: {payout_ratio:.1f}%"
        elif payout_ratio > 0:
            desc = f"低分红率: {payout_ratio:.1f}%"
        else:
            desc = "无分红"
        
        return {'value': payout_ratio, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 30-60%是最佳区间
        if 30 <= value <= 60:
            return 80.0
        elif 20 <= value < 30 or 60< value <= 80:
            return 65.0
        elif value > 80:
            return 45.0  # 过高可能不可持续
        elif value > 0:
            return 50.0
        else:
            return 35.0


@auto_register
class OperatingProfitMarginIndicator(IndicatorBase):
    """营业利润率指标
    
    营业利润 / 营业收入
    """
    name = "operating_profit_margin"
    display_name = "营业利润率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "营业利润除以营业收入"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        operating_profit = financial_data.get('operating_profit', 0)
        revenue = financial_data.get('revenue', 0)
        
        if revenue <= 0:
            return {'value': None, 'description': '营业收入无效'}
        
        margin = operating_profit / revenue * 100
        
        if margin > 25:
            desc = f"营业利润率优秀: {margin:.1f}%"
        elif margin > 15:
            desc = f"营业利润率良好: {margin:.1f}%"
        elif margin > 5:
            desc = f"营业利润率一般: {margin:.1f}%"
        elif margin > 0:
            desc = f"营业利润率较低: {margin:.1f}%"
        else:
            desc = f"营业亏损: {margin:.1f}%"
        
        return {'value': margin, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 25:
            return 90.0
        elif value >= 15:
            return 75.0
        elif value >= 5:
            return 55.0
        elif value >= 0:
            return 35.0
        else:
            return 15.0


@auto_register
class GrossMarginChangeIndicator(IndicatorBase):
    """毛利率变化指标
    
    毛利率同比变化
    """
    name = "gross_margin_change"
    display_name = "毛利率变化"
    category = IndicatorCategory.FUNDAMENTAL
    description = "毛利率同比变化"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        current_margin = financial_data.get('gross_margin', None)
        prev_margin = financial_data.get('gross_margin_prev_year', None)
        
        if current_margin is None or prev_margin is None:
            return {'value': None, 'description': '历史数据不足'}
        
        change = current_margin - prev_margin
        
        if change > 5:
            desc = f"毛利率大幅提升: +{change:.1f}pp"
        elif change > 1:
            desc = f"毛利率小幅提升: +{change:.1f}pp"
        elif change > -1:
            desc = f"毛利率基本持平: {change:+.1f}pp"
        elif change > -5:
            desc = f"毛利率小幅下降: {change:.1f}pp"
        else:
            desc = f"毛利率大幅下降: {change:.1f}pp"
        
        return {
            'value': change,
            'description': desc,
            'extra_data': {
                'current_margin': current_margin,
                'prev_margin': prev_margin
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 5:
            return 90.0
        elif value >= 2:
            return 75.0
        elif value >= 0:
            return 60.0
        elif value >= -2:
            return 45.0
        elif value >= -5:
            return 30.0
        else:
            return 15.0


# ==================== 研发与资产质量指标 ====================

@auto_register
class RDExpenseRatioIndicator(IndicatorBase):
    """研发费用率指标
    
    研发费用 / 营业收入
    """
    name = "rd_expense_ratio"
    display_name = "研发费用率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "研发费用除以营业收入"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        rd_expense = financial_data.get('rd_expense', 0)
        revenue = financial_data.get('revenue', 0)
        
        if revenue <= 0:
            return {'value': None, 'description': '营业收入无效'}
        
        ratio = rd_expense / revenue * 100
        
        if ratio > 15:
            desc = f"高研发投入: {ratio:.1f}%，科技属性强"
        elif ratio > 8:
            desc = f"较高研发投入: {ratio:.1f}%"
        elif ratio > 3:
            desc = f"适中研发投入: {ratio:.1f}%"
        elif ratio > 0:
            desc = f"较低研发投入: {ratio:.1f}%"
        else:
            desc = "无研发投入"
        
        return {'value': ratio, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 科技公司研发费用率高是好事
        if value >= 15:
            return 85.0
        elif value >= 8:
            return 75.0
        elif value >= 3:
            return 60.0
        elif value > 0:
            return 45.0
        else:
            return 35.0


@auto_register
class GoodwillRatioIndicator(IndicatorBase):
    """商誉占比指标
    
    商誉 / 总资产，衡量并购风险
    """
    name = "goodwill_ratio"
    display_name = "商誉占比"
    category = IndicatorCategory.FUNDAMENTAL
    description = "商誉除以总资产"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        goodwill = financial_data.get('goodwill', 0)
        total_assets = financial_data.get('total_assets', 0)
        
        if total_assets <= 0:
            return {'value': None, 'description': '总资产无效'}
        
        ratio = goodwill / total_assets * 100
        
        if ratio > 30:
            desc = f"商誉占比过高: {ratio:.1f}%，减值风险大"
        elif ratio > 15:
            desc = f"商誉占比较高: {ratio:.1f}%，需关注"
        elif ratio > 5:
            desc = f"商誉占比适中: {ratio:.1f}%"
        elif ratio > 0:
            desc = f"商誉占比较低: {ratio:.1f}%"
        else:
            desc = "无商誉"
        
        return {'value': ratio, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 商誉越低越好
        if value <= 0:
            return 90.0
        elif value <= 5:
            return 80.0
        elif value <= 15:
            return 60.0
        elif value <= 30:
            return 35.0
        else:
            return 15.0


# ==================== 运营效率指标 ====================

@auto_register
class InventoryTurnoverDaysIndicator(IndicatorBase):
    """存货周转天数指标
    
    365/ 存货周转率
    """
    name = "inventory_turnover_days"
    display_name = "存货周转天数"
    category = IndicatorCategory.FUNDAMENTAL
    description = "存货周转一次所需天数"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        inventory = financial_data.get('inventory', 0)
        cogs = financial_data.get('cost_of_goods_sold', 0)
        
        if cogs <= 0:
            return {'value': None, 'description': '成本数据无效'}
        
        turnover_rate = cogs / inventory if inventory > 0 else 0
        days = 365 / turnover_rate if turnover_rate > 0 else 365
        
        if days < 30:
            desc = f"存货周转极快: {days:.0f}天"
        elif days < 60:
            desc = f"存货周转较快: {days:.0f}天"
        elif days < 120:
            desc = f"存货周转正常: {days:.0f}天"
        elif days < 200:
            desc = f"存货周转较慢: {days:.0f}天"
        else:
            desc = f"存货周转很慢: {days:.0f}天"
        
        return {'value': days, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 周转天数越少越好
        if value <= 30:
            return 90.0
        elif value <= 60:
            return 75.0
        elif value <= 120:
            return 55.0
        elif value <= 200:
            return 35.0
        else:
            return 20.0


@auto_register
class ReceivableTurnoverDaysIndicator(IndicatorBase):
    """应收账款周转天数指标
    
    365 / 应收账款周转率
    """
    name = "receivable_turnover_days"
    display_name = "应收账款周转天数"
    category = IndicatorCategory.FUNDAMENTAL
    description = "应收账款回收所需天数"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        receivables = financial_data.get('accounts_receivable', 0)
        revenue = financial_data.get('revenue', 0)
        
        if revenue <= 0:
            return {'value': None, 'description': '营收数据无效'}
        
        turnover_rate = revenue / receivables if receivables > 0 else 0
        days = 365 / turnover_rate if turnover_rate > 0 else 365
        
        if days < 30:
            desc = f"回款极快: {days:.0f}天"
        elif days < 60:
            desc = f"回款较快: {days:.0f}天"
        elif days < 90:
            desc = f"回款正常: {days:.0f}天"
        elif days < 180:
            desc = f"回款较慢: {days:.0f}天"
        else:
            desc = f"回款很慢: {days:.0f}天，坏账风险"
        
        return {'value': days, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value <= 30:
            return 90.0
        elif value <= 60:
            return 75.0
        elif value <= 90:
            return 55.0
        elif value <= 180:
            return 35.0
        else:
            return 15.0


# ==================== 偿债能力指标 ====================

@auto_register
class OperatingCashFlowRatioIndicator(IndicatorBase):
    """经营现金流比率指标
    
    经营现金流 / 流动负债
    """
    name = "operating_cash_flow_ratio"
    display_name = "经营现金流比率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "经营现金流除以流动负债"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        operating_cf = financial_data.get('operating_cash_flow', 0)
        current_liabilities = financial_data.get('current_liabilities', 0)
        
        if current_liabilities <= 0:
            return {'value': None, 'description': '流动负债数据无效'}
        
        ratio = operating_cf / current_liabilities
        
        if ratio > 1.0:
            desc = f"现金流覆盖充裕: {ratio:.2f}倍"
        elif ratio > 0.5:
            desc = f"现金流覆盖良好: {ratio:.2f}倍"
        elif ratio > 0.2:
            desc = f"现金流覆盖一般: {ratio:.2f}倍"
        elif ratio > 0:
            desc = f"现金流覆盖不足: {ratio:.2f}倍"
        else:
            desc = f"经营现金流为负: {ratio:.2f}倍"
        
        return {'value': ratio, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 1.0:
            return 90.0
        elif value >= 0.5:
            return 70.0
        elif value >= 0.2:
            return 50.0
        elif value >= 0:
            return 30.0
        else:
            return 15.0


@auto_register
class InterestCoverageRatioIndicator(IndicatorBase):
    """利息保障倍数指标EBIT / 利息费用
    """
    name = "interest_coverage_ratio"
    display_name = "利息保障倍数"
    category = IndicatorCategory.FUNDAMENTAL
    description = "EBIT除以利息费用"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        ebit = financial_data.get('ebit', 0)
        interest_expense = financial_data.get('interest_expense', 0)
        
        if interest_expense <= 0:
            if ebit > 0:
                desc = "无利息支出，财务健康"
                return {'value': 100.0, 'description': desc}
            else:
                desc = "无利息支出"
                return {'value': 0.0, 'description': desc}
        
        ratio = ebit / interest_expense
        
        if ratio > 10:
            desc = f"利息保障极强: {ratio:.1f}倍"
        elif ratio > 5:
            desc = f"利息保障良好: {ratio:.1f}倍"
        elif ratio > 2:
            desc = f"利息保障适中: {ratio:.1f}倍"
        elif ratio > 1:
            desc = f"利息保障偏弱: {ratio:.1f}倍"
        else:
            desc = f"无法覆盖利息: {ratio:.1f}倍，偿债风险"
        
        return {'value': ratio, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 10:
            return 90.0
        elif value >= 5:
            return 75.0
        elif value >= 2:
            return 55.0
        elif value >= 1:
            return 35.0
        else:
            return 15.0


# ==================== 成长性指标 ====================

@auto_register
class ROEGrowthRateIndicator(IndicatorBase):
    """净资产收益率增长率指标
    
    ROE同比增长
    """
    name = "roe_growth_rate"
    display_name = "ROE增长率"
    category = IndicatorCategory.FUNDAMENTAL
    description = "净资产收益率同比增长"
    
    def calculate(self, financial_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if financial_data is None:
            return {'value': None, 'description': '数据不足'}
        
        current_roe = financial_data.get('roe', None)
        prev_roe = financial_data.get('roe_prev_year', None)
        
        if current_roe is None or prev_roe is None:
            return {'value': None, 'description': '历史数据不足'}
        
        if prev_roe == 0:
            if current_roe > 0:
                desc = "ROE由零转正"
                return {'value': 100.0, 'description': desc}
            else:
                desc = "ROE持续为零"
                return {'value': 0.0, 'description': desc}
        
        growth_rate = (current_roe - prev_roe) / abs(prev_roe) * 100
        
        if growth_rate > 30:
            desc = f"ROE大幅提升: +{growth_rate:.1f}%"
        elif growth_rate > 10:
            desc = f"ROE明显提升: +{growth_rate:.1f}%"
        elif growth_rate > 0:
            desc = f"ROE小幅提升: +{growth_rate:.1f}%"
        elif growth_rate > -10:
            desc = f"ROE小幅下降: {growth_rate:.1f}%"
        elif growth_rate > -30:
            desc = f"ROE明显下降: {growth_rate:.1f}%"
        else:
            desc = f"ROE大幅下降: {growth_rate:.1f}%"
        
        return {
            'value': growth_rate,
            'description': desc,
            'extra_data': {
                'current_roe': current_roe,
                'prev_roe': prev_roe
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value >= 30:
            return 90.0
        elif value >= 10:
            return 75.0
        elif value >= 0:
            return 60.0
        elif value >= -10:
            return 45.0
        elif value >= -30:
            return 30.0
        else:
            return 15.0


# ==================== 指标汇总 ====================

FUNDAMENTAL_EXTENDED_INDICATORS = [
    'ebitda_margin',
    'dividend_yield',
    'dividend_payout_ratio',
    'operating_profit_margin',
    'gross_margin_change',
    'rd_expense_ratio',
    'goodwill_ratio',
    'inventory_turnover_days',
    'receivable_turnover_days',
    'operating_cash_flow_ratio',
    'interest_coverage_ratio',
    'roe_growth_rate',
]


def get_all_fundamental_extended_indicators():
    """获取所有扩展基本面指标名称列表"""
    return FUNDAMENTAL_EXTENDED_INDICATORS.copy()