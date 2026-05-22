    metadata = dict(self.metadata or {})
    source_candidate = dict(metadata.get("source_candidate") or {})
    source_candidate_params = dict(source_candidate.get("params") or {})

    def _list_value(*values: Any) -> list[Any]:
        for value in values:
            if isinstance(value, (list, tuple, set)) and value:
                return list(value)
        return []

    def _dict_value(*values: Any) -> dict[str, Any]:
        for value in values:
            if isinstance(value, dict) and value:
                return dict(value)
        return {}

    def _scalar_value(*values: Any) -> Any:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return None

    target_symbols = _normalize_code_list(
        metadata.get("target_symbols"),
        source_candidate.get("target_symbols"),
        metadata.get("stock_pool"),
        source_candidate.get("stock_pool"),
        dict(self.params or {}).get("target_symbols"),
        source_candidate_params.get("target_symbols"),
        dict(self.params or {}).get("stock_pool"),
        source_candidate_params.get("stock_pool"),
    )
    stock_pool = _dict_value(
        metadata.get("stock_pool"),
        source_candidate.get("stock_pool"),
        dict(self.params or {}).get("stock_pool"),
        source_candidate_params.get("stock_pool"),
        {"selection_mode": "explicit", "symbols": list(target_symbols)} if target_symbols else {},
    )
    research_task = _safe_normalize_research_task(_dict_value(
        metadata.get("research_task"),
        source_candidate.get("research_task"),
        dict(self.params or {}).get("research_task"),
        source_candidate_params.get("research_task"),
    ))
    candidate_family = str(
        _scalar_value(
            metadata.get("candidate_family"),
            source_candidate.get("candidate_family"),
            dict(self.params or {}).get("candidate_family"),
            source_candidate_params.get("candidate_family"),
            research_task.get("candidate_family"),
        )
        or ""
    ).strip().lower() or None
    candidate_family_id = str(
        _scalar_value(
            metadata.get("candidate_family_id"),
            source_candidate.get("candidate_family_id"),
            dict(self.params or {}).get("candidate_family_id"),
            source_candidate_params.get("candidate_family_id"),
            research_task.get("candidate_family_id"),
        )
        or ""
    ).strip() or None
    event_context = _dict_value(
        metadata.get("event_context"),
        source_candidate.get("event_context"),
        dict(self.params or {}).get("event_context"),
        source_candidate_params.get("event_context"),
    )
    selection_logic = _list_value(
        metadata.get("selection_logic"),
        source_candidate.get("selection_logic"),
    )
    research_scope = _dict_value(
        metadata.get("research_scope"),
        source_candidate.get("research_scope"),
    )
    hypothesis_artifact = _dict_value(
        metadata.get("hypothesis_artifact"),
        source_candidate.get("hypothesis_artifact"),
    )
    event_prefilter = _dict_value(
        metadata.get("event_prefilter"),
        source_candidate.get("event_prefilter"),
        dict(self.params or {}).get("event_prefilter"),
        source_candidate_params.get("event_prefilter"),
        hypothesis_artifact.get("event_prefilter"),
    )
    event_anchor = _dict_value(
        metadata.get("event_anchor"),
        source_candidate.get("event_anchor"),
        dict(self.params or {}).get("event_anchor"),
        source_candidate_params.get("event_anchor"),
        event_prefilter.get("event_anchor"),
        hypothesis_artifact.get("event_anchor"),
    )
    candidate_origin = _scalar_value(
        metadata.get("candidate_origin"),
        source_candidate.get("candidate_origin"),
        dict(self.params or {}).get("candidate_origin"),
        source_candidate_params.get("candidate_origin"),
    ) or "research_signal"
    target_pool_source = _scalar_value(
        metadata.get("target_pool_source"),
        source_candidate.get("target_pool_source"),
        dict(self.params or {}).get("target_pool_source"),
        source_candidate_params.get("target_pool_source"),
    ) or ("event_anchor" if event_anchor else "explicit_task")
    source_symbol_summary = _dict_value(
        metadata.get("source_symbol_summary"),
        source_candidate.get("source_symbol_summary"),
        research_task.get("source_symbol_summary"),
    )
    backtest_metrics = _dict_value(
        metadata.get("backtest_metrics"),
        source_candidate.get("backtest_metrics"),
        dict(self.params or {}).get("backtest_metrics"),
        source_candidate_params.get("backtest_metrics"),
    )
    task_source = _task_source(research_task, event_context)
    prediction_trace_id = normalize_prediction_trace_id(
        _scalar_value(
            metadata.get("prediction_trace_id"),
            source_candidate.get("prediction_trace_id"),
            dict(self.params or {}).get("prediction_trace_id"),
            source_candidate_params.get("prediction_trace_id"),
        ),
        _scalar_value(
            metadata.get("trace_id"),
            source_candidate.get("trace_id"),
            dict(self.params or {}).get("trace_id"),
            source_candidate_params.get("trace_id"),
        ),
        fallback=f"pred_{uuid4().hex[:12]}",
    )
    explicit_research_validation_contract = _dict_value(
        metadata.get("research_validation_contract"),
        source_candidate.get("research_validation_contract"),
        dict(self.params or {}).get("research_validation_contract"),
        source_candidate_params.get("research_validation_contract"),
    )
    research_validation_contract_source = _resolve_source_label(
        ("metadata", metadata.get("research_validation_contract")),
        ("source_candidate", source_candidate.get("research_validation_contract")),
        ("params", dict(self.params or {}).get("research_validation_contract")),
        ("source_candidate_params", source_candidate_params.get("research_validation_contract")),
    )
    holding_rationale = _scalar_value(
        metadata.get("holding_rationale"),
        source_candidate.get("holding_rationale"),
        hypothesis_artifact.get("holding_rationale"),
    )
    failure_mode = _scalar_value(
        metadata.get("failure_mode"),
        source_candidate.get("failure_mode"),
        hypothesis_artifact.get("failure_mode"),
    )
    alpha_half_life = _scalar_value(
        metadata.get("alpha_half_life"),
        source_candidate.get("alpha_half_life"),
        hypothesis_artifact.get("alpha_half_life"),
    )
    market_regime_assumption = _scalar_value(
        metadata.get("market_regime_assumption"),
        source_candidate.get("market_regime_assumption"),
        hypothesis_artifact.get("market_regime_assumption"),
    )
    evidence_chain = _dict_value(
        metadata.get("evidence_chain"),
        source_candidate.get("evidence_chain"),
        dict(self.params or {}).get("evidence_chain"),
        source_candidate_params.get("evidence_chain"),
    )
    prediction_contract = _dict_value(
        metadata.get("prediction_contract"),
        source_candidate.get("prediction_contract"),
        dict(self.params or {}).get("prediction_contract"),
        source_candidate_params.get("prediction_contract"),
    )
    confidence_contract = _dict_value(
        metadata.get("confidence_contract"),
        source_candidate.get("confidence_contract"),
        dict(self.params or {}).get("confidence_contract"),
        source_candidate_params.get("confidence_contract"),
    )
    evidence_alignment_audit = _dict_value(
        metadata.get("evidence_alignment_audit"),
        source_candidate.get("evidence_alignment_audit"),
        dict(self.params or {}).get("evidence_alignment_audit"),
        source_candidate_params.get("evidence_alignment_audit"),
    )
    market_facts = normalize_market_evidence_facts(
        metadata.get("market_facts"),
        source_candidate.get("market_facts"),
        dict(self.params or {}).get("market_facts"),
        source_candidate_params.get("market_facts"),
        evidence_chain.get("market_facts") if isinstance(evidence_chain, dict) else None,
    )
    if market_facts:
        evidence_chain = dict(evidence_chain or {})
        evidence_chain["market_facts"] = list(market_facts)
        evidence_alignment_audit = {
            **dict(evidence_alignment_audit or {}),
            **_build_market_fact_gate_audit(market_facts),
        }
    dsl_support_audit = _dict_value(
        metadata.get("dsl_support_audit"),
        source_candidate.get("dsl_support_audit"),
        dict(self.params or {}).get("dsl_support_audit"),
        source_candidate_params.get("dsl_support_audit"),
    )
    claim_to_trade_plan_map = _dict_value(
        metadata.get("claim_to_trade_plan_map"),
        source_candidate.get("claim_to_trade_plan_map"),
        dict(self.params or {}).get("claim_to_trade_plan_map"),
        source_candidate_params.get("claim_to_trade_plan_map"),
    )
    trade_plan_to_dsl_map = _dict_value(
        metadata.get("trade_plan_to_dsl_map"),
        source_candidate.get("trade_plan_to_dsl_map"),
        dict(self.params or {}).get("trade_plan_to_dsl_map"),
        source_candidate_params.get("trade_plan_to_dsl_map"),
    )
    explicit_dsl = _dict_value(
        metadata.get("dsl"),
        source_candidate.get("dsl"),
        dict(self.params or {}).get("dsl"),
        source_candidate_params.get("dsl"),
    )
    holding_horizon_source = _resolve_source_label(
        ("metadata", metadata.get("holding_horizon")),
        ("source_candidate", source_candidate.get("holding_horizon")),
        ("params", dict(self.params or {}).get("holding_horizon")),
        ("source_candidate_params", source_candidate_params.get("holding_horizon")),
    )
    holding_horizon = _dict_value(
        metadata.get("holding_horizon"),
        source_candidate.get("holding_horizon"),
        dict(self.params or {}).get("holding_horizon"),
        source_candidate_params.get("holding_horizon"),
    )
    if not holding_horizon:
        holding_horizon = _default_holding_horizon(
            self.strategy_type,
            research_task,
            task_source,
            alpha_half_life=alpha_half_life,
        )
    if alpha_half_life in (None, "", [], {}):
        alpha_half_life = holding_horizon.get("alpha_half_life") or holding_horizon.get("max_days")
    if market_regime_assumption in (None, "", [], {}):
        market_regime_assumption = _default_market_regime_assumption(
            self.strategy_type,
            task_source,
        )
    if holding_rationale not in (None, "", [], {}) and hypothesis_artifact.get("holding_rationale") in (None, "", [], {}):
        hypothesis_artifact["holding_rationale"] = holding_rationale
    if failure_mode not in (None, "", [], {}) and hypothesis_artifact.get("failure_mode") in (None, "", [], {}):
        hypothesis_artifact["failure_mode"] = failure_mode
    if market_regime_assumption not in (None, "", [], {}) and hypothesis_artifact.get("market_regime_assumption") in (None, "", [], {}):
        hypothesis_artifact["market_regime_assumption"] = market_regime_assumption
    if event_prefilter and hypothesis_artifact.get("event_prefilter") in (None, "", [], {}):
        hypothesis_artifact["event_prefilter"] = dict(event_prefilter)
    holding_horizon = _merge_holding_semantics(
        holding_horizon,
        holding_rationale=holding_rationale,
        alpha_half_life=alpha_half_life,
    )
    trade_plan_source = _resolve_source_label(
        ("metadata", metadata.get("trade_plan")),
        ("source_candidate", source_candidate.get("trade_plan")),
        ("params", dict(self.params or {}).get("trade_plan")),
        ("source_candidate_params", source_candidate_params.get("trade_plan")),
    )
    trade_plan = _dict_value(
        metadata.get("trade_plan"),
        source_candidate.get("trade_plan"),
        dict(self.params or {}).get("trade_plan"),
        source_candidate_params.get("trade_plan"),
    )
    if not trade_plan:
        trade_plan = _default_trade_plan(self.strategy_type, task_source)
    trade_plan = _ensure_trade_plan_execution_nodes(self.strategy_type, trade_plan)
    risk_rules_source = _resolve_source_label(
        ("metadata", metadata.get("risk_rules")),
        ("source_candidate", source_candidate.get("risk_rules")),
        ("params", dict(self.params or {}).get("risk_rules")),
        ("source_candidate_params", source_candidate_params.get("risk_rules")),
    )
    risk_rules = _dict_value(
        metadata.get("risk_rules"),
        source_candidate.get("risk_rules"),
        dict(self.params or {}).get("risk_rules"),
        source_candidate_params.get("risk_rules"),
    )
    if not risk_rules:
        risk_rules = _default_risk_rules(task_source, holding_horizon)
    position_sizing = _dict_value(
        metadata.get("position_sizing"),
        source_candidate.get("position_sizing"),
        dict(self.params or {}).get("position_sizing"),
        source_candidate_params.get("position_sizing"),
    )
    if not position_sizing:
        position_sizing = _default_position_sizing(target_symbols)
    rebalance_rule = _dict_value(
        metadata.get("rebalance_rule"),
        source_candidate.get("rebalance_rule"),
        dict(self.params or {}).get("rebalance_rule"),
        source_candidate_params.get("rebalance_rule"),
    )
    if not rebalance_rule:
        rebalance_rule = _default_rebalance_rule(
            self.strategy_type,
            task_source,
            holding_horizon=holding_horizon,
            alpha_half_life=alpha_half_life,
        )
    rebalance_rule = _merge_rebalance_semantics(
        rebalance_rule,
        task_source=task_source,
        holding_horizon=holding_horizon,
        alpha_half_life=alpha_half_life,
    )
    portfolio_spec = _dict_value(
        metadata.get("portfolio_spec"),
        source_candidate.get("portfolio_spec"),
        dict(self.params or {}).get("portfolio_spec"),
        source_candidate_params.get("portfolio_spec"),
    )
    if not portfolio_spec:
        portfolio_spec = _default_portfolio_spec(target_symbols)
    execution_assumptions_source = _resolve_source_label(
        ("metadata", metadata.get("execution_assumptions")),
        ("source_candidate", source_candidate.get("execution_assumptions")),
        ("params", dict(self.params or {}).get("execution_assumptions")),
        ("source_candidate_params", source_candidate_params.get("execution_assumptions")),
    )
