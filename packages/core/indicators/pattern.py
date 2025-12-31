"""
K线形态识别
识别常见的K线形态和图表形态
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from .base import BaseIndicator


@dataclass
class PatternResult:
    """形态识别结果"""
    name: str           # 形态名称
    name_cn: str        # 中文名称
    type: str           # 类型: bullish/bearish/neutral
    strength: float     # 强度 0-1
    index: int          # 出现位置
    description: str    # 描述


class CandlestickPattern(BaseIndicator):
    """
    K线形态识别
    
    支持的形态：
    - 锤子线/倒锤子线
    - 吞没形态
    - 十字星
    - 早晨之星/黄昏之星
    - 三只乌鸦/三白兵
    """
    
    def __init__(self):
        super().__init__("CandlestickPattern")
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算所有K线形态"""
        df = data.copy()
        
        # 计算K线基本属性
        df['body'] = df['close'] - df['open']
        df['body_abs'] = abs(df['body'])
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        df['range'] = df['high'] - df['low']
        
        # 识别各种形态
        df['pattern_hammer'] = self._detect_hammer(df)
        df['pattern_inverted_hammer'] = self._detect_inverted_hammer(df)
        df['pattern_doji'] = self._detect_doji(df)
        df['pattern_engulfing'] = self._detect_engulfing(df)
        df['pattern_morning_star'] = self._detect_morning_star(df)
        df['pattern_evening_star'] = self._detect_evening_star(df)
        df['pattern_three_white_soldiers'] = self._detect_three_white_soldiers(df)
        df['pattern_three_black_crows'] = self._detect_three_black_crows(df)
        
        # 清理临时列
        df.drop(['body', 'body_abs', 'upper_shadow', 'lower_shadow', 'range'], 
                axis=1, inplace=True)
        
        return df
    
    def detect_patterns(self, data: pd.DataFrame) -> List[PatternResult]:
        """检测所有形态并返回结果列表"""
        df = self.calculate(data)
        patterns = []
        
        pattern_map = {
            'pattern_hammer': ('Hammer', '锤子线', 'bullish'),
            'pattern_inverted_hammer': ('Inverted Hammer', '倒锤子线', 'bullish'),
            'pattern_doji': ('Doji', '十字星', 'neutral'),
            'pattern_engulfing': ('Engulfing', '吞没形态', 'varies'),
            'pattern_morning_star': ('Morning Star', '早晨之星', 'bullish'),
            'pattern_evening_star': ('Evening Star', '黄昏之星', 'bearish'),
            'pattern_three_white_soldiers': ('Three White Soldiers', '三白兵', 'bullish'),
            'pattern_three_black_crows': ('Three Black Crows', '三只乌鸦', 'bearish'),
        }
        
        for col, (name, name_cn, ptype) in pattern_map.items():
            if col in df.columns:
                for idx in df[df[col] != 0].index:
                    value = df.loc[idx, col]
                    actual_type = ptype
                    if ptype == 'varies':
                        actual_type = 'bullish' if value > 0 else 'bearish'
                    
                    patterns.append(PatternResult(
                        name=name,
                        name_cn=name_cn,
                        type=actual_type,
                        strength=abs(value) if isinstance(value, (int, float)) else 0.5,
                        index=idx,
                        description=f"{name_cn}形态"
                    ))
        
        return patterns
    
    def _detect_hammer(self, df: pd.DataFrame) -> pd.Series:
        """
        锤子线：下影线长，实体小，上影线短或无
        出现在下跌趋势末端，看涨信号
        """
        condition = (
            (df['lower_shadow'] > 2 * df['body_abs']) &
            (df['upper_shadow'] < df['body_abs'] * 0.5) &
            (df['body_abs'] > 0)
        )
        return condition.astype(int)
    
    def _detect_inverted_hammer(self, df: pd.DataFrame) -> pd.Series:
        """
        倒锤子线：上影线长，实体小，下影线短或无
        出现在下跌趋势末端，看涨信号
        """
        condition = (
            (df['upper_shadow'] > 2 * df['body_abs']) &
            (df['lower_shadow'] < df['body_abs'] * 0.5) &
            (df['body_abs'] > 0)
        )
        return condition.astype(int)
    
    def _detect_doji(self, df: pd.DataFrame) -> pd.Series:
        """
        十字星：开盘价≈收盘价，有上下影线
        表示多空平衡，可能反转
        """
        avg_range = df['range'].rolling(20).mean()
        condition = (
            (df['body_abs'] < df['range'] * 0.1) &
            (df['range'] > avg_range * 0.5)
        )
        return condition.astype(int)

    def _detect_engulfing(self, df: pd.DataFrame) -> pd.Series:
        """
        吞没形态：
        - 看涨吞没：阴线后出现大阳线，阳线实体完全包含阴线实体
        - 看跌吞没：阳线后出现大阴线，阴线实体完全包含阳线实体
        
        返回：1=看涨吞没，-1=看跌吞没，0=无
        """
        result = pd.Series(0, index=df.index)
        
        for i in range(1, len(df)):
            prev_body = df['body'].iloc[i-1]
            curr_body = df['body'].iloc[i]
            prev_open = df['open'].iloc[i-1]
            prev_close = df['close'].iloc[i-1]
            curr_open = df['open'].iloc[i]
            curr_close = df['close'].iloc[i]
            
            # 看涨吞没：前阴后阳，阳线包含阴线
            if (prev_body < 0 and curr_body > 0 and
                curr_open <= prev_close and curr_close >= prev_open):
                result.iloc[i] = 1
            
            # 看跌吞没：前阳后阴，阴线包含阳线
            elif (prev_body > 0 and curr_body < 0 and
                  curr_open >= prev_close and curr_close <= prev_open):
                result.iloc[i] = -1
        
        return result
    
    def _detect_morning_star(self, df: pd.DataFrame) -> pd.Series:
        """
        早晨之星（三根K线组合）：
        1. 第一根：大阴线
        2. 第二根：小实体（跳空低开）
        3. 第三根：大阳线（收盘价进入第一根实体）
        
        强烈看涨信号
        """
        result = pd.Series(0, index=df.index)
        avg_body = df['body_abs'].rolling(20).mean()
        
        for i in range(2, len(df)):
            body1 = df['body'].iloc[i-2]
            body2 = df['body'].iloc[i-1]
            body3 = df['body'].iloc[i]
            
            close1 = df['close'].iloc[i-2]
            open2 = df['open'].iloc[i-1]
            close3 = df['close'].iloc[i]
            open1 = df['open'].iloc[i-2]
            
            avg = avg_body.iloc[i] if not pd.isna(avg_body.iloc[i]) else df['body_abs'].iloc[i]
            
            # 条件检查
            if (body1 < -avg * 0.5 and           # 第一根大阴线
                abs(body2) < avg * 0.3 and       # 第二根小实体
                body3 > avg * 0.5 and            # 第三根大阳线
                open2 < close1 and               # 跳空低开
                close3 > (open1 + close1) / 2):  # 收盘进入第一根实体
                result.iloc[i] = 1
        
        return result
    
    def _detect_evening_star(self, df: pd.DataFrame) -> pd.Series:
        """
        黄昏之星（三根K线组合）：
        1. 第一根：大阳线
        2. 第二根：小实体（跳空高开）
        3. 第三根：大阴线（收盘价进入第一根实体）
        
        强烈看跌信号
        """
        result = pd.Series(0, index=df.index)
        avg_body = df['body_abs'].rolling(20).mean()
        
        for i in range(2, len(df)):
            body1 = df['body'].iloc[i-2]
            body2 = df['body'].iloc[i-1]
            body3 = df['body'].iloc[i]
            
            close1 = df['close'].iloc[i-2]
            open2 = df['open'].iloc[i-1]
            close3 = df['close'].iloc[i]
            open1 = df['open'].iloc[i-2]
            
            avg = avg_body.iloc[i] if not pd.isna(avg_body.iloc[i]) else df['body_abs'].iloc[i]
            
            # 条件检查
            if (body1 > avg * 0.5 and            # 第一根大阳线
                abs(body2) < avg * 0.3 and       # 第二根小实体
                body3 < -avg * 0.5 and           # 第三根大阴线
                open2 > close1 and               # 跳空高开
                close3 < (open1 + close1) / 2):  # 收盘进入第一根实体
                result.iloc[i] = 1
        
        return result
    
    def _detect_three_white_soldiers(self, df: pd.DataFrame) -> pd.Series:
        """
        三白兵（三根连续阳线）：
        - 三根连续阳线
        - 每根开盘价在前一根实体内
        - 每根收盘价接近最高价
        
        强烈看涨信号
        """
        result = pd.Series(0, index=df.index)
        
        for i in range(2, len(df)):
            # 三根都是阳线
            if (df['body'].iloc[i-2] > 0 and 
                df['body'].iloc[i-1] > 0 and 
                df['body'].iloc[i] > 0):
                
                # 每根开盘价在前一根实体内
                cond1 = (df['open'].iloc[i-1] > df['open'].iloc[i-2] and 
                         df['open'].iloc[i-1] < df['close'].iloc[i-2])
                cond2 = (df['open'].iloc[i] > df['open'].iloc[i-1] and 
                         df['open'].iloc[i] < df['close'].iloc[i-1])
                
                # 收盘价接近最高价（上影线短）
                cond3 = (df['upper_shadow'].iloc[i-2] < df['body_abs'].iloc[i-2] * 0.3 and
                         df['upper_shadow'].iloc[i-1] < df['body_abs'].iloc[i-1] * 0.3 and
                         df['upper_shadow'].iloc[i] < df['body_abs'].iloc[i] * 0.3)
                
                if cond1 and cond2 and cond3:
                    result.iloc[i] = 1
        
        return result
    
    def _detect_three_black_crows(self, df: pd.DataFrame) -> pd.Series:
        """
        三只乌鸦（三根连续阴线）：
        - 三根连续阴线
        - 每根开盘价在前一根实体内
        - 每根收盘价接近最低价
        
        强烈看跌信号
        """
        result = pd.Series(0, index=df.index)
        
        for i in range(2, len(df)):
            # 三根都是阴线
            if (df['body'].iloc[i-2] < 0 and 
                df['body'].iloc[i-1] < 0 and 
                df['body'].iloc[i] < 0):
                
                # 每根开盘价在前一根实体内
                cond1 = (df['open'].iloc[i-1] < df['open'].iloc[i-2] and 
                         df['open'].iloc[i-1] > df['close'].iloc[i-2])
                cond2 = (df['open'].iloc[i] < df['open'].iloc[i-1] and 
                         df['open'].iloc[i] > df['close'].iloc[i-1])
                
                # 收盘价接近最低价（下影线短）
                cond3 = (df['lower_shadow'].iloc[i-2] < df['body_abs'].iloc[i-2] * 0.3 and
                         df['lower_shadow'].iloc[i-1] < df['body_abs'].iloc[i-1] * 0.3 and
                         df['lower_shadow'].iloc[i] < df['body_abs'].iloc[i] * 0.3)
                
                if cond1 and cond2 and cond3:
                    result.iloc[i] = 1
        
        return result


