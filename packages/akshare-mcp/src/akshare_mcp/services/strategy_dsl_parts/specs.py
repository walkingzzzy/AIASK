

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
            "selection_basis": "activity_fallback",
            "primary_horizon": 5,
            "overall_skill": None,
            "recent_skill": None,
            "trade_expectancy": None,
            "sample_count": 0,
            "stability_gap": None,
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

    primary_horizon = _resolve_primary_horizon(dsl)
    predictive_ranked: list[
        tuple[tuple[float, float, float, float, int, float], str, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]
    ] = []
    activity_ranked: list[tuple[tuple[float, int, int, int], str, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for name, variant, meta in variants:
        stats = summarize_dsl_activity(market_frame, variant)
        predictive_stats = _summarize_variant_predictive_edge(
            market_frame,
            variant,
            primary_horizon=primary_horizon,
        )
        activity_rank = (
            float(stats.get("score") or 0.0),
            int(min(stats.get("entry_count") or 0, stats.get("exit_count") or 0)),
            int(stats.get("active_days") or 0),
            -int(stats.get("overlap_count") or 0),
        )
        activity_ranked.append((activity_rank, name, variant, meta, stats))
        predictive_rank = (
            float(min(
                predictive_stats.get("recent_skill")
                if predictive_stats.get("recent_skill") is not None
                else -999.0,
                predictive_stats.get("overall_skill")
                if predictive_stats.get("overall_skill") is not None
                else -999.0,
            )),
            float(predictive_stats.get("overall_skill") if predictive_stats.get("overall_skill") is not None else -999.0),
            float(predictive_stats.get("trade_expectancy") if predictive_stats.get("trade_expectancy") is not None else -999.0),
            -float(predictive_stats.get("stability_gap") if predictive_stats.get("stability_gap") is not None else 999.0),
            -int(stats.get("overlap_count") or 0),
            float(stats.get("score") or 0.0),
        )
        predictive_ranked.append((predictive_rank, name, variant, meta, stats, predictive_stats))
    activity_ranked.sort(key=lambda item: item[0], reverse=True)
    predictive_ranked.sort(key=lambda item: item[0], reverse=True)
    _, fallback_name, fallback_variant, fallback_meta, fallback_after = activity_ranked[0]
    fallback_metadata = {
        "applied": False,
        "selected_variant": "original",
        "before": before,
        "after": before,
        "variants_evaluated": len(activity_ranked),
        "selection_basis": "activity_fallback",
        "primary_horizon": primary_horizon,
        "overall_skill": None,
        "recent_skill": None,
        "trade_expectancy": None,
        "sample_count": 0,
        "stability_gap": None,
        **fallback_meta,
    }
    if not predictive_ranked:
        return normalized, fallback_metadata
    _, selected_name, selected_variant, selected_meta, after, predictive_after = predictive_ranked[0]
    if int(predictive_after.get("sample_count") or 0) < 20:
        return normalized, fallback_metadata
    return selected_variant, {
        "applied": selected_name != "original",
        "selected_variant": selected_name,
        "before": before,
        "after": after,
        "variants_evaluated": len(predictive_ranked),
        "selection_basis": "predictive_edge",
        "primary_horizon": primary_horizon,
        "overall_skill": predictive_after.get("overall_skill"),
        "recent_skill": predictive_after.get("recent_skill"),
        "trade_expectancy": predictive_after.get("trade_expectancy"),
        "sample_count": predictive_after.get("sample_count"),
        "stability_gap": predictive_after.get("stability_gap"),
        **selected_meta,
    }


def _resolve_primary_horizon(dsl: dict[str, Any]) -> int:
    metadata = dict((dsl or {}).get("metadata") or {})
    raw_horizon = metadata.get("holding_horizon_days")
    if raw_horizon is None and isinstance(metadata.get("holding_horizon"), dict):
        raw_horizon = dict(metadata.get("holding_horizon") or {}).get("max_days")
    horizon = int(raw_horizon or 5)
    candidates = [5, 10, 20]
    return min(candidates, key=lambda item: abs(item - horizon))


def _summarize_variant_predictive_edge(
    frame: Optional[pd.DataFrame],
    dsl: dict[str, Any],
    *,
    primary_horizon: int,
) -> dict[str, Any]:
    if frame is None or frame.empty or "close" not in frame.columns:
        return {
            "overall_skill": None,
            "recent_skill": None,
            "trade_expectancy": None,
            "sample_count": 0,
            "stability_gap": None,
        }
    normalized = normalize_strategy_dsl(dsl)
    entry_mask, _exit_mask = evaluate_dsl_masks(frame, normalized)
    closes = pd.to_numeric(frame["close"], errors="coerce")
    forward_returns = (closes.shift(-int(primary_horizon)) / closes) - 1.0
    valid_mask = entry_mask & forward_returns.notna().to_numpy(dtype=bool)
    samples = [float(value) for value in forward_returns[valid_mask].tolist() if pd.notna(value)]
    sample_count = len(samples)
    if sample_count <= 0:
        return {
            "overall_skill": None,
            "recent_skill": None,
            "trade_expectancy": None,
            "sample_count": 0,
            "stability_gap": None,
        }
    split = int(max(1, np.floor(sample_count * 0.7)))
    recent_samples = samples[split:] if split < sample_count else samples[-max(1, min(sample_count, int(np.ceil(sample_count * 0.3)))) :]
    overall_skill = round(float(np.mean(samples)), 6)
    recent_skill = round(float(np.mean(recent_samples)), 6) if recent_samples else overall_skill
    trade_expectancy = overall_skill
    stability_gap = round(abs(recent_skill - overall_skill), 6)
    return {
        "overall_skill": overall_skill,
        "recent_skill": recent_skill,
        "trade_expectancy": trade_expectancy,
        "sample_count": sample_count,
        "stability_gap": stability_gap,
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
    if indicator in {"volume_ratio", "turnover_rate"}:
        return 3, 20
    if indicator in {"roc", "stddev", "zscore", "atr", "adx", "rolling_count", "slope"}:
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
    if indicator in {"volume_ratio", "turnover_rate"}:
        return 1.0
    if indicator == "rsi":
        return 50.0
    if indicator == "adx":
        return 20.0
    if indicator in {"roc", "zscore", "stddev", "atr", "upper_shadow_ratio", "slope", "rolling_count"}:
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
            result = {
                'indicator': indicator,
                'field': field,
                'window': max(1, int(payload.get('window') or payload.get('period') or 14)),
            }
            if indicator == "slope":
                result["lookback"] = max(1, int(payload.get("lookback") or payload.get("lag") or 5))
            if indicator == "rolling_count":
                result["condition"] = _normalize_condition(payload.get("condition"))
            return result
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
        normalized = {
            "indicator": indicator,
            "field": field_name,
            "window": max(1, int(node.get("window") or node.get("period") or 14)),
        }
        if indicator == "slope":
            normalized["lookback"] = max(1, int(node.get("lookback") or node.get("lag") or 5))
        if indicator == "rolling_count":
            normalized["condition"] = _normalize_condition(node.get("condition"))
        return normalized
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
