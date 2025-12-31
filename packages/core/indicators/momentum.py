"""
动量指标
RSI, KDJ, CCI
"""
import numpy as np
import pandas as pd
from .base import BaseIndicator


class RSI(BaseIndicator):
    """
    相对强弱指标 (Relative Strength Index)
    
    计算公式：
    RSI = 100 - 100 / (1 + RS)
    RS = 平均上涨幅度 / 平均下跌幅度
    """
    
    def __init__(self, periods: list = [6, 12, 24]):
        super().__init__("RSI")
        self.periods = periods
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        for period in self.periods:
            df[f'RSI{period}'] = self._calculate_rsi(df['close'], period)
        
        return df
    
    @staticmethod
    def _calculate_rsi(close: pd.Series, period: int) -> pd.Series:
        """计算RSI"""
        delta = close.diff()
        
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)
        
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def get_signal(rsi: float) -> str:
        """
        获取RSI信号
        
        Returns:
            'overbought': 超买 (>70)
            'oversold': 超卖 (<30)
            'neutral': 中性
        """
        if rsi > 70:
            return 'overbought'
        elif rsi < 30:
            return 'oversold'
        else:
            return 'neutral'


class KDJ(BaseIndicator):
    """
    随机指标 (KDJ)
    
    计算公式：
    RSV = (C - Ln) / (Hn - Ln) * 100
    K = 2/3 * 前K + 1/3 * RSV
    D = 2/3 * 前D + 1/3 * K
    J = 3K - 2D
    """
    
    def __init__(self, n: int = 9, m1: int = 3, m2: int = 3):
        super().__init__("KDJ")
        self.n = n    # RSV周期
        self.m1 = m1  # K平滑周期
        self.m2 = m2  # D平滑周期
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算N日内最高价和最低价
        low_n = df['low'].rolling(window=self.n).min()
        high_n = df['high'].rolling(window=self.n).max()
        
        # 计算RSV
        rsv = (df['close'] - low_n) / (high_n - low_n) * 100
        rsv = rsv.fillna(50)  # 处理除零情况
        
        # 计算K值（使用EMA平滑）
        df['KDJ_K'] = rsv.ewm(span=self.m1, adjust=False).mean()
        
        # 计算D值
        df['KDJ_D'] = df['KDJ_K'].ewm(span=self.m2, adjust=False).mean()
        
        # 计算J值
        df['KDJ_J'] = 3 * df['KDJ_K'] - 2 * df['KDJ_D']
        
        return df
    
    @staticmethod
    def get_signal(k: float, d: float, prev_k: float, prev_d: float) -> str:
        """
        获取KDJ信号
        
        Returns:
            'golden_cross': 金叉（K上穿D）
            'death_cross': 死叉（K下穿D）
            'overbought': 超买区
            'oversold': 超卖区
            'neutral': 中性
        """
        # 金叉死叉判断
        if prev_k <= prev_d and k > d:
            return 'golden_cross'
        elif prev_k >= prev_d and k < d:
            return 'death_cross'
        
        # 超买超卖判断
        if k > 80 and d > 80:
            return 'overbought'
        elif k < 20 and d < 20:
            return 'oversold'
        
        return 'neutral'


class CCI(BaseIndicator):
    """
    顺势指标 (Commodity Channel Index)
    
    计算公式：
    TP = (H + L + C) / 3
    CCI = (TP - MA(TP)) / (0.015 * MD)
    MD = 平均绝对偏差
    """
    
    def __init__(self, period: int = 14):
        super().__init__("CCI")
        self.period = period
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算典型价格
        tp = (df['high'] + df['low'] + df['close']) / 3
        
        # 计算TP的移动平均
        tp_ma = tp.rolling(window=self.period).mean()
        
        # 计算平均绝对偏差
        md = tp.rolling(window=self.period).apply(
            lambda x: np.mean(np.abs(x - x.mean())), raw=True
        )
        
        # 计算CCI
        df['CCI'] = (tp - tp_ma) / (0.015 * md)
        
        return df
    
    @staticmethod
    def get_signal(cci: float) -> str:
        """
        获取CCI信号
        
        Returns:
            'strong_buy': 强势买入 (>100)
            'strong_sell': 强势卖出 (<-100)
            'neutral': 中性
        """
        if cci > 100:
            return 'strong_buy'
        elif cci < -100:
            return 'strong_sell'
        else:
            return 'neutral'


class WilliamsR(BaseIndicator):
    """
    威廉指标 (Williams %R)
    
    计算公式：
    %R = (Hn - C) / (Hn - Ln) * -100
    
    其中：
    - Hn: N日内最高价
    - Ln: N日内最低价
    - C: 当日收盘价
    """
    
    def __init__(self, period: int = 14):
        super().__init__("WilliamsR")
        self.period = period
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算N日内最高价和最低价
        high_n = df['high'].rolling(window=self.period).max()
        low_n = df['low'].rolling(window=self.period).min()
        
        # 计算Williams %R
        df[f'WR{self.period}'] = (high_n - df['close']) / (high_n - low_n) * -100
        
        return df
    
    @staticmethod
    def get_signal(wr: float) -> str:
        """
        获取Williams %R信号
        
        Returns:
            'overbought': 超买 (> -20)
            'oversold': 超卖 (< -80)
            'neutral': 中性
        """
        if wr > -20:
            return 'overbought'
        elif wr < -80:
            return 'oversold'
        else:
            return 'neutral'


class ROC(BaseIndicator):
    """
    变动率指标 (Rate of Change)
    
    计算公式：
    ROC = (C - Cn) / Cn * 100
    
    其中：
    - C: 当日收盘价
    - Cn: N日前收盘价
    """
    
    def __init__(self, period: int = 12):
        super().__init__("ROC")
        self.period = period
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算ROC
        df[f'ROC{self.period}'] = (
            (df['close'] - df['close'].shift(self.period)) / 
            df['close'].shift(self.period) * 100
        )
        
        return df
    
    @staticmethod
    def get_signal(roc: float) -> str:
        """
        获取ROC信号
        
        Returns:
            'bullish': 看涨 (> 0)
            'bearish': 看跌 (< 0)
            'neutral': 中性
        """
        if roc > 5:
            return 'strong_bullish'
        elif roc > 0:
            return 'bullish'
        elif roc < -5:
            return 'strong_bearish'
        elif roc < 0:
            return 'bearish'
        else:
            return 'neutral'
