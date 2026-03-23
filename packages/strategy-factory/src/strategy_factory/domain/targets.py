"""策略工厂状态、任务合同与目标池工具。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import REPRESENTATIVE_STOCKS


async def _update_strategy_status(db, strategy_id: str, status: str, **kwargs) -> None:
    try:
        await db.update_strategy_status(strategy_id, status, **kwargs)
    except TypeError:
        await db.update_strategy_status(strategy_id, status)


def _normalize_target_codes(values: Any, limit: int = 12) -> List[str]:
    codes: List[str] = []
    seen: set[str] = set()

    def visit(value: Any):
        if value is None:
            return
        if isinstance(value, dict):
            for key in ("code", "symbol", "stock_code"):
                if value.get(key) is not None:
                    visit(value.get(key))
            for key in ("codes", "symbols", "stock_codes", "target_symbols"):
                if value.get(key) is not None:
                    visit(value.get(key))
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        raw = str(value or "").strip()
        if not raw:
            return
        if any(sep in raw for sep in [",", ";", "|", "\n", "\t", " "]):
            normalized = raw.replace(";", ",").replace("|", ",").replace("\n", ",").replace("\t", ",").replace(" ", ",")
            for part in normalized.split(","):
                visit(part)
            return
        code = raw.split(".")[0].strip()
        if not code or code in seen:
            return
        seen.add(code)
        codes.append(code)

    visit(values)
    return codes[: max(1, min(int(limit or 12), 40))]


def _normalize_string_list(values: Any, limit: int = 12) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        raw = str(value or "").strip()
        if not raw:
            return
        if any(sep in raw for sep in [",", ";", "|", "\n", "\t"]):
            normalized = raw.replace(";", ",").replace("|", ",").replace("\n", ",").replace("\t", ",")
            for part in normalized.split(","):
                visit(part)
            return
        if raw in seen:
            return
        seen.add(raw)
        items.append(raw)

    visit(values)
    return items[: max(1, min(int(limit or 12), 40))]


def _task_default_target_symbol_policy(task_source: str) -> str:
    return "strict_intersection" if task_source == "event_driven" else "prefer_intersection"


def _task_default_universe_expansion_policy(task_source: str) -> str:
    return "allow_same_theme_only" if task_source == "event_driven" else "allow_market_fallback"


def _task_default_validation_focus(task_source: str) -> str:
    return "event_target_only" if task_source == "event_driven" else "target_plus_representative"


def _task_default_preference_strength(task_source: str) -> str:
    return "medium" if task_source == "event_driven" else "soft"


def _task_default_preference_reason(task_source: str, preferred_strategy_types: list[str]) -> str:
    if task_source == "event_driven":
        if preferred_strategy_types:
            return f"event_theme_bias:{','.join(preferred_strategy_types[:3])}"
        return "event_theme_bias"
    if preferred_strategy_types:
        return f"snapshot_regime_bias:{','.join(preferred_strategy_types[:3])}"
    return "snapshot_regime_bias"


def _normalize_event_window_config(task: Optional[dict]) -> dict[str, Any]:
    payload = dict(task or {})
    event_window = dict(payload.get("event_window") or {})
    estimation_window = dict(payload.get("estimation_window") or {})
    holding_window = dict(payload.get("holding_window") or {})
    horizon = str(payload.get("horizon") or "").strip().lower()

    if not event_window:
        if payload.get("task_source") == "event_driven":
            event_window = {"pre_days": 1, "post_days": 10}
        else:
            event_window = {"pre_days": 0, "post_days": 20}
    if not estimation_window:
        estimation_window = {"lookback_days": 60}
    if not holding_window:
        if any(token in horizon for token in ("1_5", "5d", "intraday")):
            holding_window = {"max_days": 5}
        elif any(token in horizon for token in ("5_20", "20d", "swing")):
            holding_window = {"max_days": 20}
        else:
            holding_window = {"max_days": 10 if payload.get("task_source") == "event_driven" else 20}

    return {
        "event_window": event_window,
        "estimation_window": estimation_window,
        "holding_window": holding_window,
    }


def _normalize_research_task_contract(task: Optional[dict]) -> dict[str, Any]:
    payload = dict(task or {})
    task_source = str(payload.get("task_source") or "snapshot").strip().lower() or "snapshot"

    preferred_strategy_types = _normalize_string_list(
        payload.get("preferred_strategy_types") or payload.get("strategy_preferences"),
        limit=8,
    )
    allowed_strategy_types = _normalize_string_list(payload.get("allowed_strategy_types"), limit=12)
    target_symbols = _normalize_target_codes(
        [
            payload.get("target_symbols"),
            payload.get("stock_pool"),
            (payload.get("event_context") or {}).get("target_symbols"),
        ],
        limit=12,
    )
    stock_pool = dict(payload.get("stock_pool") or {})
    if target_symbols and not stock_pool:
        stock_pool = {"selection_mode": "explicit", "symbols": list(target_symbols)}

    target_symbol_policy = str(
        payload.get("target_symbol_policy")
        or _task_default_target_symbol_policy(task_source)
    ).strip().lower() or _task_default_target_symbol_policy(task_source)
    universe_expansion_policy = str(
        payload.get("universe_expansion_policy")
        or _task_default_universe_expansion_policy(task_source)
    ).strip().lower() or _task_default_universe_expansion_policy(task_source)
    preference_strength = str(
        payload.get("preference_strength")
        or _task_default_preference_strength(task_source)
    ).strip().lower() or _task_default_preference_strength(task_source)
    preference_reason = str(
        payload.get("preference_reason")
        or _task_default_preference_reason(task_source, preferred_strategy_types)
    ).strip() or _task_default_preference_reason(task_source, preferred_strategy_types)
    validation_focus = str(
        payload.get("validation_focus")
        or _task_default_validation_focus(task_source)
    ).strip().lower() or _task_default_validation_focus(task_source)

    event_windows = _normalize_event_window_config({**payload, "task_source": task_source, "horizon": payload.get("horizon")})
    task_signature = _build_task_signature({
        **payload,
        "task_source": task_source,
        "target_symbols": target_symbols,
        "validation_focus": validation_focus,
    })

    return {
        **payload,
        "task_source": task_source,
        "preferred_strategy_types": preferred_strategy_types,
        "allowed_strategy_types": allowed_strategy_types,
        "strategy_preferences": list(preferred_strategy_types),
        "target_symbols": target_symbols,
        "stock_pool": stock_pool,
        "target_symbol_policy": target_symbol_policy,
        "universe_expansion_policy": universe_expansion_policy,
        "preference_strength": preference_strength,
        "preference_reason": preference_reason,
        "validation_focus": validation_focus,
        **event_windows,
        "task_signature": task_signature,
        "target_symbols_signature": ",".join(target_symbols),
    }


def _normalize_strategy_type_preferences(task: Optional[dict]) -> List[str]:
    return list(_normalize_research_task_contract(task).get("preferred_strategy_types") or [])


def _build_task_signature(payload: Optional[dict]) -> str:
    item = dict(payload or {})
    target_symbols = _normalize_target_codes(
        [
            item.get("target_symbols"),
            item.get("stock_pool"),
            (item.get("research_task") or {}).get("target_symbols"),
            (item.get("event_context") or {}).get("target_symbols"),
        ],
        limit=16,
    )
    parts = [
        str(item.get("task_source") or "").strip().lower(),
        str(item.get("event_id") or (item.get("event_context") or {}).get("event_id") or "").strip().lower(),
        str(item.get("theme_code") or (item.get("event_context") or {}).get("theme_code") or "").strip().lower(),
        str(item.get("direction") or (item.get("event_context") or {}).get("direction") or "").strip().lower(),
        str(item.get("validation_focus") or "").strip().lower(),
        ",".join(sorted(target_symbols)),
    ]
    return "|".join(parts)


def _apply_target_symbol_policy(
    candidate_symbols: Any,
    research_task: Optional[dict],
    *,
    fallback_symbols: Any = None,
    limit: int = 8,
) -> dict[str, Any]:
    task = _normalize_research_task_contract(research_task)
    research_symbols = list(task.get("target_symbols") or [])
    candidate_codes = _normalize_target_codes(candidate_symbols, limit=limit)
    fallback_codes = _normalize_target_codes(fallback_symbols, limit=limit)
    candidate_before = list(candidate_codes)
    intersection = [code for code in candidate_codes if code in set(research_symbols)]
    policy = str(task.get("target_symbol_policy") or "prefer_intersection").strip().lower()
    expansion_policy = str(task.get("universe_expansion_policy") or "allow_market_fallback").strip().lower()

    resolved = list(candidate_codes)
    expansion_applied = False
    expansion_reason = ""
    expansion_source = ""
    violation = ""

    if research_symbols:
        if policy == "strict_intersection":
            resolved = list(intersection)
            if candidate_before and set(candidate_before) != set(resolved):
                expansion_applied = True
                expansion_reason = "strict_intersection_trimmed"
                expansion_source = "research_task.target_symbols"
            if not resolved:
                violation = "strict_intersection_empty"
        elif policy == "prefer_intersection":
            if intersection:
                resolved = list(intersection)
                if set(candidate_before) != set(resolved):
                    expansion_applied = True
                    expansion_reason = "prefer_intersection_trimmed"
                    expansion_source = "research_task.target_symbols"
            elif expansion_policy == "forbid":
                resolved = []
                violation = "expansion_forbidden"
            elif candidate_before:
                resolved = list(candidate_before)
                expansion_applied = True
                expansion_reason = "candidate_retained_without_intersection"
                expansion_source = "candidate_symbols"
            elif fallback_codes:
                resolved = list(fallback_codes)
                expansion_applied = True
                expansion_reason = "fallback_candidate_universe"
                expansion_source = "candidate_universe"
            else:
                resolved = list(research_symbols[:limit])
                expansion_applied = True
                expansion_reason = "fallback_research_symbols"
                expansion_source = "research_task.target_symbols"
        else:
            if candidate_before:
                resolved = list(candidate_before)
            elif fallback_codes:
                resolved = list(fallback_codes)
                expansion_applied = True
                expansion_reason = "fallback_candidate_universe"
                expansion_source = "candidate_universe"
            else:
                resolved = list(research_symbols[:limit])
                expansion_applied = True
                expansion_reason = "fallback_research_symbols"
                expansion_source = "research_task.target_symbols"
    elif not resolved and fallback_codes:
        resolved = list(fallback_codes)
        expansion_applied = True
        expansion_reason = "fallback_candidate_universe"
        expansion_source = "candidate_universe"

    resolved = resolved[: max(1, min(int(limit or 8), 40))]
    overlap_count = len(set(resolved).intersection(research_symbols))
    coverage_ratio = round(overlap_count / max(1, len(resolved)), 4) if resolved else 0.0
    intersection_ratio = round(overlap_count / max(1, len(research_symbols)), 4) if research_symbols else None

    return {
        "target_symbols": resolved,
        "constraint_check": {
            "target_symbols_before_normalize": candidate_before,
            "target_symbols_after_normalize": list(resolved),
            "research_target_symbols": list(research_symbols),
            "target_symbol_policy": policy,
            "universe_expansion_policy": expansion_policy,
            "expansion_applied": expansion_applied,
            "expansion_reason": expansion_reason or None,
            "expansion_source": expansion_source or None,
            "constraint_violation": violation or None,
            "coverage_ratio": coverage_ratio,
            "intersection_ratio": intersection_ratio,
        },
    }


def _extract_target_codes_from_payload(payload: Optional[dict], limit: int = 12) -> List[str]:
    item = dict(payload or {})
    params = dict(item.get("params") or {})
    dsl = dict(params.get("dsl") or {})
    dsl_metadata = dict(dsl.get("metadata") or {})
    generation_reason = dict(item.get("generation_reason") or {})
    research_task = dict(item.get("research_task") or {})
    item_event_context = dict(item.get("event_context") or {})
    task_event_context = dict(research_task.get("event_context") or {})
    return _normalize_target_codes([
        item.get("target_symbols"),
        item.get("stock_pool"),
        item_event_context.get("target_symbols"),
        item_event_context.get("stock_pool"),
        params.get("target_symbols"),
        params.get("stock_pool"),
        params.get("research_task"),
        params.get("event_context"),
        dsl_metadata.get("target_symbols"),
        dsl_metadata.get("stock_pool"),
        generation_reason.get("target_symbols"),
        generation_reason.get("stock_pool"),
        research_task.get("target_symbols"),
        research_task.get("stock_pool"),
        task_event_context.get("target_symbols"),
        task_event_context.get("stock_pool"),
    ], limit=limit)


def _resolve_strategy_sample_codes(strategy_type: str, params: dict, sample_size: int = 6) -> List[str]:
    target_codes = _extract_target_codes_from_payload(
        {"strategy_type": strategy_type, "params": params},
        limit=max(sample_size, 12),
    )
    combined = list(dict.fromkeys([*target_codes, *REPRESENTATIVE_STOCKS]))
    return combined[: max(sample_size, min(len(combined), max(sample_size, len(target_codes))))]


__all__ = [
    "_update_strategy_status",
    "_normalize_target_codes",
    "_normalize_string_list",
    "_normalize_research_task_contract",
    "_normalize_strategy_type_preferences",
    "_apply_target_symbol_policy",
    "_build_task_signature",
    "_extract_target_codes_from_payload",
    "_resolve_strategy_sample_codes",
]
