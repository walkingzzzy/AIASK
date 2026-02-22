"""单因子策略族 — 基于技术面近似的因子排名信号

提供 SingleFactorStrategy 抽象基类和三个具体子类:
- ValueFactorStrategy: 价值因子（负动量 + 均值回归）
- QualityFactorStrategy: 质量因子（收益稳定性 + 低波动）
- GrowthFactorStrategy: 成长因子（收益加速度）

所有策略仅使用 closes/volumes 作为输入，通过技术面指标近似基本面因子。
"""

from abc import abstractmethod
from typing import Any, Dict, Optional

import numpy as np

from .strategy_base import IStrategy


class SingleFactorStrategy(IStrategy):
    """单因子策略抽象基类 — 滚动窗口内按因子分位数排名生成信号"""

    def __init__(self):
        self._lookback = 60
        self._buy_quantile = 0.8
        self._sell_quantile = 0.2

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "lookback": self._lookback,
            "buy_quantile": self._buy_quantile,
            "sell_quantile": self._sell_quantile,
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self._lookback = max(10, int(params.get("lookback", self._lookback)))
        self._buy_quantile = float(params.get("buy_quantile", self._buy_quantile))
        self._sell_quantile = float(params.get("sell_quantile", self._sell_quantile))

    @abstractmethod
    def _compute_factor(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        """计算因子值序列，返回与 closes 等长的数组（NaN 表示无效）"""
        ...

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        n = len(closes)
        signals = np.zeros(n, dtype=np.int8)
        if n < self._lookback + 2:
            return signals
        factor = self._compute_factor(closes, volumes)
        for i in range(self._lookback, n):
            window = factor[max(0, i - self._lookback):i + 1]
            valid = window[np.isfinite(window)]
            if len(valid) < 5:
                continue
            rank = float(np.sum(valid < factor[i])) / len(valid)
            if rank >= self._buy_quantile:
                signals[i] = 1
            elif rank <= self._sell_quantile:
                signals[i] = -1
        return signals


class ValueFactorStrategy(SingleFactorStrategy):
    """价值因子 — 负动量 + 均值回归偏离度（技术面近似）"""

    @classmethod
    def name(cls) -> str:
        return "value_factor"

    @classmethod
    def description(cls) -> str:
        return "价值因子策略：低动量+均值回归倾向越强，价值得分越高"

    def _compute_factor(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        n = len(closes)
        factor = np.full(n, np.nan)
        lb = min(self._lookback, 60)
        for i in range(lb, n):
            ret = (closes[i] - closes[i - lb]) / closes[i - lb] if closes[i - lb] > 0 else 0
            ma = float(np.mean(closes[i - lb:i + 1]))
            deviation = (closes[i] - ma) / ma if ma > 0 else 0
            factor[i] = -(ret * 0.5 + deviation * 0.5)
        return factor


class QualityFactorStrategy(SingleFactorStrategy):
    """质量因子 — 收益稳定性 + 低波动（技术面近似）"""

    @classmethod
    def name(cls) -> str:
        return "quality_factor"

    @classmethod
    def description(cls) -> str:
        return "质量因子策略：收益稳定、波动低的股票得分高"

    def _compute_factor(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        n = len(closes)
        factor = np.full(n, np.nan)
        lb = min(self._lookback, 60)
        for i in range(lb, n):
            window = closes[i - lb:i + 1]
            rets = np.diff(window) / window[:-1]
            if len(rets) < 2:
                continue
            stability = -float(np.std(rets))
            positive_ratio = float(np.mean(rets > 0))
            factor[i] = stability * 0.6 + positive_ratio * 0.4
        return factor


class GrowthFactorStrategy(SingleFactorStrategy):
    """成长因子 — 收益加速度（技术面近似）"""

    @classmethod
    def name(cls) -> str:
        return "growth_factor"

    @classmethod
    def description(cls) -> str:
        return "成长因子策略：近期收益加速的股票得分高"

    def _compute_factor(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        n = len(closes)
        factor = np.full(n, np.nan)
        lb = min(self._lookback, 60)
        for i in range(lb, n):
            ret_short = (closes[i] - closes[i - 20]) / closes[i - 20] if i >= 20 and closes[i - 20] > 0 else 0
            ret_long = (closes[i] - closes[i - lb]) / closes[i - lb] if closes[i - lb] > 0 else 0
            factor[i] = ret_short - ret_long / max(lb / 20, 1)
        return factor