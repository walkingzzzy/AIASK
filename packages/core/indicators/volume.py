"""
成交量指标
OBV (能量潮), VWAP (成交量加权平均价)
"""
import numpy as np
import pandas as pd
from .base import BaseIndicator


class OBV(BaseIndicator):
    """
    能量潮 (On Balance Volume)
    
    计算公式：
    如果今日收盘价 > 昨日收盘价：OBV = 昨日OBV + 今日成交量
    如果今日收盘价 < 昨日收盘价：OBV = 昨日OBV - 今日成交量
    如果今日收盘价 = 昨日收盘价：OBV = 昨日OBV
    """
    
    def __init__(self):
        super().__init__("OBV")
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算价格变化方向
        price_change = df['close'].diff()
        
        # 计算OBV
        obv = np.where(price_change > 0, df['volume'],
                      np.where(price_change < 0, -df['volume'], 0))
        
        df['OBV'] = obv.cumsum()
        
        # OBV的移动平均（用于判断趋势）
        df['OBV_MA'] = df['OBV'].rolling(window=20).mean()
        
        return df
    
    @staticmethod
    def get_signal(obv: float, obv_ma: float, 
                   price_trend: str) -> str:
        """
        获取OBV信号
        
        Args:
            obv: 当前OBV值
            obv_ma: OBV移动平均
            price_trend: 价格趋势 'up'/'down'
            
        Returns:
            'bullish_divergence': 底背离（价格下跌但OBV上升）
            'bearish_divergence': 顶背离（价格上涨但OBV下降）
            'confirm_up': 确认上涨
            'confirm_down': 确认下跌
        """
        obv_trend = 'up' if obv > obv_ma else 'down'
        
        if price_trend == 'down' and obv_trend == 'up':
            return 'bullish_divergence'
        elif price_trend == 'up' and obv_trend == 'down':
            return 'bearish_divergence'
        elif price_trend == 'up' and obv_trend == 'up':
            return 'confirm_up'
        else:
            return 'confirm_down'


class VWAP(BaseIndicator):
    """
    成交量加权平均价 (Volume Weighted Average Price)
    
    计算公式：
    VWAP = Σ(典型价格 × 成交量) / Σ成交量
    典型价格 = (H + L + C) / 3
    """
    
    def __init__(self):
        super().__init__("VWAP")
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算典型价格
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        
        # 计算累计值
        df['TP_VOL'] = typical_price * df['volume']
        df['CUM_TP_VOL'] = df['TP_VOL'].cumsum()
        df['CUM_VOL'] = df['volume'].cumsum()
        
        # 计算VWAP
        df['VWAP'] = df['CUM_TP_VOL'] / df['CUM_VOL']
        
        # 清理临时列
        df.drop(['TP_VOL', 'CUM_TP_VOL', 'CUM_VOL'], axis=1, inplace=True)
        
        return df
    
    @staticmethod
    def get_signal(close: float, vwap: float) -> str:
        """
        获取VWAP信号
        
        Args:
            close: 当前价格
            vwap: VWAP值
            
        Returns:
            'above': 价格在VWAP上方（多头）
            'below': 价格在VWAP下方（空头）
            'at': 价格接近VWAP
        """
        diff_pct = (close - vwap) / vwap * 100
        
        if diff_pct > 0.5:
            return 'above'
        elif diff_pct < -0.5:
            return 'below'
        else:
            return 'at'


class VolumeRatio(BaseIndicator):
    """
    量比指标
    
    计算公式：
    量比 = 当日成交量 / 过去N日平均成交量
    """
    
    def __init__(self, period: int = 5):
        super().__init__("VR")
        self.period = period
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算过去N日平均成交量
        avg_volume = df['volume'].rolling(window=self.period).mean().shift(1)
        
        # 计算量比
        df['VR'] = df['volume'] / avg_volume
        
        return df
    
    @staticmethod
    def get_signal(vr: float) -> str:
        """
        获取量比信号
        
        Args:
            vr: 量比值
            
        Returns:
            'heavy': 放量 (>2)
            'light': 缩量 (<0.5)
            'normal': 正常
        """
        if vr > 2:
            return 'heavy'
        elif vr < 0.5:
            return 'light'
        else:
            return 'normal'
