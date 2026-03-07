"""条件收益统计服务。"""

from __future__ import annotations

from typing import Any

import numpy as np

from .screen_engine import engine as screen_engine
from . import screen_conditions as _screen_conditions  # noqa: F401


def _normalize_klines(klines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = [dict(k) for k in (klines or []) if isinstance(k, dict) and k.get("close") is not None]
    if len(items) < 2:
        return items
    first = str(items[0].get("date") or items[0].get("time") or "")
    last = str(items[-1].get("date") or items[-1].get("time") or "")
    if first and last and first > last:
        items.reverse()
    return items


def _normalize_conditions(conditions: Any) -> list[Any]:
    if conditions is None:
        return []
    if isinstance(conditions, str):
        return [conditions]
    if isinstance(conditions, dict):
        if isinstance(conditions.get("conditions"), list):
            return list(conditions.get("conditions") or [])
        if isinstance(conditions.get("items"), list):
            return list(conditions.get("items") or [])
        if conditions.get("id"):
            return [conditions]
        return []
    if isinstance(conditions, (list, tuple)):
        return list(conditions)
    return []


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "win_rate": None,
            "std": None,
            "worst": None,
            "best": None,
        }
    arr = np.asarray(values, dtype=float)
    return {
        "count": int(arr.size),
        "mean": round(float(np.mean(arr)), 6),
        "median": round(float(np.median(arr)), 6),
        "win_rate": round(float(np.mean(arr > 0)), 4),
        "std": round(float(np.std(arr)), 6),
        "worst": round(float(np.min(arr)), 6),
        "best": round(float(np.max(arr)), 6),
    }


def calculate_conditional_returns(
    klines: list[dict[str, Any]],
    conditions: Any,
    forward_days: list[int] | None = None,
    logic: str = "AND",
) -> dict[str, Any]:
    ordered = _normalize_klines(klines)
    normalized_conditions = _normalize_conditions(conditions)
    days = sorted({max(1, int(day)) for day in (forward_days or [5, 10, 20])})
    if not normalized_conditions:
        return {
            "condition_matches": 0,
            "evaluation_count": 0,
            "logic": str(logic or "AND").upper(),
            "conditions": [],
            "forward_returns": {f"{day}d": _stats([]) for day in days},
            "recent_matches": [],
        }

    per_day: dict[int, list[float]] = {day: [] for day in days}
    matches: list[dict[str, Any]] = []
    logic_value = str(logic or "AND").upper()

    for idx in range(len(ordered) - 1):
        window = ordered[: idx + 1]
        evaluated = screen_engine.evaluate_multi(normalized_conditions, window, logic=logic_value)
        if not evaluated.get("match"):
            continue
        current_close = float(window[-1].get("close") or 0)
        if current_close <= 0:
            continue

        one_match = {
            "date": str(window[-1].get("date") or ""),
            "details": evaluated.get("details", {}),
            "forward_returns": {},
        }
        any_forward = False
        for day in days:
            future_idx = idx + day
            if future_idx >= len(ordered):
                continue
            future_close = float(ordered[future_idx].get("close") or 0)
            if future_close <= 0:
                continue
            ret = (future_close - current_close) / current_close
            per_day[day].append(float(ret))
            one_match["forward_returns"][f"{day}d"] = round(float(ret), 6)
            any_forward = True

        if any_forward:
            matches.append(one_match)

    return {
        "condition_matches": len(matches),
        "evaluation_count": max(0, len(ordered) - max(days, default=1)),
        "logic": logic_value,
        "conditions": normalized_conditions,
        "forward_returns": {f"{day}d": _stats(per_day[day]) for day in days},
        "recent_matches": matches[-5:],
    }