

def _liquidity_threshold(requirement: str, proxy_kind: Optional[str]) -> float:
    requirement = str(requirement or "all").strip().lower() or "all"
    if requirement == "all":
        return 0.0
    if proxy_kind == "avg_daily_turnover":
        return float(_PRE_GATE_TURNOVER_THRESHOLDS.get(requirement, 0.0) or 0.0)
    return float(_PRE_GATE_MARKET_CAP_THRESHOLDS.get(requirement, 0.0) or 0.0)


def _estimate_signal_density(strategy_type: str, params: dict[str, Any]) -> float:
    strategy_type = str(strategy_type or "").strip().lower()
    lookback = max(2, int(params.get("lookback", params.get("period", 20)) or 20))
    threshold = max(0.005, _safe_float(params.get("threshold", 0.02), 0.02))
    if strategy_type == "ma_cross":
        short_period = max(2, int(params.get("short_period", 5) or 5))
        long_period = max(short_period + 1, int(params.get("long_period", 20) or 20))
        return round(252.0 / max((short_period + long_period) / 2.0, 4.0), 4)
    if strategy_type in {"momentum", "volatility_breakout", "event_structure_breakout", "north_capital_track"}:
        density = 252.0 / max(float(lookback), 3.0)
        density *= max(0.35, min(1.8, 0.02 / threshold))
        if strategy_type == "event_structure_breakout":
            density *= 0.72
        return round(density, 4)
    if strategy_type in {"rsi", "gap_fill", "mean_reversion_short"}:
        period = max(2, int(params.get("rsi_period", 14) or 14))
        band_width = max(5.0, _safe_float(params.get("overbought", 70), 70.0) - _safe_float(params.get("oversold", 30), 30.0))
        density = 252.0 / max(period * 0.75, 2.0)
        density *= max(0.5, min(1.5, 40.0 / band_width))
        return round(density, 4)
    if strategy_type in {"value_factor", "quality_factor", "growth_factor", "multi_factor", "sector_rotation"}:
        return round(252.0 / max(lookback * 0.45, 8.0), 4)
    if strategy_type in {"macro_timing", "margin_divergence"}:
        return round(252.0 / max(lookback * 1.1, 6.0), 4)
    return 12.0


# ---------------------------------------------------------------------------
# Gate-0: 结构校验
# ---------------------------------------------------------------------------

_VALID_STRATEGY_TYPES = frozenset({
    "momentum", "ma_cross", "rsi",
    "value_factor", "quality_factor", "growth_factor",
    "multi_factor", "macro_timing", "dsl_rule",
    "volatility_breakout", "event_structure_breakout", "gap_fill", "mean_reversion_short",
    "sector_rotation", "north_capital_track", "margin_divergence",
})
_REQUIRED_TRADE_FIELDS = frozenset({
    "holding_horizon",
    "trade_plan",
    "risk_rules",
    "rebalance_rule",
    "portfolio_spec",
    "execution_assumptions",
    "validation_profile",
})
_LEGACY_TRADE_ENRICHMENT_REQUIRED_FIELDS = frozenset(_REQUIRED_TRADE_FIELDS - {"validation_profile"})


def _should_enrich_legacy_gate_0_candidate(candidate: dict) -> bool:
    payload = dict(candidate or {})
    if not payload:
        return False
    missing_trade_fields = [
        key for key in sorted(_REQUIRED_TRADE_FIELDS)
        if candidate_contract_value(payload, key) in (None, "", [], {})
    ]
    return bool(missing_trade_fields)


