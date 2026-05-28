
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .constants import REPRESENTATIVE_STOCKS

_VALIDATION_PEER_CODES_BY_FAMILY: Dict[str, List[str]] = {
    "momentum": ["300750", "601012", "002415", "300059", "002594", "601318"],
    "ma_cross": ["300750", "601012", "002415", "300059", "002594", "601318"],
    "volatility_breakout": ["300750", "601012", "002415", "300059", "002594", "601318"],
    "event_structure_breakout": ["688336", "600519", "000858", "601318"],
    "quality_factor": ["600519", "000858", "600036", "000333", "600276", "601318"],
    "value_factor": ["600519", "000858", "600036", "000333", "600276", "601318"],
    "growth_factor": ["300750", "601012", "002594", "300124", "300308", "002415"],
    "multi_factor": ["600519", "000858", "600036", "000333", "300750", "601318"],
}

_VALIDATION_PEER_UNIVERSE_BY_FAMILY: Dict[str, List[str]] = {
    "momentum": [
        "300750", "601012", "002415", "300059", "002594", "601318",
        "002460", "300308", "300124", "603259", "600438", "000063",
    ],
    "ma_cross": [
        "300750", "601012", "002415", "300059", "002594", "601318",
        "002460", "300308", "300124", "603259", "600438", "000063",
    ],
    "volatility_breakout": [
        "300750", "601012", "002415", "300059", "002594", "601318",
        "300308", "002460", "603259", "000063", "688111", "300274",
    ],
    "event_structure_breakout": [
        "688336", "600519", "000858", "601318",
        "688187", "688303", "688599", "300620",
    ],
    "quality_factor": [
        "600519", "000858", "600036", "000333", "600276", "601318",
        "600809", "600887", "002415", "603288", "601888", "600690",
    ],
    "value_factor": [
        "600519", "000858", "600036", "000333", "600276", "601318",
        "600887", "601166", "600309", "000651", "600690", "601888",
    ],
    "growth_factor": [
        "300750", "601012", "002594", "300124", "300308", "002415",
        "688111", "300274", "688981", "002460", "300059", "603986",
    ],
    "multi_factor": [
        "600519", "000858", "600036", "000333", "300750", "601318",
        "601012", "002594", "603288", "600276", "300059", "002415",
    ],
}

_FACTOR_RANK_VALIDATION_SAMPLE_MIN = 12


def _primary_strategy_family(payload: Optional[dict]) -> str:
    item = dict(payload or {})
    for source in (
        item.get("candidate_family"),
        item.get("preferred_strategy_types"),
        item.get("allowed_strategy_types"),
        item.get("strategy_preferences"),
    ):
        values = _normalize_string_list(source, limit=1)
        if values:
            return str(values[0] or "").strip().lower()
    return ""


def _default_holding_window_for_family(
    family: str,
    *,
    task_source: str,
    horizon: str = "",
) -> dict[str, Any]:
    normalized_family = str(family or "").strip().lower()
    normalized_horizon = str(horizon or "").strip().lower()
    if any(token in normalized_horizon for token in ("1_5", "5d", "intraday")):
        return {"max_days": 5}
    if any(token in normalized_horizon for token in ("5_20", "20d", "swing")):
        return {"max_days": 20}
    if normalized_family == "quality_factor":
        return {"min_days": 30, "max_days": 84}
    if normalized_family == "ma_cross":
        return {"min_days": 14, "max_days": 48}
    if normalized_family == "momentum":
        return {"min_days": 14, "max_days": 42}
    if normalized_family == "growth_factor":
        return {"min_days": 18, "max_days": 60}
    if task_source == "event_driven":
        return {"max_days": 10}
    return {"max_days": 20}


def _default_validation_profile_for_task(
    *,
    family: str,
    task_source: str,
    validation_focus: str,
) -> dict[str, Any]:
    normalized_family = str(family or "").strip().lower()
    normalized_focus = _normalize_validation_focus(validation_focus) or (
        "event_target_only" if task_source == "event_driven" else "target_plus_representative"
    )
    if normalized_family == "macro_timing":
        profile = "macro_regime_validation"
    elif task_source == "event_driven" or normalized_focus == "event_target_only":
        profile = "event_trade_validation"
        normalized_focus = "event_target_only"
    elif normalized_family == "quality_factor" and normalized_focus in {
        "candidate_target_only",
        "target_only",
        "target_plus_family_peer",
    }:
        profile = "trade_rule_validation"
    elif normalized_family in {"value_factor", "quality_factor", "growth_factor", "multi_factor", "sentiment", "sentiment_factor"}:
        profile = "factor_rank_validation"
    else:
        profile = "trade_rule_validation"
    return {
        "profile": profile,
        "validation_focus": normalized_focus,
        "primary_validation_layer": "target" if normalized_focus in {"candidate_target_only", "event_target_only", "target_only"} else "combined",
    }


def _normalize_validation_focus(value: Any) -> str:
    return str(value or "").strip().lower()


def _resolve_validation_focus_layer(validation_focus: str) -> str:
    focus = _normalize_validation_focus(validation_focus)
    if focus in {"candidate_target_only", "event_target_only", "target_only"}:
        return "target_only"
    if focus in {"target_plus_family_peer", "family_peer", "target_plus_peer"}:
        return "family_peer"
    if focus in {"sector_peer", "target_plus_sector_peer"}:
        return "sector_peer"
    return "broad_market"


def _code_board_bucket(code: str) -> str:
    token = str(code or "").strip()
    if token.startswith("688"):
        return "star"
    if token.startswith("300"):
        return "chi_next"
    if token.startswith(("600", "601", "603", "605")):
        return "sh_main"
    if token.startswith(("000", "001", "002", "003")):
        return "sz_main"
    return "other"


