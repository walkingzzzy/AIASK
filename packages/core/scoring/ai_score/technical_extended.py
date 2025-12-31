"""
扩展技术指标计算模块
包含18个新增技术指标：斐波那契、动量、趋势、波动率等指标
"""
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
from dataclasses import dataclass

from .indicator_registry import (IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


#==================== 斐波那契相关指标 ====================

@auto_register
class FibonacciRetracementIndicator(IndicatorBase):
    """斐波那契回撤位指标
    
    计算0.236, 0.382, 0.5, 0.618, 0.786回撤位
    用于判断价格回调的潜在支撑位
    """
    name = "fibonacci_retracement"
    display_name = "斐波那契回撤位"
    category = IndicatorCategory.TECHNICAL
    description = "计算斐波那契回撤位，判断支撑阻力"
    LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None, 
                  close: pd.Series = None, period: int = 60, **kwargs) -> Dict[str, Any]:
        """计算斐波那契回撤位"""
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        period_high = high.tail(period).max()
        period_low = low.tail(period).min()
        current_price = close.iloc[-1]
        
        diff = period_high - period_low
        levels = {}
        for level in self.LEVELS:
            levels[f'fib_{int(level*1000)}'] = period_high - diff * level
        
        position = (period_high - current_price) / diff if diff > 0 else 0.5
        nearest_level = min(self.LEVELS, key=lambda x: abs(x - position))
        
        if position < 0.382:
            trend = "strong_bullish"
            desc = f"价格处于强势区域，回撤位: {position:.1%}"
        elif position < 0.5:
            trend = "bullish"
            desc = f"价格处于偏强区域，接近{nearest_level:.1%}回撤位"
        elif position < 0.618:
            trend = "neutral"
            desc = f"价格处于中性区域，接近{nearest_level:.1%}回撤位"
        else:
            trend = "bearish"
            desc = f"价格处于弱势区域，回撤{position:.1%}"
        
        return {
            'value': position,
            'description': desc,
            'extra_data': {
                'levels': levels,
                'period_high': period_high,
                'period_low': period_low,
                'current_price': current_price,
                'nearest_level': nearest_level,
                'trend': trend
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, (1 - value) * 100))


