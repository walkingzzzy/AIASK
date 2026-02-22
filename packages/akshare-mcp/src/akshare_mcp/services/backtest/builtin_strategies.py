"""内置策略 — IStrategy 子类封装

逻辑直接复用 engine.py 中 _build_strategy_masks() 的对应分支。
JIT 快速路径不受影响；这些类仅用于信号记录和 StrategyRegistry。
"""

from typing import Any, Dict, Optional

import numpy as np

from .strategy_base import IStrategy


class MaCrossStrategy(IStrategy):
    """均线交叉策略"""

    def __init__(self, short_period: int = 5, long_period: int = 20):
        self.short_period = short_period
        self.long_period = long_period

    @classmethod
    def name(cls) -> str:
        return "ma_cross"

    @classmethod
    def description(cls) -> str:
        return "均线交叉策略：短期均线上穿长期均线买入，下穿卖出"

    def get_parameters(self) -> Dict[str, Any]:
        return {"short_period": self.short_period, "long_period": self.long_period}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.short_period = max(2, int(params.get("short_period", self.short_period)))
        self.long_period = max(
            self.short_period + 1, int(params.get("long_period", self.long_period))
        )

    def generate_signals(
        self, closes: np.ndarray, volumes: Optional[np.ndarray] = None
    ) -> np.ndarray:
        n = len(closes)
        signals = np.zeros(n, dtype=np.int8)
        if n < self.long_period + 2:
            return signals
        short_ma = np.full(n, np.nan)
        long_ma = np.full(n, np.nan)
        for i in range(self.short_period - 1, n):
            short_ma[i] = np.mean(closes[i - self.short_period + 1 : i + 1])
        for i in range(self.long_period - 1, n):
            long_ma[i] = np.mean(closes[i - self.long_period + 1 : i + 1])
        for i in range(self.long_period, n):
            if short_ma[i - 1] <= long_ma[i - 1] and short_ma[i] > long_ma[i]:
                signals[i] = 1
            elif short_ma[i - 1] >= long_ma[i - 1] and short_ma[i] < long_ma[i]:
                signals[i] = -1
        return signals


class MomentumStrategy(IStrategy):
    """动量策略"""

    def __init__(self, lookback: int = 20, threshold: float = 0.02):
        self.lookback = lookback
        self.threshold = threshold

    @classmethod
    def name(cls) -> str:
        return "momentum"

    @classmethod
    def description(cls) -> str:
        return "动量策略：N日涨幅超过阈值买入，跌幅超过阈值卖出"

    def get_parameters(self) -> Dict[str, Any]:
        return {"lookback": self.lookback, "threshold": self.threshold}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.lookback = max(2, int(params.get("lookback", params.get("period", self.lookback))))
        self.threshold = float(params.get("threshold", self.threshold) or 0.02)

    def generate_signals(
        self, closes: np.ndarray, volumes: Optional[np.ndarray] = None
    ) -> np.ndarray:
        n = len(closes)
        signals = np.zeros(n, dtype=np.int8)
        if n < self.lookback + 2:
            return signals
        for i in range(self.lookback, n):
            base = closes[i - self.lookback]
            if base > 0:
                mom = (closes[i] - base) / base
                if mom > self.threshold:
                    signals[i] = 1
                elif mom < -self.threshold:
                    signals[i] = -1
        return signals


class RsiStrategy(IStrategy):
    """RSI 策略"""

    def __init__(self, rsi_period: int = 14, oversold: float = 30, overbought: float = 70):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    @classmethod
    def name(cls) -> str:
        return "rsi"

    @classmethod
    def description(cls) -> str:
        return "RSI策略：RSI低于超卖线买入，高于超买线卖出"

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "rsi_period": self.rsi_period,
            "oversold": self.oversold,
            "overbought": self.overbought,
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.rsi_period = max(2, int(params.get("rsi_period", self.rsi_period)))
        self.oversold = float(params.get("oversold", self.oversold) or 30)
        self.overbought = float(params.get("overbought", self.overbought) or 70)

    def generate_signals(
        self, closes: np.ndarray, volumes: Optional[np.ndarray] = None
    ) -> np.ndarray:
        n = len(closes)
        signals = np.zeros(n, dtype=np.int8)
        if n < self.rsi_period + 2:
            return signals
        for i in range(self.rsi_period, n):
            gains = 0.0
            losses = 0.0
            for j in range(i - self.rsi_period + 1, i + 1):
                change = closes[j] - closes[j - 1]
                if change > 0:
                    gains += change
                else:
                    losses -= change
            avg_gain = gains / self.rsi_period
            avg_loss = losses / self.rsi_period
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))
            if rsi < self.oversold:
                signals[i] = 1
            elif rsi > self.overbought:
                signals[i] = -1
        return signals


class BuyAndHoldStrategy(IStrategy):
    """买入持有策略"""

    @classmethod
    def name(cls) -> str:
        return "buy_and_hold"

    @classmethod
    def description(cls) -> str:
        return "买入持有策略：第一天买入，一直持有到最后"

    def get_parameters(self) -> Dict[str, Any]:
        return {}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        pass

    def generate_signals(
        self, closes: np.ndarray, volumes: Optional[np.ndarray] = None
    ) -> np.ndarray:
        n = len(closes)
        signals = np.zeros(n, dtype=np.int8)
        if n > 1:
            signals[0] = 1  # 第一天买入
        return signals
