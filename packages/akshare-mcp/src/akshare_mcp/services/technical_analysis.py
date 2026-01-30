"""
技术分析服务
使用 pandas-ta 和 ta-lib 实现高性能技术指标计算
"""

from typing import List, Dict, Any, Optional
import numpy as np

try:
    import pandas as pd
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    pd = None
    ta = None

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    talib = None


class TechnicalAnalysis:
    """技术分析计算器"""
    
    @staticmethod
    def calculate_sma(closes: List[float], period: int = 20) -> List[float]:
        """计算简单移动平均"""
        if not PANDAS_TA_AVAILABLE:
            return TechnicalAnalysis._calculate_sma_numpy(closes, period)
        
        df = pd.DataFrame({'close': closes})
        result = df.ta.sma(length=period)
        return result.fillna(0).tolist()
    
    @staticmethod
    def _calculate_sma_numpy(closes: List[float], period: int) -> List[float]:
        """NumPy实现的SMA（fallback）"""
        closes_arr = np.array(closes)
        if len(closes_arr) < period:
            return [0.0] * len(closes)
        
        weights = np.ones(period) / period
        sma = np.convolve(closes_arr, weights, mode='valid')
        
        # 前面补0
        result = np.zeros(len(closes))
        result[period-1:] = sma
        return result.tolist()
    
    @staticmethod
    def calculate_ema(closes: List[float], period: int = 20) -> List[float]:
        """计算指数移动平均"""
        if TALIB_AVAILABLE:
            result = talib.EMA(np.array(closes), timeperiod=period)
            return np.nan_to_num(result, 0).tolist()
        
        if PANDAS_TA_AVAILABLE:
            df = pd.DataFrame({'close': closes})
            result = df.ta.ema(length=period)
            return result.fillna(0).tolist()
        
        return TechnicalAnalysis._calculate_ema_numpy(closes, period)
    
    @staticmethod
    def _calculate_ema_numpy(closes: List[float], period: int) -> List[float]:
        """NumPy实现的EMA（fallback）"""
        closes_arr = np.array(closes)
        alpha = 2 / (period + 1)
        ema = np.zeros(len(closes))
        ema[0] = closes_arr[0]
        
        for i in range(1, len(closes)):
            ema[i] = alpha * closes_arr[i] + (1 - alpha) * ema[i-1]
        
        return ema.tolist()
    
    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> Dict[str, Any]:
        """计算RSI指标"""
        if TALIB_AVAILABLE:
            rsi = talib.RSI(np.array(closes), timeperiod=period)
            rsi_value = float(rsi[-1]) if not np.isnan(rsi[-1]) else 0
        elif PANDAS_TA_AVAILABLE:
            df = pd.DataFrame({'close': closes})
            rsi_series = df.ta.rsi(length=period)
            rsi_value = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 0
        else:
            rsi_value = TechnicalAnalysis._calculate_rsi_numpy(closes, period)
        
        # 生成信号
        signal = 'hold'
        if rsi_value < 30:
            signal = 'buy'
        elif rsi_value > 70:
            signal = 'sell'
        
        return {
            'value': round(rsi_value, 2),
            'signal': signal,
            'overbought': rsi_value > 70,
            'oversold': rsi_value < 30,
        }
    
    @staticmethod
    def _calculate_rsi_numpy(closes: List[float], period: int) -> float:
        """NumPy实现的RSI（fallback）"""
        closes_arr = np.array(closes)
        deltas = np.diff(closes_arr)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:]) if len(gains) >= period else 0
        avg_loss = np.mean(losses[-period:]) if len(losses) >= period else 0
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(
        closes: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, Any]:
        """计算MACD指标"""
        if TALIB_AVAILABLE:
            macd, signal, hist = talib.MACD(
                np.array(closes),
                fastperiod=fast_period,
                slowperiod=slow_period,
                signalperiod=signal_period
            )
            return {
                'macd': np.nan_to_num(macd, 0).tolist(),
                'signal': np.nan_to_num(signal, 0).tolist(),
                'histogram': np.nan_to_num(hist, 0).tolist(),
            }
        
        if PANDAS_TA_AVAILABLE:
            df = pd.DataFrame({'close': closes})
            macd_df = df.ta.macd(fast=fast_period, slow=slow_period, signal=signal_period)
            return {
                'macd': macd_df[f'MACD_{fast_period}_{slow_period}_{signal_period}'].fillna(0).tolist(),
                'signal': macd_df[f'MACDs_{fast_period}_{slow_period}_{signal_period}'].fillna(0).tolist(),
                'histogram': macd_df[f'MACDh_{fast_period}_{slow_period}_{signal_period}'].fillna(0).tolist(),
            }
        
        # NumPy fallback
        ema_fast = TechnicalAnalysis._calculate_ema_numpy(closes, fast_period)
        ema_slow = TechnicalAnalysis._calculate_ema_numpy(closes, slow_period)
        macd = np.array(ema_fast) - np.array(ema_slow)
        signal = TechnicalAnalysis._calculate_ema_numpy(macd.tolist(), signal_period)
        histogram = macd - np.array(signal)
        
        return {
            'macd': macd.tolist(),
            'signal': signal,
            'histogram': histogram.tolist(),
        }
    
    @staticmethod
    def calculate_kdj(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 9,
        k_period: int = 3,
        d_period: int = 3
    ) -> Dict[str, Any]:
        """计算KDJ指标"""
        if TALIB_AVAILABLE:
            k, d = talib.STOCH(
                np.array(highs),
                np.array(lows),
                np.array(closes),
                fastk_period=period,
                slowk_period=k_period,
                slowd_period=d_period
            )
            k = np.nan_to_num(k, 0)
            d = np.nan_to_num(d, 0)
            j = 3 * k - 2 * d
            
            return {
                'k': k.tolist(),
                'd': d.tolist(),
                'j': j.tolist(),
            }
        
        # NumPy实现
        n = len(closes)
        rsv = np.zeros(n)
        
        for i in range(period - 1, n):
            period_high = max(highs[i-period+1:i+1])
            period_low = min(lows[i-period+1:i+1])
            
            if period_high != period_low:
                rsv[i] = (closes[i] - period_low) / (period_high - period_low) * 100
            else:
                rsv[i] = 50
        
        # 计算K值
        k = np.zeros(n)
        k[0] = 50
        for i in range(1, n):
            k[i] = (2/3) * k[i-1] + (1/3) * rsv[i]
        
        # 计算D值
        d = np.zeros(n)
        d[0] = 50
        for i in range(1, n):
            d[i] = (2/3) * d[i-1] + (1/3) * k[i]
        
        # 计算J值
        j = 3 * k - 2 * d
        
        return {
            'k': k.tolist(),
            'd': d.tolist(),
            'j': j.tolist(),
        }
    
    @staticmethod
    def calculate_bollinger_bands(
        closes: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, Any]:
        """计算布林带"""
        if TALIB_AVAILABLE:
            upper, middle, lower = talib.BBANDS(
                np.array(closes),
                timeperiod=period,
                nbdevup=std_dev,
                nbdevdn=std_dev
            )
            return {
                'upper': np.nan_to_num(upper, 0).tolist(),
                'middle': np.nan_to_num(middle, 0).tolist(),
                'lower': np.nan_to_num(lower, 0).tolist(),
            }
        
        if PANDAS_TA_AVAILABLE:
            df = pd.DataFrame({'close': closes})
            bbands = df.ta.bbands(length=period, std=std_dev)
            return {
                'upper': bbands[f'BBU_{period}_{std_dev}'].fillna(0).tolist(),
                'middle': bbands[f'BBM_{period}_{std_dev}'].fillna(0).tolist(),
                'lower': bbands[f'BBL_{period}_{std_dev}'].fillna(0).tolist(),
            }
        
        # NumPy实现
        sma = TechnicalAnalysis._calculate_sma_numpy(closes, period)
        closes_arr = np.array(closes)
        
        std = np.zeros(len(closes))
        for i in range(period - 1, len(closes)):
            std[i] = np.std(closes_arr[i-period+1:i+1])
        
        upper = np.array(sma) + std_dev * std
        lower = np.array(sma) - std_dev * std
        
        return {
            'upper': upper.tolist(),
            'middle': sma,
            'lower': lower.tolist(),
        }
    
    @staticmethod
    def calculate_atr(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> List[float]:
        """计算ATR（平均真实波幅）"""
        if TALIB_AVAILABLE:
            atr = talib.ATR(
                np.array(highs),
                np.array(lows),
                np.array(closes),
                timeperiod=period
            )
            return np.nan_to_num(atr, 0).tolist()
        
        # NumPy实现
        n = len(closes)
        tr = np.zeros(n)
        
        for i in range(1, n):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            tr[i] = max(hl, hc, lc)
        
        # 计算ATR
        atr = np.zeros(n)
        atr[period-1] = np.mean(tr[1:period])
        
        for i in range(period, n):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
        
        return atr.tolist()
    
    @staticmethod
    @staticmethod
    def calculate_all_indicators(
        klines: List[Dict[str, Any]],
        indicators: List[str]
    ) -> Dict[str, Any]:
        """批量计算多个技术指标"""
        if not klines:
            return {}
        
        # 提取OHLCV数据
        closes = [k['close'] for k in klines]
        opens = [k['open'] for k in klines]
        highs = [k['high'] for k in klines]
        lows = [k['low'] for k in klines]
        volumes = [k['volume'] for k in klines]
        
        results = {}
        
        for indicator in indicators:
            indicator_lower = indicator.lower()
            
            if indicator_lower == 'ma' or indicator_lower == 'sma':
                results['ma'] = TechnicalAnalysis.calculate_sma(closes, 20)
            elif indicator_lower == 'ema':
                results['ema'] = TechnicalAnalysis.calculate_ema(closes, 20)
            elif indicator_lower == 'rsi':
                results['rsi'] = TechnicalAnalysis.calculate_rsi(closes, 14)
            elif indicator_lower == 'macd':
                results['macd'] = TechnicalAnalysis.calculate_macd(closes)
            elif indicator_lower == 'kdj':
                results['kdj'] = TechnicalAnalysis.calculate_kdj(highs, lows, closes)
            elif indicator_lower == 'boll' or indicator_lower == 'bbands':
                results['boll'] = TechnicalAnalysis.calculate_bollinger_bands(closes)
            elif indicator_lower == 'atr':
                results['atr'] = TechnicalAnalysis.calculate_atr(highs, lows, closes)
            elif indicator_lower == 'obv':
                results['obv'] = TechnicalAnalysis.calculate_obv(closes, volumes)
            elif indicator_lower == 'cci':
                results['cci'] = TechnicalAnalysis.calculate_cci(highs, lows, closes)
            elif indicator_lower == 'wr':
                results['wr'] = TechnicalAnalysis.calculate_wr(highs, lows, closes)
            elif indicator_lower == 'roc':
                results['roc'] = TechnicalAnalysis.calculate_roc(closes)
        
        return results
    
    @staticmethod
    def calculate_obv(closes: List[float], volumes: List[float]) -> List[float]:
        """计算能量潮指标 (On Balance Volume)"""
        if TALIB_AVAILABLE:
            obv = talib.OBV(np.array(closes), np.array(volumes))
            return np.nan_to_num(obv, 0).tolist()
        
        # NumPy实现
        obv = np.zeros(len(closes))
        obv[0] = volumes[0]
        
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv[i] = obv[i-1] + volumes[i]
            elif closes[i] < closes[i-1]:
                obv[i] = obv[i-1] - volumes[i]
            else:
                obv[i] = obv[i-1]
        
        return obv.tolist()
    
    @staticmethod
    def calculate_cci(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
        """计算顺势指标 (Commodity Channel Index)"""
        if TALIB_AVAILABLE:
            cci = talib.CCI(np.array(highs), np.array(lows), np.array(closes), timeperiod=period)
            return np.nan_to_num(cci, 0).tolist()
        
        # NumPy实现
        tp = (np.array(highs) + np.array(lows) + np.array(closes)) / 3
        cci = np.zeros(len(closes))
        
        for i in range(period - 1, len(closes)):
            sma = np.mean(tp[i-period+1:i+1])
            md = np.mean(np.abs(tp[i-period+1:i+1] - sma))
            if md != 0:
                cci[i] = (tp[i] - sma) / (0.015 * md)
        
        return cci.tolist()
    
    @staticmethod
    def calculate_wr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
        """计算威廉指标 (Williams %R)"""
        if TALIB_AVAILABLE:
            wr = talib.WILLR(np.array(highs), np.array(lows), np.array(closes), timeperiod=period)
            return np.nan_to_num(wr, 0).tolist()
        
        # NumPy实现
        wr = np.zeros(len(closes))
        
        for i in range(period - 1, len(closes)):
            highest = max(highs[i-period+1:i+1])
            lowest = min(lows[i-period+1:i+1])
            
            if highest != lowest:
                wr[i] = -100 * (highest - closes[i]) / (highest - lowest)
            else:
                wr[i] = -50
        
        return wr.tolist()
    
    @staticmethod
    def calculate_roc(closes: List[float], period: int = 12) -> List[float]:
        """计算变动率指标 (Rate of Change)"""
        if TALIB_AVAILABLE:
            roc = talib.ROC(np.array(closes), timeperiod=period)
            return np.nan_to_num(roc, 0).tolist()
        
        # NumPy实现
        roc = np.zeros(len(closes))
        
        for i in range(period, len(closes)):
            if closes[i-period] != 0:
                roc[i] = ((closes[i] - closes[i-period]) / closes[i-period]) * 100
        
        return roc.tolist()


# 全局实例
technical_analysis = TechnicalAnalysis()
