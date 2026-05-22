    effective_research_sections = {
        "walk_forward_config": _merge_contract_payloads(
            default_research_sections.get("walk_forward_config"),
            dict(explicit_research_validation_contract.get("walk_forward_config") or {}),
        ),
        "baseline_reference": _merge_contract_payloads(
            default_research_sections.get("baseline_reference"),
            dict(explicit_research_validation_contract.get("baseline_reference") or {}),
        ),
        "cash_sleeve_policy": _merge_contract_payloads(
            default_research_sections.get("cash_sleeve_policy"),
            dict(explicit_research_validation_contract.get("cash_sleeve_policy") or {}),
        ),
        "cost_sensitivity_grid": _merge_contract_payloads(
            default_research_sections.get("cost_sensitivity_grid"),
            dict(cost_sensitivity_grid or {}),
            dict(explicit_research_validation_contract.get("cost_sensitivity_grid") or {}),
        ),
        "capacity_execution": dict(capacity_execution_contract or {}),
        "multiple_testing": _merge_contract_payloads(
            default_research_sections.get("multiple_testing"),
            dict(explicit_research_validation_contract.get("multiple_testing") or {}),
        ),
        "admission_thresholds": _merge_contract_payloads(
            default_research_sections.get("admission_thresholds"),
            derived_admission_thresholds,
        ),
        "family_holding_bucket": dict(family_holding_bucket_contract or {}),
    }
    research_field_provenance = {
        "walk_forward_config": normalize_field_provenance_token(
            research_validation_contract_source
            if effective_research_sections["walk_forward_config"]
            and explicit_research_validation_contract.get("walk_forward_config")
            else "derived"
            if effective_research_sections["walk_forward_config"]
            else "missing"
        ),
        "baseline_reference": normalize_field_provenance_token(
            research_validation_contract_source
            if effective_research_sections["baseline_reference"]
            and explicit_research_validation_contract.get("baseline_reference")
            else "derived"
            if effective_research_sections["baseline_reference"]
            else "missing"
        ),
        "cash_sleeve_policy": normalize_field_provenance_token(
            research_validation_contract_source
            if effective_research_sections["cash_sleeve_policy"]
            and explicit_research_validation_contract.get("cash_sleeve_policy")
            else "derived"
            if effective_research_sections["cash_sleeve_policy"]
            else "missing"
        ),
        "cost_sensitivity_grid": normalize_field_provenance_token(
            research_validation_contract_source
            if explicit_research_validation_contract.get("cost_sensitivity_grid")
            else _resolve_nonmissing_field_provenance(cost_sensitivity_grid_source)
            if dict(cost_sensitivity_grid or {})
            else "derived"
            if effective_research_sections["cost_sensitivity_grid"]
            else "missing"
        ),
        "capacity_execution": normalize_field_provenance_token(
            research_validation_contract_source
            if explicit_research_validation_contract.get("capacity_execution")
            else _resolve_nonmissing_field_provenance(capacity_assumption_source)
            if dict(capacity_assumption or {})
            else "derived"
            if effective_research_sections["capacity_execution"]
            else "missing"
        ),
        "multiple_testing": normalize_field_provenance_token(
            research_validation_contract_source
            if effective_research_sections["multiple_testing"]
            and explicit_research_validation_contract.get("multiple_testing")
            else "derived"
            if effective_research_sections["multiple_testing"]
            else "missing"
        ),
        "admission_thresholds": normalize_field_provenance_token(
            research_validation_contract_source
            if explicit_research_validation_contract.get("admission_thresholds")
            else "derived"
            if effective_research_sections["admission_thresholds"]
            else "missing"
        ),
        "family_holding_bucket": normalize_field_provenance_token(
            research_validation_contract_source
            if explicit_research_validation_contract.get("family_holding_bucket")
            else "derived"
            if effective_research_sections["family_holding_bucket"]
            else "missing"
        ),
    }
    recommended_defaults = {
        field_name: dict(default_research_validation_contract.get(field_name) or {})
        for field_name in effective_research_sections
        if not effective_research_sections.get(field_name)
        and dict(default_research_validation_contract.get(field_name) or {})
    }
    research_contract_hard_failures: list[dict[str, Any]] = []
    for field_name in list(runtime_semantic_diagnostics.get("semantic_contract_missing_fields") or []):
        token = str(field_name or "").strip()
        if token:
            research_contract_hard_failures.append(
                {
                    "field": token,
                    "issue": "semantic_contract_missing_field",
                    "reason_code": f"semantic_contract_missing:{token}",
                    "detail": "runtime semantic contract is not executable without this field",
                }
            )
    for reason_code in execution_semantic_gap_reasons:
        token = str(reason_code or "").strip()
        if token:
            research_contract_hard_failures.append(
                {
                    "issue": "execution_semantic_gap",
                    "reason_code": token,
                }
            )
    research_validation_contract = build_research_validation_contract(
        walk_forward_config=effective_research_sections.get("walk_forward_config"),
        baseline_reference=effective_research_sections.get("baseline_reference"),
        cash_sleeve_policy=effective_research_sections.get("cash_sleeve_policy"),
        cost_sensitivity_grid=effective_research_sections.get("cost_sensitivity_grid"),
        capacity_execution=effective_research_sections.get("capacity_execution"),
        multiple_testing=effective_research_sections.get("multiple_testing"),
        admission_thresholds=effective_research_sections.get("admission_thresholds"),
        family_holding_bucket=effective_research_sections.get("family_holding_bucket"),
        field_provenance=research_field_provenance,
        recommended_defaults=recommended_defaults,
        hard_failures=research_contract_hard_failures,
    )
    research_protocol_version = str(
        research_validation_contract.get("contract_version")
        or default_research_validation_contract.get("contract_version")
        or "strategy_factory.research_protocol.v2"
    ).strip() or "strategy_factory.research_protocol.v2"
    candidate_contract_version = CANDIDATE_CONTRACT_V2
    field_provenance = dict(research_validation_contract.get("field_provenance") or {})
    field_provenance_summary = dict(research_validation_contract.get("field_provenance_summary") or {})
    spec_completeness = str(research_validation_contract.get("spec_completeness") or "complete").strip() or "complete"
    completion_issues = list(research_validation_contract.get("completion_issues") or [])
    research_hard_failures = list(research_validation_contract.get("hard_failures") or [])
    candidate_params = {
        **dict(self.params or {}),
        "target_symbols": list(target_symbols),
        "stock_pool": dict(stock_pool),
        "research_task": dict(research_task),
        "event_context": dict(event_context),
        "holding_horizon": dict(holding_horizon),
        "trade_plan": dict(trade_plan),
        "risk_rules": dict(risk_rules),
        "position_sizing": dict(position_sizing),
        "rebalance_rule": dict(rebalance_rule),
        "portfolio_spec": dict(portfolio_spec),
        "execution_assumptions": dict(execution_assumptions),
        "runtime_playbook": dict(runtime_playbook),
        "validation_profile": dict(validation_profile),
        "event_prefilter": dict(event_prefilter),
        "targeting_policy": dict(targeting_policy),
        "constraint_check": dict(constraint_check),
        "hypothesis_artifact": dict(hypothesis_artifact),
        "holding_rationale": holding_rationale,
        "alpha_half_life": alpha_half_life,
        "cost_sensitivity_grid": dict(cost_sensitivity_grid),
        "position_model": position_model,
        "capacity_assumption": dict(capacity_assumption),
        "market_regime_assumption": market_regime_assumption,
        "instrument_profile": dict(instrument_profile),
        "regime_filter_contract": dict(regime_filter_contract),
        "parameter_coherence_audit": dict(parameter_coherence_audit),
        "thesis_invalidation_contract": dict(thesis_invalidation_contract),
        "drawdown_invalidation_contract": dict(drawdown_invalidation_contract),
        "position_sizing_rationale": position_sizing_rationale,
        "capacity_bucket": capacity_bucket,
        "turnover_cost_class": execution_assumptions.get("turnover_cost_class"),
        "expected_turnover_band": expected_turnover_band,
        "family_specialization": dict(family_specialization),
        "execution_semantic_mode": execution_semantic_contract.get("execution_semantic_mode"),
        "execution_semantic_gap": bool(execution_semantic_contract.get("execution_semantic_gap") or execution_semantic_gap_reasons),
        "execution_semantic_gap_reasons": execution_semantic_gap_reasons,
        "dsl_required": bool(execution_semantic_contract.get("dsl_required")),
        "dsl_compiled": bool(execution_semantic_contract.get("dsl_compiled")),
        "dsl_compile_failure_reasons": list(execution_semantic_contract.get("dsl_compile_failure_reasons") or []),
        "semantic_runtime_match": bool(runtime_semantic_diagnostics.get("semantic_runtime_match")),
        "runtime_family_data_source": runtime_semantic_diagnostics.get("runtime_family_data_source"),
        "proxy_runtime_used": bool(runtime_semantic_diagnostics.get("proxy_runtime_used")),
        "diagnostic_only": bool(runtime_semantic_diagnostics.get("diagnostic_only")),
        "execution_readiness_tier": runtime_semantic_diagnostics.get("execution_readiness_tier"),
        "semantic_contract_missing_fields": list(runtime_semantic_diagnostics.get("semantic_contract_missing_fields") or []),
        "economic_semantics_score": _scalar_value(
            metadata.get("economic_semantics_score"),
            source_candidate.get("economic_semantics_score"),
            hypothesis_artifact.get("economic_semantics_score"),
        ),
        "economic_semantics_missing_fields": _list_value(
            metadata.get("economic_semantics_missing_fields"),
            source_candidate.get("economic_semantics_missing_fields"),
            hypothesis_artifact.get("economic_semantics_missing_fields"),
        ),
        "validation_focus": _scalar_value(
            metadata.get("validation_focus"),
            source_candidate.get("validation_focus"),
            hypothesis_artifact.get("validation_focus"),
            validation_profile.get("validation_focus"),
        ),
        "candidate_family": candidate_family,
        "candidate_family_id": candidate_family_id,
        "candidate_origin": candidate_origin,
        "event_anchor": dict(event_anchor),
        "target_pool_source": target_pool_source,
        "prediction_trace_id": prediction_trace_id,
        "trace_id": prediction_trace_id,
        "research_validation_contract": dict(research_validation_contract),
        "research_protocol_version": research_protocol_version,
        "candidate_contract_version": candidate_contract_version,
        "field_provenance": dict(field_provenance),
        "field_provenance_summary": dict(field_provenance_summary),
        "spec_completeness": spec_completeness,
        "completion_issues": list(completion_issues),
        "hard_failures": list(research_hard_failures),
    }
    if market_facts:
        candidate_params["market_facts"] = list(market_facts)
    if backtest_metrics:
        candidate_params["backtest_metrics"] = dict(backtest_metrics)
    if source_symbol_summary:
        candidate_params["source_symbol_summary"] = dict(source_symbol_summary)
    if execution_semantic_contract.get("dsl"):
        candidate_params["dsl"] = dict(execution_semantic_contract.get("dsl") or {})
    for field_name, field_value in (
        ("evidence_chain", evidence_chain),
        ("prediction_contract", prediction_contract),
        ("confidence_contract", confidence_contract),
        ("evidence_alignment_audit", evidence_alignment_audit),
        ("dsl_support_audit", dsl_support_audit),
        ("claim_to_trade_plan_map", claim_to_trade_plan_map),
        ("trade_plan_to_dsl_map", trade_plan_to_dsl_map),
    ):
        if field_value:
            candidate_params[field_name] = dict(field_value)
    for field_name in ("legacy_semantic_contract", "contradiction_count", "proxy_dependency_score"):
        field_value = _scalar_value(
            metadata.get(field_name),
            source_candidate.get(field_name),
            dict(self.params or {}).get(field_name),
            source_candidate_params.get(field_name),
        )
        if field_value not in (None, "", [], {}):
            candidate_params[field_name] = field_value
    candidate_payload = {
        'name': self.name or str(source_candidate.get('name') or ''),
        'description': self.description or str(source_candidate.get('description') or ''),
        'strategy_type': self.strategy_type,
        'params': candidate_params,
        'spawn_reason': self.description or self.name or f'{source}:{self.strategy_type}',
        'hypothesis': _scalar_value(metadata.get('hypothesis'), source_candidate.get('hypothesis')),
        'holding_horizon': dict(holding_horizon),
        'trade_plan': dict(trade_plan),
        'risk_rules': dict(risk_rules),
        'position_sizing': dict(position_sizing),
        'execution_notes': _scalar_value(metadata.get('execution_notes'), source_candidate.get('execution_notes')),
        'rebalance_rule': dict(rebalance_rule),
        'portfolio_spec': dict(portfolio_spec),
        'execution_assumptions': dict(execution_assumptions),
        'runtime_playbook': dict(runtime_playbook),
        'validation_profile': dict(validation_profile),
        'event_prefilter': dict(event_prefilter),
        'targeting_policy': dict(targeting_policy),
        'constraint_check': dict(constraint_check),
        'hypothesis_artifact': dict(hypothesis_artifact),
        'hypothesis_artifact_id': _scalar_value(
            metadata.get('hypothesis_artifact_id'),
            source_candidate.get('hypothesis_artifact_id'),
            hypothesis_artifact.get('artifact_id'),
        ),
        'hypothesis_lowering_audit': _dict_value(
            metadata.get('hypothesis_lowering_audit'),
            source_candidate.get('hypothesis_lowering_audit'),
        ),
        'holding_rationale': holding_rationale,
        'failure_mode': failure_mode,
        'alpha_half_life': alpha_half_life,
        'cost_sensitivity_grid': _dict_value(
            cost_sensitivity_grid,
        ),
        'position_model': position_model,
        'capacity_assumption': dict(capacity_assumption),
        'market_regime_assumption': market_regime_assumption,
        'instrument_profile': dict(instrument_profile),
        'regime_filter_contract': dict(regime_filter_contract),
        'parameter_coherence_audit': dict(parameter_coherence_audit),
        'thesis_invalidation_contract': dict(thesis_invalidation_contract),
        'drawdown_invalidation_contract': dict(drawdown_invalidation_contract),
        'position_sizing_rationale': position_sizing_rationale,
        'capacity_bucket': capacity_bucket,
        'turnover_cost_class': execution_assumptions.get('turnover_cost_class'),
        'expected_turnover_band': expected_turnover_band,
        'family_specialization': dict(family_specialization),
        'execution_semantic_mode': execution_semantic_contract.get('execution_semantic_mode'),
        'execution_semantic_gap': bool(execution_semantic_contract.get('execution_semantic_gap') or execution_semantic_gap_reasons),
        'execution_semantic_gap_reasons': execution_semantic_gap_reasons,
        'dsl_required': bool(execution_semantic_contract.get('dsl_required')),
        'dsl_compiled': bool(execution_semantic_contract.get('dsl_compiled')),
        'dsl_compile_failure_reasons': list(execution_semantic_contract.get('dsl_compile_failure_reasons') or []),
        'semantic_runtime_match': bool(runtime_semantic_diagnostics.get('semantic_runtime_match')),
        'runtime_family_data_source': runtime_semantic_diagnostics.get('runtime_family_data_source'),
        'proxy_runtime_used': bool(runtime_semantic_diagnostics.get('proxy_runtime_used')),
        'diagnostic_only': bool(runtime_semantic_diagnostics.get('diagnostic_only')),
        'execution_readiness_tier': runtime_semantic_diagnostics.get('execution_readiness_tier'),
        'semantic_contract_missing_fields': list(runtime_semantic_diagnostics.get('semantic_contract_missing_fields') or []),
        'economic_semantics_score': _scalar_value(
            metadata.get('economic_semantics_score'),
            source_candidate.get('economic_semantics_score'),
            hypothesis_artifact.get('economic_semantics_score'),
        ),
        'economic_semantics_missing_fields': _list_value(
            metadata.get('economic_semantics_missing_fields'),
            source_candidate.get('economic_semantics_missing_fields'),
            hypothesis_artifact.get('economic_semantics_missing_fields'),
        ),
        'validation_focus': _scalar_value(
            metadata.get('validation_focus'),
            source_candidate.get('validation_focus'),
            hypothesis_artifact.get('validation_focus'),
            validation_profile.get('validation_focus'),
        ),
        'candidate_family': candidate_family,
        'candidate_family_id': candidate_family_id,
        'candidate_origin': candidate_origin,
        'event_anchor': dict(event_anchor),
        'target_pool_source': target_pool_source,
        'generation_reason': _dict_value(metadata.get('generation_reason'), source_candidate.get('generation_reason')),
        'committee_review': _dict_value(metadata.get('committee_review'), source_candidate.get('committee_review')),
        'generator_type': _scalar_value(metadata.get('generator_type'), source_candidate.get('generator_type'), source) or source,
        'optimizer_type': _scalar_value(metadata.get('optimizer_type'), source_candidate.get('optimizer_type')),
        'llm_prompt': _dict_value(metadata.get('llm_prompt'), source_candidate.get('llm_prompt')),
        'llm_response': _dict_value(metadata.get('llm_response'), source_candidate.get('llm_response')),
        'target_symbols': list(target_symbols),
        'stock_pool': dict(stock_pool),
        'selection_logic': list(selection_logic),
        'research_scope': dict(research_scope),
        'research_task': dict(research_task),
        'event_context': dict(event_context),
        'source_symbol_summary': dict(source_symbol_summary),
        'task_run_id': _scalar_value(metadata.get('task_run_id'), source_candidate.get('task_run_id')),
        'parent_strategy_id': _scalar_value(metadata.get('parent_strategy_id'), source_candidate.get('parent_strategy_id')),
        'pipeline_provenance': _dict_value(metadata.get('pipeline_provenance')),
        'experiment_id': experiment_id,
        'prediction_trace_id': prediction_trace_id,
        'trace_id': prediction_trace_id,
        'research_validation_contract': dict(research_validation_contract),
        'research_protocol_version': research_protocol_version,
        'candidate_contract_version': candidate_contract_version,
        'field_provenance': dict(field_provenance),
        'field_provenance_summary': dict(field_provenance_summary),
        'spec_completeness': spec_completeness,
        'completion_issues': list(completion_issues),
        'hard_failures': list(research_hard_failures),
        'tags': list(dict.fromkeys(['ai_generated', source, self.strategy_type, *(self.tags or [])])),
    }
    if backtest_metrics:
        candidate_payload['backtest_metrics'] = dict(backtest_metrics)
    if execution_semantic_contract.get("dsl"):
        candidate_payload["dsl"] = dict(execution_semantic_contract.get("dsl") or {})
    for field_name in (
        "evidence_chain",
        "prediction_contract",
        "confidence_contract",
        "evidence_alignment_audit",
        "dsl_support_audit",
        "claim_to_trade_plan_map",
        "trade_plan_to_dsl_map",
    ):
        if isinstance(candidate_params.get(field_name), dict) and candidate_params.get(field_name):
            candidate_payload[field_name] = dict(candidate_params.get(field_name) or {})
