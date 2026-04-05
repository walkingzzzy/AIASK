"""Expanded factory strategies for P1 runtime coverage.

These strategies provide lightweight, deterministic signal generation so the
strategy factory's expanded rule families are executable in the backtest
engine instead of being whitelisted-only types.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from .strategy_base import IStrategy


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=float)
    if window <= 0 or len(values) < window:
        return result
    for i in range(window - 1, len(values)):
        result[i] = float(np.mean(values[i - window + 1 : i + 1]))
    return result


def _rolling_volatility(closes: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(closes), np.nan, dtype=float)
    if len(closes) < window + 1:
        return result
    for i in range(window, len(closes)):
        window_slice = closes[i - window : i + 1]
        prev = window_slice[:-1]
        curr = window_slice[1:]
        valid = prev > 0
        if not np.any(valid):
            continue
        returns = (curr[valid] - prev[valid]) / prev[valid]
        if returns.size >= 2:
            result[i] = float(np.std(returns))
    return result


def _compute_rsi(closes: np.ndarray, period: int) -> np.ndarray:
    rsi = np.full(len(closes), np.nan, dtype=float)
    if len(closes) < period + 1:
        return rsi
    for i in range(period, len(closes)):
        gains = 0.0
        losses = 0.0
        for j in range(i - period + 1, i + 1):
            change = float(closes[j] - closes[j - 1])
            if change > 0:
                gains += change
            else:
                losses -= change
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _clamped_rank(window: np.ndarray, value: float) -> float:
    valid = window[np.isfinite(window)]
    if valid.size < 5 or not np.isfinite(value):
        return np.nan
    return float(np.sum(valid < value)) / float(valid.size)


class VolatilityBreakoutStrategy(IStrategy):
    def __init__(self, lookback: int = 20, threshold: float = 0.025):
        self.lookback = lookback
        self.threshold = threshold

    @classmethod
    def name(cls) -> str:
        return "volatility_breakout"

    @classmethod
    def description(cls) -> str:
        return "波动率突破策略：突破滚动波动率阈值且价格站上均线时买入"

    def get_parameters(self) -> Dict[str, Any]:
        return {"lookback": self.lookback, "threshold": self.threshold}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.lookback = max(5, int(params.get("lookback", self.lookback) or self.lookback))
        self.threshold = max(0.005, float(params.get("threshold", self.threshold) or self.threshold))

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        signals = np.zeros(len(closes), dtype=np.int8)
        if len(closes) < self.lookback + 2:
            return signals
        rolling_ma = _rolling_mean(closes, self.lookback)
        rolling_vol = _rolling_volatility(closes, self.lookback)
        for i in range(self.lookback, len(closes)):
            base = float(closes[i - self.lookback])
            if base <= 0 or not np.isfinite(rolling_ma[i]) or not np.isfinite(rolling_vol[i]):
                continue
            breakout = float(closes[i] - base) / base
            effective_threshold = max(self.threshold, float(rolling_vol[i]) * 0.9)
            if closes[i] > rolling_ma[i] and breakout > effective_threshold:
                signals[i] = 1
            elif breakout < -effective_threshold * 0.6 or closes[i] < rolling_ma[i] * 0.985:
                signals[i] = -1
        return signals


class GapFillStrategy(IStrategy):
    def __init__(
        self,
        gap_threshold: float = 0.02,
        rsi_period: int = 5,
        oversold: float = 24.0,
        overbought: float = 58.0,
    ):
        self.gap_threshold = gap_threshold
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    @classmethod
    def name(cls) -> str:
        return "gap_fill"

    @classmethod
    def description(cls) -> str:
        return "跳空回补策略：利用向下跳空后的回补行为进行短线均值回归"

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "gap_threshold": self.gap_threshold,
            "rsi_period": self.rsi_period,
            "oversold": self.oversold,
            "overbought": self.overbought,
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.gap_threshold = max(0.005, float(params.get("gap_threshold", self.gap_threshold) or self.gap_threshold))
        self.rsi_period = max(2, int(params.get("rsi_period", self.rsi_period) or self.rsi_period))
        self.oversold = float(params.get("oversold", self.oversold) or self.oversold)
        self.overbought = float(params.get("overbought", self.overbought) or self.overbought)

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        signals = np.zeros(len(closes), dtype=np.int8)
        if len(closes) < self.rsi_period + 3:
            return signals
        rsi = _compute_rsi(closes, self.rsi_period)
        mean_line = _rolling_mean(closes, max(5, self.rsi_period * 2))
        for i in range(max(5, self.rsi_period), len(closes)):
            if not np.isfinite(rsi[i]) or not np.isfinite(mean_line[i]):
                continue
            if rsi[i] <= self.oversold and closes[i] < mean_line[i] * 0.99:
                signals[i] = 1
            elif rsi[i] >= self.overbought or closes[i] >= mean_line[i] * 1.01:
                signals[i] = -1
        return signals

    def generate_entry_exit_masks_from_klines(self, klines: list[dict[str, Any]]):
        closes = np.array([float((item or {}).get("close", 0.0) or 0.0) for item in klines], dtype=float)
        entry = np.zeros(len(closes), dtype=bool)
        exit_ = np.zeros(len(closes), dtype=bool)
        if len(closes) < self.rsi_period + 3:
            return entry, exit_

        rsi = _compute_rsi(closes, self.rsi_period)
        for i in range(1, len(klines)):
            row = dict(klines[i] or {})
            prev_close = float((klines[i - 1] or {}).get("close", 0.0) or 0.0)
            open_price = float(row.get("open", 0.0) or 0.0)
            close_price = float(row.get("close", 0.0) or 0.0)
            if prev_close <= 0 or open_price <= 0 or close_price <= 0:
                continue
            gap = (open_price - prev_close) / prev_close
            if gap <= -self.gap_threshold and close_price >= open_price and rsi[i] <= max(self.oversold + 15.0, 45.0):
                entry[i] = True
            if close_price >= prev_close or rsi[i] >= self.overbought or gap >= self.gap_threshold:
                exit_[i] = True
        return entry, exit_


class MeanReversionShortStrategy(IStrategy):
    def __init__(self, rsi_period: int = 6, oversold: float = 26.0, overbought: float = 62.0):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    @classmethod
    def name(cls) -> str:
        return "mean_reversion_short"

    @classmethod
    def description(cls) -> str:
        return "短周期均值回归策略：短周期 RSI 和均线乖离共同确认反转"

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "rsi_period": self.rsi_period,
            "oversold": self.oversold,
            "overbought": self.overbought,
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.rsi_period = max(2, int(params.get("rsi_period", self.rsi_period) or self.rsi_period))
        self.oversold = float(params.get("oversold", self.oversold) or self.oversold)
        self.overbought = float(params.get("overbought", self.overbought) or self.overbought)

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        signals = np.zeros(len(closes), dtype=np.int8)
        if len(closes) < self.rsi_period + 3:
            return signals
        rsi = _compute_rsi(closes, self.rsi_period)
        mean_line = _rolling_mean(closes, max(5, self.rsi_period * 2))
        for i in range(max(5, self.rsi_period), len(closes)):
            if not np.isfinite(rsi[i]) or not np.isfinite(mean_line[i]) or mean_line[i] <= 0:
                continue
            deviation = (float(closes[i]) - float(mean_line[i])) / float(mean_line[i])
            if rsi[i] <= self.oversold and deviation <= -0.015:
                signals[i] = 1
            elif rsi[i] >= self.overbought or deviation >= 0.02:
                signals[i] = -1
        return signals


class SectorRotationStrategy(IStrategy):
    def __init__(self):
        self._lookback = 20
        self._factor_weights: Dict[str, float] = {"momentum": 0.45, "quality": 0.30, "value": 0.25}

    @classmethod
    def name(cls) -> str:
        return "sector_rotation"

    @classmethod
    def description(cls) -> str:
        return "行业轮动策略：用动量、稳定性与估值回归代理构造轮动打分"

    def get_parameters(self) -> Dict[str, Any]:
        return {"lookback": self._lookback, "factor_weights": dict(self._factor_weights)}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self._lookback = max(10, int(params.get("lookback", self._lookback) or self._lookback))
        weights = dict(params.get("factor_weights") or {})
        if weights:
            total = sum(float(value or 0.0) for value in weights.values()) or 1.0
            self._factor_weights = {
                str(key): float(value or 0.0) / total
                for key, value in weights.items()
            }

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        signals = np.zeros(len(closes), dtype=np.int8)
        if len(closes) < self._lookback + 5:
            return signals
        score = np.full(len(closes), np.nan, dtype=float)
        for i in range(self._lookback, len(closes)):
            base = float(closes[i - self._lookback])
            short_base = float(closes[max(0, i - 10)])
            if base <= 0 or short_base <= 0:
                continue
            window = closes[i - self._lookback : i + 1]
            returns = np.diff(window) / np.maximum(window[:-1], 1e-8)
            momentum = (float(closes[i]) - base) / base
            short_momentum = (float(closes[i]) - short_base) / short_base
            stability = -float(np.std(returns)) if returns.size > 1 else 0.0
            mean_line = float(np.mean(window))
            value_reversion = -((float(closes[i]) - mean_line) / mean_line) if mean_line > 0 else 0.0
            score[i] = (
                self._factor_weights.get("momentum", 0.0) * (0.6 * momentum + 0.4 * short_momentum)
                + self._factor_weights.get("quality", 0.0) * stability
                + self._factor_weights.get("value", 0.0) * value_reversion
            )
        for i in range(self._lookback, len(closes)):
            rank = _clamped_rank(score[max(0, i - self._lookback) : i + 1], score[i])
            if not np.isfinite(rank):
                continue
            if rank >= 0.72:
                signals[i] = 1
            elif rank <= 0.28:
                signals[i] = -1
        return signals


class NorthCapitalTrackStrategy(IStrategy):
    def __init__(self, lookback: int = 15, threshold: float = 0.015):
        self.lookback = lookback
        self.threshold = threshold

    @classmethod
    def name(cls) -> str:
        return "north_capital_track"

    @classmethod
    def description(cls) -> str:
        return "北向资金跟踪策略：用价量共振近似外资持续流入的跟随交易"

    def get_parameters(self) -> Dict[str, Any]:
        return {"lookback": self.lookback, "threshold": self.threshold}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.lookback = max(5, int(params.get("lookback", self.lookback) or self.lookback))
        self.threshold = max(0.005, float(params.get("threshold", self.threshold) or self.threshold))

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        signals = np.zeros(len(closes), dtype=np.int8)
        if len(closes) < self.lookback + 2:
            return signals
        volume_arr = np.asarray(volumes if volumes is not None else np.zeros(len(closes)), dtype=float)
        for i in range(self.lookback, len(closes)):
            base = float(closes[i - self.lookback])
            if base <= 0:
                continue
            trend = (float(closes[i]) - base) / base
            short_volume = float(np.mean(volume_arr[max(0, i - 4) : i + 1])) if volume_arr.size else 0.0
            long_volume = float(np.mean(volume_arr[i - self.lookback : i + 1])) if volume_arr.size else 0.0
            volume_ratio = short_volume / long_volume if long_volume > 0 else 1.0
            if trend > self.threshold and volume_ratio >= 1.1:
                signals[i] = 1
            elif trend < -self.threshold * 0.8 or (trend < self.threshold * 0.25 and volume_ratio <= 0.9):
                signals[i] = -1
        return signals


class MarginDivergenceStrategy(IStrategy):
    def __init__(self, fear_threshold: int = 40, greed_threshold: int = 60, lookback: int = 15):
        self.fear_threshold = fear_threshold
        self.greed_threshold = greed_threshold
        self.lookback = lookback

    @classmethod
    def name(cls) -> str:
        return "margin_divergence"

    @classmethod
    def description(cls) -> str:
        return "融资背离策略：价格调整但量能韧性仍在时布局，过热时退出"

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "fear_threshold": self.fear_threshold,
            "greed_threshold": self.greed_threshold,
            "lookback": self.lookback,
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.fear_threshold = int(params.get("fear_threshold", self.fear_threshold) or self.fear_threshold)
        self.greed_threshold = int(params.get("greed_threshold", self.greed_threshold) or self.greed_threshold)
        self.lookback = max(5, int(params.get("lookback", self.lookback) or self.lookback))

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        signals = np.zeros(len(closes), dtype=np.int8)
        if len(closes) < self.lookback + 5:
            return signals
        volume_arr = np.asarray(volumes if volumes is not None else np.zeros(len(closes)), dtype=float)
        for i in range(self.lookback, len(closes)):
            medium_base = float(closes[i - self.lookback])
            short_base = float(closes[max(0, i - 5)])
            if medium_base <= 0 or short_base <= 0:
                continue
            medium_return = (float(closes[i]) - medium_base) / medium_base
            short_return = (float(closes[i]) - short_base) / short_base
            short_volume = float(np.mean(volume_arr[max(0, i - 4) : i + 1])) if volume_arr.size else 0.0
            long_volume = float(np.mean(volume_arr[i - self.lookback : i + 1])) if volume_arr.size else 0.0
            volume_ratio = short_volume / long_volume if long_volume > 0 else 1.0
            pseudo_fg = 50.0 + short_return * 450.0 + (volume_ratio - 1.0) * 20.0
            divergence = medium_return - short_return
            if pseudo_fg <= self.fear_threshold and divergence > 0.01 and volume_ratio >= 0.95:
                signals[i] = 1
            elif pseudo_fg >= self.greed_threshold or divergence < -0.015:
                signals[i] = -1
        return signals


__all__ = [
    "VolatilityBreakoutStrategy",
    "GapFillStrategy",
    "MeanReversionShortStrategy",
    "SectorRotationStrategy",
    "NorthCapitalTrackStrategy",
    "MarginDivergenceStrategy",
]
