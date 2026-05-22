    execution_assumptions = _dict_value(
        metadata.get("execution_assumptions"),
        source_candidate.get("execution_assumptions"),
        dict(self.params or {}).get("execution_assumptions"),
        source_candidate_params.get("execution_assumptions"),
    )
    if not execution_assumptions:
        execution_assumptions = _default_execution_assumptions(task_source)
    runtime_playbook_source = _resolve_source_label(
        ("metadata", metadata.get("runtime_playbook")),
        ("source_candidate", source_candidate.get("runtime_playbook")),
        ("params", dict(self.params or {}).get("runtime_playbook")),
        ("source_candidate_params", source_candidate_params.get("runtime_playbook")),
    )
    runtime_playbook = _dict_value(
        metadata.get("runtime_playbook"),
        source_candidate.get("runtime_playbook"),
        dict(self.params or {}).get("runtime_playbook"),
        source_candidate_params.get("runtime_playbook"),
    )
    validation_profile = _dict_value(
        metadata.get("validation_profile"),
        source_candidate.get("validation_profile"),
        dict(self.params or {}).get("validation_profile"),
        source_candidate_params.get("validation_profile"),
    )
    default_validation_profile = _default_validation_profile(self.strategy_type, research_task, task_source)
    if not validation_profile:
        validation_profile = dict(default_validation_profile)
    else:
        validation_profile = {
            **dict(default_validation_profile),
            **dict(validation_profile),
        }
    if not event_prefilter:
        event_prefilter = _default_event_prefilter(self.strategy_type, validation_profile)
    targeting_policy = _dict_value(
        metadata.get("targeting_policy"),
        source_candidate.get("targeting_policy"),
        dict(self.params or {}).get("targeting_policy"),
        source_candidate_params.get("targeting_policy"),
    )
    if not targeting_policy:
        targeting_policy = _default_targeting_policy(research_task)
    constraint_check = _dict_value(
        metadata.get("constraint_check"),
        source_candidate.get("constraint_check"),
        dict(self.params or {}).get("constraint_check"),
        source_candidate_params.get("constraint_check"),
    )
    if not constraint_check:
        constraint_check = _default_constraint_check(
            target_symbols=list(target_symbols),
            research_task=research_task,
            targeting_policy=targeting_policy,
        )
    position_model = _scalar_value(
        metadata.get("position_model"),
        source_candidate.get("position_model"),
        hypothesis_artifact.get("position_model"),
        position_sizing.get("mode"),
        portfolio_spec.get("position_assumption"),
    )
    capacity_assumption = _dict_value(
        metadata.get("capacity_assumption"),
        source_candidate.get("capacity_assumption"),
        hypothesis_artifact.get("capacity_assumption"),
    )
    capacity_assumption_source = _resolve_source_label(
        ("metadata", metadata.get("capacity_assumption")),
        ("source_candidate", source_candidate.get("capacity_assumption")),
        ("hypothesis_artifact", hypothesis_artifact.get("capacity_assumption")),
    )
    cost_sensitivity_grid = _dict_value(
        metadata.get("cost_sensitivity_grid"),
        source_candidate.get("cost_sensitivity_grid"),
        hypothesis_artifact.get("cost_sensitivity_grid"),
    )
    cost_sensitivity_grid_source = _resolve_source_label(
        ("metadata", metadata.get("cost_sensitivity_grid")),
        ("source_candidate", source_candidate.get("cost_sensitivity_grid")),
        ("hypothesis_artifact", hypothesis_artifact.get("cost_sensitivity_grid")),
    )
    instrument_profile = _normalize_instrument_profile(
        _dict_value(
            metadata.get("instrument_profile"),
            source_candidate.get("instrument_profile"),
            dict(self.params or {}).get("instrument_profile"),
            source_candidate_params.get("instrument_profile"),
            research_task.get("instrument_profile"),
        ),
        target_symbols=list(target_symbols),
        source_symbol_summary=source_symbol_summary,
    )
    execution_semantic_contract = _resolve_execution_semantic_contract(
        strategy_type=self.strategy_type,
        params={**dict(self.params or {}), "target_symbols": list(target_symbols)},
        target_symbols=list(target_symbols),
        trade_plan=trade_plan,
        holding_horizon=holding_horizon,
        risk_rules=risk_rules,
        position_sizing=position_sizing,
        stock_pool=stock_pool,
        prediction_contract=prediction_contract,
        instrument_profile=instrument_profile,
        explicit_dsl=explicit_dsl,
        existing_claim_to_trade_plan_map=claim_to_trade_plan_map,
        existing_trade_plan_to_dsl_map=trade_plan_to_dsl_map,
        existing_dsl_support_audit=dsl_support_audit,
    )
    if execution_semantic_contract.get("dsl_support_audit"):
        dsl_support_audit = dict(execution_semantic_contract.get("dsl_support_audit") or {})
    if execution_semantic_contract.get("claim_to_trade_plan_map"):
        claim_to_trade_plan_map = dict(execution_semantic_contract.get("claim_to_trade_plan_map") or {})
    if execution_semantic_contract.get("trade_plan_to_dsl_map"):
        trade_plan_to_dsl_map = dict(execution_semantic_contract.get("trade_plan_to_dsl_map") or {})
    family_specialization = _default_family_specialization(
        self.strategy_type,
        task_source,
        holding_horizon=holding_horizon,
        rebalance_rule=rebalance_rule,
    )
    family_specialization.update(
        _dict_value(
            metadata.get("family_specialization"),
            source_candidate.get("family_specialization"),
            dict(self.params or {}).get("family_specialization"),
            source_candidate_params.get("family_specialization"),
            hypothesis_artifact.get("family_specific_hypothesis"),
        )
    )
    expected_turnover_band = (
        _normalize_turnover_band(
            holding_horizon.get("expected_turnover_band")
            or rebalance_rule.get("expected_turnover_band")
        )
        or _derive_half_life_semantics(alpha_half_life).get("expected_turnover_band")
    )
    capacity_bucket = _resolve_capacity_bucket(
        dict(capacity_assumption),
        target_symbols=list(target_symbols),
        position_model=str(position_model or ""),
    )
    if not capacity_assumption:
        capacity_assumption = {
            "max_position_pct": portfolio_spec.get("max_position_pct"),
            "symbol_count": len(target_symbols),
            "capacity_bucket": capacity_bucket,
        }
    if capacity_assumption and hypothesis_artifact.get("capacity_assumption") in (None, "", [], {}):
        hypothesis_artifact["capacity_assumption"] = dict(capacity_assumption)
    if not cost_sensitivity_grid:
        cost_sensitivity_grid = {
            "base_case": {
                "commission_rate": execution_assumptions.get("commission_rate"),
                "slippage_bps": execution_assumptions.get("slippage_bps"),
                "tradability_filter": execution_assumptions.get("tradability_filter"),
                "slippage_model": execution_assumptions.get("slippage_model"),
                "market_impact_bps": execution_assumptions.get("market_impact_bps"),
            },
            "source": "strategy_spec_execution_defaults",
        }
    if cost_sensitivity_grid and hypothesis_artifact.get("cost_sensitivity_grid") in (None, "", [], {}):
        hypothesis_artifact["cost_sensitivity_grid"] = dict(cost_sensitivity_grid)
    position_sizing_rationale = _resolve_position_sizing_rationale(
        position_model=str(position_model or ""),
        target_symbols=list(target_symbols),
        capacity_bucket=capacity_bucket,
        expected_turnover_band=expected_turnover_band or "medium",
    )
    position_sizing.setdefault("capacity_bucket", capacity_bucket or None)
    position_sizing.setdefault("expected_turnover_band", expected_turnover_band or None)
    position_sizing.setdefault("position_sizing_rationale", position_sizing_rationale)
    portfolio_spec.setdefault("capacity_bucket", capacity_bucket or None)
    portfolio_spec.setdefault("expected_turnover_band", expected_turnover_band or None)
    portfolio_spec.setdefault("position_sizing_rationale", position_sizing_rationale)
    execution_assumptions.setdefault("capacity_bucket", capacity_bucket or None)
    execution_assumptions.setdefault(
        "turnover_cost_class",
        _resolve_turnover_cost_class(
            execution_assumptions=execution_assumptions,
            expected_turnover_band=expected_turnover_band or "medium",
            capacity_bucket=capacity_bucket,
        ),
    )
    execution_assumptions.setdefault("expected_turnover_band", expected_turnover_band or None)
    trade_plan.setdefault("cooldown_window_days", holding_horizon.get("cooldown_window_days"))
    trade_plan.setdefault("expected_turnover_band", expected_turnover_band or None)
    risk_rules.setdefault("cooldown_window_days", holding_horizon.get("cooldown_window_days"))
    if not runtime_playbook:
        runtime_playbook = _default_runtime_playbook(
            self.strategy_type,
            holding_horizon=holding_horizon,
            trade_plan=trade_plan,
            risk_rules=risk_rules,
            portfolio_spec=portfolio_spec,
            execution_assumptions=execution_assumptions,
            instrument_profile=instrument_profile,
            backtest_metrics=backtest_metrics,
        )
    runtime_playbook = _enrich_runtime_playbook_provenance(
        runtime_playbook,
        strategy_type=self.strategy_type,
        prediction_contract=prediction_contract,
        trade_plan=trade_plan,
        claim_to_trade_plan_map=claim_to_trade_plan_map,
        trade_plan_to_dsl_map=trade_plan_to_dsl_map,
        source_priority={
            "holding_horizon": holding_horizon_source,
            "trade_plan": trade_plan_source,
            "risk_rules": risk_rules_source,
            "execution_assumptions": execution_assumptions_source,
            "runtime_playbook": runtime_playbook_source,
        },
        runtime_playbook_source=runtime_playbook_source,
    )
    regime_filter_contract = _dict_value(
        metadata.get("regime_filter_contract"),
        source_candidate.get("regime_filter_contract"),
        dict(self.params or {}).get("regime_filter_contract"),
        source_candidate_params.get("regime_filter_contract"),
    )
    if not regime_filter_contract:
        regime_filter_contract = _build_regime_filter_contract(
            self.strategy_type,
            market_regime_assumption=market_regime_assumption,
            instrument_profile=instrument_profile,
            runtime_playbook=runtime_playbook,
        )
    drawdown_invalidation_contract = _dict_value(
        metadata.get("drawdown_invalidation_contract"),
        source_candidate.get("drawdown_invalidation_contract"),
        dict(self.params or {}).get("drawdown_invalidation_contract"),
        source_candidate_params.get("drawdown_invalidation_contract"),
    )
    if not drawdown_invalidation_contract:
        drawdown_invalidation_contract = _build_drawdown_invalidation_contract(
            self.strategy_type,
            instrument_profile=instrument_profile,
            runtime_playbook=runtime_playbook,
            target_symbols=list(target_symbols),
        )
    thesis_invalidation_contract = _dict_value(
        metadata.get("thesis_invalidation_contract"),
        source_candidate.get("thesis_invalidation_contract"),
        dict(self.params or {}).get("thesis_invalidation_contract"),
        source_candidate_params.get("thesis_invalidation_contract"),
    )
    if not thesis_invalidation_contract:
        thesis_invalidation_contract = _build_thesis_invalidation_contract(
            self.strategy_type,
            trade_plan=trade_plan,
            runtime_playbook=runtime_playbook,
            instrument_profile=instrument_profile,
            drawdown_invalidation_contract=drawdown_invalidation_contract,
        )
    parameter_coherence_audit = _dict_value(
        metadata.get("parameter_coherence_audit"),
        source_candidate.get("parameter_coherence_audit"),
        dict(self.params or {}).get("parameter_coherence_audit"),
        source_candidate_params.get("parameter_coherence_audit"),
    )
    if not parameter_coherence_audit:
        parameter_coherence_audit = _build_parameter_coherence_audit(
            self.strategy_type,
            holding_horizon=holding_horizon,
            rebalance_rule=rebalance_rule,
            runtime_playbook=runtime_playbook,
            instrument_profile=instrument_profile,
            backtest_metrics=backtest_metrics,
        )
    runtime_semantic_diagnostics = _resolve_runtime_semantic_diagnostics(
        strategy_type=self.strategy_type,
        params={**dict(self.params or {}), "runtime_playbook": runtime_playbook},
        target_symbols=list(target_symbols),
        instrument_profile=instrument_profile,
        runtime_playbook=runtime_playbook,
        evidence_chain=evidence_chain,
        prediction_contract=prediction_contract,
        confidence_contract=confidence_contract,
        execution_semantic_contract=execution_semantic_contract,
    )
    execution_semantic_gap_reasons = list(
        dict.fromkeys(
            [
                *list(execution_semantic_contract.get("execution_semantic_gap_reasons") or []),
                *list(runtime_semantic_diagnostics.get("execution_semantic_gap_reasons") or []),
            ]
        )
    )
    holding_bucket = _classify_holding_bucket(holding_horizon)
    default_research_validation_contract = _default_research_validation_contract_payload(
        strategy_type=self.strategy_type,
        target_symbols=list(target_symbols),
        research_task=research_task,
        validation_profile=validation_profile,
        candidate_family=candidate_family,
        holding_bucket=holding_bucket,
    )
    default_research_sections = {
        field_name: dict(default_research_validation_contract.get(field_name) or {})
        for field_name in (
            "walk_forward_config",
            "baseline_reference",
            "cash_sleeve_policy",
            "cost_sensitivity_grid",
            "capacity_execution",
            "multiple_testing",
            "admission_thresholds",
            "family_holding_bucket",
        )
    }
    derived_capacity_execution_contract = {
        **dict(capacity_assumption or {}),
        "capacity_bucket": capacity_bucket,
        "position_model": position_model,
        "max_position_pct": portfolio_spec.get("max_position_pct"),
        "market_impact_bps": execution_assumptions.get("market_impact_bps"),
        "slippage_bps": execution_assumptions.get("slippage_bps"),
        "commission_rate": execution_assumptions.get("commission_rate"),
        "tradability_filter": execution_assumptions.get("tradability_filter"),
    }
    capacity_execution_contract = _merge_contract_payloads(
        default_research_sections.get("capacity_execution"),
        derived_capacity_execution_contract,
        dict(explicit_research_validation_contract.get("capacity_execution") or {}),
    )
    derived_family_holding_bucket_contract = {
        "family": candidate_family
        or family_specialization.get("family")
        or family_specialization.get("family_id")
        or self.strategy_type,
        "holding_bucket": holding_bucket,
        "expected_turnover_band": expected_turnover_band,
    }
    family_holding_bucket_contract = _merge_contract_payloads(
        default_research_sections.get("family_holding_bucket"),
        dict(explicit_research_validation_contract.get("family_holding_bucket") or {}),
        derived_family_holding_bucket_contract,
    )
    derived_admission_thresholds = _merge_contract_payloads(
        dict(explicit_research_validation_contract.get("admission_thresholds") or {}),
        {"validation_profile": dict(validation_profile or {})},
    )
