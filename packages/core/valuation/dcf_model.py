"""
DCF现金流折现估值模型
"""
from typing import Dict, Any, List
from dataclasses import dataclass
import numpy as np


@dataclass
class DCFResult:
    """DCF估值结果"""
    intrinsic_value: float  # 内在价值
    current_price: float  # 当前价格
    upside_potential: float  # 上涨空间 (%)
    wacc: float  # 加权平均资本成本
    terminal_value: float  # 终值
    fcf_projections: List[float]  # 自由现金流预测
    valuation_signal: str  # 估值信号: undervalued/fairly_valued/overvalued


class DCFValuation:
    """DCF估值模型"""

    def __init__(self):
        self.projection_years = 5  # 预测年限
        self.terminal_growth_rate = 0.03  # 永续增长率

    def calculate_dcf(
        self,
        financial_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> DCFResult:
        """
        计算DCF估值

        Args:
            financial_data: 财务数据
            market_data: 市场数据

        Returns:
            DCF估值结果

        Raises:
            ValueError: 当 wacc <= terminal_growth_rate 时
        """
        # 1. 计算WACC
        wacc = self._calculate_wacc(financial_data, market_data)

        # 验证: wacc 必须大于 terminal_growth_rate，否则终值计算会除零或为负
        if wacc <= self.terminal_growth_rate:
            raise ValueError(
                f"WACC ({wacc:.2%}) 必须大于永续增长率 ({self.terminal_growth_rate:.2%})，"
                f"否则无法计算终值"
            )

        # 2. 预测未来自由现金流
        fcf_projections = self._project_fcf(financial_data)

        # 3. 计算现值
        pv_fcf = self._calculate_present_value(fcf_projections, wacc)

        # 4. 计算终值
        terminal_fcf = fcf_projections[-1] * (1 + self.terminal_growth_rate)
        terminal_value = terminal_fcf / (wacc - self.terminal_growth_rate)
        pv_terminal = terminal_value / ((1 + wacc) ** self.projection_years)

        # 5. 计算企业价值和股权价值
        enterprise_value = pv_fcf + pv_terminal
        equity_value = enterprise_value - financial_data.get('net_debt', 0)

        # 6. 计算每股内在价值
        shares_outstanding = financial_data.get('shares_outstanding', 1)
        intrinsic_value = equity_value / shares_outstanding

        # 7. 计算上涨空间
        current_price = market_data.get('current_price', intrinsic_value)
        upside_potential = (intrinsic_value - current_price) / current_price * 100

        # 8. 估值信号
        if upside_potential > 20:
            signal = 'undervalued'
        elif upside_potential < -20:
            signal = 'overvalued'
        else:
            signal = 'fairly_valued'

        return DCFResult(
            intrinsic_value=intrinsic_value,
            current_price=current_price,
            upside_potential=upside_potential,
            wacc=wacc,
            terminal_value=terminal_value,
            fcf_projections=fcf_projections,
            valuation_signal=signal
        )

    def _calculate_wacc(
        self,
        financial_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> float:
        """
        计算加权平均资本成本 (WACC)
        WACC = (E/V) * Re + (D/V) * Rd * (1 - Tc)
        """
        # 权益成本 (使用CAPM)
        risk_free_rate = market_data.get('risk_free_rate', 0.03)
        beta = market_data.get('beta', 1.0)
        market_return = market_data.get('market_return', 0.10)
        cost_of_equity = risk_free_rate + beta * (market_return - risk_free_rate)

        # 债务成本
        interest_expense = financial_data.get('interest_expense', 0)
        total_debt = financial_data.get('total_debt', 1)
        cost_of_debt = interest_expense / total_debt if total_debt > 0 else 0.05

        # 税率
        tax_rate = financial_data.get('tax_rate', 0.25)

        # 权益和债务比例
        market_cap = market_data.get('market_cap', 1)
        total_value = market_cap + total_debt
        equity_weight = market_cap / total_value
        debt_weight = total_debt / total_value

        # WACC
        wacc = (equity_weight * cost_of_equity +
                debt_weight * cost_of_debt * (1 - tax_rate))

        return wacc

    def _project_fcf(self, financial_data: Dict[str, Any]) -> List[float]:
        """预测未来自由现金流"""
        # 历史FCF
        historical_fcf = financial_data.get('free_cash_flow', 0)

        # 增长率（基于历史增长或行业平均）
        fcf_growth_rate = financial_data.get('fcf_growth_rate', 0.10)

        # 预测未来FCF
        projections = []
        current_fcf = historical_fcf

        for year in range(1, self.projection_years + 1):
            # 逐年递减增长率
            adjusted_growth = fcf_growth_rate * (1 - 0.1 * (year - 1))
            current_fcf = current_fcf * (1 + adjusted_growth)
            projections.append(current_fcf)

        return projections

    def _calculate_present_value(
        self,
        cash_flows: List[float],
        discount_rate: float
    ) -> float:
        """计算现值"""
        pv = 0
        for year, cf in enumerate(cash_flows, start=1):
            pv += cf / ((1 + discount_rate) ** year)
        return pv


class RelativeValuation:
    """相对估值模型"""

    def calculate_relative_valuation(
        self,
        stock_data: Dict[str, Any],
        industry_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        计算相对估值

        Args:
            stock_data: 个股数据
            industry_data: 行业数据

        Returns:
            相对估值结果
        """
        results = {}

        # PE估值
        pe = stock_data.get('pe', 0)
        industry_pe = industry_data.get('avg_pe', pe)
        pe_discount = (pe - industry_pe) / industry_pe * 100 if industry_pe > 0 else 0

        results['pe'] = {
            'value': pe,
            'industry_avg': industry_pe,
            'discount': pe_discount,
            'signal': 'undervalued' if pe_discount < -20 else 'overvalued' if pe_discount > 20 else 'fairly_valued'
        }

        # PB估值
        pb = stock_data.get('pb', 0)
        industry_pb = industry_data.get('avg_pb', pb)
        pb_discount = (pb - industry_pb) / industry_pb * 100 if industry_pb > 0 else 0

        results['pb'] = {
            'value': pb,
            'industry_avg': industry_pb,
            'discount': pb_discount,
            'signal': 'undervalued' if pb_discount < -20 else 'overvalued' if pb_discount > 20 else 'fairly_valued'
        }

        # PS估值
        ps = stock_data.get('ps', 0)
        industry_ps = industry_data.get('avg_ps', ps)
        ps_discount = (ps - industry_ps) / industry_ps * 100 if industry_ps > 0 else 0

        results['ps'] = {
            'value': ps,
            'industry_avg': industry_ps,
            'discount': ps_discount,
            'signal': 'undervalued' if ps_discount < -20 else 'overvalued' if ps_discount > 20 else 'fairly_valued'
        }

        # 综合估值信号
        signals = [results['pe']['signal'], results['pb']['signal'], results['ps']['signal']]
        undervalued_count = signals.count('undervalued')
        overvalued_count = signals.count('overvalued')

        if undervalued_count >= 2:
            overall_signal = 'undervalued'
        elif overvalued_count >= 2:
            overall_signal = 'overvalued'
        else:
            overall_signal = 'fairly_valued'

        results['overall'] = {
            'signal': overall_signal,
            'confidence': max(undervalued_count, overvalued_count) / 3
        }

        return results