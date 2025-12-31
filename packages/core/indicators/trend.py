"""
趋势指标
MA, EMA, MACD, DMI
"""
import numpy as np
import pandas as pd
from typing import Tuple
from .base import BaseIndicator


class MA(BaseIndicator):
    """简单移动平均线"""
    
    def __init__(self, periods: list = [5, 10, 20, 60]):
        super().__init__("MA")
        self.periods = periods
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        for period in self.periods:
            df[f'MA{period}'] = df['close'].rolling(window=period).mean()
        return df
    
    @staticmethod
    def calculate_single(close: pd.Series, period: int) -> pd.Series:
        """计算单个MA"""
        return close.rolling(window=period).mean()


class EMA(BaseIndicator):
    """指数移动平均线"""
    
    def __init__(self, periods: list = [12, 26]):
        super().__init__("EMA")
        self.periods = periods
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        for period in self.periods:
            df[f'EMA{period}'] = df['close'].ewm(span=period, adjust=False).mean()
        return df
    
    @staticmethod
    def calculate_single(close: pd.Series, period: int) -> pd.Series:
        """计算单个EMA"""
        return close.ewm(span=period, adjust=False).mean()


class MACD(BaseIndicator):
    """
    MACD指标
    
    计算公式：
    - DIF = EMA12 - EMA26
    - DEA = EMA9(DIF)
    - MACD柱 = 2 * (DIF - DEA)
    """
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__("MACD")
        self.fast = fast
        self.slow = slow
        self.signal = signal
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算快慢EMA
        ema_fast = df['close'].ewm(span=self.fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.slow, adjust=False).mean()
        
        # DIF线
        df['MACD_DIF'] = ema_fast - ema_slow
        
        # DEA线（信号线）
        df['MACD_DEA'] = df['MACD_DIF'].ewm(span=self.signal, adjust=False).mean()
        
        # MACD柱
        df['MACD_HIST'] = 2 * (df['MACD_DIF'] - df['MACD_DEA'])
        
        return df
    
    @staticmethod
    def get_signal(dif: float, dea: float, prev_dif: float, prev_dea: float) -> str:
        """
        获取MACD信号
        
        Returns:
            'golden_cross': 金叉
            'death_cross': 死叉
            'bullish': 多头
            'bearish': 空头
        """
        if prev_dif <= prev_dea and dif > dea:
            return 'golden_cross'
        elif prev_dif >= prev_dea and dif < dea:
            return 'death_cross'
        elif dif > dea:
            return 'bullish'
        else:
            return 'bearish'


