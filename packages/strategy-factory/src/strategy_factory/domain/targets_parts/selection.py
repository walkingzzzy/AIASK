

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
    primary_family = _primary_strategy_family(payload)
    task_source = str(payload.get("task_source") or "snapshot").strip().lower() or "snapshot"

    if not event_window:
        if task_source == "event_driven":
            event_window = {"pre_days": 1, "post_days": 10}
        else:
            event_window = {"pre_days": 0, "post_days": 20}
    if not estimation_window:
        estimation_window = {"lookback_days": 60}
    if not holding_window:
        holding_window = _default_holding_window_for_family(
            primary_family,
            task_source=task_source,
            horizon=horizon,
        )

    return {
        "event_window": event_window,
        "estimation_window": estimation_window,
        "holding_window": holding_window,
    }


def _compact_task_metadata_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        preview = [
            item
            for item in value[:8]
            if isinstance(item, (str, int, float, bool)) or item is None
        ]
        return preview or None
    if isinstance(value, dict):
        compact = {
            str(key): item
            for key, item in list(value.items())[:12]
            if isinstance(item, (str, int, float, bool)) or item is None
        }
        if compact:
            return compact
    return None


def _summarize_factor_research_metadata(factor_research: Optional[dict]) -> dict[str, Any]:
    payload = dict(factor_research or {})
    summary = dict(payload.get("summary") or {})
    freshness_repair = dict(payload.get("freshness_repair") or {})
    compact = {
        "top_factor_names": list(summary.get("top_factor_names") or payload.get("active_factors") or [])[:6],
        "preferred_strategy_types": _normalize_string_list(payload.get("preferred_strategy_types"), limit=6),
        "degraded": bool(payload.get("degraded")),
    }
    for key in (
        "active_candidate_count",
        "candidate_pool_size",
        "registry_size",
        "freshness_days",
        "refresh_status",
    ):
        value = summary.get(key)
        if value not in (None, "", [], {}):
            compact[key] = value
    if freshness_repair:
        compact["freshness_repair"] = {
            key: freshness_repair.get(key)
            for key in (
                "refresh_attempted",
                "refresh_status",
                "refresh_trigger",
                "fallback_reason",
                "stale_days",
            )
            if freshness_repair.get(key) not in (None, "", [], {})
        }
    return {key: value for key, value in compact.items() if value not in (None, "", [], {})}


def _compact_research_task_metadata(metadata: Optional[dict]) -> dict[str, Any]:
    payload = dict(metadata or {})
    compact: dict[str, Any] = {}
    factor_research = _summarize_factor_research_metadata(payload.get("factor_research"))
    if factor_research:
        compact["factor_research"] = factor_research
    for key, value in payload.items():
        if key == "factor_research":
            continue
        compact_value = _compact_task_metadata_value(value)
        if compact_value not in (None, "", [], {}):
            compact[str(key)] = compact_value
    return compact


