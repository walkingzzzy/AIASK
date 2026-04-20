

def _should_trim_candidate_targets_by_alignment_policy(
    candidate: Optional[Mapping[str, Any]],
    normalized_task: Optional[Mapping[str, Any]],
    requested_target_symbols: list[str],
) -> bool:
    payload = dict(candidate or {})
    task = dict(normalized_task or {})
    research_symbols = set(task.get("target_symbols") or [])
    if not requested_target_symbols or not research_symbols:
        return False
    requested_set = set(requested_target_symbols)
    if requested_set.issubset(research_symbols):
        return False
    strategy_type = _string(payload.get("strategy_type")).lower()
    strategy_profile = infer_candidate_strategy_profile(payload, research_task=task)
    return (
        _string(task.get("task_source")).lower() == "snapshot"
        and strategy_type == "momentum"
        and _string(strategy_profile.get("generator_mode")).lower() == "rl_bandit"
    )


def build_portfolio_candidate_contract(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(candidate_contract_value(payload, "research_task", {}) or {})
    strategy_profile = infer_candidate_strategy_profile(payload, research_task=normalized_task)
    provenance = _as_dict(candidate_contract_value(payload, "candidate_provenance", {}))
    target_symbols = _extract_target_codes_from_payload(payload, limit=12)
    constraint_check = _as_dict(candidate_contract_value(payload, "constraint_check", {}))
    validation_profile = resolve_candidate_validation_profile(payload, research_task=normalized_task)
    candidate_family = _string(
        candidate_contract_value(payload, "candidate_family")
        or provenance.get("candidate_family")
        or strategy_profile.get("strategy_family")
        or payload.get("strategy_type")
    ).lower()
    candidate_family_id = _string(
        candidate_contract_value(payload, "candidate_family_id")
        or provenance.get("candidate_family_id")
        or strategy_profile.get("candidate_family_id")
    )
    stock_pool = _as_dict(candidate_contract_value(payload, "stock_pool", {}))
    target_source = _string(
        candidate_contract_value(payload, "target_source")
        or stock_pool.get("selection_mode")
        or normalized_task.get("task_source")
        or payload.get("source")
    ).lower()
    economic_semantics = _resolve_economic_semantics(payload)
    targeting = {
        "target_symbols": list(target_symbols),
        "stock_pool": stock_pool,
        "target_pool_id": _resolve_target_pool_id(payload, research_task=normalized_task, target_symbols=target_symbols),
        "coverage_ratio": None
        if constraint_check.get("coverage_ratio") is None
        else round(_safe_float(constraint_check.get("coverage_ratio")), 4),
        "intersection_ratio": None
        if constraint_check.get("intersection_ratio") is None
        else round(_safe_float(constraint_check.get("intersection_ratio")), 4),
        "target_overlap_count": _safe_int(constraint_check.get("target_overlap_count")),
        "target_source": target_source or None,
        "constraint_check": constraint_check,
    }
    contract = {
        "candidate_id": _string(payload.get("candidate_id") or payload.get("id")) or None,
        "name": _string(payload.get("name")) or None,
        "strategy_type": _string(payload.get("strategy_type")).lower() or "unknown",
        "generator_mode": _string(payload.get("generator_mode") or strategy_profile.get("generator_mode")).lower() or None,
        "candidate_family": candidate_family or None,
        "candidate_family_id": candidate_family_id or None,
        "targeting": targeting,
        "research_task": normalized_task,
        "holding_horizon": _as_dict(candidate_contract_value(payload, "holding_horizon", {})),
        "trade_plan": _as_dict(candidate_contract_value(payload, "trade_plan", {})),
        "risk_rules": _as_dict(candidate_contract_value(payload, "risk_rules", {})),
        "runtime_playbook": _as_dict(candidate_contract_value(payload, "runtime_playbook", {})),
        "rebalance_rule": candidate_contract_value(payload, "rebalance_rule", {}),
        "portfolio_spec": _as_dict(candidate_contract_value(payload, "portfolio_spec", {})),
        "execution_assumptions": _as_dict(candidate_contract_value(payload, "execution_assumptions", {})),
        "instrument_profile": _as_dict(candidate_contract_value(payload, "instrument_profile", {})),
        "economic_semantics": economic_semantics,
        "validation_profile": validation_profile,
        "lineage": _resolve_lineage(payload, research_task=normalized_task),
    }
    for field_name in ("evidence_chain", "prediction_contract", "confidence_contract"):
        value = _as_dict(candidate_contract_value(payload, field_name, {}))
        if value:
            contract[field_name] = value
    return contract


def build_resolved_candidate_envelope(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    existing_envelope = _as_dict(payload.get("resolved_candidate_envelope"))
    params = _as_dict(payload.get("params"))
    if "had_explicit_research_task" in existing_envelope:
        had_explicit_research_task = bool(existing_envelope.get("had_explicit_research_task"))
    else:
        had_explicit_research_task = False
        for raw_task in (payload.get("research_task"), params.get("research_task")):
            task_payload = dict(raw_task or {}) if isinstance(raw_task, Mapping) else {}
            if not task_payload:
                continue
            if bool(task_payload.get("synthetic_local_spawn")):
                continue
            had_explicit_research_task = True
            break
    normalized_task = _normalize_research_task_contract(
        existing_envelope.get("normalized_research_task")
        or candidate_contract_value(payload, "research_task", {})
        or {}
    )
    normalized_task = _repair_allowed_strategy_types_for_candidate(payload, normalized_task)
    requested_target_symbols = _normalize_target_codes(
        candidate_contract_value(payload, "requested_target_symbols")
        or existing_envelope.get("requested_target_symbols")
        or _extract_candidate_origin_target_codes(payload, limit=12)
        or _extract_target_codes_from_payload(payload, limit=12),
        limit=12,
    )
    raw_constraint_check = _as_dict(candidate_contract_value(payload, "constraint_check", {}))
    should_trim_targets = _should_trim_candidate_targets_by_alignment_policy(
        payload,
        normalized_task,
        requested_target_symbols,
    )
    if should_trim_targets:
        aligned_targeting = _apply_target_symbol_policy(
            requested_target_symbols,
            normalized_task,
            fallback_symbols=[
                normalized_task.get("target_symbols"),
                normalized_task.get("stock_pool"),
            ],
            limit=12,
        )
        resolved_target_symbols = _canonical_target_symbols(
            aligned_targeting.get("target_symbols"),
            limit=12,
        )
        resolved_constraint_check = {
            **raw_constraint_check,
            **_as_dict(aligned_targeting.get("constraint_check")),
        }
    else:
        resolved_target_symbols = _canonical_target_symbols(
            requested_target_symbols,
            limit=12,
        )
        resolved_constraint_check = dict(raw_constraint_check)
    if _constraint_check_refresh_required(
        resolved_target_symbols,
        normalized_task,
        resolved_constraint_check,
    ):
        resolved_constraint_check = _refresh_constraint_check_from_targets(
            resolved_target_symbols,
            normalized_task,
            existing_constraint_check=resolved_constraint_check,
        )
    resolved_stock_pool = _as_dict(
        existing_envelope.get("resolved_stock_pool")
        or candidate_contract_value(payload, "stock_pool", {})
        or normalized_task.get("stock_pool")
        or {}
    )
    if resolved_target_symbols:
        resolved_stock_pool = {
            **resolved_stock_pool,
            "selection_mode": _string(resolved_stock_pool.get("selection_mode") or "explicit") or "explicit",
            "symbols": list(resolved_target_symbols),
        }

    resolved_payload = {
        **payload,
        "research_task": normalized_task,
        "target_symbols": list(resolved_target_symbols),
        "stock_pool": dict(resolved_stock_pool),
        "constraint_check": dict(resolved_constraint_check),
        "params": {
            **params,
            "research_task": dict(normalized_task),
            "requested_target_symbols": list(requested_target_symbols),
            "target_symbols": list(resolved_target_symbols),
            "stock_pool": dict(resolved_stock_pool),
            "constraint_check": dict(resolved_constraint_check),
        },
    }
    contract_snapshot = build_portfolio_candidate_contract(resolved_payload)
    resolved_target_symbols = list((contract_snapshot.get("targeting") or {}).get("target_symbols") or resolved_target_symbols)
    resolved_stock_pool = _as_dict((contract_snapshot.get("targeting") or {}).get("stock_pool") or resolved_stock_pool)
    resolved_constraint_check = _as_dict((contract_snapshot.get("targeting") or {}).get("constraint_check") or resolved_constraint_check)
    resolved_validation_profile = dict(
        contract_snapshot.get("validation_profile")
        or resolve_candidate_validation_profile(resolved_payload, research_task=normalized_task)
    )
    resolved_targeting_policy = resolve_candidate_targeting_policy(
        resolved_payload,
        research_task=normalized_task,
        validation_profile=resolved_validation_profile,
        constraint_check=resolved_constraint_check,
    )
    alpha_identity_components = build_alpha_identity_components(resolved_payload)
    execution_contract_hash = build_execution_contract_hash(contract=contract_snapshot)
    candidate_contract_hash = execution_contract_hash
    tested_object_hash = build_tested_object_hash(resolved_payload)
    candidate_identity_signature = build_candidate_identity_signature(resolved_payload)
    candidate_lineage_contract = dict(contract_snapshot.get("lineage") or {})
    return {
        "had_explicit_research_task": bool(had_explicit_research_task),
        "normalized_research_task": normalized_task,
        "requested_target_symbols": list(requested_target_symbols),
        "resolved_target_symbols": list(resolved_target_symbols),
        "resolved_stock_pool": dict(resolved_stock_pool),
        "resolved_constraint_check": dict(resolved_constraint_check),
        "resolved_validation_profile": dict(resolved_validation_profile),
        "resolved_targeting_policy": dict(resolved_targeting_policy),
        "candidate_contract_snapshot": contract_snapshot,
        "candidate_contract_hash": candidate_contract_hash,
        "execution_contract_hash": execution_contract_hash,
        "tested_object_hash": tested_object_hash,
        "candidate_identity_signature": candidate_identity_signature,
        "candidate_lineage_contract": candidate_lineage_contract,
        "logic_signature": alpha_identity_components.get("logic_signature"),
        "dsl_signature": alpha_identity_components.get("dsl_signature"),
        "factor_signature": alpha_identity_components.get("factor_signature"),
        "entry_exit_signature": alpha_identity_components.get("entry_exit_signature"),
    }


def apply_resolved_candidate_envelope(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    envelope = build_resolved_candidate_envelope(payload)
    resolved_validation_profile = dict(envelope.get("resolved_validation_profile") or {})
    resolved_targeting_policy = dict(envelope.get("resolved_targeting_policy") or {})
    params = {
        **_as_dict(payload.get("params")),
        "had_explicit_research_task": bool(envelope.get("had_explicit_research_task")),
        "research_task": dict(envelope.get("normalized_research_task") or {}),
        "requested_target_symbols": list(envelope.get("requested_target_symbols") or []),
        "target_symbols": list(envelope.get("resolved_target_symbols") or []),
        "stock_pool": dict(envelope.get("resolved_stock_pool") or {}),
        "constraint_check": dict(envelope.get("resolved_constraint_check") or {}),
        "runtime_playbook": _as_dict(candidate_contract_value(payload, "runtime_playbook", {})),
        "validation_profile": resolved_validation_profile,
        "targeting_policy": resolved_targeting_policy,
        "candidate_contract_snapshot": dict(envelope.get("candidate_contract_snapshot") or {}),
        "candidate_contract_hash": envelope.get("candidate_contract_hash"),
        "execution_contract_hash": envelope.get("execution_contract_hash"),
        "tested_object_hash": envelope.get("tested_object_hash"),
        "candidate_identity_signature": envelope.get("candidate_identity_signature"),
        "candidate_lineage_contract": dict(envelope.get("candidate_lineage_contract") or {}),
        "logic_signature": envelope.get("logic_signature"),
        "dsl_signature": envelope.get("dsl_signature"),
        "factor_signature": envelope.get("factor_signature"),
        "entry_exit_signature": envelope.get("entry_exit_signature"),
        "candidate_origin": candidate_contract_value(payload, "candidate_origin"),
        "event_anchor": _as_dict(candidate_contract_value(payload, "event_anchor", {})),
        "target_pool_source": candidate_contract_value(payload, "target_pool_source"),
        "resolved_candidate_envelope": envelope,
    }
    return {
        **payload,
        "params": params,
        "had_explicit_research_task": bool(envelope.get("had_explicit_research_task")),
        "research_task": dict(envelope.get("normalized_research_task") or {}),
        "requested_target_symbols": list(envelope.get("requested_target_symbols") or []),
        "target_symbols": list(envelope.get("resolved_target_symbols") or []),
        "stock_pool": dict(envelope.get("resolved_stock_pool") or {}),
        "constraint_check": dict(envelope.get("resolved_constraint_check") or {}),
        "validation_profile": resolved_validation_profile,
        "targeting_policy": resolved_targeting_policy,
        "candidate_contract_snapshot": dict(envelope.get("candidate_contract_snapshot") or {}),
        "candidate_contract_hash": str(envelope.get("candidate_contract_hash") or ""),
        "execution_contract_hash": str(envelope.get("execution_contract_hash") or ""),
        "tested_object_hash": str(envelope.get("tested_object_hash") or ""),
        "candidate_identity_signature": str(envelope.get("candidate_identity_signature") or ""),
        "candidate_lineage_contract": dict(envelope.get("candidate_lineage_contract") or {}),
        "logic_signature": str(envelope.get("logic_signature") or ""),
        "dsl_signature": str(envelope.get("dsl_signature") or ""),
        "factor_signature": str(envelope.get("factor_signature") or ""),
        "entry_exit_signature": str(envelope.get("entry_exit_signature") or ""),
        "candidate_origin": candidate_contract_value(payload, "candidate_origin"),
        "event_anchor": _as_dict(candidate_contract_value(payload, "event_anchor", {})),
        "target_pool_source": candidate_contract_value(payload, "target_pool_source"),
        "resolved_candidate_envelope": envelope,
    }


def build_execution_contract_hash(
    candidate: Optional[Mapping[str, Any]] = None,
    *,
    contract: Optional[Mapping[str, Any]] = None,
) -> str:
    payload = dict(contract or build_portfolio_candidate_contract(candidate))
    semantic_payload = _semantic_contract_payload(payload)
    return _hash_payload(semantic_payload)


def build_candidate_contract_hash(
    candidate: Optional[Mapping[str, Any]] = None,
    *,
    contract: Optional[Mapping[str, Any]] = None,
) -> str:
    return build_execution_contract_hash(candidate, contract=contract)


def build_tested_object_hash(candidate: Optional[Mapping[str, Any]]) -> str:
    alpha_identity = build_alpha_identity_components(candidate)
    tested_object_payload = {
        "strategy_type": alpha_identity.get("strategy_type"),
        "logic_signature": alpha_identity.get("logic_signature"),
        "dsl_signature": alpha_identity.get("dsl_signature"),
        "factor_signature": alpha_identity.get("factor_signature"),
        "entry_exit_signature": alpha_identity.get("entry_exit_signature"),
    }
    return _hash_payload(tested_object_payload)


def build_candidate_identity_signature(candidate: Optional[Mapping[str, Any]]) -> str:
    contract = _semantic_contract_payload(build_portfolio_candidate_contract(candidate))
    targeting = dict(contract.get("targeting") or {})
    lineage = dict(contract.get("lineage") or {})
    execution_contract_hash = build_execution_contract_hash(contract=contract)
    identity_payload = {
        "strategy_type": contract.get("strategy_type"),
        "candidate_family_id": contract.get("candidate_family_id"),
        "execution_contract_hash": execution_contract_hash,
        "tested_object_hash": build_tested_object_hash(candidate),
        "validation_profile": dict(contract.get("validation_profile") or {}),
        "targeting": {
            "target_pool_id": targeting.get("target_pool_id"),
            "target_symbols": list(targeting.get("target_symbols") or []),
        },
        "holding_horizon": dict(contract.get("holding_horizon") or {}),
        "trade_plan": dict(contract.get("trade_plan") or {}),
        "risk_rules": dict(contract.get("risk_rules") or {}),
        "runtime_playbook": dict(contract.get("runtime_playbook") or {}),
        "rebalance_rule": contract.get("rebalance_rule"),
        "portfolio_spec": dict(contract.get("portfolio_spec") or {}),
        "execution_assumptions": dict(contract.get("execution_assumptions") or {}),
        "lineage_id": lineage.get("lineage_id"),
        "task_signature": lineage.get("task_signature"),
    }
    return _hash_payload(identity_payload)


def build_candidate_contract_backfill(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    resolved = apply_resolved_candidate_envelope(candidate)
    contract_snapshot = dict(resolved.get("candidate_contract_snapshot") or build_portfolio_candidate_contract(resolved))
    targeting = dict(contract_snapshot.get("targeting") or {})
    params = _as_dict(resolved.get("params"))
    alpha_identity = build_alpha_identity_components(resolved)
    has_material_logic = bool(alpha_identity.get("has_material_logic"))
    legacy_identity_partial = not has_material_logic
    tested_object_backfill_incomplete = not has_material_logic
    return {
        "candidate_contract_snapshot": contract_snapshot,
        "candidate_contract_hash": str(resolved.get("candidate_contract_hash") or build_candidate_contract_hash(contract=contract_snapshot)),
        "execution_contract_hash": str(resolved.get("execution_contract_hash") or build_execution_contract_hash(contract=contract_snapshot)),
        "candidate_identity_signature": str(
            resolved.get("candidate_identity_signature") or build_candidate_identity_signature(resolved)
        ),
        "tested_object_hash": str(resolved.get("tested_object_hash") or build_tested_object_hash(resolved)),
        "candidate_lineage_contract": dict(
            resolved.get("candidate_lineage_contract") or contract_snapshot.get("lineage") or {}
        ),
        "target_pool_id": targeting.get("target_pool_id"),
        "logic_signature": str(alpha_identity.get("logic_signature") or params.get("logic_signature") or ""),
        "dsl_signature": str(alpha_identity.get("dsl_signature") or params.get("dsl_signature") or ""),
        "factor_signature": str(alpha_identity.get("factor_signature") or params.get("factor_signature") or ""),
        "entry_exit_signature": str(alpha_identity.get("entry_exit_signature") or params.get("entry_exit_signature") or ""),
        "legacy_identity_partial": legacy_identity_partial,
        "tested_object_backfill_incomplete": tested_object_backfill_incomplete,
    }


def build_factory_backtest_assumptions(candidate: Optional[Mapping[str, Any]]) -> FactoryBacktestAssumptions:
    contract = build_portfolio_candidate_contract(candidate)
    execution_assumptions = normalize_execution_assumptions(
        contract.get("execution_assumptions"),
        portfolio_spec=contract.get("portfolio_spec"),
        capacity_assumption=candidate_contract_value(candidate, "capacity_assumption", {}),
        holding_horizon=contract.get("holding_horizon"),
        cost_sensitivity_grid=candidate_contract_value(candidate, "cost_sensitivity_grid", {}),
    )
    portfolio_spec = dict(contract.get("portfolio_spec") or {})
    validation_profile = dict(contract.get("validation_profile") or {})
    economic_semantics = dict(contract.get("economic_semantics") or {})
    target_symbols = list((contract.get("targeting") or {}).get("target_symbols") or [])
    target_weight_scheme = _string(
        portfolio_spec.get("target_weight_scheme")
        or ("equal_weight" if len(target_symbols) > 1 else "single_name")
    ) or ("equal_weight" if len(target_symbols) > 1 else "single_name")
    return FactoryBacktestAssumptions(
        initial_capital=_safe_float(execution_assumptions.get("initial_capital"), 100000.0),
        commission_rate=_safe_float(execution_assumptions.get("commission_rate"), 0.00025),
        slippage_bps=_safe_float(
            execution_assumptions.get("slippage_bps"),
            _safe_float(
                execution_assumptions.get("slippage"),
                _safe_float(economic_semantics.get("slippage_bps"), 0.0) / 10000.0,
            ) * 10000.0,
        ),
        market_impact_bps=_safe_float(
            execution_assumptions.get("market_impact_bps"),
            _safe_float(economic_semantics.get("market_impact_bps"), 0.0),
        ),
        arrival_price_policy=_string(execution_assumptions.get("arrival_price_policy") or "next_open_proxy") or "next_open_proxy",
        implementation_shortfall_proxy=_safe_float(execution_assumptions.get("implementation_shortfall_proxy"), 0.0),
        tradability_filter=_safe_bool(execution_assumptions.get("tradability_filter"), True),
        slippage_model=_string(execution_assumptions.get("slippage_model") or "fixed") or "fixed",
        max_position_pct=(
            _safe_float(portfolio_spec.get("max_position_pct"))
            if portfolio_spec.get("max_position_pct") is not None
            else (
                _safe_float(economic_semantics.get("max_position_pct"))
                if economic_semantics.get("max_position_pct") is not None
                else None
            )
        ),
        capacity_participation_rate=_safe_float(
            execution_assumptions.get("capacity_participation_rate"),
            _safe_float(economic_semantics.get("capacity_participation_rate"), 0.0),
        ),
        adv_ratio_limit=_safe_float(
            execution_assumptions.get("adv_ratio_limit"),
            _safe_float(economic_semantics.get("adv_ratio_limit"), 0.0),
        ),
        capacity_bucket=_string(
            execution_assumptions.get("capacity_bucket")
            or economic_semantics.get("capacity_bucket")
        ) or None,
        margin_rate=(
            _safe_float(execution_assumptions.get("margin_rate"))
            if execution_assumptions.get("margin_rate") is not None
            else None
        ),
        contract_multiplier=(
            _safe_int(execution_assumptions.get("contract_multiplier"))
            if execution_assumptions.get("contract_multiplier") is not None
            else None
        ),
        liquidity_bucket=_string(execution_assumptions.get("liquidity_bucket")) or None,
        max_contracts_per_rebalance=(
            _safe_int(execution_assumptions.get("max_contracts_per_rebalance"))
            if execution_assumptions.get("max_contracts_per_rebalance") is not None
            else None
        ),
        position_assumption=_string(
            portfolio_spec.get("position_assumption")
            or economic_semantics.get("position_model")
            or ("equal_weight_proxy" if len(target_symbols) > 1 else "single_name_full_notional")
        )
        or ("equal_weight_proxy" if len(target_symbols) > 1 else "single_name_full_notional"),
        target_weight_scheme=target_weight_scheme,
        target_weight_map=_as_dict(portfolio_spec.get("target_weight_map")),
        turnover_cost_class=_string(
            execution_assumptions.get("turnover_cost_class")
            or economic_semantics.get("turnover_cost_class")
        ) or None,
        position_sizing_rationale=_string(
            portfolio_spec.get("position_sizing_rationale")
            or execution_assumptions.get("position_sizing_rationale")
            or economic_semantics.get("position_sizing_rationale")
            or candidate_contract_value(candidate, "position_sizing_rationale")
        )
        or None,
        expected_turnover_band=_string(
            execution_assumptions.get("expected_turnover_band")
            or portfolio_spec.get("expected_turnover_band")
            or economic_semantics.get("expected_turnover_band")
            or dict(contract.get("holding_horizon") or {}).get("expected_turnover_band")
            or candidate_contract_value(candidate, "expected_turnover_band")
        )
        or None,
        market_regime_assumption=(
            economic_semantics.get("market_regime_assumption")
            if economic_semantics.get("market_regime_assumption") not in _EMPTY_VALUES
            else None
        ),
        market_ruleset=_string(execution_assumptions.get("market_ruleset") or "cn_equity") or "cn_equity",
        sell_tax_rate=_safe_float(execution_assumptions.get("sell_tax_rate"), 0.001),
        min_trade_lot=max(1, _safe_int(execution_assumptions.get("min_trade_lot"), 100)),
        t_plus_one=_safe_bool(execution_assumptions.get("t_plus_one"), True),
        validation_focus=_string(validation_profile.get("validation_focus") or "target_plus_representative")
        or "target_plus_representative",
    )