def _code_prefix_bucket(code: str) -> str:
    token = str(code or "").strip()
    if len(token) >= 3:
        return token[:3]
    if len(token) >= 2:
        return token[:2]
    return token


def _score_peer_candidate(target_codes: List[str], candidate_code: str) -> tuple[int, int, str]:
    candidate = str(candidate_code or "").strip()
    if not candidate:
        return (0, 0, "")
    if not target_codes:
        return (0, 0, candidate)
    target_boards = {_code_board_bucket(code) for code in target_codes}
    target_prefixes = {_code_prefix_bucket(code) for code in target_codes}
    board_score = 2 if _code_board_bucket(candidate) in target_boards else 0
    prefix_score = 1 if _code_prefix_bucket(candidate) in target_prefixes else 0
    return (board_score + prefix_score, board_score, candidate)


def _resolve_dynamic_family_peers(
    strategy_type: str,
    target_codes: List[str],
    *,
    sample_size: int,
) -> List[str]:
    family = str(strategy_type or "").strip().lower()
    anchor_peers = [
        code for code in list(_VALIDATION_PEER_CODES_BY_FAMILY.get(family) or [])
        if code not in set(target_codes)
    ]
    peer_universe = list(_VALIDATION_PEER_UNIVERSE_BY_FAMILY.get(family) or [])
    if not peer_universe and not anchor_peers:
        return []
    deduped_universe = [
        code for code in dict.fromkeys([*peer_universe, *anchor_peers])
        if code not in set(target_codes) and code not in set(anchor_peers)
    ]
    ranked = sorted(
        deduped_universe,
        key=lambda code: _score_peer_candidate(target_codes, code),
        reverse=True,
    )
    limit = max(sample_size * 2, 8)
    return list(dict.fromkeys([*anchor_peers, *ranked]))[:limit]


def _resolve_strategy_sample_selection(
    strategy_type: str,
    params: dict,
    sample_size: int = 6,
) -> dict[str, Any]:
    validation_profile = dict(params.get("validation_profile") or {})
    profile_name = str(validation_profile.get("profile") or "").strip().lower()
    requested_sample_size = max(1, int(sample_size or 6))
    effective_sample_size = requested_sample_size
    statistical_sample_min = 0
    if profile_name == "factor_rank_validation":
        statistical_sample_min = _FACTOR_RANK_VALIDATION_SAMPLE_MIN
        effective_sample_size = max(effective_sample_size, statistical_sample_min)
    research_task = dict(params.get("research_task") or {})
    validation_focus = str(
        validation_profile.get("validation_focus")
        or research_task.get("validation_focus")
        or ""
    ).strip().lower()
    validation_focus_layer = _resolve_validation_focus_layer(validation_focus)
    target_codes = _extract_target_codes_from_payload(
        {"strategy_type": strategy_type, "params": params},
        limit=max(effective_sample_size, 12),
    )
    static_family_peers = list(
        _VALIDATION_PEER_CODES_BY_FAMILY.get(str(strategy_type or "").strip().lower()) or []
    )
    dynamic_family_peers = _resolve_dynamic_family_peers(
        strategy_type,
        target_codes,
        sample_size=effective_sample_size,
    )

    sample_selection_mode = "representative_only"
    sample_alignment_reason = "broad_market_representative_fallback"
    if validation_focus_layer == "target_only" and target_codes:
        combined = list(dict.fromkeys([*target_codes, *dynamic_family_peers, *REPRESENTATIVE_STOCKS]))
        sample_selection_mode = "target_plus_dynamic_family_peer"
        sample_alignment_reason = "target_only_with_family_aligned_dynamic_peers"
    elif validation_focus_layer == "family_peer" and target_codes:
        combined = list(dict.fromkeys([*target_codes, *dynamic_family_peers, *static_family_peers]))
        sample_selection_mode = "family_peer_dynamic_panel"
        sample_alignment_reason = "family_peer_panel_aligned_to_target_codes"
    elif validation_focus_layer == "sector_peer" and target_codes:
        combined = list(dict.fromkeys([*target_codes, *dynamic_family_peers, *REPRESENTATIVE_STOCKS]))
        sample_selection_mode = "sector_peer_proxy_panel"
        sample_alignment_reason = "sector_peer_proxy_via_family_and_representative_mix"
    elif target_codes and dynamic_family_peers:
        combined = list(dict.fromkeys([*target_codes, *dynamic_family_peers, *REPRESENTATIVE_STOCKS]))
        validation_focus_layer = "family_peer"
        sample_selection_mode = "target_plus_dynamic_family_peer"
        sample_alignment_reason = "target_codes_present_promoted_to_family_peer_panel"
    else:
        combined = list(dict.fromkeys([*target_codes, *REPRESENTATIVE_STOCKS]))

    requested_size = max(
        effective_sample_size,
        min(len(combined), max(effective_sample_size, len(target_codes))),
    )
    sample_codes = combined[:requested_size]
    return {
        "sample_codes": sample_codes,
        "target_codes": list(target_codes),
        "family_peer_codes": list(dynamic_family_peers[: max(effective_sample_size, 8)]),
        "validation_focus": validation_focus or None,
        "validation_focus_layer": validation_focus_layer,
        "sample_selection_mode": sample_selection_mode,
        "sample_alignment_reason": sample_alignment_reason,
        "sample_code_count": int(len(sample_codes)),
        "requested_sample_size": int(requested_sample_size),
        "effective_sample_size": int(effective_sample_size),
        "statistical_sample_min": int(statistical_sample_min),
        "statistical_sample_expanded": bool(effective_sample_size > requested_sample_size),
    }


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
    targeted_snapshot = task_source == "snapshot" and target_count > 0
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
