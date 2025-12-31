"""
时序向量化 - 技术指标计算辅助模块
"""
import numpy as np
import pandas as pd
from typing import List


def calculate_bollinger(df: pd.DataFrame, period: int = 20) -> List[float]:
    """计算布林带特征"""
    close = df['close'].astype(float)

    # 中轨（MA20）
    middle = close.rolling(window=period, min_periods=1).mean()

    # 标准差
    std = close.rolling(window=period, min_periods=1).std()

    # 上轨和下轨
    upper = middle + 2 * std
    lower = middle - 2 * std

    current_price = close.iloc[-1]
    current_upper = upper.iloc[-1]
    current_lower = lower.iloc[-1]
    current_middle = middle.iloc[-1]

    # 布林带宽度
    bandwidth = (current_upper - current_lower) / current_middle if current_middle != 0 else 0

    # 价格在布林带中的位置 (0-1)
    position = (current_price - current_lower) / (current_upper - current_lower) if (current_upper - current_lower) != 0 else 0.5

    return [bandwidth, position]


def calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """计算ATR（平均真实波幅）"""
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    close = df['close'].astype(float)

    # 真实波幅
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR
    atr = tr.rolling(window=period, min_periods=1).mean()

    # 归一化ATR（相对于价格）
    normalized_atr = atr.iloc[-1] / close.iloc[-1] if close.iloc[-1] != 0 else 0

    return float(normalized_atr)


def calculate_pattern_features(df: pd.DataFrame) -> List[float]:
    """计算形态特征"""
    close = df['close'].astype(float)
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    open_price = df['open'].astype(float)

    features = []

    # 1. 趋势方向（最近5天的线性回归斜率）
    if len(close) >= 5:
        x = np.arange(5)
        y = close.iloc[-5:].values
        slope = np.polyfit(x, y, 1)[0]
        features.append(slope / close.iloc[-1] if close.iloc[-1] != 0 else 0)
    else:
        features.append(0)

    # 2. 波动率（最近10天的标准差）
    if len(close) >= 10:
        volatility = close.iloc[-10:].std() / close.iloc[-10:].mean() if close.iloc[-10:].mean() != 0 else 0
        features.append(float(volatility))
    else:
        features.append(0)

    # 3. 上影线/下影线比例（最后一天）
    last_high = high.iloc[-1]
    last_low = low.iloc[-1]
    last_open = open_price.iloc[-1]
    last_close = close.iloc[-1]

    body_high = max(last_open, last_close)
    body_low = min(last_open, last_close)

    upper_shadow = last_high - body_high
    lower_shadow = body_low - last_low
    body_size = abs(last_close - last_open)

    if body_size != 0:
        upper_ratio = upper_shadow / body_size
        lower_ratio = lower_shadow / body_size
    else:
        upper_ratio = 0
        lower_ratio = 0

    features.extend([upper_ratio, lower_ratio])

    # 4. 涨跌幅（最近1天、3天、5天）
    if len(close) >= 1:
        return_1d = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] if len(close) >= 2 and close.iloc[-2] != 0 else 0
        features.append(float(return_1d))
    else:
        features.append(0)

    if len(close) >= 3:
        return_3d = (close.iloc[-1] - close.iloc[-4]) / close.iloc[-4] if len(close) >= 4 and close.iloc[-4] != 0 else 0
        features.append(float(return_3d))
    else:
        features.append(0)

    if len(close) >= 5:
        return_5d = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] if len(close) >= 6 and close.iloc[-6] != 0 else 0
        features.append(float(return_5d))
    else:
        features.append(0)

    return features
