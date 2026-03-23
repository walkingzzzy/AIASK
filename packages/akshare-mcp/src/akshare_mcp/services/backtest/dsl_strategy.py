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

    def _apply_risk_rules(
        self,
        frame,
        entry_mask: np.ndarray,
        exit_mask: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        closes = np.asarray(frame["close"].to_numpy(dtype=float), dtype=float)
        if len(closes) <= 0:
            return entry_mask, exit_mask

        stop_loss_pct = float(self.risk_rules.get("stop_loss_pct") or self.risk_rules.get("stop_loss") or 0.0)
        take_profit_pct = float(self.risk_rules.get("take_profit_pct") or self.risk_rules.get("take_profit") or 0.0)
        max_holding_days = int(self.risk_rules.get("max_holding_days") or 0)
        cooldown_days = int(self.risk_rules.get("cooldown_days") or 0)
        if stop_loss_pct <= 0 and take_profit_pct <= 0 and max_holding_days <= 0 and cooldown_days <= 0:
            return entry_mask, exit_mask

        adjusted_entry = np.asarray(entry_mask, dtype=bool).copy()
        adjusted_exit = np.asarray(exit_mask, dtype=bool).copy()
        in_position = False
        entry_price = 0.0
        holding_days = 0
        cooldown_left = 0

        for idx in range(len(closes)):
            if cooldown_left > 0 and not in_position:
                adjusted_entry[idx] = False
                cooldown_left -= 1
            price = float(closes[idx] or 0.0)
            if not in_position:
                if adjusted_entry[idx] and price > 0:
                    in_position = True
                    entry_price = price
                    holding_days = 0
                continue

            holding_days += 1
            forced_exit = False
            if stop_loss_pct > 0 and entry_price > 0:
                forced_exit = forced_exit or (price / entry_price - 1.0) <= -abs(stop_loss_pct)
            if take_profit_pct > 0 and entry_price > 0:
                forced_exit = forced_exit or (price / entry_price - 1.0) >= abs(take_profit_pct)
            if max_holding_days > 0 and holding_days >= max_holding_days:
                forced_exit = True
            if forced_exit:
                adjusted_exit[idx] = True

            if adjusted_exit[idx]:
                in_position = False
                entry_price = 0.0
                holding_days = 0
                cooldown_left = max(cooldown_left, cooldown_days)
                adjusted_entry[idx] = False

        overlap = adjusted_entry & adjusted_exit
        adjusted_entry[overlap] = False
        adjusted_exit[overlap] = False
        return adjusted_entry, adjusted_exit

    def generate_signals(self, closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> np.ndarray:
        frame = build_close_volume_frame(closes, volumes)
        entry_mask, exit_mask = evaluate_dsl_masks(frame, self.dsl)
        entry_mask, exit_mask = self._apply_risk_rules(frame, entry_mask, exit_mask)
        signals = np.zeros(len(frame), dtype=np.int8)
        signals[entry_mask] = 1
        signals[exit_mask] = -1
        overlap = entry_mask & exit_mask
        signals[overlap] = 0
        return signals

    def generate_entry_exit_masks_from_klines(self, klines: list[dict]) -> tuple[np.ndarray, np.ndarray]:
        frame = build_ohlcv_frame(list(klines or []))
        entry_mask, exit_mask = evaluate_dsl_masks(frame, self.dsl)
        return self._apply_risk_rules(frame, entry_mask, exit_mask)
