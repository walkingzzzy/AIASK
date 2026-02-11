"""波动率因子 - 波动率/ATR/布林带宽度"""
import numpy as np
from typing import List


class VolatilityFactorsMixin:
    """波动率因子混入类"""

    @staticmethod
    def calculate_volatility(closes: List[float], period: int = 20) -> float:
        """波动率因子（通用）"""
        if len(closes) < period:
            return 0.0
        returns = np.diff(closes[-period:]) / closes[-period-1:-1]
        return float(np.std(returns) * np.sqrt(252))

    @staticmethod
    def calculate_vol_5d(closes: List[float]) -> float:
        """5日波动率 VOL_5D"""
        if len(closes) < 6:
            return 0.0
        returns = np.diff(closes[-6:]) / closes[-6:-1]
        return float(np.std(returns) * np.sqrt(252))

    @staticmethod
    def calculate_vol_10d(closes: List[float]) -> float:
        """10日波动率 VOL_10D"""
        if len(closes) < 11:
            return 0.0
        returns = np.diff(closes[-11:]) / closes[-11:-1]
        return float(np.std(returns) * np.sqrt(252))

    @staticmethod
    def calculate_vol_20d(closes: List[float]) -> float:
        """20日波动率 VOL_20D"""
        if len(closes) < 21:
            return 0.0
        returns = np.diff(closes[-21:]) / closes[-21:-1]
        return float(np.std(returns) * np.sqrt(252))

    @staticmethod
    def calculate_vol_60d(closes: List[float]) -> float:
        """60日波动率 VOL_60D"""
        if len(closes) < 61:
            return 0.0
        returns = np.diff(closes[-61:]) / closes[-61:-1]
        return float(np.std(returns) * np.sqrt(252))

    @staticmethod
    def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """平均真实波幅 ATR（通用）"""
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
            return 0.0
        true_ranges = []
        for i in range(1, period + 1):
            idx = -(period + 1 - i + 1)
            high_low = highs[idx] - lows[idx]
            high_close = abs(highs[idx] - closes[idx - 1])
            low_close = abs(lows[idx] - closes[idx - 1])
            true_range = max(high_low, high_close, low_close)
            true_ranges.append(true_range)
        atr = np.mean(true_ranges)
        return float(atr)

    @staticmethod
    def calculate_atr_14(highs: List[float], lows: List[float], closes: List[float]) -> float:
        """14日ATR"""
        return VolatilityFactorsMixin.calculate_atr(highs, lows, closes, period=14)

    @staticmethod
    def calculate_atr_20(highs: List[float], lows: List[float], closes: List[float]) -> float:
        """20日ATR"""
        return VolatilityFactorsMixin.calculate_atr(highs, lows, closes, period=20)

    @staticmethod
    def calculate_bbwidth(closes: List[float], period: int = 20, num_std: float = 2.0) -> float:
        """布林带宽度 BBWIDTH"""
        if len(closes) < period:
            return 0.0
        middle = np.mean(closes[-period:])
        std = np.std(closes[-period:])
        upper = middle + num_std * std
        lower = middle - num_std * std
        if middle == 0:
            return 0.0
        bbwidth = (upper - lower) / middle
        return float(bbwidth)