@auto_register
class FibonacciExtensionIndicator(IndicatorBase):
    """斐波那契扩展位指标
    
    计算1.0, 1.272, 1.618扩展位
    """
    name = "fibonacci_extension"
    display_name = "斐波那契扩展位"
    category = IndicatorCategory.TECHNICAL
    description = "计算斐波那契扩展位，判断上涨目标"
    EXTENSION_LEVELS = [1.0, 1.272, 1.618, 2.0, 2.618]
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 60, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        period_high = high.tail(period).max()
        period_low = low.tail(period).min()
        current_price = close.iloc[-1]
        
        diff = period_high - period_low
        extensions = {}
        for level in self.EXTENSION_LEVELS:
            extensions[f'ext_{int(level*1000)}'] = period_low + diff * level
        
        extension_ratio = (current_price - period_low) / diff if diff > 0 else 1.0
        
        if extension_ratio >=1.618:
            desc = f"价格已突破1.618扩展位，强势上涨"
        elif extension_ratio >= 1.272:
            desc = f"价格接近1.618扩展位，目标: {extensions['ext_1618']:.2f}"
        elif extension_ratio >= 1.0:
            desc = f"价格已突破前高，扩展比例: {extension_ratio:.2f}"
        else:
            desc = f"价格未突破前高，当前位置: {extension_ratio:.2f}"
        
        return {
            'value': extension_ratio,
            'description': desc,
            'extra_data': {'extensions': extensions}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 0.5:
            return 20.0
        elif value < 1.0:
            return 40 + (value - 0.5) * 40
        elif value < 1.618:
            return 60 + (value - 1.0) * 30
        else:
            return max(50, 90 - (value - 1.618) * 20)


@auto_register
class SupportDistanceIndicator(IndicatorBase):
    """支撑位距离指标"""
    name = "support_distance"
    display_name = "支撑位距离"
    category = IndicatorCategory.TECHNICAL
    description = "当前价与最近支撑位的距离"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 20, **kwargs) -> Dict[str, Any]:
        if low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        current_price = close.iloc[-1]
        recent_lows = []
        for i in range(2, min(len(low) - 1, period * 3)):
            if low.iloc[-i] < low.iloc[-i-1] and low.iloc[-i] < low.iloc[-i+1]:
                recent_lows.append(low.iloc[-i])
        
        if not recent_lows:
            support = low.tail(period).min()
        else:
            valid_supports = [s for s in recent_lows if s < current_price]
            support = max(valid_supports) if valid_supports else min(recent_lows)
        
        distance_pct = (current_price - support) / support * 100 if support > 0 else 0
        
        if distance_pct < 2:
            desc = f"接近支撑位，距离{distance_pct:.1f}%"
        elif distance_pct < 5:
            desc = f"略高于支撑位，距离{distance_pct:.1f}%"
        else:
            desc = f"远离支撑位，距离{distance_pct:.1f}%"
        
        return {
            'value': distance_pct,
            'description': desc,
            'extra_data': {'support_level': support}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 2:
            return 80 + (2 - value) * 10
        elif value < 5:
            return 60 + (5 - value) / 3* 20
        else:
            return max(20, 60 - (value - 5) * 4)


@auto_register
class ResistanceDistanceIndicator(IndicatorBase):
    """阻力位距离指标"""
    name = "resistance_distance"
    display_name = "阻力位距离"
    category = IndicatorCategory.TECHNICAL
    description = "当前价与最近阻力位的距离"
    
    def calculate(self, high: pd.Series = None, close: pd.Series = None,
                  period: int = 20, **kwargs) -> Dict[str, Any]:
        if high is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        current_price = close.iloc[-1]
        recent_highs = []
        for i in range(2, min(len(high) - 1, period * 3)):
            if high.iloc[-i] > high.iloc[-i-1] and high.iloc[-i] > high.iloc[-i+1]:
                recent_highs.append(high.iloc[-i])
        
        if not recent_highs:
            resistance = high.tail(period).max()
        else:
            valid_resistances = [r for r in recent_highs if r > current_price]
            resistance = min(valid_resistances) if valid_resistances else max(recent_highs)
        
        distance_pct = (resistance - current_price) / current_price * 100 if current_price > 0 else 0
        desc = f"距阻力位{distance_pct:.1f}%，上涨空间"
        
        return {
            'value': distance_pct,
            'description': desc,
            'extra_data': {'resistance_level': resistance}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 2:
            return 30 + value * 10
        elif value < 10:
            return 50 + (value - 2) * 5
        else:
            return min(95, 90)


# ==================== 动量指标 ====================

@auto_register
class MomentumIndicator(IndicatorBase):
    """Momentum动量指标"""
    name = "momentum"
    display_name = "动量指标"
    category = IndicatorCategory.TECHNICAL
    description = "价格动量，反映趋势强度"
    
    def calculate(self, close: pd.Series = None, period: int = 10, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period + 1:
            return {'value': None, 'description': '数据不足'}
        
        momentum_pct = (close.iloc[-1] - close.iloc[-period-1]) / close.iloc[-period-1] * 100
        
        if momentum_pct > 5:
            desc = f"强劲上涨动量 (+{momentum_pct:.1f}%)"
        elif momentum_pct > 0:
            desc = f"正向动量 (+{momentum_pct:.1f}%)"
        elif momentum_pct > -5:
            desc = f"负向动量 ({momentum_pct:.1f}%)"
        else:
            desc = f"强劲下跌动量 ({momentum_pct:.1f}%)"
        
        return {'value': momentum_pct, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value * 5))


@auto_register
class ROCIndicator(IndicatorBase):
    """ROC变化率指标"""
    name = "roc"
    display_name = "变化率ROC"
    category = IndicatorCategory.TECHNICAL
    description = "价格变化率"
    
    def calculate(self, close: pd.Series = None, period: int = 12, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period + 1:
            return {'value': None, 'description': '数据不足'}
        
        roc = (close.iloc[-1] - close.iloc[-period-1]) / close.iloc[-period-1] * 100
        desc = f"ROC: {roc:.2f}%"
        
        return {'value': roc, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value * 4))


@auto_register
class CCIIndicator(IndicatorBase):
    """CCI商品通道指数"""
    name = "cci"
    display_name = "商品通道指数CCI"
    category = IndicatorCategory.TECHNICAL
    description = "CCI指标，判断超买超卖"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 20, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        tp = (high + low + close) / 3
        tp_ma = tp.rolling(period).mean()
        mean_dev = tp.rolling(period).apply(lambda x: np.mean(np.abs(x - x.mean())))
        cci = (tp - tp_ma) / (0.015 * mean_dev)
        current_cci = cci.iloc[-1]
        
        if current_cci > 100:
            desc = f"超买区域(CCI: {current_cci:.0f})"
        elif current_cci > -100:
            desc = f"正常区域 (CCI: {current_cci:.0f})"
        else:
            desc = f"超卖区域 (CCI: {current_cci:.0f})"
        
        return {'value': current_cci, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < -100:
            return min(85, 70 + (-value - 100) / 10)
        elif value > 100:
            return max(15, 30 - (value - 100) / 10)
        else:
            return 50 + value / 5


# ==================== 趋势指标 ====================

@auto_register
class SARIndicator(IndicatorBase):
    """SAR抛物线指标"""
    name = "sar"
    display_name = "抛物线SAR"
    category = IndicatorCategory.TECHNICAL
    description = "SAR指标，判断趋势反转点"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, af_start: float = 0.02, 
                  af_max: float = 0.2, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None or len(close) < 5:
            return {'value': None, 'description': '数据不足'}
        
        # 简化SAR计算
        n = len(close)
        trend = 1 if close.iloc[-1] > close.iloc[-5] else -1
        
        if trend == 1:
            sar_value = low.tail(5).min()
        else:
            sar_value = high.tail(5).max()
        
        current_price = close.iloc[-1]
        distance_pct = abs(current_price - sar_value) / current_price * 100
        
        if trend == 1:
            desc = f"上涨趋势，SAR支撑: {sar_value:.2f}"
        else:
            desc = f"下跌趋势，SAR阻力: {sar_value:.2f}"
        
        return {
            'value': trend,
            'description': desc,
            'extra_data': {'sar_value': sar_value, 'distance_pct': distance_pct}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return 70.0 if value == 1 else 30.0


@auto_register
class ADXIndicator(IndicatorBase):
    """ADX平均趋向指数"""
    name = "adx"
    display_name = "平均趋向指数ADX"
    category = IndicatorCategory.TECHNICAL
    description = "ADX指标，衡量趋势强度"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 14, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None or len(close) < period * 2:
            return {'value': None, 'description': '数据不足'}
        
        high_diff = high.diff()
        low_diff = -low.diff()
        
        plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0), index=high.index)
        minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0), index=low.index)
        
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = plus_dm.rolling(period).mean() / atr * 100
        minus_di = minus_dm.rolling(period).mean() / atr * 100
        
        dx = abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001) * 100
        adx = dx.rolling(period).mean()
        
        current_adx = adx.iloc[-1]
        
        if current_adx > 40:
            desc = f"强趋势 (ADX: {current_adx:.1f})"
        elif current_adx > 25:
            desc = f"中等趋势 (ADX: {current_adx:.1f})"
        else:
            desc = f"弱趋势或盘整 (ADX: {current_adx:.1f})"
        
        return {
            'value': current_adx,
            'description': desc,
            'extra_data': {
                'plus_di': plus_di.iloc[-1],
                'minus_di': minus_di.iloc[-1]
            }
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 40:
            return 75.0
        elif value > 25:
            return 60.0
        else:
            return 45.0


@auto_register
class DMIIndicator(IndicatorBase):
    """DMI动向指标"""
    name = "dmi"
    display_name = "动向指标DMI"
    category = IndicatorCategory.TECHNICAL
    description = "DMI指标，判断多空方向"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 14, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        high_diff = high.diff()
        low_diff = -low.diff()
        
        plus_dm = pd.Series(np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0), index=high.index)
        minus_dm = pd.Series(np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0), index=low.index)
        
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        atr = tr.ewm(span=period, adjust=False).mean()
        
        plus_di = plus_dm.ewm(span=period, adjust=False).mean() / atr * 100
        minus_di = minus_dm.ewm(span=period, adjust=False).mean() / atr * 100
        
        current_plus = plus_di.iloc[-1]
        current_minus = minus_di.iloc[-1]
        dmi_diff = current_plus - current_minus
        
        if dmi_diff > 10:
            desc = f"多头主导 (+DI: {current_plus:.1f}, -DI: {current_minus:.1f})"
        elif dmi_diff < -10:
            desc = f"空头主导 (+DI: {current_plus:.1f}, -DI: {current_minus:.1f})"
        else:
            desc = f"多空均衡 (+DI: {current_plus:.1f}, -DI: {current_minus:.1f})"
        
        return {
            'value': dmi_diff,
            'description': desc,
            'extra_data': {'plus_di': current_plus, 'minus_di': current_minus}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value))