def _enrich_legacy_gate_0_candidate(candidate: dict) -> dict:
    if not _should_enrich_legacy_gate_0_candidate(candidate):
        return candidate
    payload = dict(candidate or {})
    contract_snapshot = build_portfolio_candidate_contract(payload)
    assumptions = build_factory_backtest_assumptions(payload)
    holding_horizon = dict(contract_snapshot.get("holding_horizon") or {})
    max_days = max(1, int(holding_horizon.get("max_days") or 10))
    defaults = {
        "holding_horizon": {"max_days": max_days},
        "trade_plan": {"entry_bias": "signal_confirmed", "exit_bias": "signal_or_time_stop"},
        "risk_rules": {
            "stop_loss_pct": 0.08,
            "take_profit_pct": 0.18,
            "max_holding_days": max_days,
        },
        "rebalance_rule": {"mode": "signal_rebalance"},
        "portfolio_spec": {
            "position_assumption": assumptions.position_assumption,
            "target_weight_scheme": assumptions.target_weight_scheme,
        },
        "execution_assumptions": {
            "slippage_bps": assumptions.slippage_bps,
            "commission_rate": assumptions.commission_rate,
            "tradability_filter": assumptions.tradability_filter,
            "slippage_model": assumptions.slippage_model or "fixed",
        },
        "validation_profile": dict(contract_snapshot.get("validation_profile") or {}),
    }
    enriched = dict(payload)
    params = dict(enriched.get("params") or {})
    for key in sorted(_REQUIRED_TRADE_FIELDS):
        default_value = deepcopy(defaults.get(key) or contract_snapshot.get(key))
        if candidate_contract_value(enriched, key) in (None, "", [], {}):
            enriched[key] = deepcopy(default_value)
        params.setdefault(key, deepcopy(default_value))
    enriched["params"] = params
    return enriched


def gate_0_structural(candidate: dict) -> GateResult:
    """纯同步结构校验。"""
    reasons: list[str] = []
    strategy_type = str(candidate.get("strategy_type") or "").strip()
    if not strategy_type:
        reasons.append("missing_strategy_type")
    elif strategy_type not in _VALID_STRATEGY_TYPES:
        reasons.append(f"invalid_strategy_type:{strategy_type}")

    params = candidate.get("params")
    if params is None:
        reasons.append("missing_params")
    elif not isinstance(params, dict):
        reasons.append("params_not_dict")
    elif params:
        # 检查 params 是否只包含任务元数据（无实际策略参数）
        _META_ONLY_KEYS = {
            "task_attempt_count", "task_stage_attempt_count", "candidate_local_attempt_count",
            "task_local_attempt_count", "candidate_local_selected_count", "task_local_selected_count",
            "task_network_request_count", "task_real_request_count", "task_compatibility_skip_count",
            "task_cooldown_skip_count", "task_compatibility_failure_count",
            "task_effective_response_count", "task_empty_200_response_count",
            "task_compatibility_failure_ratio", "task_effective_response_ratio",
            "task_selected_count",
        }
        actual_strategy_keys = {k for k in params.keys() if k not in _META_ONLY_KEYS}
        if not actual_strategy_keys:
            # 只有元数据，无策略参数 → 用 Spawner 补充（不阻断，只补充）
            try:
                from strategy_factory.domain.spawner import StrategySpawner
                from strategy_factory.domain.parameter_distribution_registry import (
                    ParameterDistributionRegistry,
                )
                spawner = StrategySpawner.__new__(StrategySpawner)
                default_params = spawner._legacy_varied_defaults(strategy_type, 0, snapshot=None)
                # PR-S21：优先取 task 上的 stock_profile 参数 band（更专属）
                research_task = dict(candidate.get("research_task") or {})
                band = (
                    research_task.get("param_search_space")
                    or research_task.get("profile_param_band")
                )
                band_sample = ParameterDistributionRegistry.sample_from_param_band(band, idx=0)
                merged_defaults = dict(default_params or {})
                if band_sample:
                    merged_defaults.update(dict(band_sample.get("params") or {}))
                if merged_defaults:
                    candidate["params"] = {**merged_defaults, **params}
            except Exception:
                pass

    missing_trade_fields = [
        key for key in sorted(_REQUIRED_TRADE_FIELDS)
        if candidate_contract_value(candidate, key) in (None, "", [], {})
    ]
    if missing_trade_fields:
        reasons.append(f"missing_trade_fields:{','.join(missing_trade_fields)}")

    # DSL 编译检查（可选）
    if strategy_type == "dsl_rule":
        dsl = (params or {}).get("dsl") if isinstance(params, dict) else None
        if not dsl or not isinstance(dsl, dict):
            reasons.append("dsl_rule_missing_dsl_payload")
        else:
            try:
                compile_strategy_blueprint = get_strategy_dsl_compiler()
                compile_strategy_blueprint(candidate, tune_for_factory=True)
            except Exception as exc:
                reasons.append(f"dsl_compile_failed:{type(exc).__name__}")

    return GateResult(passed=len(reasons) == 0, gate="gate_0", reasons=reasons)


