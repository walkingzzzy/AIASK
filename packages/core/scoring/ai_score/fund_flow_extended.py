"""
扩展资金流向指标计算模块
包含6个新增资金面指标：机构持仓、解禁压力、资金控盘等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class SocialSecurityHoldingChangeIndicator(IndicatorBase):
    """社保基金持仓变化指标
    
    社保基金持股比例变化，反映长期资金动向
    """
    name = "social_security_holding_change"
    display_name = "社保基金持仓变化"
    category = IndicatorCategory.FUND_FLOW
    description = "社保基金持股比例变化"
    
    def calculate(self, fund_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if fund_data is None:
            return {'value': None, 'description': '数据不足'}
        
        current_holding = fund_data.get('social_security_holding_pct', 0)
        prev_holding = fund_data.get('social_security_holding_pct_prev', 0)
        
        change = current_holding - prev_holding
        
        if change > 1:
            desc = f"社保基金大幅增持: +{change:.2f}pp"
            signal = "strong_bullish"
        elif change > 0.3:
            desc = f"社保基金增持: +{change:.2f}pp"
            signal = "bullish"
        elif change > -0.3:
            desc = f"社保基金持仓稳定: {change:+.2f}pp"
            signal = "neutral"
        elif change > -1:
            desc = f"社保基金减持: {change:.2f}pp"
            signal = "bearish"
        else:
            desc = f"社保基金大幅减持: {change:.2f}pp"
            signal = "strong_bearish"
        
        return {
            'value': change,
            'description': desc,
            'extra_data': {
                'current_holding': current_holding,
                'prev_holding': prev_holding,
                'signal': signal
            }
        }
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 1:
            return 90.0
        elif value > 0.3:
            return 75.0
        elif value > -0.3:
            return 55.0
        elif value > -1:
            return 35.0
        else:
            return 15.0


@auto_register
class ShareholderChangeIndicator(IndicatorBase):
    """股东增减持指标
    
    重要股东近期增减持情况
    """
    name = "shareholder_change"
    display_name = "股东增减持"
    category = IndicatorCategory.FUND_FLOW
    description = "重要股东近期增减持情况"
    
    def calculate(self, fund_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if fund_data is None:
            return {'value': None, 'description': '数据不足'}
        
        # 增持金额（正）和减持金额（负）
        increase_amount = fund_data.get('shareholder_increase_amount', 0)  # 万元
        decrease_amount = fund_data.get('shareholder_decrease_amount', 0)  # 万元
        
        net_amount = increase_amount - decrease_amount
        net_amount_yi = net_amount / 10000  # 转换为亿元
        
        if net_amount_yi > 1:
            desc = f"股东大幅净增持: {net_amount_yi:.2f}亿元"
            signal = "strong_bullish"
        elif net_amount_yi > 0.1:
            desc = f"股东净增持: {net_amount_yi:.2f}亿元"
            signal = "bullish"
        elif net_amount_yi > -0.1:
            desc = f"股东增减持平衡"
            signal = "neutral"
        elif net_amount_yi > -1:
            desc = f"股东净减持: {abs(net_amount_yi):.2f}亿元"
            signal = "bearish"
        else:
            desc = f"股东大幅净减持: {abs(net_amount_yi):.2f}亿元"
            signal = "strong_bearish"
        
        return {
            'value': net_amount_yi,
            'description': desc,
            'extra_data': {
                'increase_amount': increase_amount,
                'decrease_amount': decrease_amount,
                'signal': signal
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 1:
            return 85.0
        elif value > 0.1:
            return 70.0
        elif value > -0.1:
            return 50.0
        elif value > -1:
            return 30.0
        else:
            return 15.0


@auto_register
class LockupExpiryPressureIndicator(IndicatorBase):
    """限售股解禁压力指标
    
    近期解禁股份占流通股比例
    """
    name = "lockup_expiry_pressure"
    display_name = "限售股解禁压力"
    category = IndicatorCategory.FUND_FLOW
    description = "近期解禁股份占比"
    
    def calculate(self, fund_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if fund_data is None:
            return {'value': None, 'description': '数据不足'}
        
        # 未来30天解禁股份数
        upcoming_unlock_shares = fund_data.get('upcoming_unlock_shares', 0)
        circulating_shares = fund_data.get('circulating_shares', 1)
        
        if circulating_shares <= 0:
            return {'value': None, 'description': '流通股数据无效'}
        
        unlock_ratio = upcoming_unlock_shares / circulating_shares * 100
        
        if unlock_ratio > 20:
            desc = f"解禁压力极大: {unlock_ratio:.1f}%"
            risk_level = "high"
        elif unlock_ratio > 10:
            desc = f"解禁压力较大: {unlock_ratio:.1f}%"
            risk_level = "medium_high"
        elif unlock_ratio > 5:
            desc = f"解禁压力中等: {unlock_ratio:.1f}%"
            risk_level = "medium"
        elif unlock_ratio > 1:
            desc = f"解禁压力较小: {unlock_ratio:.1f}%"
            risk_level = "low"
        else:
            desc = f"几乎无解禁压力: {unlock_ratio:.1f}%"
            risk_level = "very_low"
        
        return {
            'value': unlock_ratio,
            'description': desc,
            'extra_data': {
                'upcoming_unlock_shares': upcoming_unlock_shares,
                'circulating_shares': circulating_shares,
                'risk_level': risk_level
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 解禁压力越小，分数越高
        if value > 20:
            return 15.0
        elif value > 10:
            return 30.0
        elif value > 5:
            return 50.0
        elif value > 1:
            return 70.0
        else:
            return 85.0


@auto_register
class LargeOrderNetInflowRatioIndicator(IndicatorBase):
    """大单净流入比指标
    
    大单净流入/ 成交额
    """
    name = "large_order_net_inflow_ratio"
    display_name = "大单净流入比"
    category = IndicatorCategory.FUND_FLOW
    description = "大单净流入占成交额比例"
    
    def calculate(self, fund_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if fund_data is None:
            return {'value': None, 'description': '数据不足'}
        
        large_order_inflow = fund_data.get('large_order_inflow', 0)
        large_order_outflow = fund_data.get('large_order_outflow', 0)
        total_turnover = fund_data.get('total_turnover', 1)
        
        if total_turnover <= 0:
            return {'value': None, 'description': '成交额数据无效'}
        
        net_inflow = large_order_inflow - large_order_outflow
        ratio = net_inflow / total_turnover * 100
        
        if ratio > 10:
            desc = f"大单大幅净流入: +{ratio:.1f}%"
            signal = "strong_bullish"
        elif ratio > 3:
            desc = f"大单净流入: +{ratio:.1f}%"
            signal = "bullish"
        elif ratio > -3:
            desc = f"大单流向平衡: {ratio:+.1f}%"
            signal = "neutral"
        elif ratio > -10:
            desc = f"大单净流出: {ratio:.1f}%"
            signal = "bearish"
        else:
            desc = f"大单大幅净流出: {ratio:.1f}%"
            signal = "strong_bearish"
        
        return {
            'value': ratio,
            'description': desc,
            'extra_data': {
                'net_inflow': net_inflow,
                'signal': signal
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 10:
            return 90.0
        elif value > 3:
            return 70.0
        elif value > -3:
            return 50.0
        elif value > -10:
            return 30.0
        else:
            return 10.0


@auto_register
class SuperLargeOrderNetInflowRatioIndicator(IndicatorBase):
    """超大单净流入比指标
    
    超大单净流入 / 成交额
    """
    name = "super_large_order_net_inflow_ratio"
    display_name = "超大单净流入比"
    category = IndicatorCategory.FUND_FLOW
    description = "超大单净流入占成交额比例"
    
    def calculate(self, fund_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        if fund_data is None:
            return {'value': None, 'description': '数据不足'}
        
        super_large_inflow = fund_data.get('super_large_order_inflow', 0)
        super_large_outflow = fund_data.get('super_large_order_outflow', 0)
        total_turnover = fund_data.get('total_turnover', 1)
        
        if total_turnover <= 0:
            return {'value': None, 'description': '成交额数据无效'}
        
        net_inflow = super_large_inflow - super_large_outflow
        ratio = net_inflow / total_turnover * 100
        
        if ratio > 8:
            desc = f"超大单大幅净流入: +{ratio:.1f}%，主力资金积极"
            signal = "strong_bullish"
        elif ratio > 2:
            desc = f"超大单净流入: +{ratio:.1f}%"
            signal = "bullish"
        elif ratio > -2:
            desc = f"超大单流向平衡: {ratio:+.1f}%"
            signal = "neutral"
        elif ratio > -8:
            desc = f"超大单净流出: {ratio:.1f}%"
            signal = "bearish"
        else:
            desc = f"超大单大幅净流出: {ratio:.1f}%，主力资金撤退"
            signal = "strong_bearish"
        
        return {
            'value': ratio,
            'description': desc,
            'extra_data': {
                'net_inflow': net_inflow,
                'signal': signal
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 8:
            return 92.0
        elif value > 2:
            return 72.0
        elif value > -2:
            return 50.0
        elif value > -8:
            return 28.0
        else:
            return 8.0


@auto_register
class MainForceControlIndicator(IndicatorBase):
    """主力控盘度指标
    
    主力资金控制程度
    """
    name = "main_force_control"
    display_name = "主力控盘度"
    category = IndicatorCategory.FUND_FLOW
    description = "主力资金控制程度"
    
    def calculate(self, fund_data: Dict[str, Any] = None,
                  volume_data: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if fund_data is None:
            return {'value': None, 'description': '数据不足'}
        
        # 方法1：基于机构持股比例
        institution_holding = fund_data.get('institution_holding_pct', 0)
        top10_holding = fund_data.get('top10_holder_pct', 0)
        
        # 方法2：基于成交量分析（如果有数据）
        if volume_data is not None and len(volume_data) >= 20:
            # 计算成交量集中度
            vol_std = volume_data.tail(20).std()
            vol_mean = volume_data.tail(20).mean()
            vol_cv = vol_std / vol_mean if vol_mean > 0 else 0
            volume_control = max(0, 1 - vol_cv) * 100
        else:
            volume_control = None
        
        # 综合控盘度
        if volume_control is not None:
            control_score = (institution_holding * 0.4 + 
                top10_holding * 0.3 + 
                            volume_control * 0.3)
        else:
            control_score = (institution_holding * 0.6 + top10_holding * 0.4)
        
        if control_score > 70:
            desc = f"高度控盘: {control_score:.1f}%"
            level = "high"
        elif control_score > 50:
            desc = f"中度控盘: {control_score:.1f}%"
            level = "medium"
        elif control_score > 30:
            desc = f"低度控盘: {control_score:.1f}%"
            level = "low"
        else:
            desc = f"筹码分散: {control_score:.1f}%"
            level = "dispersed"
        
        return {
            'value': control_score,
            'description': desc,
            'extra_data': {
                'institution_holding': institution_holding,
                'top10_holding': top10_holding,
                'volume_control': volume_control,
                'level': level
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 适度控盘（40-60）最佳
        if 40 <= value <= 60:
            return 75.0
        elif 30 <= value< 40 or 60 < value <= 70:
            return 65.0
        elif value > 70:
            return 50.0  # 过度控盘可能有操纵风险
        elif value > 20:
            return 45.0
        else:
            return 35.0  # 筹码过于分散


#==================== 指标汇总 ====================

FUND_FLOW_EXTENDED_INDICATORS = [
    'social_security_holding_change',
    'shareholder_change',
    'lockup_expiry_pressure',
    'large_order_net_inflow_ratio',
    'super_large_order_net_inflow_ratio',
    'main_force_control',
]


def get_all_fund_flow_extended_indicators():
    """获取所有扩展资金面指标名称列表"""
    return FUND_FLOW_EXTENDED_INDICATORS.copy()