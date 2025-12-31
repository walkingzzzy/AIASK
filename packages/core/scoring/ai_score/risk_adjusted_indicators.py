"""
风险调整收益指标模块
包含：索提诺比率、Omega比率、尾部风险、动量质量、均值回归、流动性指标等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class SortinoRatioIndicator(IndicatorBase):
    """索提诺比率"""
    name = "sortino_ratio"
    display_name = "索提诺比率"
    category = IndicatorCategory.RISK
    description = "下行风险调整收益"

    def calculate(self, returns: pd.Series = None, risk_free_rate: float = 0.03, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        excess_returns = returns - risk_free_rate / 252
        downside_returns = excess_returns[excess_returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else 0.0001

        sortino = excess_returns.mean() / downside_std * np.sqrt(252)
        score = min(100, max(0, 50 + sortino * 10))
        desc = f"索提诺比率: {sortino:.2f}"
        return {'value': sortino, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, 50 + value * 10))


@auto_register
class OmegaRatioIndicator(IndicatorBase):
    """Omega比率"""
    name = "omega_ratio"
    display_name = "Omega比率"
    category = IndicatorCategory.RISK
    description = "收益概率加权比率"

    def calculate(self, returns: pd.Series = None, threshold: float = 0, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        gains = returns[returns > threshold].sum()
        losses = abs(returns[returns < threshold].sum())
        omega = gains / (losses + 0.0001)

        score = min(100, max(0, omega * 50))
        desc = f"Omega比率: {omega:.2f}"
        return {'value': omega, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, value * 50))


@auto_register
class TailRiskIndicator(IndicatorBase):
    """尾部风险指标"""
    name = "tail_risk"
    display_name = "尾部风险"
    category = IndicatorCategory.RISK
    description = "极端损失风险"

    def calculate(self, returns: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < 50:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        percentile_5 = returns.quantile(0.05)
        tail_risk = abs(percentile_5)

        if tail_risk < 0.02:
            score = 80
            desc = f"尾部风险低 ({tail_risk:.2%})"
        elif tail_risk < 0.05:
            score = 60
            desc = f"尾部风险中等 ({tail_risk:.2%})"
        else:
            score = 30
            desc = f"尾部风险高 ({tail_risk:.2%})"

        return {'value': tail_risk, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 0.02:
            return 80.0
        elif value < 0.05:
            return 60.0
        else:
            return 30.0


@auto_register
class MomentumQualityIndicator(IndicatorBase):
    """动量质量指标"""
    name = "momentum_quality"
    display_name = "动量质量"
    category = IndicatorCategory.TECHNICAL
    description = "动量的持续性和稳定性"

    def calculate(self, returns: pd.Series = None, period: int = 20, **kwargs) -> Dict[str, Any]:
        if returns is None or len(returns) < period:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        momentum = returns.rolling(period).sum().iloc[-1]
        consistency = (returns.rolling(period).apply(lambda x: (x > 0).sum() / len(x))).iloc[-1]

        quality = momentum * consistency
        score = min(100, max(0, 50 + quality * 500))
        desc = f"动量质量: {quality:.4f}"
        return {'value': quality, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return min(100, max(0, 50 + value * 500))


@auto_register
class MeanReversionIndicator(IndicatorBase):
    """均值回归指标"""
    name = "mean_reversion"
    display_name = "均值回归"
    category = IndicatorCategory.TECHNICAL
    description = "价格偏离均值程度"

    def calculate(self, close: pd.Series = None, period: int = 20, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        mean = close.rolling(period).mean().iloc[-1]
        std = close.rolling(period).std().iloc[-1]
        current = close.iloc[-1]

        z_score = (current - mean) / (std + 0.0001)

        if abs(z_score) > 2:
            score = 70
            desc = f"严重偏离均值 (Z={z_score:.2f})，可能回归"
        elif abs(z_score) > 1:
            score = 60
            desc = f"偏离均值 (Z={z_score:.2f})"
        else:
            score = 50
            desc = f"接近均值 (Z={z_score:.2f})"

        return {'value': z_score, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if abs(value) > 2:
            return 70.0
        elif abs(value) > 1:
            return 60.0
        else:
            return 50.0


@auto_register
class AmihudIlliquidityIndicator(IndicatorBase):
    """Amihud非流动性指标"""
    name = "amihud_illiquidity"
    display_name = "Amihud非流动性"
    category = IndicatorCategory.TECHNICAL
    description = "价格冲击成本"

    def calculate(self, returns: pd.Series = None, volume: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if returns is None or volume is None or len(returns) < 20:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        illiquidity = (abs(returns) / (volume + 1)).mean()

        if illiquidity < 0.0001:
            score = 85
            desc = f"流动性极佳 (Amihud={illiquidity:.6f})"
        elif illiquidity < 0.001:
            score = 65
            desc = f"流动性良好 (Amihud={illiquidity:.6f})"
        else:
            score = 40
            desc = f"流动性一般 (Amihud={illiquidity:.6f})"

        return {'value': illiquidity, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 0.0001:
            return 85.0
        elif value < 0.001:
            return 65.0
        else:
            return 40.0


@auto_register
class TurnoverVolatilityIndicator(IndicatorBase):
    """换手率波动指标"""
    name = "turnover_volatility"
    display_name = "换手率波动"
    category = IndicatorCategory.TECHNICAL
    description = "换手率稳定性"

    def calculate(self, turnover_rate: pd.Series = None, period: int = 20, **kwargs) -> Dict[str, Any]:
        if turnover_rate is None or len(turnover_rate) < period:
            return {'value': None, 'score': 50, 'description': '数据不足'}

        volatility = turnover_rate.rolling(period).std().iloc[-1]
        mean_turnover = turnover_rate.rolling(period).mean().iloc[-1]
        cv = volatility / (mean_turnover + 0.0001)

        if cv < 0.5:
            score = 75
            desc = f"换手率稳定 (CV={cv:.2f})"
        elif cv < 1.0:
            score = 55
            desc = f"换手率波动适中 (CV={cv:.2f})"
        else:
            score = 35
            desc = f"换手率波动大 (CV={cv:.2f})"

        return {'value': cv, 'score': score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 0.5:
            return 75.0
        elif value < 1.0:
            return 55.0
        else:
            return 35.0


# 指标列表
RISK_ADJUSTED_INDICATORS = [
    'sortino_ratio',
    'omega_ratio',
    'tail_risk',
    'momentum_quality',
    'mean_reversion',
    'amihud_illiquidity',
    'turnover_volatility',
]


def get_all_risk_adjusted_indicators():
    """获取所有风险调整指标名称列表"""
    return RISK_ADJUSTED_INDICATORS.copy()