class DMI(BaseIndicator):
    """
    动向指标 (Directional Movement Index)
    
    包含：+DI, -DI, ADX
    """
    
    def __init__(self, period: int = 14):
        super().__init__("DMI")
        self.period = period
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        # 计算True Range
        df['TR'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        
        # 计算+DM和-DM
        df['HD'] = df['high'] - df['high'].shift(1)
        df['LD'] = df['low'].shift(1) - df['low']
        
        df['+DM'] = np.where((df['HD'] > df['LD']) & (df['HD'] > 0), df['HD'], 0)
        df['-DM'] = np.where((df['LD'] > df['HD']) & (df['LD'] > 0), df['LD'], 0)
        
        # 平滑处理
        df['TR_smooth'] = df['TR'].ewm(span=self.period, adjust=False).mean()
        df['+DM_smooth'] = df['+DM'].ewm(span=self.period, adjust=False).mean()
        df['-DM_smooth'] = df['-DM'].ewm(span=self.period, adjust=False).mean()
        
        # 计算+DI和-DI
        df['+DI'] = 100 * df['+DM_smooth'] / df['TR_smooth']
        df['-DI'] = 100 * df['-DM_smooth'] / df['TR_smooth']
        
        # 计算DX和ADX
        df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
        df['ADX'] = df['DX'].ewm(span=self.period, adjust=False).mean()
        
        # 清理临时列
        df.drop(['TR', 'HD', 'LD', '+DM', '-DM', 'TR_smooth', 
                 '+DM_smooth', '-DM_smooth', 'DX'], axis=1, inplace=True)
        
        return df


class SAR(BaseIndicator):
    """
    抛物线转向指标 (Parabolic SAR)
    
    用于判断趋势转折点，提供止损位参考
    
    参数：
    - af_start: 加速因子初始值 (默认0.02)
    - af_step: 加速因子步进值 (默认0.02)
    - af_max: 加速因子最大值 (默认0.2)
    """
    
    def __init__(self, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2):
        super().__init__("SAR")
        self.af_start = af_start
        self.af_step = af_step
        self.af_max = af_max
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        n = len(df)
        
        if n < 2:
            df['SAR'] = np.nan
            df['SAR_trend'] = 0
            return df
        
        # 初始化
        sar = np.zeros(n)
        trend = np.zeros(n)  # 1: 上升趋势, -1: 下降趋势
        af = np.zeros(n)
        ep = np.zeros(n)  # 极值点
        
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        # 确定初始趋势
        if close[1] > close[0]:
            trend[0] = trend[1] = 1
            sar[0] = sar[1] = low[0]
            ep[0] = ep[1] = high[1]
        else:
            trend[0] = trend[1] = -1
            sar[0] = sar[1] = high[0]
            ep[0] = ep[1] = low[1]
        
        af[0] = af[1] = self.af_start
        
        # 计算SAR
        for i in range(2, n):
            # 计算新的SAR
            sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
            
            if trend[i-1] == 1:  # 上升趋势
                # SAR不能高于前两日最低价
                sar[i] = min(sar[i], low[i-1], low[i-2])
                
                if low[i] < sar[i]:  # 趋势反转
                    trend[i] = -1
                    sar[i] = ep[i-1]
                    ep[i] = low[i]
                    af[i] = self.af_start
                else:
                    trend[i] = 1
                    if high[i] > ep[i-1]:
                        ep[i] = high[i]
                        af[i] = min(af[i-1] + self.af_step, self.af_max)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
            else:  # 下降趋势
                # SAR不能低于前两日最高价
                sar[i] = max(sar[i], high[i-1], high[i-2])
                
                if high[i] > sar[i]:  # 趋势反转
                    trend[i] = 1
                    sar[i] = ep[i-1]
                    ep[i] = high[i]
                    af[i] = self.af_start
                else:
                    trend[i] = -1
                    if low[i] < ep[i-1]:
                        ep[i] = low[i]
                        af[i] = min(af[i-1] + self.af_step, self.af_max)
                    else:
                        ep[i] = ep[i-1]
                        af[i] = af[i-1]
        
        df['SAR'] = sar
        df['SAR_trend'] = trend
        
        return df
    
    @staticmethod
    def get_signal(price: float, sar: float, trend: int) -> str:
        """
        获取SAR信号
        
        Returns:
            'buy': 买入信号（价格上穿SAR）
            'sell': 卖出信号（价格下穿SAR）
            'hold_long': 持有多头
            'hold_short': 持有空头
        """
        if trend == 1:
            return 'hold_long'
        else:
            return 'hold_short'


class WMA(BaseIndicator):
    """
    加权移动平均线 (Weighted Moving Average)
    
    计算公式：
    WMA = Σ(Wi * Pi) / Σ(Wi)
    其中权重Wi = i (越近期权重越大)
    """
    
    def __init__(self, periods: list = [5, 10, 20]):
        super().__init__("WMA")
        self.periods = periods
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        for period in self.periods:
            weights = np.arange(1, period + 1)
            df[f'WMA{period}'] = df['close'].rolling(window=period).apply(
                lambda x: np.sum(weights * x) / np.sum(weights), raw=True
            )
        
        return df


class DEMA(BaseIndicator):
    """
    双指数移动平均线 (Double Exponential Moving Average)
    
    计算公式：
    DEMA = 2 * EMA(n) - EMA(EMA(n))
    
    比EMA更快响应价格变化
    """
    
    def __init__(self, periods: list = [12, 26]):
        super().__init__("DEMA")
        self.periods = periods
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        
        for period in self.periods:
            ema1 = df['close'].ewm(span=period, adjust=False).mean()
            ema2 = ema1.ewm(span=period, adjust=False).mean()
            df[f'DEMA{period}'] = 2 * ema1 - ema2
        
        return df
