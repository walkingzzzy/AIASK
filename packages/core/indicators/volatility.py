"""
波动率指标
BOLL (布林带), ATR (真实波动幅度)
"""
import numpy as np
import pandas as pd
from .base import BaseIndicator


class BOLL(BaseIndicator):
    """
    布林带 (Bollinger Bands)
    
    计算公式：
    中轨 = MA(N)
    上轨 = 中轨 + K * STD(N)
    下轨 = 中轨 - K * STD(N)
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__("BOLL")
        self.period = period
        self.std_dev = std_dev
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 中轨（移动平均）
        df['BOLL_MID'] = df['close'].rolling(window=self.period).mean()
        
        # 标准差
        std = df['close'].rolling(window=self.period).std()
        
        # 上轨和下轨
        df['BOLL_UP'] = df['BOLL_MID'] + self.std_dev * std
        df['BOLL_DOWN'] = df['BOLL_MID'] - self.std_dev * std
        
        # 带宽 (Bandwidth)
        df['BOLL_WIDTH'] = (df['BOLL_UP'] - df['BOLL_DOWN']) / df['BOLL_MID'] * 100
        
        # %B指标（价格在布林带中的位置）
        df['BOLL_PB'] = (df['close'] - df['BOLL_DOWN']) / (df['BOLL_UP'] - df['BOLL_DOWN'])
        
        return df
    
    @staticmethod
    def get_signal(close: float, upper: float, lower: float, mid: float) -> str:
        """
        获取布林带信号
        
        Returns:
            'overbought': 超买（价格触及上轨）
            'oversold': 超卖（价格触及下轨）
            'squeeze': 收窄（带宽收窄，可能突破）
            'neutral': 中性
        """
        if close >= upper:
            return 'overbought'
        elif close <= lower:
            return 'oversold'
        elif close > mid:
            return 'bullish'
        else:
            return 'bearish'


class ATR(BaseIndicator):
    """
    真实波动幅度 (Average True Range)
    
    计算公式：
    TR = max(H-L, |H-Cp|, |L-Cp|)
    ATR = EMA(TR, N)
    """
    
    def __init__(self, period: int = 14):
        super().__init__("ATR")
        self.period = period
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算True Range
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))
        
        df['TR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # 计算ATR
        df['ATR'] = df['TR'].ewm(span=self.period, adjust=False).mean()
        
        # ATR百分比（相对于收盘价）
        df['ATR_PCT'] = df['ATR'] / df['close'] * 100
        
        # 清理临时列
        df.drop(['TR'], axis=1, inplace=True)
        
        return df
    
    @staticmethod
    def calculate_stop_loss(close: float, atr: float, multiplier: float = 2.0) -> float:
        """
        基于ATR计算止损价
        
        Args:
            close: 当前价格
            atr: ATR值
            multiplier: ATR倍数
            
        Returns:
            止损价格
        """
        return close - multiplier * atr
    
    @staticmethod
    def get_volatility_level(atr_pct: float) -> str:
        """
        获取波动率水平
        
        Args:
            atr_pct: ATR百分比
            
        Returns:
            'low': 低波动
            'medium': 中等波动
            'high': 高波动
        """
        if atr_pct < 2:
            return 'low'
        elif atr_pct < 5:
            return 'medium'
        else:
            return 'high'