@auto_register
class TRIXIndicator(IndicatorBase):
    """TRIX三重指数平滑平均"""
    name = "trix"
    display_name = "三重指数TRIX"
    category = IndicatorCategory.TECHNICAL
    description = "TRIX指标，过滤短期波动"
    
    def calculate(self, close: pd.Series = None, period: int = 12, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period * 3:
            return {'value': None, 'description': '数据不足'}
        ema1 = close.ewm(span=period, adjust=False).mean()
        ema2 = ema1.ewm(span=period, adjust=False).mean()
        ema3 = ema2.ewm(span=period, adjust=False).mean()
        
        trix = (ema3 - ema3.shift(1)) / ema3.shift(1) * 100
        current_trix = trix.iloc[-1]
        trix_ma = trix.rolling(9).mean().iloc[-1]
        
        if current_trix > trix_ma:
            signal = "金叉看多"
        else:
            signal = "死叉看空"
        
        desc = f"TRIX: {current_trix:.4f} ({signal})"
        
        return {
            'value': current_trix,
            'description': desc,
            'extra_data': {'trix_ma': trix_ma, 'signal': signal}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value * 100))


@auto_register
class EMVIndicator(IndicatorBase):
    """EMV简易波动指标"""
    name = "emv"
    display_name = "简易波动EMV"
    category = IndicatorCategory.TECHNICAL
    description = "EMV指标，结合成交量和价格波动"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  volume: pd.Series = None, period: int = 14, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or volume is None:
            return {'value': None, 'description': '数据不足'}
        
        mid_move = ((high + low) / 2) - ((high.shift(1) + low.shift(1)) / 2)
        box_ratio = (volume / 100000000) / (high - low + 0.0001)
        
        emv = mid_move / box_ratio
        emv_ma = emv.rolling(period).mean()
        
        current_emv = emv_ma.iloc[-1]
        
        if current_emv > 0:
            desc = f"EMV为正，上涨阻力小 ({current_emv:.2f})"
        else:
            desc = f"EMV为负，下跌压力大 ({current_emv:.2f})"
        
        return {'value': current_emv, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value * 2))


