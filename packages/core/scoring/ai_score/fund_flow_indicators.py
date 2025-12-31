"""
高级资金流向指标计算模块
扩展AI评分系统的资金流向指标维度
"""
from typing import Dict, Any, List
from dataclasses import dataclass
import pandas as pd


@dataclass
class FundFlowIndicatorResult:
    """资金流向指标结果"""
    value: float
    signal: str  # 'inflow', 'outflow', 'neutral'
    strength: float  # 0-1
    description: str


class AdvancedFundFlowIndicators:
    """高级资金流向指标计算器"""

    @staticmethod
    def calculate_etf_flow_impact(stock_code: str, etf_flows: Dict[str, float]) -> FundFlowIndicatorResult:
        """
        ETF资金流向影响

        Args:
            stock_code: 股票代码
            etf_flows: ETF资金流向数据

        Returns:
            指标结果
        """
        total_flow = sum(etf_flows.values())
        flow_amount = total_flow / 100000000  # 转换为亿元

        if flow_amount > 5:
            signal = 'inflow'
            strength = min(flow_amount / 20, 1.0)
            desc = f"ETF大幅净流入 {flow_amount:.1f}亿"
        elif flow_amount > 1:
            signal = 'inflow'
            strength = flow_amount / 5
            desc = f"ETF净流入 {flow_amount:.1f}亿"
        elif flow_amount < -5:
            signal = 'outflow'
            strength = min(abs(flow_amount) / 20, 1.0)
            desc = f"ETF大幅净流出 {abs(flow_amount):.1f}亿"
        elif flow_amount < -1:
            signal = 'outflow'
            strength = abs(flow_amount) / 5
            desc = f"ETF净流出 {abs(flow_amount):.1f}亿"
        else:
            signal = 'neutral'
            strength = 0.2
            desc = "ETF资金流向平稳"

        return FundFlowIndicatorResult(
            value=flow_amount,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_qfii_holding_change(holding_data: Dict[str, Any]) -> FundFlowIndicatorResult:
        """
        QFII持仓变化

        Args:
            holding_data: 持仓数据

        Returns:
            指标结果
        """
        current_holding = holding_data.get('current_holding', 0)
        previous_holding = holding_data.get('previous_holding', 0)
        change_pct = (current_holding - previous_holding) / previous_holding * 100 if previous_holding > 0 else 0

        if change_pct > 20:
            signal = 'inflow'
            strength = min(change_pct / 50, 1.0)
            desc = f"QFII大幅增持 {change_pct:.1f}%"
        elif change_pct > 5:
            signal = 'inflow'
            strength = change_pct / 20
            desc = f"QFII增持 {change_pct:.1f}%"
        elif change_pct < -20:
            signal = 'outflow'
            strength = min(abs(change_pct) / 50, 1.0)
            desc = f"QFII大幅减持 {abs(change_pct):.1f}%"
        elif change_pct < -5:
            signal = 'outflow'
            strength = abs(change_pct) / 20
            desc = f"QFII减持 {abs(change_pct):.1f}%"
        else:
            signal = 'neutral'
            strength = 0.2
            desc = "QFII持仓稳定"

        return FundFlowIndicatorResult(
            value=change_pct,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_margin_trading_trend(margin_data: pd.Series) -> FundFlowIndicatorResult:
        """
        融资融券趋势

        Args:
            margin_data: 融资余额序列

        Returns:
            指标结果
        """
        # 计算5日变化率
        change_5d = (margin_data.iloc[-1] - margin_data.iloc[-6]) / margin_data.iloc[-6] * 100

        # 计算趋势强度
        trend_strength = abs(change_5d) / 10

        if change_5d > 5:
            signal = 'inflow'
            strength = min(trend_strength, 1.0)
            desc = f"融资余额快速增长 {change_5d:.1f}%"
        elif change_5d > 2:
            signal = 'inflow'
            strength = trend_strength / 2
            desc = f"融资余额增长 {change_5d:.1f}%"
        elif change_5d < -5:
            signal = 'outflow'
            strength = min(trend_strength, 1.0)
            desc = f"融资余额快速下降 {abs(change_5d):.1f}%"
        elif change_5d < -2:
            signal = 'outflow'
            strength = trend_strength / 2
            desc = f"融资余额下降 {abs(change_5d):.1f}%"
        else:
            signal = 'neutral'
            strength = 0.2
            desc = "融资余额稳定"

        return FundFlowIndicatorResult(
            value=change_5d,
            signal=signal,
            strength=strength,
            description=desc
        )