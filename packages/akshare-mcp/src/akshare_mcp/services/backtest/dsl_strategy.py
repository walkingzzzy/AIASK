"""DSL 规则策略。"""

from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from ..strategy_dsl import build_close_volume_frame, build_ohlcv_frame, evaluate_dsl_masks, normalize_strategy_dsl
from .strategy_base import IStrategy


class DslRuleStrategy(IStrategy):
    def __init__(self, dsl: Optional[dict] = None, risk_rules: Optional[dict] = None):
        self.dsl = normalize_strategy_dsl(dsl or {
            "entry": {"any": [{"op": "gt", "left": {"field": "close"}, "right": {"indicator": "sma", "field": "close", "window": 20}}]},
            "exit": {"any": [{"op": "lt", "left": {"field": "close"}, "right": {"indicator": "sma", "field": "close", "window": 20}}]},
        })
        self.risk_rules = dict(risk_rules or {})

    @classmethod
    def name(cls) -> str:
        return "dsl_rule"

    @classmethod
    def description(cls) -> str:
        return "DSL 规则策略：基于条件表达式组合生成买卖信号"

    def get_parameters(self) -> Dict[str, Any]:
        return {"dsl": self.dsl, "risk_rules": self.risk_rules}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        payload = dict(params or {})
        self.dsl = normalize_strategy_dsl(payload.get("dsl") or self.dsl)
        self.risk_rules = dict(payload.get("risk_rules") or self.risk_rules or {})

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        frame = build_close_volume_frame(closes, volumes)
        entry_mask, exit_mask = evaluate_dsl_masks(frame, self.dsl)
        signals = np.zeros(len(frame), dtype=np.int8)
        signals[entry_mask] = 1
        signals[exit_mask] = -1
        overlap = entry_mask & exit_mask
        signals[overlap] = 0
        return signals

    def generate_entry_exit_masks_from_klines(self, klines: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        frame = build_ohlcv_frame(list(klines or []))
        return evaluate_dsl_masks(frame, self.dsl)
