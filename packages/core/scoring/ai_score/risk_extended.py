"""
扩展风险指标计算模块
包含2个新增风险指标：卡玛比率和最大连续亏损天数
"""
from typing import Dict, Any, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (IndicatorBase, IndicatorCategory, 
    auto_register, get_registry
)


@auto_register
class CalmarRatioIndicator(IndicatorBase):
    """卡玛比率指标
    
    年化收益率 / 最大回撤，衡量风险调整后收益
    """
    name = "calmar_ratio"
    display_name = "卡玛比率"
    category = IndicatorCategory.RISK
    description = "年化收益率除以最大回撤"
    
    def calculate(self, returns: pd.Series = None, close: pd.Series = None,
                  **kwargs) -> Dict[str, Any]:
        """计算卡玛比率"""
        if returns is None and close is not None:
            returns = close.pct_change().dropna()
        
        if returns is None or len(returns) < 20:
            return {'value': None, 'description': '数据不足'}
        
        # 计算累计收益
        cumulative = (1 + returns).cumprod()
        # 计算最大回撤
        rolling_max = cumulative.cummax()
        drawdowns = (cumulative - rolling_max) / rolling_max
        max_drawdown = abs(drawdowns.min())
        
        # 计算年化收益率
        total_return = cumulative.iloc[-1] - 1
        years = len(returns) / 252  # 假设252个交易日
        
        if years > 0 and total_return > -1:
            annualized_return = (1 + total_return) ** (1 / years) - 1
        else:
            annualized_return = total_return
        
        # 计算卡玛比率
        if max_drawdown > 0.001:
            calmar_ratio = annualized_return / max_drawdown
        else:
            calmar_ratio =10.0 if annualized_return > 0 else 0
        
        if calmar_ratio > 3:
            desc = f"卡玛比率优秀 ({calmar_ratio:.2f})"
        elif calmar_ratio > 1.5:
            desc = f"卡玛比率良好 ({calmar_ratio:.2f})"
        elif calmar_ratio > 0.5:
            desc = f"卡玛比率中等 ({calmar_ratio:.2f})"
        elif calmar_ratio > 0:
            desc = f"卡玛比率较低 ({calmar_ratio:.2f})"
        else:
            desc = f"卡玛比率为负 ({calmar_ratio:.2f})"
        
        return {
            'value': calmar_ratio,
            'description': desc,
            'extra_data': {
                'annualized_return': annualized_return,
                'max_drawdown': max_drawdown
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 3:
            return 90.0
        elif value > 1.5:
            return 75.0
        elif value > 0.5:
            return 55.0
        elif value > 0:
            return 40.0
        else:
            return 20.0


@auto_register
class MaxConsecutiveLossDaysIndicator(IndicatorBase):
    """最大连续亏损天数指标
    
    连续下跌的最大天数，衡量趋势风险
    """
    name = "max_consecutive_loss_days"
    display_name = "最大连续亏损天数"
    category = IndicatorCategory.RISK
    description = "连续下跌的最大天数"
    
    def calculate(self, returns: pd.Series = None, close: pd.Series = None,
                  **kwargs) -> Dict[str, Any]:
        """计算最大连续亏损天数"""
        if returns is None and close is not None:
            returns = close.pct_change().dropna()
        
        if returns is None or len(returns) < 10:
            return {'value': None, 'description': '数据不足'}
        
        # 标记是否为亏损日
        is_loss = returns < 0
        
        # 计算连续亏损天数
        consecutive_losses = []
        current_streak = 0
        
        for loss in is_loss:
            if loss:
                current_streak += 1
            else:
                if current_streak > 0:
                    consecutive_losses.append(current_streak)
                current_streak = 0
        
        # 别忘了最后一段
        if current_streak > 0:
            consecutive_losses.append(current_streak)
        
        max_consecutive_loss = max(consecutive_losses) if consecutive_losses else 0
        
        if max_consecutive_loss <= 3:
            desc = f"连续亏损天数较少 ({max_consecutive_loss}天)"
        elif max_consecutive_loss <= 5:
            desc = f"连续亏损天数可接受 ({max_consecutive_loss}天)"
        elif max_consecutive_loss <= 8:
            desc = f"连续亏损天数中等 ({max_consecutive_loss}天)"
        elif max_consecutive_loss <= 12:
            desc = f"连续亏损天数较多 ({max_consecutive_loss}天)"
        else:
            desc = f"连续亏损天数过多 ({max_consecutive_loss}天)"
        
        return {
            'value': max_consecutive_loss,
            'description': desc,
            'extra_data': {
                'total_loss_days': sum(is_loss),
                'total_days': len(returns)
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 连续亏损天数越少越好
        if value <= 3:
            return 90.0
        elif value <= 5:
            return 75.0
        elif value <= 8:
            return 55.0
        elif value <= 12:
            return 40.0
        else:
            return 20.0


#==================== 风险指标汇总 ====================

RISK_EXTENDED_INDICATORS = [
    'calmar_ratio',
    'max_consecutive_loss_days',
]


def get_all_risk_extended_indicators():
    """获取所有扩展风险指标名称列表"""
    return RISK_EXTENDED_INDICATORS.copy()