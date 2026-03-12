"""策略 DSL：规范化、编译与条件求值。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

import numpy as np
import pandas as pd

SUPPORTED_DSL_VERSION = "1.0"
SUPPORTED_FIELDS = {"open", "high", "low", "close", "volume"}
SUPPORTED_INDICATORS = {
    "sma", "ema", "roc", "rsi", "stddev", "zscore",
    "highest", "lowest", "volume_ratio", "atr",
}
SUPPORTED_COMPARE_OPS = {"gt", "gte", "lt", "lte", "eq", "ne", "cross_above", "cross_below"}
SUPPORTED_BINARY_OPS = {"add", "sub", "mul", "div", "max", "min"}


def build_ohlcv_frame(klines: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(klines or []))
    if frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    aliases = {
        "open": ["open", "开盘"],
        "high": ["high", "最高"],
        "low": ["low", "最低"],
        "close": ["close", "收盘", "close_price"],
        "volume": ["volume", "vol", "成交量"],
    }
    normalized = pd.DataFrame(index=frame.index)
    lower_map = {str(column).lower(): str(column) for column in frame.columns}
    for target, options in aliases.items():
        source = None
        for alias in options:
            source = lower_map.get(str(alias).lower())
            if source is not None:
                break
        if source is not None:
            normalized[target] = pd.to_numeric(frame[source], errors="coerce")
    if "close" not in normalized:
        normalized["close"] = 0.0
    normalized["open"] = normalized.get("open", normalized["close"]).fillna(normalized["close"])
    normalized["high"] = normalized.get("high", normalized["close"]).fillna(normalized["close"])
    normalized["low"] = normalized.get("low", normalized["close"]).fillna(normalized["close"])
    normalized["volume"] = normalized.get("volume", 0.0).fillna(0.0)
    return normalized.astype(float)


def build_close_volume_frame(closes: np.ndarray, volumes: Optional[np.ndarray] = None) -> pd.DataFrame:
    close_arr = np.asarray([] if closes is None else closes, dtype=float)
    volume_arr = np.asarray(volumes if volumes is not None else np.zeros(len(close_arr)), dtype=float)
    if len(volume_arr) != len(close_arr):
        volume_arr = np.resize(volume_arr, len(close_arr)) if len(close_arr) else np.array([], dtype=float)
    frame = pd.DataFrame({
        "open": close_arr,
        "high": close_arr,
        "low": close_arr,
        "close": close_arr,
        "volume": volume_arr,
    })
    return frame.astype(float)


def normalize_strategy_dsl(dsl: dict[str, Any]) -> dict[str, Any]:
    payload = dict(dsl or {})
    entry = _normalize_condition(payload.get("entry"))
    if not entry:
        raise ValueError("dsl.entry is required")
    exit_rule = _normalize_condition(payload.get("exit") or {
        "any": [{
            "op": "cross_below",
            "left": {"indicator": "sma", "field": "close", "window": 5},
            "right": {"indicator": "sma", "field": "close", "window": 20},
        }],
    })
    return {
        "version": str(payload.get("version") or SUPPORTED_DSL_VERSION),
        "timeframe": str(payload.get("timeframe") or "daily"),
        "entry": entry,
        "exit": exit_rule,
        "metadata": dict(payload.get("metadata") or {}),
        "risk_rules": dict(payload.get("risk_rules") or {}),
    }


def compile_strategy_blueprint(
    blueprint: dict[str, Any],
    market_frame: Optional[pd.DataFrame] = None,
    tune_for_factory: bool = False,
) -> dict[str, Any]:
    payload = dict(blueprint or {})
    if payload.get("dsl") or payload.get("entry"):
        dsl = payload.get("dsl") or {
            "version": payload.get("version"),
            "timeframe": payload.get("timeframe"),
            "entry": payload.get("entry"),
            "exit": payload.get("exit"),
            "metadata": payload.get("metadata") or {},
            "risk_rules": payload.get("risk_rules") or {},
        }
        normalized = normalize_strategy_dsl(dsl)
        tuning = {
            "applied": False,
            "selected_variant": "original",
            "before": summarize_dsl_activity(market_frame, normalized),
            "after": summarize_dsl_activity(market_frame, normalized),
            "variants_evaluated": 1,
        }
        if tune_for_factory and market_frame is not None and not market_frame.empty:
            normalized, tuning = tune_strategy_dsl(normalized, market_frame)
        return {
            "strategy_type": "dsl_rule",
            "params": {
                "dsl": normalized,
                "risk_rules": dict(payload.get("risk_rules") or normalized.get("risk_rules") or {}),
            },
            "name": str(payload.get("name") or "外部 AI DSL 策略"),
            "description": str(payload.get("description") or payload.get("rationale") or "外部 AI 生成的 DSL 策略"),
            "tags": list(dict.fromkeys(list(payload.get("tags") or []) + ["dsl_rule"])),
            "metadata": {
                "rationale": payload.get("rationale"),
                "dsl": normalized,
                "dsl_tuning": tuning,
                "dsl_activity": tuning.get("after") or summarize_dsl_activity(market_frame, normalized),
            },
        }

    strategy_type = str(payload.get("strategy_type") or "").strip()
    params = dict(payload.get("params") or {})
    if not strategy_type or not params:
        raise ValueError("strategy blueprint must contain dsl or strategy_type+params")
    return {
        "strategy_type": strategy_type,
        "params": params,
        "name": str(payload.get("name") or f"外部 AI {strategy_type} 策略"),
        "description": str(payload.get("description") or payload.get("rationale") or "外部 AI 生成策略"),
        "tags": list(payload.get("tags") or []),
        "metadata": {
            "rationale": payload.get("rationale"),
        },
    }


def evaluate_dsl_masks(frame: pd.DataFrame, dsl: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    normalized = normalize_strategy_dsl(dsl)
    entry_mask = _eval_condition(frame, normalized["entry"]).fillna(False).to_numpy(dtype=bool)
    exit_mask = _eval_condition(frame, normalized["exit"]).fillna(False).to_numpy(dtype=bool)
    return entry_mask, exit_mask


def summarize_dsl_activity(frame: Optional[pd.DataFrame], dsl: dict[str, Any]) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {
            "entry_count": 0,
            "exit_count": 0,
            "active_days": 0,
            "overlap_count": 0,
            "score": 0.0,
        }
    normalized = normalize_strategy_dsl(dsl)
    entry_mask, exit_mask = evaluate_dsl_masks(frame, normalized)
    overlap = entry_mask & exit_mask
    entry_count = int(np.count_nonzero(entry_mask))
    exit_count = int(np.count_nonzero(exit_mask))
    active_days = int(np.count_nonzero(entry_mask | exit_mask))
    overlap_count = int(np.count_nonzero(overlap))
    return {
        "entry_count": entry_count,
        "exit_count": exit_count,
        "active_days": active_days,
        "overlap_count": overlap_count,
        "score": round(_dsl_activity_score(entry_count, exit_count, active_days, overlap_count), 4),
    }


def tune_strategy_dsl(dsl: dict[str, Any], market_frame: Optional[pd.DataFrame]) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = normalize_strategy_dsl(dsl)
    before = summarize_dsl_activity(market_frame, normalized)
    if market_frame is None or market_frame.empty:
        return normalized, {
            "applied": False,
            "selected_variant": "original",
            "before": before,
            "after": before,
            "variants_evaluated": 1,
        }

    variants: list[tuple[str, dict[str, Any], dict[str, Any]]] = [
        ("original", normalized, {"window_scale": 1.0, "threshold_scale": 1.0}),
    ]
    for scale in (0.85, 0.7, 0.55):
        scaled = _scale_dsl_windows(normalized, scale)
        variants.append((f"window_scale_{scale:.2f}", scaled, {"window_scale": scale, "threshold_scale": 1.0}))
    base_variants = list(variants)
    for base_name, base_dsl, base_meta in base_variants:
        for scale in (0.9, 0.75):
            relaxed = _relax_dsl_thresholds(base_dsl, scale)
            variants.append((
                f"{base_name}_threshold_scale_{scale:.2f}",
                relaxed,
                {**base_meta, "threshold_scale": scale},
            ))

    structural_variants = list(variants)
    for base_name, base_dsl, base_meta in structural_variants:
        softened = _soften_cross_operators(base_dsl)
        if softened != base_dsl:
            variants.append((
                f"{base_name}_soft_cross",
                softened,
                {**base_meta, "cross_mode": "state"},
            ))
            relaxed_groups = _soften_condition_groups(softened)
            if relaxed_groups != softened:
                variants.append((
                    f"{base_name}_soft_cross_relaxed_group",
                    relaxed_groups,
                    {**base_meta, "cross_mode": "state", "group_mode": "relaxed_any"},
                ))

    ranked: list[tuple[tuple[float, int, int, int], str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for name, variant, meta in variants:
        stats = summarize_dsl_activity(market_frame, variant)
        rank = (
            float(stats.get("score") or 0.0),
            int(min(stats.get("entry_count") or 0, stats.get("exit_count") or 0)),
            int(stats.get("active_days") or 0),
            -int(stats.get("overlap_count") or 0),
        )
        ranked.append((rank, name, variant, meta, stats))
    ranked.sort(key=lambda item: item[0], reverse=True)
    _, selected_name, selected_variant, selected_meta, after = ranked[0]
    return selected_variant, {
        "applied": selected_name != "original",
        "selected_variant": selected_name,
        "before": before,
        "after": after,
        "variants_evaluated": len(ranked),
        **selected_meta,
    }


def _dsl_activity_score(entry_count: int, exit_count: int, active_days: int, overlap_count: int) -> float:
    return (
        _count_band_score(entry_count)
        + _count_band_score(exit_count)
        + min(active_days, 24) / 24.0
        - min(overlap_count, 6) * 0.25
    )


def _count_band_score(count: int) -> float:
    if count <= 0:
        return 0.0
    if 2 <= count <= 18:
        return 2.5
    if count < 2:
        return float(count)
    return max(0.5, 18.0 / float(count))


def _scale_dsl_windows(dsl: dict[str, Any], scale: float) -> dict[str, Any]:
    payload = deepcopy(normalize_strategy_dsl(dsl))
    payload["entry"] = _transform_condition(payload.get("entry") or {}, expr_transform=lambda expr: _scale_expr_window(expr, scale))
    payload["exit"] = _transform_condition(payload.get("exit") or {}, expr_transform=lambda expr: _scale_expr_window(expr, scale))
    return normalize_strategy_dsl(payload)


def _relax_dsl_thresholds(dsl: dict[str, Any], scale: float) -> dict[str, Any]:
    payload = deepcopy(normalize_strategy_dsl(dsl))
    payload["entry"] = _transform_condition(payload.get("entry") or {}, condition_transform=lambda cond: _relax_condition_threshold(cond, scale))
    payload["exit"] = _transform_condition(payload.get("exit") or {}, condition_transform=lambda cond: _relax_condition_threshold(cond, scale))
    return normalize_strategy_dsl(payload)


def _transform_condition(
    node: dict[str, Any],
    *,
    expr_transform=None,
    condition_transform=None,
) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    if "all" in node:
        return {"all": [_transform_condition(item, expr_transform=expr_transform, condition_transform=condition_transform) for item in list(node.get("all") or [])]}
    if "any" in node:
        return {"any": [_transform_condition(item, expr_transform=expr_transform, condition_transform=condition_transform) for item in list(node.get("any") or [])]}
    if "not" in node:
        return {"not": _transform_condition(dict(node.get("not") or {}), expr_transform=expr_transform, condition_transform=condition_transform)}
    transformed = {
        "op": str(node.get("op") or "").strip().lower(),
        "left": _transform_expr(dict(node.get("left") or {}), transform=expr_transform),
        "right": _transform_expr(dict(node.get("right") or {}), transform=expr_transform),
    }
    return condition_transform(transformed) if callable(condition_transform) else transformed


def _transform_expr(node: dict[str, Any], *, transform=None) -> dict[str, Any]:
    expr = dict(node or {})
    binary = expr.get("binary")
    if isinstance(binary, dict):
        expr["binary"] = {
            "op": str(binary.get("op") or "").strip().lower(),
            "left": _transform_expr(dict(binary.get("left") or {}), transform=transform),
            "right": _transform_expr(dict(binary.get("right") or {}), transform=transform),
        }
    if callable(transform):
        expr = transform(expr)
    return expr


def _scale_expr_window(expr: dict[str, Any], scale: float) -> dict[str, Any]:
    payload = dict(expr or {})
    indicator = str(payload.get("indicator") or "").strip().lower()
    if indicator in SUPPORTED_INDICATORS:
        window = int(payload.get("window") or 14)
        min_window, max_window = _indicator_window_bounds(indicator)
        scaled = int(round(window * float(scale or 1.0)))
        payload["window"] = max(min_window, min(max_window, scaled))
    return payload


def _indicator_window_bounds(indicator: str) -> tuple[int, int]:
    if indicator == "rsi":
        return 5, 21
    if indicator == "volume_ratio":
        return 3, 20
    if indicator in {"roc", "stddev", "zscore", "atr"}:
        return 3, 30
    if indicator in {"highest", "lowest"}:
        return 5, 40
    return 3, 40


def _relax_condition_threshold(cond: dict[str, Any], scale: float) -> dict[str, Any]:
    payload = dict(cond or {})
    op = str(payload.get("op") or "").strip().lower()
    right = dict(payload.get("right") or {})
    if "value" in right:
        baseline = _expr_neutral_value(payload.get("left") or {})
        right["value"] = round(_relax_threshold_value(float(right.get("value") or 0.0), baseline, op, scale), 6)
        payload["right"] = right
    return payload


def _soften_cross_operators(dsl: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(normalize_strategy_dsl(dsl))
    payload["entry"] = _transform_condition(payload.get("entry") or {}, condition_transform=_soften_cross_condition)
    payload["exit"] = _transform_condition(payload.get("exit") or {}, condition_transform=_soften_cross_condition)
    return normalize_strategy_dsl(payload)


def _soften_cross_condition(cond: dict[str, Any]) -> dict[str, Any]:
    payload = dict(cond or {})
    op = str(payload.get("op") or "").strip().lower()
    if op == "cross_above":
        payload["op"] = "gt"
    elif op == "cross_below":
        payload["op"] = "lt"
    return payload


def _soften_condition_groups(dsl: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(normalize_strategy_dsl(dsl))
    payload["entry"] = _soften_group_node(payload.get("entry") or {})
    payload["exit"] = _soften_group_node(payload.get("exit") or {})
    return normalize_strategy_dsl(payload)


def _soften_group_node(node: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    if "all" in node:
        items = [_soften_group_node(item) for item in list(node.get("all") or [])]
        if len(items) > 1:
            return {"any": items}
        return {"all": items}
    if "any" in node:
        return {"any": [_soften_group_node(item) for item in list(node.get("any") or [])]}
    if "not" in node:
        return {"not": _soften_group_node(dict(node.get("not") or {}))}
    return dict(node)


def _expr_neutral_value(expr: dict[str, Any]) -> float:
    indicator = str((expr or {}).get("indicator") or "").strip().lower()
    if indicator == "volume_ratio":
        return 1.0
    if indicator == "rsi":
        return 50.0
    if indicator in {"roc", "zscore", "stddev", "atr"}:
        return 0.0
    return 0.0


def _relax_threshold_value(value: float, baseline: float, op: str, scale: float) -> float:
    factor = float(scale or 1.0)
    if op in {"gt", "gte"} and value > baseline:
        return baseline + (value - baseline) * factor
    if op in {"lt", "lte"} and value < baseline:
        return baseline + (value - baseline) * factor
    return value


def _expand_shorthand_condition(node: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    for op in SUPPORTED_COMPARE_OPS:
        if op not in node:
            continue
        payload = node.get(op)
        if isinstance(payload, (list, tuple)) and len(payload) >= 2:
            return {
                'op': op,
                'left': _normalize_expr(payload[0]),
                'right': _normalize_expr(payload[1]),
            }
        if isinstance(payload, dict):
            left = payload.get('left') if 'left' in payload else payload.get('a')
            right = payload.get('right') if 'right' in payload else payload.get('b')
            return {
                'op': op,
                'left': _normalize_expr(left),
                'right': _normalize_expr(right),
            }
    return {}


def _expand_shorthand_expr(node: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    for indicator in SUPPORTED_INDICATORS:
        if indicator not in node:
            continue
        payload = node.get(indicator)
        if isinstance(payload, dict):
            field = str(payload.get('field') or 'close').strip().lower() or 'close'
            if field not in SUPPORTED_FIELDS:
                field = 'close'
            return {
                'indicator': indicator,
                'field': field,
                'window': max(1, int(payload.get('window') or payload.get('period') or 14)),
            }
        if isinstance(payload, (int, float)):
            return {
                'indicator': indicator,
                'field': 'close',
                'window': max(1, int(payload or 14)),
            }
        if isinstance(payload, str):
            try:
                window = max(1, int(float(payload)))
                return {'indicator': indicator, 'field': 'close', 'window': window}
            except Exception:
                pass
            field = payload.strip().lower()
            if field in SUPPORTED_FIELDS:
                return {'indicator': indicator, 'field': field, 'window': 14}
    for op in SUPPORTED_BINARY_OPS:
        if op not in node:
            continue
        payload = node.get(op)
        if isinstance(payload, (list, tuple)) and len(payload) >= 2:
            return {
                'binary': {
                    'op': op,
                    'left': _normalize_expr(payload[0]),
                    'right': _normalize_expr(payload[1]),
                }
            }
        if isinstance(payload, dict):
            left = payload.get('left') if 'left' in payload else payload.get('a')
            right = payload.get('right') if 'right' in payload else payload.get('b')
            return {
                'binary': {
                    'op': op,
                    'left': _normalize_expr(left),
                    'right': _normalize_expr(right),
                }
            }
    return {}


def _normalize_condition(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    if "all" in node:
        items = []
        for item in list(node.get("all") or []):
            normalized = _normalize_condition(item)
            if normalized:
                items.append(normalized)
        return {"all": items}
    if "any" in node:
        items = []
        for item in list(node.get("any") or []):
            normalized = _normalize_condition(item)
            if normalized:
                items.append(normalized)
        return {"any": items}
    if "not" in node:
        child = _normalize_condition(node.get("not"))
        return {"not": child} if child else {}
    op = str(node.get("op") or "").strip().lower()
    if op in SUPPORTED_COMPARE_OPS:
        return {
            "op": op,
            "left": _normalize_expr(node.get("left")),
            "right": _normalize_expr(node.get("right")),
        }
    return _expand_shorthand_condition(node)


def _normalize_expr(node: Any) -> dict[str, Any]:
    if isinstance(node, (int, float)):
        return {"value": float(node)}
    if isinstance(node, str):
        text = node.strip().lower()
        if text in SUPPORTED_FIELDS:
            return {"field": text}
        try:
            return {"value": float(text)}
        except Exception:
            return {"field": "close"}
    if not isinstance(node, dict):
        return {"value": 0.0}
    if "value" in node:
        return {"value": float(node.get("value") or 0.0)}
    indicator = str(node.get("indicator") or "").strip().lower()
    if indicator in SUPPORTED_INDICATORS:
        field_name = str(node.get("field") or "close").strip().lower() or "close"
        if field_name not in SUPPORTED_FIELDS:
            field_name = "close"
        return {
            "indicator": indicator,
            "field": field_name,
            "window": max(1, int(node.get("window") or node.get("period") or 14)),
        }
    field = str(node.get("field") or node.get("column") or "").strip().lower()
    if field in SUPPORTED_FIELDS:
        return {"field": field}
    shorthand_expr = _expand_shorthand_expr(node)
    if shorthand_expr:
        return shorthand_expr
    if "binary" in node and isinstance(node.get("binary"), dict):
        node = node.get("binary")
    op = str(node.get("op") or "").strip().lower()
    if op in SUPPORTED_BINARY_OPS and "left" in node and "right" in node:
        return {
            "binary": {
                "op": op,
                "left": _normalize_expr(node.get("left")),
                "right": _normalize_expr(node.get("right")),
            }
        }
    return {"field": "close"}


def _eval_condition(frame: pd.DataFrame, node: dict[str, Any]) -> pd.Series:
    if not node:
        return pd.Series(False, index=frame.index)
    if "all" in node:
        items = list(node.get("all") or [])
        if not items:
            return pd.Series(False, index=frame.index)
        result = pd.Series(True, index=frame.index)
        for item in items:
            result &= _eval_condition(frame, item)
        return result
    if "any" in node:
        items = list(node.get("any") or [])
        if not items:
            return pd.Series(False, index=frame.index)
        result = pd.Series(False, index=frame.index)
        for item in items:
            result |= _eval_condition(frame, item)
        return result
    if "not" in node:
        return ~_eval_condition(frame, dict(node.get("not") or {}))

    left = _eval_expr(frame, dict(node.get("left") or {}))
    right = _eval_expr(frame, dict(node.get("right") or {}))
    op = str(node.get("op") or "").strip().lower()
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "eq":
        return pd.Series(np.isclose(left, right), index=frame.index)
    if op == "ne":
        return pd.Series(~np.isclose(left, right), index=frame.index)
    if op == "cross_above":
        return (left.shift(1) <= right.shift(1)) & (left > right)
    if op == "cross_below":
        return (left.shift(1) >= right.shift(1)) & (left < right)
    return pd.Series(False, index=frame.index)


def _eval_expr(frame: pd.DataFrame, node: dict[str, Any]) -> pd.Series:
    if "value" in node:
        return pd.Series(float(node.get("value") or 0.0), index=frame.index, dtype=float)
    indicator = str(node.get("indicator") or "").strip().lower()
    if indicator in SUPPORTED_INDICATORS:
        series = _eval_expr(frame, {"field": node.get("field") or "close"})
        window = max(1, int(node.get("window") or 14))
        if indicator == "sma":
            return series.rolling(window).mean()
        if indicator == "ema":
            return series.ewm(span=window, adjust=False).mean()
        if indicator == "roc":
            return series.pct_change(window)
        if indicator == "rsi":
            delta = series.diff()
            up = delta.clip(lower=0.0)
            down = -delta.clip(upper=0.0)
            avg_gain = up.rolling(window).mean()
            avg_loss = down.rolling(window).mean()
            rs = avg_gain / np.maximum(avg_loss, 1e-9)
            return 100.0 - (100.0 / (1.0 + rs))
        if indicator == "stddev":
            return series.rolling(window).std()
        if indicator == "zscore":
            mean = series.rolling(window).mean()
            std = series.rolling(window).std()
            return (series - mean) / np.maximum(std, 1e-9)
        if indicator == "highest":
            return series.rolling(window).max()
        if indicator == "lowest":
            return series.rolling(window).min()
        if indicator == "volume_ratio":
            volume = _eval_expr(frame, {"field": "volume"})
            return volume / np.maximum(volume.rolling(window).mean(), 1e-9)
        if indicator == "atr":
            high = _eval_expr(frame, {"field": "high"})
            low = _eval_expr(frame, {"field": "low"})
            close = _eval_expr(frame, {"field": "close"})
            prev_close = close.shift(1)
            tr = pd.concat([
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ], axis=1).max(axis=1)
            return tr.rolling(window).mean()
    field = str(node.get("field") or "").strip().lower()
    if field in SUPPORTED_FIELDS:
        return pd.to_numeric(frame.get(field, pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
    binary = node.get("binary")
    if isinstance(binary, dict):
        left = _eval_expr(frame, dict(binary.get("left") or {}))
        right = _eval_expr(frame, dict(binary.get("right") or {}))
        op = str(binary.get("op") or "").strip().lower()
        if op == "add":
            return left + right
        if op == "sub":
            return left - right
        if op == "mul":
            return left * right
        if op == "div":
            denom = right.abs().clip(lower=1e-9)
            return left / denom
        if op == "max":
            return pd.concat([left, right], axis=1).max(axis=1)
        if op == "min":
            return pd.concat([left, right], axis=1).min(axis=1)
    return pd.Series(0.0, index=frame.index, dtype=float)
