"""
补充技术面指标模块
包含：RSI背离、MACD背离、KDJ交叉、缺口分析、布林带宽度、OBV趋势、一目均衡云等
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from .indicator_registry import (
    IndicatorBase, IndicatorCategory, IndicatorResult,
    auto_register, get_registry
)


@auto_register
class RSISlopeIndicator(IndicatorBase):
    """RSI斜率指标

    计算RSI变化趋势，判断动量加速或减速
    """
    name = "rsi_slope"
    display_name = "RSI斜率"
    category = IndicatorCategory.TECHNICAL
    description = "RSI变化趋势，判断动量加速或减速"

    def calculate(self, close: pd.Series = None, period: int = 14,
                  slope_period: int = 5, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period + slope_period:
            return {'value': None, 'description': '数据不足'}

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / (loss + 0.0001)
        rsi = 100 - (100 / (1 + rs))

        rsi_slope = (rsi.iloc[-1] - rsi.iloc[-slope_period]) / slope_period

        if rsi_slope > 3:
            desc = f"RSI快速上升 (斜率: +{rsi_slope:.2f})"
            signal = "accelerating_bullish"
        elif rsi_slope > 1:
            desc = f"RSI温和上升 (斜率: +{rsi_slope:.2f})"
            signal = "bullish"
        elif rsi_slope > -1:
            desc = f"RSI横盘 (斜率: {rsi_slope:+.2f})"
            signal = "neutral"
        elif rsi_slope > -3:
            desc = f"RSI温和下降 (斜率: {rsi_slope:.2f})"
            signal = "bearish"
        else:
            desc = f"RSI快速下降 (斜率: {rsi_slope:.2f})"
            signal = "accelerating_bearish"

        return {
            'value': rsi_slope,
            'description': desc,
            'extra_data': {
                'current_rsi': rsi.iloc[-1],
                'signal': signal
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value * 8))


@auto_register
class RSIDivergenceIndicator(IndicatorBase):
    """RSI背离指标

    检测价格与RSI的顶背离和底背离
    """
    name = "rsi_divergence"
    display_name = "RSI背离"
    category = IndicatorCategory.TECHNICAL
    description = "检测价格与RSI的背离"

    def calculate(self, close: pd.Series = None, high: pd.Series = None,
                  low: pd.Series = None, period: int = 14,
                  lookback: int = 20, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period + lookback:
            return {'value': None, 'description': '数据不足'}

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / (loss + 0.0001)
        rsi = 100 - (100 / (1 + rs))

        price_data = close.tail(lookback)
        rsi_data = rsi.tail(lookback)

        price_trend = price_data.iloc[-1] - price_data.iloc[0]
        rsi_trend = rsi_data.iloc[-1] - rsi_data.iloc[0]

        divergence_score = 0
        if price_trend > 0 and rsi_trend < 0:
            divergence_score = -1
            desc = "顶背离：价格上涨但RSI走弱，警惕回调"
            signal = "bearish_divergence"
        elif price_trend < 0 and rsi_trend > 0:
            divergence_score = 1
            desc = "底背离：价格下跌但RSI走强，可能反弹"
            signal = "bullish_divergence"
        else:
            divergence_score = 0
            desc = "无明显背离"
            signal = "no_divergence"

        return {
            'value': divergence_score,
            'description': desc,
            'extra_data': {
                'price_trend': price_trend,
                'rsi_trend': rsi_trend,
                'signal': signal
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0:
            return 75.0
        elif value < 0:
            return 25.0
        else:
            return 50.0


@auto_register
class MACDDivergenceIndicator(IndicatorBase):
    """MACD背离指标

    检测价格与MACD的背离
    """
    name = "macd_divergence"
    display_name = "MACD背离"
    category = IndicatorCategory.TECHNICAL
    description = "检测价格与MACD的背离"

    def calculate(self, close: pd.Series = None, lookback: int = 30, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < lookback + 26:
            return {'value': None, 'description': '数据不足'}

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26

        price_data = close.tail(lookback)
        macd_data = macd.tail(lookback)

        price_trend = price_data.iloc[-1] - price_data.iloc[0]
        macd_trend = macd_data.iloc[-1] - macd_data.iloc[0]

        divergence_score = 0
        if price_trend > 0 and macd_trend < 0:
            divergence_score = -1
            desc = "MACD顶背离：价格上涨但MACD走弱"
            signal = "bearish_divergence"
        elif price_trend < 0 and macd_trend > 0:
            divergence_score = 1
            desc = "MACD底背离：价格下跌但MACD走强"
            signal = "bullish_divergence"
        else:
            divergence_score = 0
            desc = "MACD无背离"
            signal = "no_divergence"

        return {
            'value': divergence_score,
            'description': desc,
            'extra_data': {'signal': signal}
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        if value > 0:
            return 75.0
        elif value < 0:
            return 25.0
        else:
            return 50.0


@auto_register
class MACDHistogramAreaIndicator(IndicatorBase):
    """MACD柱状图面积指标

    计算MACD柱状图累计面积，衡量动量强度
    """
    name = "macd_histogram_area"
    display_name = "MACD柱状图面积"
    category = IndicatorCategory.TECHNICAL
    description = "MACD柱状图累计面积"

    def calculate(self, close: pd.Series = None, period: int = 10, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < 26 + period:
            return {'value': None, 'description': '数据不足'}

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        recent_hist = histogram.tail(period)
        positive_area = recent_hist.where(recent_hist > 0, 0).sum()
        negative_area = abs(recent_hist.where(recent_hist < 0, 0).sum())

        net_area = positive_area - negative_area

        if net_area > 0.5:
            desc = f"MACD柱状图正面积累积({net_area:.3f})"
        elif net_area < -0.5:
            desc = f"MACD柱状图负面积累积 ({net_area:.3f})"
        else:
            desc = f"MACD柱状图面积平衡 ({net_area:.3f})"

        return {
            'value': net_area,
            'description': desc,
            'extra_data': {
                'positive_area': positive_area,
                'negative_area': negative_area
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value * 30))


@auto_register
class KDJCrossIndicator(IndicatorBase):
    """KDJ金叉死叉指标

    检测KDJ的交叉信号
    """
    name = "kdj_cross"
    display_name = "KDJ交叉信号"
    category = IndicatorCategory.TECHNICAL
    description = "检测KDJ金叉和死叉"

    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 9, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None or len(close) < period + 5:
            return {'value': None, 'description': '数据不足'}

        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()

        rsv = (close - lowest_low) / (highest_high - lowest_low + 0.0001) * 100

        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d

        k_prev, k_curr = k.iloc[-2], k.iloc[-1]
        d_prev, d_curr = d.iloc[-2], d.iloc[-1]
        
        cross_signal = 0
        if k_prev <= d_prev and k_curr > d_curr:
            cross_signal = 1
            desc = f"KDJ金叉 (K:{k_curr:.1f}, D:{d_curr:.1f})"
            signal_type = "golden_cross"
        elif k_prev >= d_prev and k_curr < d_curr:
            cross_signal = -1
            desc = f"KDJ死叉 (K:{k_curr:.1f}, D:{d_curr:.1f})"
            signal_type = "death_cross"
        else:
            cross_signal = 0
            desc = f"KDJ无交叉 (K:{k_curr:.1f}, D:{d_curr:.1f})"
            signal_type = "no_cross"

        if k_curr < 20 and cross_signal == 1:
            desc += "，超卖区金叉，买入信号强"
            cross_signal = 2
        elif k_curr > 80 and cross_signal == -1:
            desc += "，超买区死叉，卖出信号强"
            cross_signal = -2

        return {
            'value': cross_signal,
            'description': desc,
            'extra_data': {
                'k': k_curr,
                'd': d_curr,
                'j': j.iloc[-1],
                'signal_type': signal_type
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        score_map = {2: 90, 1: 70, 0: 50, -1: 30, -2: 10}
        return score_map.get(value, 50.0)


@auto_register
class KDJDivergenceIndicator(IndicatorBase):
    """KDJ背离指标

    检测价格与KDJ的背离
    """
    name = "kdj_divergence"
    display_name = "KDJ背离"
    category = IndicatorCategory.TECHNICAL
    description = "检测价格与KDJ的背离"

    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, period: int = 9,
                  lookback: int = 20, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None or len(close) < period + lookback:
            return {'value': None, 'description': '数据不足'}

        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()
        rsv = (close - lowest_low) / (highest_high - lowest_low + 0.0001) * 100
        k = rsv.ewm(com=2, adjust=False).mean()

        price_data = close.tail(lookback)
        k_data = k.tail(lookback)

        price_trend = price_data.iloc[-1] - price_data.iloc[0]
        k_trend = k_data.iloc[-1] - k_data.iloc[0]

        divergence_score = 0
        if price_trend > 0 and k_trend < -10:
            divergence_score = -1
            desc = "KDJ顶背离"
        elif price_trend < 0 and k_trend > 10:
            divergence_score = 1
            desc = "KDJ底背离"
        else:
            divergence_score = 0
            desc = "KDJ无背离"

        return {'value': divergence_score, 'description': desc}

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return {1: 75.0, -1: 25.0}.get(value, 50.0)


@auto_register
class GapAnalysisIndicator(IndicatorBase):
    """缺口分析指标

    识别突破缺口、持续缺口、衰竭缺口
    """
    name = "gap_analysis"
    display_name = "缺口分析"
    category = IndicatorCategory.TECHNICAL
    description = "识别和分析价格缺口"

    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, volume: pd.Series = None,
                  lookback: int = 5, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None:
            return {'value': None, 'description': '数据不足'}

        gaps = []
        for i in range(1, min(lookback, len(close) - 1)):
            prev_high = high.iloc[-i-1]
            prev_low = low.iloc[-i-1]
            curr_high = high.iloc[-i]
            curr_low = low.iloc[-i]

            if curr_low > prev_high:
                gap_size = (curr_low - prev_high) / prev_high * 100
                gaps.append({'type': 'up', 'size': gap_size, 'days_ago': i})
            elif curr_high < prev_low:
                gap_size = (prev_low - curr_high) / prev_low * 100
                gaps.append({'type': 'down', 'size': gap_size, 'days_ago': i})

        if not gaps:
            return {
                'value': 0,
                'description': '近期无缺口',
                'extra_data': {'gaps': []}
            }

        latest_gap = gaps[0]
        gap_type = latest_gap['type']
        gap_size = latest_gap['size']
        
        if gap_type == 'up':
            score = min(gap_size * 10, 30)
            desc = f"向上跳空 {gap_size:.2f}%，{latest_gap['days_ago']}天前"
        else:
            score = -min(gap_size * 10, 30)
            desc = f"向下跳空 {gap_size:.2f}%，{latest_gap['days_ago']}天前"

        return {
            'value': score,
            'description': desc,
            'extra_data': {'gaps': gaps}
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value))


@auto_register
class BollingerBandWidthIndicator(IndicatorBase):
    """布林带宽度指标
    
    衡量波动率收缩或扩张
    """
    name = "bollinger_band_width"
    display_name = "布林带宽度"
    category = IndicatorCategory.TECHNICAL
    description = "布林带宽度，衡量波动率"

    def calculate(self, close: pd.Series = None, period: int = 20,
                  std_dev: float = 2.0, **kwargs) -> Dict[str, Any]:
        if close is None or len(close) < period:
            return {'value': None, 'description': '数据不足'}

        ma = close.rolling(period).mean()
        std = close.rolling(period).std()

        upper = ma + std_dev * std
        lower = ma - std_dev * std

        bandwidth = ((upper - lower) / ma * 100).iloc[-1]
        bandwidth_series = (upper - lower) / ma * 100
        bandwidth_percentile = (bandwidth_series.tail(60) < bandwidth).mean() * 100

        if bandwidth_percentile < 20:
            desc = f"布林带极度收窄 ({bandwidth:.2f}%)，可能即将突破"
            signal = "squeeze"
        elif bandwidth_percentile < 40:
            desc = f"布林带收窄 ({bandwidth:.2f}%)"
            signal = "narrowing"
        elif bandwidth_percentile > 80:
            desc = f"布林带极度扩张 ({bandwidth:.2f}%)，波动剧烈"
            signal = "expansion"
        else:
            desc = f"布林带正常 ({bandwidth:.2f}%)"
            signal = "normal"

        return {
            'value': bandwidth,
            'description': desc,
            'extra_data': {
                'bandwidth_percentile': bandwidth_percentile,
                'signal': signal
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return 50.0


@auto_register
class OBVTrendIndicator(IndicatorBase):
    """OBV趋势指标

    能量潮趋势分析
    """
    name = "obv_trend"
    display_name = "OBV趋势"
    category = IndicatorCategory.TECHNICAL
    description = "能量潮趋势分析"

    def calculate(self, close: pd.Series = None, volume: pd.Series = None,
                  period: int = 20, **kwargs) -> Dict[str, Any]:
        if close is None or volume is None or len(close) < period:
            return {'value': None, 'description': '数据不足'}

        obv = (volume * np.sign(close.diff())).cumsum()
        obv_ma = obv.rolling(period).mean()
        obv_trend = (obv.iloc[-1] - obv.iloc[-period]) / abs(obv.iloc[-period] + 1) * 100
        price_trend = (close.iloc[-1] - close.iloc[-period]) / close.iloc[-period] * 100

        if price_trend > 5 and obv_trend < 0:
            desc = f"OBV顶背离：价格涨但OBV跌"
            signal = "bearish_divergence"
            score = -20
        elif price_trend < -5 and obv_trend > 0:
            desc = f"OBV底背离：价格跌但OBV涨"
            signal = "bullish_divergence"
            score = 20
        elif obv_trend > 10:
            desc = f"OBV上升趋势 (+{obv_trend:.1f}%)"
            signal = "bullish"
            score = 15
        elif obv_trend < -10:
            desc = f"OBV下降趋势 ({obv_trend:.1f}%)"
            signal = "bearish"
            score = -15
        else:
            desc = f"OBV横盘 ({obv_trend:+.1f}%)"
            signal = "neutral"
            score = 0

        return {
            'value': score,
            'description': desc,
            'extra_data': {
                'obv_trend': obv_trend,
                'price_trend': price_trend,
                'signal': signal
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value))


@auto_register
class IchimokuCloudIndicator(IndicatorBase):
    """一目均衡云指标

    综合趋势判断
    """
    name = "ichimoku_cloud"
    display_name = "一目均衡云"
    category = IndicatorCategory.TECHNICAL
    description = "一目均衡云趋势判断"

    def calculate(self, high: pd.Series = None, low: pd.Series = None,
                  close: pd.Series = None, **kwargs) -> Dict[str, Any]:
        if high is None or low is None or close is None or len(close) < 52:
            return {'value': None, 'description': '数据不足'}

        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
        kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

        current_price = close.iloc[-1]
        current_tenkan = tenkan.iloc[-1]
        current_kijun = kijun.iloc[-1]
        cloud_top = max(senkou_a.iloc[-1], senkou_b.iloc[-1])
        cloud_bottom = min(senkou_a.iloc[-1], senkou_b.iloc[-1])

        if current_price > cloud_top:
            if current_tenkan > current_kijun:
                score = 30
                desc = "价格在云上方，转换线>基准线，强势多头"
                signal = "strong_bullish"
            else:
                score = 15
                desc = "价格在云上方，趋势偏多"
                signal = "bullish"
        elif current_price < cloud_bottom:
            if current_tenkan < current_kijun:
                score = -30
                desc = "价格在云下方，转换线<基准线，强势空头"
                signal = "strong_bearish"
            else:
                score = -15
                desc = "价格在云下方，趋势偏空"
                signal = "bearish"
        else:
            score = 0
            desc = "价格在云中，方向不明"
            signal = "neutral"

        return {
            'value': score,
            'description': desc,
            'extra_data': {
                'tenkan': current_tenkan,
                'kijun': current_kijun,
                'cloud_top': cloud_top,
                'cloud_bottom': cloud_bottom,
                'signal': signal
            }
        }

    def get_score(self, value: Any) -> float:
        if value is None:
            return 50.0
        return max(0, min(100, 50 + value))


# 指标列表
ADDITIONAL_TECHNICAL_INDICATORS = [
    'rsi_slope',
    'rsi_divergence',
    'macd_divergence',
    'macd_histogram_area',
    'kdj_cross',
    'kdj_divergence',
    'gap_analysis',
    'bollinger_band_width',
    'obv_trend',
    'ichimoku_cloud',
]


def get_all_additional_technical_indicators():
    """获取所有补充技术面指标名称列表"""
    return ADDITIONAL_TECHNICAL_INDICATORS.copy()
