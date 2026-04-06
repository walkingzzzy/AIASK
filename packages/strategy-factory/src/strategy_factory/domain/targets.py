"""策略工厂状态、任务合同与目标池工具。"""

from __future__ import annotations

import math
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


def _normalize_lower_string_list(values: Any, limit: int = 12) -> List[str]:
    return [
        str(item).strip().lower()
        for item in _normalize_string_list(values, limit=limit)
        if str(item).strip()
    ]


def _candidate_generation_mode(candidate: Optional[dict]) -> str:
    payload = dict(candidate or {})
    for source in (
        payload,
        dict(payload.get("params") or {}),
        dict(payload.get("candidate_provenance") or {}),
        dict(payload.get("generation_reason") or {}),
        dict(payload.get("research_task") or {}),
    ):
        if not isinstance(source, dict):
            continue
        for key in ("generator_type", "generator_mode"):
            value = str(source.get(key) or "").strip().lower()
            if value:
                return value
    return ""


def _build_target_alignment_contract(
    research_task: Optional[dict],
    *,
    candidate: Optional[dict] = None,
) -> dict[str, Any]:
    task = dict(research_task or {})
    task_source = str(task.get("task_source") or "snapshot").strip().lower() or "snapshot"
    target_symbols = _normalize_target_codes(
        [
            task.get("target_symbols"),
            task.get("stock_pool"),
            (task.get("event_context") or {}).get("target_symbols"),
        ],
        limit=12,
    )
    target_count = len(target_symbols)
    targeted_snapshot = task_source == "snapshot" and target_count > 1
    event_targeted = task_source == "event_driven" and target_count > 0

    family_hints = set(
        _normalize_lower_string_list(
            [
                task.get("allowed_strategy_types"),
                task.get("preferred_strategy_types"),
                task.get("strategy_preferences"),
            ],
            limit=12,
        )
    )
    payload = dict(candidate or {})
    candidate_strategy_type = str(
        payload.get("strategy_type")
        or payload.get("candidate_family")
        or task.get("candidate_family")
        or ""
    ).strip().lower()
    if candidate_strategy_type:
        family_hints.add(candidate_strategy_type)
    generator_mode = _candidate_generation_mode(payload) or str(
        task.get("generator_type") or task.get("generator_mode") or ""
    ).strip().lower()
    candidate_tags = {
        str(tag).strip().lower()
        for tag in list(payload.get("tags") or [])
        if str(tag).strip()
    }

    single_family_hint = next(iter(family_hints)) if len(family_hints) == 1 else ""
    strategy_hint = candidate_strategy_type or single_family_hint
    is_pipeline_staged = (
        generator_mode == "pipeline_staged"
        or "pipeline_staged" in candidate_tags
        or "generator_pipeline_staged" in candidate_tags
    )
    is_rl_bandit = (
        generator_mode == "rl_bandit"
        or "rl_bandit" in candidate_tags
        or "generator_rl_bandit" in candidate_tags
        or "rl_evolved" in candidate_tags
    )
    pipeline_rsi = targeted_snapshot and strategy_hint == "rsi" and (is_pipeline_staged or not payload)
    pipeline_ma_cross = targeted_snapshot and strategy_hint == "ma_cross" and (is_pipeline_staged or not payload)
    rl_bandit_momentum = targeted_snapshot and strategy_hint == "momentum" and is_rl_bandit
    rl_bandit_volatility_breakout = targeted_snapshot and strategy_hint == "volatility_breakout" and is_rl_bandit

    min_coverage_ratio = 0.0
    min_intersection_ratio = 0.0
    min_target_layer_stability = 0.0
    strict_target_subset_required = False
    reject_market_fallback = False
    default_target_cap = min(target_count, 8) if target_count > 0 else 0
    contract_profile = "untargeted"

    if event_targeted:
        strict_target_subset_required = True
        reject_market_fallback = False
        min_coverage_ratio = 1.0
        min_intersection_ratio = 0.5 if target_count > 1 else 1.0
        min_target_layer_stability = 0.4
        default_target_cap = min(target_count, 8)
        contract_profile = "event_targeted"
    elif targeted_snapshot:
        strict_target_subset_required = True
        reject_market_fallback = True
        min_coverage_ratio = 0.75
        min_intersection_ratio = 0.25
        min_target_layer_stability = 0.35
        default_target_cap = min(target_count, 4 if target_count >= 4 else target_count)
        contract_profile = "snapshot_targeted"

        if pipeline_ma_cross:
            min_intersection_ratio = 0.35 if target_count >= 4 else min_intersection_ratio
            min_target_layer_stability = 0.42
            default_target_cap = min(target_count, 4 if target_count >= 4 else target_count)
            contract_profile = "pipeline_staged_ma_cross"
        if pipeline_rsi:
            min_intersection_ratio = 0.5 if target_count >= 6 else max(min_intersection_ratio, 0.35)
            min_target_layer_stability = 0.55
            default_target_cap = min(target_count, 4 if target_count >= 4 else target_count)
            contract_profile = "pipeline_staged_rsi"
        if rl_bandit_momentum:
            min_coverage_ratio = 0.85
            min_intersection_ratio = 0.45 if target_count >= 6 else max(min_intersection_ratio, 0.35)
            min_target_layer_stability = 0.5
            default_target_cap = min(target_count, 6 if target_count >= 6 else target_count)
            contract_profile = "rl_bandit_momentum"
        if rl_bandit_volatility_breakout:
            min_coverage_ratio = 0.85
            min_intersection_ratio = 0.2 if target_count >= 8 else max(min_intersection_ratio, 0.15)
            min_target_layer_stability = 0.45
            default_target_cap = min(target_count, 6 if target_count >= 6 else target_count)
            contract_profile = "rl_bandit_volatility_breakout"

    min_required_overlap_count = (
        max(1, int(math.ceil(target_count * min_intersection_ratio)))
        if target_count > 0 and strict_target_subset_required
        else (1 if target_count > 0 and targeted_snapshot else 0)
    )
    min_target_sample_count = min(
        target_count,
        max(1, min_required_overlap_count),
    ) if target_count > 0 and targeted_snapshot else (1 if event_targeted and target_count > 0 else 0)
    max_candidate_target_symbols = (
        min(target_count, max(default_target_cap, min_required_overlap_count))
        if target_count > 0
        else 0
    )

    return {
        "profile": contract_profile,
        "task_source": task_source,
        "targeted_snapshot": targeted_snapshot,
        "event_targeted": event_targeted,
        "quality_gate_enabled": targeted_snapshot or event_targeted,
        "strict_target_subset_required": strict_target_subset_required,
        "market_fallback_allowed": not reject_market_fallback,
        "min_coverage_ratio": round(min_coverage_ratio, 4),
        "min_intersection_ratio": round(min_intersection_ratio, 4),
        "min_required_overlap_count": int(min_required_overlap_count),
        "min_target_sample_count": int(min_target_sample_count),
        "min_target_layer_stability": round(min_target_layer_stability, 4),
        "max_candidate_target_symbols": int(max_candidate_target_symbols),
        "focus_strategy_families": sorted(family_hints)[:6],
        "generator_mode": generator_mode or None,
    }


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

    target_symbol_policy_explicit = payload.get("target_symbol_policy") is not None
    universe_expansion_policy_explicit = payload.get("universe_expansion_policy") is not None
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
    target_alignment_contract = _build_target_alignment_contract(
        {
            **payload,
            "task_source": task_source,
            "preferred_strategy_types": preferred_strategy_types,
            "allowed_strategy_types": allowed_strategy_types,
            "strategy_preferences": preferred_strategy_types,
            "target_symbols": target_symbols,
            "stock_pool": stock_pool,
        }
    )

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
        "target_symbol_policy_explicit": target_symbol_policy_explicit,
        "universe_expansion_policy": universe_expansion_policy,
        "universe_expansion_policy_explicit": universe_expansion_policy_explicit,
        "preference_strength": preference_strength,
        "preference_reason": preference_reason,
        "validation_focus": validation_focus,
        "target_alignment_contract": target_alignment_contract,
        **event_windows,
        "task_signature": task_signature,
        "target_symbols_signature": ",".join(sorted(target_symbols)),
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
    target_alignment_contract = dict(task.get("target_alignment_contract") or {})
    research_symbols = list(task.get("target_symbols") or [])
    candidate_codes = _normalize_target_codes(candidate_symbols, limit=limit)
    fallback_codes = _normalize_target_codes(fallback_symbols, limit=limit)
    same_theme_codes = _normalize_target_codes(
        [
            task.get("same_theme_symbols"),
            task.get("theme_members"),
            (task.get("event_context") or {}).get("same_theme_symbols"),
            (task.get("event_context") or {}).get("theme_members"),
        ],
        limit=limit,
    )
    candidate_before = list(candidate_codes)
    intersection = [code for code in candidate_codes if code in set(research_symbols)]
    policy = str(task.get("target_symbol_policy") or "prefer_intersection").strip().lower()
    expansion_policy = str(task.get("universe_expansion_policy") or "allow_market_fallback").strip().lower()
    if (
        research_symbols
        and target_alignment_contract.get("strict_target_subset_required")
        and not task.get("target_symbol_policy_explicit")
        and not task.get("universe_expansion_policy_explicit")
        and not target_alignment_contract.get("market_fallback_allowed", True)
    ):
        expansion_policy = "forbid"

    resolved = list(candidate_codes)
    expansion_applied = False
    expansion_reason = ""
    expansion_source = ""
    violation = ""
    blocked_reason = ""

    same_theme_set = set(same_theme_codes)

    def _resolve_same_theme_subset() -> list[str]:
        same_theme_candidate = [code for code in candidate_before if code in same_theme_set]
        if same_theme_candidate:
            return same_theme_candidate
        return [code for code in fallback_codes if code in same_theme_set]

    if research_symbols:
        if policy == "strict_intersection":
            resolved = list(intersection)
            if candidate_before and resolved and set(candidate_before) != set(resolved):
                expansion_applied = True
                expansion_reason = "strict_intersection_trimmed"
                expansion_source = "research_task.target_symbols"
            if not resolved and expansion_policy == "allow_same_theme_only":
                same_theme_subset = _resolve_same_theme_subset()
                if same_theme_subset:
                    resolved = list(same_theme_subset)
                    expansion_applied = True
                    expansion_reason = "fallback_same_theme_symbols"
                    expansion_source = "same_theme_symbols"
                else:
                    blocked_reason = "same_theme_symbols_unavailable"
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
            elif expansion_policy == "allow_same_theme_only":
                same_theme_subset = _resolve_same_theme_subset()
                if same_theme_subset:
                    resolved = list(same_theme_subset)
                    expansion_applied = True
                    expansion_reason = "fallback_same_theme_symbols"
                    expansion_source = "same_theme_symbols"
                else:
                    resolved = []
                    violation = "same_theme_expansion_empty"
                    blocked_reason = "same_theme_symbols_unavailable"
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

    resolved_limit = max(1, min(int(limit or 8), 40))
    contract_target_cap = int(target_alignment_contract.get("max_candidate_target_symbols") or 0)
    if contract_target_cap > 0:
        resolved_limit = min(resolved_limit, contract_target_cap)
    resolved = resolved[:resolved_limit]
    overlap_count = len(set(resolved).intersection(research_symbols))
    coverage_ratio = round(overlap_count / max(1, len(resolved)), 4) if resolved else 0.0
    intersection_ratio = round(overlap_count / max(1, len(research_symbols)), 4) if research_symbols else None
    alignment_violation = None
    min_coverage_ratio = float(target_alignment_contract.get("min_coverage_ratio") or 0.0)
    min_intersection_ratio = (
        None
        if target_alignment_contract.get("min_intersection_ratio") is None
        else float(target_alignment_contract.get("min_intersection_ratio") or 0.0)
    )
    min_required_overlap_count = int(target_alignment_contract.get("min_required_overlap_count") or 0)
    alignment_ok = True
    if target_alignment_contract.get("quality_gate_enabled"):
        if resolved_limit > 0 and len(candidate_before) > resolved_limit:
            expansion_applied = True
            expansion_reason = expansion_reason or "target_count_trimmed_by_contract"
            expansion_source = expansion_source or "target_alignment_contract"
        if not resolved and research_symbols:
            alignment_ok = False
            alignment_violation = "empty_target_symbols_after_alignment"
        elif coverage_ratio < min_coverage_ratio:
            alignment_ok = False
            alignment_violation = "coverage_ratio_below_contract"
        elif min_intersection_ratio is not None and (intersection_ratio or 0.0) < min_intersection_ratio:
            alignment_ok = False
            alignment_violation = "intersection_ratio_below_contract"
        elif min_required_overlap_count > 0 and overlap_count < min_required_overlap_count:
            alignment_ok = False
            alignment_violation = "target_overlap_count_below_contract"

    return {
        "target_symbols": resolved,
        "constraint_check": {
            "target_symbols_before_normalize": candidate_before,
            "target_symbols_after_normalize": list(resolved),
            "research_target_symbols": list(research_symbols),
            "same_theme_symbols": list(same_theme_codes),
            "target_symbol_policy": policy,
            "universe_expansion_policy": expansion_policy,
            "expansion_applied": expansion_applied,
            "expansion_reason": expansion_reason or None,
            "expansion_source": expansion_source or None,
            "constraint_violation": violation or None,
            "expansion_blocked_reason": blocked_reason or None,
            "coverage_ratio": coverage_ratio,
            "intersection_ratio": intersection_ratio,
            "target_overlap_count": int(overlap_count),
            "alignment_contract_ok": alignment_ok,
            "alignment_contract_violation": alignment_violation,
            "target_alignment_contract": dict(target_alignment_contract),
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
    "_build_target_alignment_contract",
    "_apply_target_symbol_policy",
    "_build_task_signature",
    "_extract_target_codes_from_payload",
    "_resolve_strategy_sample_codes",
]
