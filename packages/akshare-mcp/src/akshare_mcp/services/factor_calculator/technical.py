"""技术因子 - 动量/RSI/MACD/ROC/TRIX/反转/WillR/CCI/MFI/StochK"""
import numpy as np
from typing import List


class TechnicalFactorsMixin:
    """技术因子混入类 - 动量、反转、振荡器指标"""

    # ========== 技术因子 - 动量因子 ==========

    @staticmethod
    def calculate_momentum(closes: List[float], period: int = 20) -> float:
        """动量因子（通用）"""
        if len(closes) < period:
            return 0.0
        return (closes[-1] - closes[-period]) / closes[-period]

    @staticmethod
    def calculate_mom_1d(closes: List[float]) -> float:
        """1日动量因子 MOM_1D"""
        if len(closes) < 2:
            return 0.0
        return (closes[-1] - closes[-2]) / closes[-2]

    @staticmethod
    def calculate_mom_5d(closes: List[float]) -> float:
        """5日动量因子 MOM_5D"""
        if len(closes) < 6:
            return 0.0
        return (closes[-1] - closes[-6]) / closes[-6]

    @staticmethod
    def calculate_mom_10d(closes: List[float]) -> float:
        """10日动量因子 MOM_10D"""
        if len(closes) < 11:
            return 0.0
        return (closes[-1] - closes[-11]) / closes[-11]

    @staticmethod
    def calculate_mom_20d(closes: List[float]) -> float:
        """20日动量因子 MOM_20D"""
        if len(closes) < 21:
            return 0.0
        return (closes[-1] - closes[-21]) / closes[-21]

    @staticmethod
    def calculate_mom_60d(closes: List[float]) -> float:
        """60日动量因子 MOM_60D"""
        if len(closes) < 61:
            return 0.0
        return (closes[-1] - closes[-61]) / closes[-61]

    @staticmethod
    def calculate_rsi(closes: List[float], period: int = 14) -> float:
        """RSI相对强弱指数（通用）"""
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)

    @staticmethod
    def calculate_rsi_6(closes: List[float]) -> float:
        """6日RSI"""
        return TechnicalFactorsMixin.calculate_rsi(closes, period=6)

    @staticmethod
    def calculate_rsi_14(closes: List[float]) -> float:
        """14日RSI"""
        return TechnicalFactorsMixin.calculate_rsi(closes, period=14)

    @staticmethod
    def calculate_rsi_24(closes: List[float]) -> float:
        """24日RSI"""
        return TechnicalFactorsMixin.calculate_rsi(closes, period=24)

    @staticmethod
    def calculate_macd(closes: List[float], fast: int = 12, slow: int = 26) -> float:
        """MACD指标"""
        if len(closes) < slow:
            return 0.0
        closes_arr = np.array(closes)
        ema_fast = TechnicalFactorsMixin._calculate_ema(closes_arr, fast)
        ema_slow = TechnicalFactorsMixin._calculate_ema(closes_arr, slow)
        macd = ema_fast - ema_slow
        return float(macd)

    @staticmethod
    def calculate_macd_signal(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
        """MACD信号线"""
        if len(closes) < slow + signal:
            return 0.0
        macd_values = []
        for i in range(slow, len(closes) + 1):
            macd = TechnicalFactorsMixin.calculate_macd(closes[:i], fast, slow)
            macd_values.append(macd)
        if len(macd_values) < signal:
            return 0.0
        signal_line = TechnicalFactorsMixin._calculate_ema(np.array(macd_values), signal)
        return float(signal_line)

    @staticmethod
    def calculate_macd_hist(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
        """MACD柱状图（MACD - Signal）"""
        macd = TechnicalFactorsMixin.calculate_macd(closes, fast, slow)
        macd_signal = TechnicalFactorsMixin.calculate_macd_signal(closes, fast, slow, signal)
        return macd - macd_signal

    @staticmethod
    def calculate_roc(closes: List[float], period: int = 10) -> float:
        """变动率ROC（通用）"""
        if len(closes) < period + 1:
            return 0.0
        return ((closes[-1] - closes[-(period+1)]) / closes[-(period+1)]) * 100

    @staticmethod
    def calculate_roc_5(closes: List[float]) -> float:
        """5日变动率 ROC_5"""
        return TechnicalFactorsMixin.calculate_roc(closes, period=5)

    @staticmethod
    def calculate_roc_10(closes: List[float]) -> float:
        """10日变动率 ROC_10"""
        return TechnicalFactorsMixin.calculate_roc(closes, period=10)

    @staticmethod
    def calculate_roc_20(closes: List[float]) -> float:
        """20日变动率 ROC_20"""
        return TechnicalFactorsMixin.calculate_roc(closes, period=20)

    @staticmethod
    def calculate_trix(closes: List[float], period: int = 12) -> float:
        """三重指数平滑TRIX"""
        if len(closes) < period * 3:
            return 0.0
        closes_arr = np.array(closes)
        ema1 = TechnicalFactorsMixin._calculate_ema(closes_arr, period)
        ema1_series = []
        for i in range(period, len(closes) + 1):
            ema1_series.append(TechnicalFactorsMixin._calculate_ema(np.array(closes[:i]), period))
        if len(ema1_series) < period:
            return 0.0
        ema2 = TechnicalFactorsMixin._calculate_ema(np.array(ema1_series), period)
        ema2_series = []
        for i in range(period, len(ema1_series) + 1):
            ema2_series.append(TechnicalFactorsMixin._calculate_ema(np.array(ema1_series[:i]), period))
        if len(ema2_series) < period + 1:
            return 0.0
        ema3_current = TechnicalFactorsMixin._calculate_ema(np.array(ema2_series), period)
        ema3_prev = TechnicalFactorsMixin._calculate_ema(np.array(ema2_series[:-1]), period)
        if ema3_prev == 0:
            return 0.0
        trix = ((ema3_current - ema3_prev) / ema3_prev) * 100
        return float(trix)

    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> float:
        """计算指数移动平均EMA"""
        if len(data) < period:
            return float(np.mean(data))
        alpha = 2.0 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = alpha * price + (1 - alpha) * ema
        return float(ema)

    # ========== 技术因子 - 反转因子 ==========

    @staticmethod
    def calculate_reversal(closes: List[float], period: int = 5) -> float:
        """反转因子（通用）"""
        if len(closes) < period:
            return 0.0
        return -(closes[-1] - closes[-period]) / closes[-period]

    @staticmethod
    def calculate_rev_1d(closes: List[float]) -> float:
        """1日反转因子 REV_1D"""
        if len(closes) < 2:
            return 0.0
        return -(closes[-1] - closes[-2]) / closes[-2]

    @staticmethod
    def calculate_rev_5d(closes: List[float]) -> float:
        """5日反转因子 REV_5D"""
        if len(closes) < 6:
            return 0.0
        return -(closes[-1] - closes[-6]) / closes[-6]

    @staticmethod
    def calculate_rev_10d(closes: List[float]) -> float:
        """10日反转因子 REV_10D"""
        if len(closes) < 11:
            return 0.0
        return -(closes[-1] - closes[-11]) / closes[-11]

    @staticmethod
    def calculate_rev_20d(closes: List[float]) -> float:
        """20日反转因子 REV_20D"""
        if len(closes) < 21:
            return 0.0
        return -(closes[-1] - closes[-21]) / closes[-21]

    @staticmethod
    def calculate_willr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """威廉指标 Williams %R"""
        if len(highs) < period or len(lows) < period or len(closes) < period:
            return -50.0
        highest_high = max(highs[-period:])
        lowest_low = min(lows[-period:])
        if highest_high == lowest_low:
            return -50.0
        willr = ((highest_high - closes[-1]) / (highest_high - lowest_low)) * -100
        return float(willr)

    @staticmethod
    def calculate_cci(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """商品通道指数 CCI"""
        if len(highs) < period or len(lows) < period or len(closes) < period:
            return 0.0
        typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs[-period:], lows[-period:], closes[-period:])]
        sma_tp = np.mean(typical_prices)
        mean_deviation = np.mean([abs(tp - sma_tp) for tp in typical_prices])
        if mean_deviation == 0:
            return 0.0
        cci = (typical_prices[-1] - sma_tp) / (0.015 * mean_deviation)
        return float(cci)

    @staticmethod
    def calculate_mfi(highs: List[float], lows: List[float], closes: List[float],
                     volumes: List[float], period: int = 14) -> float:
        """资金流量指数 MFI"""
        if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1 or len(volumes) < period + 1:
            return 50.0
        typical_prices = [(h + l + c) / 3 for h, l, c in zip(highs[-(period+1):], lows[-(period+1):], closes[-(period+1):])]
        money_flows = [tp * v for tp, v in zip(typical_prices, volumes[-(period+1):])]
        positive_flow = 0.0
        negative_flow = 0.0
        for i in range(1, len(typical_prices)):
            if typical_prices[i] > typical_prices[i-1]:
                positive_flow += money_flows[i]
            elif typical_prices[i] < typical_prices[i-1]:
                negative_flow += money_flows[i]
        if negative_flow == 0:
            return 100.0
        money_flow_ratio = positive_flow / negative_flow
        mfi = 100 - (100 / (1 + money_flow_ratio))
        return float(mfi)

    @staticmethod
    def calculate_stoch_k(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """随机指标K值 STOCH_K"""
        if len(highs) < period or len(lows) < period or len(closes) < period:
            return 50.0
        highest_high = max(highs[-period:])
        lowest_low = min(lows[-period:])
        if highest_high == lowest_low:
            return 50.0
        stoch_k = ((closes[-1] - lowest_low) / (highest_high - lowest_low)) * 100
        return float(stoch_k)