@auto_register
class WRVariantIndicator(IndicatorBase):
    """WR威廉指标变体"""
    name = "wr_variant"
    display_name = "威廉指标变体"
    category = IndicatorCategory.TECHNICAL
    description = "WR变体，多周期综合"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        # 计算多周期WR
        wr_10 = self._calc_wr(high, low, close, 10)
        wr_20 = self._calc_wr(high, low, close, 20)
        wr_60 = self._calc_wr(high, low, close, 60)
        
        # 加权平均
        avg_wr = wr_10 * 0.5 + wr_20 * 0.3 + wr_60 * 0.2
        
        if avg_wr > -20:
            desc = f"综合超买 (WR均值: {avg_wr:.1f})"
        elif avg_wr < -80:
            desc = f"综合超卖 (WR均值: {avg_wr:.1f})"
        else:
            desc = f"正常区间 (WR均值: {avg_wr:.1f})"
        
        return {
            'value': avg_wr,
            'description': desc,
            'extra_data': {'wr_10': wr_10, 'wr_20': wr_20, 'wr_60': wr_60}
        }
    
    def _calc_wr(self, high, low, close, period):
        hh = high.rolling(period).max()
        ll = low.rolling(period).min()
        wr = -100 * (hh - close) / (hh - ll + 0.0001)
        return wr.iloc[-1]
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # WR为-100到0，-80以下超卖，-20以上超买
        if value < -80:
            return 80 + (-80 - value) / 2
        elif value > -20:
            return 20 - (value + 20) / 2
        else:
            return 50 - value / 1.2


