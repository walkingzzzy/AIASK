"""
高级技术指标计算模块
扩展AI评分系统的技术指标维度
"""
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class IndicatorResult:
    """指标计算结果"""
    value: float
    signal: str  # 'bullish', 'bearish', 'neutral'
    strength: float  # 0-1, 信号强度
    description: str


class AdvancedTechnicalIndicators:
    """高级技术指标计算器"""

    @staticmethod
    def calculate_rsi_slope(prices: pd.Series, period: int = 14) -> IndicatorResult:
        """
        RSI斜率 - 衡量RSI变化趋势

        Args:
            prices: 价格序列
            period: RSI周期

        Returns:
            指标结果
        """
        # 计算RSI
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # 计算RSI的5日斜率
        rsi_slope = rsi.diff(5).iloc[-1]

        if rsi_slope > 5:
            signal = 'bullish'
            strength = min(abs(rsi_slope) / 10, 1.0)
            desc = f"RSI上升趋势强劲 (+{rsi_slope:.1f})"
        elif rsi_slope < -5:
            signal = 'bearish'
            strength = min(abs(rsi_slope) / 10, 1.0)
            desc = f"RSI下降趋势 ({rsi_slope:.1f})"
        else:
            signal = 'neutral'
            strength = 0.3
            desc = "RSI趋势平稳"

        return IndicatorResult(
            value=rsi_slope,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_macd_divergence(prices: pd.Series, macd_hist: pd.Series) -> IndicatorResult:
        """
        MACD背离检测

        Args:
            prices: 价格序列
            macd_hist: MACD柱状图序列

        Returns:
            指标结果
        """
        # 寻找价格和MACD的背离
        price_trend = prices.iloc[-1] - prices.iloc[-20]
        macd_trend = macd_hist.iloc[-1] - macd_hist.iloc[-20]

        # 顶背离：价格新高，MACD不创新高
        if price_trend > 0 and macd_trend < 0:
            signal = 'bearish'
            strength = min(abs(macd_trend) / abs(price_trend) * 10, 1.0)
            desc = "顶背离，警惕回调"
        # 底背离：价格新低，MACD不创新低
        elif price_trend < 0 and macd_trend > 0:
            signal = 'bullish'
            strength = min(abs(macd_trend) / abs(price_trend) * 10, 1.0)
            desc = "底背离，可能反弹"
        else:
            signal = 'neutral'
            strength = 0.2
            desc = "无明显背离"

        return IndicatorResult(
            value=macd_trend / price_trend if price_trend != 0 else 0,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_bollinger_position(prices: pd.Series, period: int = 20) -> IndicatorResult:
        """
        布林带位置 - 价格在布林带中的相对位置

        Args:
            prices: 价格序列
            period: 周期

        Returns:
            指标结果
        """
        ma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = ma + 2 * std
        lower = ma - 2 * std

        current_price = prices.iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]

        # 计算位置百分比 (0-1)
        position = (current_price - current_lower) / (current_upper - current_lower)

        if position > 0.8:
            signal = 'bearish'
            strength = (position - 0.8) * 5
            desc = f"接近上轨 ({position*100:.0f}%)，可能回调"
        elif position < 0.2:
            signal = 'bullish'
            strength = (0.2 - position) * 5
            desc = f"接近下轨 ({position*100:.0f}%)，可能反弹"
        else:
            signal = 'neutral'
            strength = 0.3
            desc = f"位于中轨附近 ({position*100:.0f}%)"

        return IndicatorResult(
            value=position,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_kdj_cross(k: pd.Series, d: pd.Series, j: pd.Series) -> IndicatorResult:
        """
        KDJ交叉信号

        Args:
            k, d, j: KDJ指标序列

        Returns:
            指标结果
        """
        k_curr, k_prev = k.iloc[-1], k.iloc[-2]
        d_curr, d_prev = d.iloc[-1], d.iloc[-2]

        # 金叉
        if k_prev < d_prev and k_curr > d_curr:
            signal = 'bullish'
            strength = 0.8 if k_curr < 50 else 0.5  # 低位金叉更强
            desc = "KDJ金叉" + ("(低位)" if k_curr < 50 else "")
        # 死叉
        elif k_prev > d_prev and k_curr < d_curr:
            signal = 'bearish'
            strength = 0.8 if k_curr > 50 else 0.5
            desc = "KDJ死叉" + ("(高位)" if k_curr > 50 else "")
        else:
            signal = 'neutral'
            strength = 0.2
            desc = "KDJ无交叉"

        return IndicatorResult(
            value=k_curr - d_curr,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_atr_volatility(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> IndicatorResult:
        """
        ATR波动率指标

        Args:
            high, low, close: 价格序列
            period: 周期

        Returns:
            指标结果
        """
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        current_atr = atr.iloc[-1]
        avg_atr = atr.mean()
        atr_ratio = current_atr / avg_atr

        if atr_ratio > 1.5:
            signal = 'bearish'
            strength = min((atr_ratio - 1) / 2, 1.0)
            desc = f"波动率异常放大 ({atr_ratio:.2f}x)"
        elif atr_ratio < 0.7:
            signal = 'neutral'
            strength = 0.4
            desc = f"波动率收窄 ({atr_ratio:.2f}x)"
        else:
            signal = 'neutral'
            strength = 0.3
            desc = f"波动率正常 ({atr_ratio:.2f}x)"

        return IndicatorResult(
            value=current_atr,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_obv_trend(volume: pd.Series, close: pd.Series) -> IndicatorResult:
        """
        OBV能量潮趋势

        Args:
            volume: 成交量序列
            close: 收盘价序列

        Returns:
            指标结果
        """
        obv = (volume * ((close.diff() > 0).astype(int) * 2 - 1)).cumsum()
        obv_ma = obv.rolling(window=20).mean()

        current_obv = obv.iloc[-1]
        current_ma = obv_ma.iloc[-1]

        if current_obv > current_ma * 1.05:
            signal = 'bullish'
            strength = min((current_obv / current_ma - 1) * 10, 1.0)
            desc = "OBV上升趋势，资金流入"
        elif current_obv < current_ma * 0.95:
            signal = 'bearish'
            strength = min((1 - current_obv / current_ma) * 10, 1.0)
            desc = "OBV下降趋势，资金流出"
        else:
            signal = 'neutral'
            strength = 0.3
            desc = "OBV趋势平稳"

        return IndicatorResult(
            value=current_obv,
            signal=signal,
            strength=strength,
            description=desc
        )

    @staticmethod
    def calculate_williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> IndicatorResult:
        """
        威廉指标 %R

        Args:
            high, low, close: 价格序列
            period: 周期

        Returns:
            指标结果
        """
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        wr = -100 * (highest_high - close) / (highest_high - lowest_low)

        current_wr = wr.iloc[-1]

        if current_wr > -20:
            signal = 'bearish'
            strength = (current_wr + 20) / 20
            desc = f"超买区域 ({current_wr:.1f})"
        elif current_wr < -80:
            signal = 'bullish'
            strength = (-80 - current_wr) / 20
            desc = f"超卖区域 ({current_wr:.1f})"
        else:
            signal = 'neutral'
            strength = 0.3
            desc = f"正常区域 ({current_wr:.1f})"

        return IndicatorResult(
            value=current_wr,
            signal=signal,
            strength=strength,
            description=desc
        )