def _normalize_research_task_contract(task: Optional[dict]) -> dict[str, Any]:
    payload = dict(task or {})
    task_source = str(payload.get("task_source") or "snapshot").strip().lower() or "snapshot"
    compact_metadata = _compact_research_task_metadata(payload.get("metadata") or {})
    if compact_metadata:
        payload = {**payload, "metadata": compact_metadata}
    elif "metadata" in payload:
        payload = {key: value for key, value in payload.items() if key != "metadata"}

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
    targeted_snapshot = task_source == "snapshot" and len(target_symbols) > 0
    event_targeted = task_source == "event_driven" and len(target_symbols) > 0

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
    if targeted_snapshot and not target_symbol_policy_explicit:
        target_symbol_policy = "strict_intersection"
    if targeted_snapshot and not universe_expansion_policy_explicit:
        universe_expansion_policy = "forbid"
    if event_targeted and not universe_expansion_policy_explicit:
        universe_expansion_policy = "allow_same_theme_only"
    preference_strength = str(
        payload.get("preference_strength")
        or _task_default_preference_strength(task_source)
    ).strip().lower() or _task_default_preference_strength(task_source)
    preference_reason = str(
        payload.get("preference_reason")
        or _task_default_preference_reason(task_source, preferred_strategy_types)
    ).strip() or _task_default_preference_reason(task_source, preferred_strategy_types)
    validation_focus_explicit = payload.get("validation_focus") is not None
    validation_focus = str(
        payload.get("validation_focus")
        or _task_default_validation_focus(task_source)
    ).strip().lower() or _task_default_validation_focus(task_source)
    primary_family = _primary_strategy_family(
        {
            **payload,
            "preferred_strategy_types": preferred_strategy_types,
            "allowed_strategy_types": allowed_strategy_types,
            "strategy_preferences": preferred_strategy_types,
        }
    )
    if (
        primary_family == "quality_factor"
        and not validation_focus_explicit
        and task_source != "event_driven"
        and validation_focus == "target_plus_representative"
    ):
        validation_focus = "candidate_target_only"
    validation_profile = dict(payload.get("validation_profile") or {})
    if not validation_profile:
        validation_profile = _default_validation_profile_for_task(
            family=primary_family,
            task_source=task_source,
            validation_focus=validation_focus,
        )
    else:
        merged_profile = _default_validation_profile_for_task(
            family=primary_family,
            task_source=task_source,
            validation_focus=str(validation_profile.get("validation_focus") or validation_focus),
        )
        validation_profile = {
            **merged_profile,
            **validation_profile,
        }
        if (
            primary_family == "quality_factor"
            and str(validation_profile.get("validation_focus") or validation_focus).strip().lower()
            in {"candidate_target_only", "target_only", "target_plus_family_peer"}
        ):
            validation_profile["profile"] = "trade_rule_validation"
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
        "validation_profile": validation_profile,
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


def _extract_candidate_origin_target_codes(payload: Optional[dict], limit: int = 12) -> List[str]:
    item = dict(payload or {})
    params = dict(item.get("params") or {})
    dsl = dict(params.get("dsl") or {})
    dsl_metadata = dict(dsl.get("metadata") or {})
    generation_reason = dict(item.get("generation_reason") or {})
    candidate_provenance = dict(item.get("candidate_provenance") or {})
    item_event_context = dict(item.get("event_context") or {})
    return _normalize_target_codes([
        item.get("target_symbols"),
        item.get("stock_pool"),
        item_event_context.get("target_symbols"),
        item_event_context.get("stock_pool"),
        params.get("target_symbols"),
        params.get("stock_pool"),
        params.get("event_context"),
        dsl_metadata.get("target_symbols"),
        dsl_metadata.get("stock_pool"),
        generation_reason.get("target_symbols"),
        generation_reason.get("stock_pool"),
        candidate_provenance.get("target_symbols"),
        candidate_provenance.get("stock_pool"),
    ], limit=limit)


def _extract_target_codes_from_payload(payload: Optional[dict], limit: int = 12) -> List[str]:
    item = dict(payload or {})
    candidate_codes = _extract_candidate_origin_target_codes(item, limit=limit)
    if candidate_codes:
        return list(candidate_codes)
    params = dict(item.get("params") or {})
    research_task = dict(item.get("research_task") or {})
    task_event_context = dict(research_task.get("event_context") or {})
    params_research_task = dict(params.get("research_task") or {})
    params_task_event_context = dict(params_research_task.get("event_context") or {})
    return _normalize_target_codes([
        research_task.get("target_symbols"),
        research_task.get("stock_pool"),
        task_event_context.get("target_symbols"),
        task_event_context.get("stock_pool"),
        params_research_task.get("target_symbols"),
        params_research_task.get("stock_pool"),
        params_task_event_context.get("target_symbols"),
        params_task_event_context.get("stock_pool"),
    ], limit=limit)


def _resolve_strategy_sample_codes(strategy_type: str, params: dict, sample_size: int = 6) -> List[str]:
    selection = _resolve_strategy_sample_selection(
        strategy_type,
        params,
        sample_size=sample_size,
    )
    return list(selection.get("sample_codes") or [])


__all__ = [
    "_update_strategy_status",
    "_normalize_target_codes",
    "_normalize_string_list",
    "_normalize_research_task_contract",
    "_normalize_strategy_type_preferences",
    "_build_target_alignment_contract",
    "_apply_target_symbol_policy",
    "_build_task_signature",
    "_extract_candidate_origin_target_codes",
    "_extract_target_codes_from_payload",
    "_resolve_strategy_sample_codes",
]