@auto_register
class BIASIndicator(IndicatorBase):
    """BIAS乖离率指标"""
    name = "bias"
    display_name = "乖离率BIAS"
    category = IndicatorCategory.TECHNICAL
    description = "价格与均线的偏离程度"
    
    def calculate(self, close: pd.Series = None, period: int = 20, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period:
            return {'value': None, 'description': '数据不足'}
        
        ma = close.rolling(period).mean()
        bias = (close - ma) / ma * 100
        current_bias = bias.iloc[-1]
        
        if current_bias > 10:
            desc = f"严重超买，乖离率: +{current_bias:.2f}%"
        elif current_bias > 5:
            desc = f"轻度超买，乖离率: +{current_bias:.2f}%"
        elif current_bias > -5:
            desc = f"正常区间，乖离率: {current_bias:+.2f}%"
        elif current_bias > -10:
            desc = f"轻度超卖，乖离率: {current_bias:.2f}%"
        else:
            desc = f"严重超卖，乖离率: {current_bias:.2f}%"
        
        return {'value': current_bias, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # 乖离率为负表示超卖（看多），为正表示超买（看空）
        if value < -10:
            return 90
        elif value > 10:
            return 10
        else:
            return 50 - value * 4


@auto_register
class PSYIndicator(IndicatorBase):
    """PSY心理线指标"""
    name = "psy"
    display_name = "心理线PSY"
    category = IndicatorCategory.TECHNICAL
    description = "多空心理指标"
    
    def calculate(self, close: pd.Series = None, period: int = 12, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period:
            return {'value': None, 'description': '数据不足'}
        
        # 计算上涨天数占比
        up_days = (close.diff() > 0).rolling(period).sum()
        psy = up_days / period * 100
        current_psy = psy.iloc[-1]
        
        if current_psy > 75:
            desc = f"极度乐观 (PSY: {current_psy:.1f})"
        elif current_psy > 50:
            desc = f"偏乐观 (PSY: {current_psy:.1f})"
        elif current_psy > 25:
            desc = f"偏悲观 (PSY: {current_psy:.1f})"
        else:
            desc = f"极度悲观 (PSY: {current_psy:.1f})"
        
        return {'value': current_psy, 'description': desc}
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        # PSY低于25超卖看多，高于75超买看空
        if value < 25:
            return 80 + (25 - value)
        elif value > 75:
            return 20 - (value - 75)
        else:
            return 50 + (50 - value) * 0.6


@auto_register
class VRIndicator(IndicatorBase):
    """VR容量比率指标"""
    name = "vr"
    display_name = "容量比率VR"
    category = IndicatorCategory.TECHNICAL
    description = "成交量强弱指标"
    
    def calculate(self, close: pd.Series = None, volume: pd.Series = None,
                  period: int = 26, **kwargs) -> Dict[str, Any]:
        if close is None or volume is None or len(close) < period:
            return {'value': None, 'description': '数据不足'}
        
        price_change = close.diff()
        
        # 上涨日成交量
        up_volume = volume.where(price_change > 0, 0).rolling(period).sum()
        # 下跌日成交量
        down_volume = volume.where(price_change < 0, 0).rolling(period).sum()
        # 平盘日成交量
        flat_volume = volume.where(price_change == 0, 0).rolling(period).sum()
        
        vr = (up_volume + flat_volume / 2) / (down_volume + flat_volume / 2 + 0.0001) * 100
        current_vr = vr.iloc[-1]
        
        if current_vr > 350:
            desc = f"极度活跃，警惕回调 (VR: {current_vr:.0f})"
        elif current_vr > 160:
            desc = f"活跃，多头占优 (VR: {current_vr:.0f})"
        elif current_vr > 70:
            desc = f"正常区间 (VR: {current_vr:.0f})"
        elif current_vr > 40:
            desc = f"低迷，空头占优 (VR: {current_vr:.0f})"
        else:
            desc = f"极度低迷，或将反弹 (VR: {current_vr:.0f})"
        
        return {'value': current_vr, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 40:
            return 80  # 超卖
        elif value > 350:
            return 20  # 超买
        elif value < 70:
            return 70 - (70 - value)
        elif value > 160:
            return 50 - (value - 160) / 5
        else:
            return 50 + (value - 100) / 3


@auto_register
class ARBRIndicator(IndicatorBase):
    """ARBR人气意愿指标"""
    name = "arbr"
    display_name = "人气意愿ARBR"
    category = IndicatorCategory.TECHNICAL
    description = "AR人气指标和BR意愿指标"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  open_price: pd.Series = None, close: pd.Series = None,
                  period: int = 26, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        if open_price is None:
            open_price = close.shift(1)
        
        # AR = (H-O)之和 / (O-L)之和 * 100
        ar = (high - open_price).rolling(period).sum() / (open_price - low + 0.0001).rolling(period).sum() * 100
        
        # BR = (H-昨C)之和 / (昨C-L)之和 * 100
        prev_close = close.shift(1)
        br = (high - prev_close).clip(lower=0).rolling(period).sum() / (prev_close - low).clip(lower=0).rolling(period).sum() * 100
        
        current_ar = ar.iloc[-1]
        current_br = br.iloc[-1]
        
        if current_ar > 180 and current_br > 300:
            desc = f"极度超买 (AR: {current_ar:.0f}, BR: {current_br:.0f})"
        elif current_ar > 120 and current_br > 150:
            desc = f"偏多头 (AR: {current_ar:.0f}, BR: {current_br:.0f})"
        elif current_ar < 50 and current_br< 50:
            desc = f"极度超卖 (AR: {current_ar:.0f}, BR: {current_br:.0f})"
        else:
            desc = f"正常区间 (AR: {current_ar:.0f}, BR: {current_br:.0f})"
        
        # 返回AR和BR的综合值
        combined = (current_ar + current_br) / 2
        
        return {
            'value': combined,
            'description': desc,
            'extra_data': {'ar': current_ar, 'br': current_br}
        }
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 50:
            return 85  # 超卖看多
        elif value > 200:
            return 15  # 超买看空
        else:
            return 50 + (100 - value) / 3


@auto_register
class CRIndicator(IndicatorBase):
    """CR能量指标"""
    name = "cr"
    display_name = "能量指标CR"
    category = IndicatorCategory.TECHNICAL
    description = "CR中间意愿指标"
    
    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 26, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}
        
        # 中间价
        mid = (high + low + close) / 3
        prev_mid = mid.shift(1)
        
        # CR = (H-昨M)之和 / (昨M-L)之和 * 100
        up_power = (high - prev_mid).clip(lower=0).rolling(period).sum()
        down_power = (prev_mid - low).clip(lower=0).rolling(period).sum()
        
        cr = up_power / (down_power + 0.0001) * 100
        current_cr = cr.iloc[-1]
        
        if current_cr > 200:
            desc = f"强势超买 (CR: {current_cr:.0f})"
        elif current_cr > 100:
            desc = f"偏强势 (CR: {current_cr:.0f})"
        elif current_cr > 50:
            desc = f"正常区间 (CR: {current_cr:.0f})"
        elif current_cr > 20:
            desc = f"偏弱势 (CR: {current_cr:.0f})"
        else:
            desc = f"极度超卖 (CR: {current_cr:.0f})"
        
        return {'value': current_cr, 'description': desc}
    
    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value < 20:
            return 90  # 极度超卖
        elif value > 200:
            return 10  # 极度超买
        elif value < 50:
            return 70 + (50 - value)
        elif value > 100:
            return 50 - (value - 100) / 3
        else:
            return 50 + (80 - value) / 2


#==================== 指标汇总 ====================

# 技术指标列表
TECHNICAL_INDICATORS = [
    'fibonacci_retracement',
    'fibonacci_extension',
    'support_distance',
    'resistance_distance',
    'momentum',
    'roc',
    'cci',
    'sar',
    'adx',
    'dmi',
    'trix',
    'emv',
    'wr_variant',
    'bias',
    'psy',
    'vr',
    'arbr',
    'cr',
]


def get_all_technical_extended_indicators():
    """获取所有扩展技术指标名称列表"""
    return TECHNICAL_INDICATORS.copy()