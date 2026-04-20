

def candidate_contract_value(candidate: Optional[Mapping[str, Any]], key: str, default: Any = None) -> Any:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    research_task = _as_dict(payload.get("research_task"))
    lineage = _as_dict(payload.get("lineage"))
    provenance = _as_dict(payload.get("candidate_provenance"))
    for source in (payload, params, lineage, provenance, research_task):
        if key in source and source.get(key) not in _EMPTY_VALUES:
            return source.get(key)
    return default


def resolve_candidate_validation_profile(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    strategy_type = _string(payload.get("strategy_type")).lower()
    explicit_profile = {}
    for source in (
        payload,
        _as_dict(payload.get("params")),
        _as_dict(payload.get("lineage")),
        _as_dict(payload.get("candidate_provenance")),
    ):
        explicit_profile = _as_dict(source.get("validation_profile"))
        if explicit_profile:
            break
    task_validation_profile = _as_dict(normalized_task.get("validation_profile"))
    use_task_validation_profile = bool(
        task_validation_profile
        and (
            bool(candidate_contract_value(payload, "had_explicit_research_task", False))
            or _string(normalized_task.get("task_source")).lower() in {"bulk_stock_matrix", "event_driven"}
            or _string(task_validation_profile.get("validation_focus")).lower()
            in {"candidate_target_only", "event_target_only", "target_only"}
        )
    )
    if not explicit_profile and use_task_validation_profile:
        explicit_profile = dict(task_validation_profile)
    profile_name = _string(explicit_profile.get("profile")).lower()
    validation_focus = _string(
        explicit_profile.get("validation_focus")
        or normalized_task.get("validation_focus")
        or ("event_target_only" if normalized_task.get("task_source") == "event_driven" else "target_plus_representative")
    ).lower() or "target_plus_representative"
    if not profile_name:
        if strategy_type in _FACTOR_VALIDATION_TYPES:
            profile_name = "factor_rank_validation"
        elif strategy_type == "macro_timing":
            profile_name = "macro_regime_validation"
        elif normalized_task.get("task_source") == "event_driven" or validation_focus == "event_target_only":
            profile_name = "event_trade_validation"
        else:
            profile_name = "trade_rule_validation"
    primary_validation_layer = _string(explicit_profile.get("primary_validation_layer")).lower()
    if not primary_validation_layer:
        if validation_focus == "event_target_only":
            primary_validation_layer = "target"
        elif validation_focus == "broad_generalization" or profile_name == "factor_rank_validation":
            primary_validation_layer = "combined"
        else:
            primary_validation_layer = "target"
    return {
        **explicit_profile,
        "profile": profile_name,
        "validation_focus": validation_focus,
        "primary_validation_layer": primary_validation_layer,
    }


def resolve_candidate_targeting_policy(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
    validation_profile: Optional[Mapping[str, Any]] = None,
    constraint_check: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    resolved_validation_profile = dict(
        validation_profile
        or resolve_candidate_validation_profile(payload, research_task=normalized_task)
    )
    explicit_policy = _as_dict(candidate_contract_value(payload, "targeting_policy", {}))
    resolved_constraint_check = _as_dict(
        constraint_check
        if constraint_check is not None
        else candidate_contract_value(payload, "constraint_check", {})
    )
    coverage_ratio_raw = explicit_policy.get("coverage_ratio")
    if coverage_ratio_raw is None:
        coverage_ratio_raw = resolved_constraint_check.get("coverage_ratio")
    intersection_ratio_raw = explicit_policy.get("intersection_ratio")
    if intersection_ratio_raw is None:
        intersection_ratio_raw = resolved_constraint_check.get("intersection_ratio")
    constraint_violation = explicit_policy.get("constraint_violation")
    if constraint_violation is None:
        constraint_violation = (
            resolved_constraint_check.get("constraint_violation")
            or resolved_constraint_check.get("alignment_contract_violation")
        )
    return {
        **explicit_policy,
        "target_symbol_policy": _string(
            explicit_policy.get("target_symbol_policy")
            or normalized_task.get("target_symbol_policy")
            or "prefer_intersection"
        ) or "prefer_intersection",
        "universe_expansion_policy": _string(
            explicit_policy.get("universe_expansion_policy")
            or normalized_task.get("universe_expansion_policy")
            or "allow_market_fallback"
        ) or "allow_market_fallback",
        "validation_focus": _string(
            explicit_policy.get("validation_focus")
            or resolved_validation_profile.get("validation_focus")
            or normalized_task.get("validation_focus")
            or "target_plus_representative"
        ) or "target_plus_representative",
        "constraint_violation": bool(constraint_violation),
        "expansion_applied": bool(
            explicit_policy.get("expansion_applied")
            or resolved_constraint_check.get("expansion_applied")
        ),
        "expansion_reason": (
            explicit_policy.get("expansion_reason")
            or resolved_constraint_check.get("expansion_reason")
        ),
        "expansion_source": (
            explicit_policy.get("expansion_source")
            or resolved_constraint_check.get("expansion_source")
        ),
        "coverage_ratio": round(_safe_float(coverage_ratio_raw, 0.0), 4),
        "intersection_ratio": round(_safe_float(intersection_ratio_raw, 0.0), 4),
    }


def _resolve_target_pool_id(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
    target_symbols: Optional[list[str]] = None,
) -> Optional[str]:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    stock_pool = _as_dict(candidate_contract_value(payload, "stock_pool", {}))
    task_stock_pool = _as_dict(normalized_task.get("stock_pool"))
    provenance = _as_dict(candidate_contract_value(payload, "candidate_provenance", {}))
    resolved_symbols = list(target_symbols or _extract_target_codes_from_payload(payload, limit=12))
    canonical_symbols = _canonical_target_symbols(resolved_symbols)
    for source in (payload, params, stock_pool, task_stock_pool, provenance, normalized_task):
        for key in ("target_pool_id", "pool_id", "active_pool_id", "candidate_pool_id", "theme_code", "theme_id"):
            value = _string(source.get(key))
            if value:
                return value
    selection_mode = _string(stock_pool.get("selection_mode") or task_stock_pool.get("selection_mode")).lower()
    if selection_mode and canonical_symbols:
        return f"{selection_mode}:{','.join(canonical_symbols)}"
    if canonical_symbols:
        return f"symbols:{','.join(canonical_symbols)}"
    return None


def _resolve_lineage(
    candidate: Optional[Mapping[str, Any]],
    *,
    research_task: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    explicit = _as_dict(candidate_contract_value(payload, "lineage", {}))
    event_context = _as_dict(payload.get("event_context") or normalized_task.get("event_context"))
    task_signature = _string(
        explicit.get("task_signature")
        or candidate_contract_value(payload, "task_signature")
        or normalized_task.get("task_signature")
        or _build_task_signature({**normalized_task, **event_context})
    )
    lineage_id = _string(
        explicit.get("lineage_id")
        or candidate_contract_value(payload, "lineage_id")
        or task_signature
    )
    run_id = _string(
        explicit.get("run_id")
        or candidate_contract_value(payload, "run_id")
        or candidate_contract_value(payload, "factory_run_id")
    )
    parent_strategy_ids = _normalize_string_list(
        explicit.get("parent_strategy_ids"),
        explicit.get("parent_candidate_ids"),
        candidate_contract_value(payload, "parent_strategy_ids"),
        candidate_contract_value(payload, "parent_candidate_ids"),
        candidate_contract_value(payload, "parent_strategy_id"),
        candidate_contract_value(payload, "parent_candidate_id"),
    )
    return {
        "lineage_id": lineage_id or None,
        "run_id": run_id or None,
        "task_signature": task_signature or None,
        "parent_strategy_ids": parent_strategy_ids,
    }


def _derive_turnover_cost_class(
    *,
    expected_turnover_band: str,
    capacity_bucket: str,
    slippage_bps: float,
    market_impact_bps: float,
) -> Optional[str]:
    if expected_turnover_band == "very_high" or slippage_bps >= 10.0 or market_impact_bps >= 4.0:
        return "high_touch"
    if expected_turnover_band == "high" or slippage_bps >= 5.0 or capacity_bucket == "small":
        return "medium_touch"
    if expected_turnover_band in {"medium", "low"} or capacity_bucket:
        return "low_touch"
    return None


def _resolve_economic_semantics(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    holding_horizon = _as_dict(candidate_contract_value(payload, "holding_horizon", {}))
    rebalance_rule = _as_dict(candidate_contract_value(payload, "rebalance_rule", {}))
    portfolio_spec = _as_dict(candidate_contract_value(payload, "portfolio_spec", {}))
    execution_assumptions = _as_dict(candidate_contract_value(payload, "execution_assumptions", {}))
    position_sizing = _as_dict(candidate_contract_value(payload, "position_sizing", {}))
    capacity_assumption = _as_dict(candidate_contract_value(payload, "capacity_assumption", {}))
    cost_sensitivity_grid = _as_dict(candidate_contract_value(payload, "cost_sensitivity_grid", {}))
    cost_base_case = _as_dict(cost_sensitivity_grid.get("base_case"))

    expected_turnover_band = _string(
        candidate_contract_value(payload, "expected_turnover_band")
        or execution_assumptions.get("expected_turnover_band")
        or portfolio_spec.get("expected_turnover_band")
        or holding_horizon.get("expected_turnover_band")
        or rebalance_rule.get("expected_turnover_band")
        or position_sizing.get("expected_turnover_band")
    ).lower()
    capacity_bucket = _string(
        candidate_contract_value(payload, "capacity_bucket")
        or execution_assumptions.get("capacity_bucket")
        or portfolio_spec.get("capacity_bucket")
        or capacity_assumption.get("capacity_bucket")
        or capacity_assumption.get("bucket")
    ).lower()
    slippage_bps = _safe_float(
        execution_assumptions.get("slippage_bps"),
        _safe_float(cost_base_case.get("slippage_bps"), 0.0),
    )
    market_impact_bps = _safe_float(
        execution_assumptions.get("market_impact_bps"),
        _safe_float(cost_base_case.get("market_impact_bps"), 0.0),
    )
    position_model = _string(
        candidate_contract_value(payload, "position_model")
        or position_sizing.get("mode")
        or portfolio_spec.get("position_assumption")
    )
    return {
        "holding_rationale": _string(
            candidate_contract_value(payload, "holding_rationale")
            or holding_horizon.get("rationale")
        ) or None,
        "cost_sensitivity_grid": dict(cost_sensitivity_grid),
        "position_model": position_model or None,
        "capacity_assumption": dict(capacity_assumption),
        "market_regime_assumption": (
            candidate_contract_value(payload, "market_regime_assumption")
            if candidate_contract_value(payload, "market_regime_assumption") not in _EMPTY_VALUES
            else None
        ),
        "expected_turnover_band": expected_turnover_band or None,
        "capacity_bucket": capacity_bucket or None,
        "position_sizing_rationale": _string(
            portfolio_spec.get("position_sizing_rationale")
            or execution_assumptions.get("position_sizing_rationale")
            or position_sizing.get("position_sizing_rationale")
            or candidate_contract_value(payload, "position_sizing_rationale")
        ) or None,
        "turnover_cost_class": _string(
            execution_assumptions.get("turnover_cost_class")
            or _derive_turnover_cost_class(
                expected_turnover_band=expected_turnover_band,
                capacity_bucket=capacity_bucket,
                slippage_bps=slippage_bps,
                market_impact_bps=market_impact_bps,
            )
        ) or None,
        "slippage_bps": slippage_bps,
        "market_impact_bps": market_impact_bps,
        "capacity_participation_rate": _safe_float(
            execution_assumptions.get("capacity_participation_rate"),
            _safe_float(
                cost_base_case.get("capacity_participation_rate"),
                _safe_float(capacity_assumption.get("capacity_participation_rate"), 0.0),
            ),
        ),
        "adv_ratio_limit": _safe_float(
            execution_assumptions.get("adv_ratio_limit"),
            _safe_float(
                cost_base_case.get("adv_ratio_limit"),
                _safe_float(capacity_assumption.get("adv_ratio_limit"), 0.0),
            ),
        ),
        "max_position_pct": (
            _safe_float(portfolio_spec.get("max_position_pct"))
            if portfolio_spec.get("max_position_pct") is not None
            else (
                _safe_float(capacity_assumption.get("max_position_pct"))
                if capacity_assumption.get("max_position_pct") is not None
                else None
            )
        ),
    }


def _repair_allowed_strategy_types_for_candidate(
    candidate: Optional[Mapping[str, Any]],
    normalized_task: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = dict(candidate or {})
    task = dict(normalized_task or {})
    strategy_type = _string(payload.get("strategy_type")).lower()
    allowed_strategy_types = _normalize_string_list(task.get("allowed_strategy_types"))
    if not allowed_strategy_types or not strategy_type:
        return task

    allowed_strategy_type_set = {
        _string(item).lower()
        for item in allowed_strategy_types
        if _string(item)
    }
    if strategy_type in allowed_strategy_type_set:
        return task

    strategy_profile = infer_candidate_strategy_profile(payload, research_task=task)
    preferred_strategy_types = {
        _string(item).lower()
        for item in _normalize_string_list(
            task.get("preferred_strategy_types"),
            task.get("strategy_preferences"),
        )
        if _string(item)
    }
    if (
        _string(task.get("task_source")).lower() == "snapshot"
        and strategy_type == "momentum"
        and _string(strategy_profile.get("generator_mode")).lower() == "rl_bandit"
        and strategy_type in preferred_strategy_types
    ):
        return {
            **task,
            "allowed_strategy_types": _normalize_string_list(
                task.get("allowed_strategy_types"),
                strategy_type,
            ),
        }
    return task


def _alignment_violation_from_metrics(
    target_symbols: list[str],
    research_symbols: list[str],
    target_alignment_contract: dict[str, Any],
) -> Optional[str]:
    overlap_count = len(set(target_symbols).intersection(research_symbols))
    coverage_ratio = round(overlap_count / max(1, len(target_symbols)), 4) if target_symbols else 0.0
    intersection_ratio = (
        round(overlap_count / max(1, len(research_symbols)), 4)
        if research_symbols
        else None
    )
    min_coverage_ratio = _safe_float(target_alignment_contract.get("min_coverage_ratio"), 0.0)
    min_intersection_ratio = (
        None
        if target_alignment_contract.get("min_intersection_ratio") is None
        else _safe_float(target_alignment_contract.get("min_intersection_ratio"), 0.0)
    )
    min_required_overlap_count = _safe_int(target_alignment_contract.get("min_required_overlap_count"), 0)
    if not target_symbols and research_symbols:
        return "empty_target_symbols_after_alignment"
    if coverage_ratio < min_coverage_ratio:
        return "coverage_ratio_below_contract"
    if intersection_ratio is not None and min_intersection_ratio is not None and intersection_ratio < min_intersection_ratio:
        return "intersection_ratio_below_contract"
    if min_required_overlap_count > 0 and overlap_count < min_required_overlap_count:
        return "target_overlap_count_below_contract"
    return None


def _refresh_constraint_check_from_targets(
    target_symbols: list[str],
    normalized_task: Optional[Mapping[str, Any]],
    existing_constraint_check: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    task = dict(normalized_task or {})
    existing = _as_dict(existing_constraint_check)
    research_symbols = list(task.get("target_symbols") or [])
    target_alignment_contract = dict(task.get("target_alignment_contract") or {})
    overlap_count = len(set(target_symbols).intersection(research_symbols))
    coverage_ratio = round(overlap_count / max(1, len(target_symbols)), 4) if target_symbols else 0.0
    intersection_ratio = (
        round(overlap_count / max(1, len(research_symbols)), 4)
        if research_symbols
        else None
    )
    alignment_violation = None
    alignment_ok = True
    if target_alignment_contract.get("quality_gate_enabled"):
        alignment_violation = _alignment_violation_from_metrics(
            target_symbols,
            research_symbols,
            target_alignment_contract,
        )
        alignment_ok = alignment_violation is None
    return {
        **existing,
        "target_symbols_before_normalize": list(existing.get("target_symbols_before_normalize") or target_symbols),
        "target_symbols_after_normalize": list(target_symbols),
        "research_target_symbols": list(research_symbols),
        "target_symbol_policy": _string(existing.get("target_symbol_policy") or task.get("target_symbol_policy")) or None,
        "universe_expansion_policy": _string(
            existing.get("universe_expansion_policy") or task.get("universe_expansion_policy")
        ) or None,
        "expansion_applied": bool(existing.get("expansion_applied")),
        "expansion_reason": existing.get("expansion_reason"),
        "expansion_source": existing.get("expansion_source"),
        "constraint_violation": existing.get("constraint_violation"),
        "expansion_blocked_reason": existing.get("expansion_blocked_reason"),
        "coverage_ratio": coverage_ratio,
        "intersection_ratio": intersection_ratio,
        "target_overlap_count": int(overlap_count),
        "alignment_contract_ok": alignment_ok,
        "alignment_contract_violation": alignment_violation,
        "target_alignment_contract": dict(target_alignment_contract),
    }


def _constraint_check_refresh_required(
    target_symbols: list[str],
    normalized_task: Optional[Mapping[str, Any]],
    existing_constraint_check: Optional[Mapping[str, Any]] = None,
) -> bool:
    task = dict(normalized_task or {})
    target_alignment_contract = dict(task.get("target_alignment_contract") or {})
    if not target_alignment_contract.get("quality_gate_enabled"):
        return False

    existing = _as_dict(existing_constraint_check)
    if not existing:
        return True

    refreshed = _refresh_constraint_check_from_targets(
        target_symbols,
        task,
        existing_constraint_check=existing,
    )
    for key in ("coverage_ratio", "intersection_ratio"):
        lhs = existing.get(key)
        rhs = refreshed.get(key)
        if lhs is None and rhs is None:
            continue
        if lhs is None or rhs is None:
            return True
        if abs(_safe_float(lhs) - _safe_float(rhs)) > 1e-4:
            return True
    if _safe_int(existing.get("target_overlap_count"), -1) != _safe_int(refreshed.get("target_overlap_count"), -1):
        return True
    if _string(existing.get("alignment_contract_violation")) != _string(refreshed.get("alignment_contract_violation")):
        return True
    return False
