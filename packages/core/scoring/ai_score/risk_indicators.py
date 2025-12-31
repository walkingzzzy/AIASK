"""
高级风险指标计算模块
扩展AI评分系统的风险指标维度
"""
from typing import Dict, Any
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class RiskIndicatorResult:
    """风险指标结果"""
    value: float
    risk_level: str  # 'low', 'medium', 'high'
    score: float  # 0-10分，风险越低分数越高
    description: str


class AdvancedRiskIndicators:
    """高级风险指标计算器"""

    @staticmethod
    def calculate_downside_deviation(returns: pd.Series, target_return: float = 0) -> RiskIndicatorResult:
        """
        下行偏差 - 只考虑负收益的波动

        Args:
            returns: 收益率序列
            target_return: 目标收益率

        Returns:
            指标结果
        """
        downside_returns = returns[returns < target_return]
        downside_dev = np.sqrt(np.mean(downside_returns ** 2))

        if downside_dev < 0.015:
            risk_level = 'low'
            score = 9.0
            desc = f"下行风险低 ({downside_dev*100:.2f}%)"
        elif downside_dev < 0.025:
            risk_level = 'medium'
            score = 6.0
            desc = f"下行风险中等 ({downside_dev*100:.2f}%)"
        else:
            risk_level = 'high'
            score = 3.0
            desc = f"下行风险高 ({downside_dev*100:.2f}%)"

        return RiskIndicatorResult(
            value=downside_dev,
            risk_level=risk_level,
            score=score,
            description=desc
        )

    @staticmethod
    def calculate_var(returns: pd.Series, confidence: float = 0.95) -> RiskIndicatorResult:
        """
        VaR (Value at Risk) - 在险价值

        Args:
            returns: 收益率序列
            confidence: 置信水平

        Returns:
            指标结果
        """
        var = np.percentile(returns, (1 - confidence) * 100)

        if var > -0.03:
            risk_level = 'low'
            score = 9.0
            desc = f"VaR风险低 ({var*100:.2f}%)"
        elif var > -0.05:
            risk_level = 'medium'
            score = 6.0
            desc = f"VaR风险中等 ({var*100:.2f}%)"
        else:
            risk_level = 'high'
            score = 3.0
            desc = f"VaR风险高 ({var*100:.2f}%)"

        return RiskIndicatorResult(
            value=var,
            risk_level=risk_level,
            score=score,
            description=desc
        )

    @staticmethod
    def calculate_cvar(returns: pd.Series, confidence: float = 0.95) -> RiskIndicatorResult:
        """
        CVaR (Conditional VaR) - 条件在险价值

        Args:
            returns: 收益率序列
            confidence: 置信水平

        Returns:
            指标结果
        """
        var = np.percentile(returns, (1 - confidence) * 100)
        cvar = returns[returns <= var].mean()

        if cvar > -0.04:
            risk_level = 'low'
            score = 9.0
            desc = f"CVaR风险低 ({cvar*100:.2f}%)"
        elif cvar > -0.07:
            risk_level = 'medium'
            score = 6.0
            desc = f"CVaR风险中等 ({cvar*100:.2f}%)"
        else:
            risk_level = 'high'
            score = 3.0
            desc = f"CVaR风险高 ({cvar*100:.2f}%)"

        return RiskIndicatorResult(
            value=cvar,
            risk_level=risk_level,
            score=score,
            description=desc
        )

    @staticmethod
    def calculate_information_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> RiskIndicatorResult:
        """
        信息比率 - 超额收益/跟踪误差

        Args:
            returns: 收益率序列
            benchmark_returns: 基准收益率序列

        Returns:
            指标结果
        """
        excess_returns = returns - benchmark_returns
        ir = excess_returns.mean() / excess_returns.std() if excess_returns.std() > 0 else 0

        if ir > 0.5:
            risk_level = 'low'
            score = 9.0
            desc = f"信息比率优秀 ({ir:.2f})"
        elif ir > 0:
            risk_level = 'medium'
            score = 6.0
            desc = f"信息比率良好 ({ir:.2f})"
        else:
            risk_level = 'high'
            score = 3.0
            desc = f"信息比率较差 ({ir:.2f})"

        return RiskIndicatorResult(
            value=ir,
            risk_level=risk_level,
            score=score,
            description=desc
        )