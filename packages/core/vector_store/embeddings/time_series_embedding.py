"""
时序向量化模块
将K线数据转换为固定维度的向量，支持模式匹配和相似性搜索
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from dataclasses import dataclass
from .indicators import calculate_bollinger, calculate_atr, calculate_pattern_features


@dataclass
class WindowData:
    """窗口数据"""
    stock_code: str
    start_date: str
    end_date: str
    ohlcv: List[Dict]  # [{date, open, high, low, close, volume}, ...]


class TimeSeriesEmbedding:
    """时序向量化器"""

    def __init__(self, window_size: int = 20, strategy: str = "indicators"):
        """
        初始化时序向量化器

        Args:
            window_size: 窗口大小（天数）
            strategy: 向量化策略 ["simple", "indicators"]
        """
        self.window_size = window_size
        self.strategy = strategy

    def embed_window(self, ohlcv: List[Dict]) -> np.ndarray:
        """
        将K线窗口转换为向量

        Args:
            ohlcv: K线数据列表

        Returns:
            向量表示
        """
        if len(ohlcv) < self.window_size:
            raise ValueError(f"数据不足，需要至少{self.window_size}天数据")

        if self.strategy == "simple":
            return self._embed_simple(ohlcv)
        elif self.strategy == "indicators":
            return self._embed_indicators(ohlcv)
        else:
            raise ValueError(f"未知策略: {self.strategy}")

    def _embed_simple(self, ohlcv: List[Dict]) -> np.ndarray:
        """
        简单拼接法：归一化OHLCV拼接
        向量维度: window_size * 5 = 100维（20天）
        """
        if not ohlcv or len(ohlcv) == 0:
            raise ValueError("OHLCV数据为空")

        base_price = float(ohlcv[0]['close'])
        if base_price == 0:
            base_price = 1.0

        normalized = []
        for day in ohlcv[:self.window_size]:
            # 价格归一化（相对于窗口起点）
            normalized.extend([
                float(day['open']) / base_price - 1,
                float(day['high']) / base_price - 1,
                float(day['low']) / base_price - 1,
                float(day['close']) / base_price - 1,
                np.log1p(float(day.get('volume', 0)))  # 成交量对数
            ])

        return np.array(normalized, dtype=np.float32)

    def _embed_indicators(self, ohlcv: List[Dict]) -> np.ndarray:
        """
        技术指标法：使用技术指标组合
        向量维度: 约50维
        """
        df = pd.DataFrame(ohlcv[:self.window_size])
        features = []

        # 1. 趋势指标
        features.extend(self._calculate_ma_features(df))
        features.extend(self._calculate_macd_features(df))

        # 2. 动量指标
        features.append(self._calculate_rsi(df))
        features.extend(self._calculate_kdj(df))

        # 3. 波动指标
        features.extend(self._calculate_bollinger(df))
        features.append(self._calculate_atr(df))

        # 4. 形态特征
        features.extend(self._calculate_pattern_features(df))

        return np.array(features, dtype=np.float32)

    def _calculate_ma_features(self, df: pd.DataFrame) -> List[float]:
        """计算均线特征"""
        close = df['close'].astype(float)

        # MA5, MA10, MA20
        ma5 = close.rolling(5, min_periods=1).mean().iloc[-1]
        ma10 = close.rolling(10, min_periods=1).mean().iloc[-1]
        ma20 = close.rolling(20, min_periods=1).mean().iloc[-1]

        current_price = close.iloc[-1]

        return [
            (current_price - ma5) / ma5 if ma5 != 0 else 0,
            (current_price - ma10) / ma10 if ma10 != 0 else 0,
            (current_price - ma20) / ma20 if ma20 != 0 else 0,
            (ma5 - ma10) / ma10 if ma10 != 0 else 0,
            (ma10 - ma20) / ma20 if ma20 != 0 else 0,
        ]

    def _calculate_macd_features(self, df: pd.DataFrame) -> List[float]:
        """计算MACD特征"""
        close = df['close'].astype(float)

        # EMA12, EMA26
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()

        # MACD线
        macd = ema12 - ema26

        # 信号线
        signal = macd.ewm(span=9, adjust=False).mean()

        # 柱状图
        hist = macd - signal

        return [
            float(macd.iloc[-1]),
            float(signal.iloc[-1]),
            float(hist.iloc[-1])
        ]

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算RSI"""
        close = df['close'].astype(float)
        delta = close.diff()

        gain = (delta.where(delta > 0, 0)).rolling(window=period, min_periods=1).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period, min_periods=1).mean()

        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1])

    def _calculate_kdj(self, df: pd.DataFrame, period: int = 9) -> List[float]:
        """计算KDJ"""
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)

        low_min = low.rolling(window=period, min_periods=1).min()
        high_max = high.rolling(window=period, min_periods=1).max()

        rsv = (close - low_min) / (high_max - low_min).replace(0, 1) * 100

        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        j = 3 * k - 2 * d

        return [float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])]

    def _calculate_bollinger(self, df: pd.DataFrame) -> List[float]:
        """计算布林带特征"""
        return calculate_bollinger(df)

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """计算ATR"""
        return calculate_atr(df)

    def _calculate_pattern_features(self, df: pd.DataFrame) -> List[float]:
        """计算形态特征"""
        return calculate_pattern_features(df)

    def get_embedding_dim(self) -> int:
        """获取向量维度"""
        if self.strategy == "simple":
            return self.window_size * 5  # 100维
        elif self.strategy == "indicators":
            # 5(MA) + 3(MACD) + 1(RSI) + 3(KDJ) + 2(Bollinger) + 1(ATR) + 7(Pattern) = 22维
            return 22
        else:
            return 0