class ChartPattern(BaseIndicator):
    """
    图表形态识别
    
    支持的形态：
    - 双顶/双底
    - 头肩顶/头肩底
    - 三角形整理
    - 旗形整理
    """
    
    def __init__(self, lookback: int = 60):
        super().__init__("ChartPattern")
        self.lookback = lookback
    
    def calculate(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算图表形态"""
        df = data.copy()
        
        # 找出局部高点和低点
        df['local_high'] = self._find_local_extrema(df['high'], 'high')
        df['local_low'] = self._find_local_extrema(df['low'], 'low')
        
        return df
    
    def _find_local_extrema(self, series: pd.Series, extrema_type: str, 
                            window: int = 5) -> pd.Series:
        """找出局部极值点"""
        result = pd.Series(0, index=series.index)
        
        for i in range(window, len(series) - window):
            if extrema_type == 'high':
                if series.iloc[i] == series.iloc[i-window:i+window+1].max():
                    result.iloc[i] = 1
            else:
                if series.iloc[i] == series.iloc[i-window:i+window+1].min():
                    result.iloc[i] = 1
        
        return result
    
    def detect_double_top(self, data: pd.DataFrame, tolerance: float = 0.02) -> Optional[Dict]:
        """
        检测双顶形态
        
        Args:
            data: OHLC数据
            tolerance: 两个顶点价格差异容忍度
            
        Returns:
            形态信息字典或None
        """
        df = self.calculate(data)
        highs = df[df['local_high'] == 1]['high']
        
        if len(highs) < 2:
            return None
        
        # 检查最近两个高点
        recent_highs = highs.tail(2)
        h1, h2 = recent_highs.iloc[0], recent_highs.iloc[1]
        
        # 价格接近
        if abs(h1 - h2) / h1 < tolerance:
            return {
                'pattern': 'double_top',
                'name_cn': '双顶',
                'type': 'bearish',
                'peak1': h1,
                'peak2': h2,
                'neckline': df.loc[recent_highs.index[0]:recent_highs.index[1], 'low'].min()
            }
        
        return None
    
    def detect_double_bottom(self, data: pd.DataFrame, tolerance: float = 0.02) -> Optional[Dict]:
        """
        检测双底形态
        
        Args:
            data: OHLC数据
            tolerance: 两个底点价格差异容忍度
            
        Returns:
            形态信息字典或None
        """
        df = self.calculate(data)
        lows = df[df['local_low'] == 1]['low']
        
        if len(lows) < 2:
            return None
        
        # 检查最近两个低点
        recent_lows = lows.tail(2)
        l1, l2 = recent_lows.iloc[0], recent_lows.iloc[1]
        
        # 价格接近
        if abs(l1 - l2) / l1 < tolerance:
            return {
                'pattern': 'double_bottom',
                'name_cn': '双底',
                'type': 'bullish',
                'trough1': l1,
                'trough2': l2,
                'neckline': df.loc[recent_lows.index[0]:recent_lows.index[1], 'high'].max()
            }
        
        return None
    
    def detect_support_resistance(self, data: pd.DataFrame, 
                                   num_levels: int = 3) -> Dict[str, List[float]]:
        """
        检测支撑位和阻力位
        
        Args:
            data: OHLC数据
            num_levels: 返回的支撑/阻力位数量
            
        Returns:
            {'support': [...], 'resistance': [...]}
        """
        df = self.calculate(data)
        current_price = df['close'].iloc[-1]
        
        # 获取所有局部高点和低点
        highs = df[df['local_high'] == 1]['high'].values
        lows = df[df['local_low'] == 1]['low'].values
        
        # 阻力位：高于当前价格的局部高点
        resistance = sorted([h for h in highs if h > current_price])[:num_levels]
        
        # 支撑位：低于当前价格的局部低点
        support = sorted([l for l in lows if l < current_price], reverse=True)[:num_levels]
        
        return {
            'support': support,
            'resistance': resistance,
            'current_price': current_price
        }