def pre_gate_screen(
    candidate: dict,
    *,
    seen_signatures: Optional[set[str]] = None,
    family_counts: Optional[Dict[str, int]] = None,
    stock_counts: Optional[Dict[str, int]] = None,
    family_quota_limit: int = _PRE_GATE_FAMILY_QUOTA_DEFAULT,
    per_stock_quota_limit: int = _PRE_GATE_PER_STOCK_QUOTA_DEFAULT,
) -> GateResult:
    """廉价预筛：约束任务类型一致性、单股矩阵目标完整性与重复候选。"""
    payload = dict(candidate or {})
    reasons: list[str] = []
    raw_research_task = dict(payload.get("research_task") or {})
    # PR-E (Phase 3, 2026-05-24): capture the operator-supplied
    # ``target_alignment_contract`` *before* normalize. Normalize will
    # always synthesize a default contract from ``target_symbols`` /
    # ``strategy_type``, which would mask the operator's explicit cap.
    # Gate priority #1 must look at the *raw* contract, not the
    # synthesized one.
    raw_user_contract = (
        raw_research_task.get("target_alignment_contract")
        or payload.get("target_alignment_contract")
        or {}
    )
    research_task = _normalize_research_task_contract(raw_research_task)
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    # PR-E: ``target_codes`` keeps the legacy 12-cap so quota/snapshot
    # bookkeeping stays untouched. The *real* count for the dynamic
    # limit check is derived separately below from the unbounded payload.
    target_codes = _extract_target_codes_from_payload(payload, limit=12)
    raw_target_codes = _extract_target_codes_from_payload(payload, limit=64)
    tags = _candidate_tags(payload)
    allowed_strategy_types = {
        str(item).strip().lower()
        for item in list(research_task.get("allowed_strategy_types") or [])
        if str(item).strip()
    }
    signature = candidate_signature(payload)
    task_source = str(research_task.get("task_source") or "").strip().lower()
    strategy_profile = infer_candidate_strategy_profile(payload, research_task=research_task)
    candidate_family = str(
        payload.get("candidate_family")
        or strategy_profile.get("strategy_family")
        or strategy_type
        or "unknown"
    ).strip().lower() or "unknown"
    family_used_before = int((family_counts or {}).get(candidate_family) or 0)
    per_stock_quota_increment = _per_stock_quota_increment(payload, research_task, target_codes)
    stock_quota_snapshot = {
        code: round(_safe_float((stock_counts or {}).get(code), 0.0), 4)
        for code in target_codes
    }
    constraint_check = _candidate_constraint_check(payload)
    coverage_ratio_raw = constraint_check.get("coverage_ratio")
    intersection_ratio_raw = constraint_check.get("intersection_ratio")
    coverage_ratio = None if coverage_ratio_raw is None else round(_safe_float(coverage_ratio_raw, 0.0), 4)
    intersection_ratio = None if intersection_ratio_raw is None else round(_safe_float(intersection_ratio_raw, 0.0), 4)
    validation_focus = str(research_task.get("validation_focus") or "").strip().lower()
    targeted_snapshot = _is_targeted_snapshot_candidate(
        payload,
        research_task,
        tags=tags,
        target_count=len(target_codes),
        validation_focus=validation_focus,
    )
    target_quality_summary = build_target_quality_gate_summary(payload)
    explicit_target_sample_count = None
    if targeted_snapshot:
        explicit_raw = (
            payload.get("gate_1_representative_count")
            or research_task.get("gate_1_representative_count")
        )
        if explicit_raw is not None:
            try:
                explicit_target_sample_count = max(1, int(explicit_raw))
            except Exception:
                explicit_target_sample_count = None
    resolved_target_sample_count = len(_resolve_gate_1_codes(payload)[1]) if targeted_snapshot else None
    planned_target_sample_count = (
        explicit_target_sample_count
        if explicit_target_sample_count is not None
        else resolved_target_sample_count
    )
    min_target_sample_count = int(target_quality_summary.get("min_target_sample_count") or 0)

    if allowed_strategy_types and strategy_type and strategy_type not in allowed_strategy_types:
        reasons.append("outside_allowed_strategy_types")
    if task_source == "bulk_stock_matrix":
        if not target_codes:
            reasons.append("bulk_stock_matrix_missing_target_symbols")
        elif len(target_codes) != 1:
            reasons.append("bulk_stock_matrix_requires_single_target")
    elif task_source == "event_driven" and not target_codes:
        reasons.append("event_task_missing_target_symbols")

    # PR-E (Phase 3, 2026-05-24): replace the hardcoded ``> 12`` check
    # with the canonical ``resolve_target_symbol_limit`` so:
    #   - ``snapshot`` and other legacy task_sources still cap at 12;
    #   - ``event_driven`` honors the dynamic feature flag (defaults to
    #     12 in 5a, allows up to 30 in 5b);
    #   - operators see the *actual* limit in the reject reason.
    #
    # Resolution priority (matches plan §6 Phase 3):
    #   1. operator-supplied target_alignment_contract.max_candidate_target_symbols
    #      (raw, pre-normalize — see ``raw_user_contract`` above)
    #   2. research_task.target_symbol_limit (rare; legacy override)
    #   3. resolve_target_symbol_limit(task_source=...)
    #
    # Why we use ``raw_user_contract`` instead of the normalized one:
    # ``_normalize_research_task_contract`` always synthesizes a default
    # ``target_alignment_contract`` from ``target_symbols`` /
    # ``strategy_type`` (typically capping at 8 for event_targeted,
    # 4 for snapshot pipelines). Reading the normalized contract would
    # mean the gate's "5b allow 30" path can never be reached because
    # the synthesized cap of 8 always wins priority #1.
    contract_cap = 0
    try:
        contract_cap = int((raw_user_contract or {}).get("max_candidate_target_symbols") or 0)
    except (TypeError, ValueError):
        contract_cap = 0

    explicit_limit = 0
    explicit_raw = research_task.get("target_symbol_limit") or payload.get("target_symbol_limit")
    if explicit_raw is not None:
        try:
            explicit_limit = int(explicit_raw)
        except (TypeError, ValueError):
            explicit_limit = 0

    fallback_limit = resolve_target_symbol_limit(
        task_source=task_source,
        validation_focus=validation_focus,
    )

    target_symbol_limit = max(
        1,
        contract_cap if contract_cap > 0 else (explicit_limit if explicit_limit > 0 else fallback_limit),
    )

    if len(target_codes) > target_symbol_limit:
        reasons.append(
            f"target_symbol_count_exceeds_limit:{target_symbol_limit}"
        )
    elif len(raw_target_codes) > target_symbol_limit:
        # ``target_codes`` is already capped at 12 by the legacy extractor;
        # if the raw payload would have exceeded the dynamic limit, we
        # still surface the violation so 5b operators (limit > 12) see
        # the real reject.
        reasons.append(
            f"target_symbol_count_exceeds_limit:{target_symbol_limit}"
        )
    if (
        targeted_snapshot
        and "target_universe_alignment_too_low" in list(target_quality_summary.get("reasons") or [])
    ):
        reasons.append("target_universe_alignment_too_low")
    if (
        targeted_snapshot
        and planned_target_sample_count is not None
        and min_target_sample_count > 0
        and planned_target_sample_count < min_target_sample_count
    ):
        reasons.append("target_sample_sufficiency_too_low")
    if (
        targeted_snapshot
        and _is_rl_bandit_momentum_candidate(payload, research_task)
        and coverage_ratio is not None
        and coverage_ratio <= _RL_BANDIT_ALIGNMENT_HARD_BLOCK_COVERAGE
        and (
            intersection_ratio is None
            or intersection_ratio <= _RL_BANDIT_ALIGNMENT_HARD_BLOCK_INTERSECTION
        )
        and "target_universe_alignment_too_low" not in reasons
    ):
        reasons.append("target_universe_alignment_too_low")
    if (
        targeted_snapshot
        and len(target_codes) >= 6
        and _is_pipeline_staged_rsi_candidate(payload, research_task)
        and intersection_ratio is not None
        and intersection_ratio <= _PIPELINE_RSI_ALIGNMENT_HARD_BLOCK_INTERSECTION
        and "target_universe_alignment_too_low" not in reasons
    ):
        reasons.append("target_universe_alignment_too_low")
    if (
        targeted_snapshot
        and len(target_codes) >= _RL_BANDIT_VOLATILITY_BREAKOUT_ALIGNMENT_MIN_TARGET_COUNT
        and _is_rl_bandit_volatility_breakout_candidate(payload, research_task)
        and intersection_ratio is not None
        and intersection_ratio <= _RL_BANDIT_VOLATILITY_BREAKOUT_ALIGNMENT_HARD_BLOCK_INTERSECTION
        and "target_universe_alignment_too_low" not in reasons
    ):
        reasons.append("target_universe_alignment_too_low")
    if seen_signatures is not None:
        if signature in seen_signatures:
            reasons.append("duplicate_candidate_signature")
        else:
            seen_signatures.add(signature)

    liquidity_requirement = _resolve_liquidity_requirement(payload, research_task, target_codes)
    liquidity = _estimate_liquidity_proxy(payload, research_task, target_codes)
    liquidity_threshold = _liquidity_threshold(liquidity_requirement, liquidity.get("proxy_kind"))
    liquidity_value = _safe_float(liquidity.get("proxy_value"), 0.0)
    if liquidity.get("available") and liquidity_threshold > 0 and 0 < liquidity_value < liquidity_threshold:
        reasons.append("liquidity_below_requirement")

    signal_density = _estimate_signal_density(strategy_type, dict(payload.get("params") or {}))
    if signal_density < _PRE_GATE_SIGNAL_DENSITY_MIN:
        reasons.append("signal_density_too_sparse")
    elif signal_density > _PRE_GATE_SIGNAL_DENSITY_MAX:
        reasons.append("signal_density_too_dense")

    if family_counts is not None and family_used_before >= max(1, int(family_quota_limit or 1)):
        reasons.append("family_quota_exceeded")

    per_stock_quota_hit = [
        code
        for code in target_codes
        if _safe_float((stock_counts or {}).get(code), 0.0) >= max(1, int(per_stock_quota_limit or 1))
    ]
    if per_stock_quota_hit:
        reasons.append("per_stock_quota_exceeded")

    if not reasons:
        if family_counts is not None:
            family_counts[candidate_family] = family_used_before + 1
        if stock_counts is not None:
            for code in target_codes:
                stock_counts[code] = round(
                    _safe_float(stock_counts.get(code), 0.0) + per_stock_quota_increment,
                    4,
                )

    return GateResult(
        passed=len(reasons) == 0,
        gate="pre_gate",
        reasons=reasons,
        metrics={
            "task_source": task_source or None,
            "target_symbol_count": len(target_codes),
            "target_symbols": target_codes,
            "allowed_strategy_types": sorted(allowed_strategy_types),
            "candidate_signature": signature,
            "candidate_family": candidate_family,
            "coverage_ratio": coverage_ratio,
            "intersection_ratio": intersection_ratio,
            "target_quality_summary": dict(target_quality_summary),
            "planned_target_sample_count": planned_target_sample_count,
            "resolved_target_sample_count": resolved_target_sample_count,
            "min_target_sample_count": min_target_sample_count,
            "family_quota_limit": max(1, int(family_quota_limit or 1)),
            "family_quota_used_before": family_used_before,
            "per_stock_quota_limit": max(1, int(per_stock_quota_limit or 1)),
            "per_stock_quota_used_before": stock_quota_snapshot,
            "per_stock_quota_increment": per_stock_quota_increment,
            "per_stock_quota_hit_symbols": per_stock_quota_hit,
            "liquidity_requirement": liquidity_requirement,
            "liquidity_proxy_available": bool(liquidity.get("available")),
            "liquidity_proxy_kind": liquidity.get("proxy_kind"),
            "liquidity_proxy_value": liquidity.get("proxy_value"),
            "liquidity_threshold": liquidity_threshold,
            "signal_density_estimate": signal_density,
            "signal_density_min": _PRE_GATE_SIGNAL_DENSITY_MIN,
            "signal_density_max": _PRE_GATE_SIGNAL_DENSITY_MAX,
        },
    )
