

def _resolve_high_precision_context(strategy: dict, profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    payload = dict(strategy or {})
    params = dict(payload.get("params") or {})
    validation_profile = dict(
        _strategy_payload_value(payload, "validation_profile")
        or payload.get("validation_profile")
        or {}
    )
    research_task = dict(
        _strategy_payload_value(payload, "research_task")
        or payload.get("research_task")
        or {}
    )
    research_context = dict(
        _strategy_payload_value(payload, "research_context")
        or payload.get("research_context")
        or {}
    )
    event_context = dict(
        _strategy_payload_value(payload, "event_context")
        or payload.get("event_context")
        or {}
    )
    hypothesis_artifact = dict(
        _strategy_payload_value(payload, "hypothesis_artifact")
        or payload.get("hypothesis_artifact")
        or {}
    )
    generation_reason = dict(
        _strategy_payload_value(payload, "generation_reason")
        or payload.get("generation_reason")
        or {}
    )
    trigger_signal = dict(
        generation_reason.get("trigger_signal")
        or _strategy_payload_value(payload, "trigger_signal")
        or payload.get("trigger_signal")
        or {}
    )
    market_regime_assumption = dict(
        hypothesis_artifact.get("market_regime_assumption")
        or _strategy_payload_value(payload, "market_regime_assumption")
        or payload.get("market_regime_assumption")
        or research_context.get("market_regime_assumption")
        or {}
    )
    event_prefilter = dict(
        _strategy_payload_value(payload, "event_prefilter")
        or payload.get("event_prefilter")
        or hypothesis_artifact.get("event_prefilter")
        or validation_profile.get("event_prefilter")
        or research_context.get("event_prefilter")
        or research_task.get("event_prefilter")
        or {}
    )
    event_anchor = _normalize_event_anchor_payload(
        event_prefilter.get("event_anchor"),
        _strategy_payload_value(payload, "event_anchor"),
        payload.get("event_anchor"),
        hypothesis_artifact.get("event_anchor"),
        research_task.get("event_anchor"),
        research_context.get("event_anchor"),
        event_context.get("event_anchor"),
    )
    objective_profile = _normalize_text(
        (profile or {}).get("objective_profile")
        or validation_profile.get("objective_profile")
        or hypothesis_artifact.get("objective_profile")
        or research_task.get("objective_profile")
        or research_context.get("objective_profile")
    ) or None
    if not objective_profile and str(payload.get("generator_mode") or "").strip().lower() == "futures_calendar_research_adapter":
        objective_profile = "high_precision"
    trade_density_preference = _normalize_text(
        (profile or {}).get("trade_density_preference")
        or validation_profile.get("trade_density_preference")
        or hypothesis_artifact.get("trade_density_preference")
        or research_task.get("trade_density_preference")
    ) or ("low" if objective_profile == "high_precision" else None)
    entry_selectivity = _normalize_text(
        (profile or {}).get("entry_selectivity")
        or validation_profile.get("entry_selectivity")
        or hypothesis_artifact.get("entry_selectivity")
    ) or None
    strategy_type = _normalize_text(payload.get("strategy_type") or params.get("strategy_type"))
    event_prefilter_required = _normalize_boolish(
        event_prefilter.get("required")
        if event_prefilter.get("required") is not None
        else (profile or {}).get("event_prefilter_required")
        if (profile or {}).get("event_prefilter_required") is not None
        else validation_profile.get("event_prefilter_required"),
        default=objective_profile == "high_precision" and strategy_type == "event_structure_breakout",
    )
    event_prefilter_profile = _strip_text(
        event_prefilter.get("profile")
        or (profile or {}).get("event_prefilter_profile")
        or validation_profile.get("event_prefilter_profile")
    ) or ("announcement_flow_sector_v1" if event_prefilter_required else None)
    try:
        event_prefilter_min_confirmations = max(
            1,
            int(
                event_prefilter.get("min_confirmations")
                or (profile or {}).get("event_prefilter_min_confirmations")
                or validation_profile.get("event_prefilter_min_confirmations")
                or 1
            ),
        )
    except Exception:
        event_prefilter_min_confirmations = 1
    observed_sources = _normalize_string_list(
        event_prefilter.get("observed_sources"),
        event_prefilter.get("catalyst_sources"),
        event_prefilter.get("source_types"),
    )
    event_id = _strip_text(
        event_prefilter.get("event_id")
        or research_task.get("event_id")
        or event_context.get("event_id")
        or research_context.get("event_id")
    ) or None
    announcement_id = _strip_text(
        event_prefilter.get("announcement_id")
        or research_task.get("announcement_id")
        or event_context.get("announcement_id")
        or research_context.get("announcement_id")
    ) or None
    announcement_ids = _normalize_string_list(
        event_prefilter.get("announcement_ids"),
        research_task.get("announcement_ids"),
        event_context.get("announcement_ids"),
        research_context.get("announcement_ids"),
    )
    event_type = _normalize_text(
        event_prefilter.get("event_type")
        or research_task.get("event_type")
        or event_context.get("event_type")
        or research_context.get("event_type")
        or event_prefilter.get("catalyst_type")
        or research_task.get("catalyst_type")
        or event_context.get("catalyst_type")
        or research_context.get("catalyst_type")
    )
    theme_code = _strip_text(
        event_prefilter.get("theme_code")
        or research_task.get("theme_code")
        or event_context.get("theme_code")
        or research_context.get("theme_code")
    ) or None
    evidence_summary = _strip_text(
        event_prefilter.get("evidence_summary")
        or research_task.get("evidence_summary")
        or event_context.get("evidence_summary")
        or research_context.get("evidence_summary")
    ) or None
    focus_industries = _normalize_string_list(
        event_prefilter.get("focus_industries"),
        research_task.get("focus_industries"),
        research_task.get("hot_sectors"),
        research_context.get("focus_industries"),
        research_context.get("hot_sectors"),
    )
    generation_source = _normalize_text(generation_reason.get("source"))
    trigger_field = _normalize_text(trigger_signal.get("field"))
    has_announcement_anchor = bool(
        _normalize_text(event_anchor.get("source")) == "announcement"
        or event_id
        or announcement_id
        or announcement_ids
        or event_type in {"announcement", "earnings", "filing", "news"}
        or generation_source == "announcement"
    )
    if not event_anchor:
        if has_announcement_anchor:
            event_anchor = {
                "source": "announcement",
                "id": event_id or announcement_id or (announcement_ids[0] if announcement_ids else None) or event_type or "announcement",
                "type": event_type or "announcement",
                "strength": event_prefilter.get("anchor_strength"),
                "theme_code": theme_code,
                "focus_industries": focus_industries,
                "target_symbols": _normalize_symbol_list(
                    research_task.get("target_symbols"),
                    event_context.get("target_symbols"),
                    research_context.get("target_symbols"),
                    limit=12,
                ),
            }
        elif generation_source == "fund_flow" or trigger_field in {"north_fund_3d_net", "margin_5d_change_pct"}:
            event_anchor = {
                "source": "fund_flow",
                "id": trigger_field or generation_source or "fund_flow",
                "type": "fund_flow",
                "strength": trigger_signal.get("value"),
                "theme_code": theme_code,
                "focus_industries": focus_industries,
                "target_symbols": _normalize_symbol_list(
                    research_task.get("target_symbols"),
                    event_context.get("target_symbols"),
                    research_context.get("target_symbols"),
                    limit=12,
                ),
            }
    anchor_source = _normalize_text(event_anchor.get("source"))
    if has_announcement_anchor and "announcement" not in observed_sources:
        observed_sources.append("announcement")
    if anchor_source == "sector_catalyst" and "sector_catalyst" not in observed_sources:
        observed_sources.append("sector_catalyst")
    if anchor_source == "fund_flow" or generation_source == "fund_flow" or trigger_field in {"north_fund_3d_net", "margin_5d_change_pct"}:
        if "fund_flow" not in observed_sources:
            observed_sources.append("fund_flow")
    allowed_sources = _normalize_string_list(
        event_prefilter.get("allowed_sources"),
        ["announcement", "fund_flow", "sector_catalyst"] if event_prefilter_required else [],
    )
    matched_sources = [item for item in observed_sources if not allowed_sources or item in allowed_sources]
    confirmation_count = max(
        int(event_prefilter.get("confirmation_count") or 0),
        len(matched_sources),
    )
    event_prefilter_passed = (not event_prefilter_required) or (bool(event_anchor) and confirmation_count >= event_prefilter_min_confirmations)
    event_prefilter_summary = {
        "available": bool(event_prefilter_required or event_prefilter or observed_sources),
        "required": event_prefilter_required,
        "profile": event_prefilter_profile,
        "allowed_sources": allowed_sources,
        "observed_sources": matched_sources,
        "observed_confirmation_count": len(matched_sources),
        "confirmation_count": confirmation_count,
        "min_confirmations": event_prefilter_min_confirmations,
        "passed": event_prefilter_passed,
        "event_id": event_id,
        "announcement_id": announcement_id,
        "announcement_ids": announcement_ids,
        "theme_code": theme_code,
        "focus_industries": focus_industries,
        "evidence_summary": evidence_summary,
        "event_anchor": event_anchor,
        "anchor_strength": event_prefilter.get("anchor_strength")
        if event_prefilter.get("anchor_strength") is not None
        else event_anchor.get("strength"),
        "event_type": event_type or None,
        "trigger_field": trigger_field or None,
        "generation_source": generation_source or None,
        "status": (
            "passed"
            if event_prefilter_passed
            else ("missing" if not event_anchor else "insufficient_confirmations")
        ),
    }
    return {
        "objective_profile": objective_profile,
        "trade_density_preference": trade_density_preference,
        "entry_selectivity": entry_selectivity,
        "regime_required": _normalize_boolish(
            (profile or {}).get("regime_required")
            if (profile or {}).get("regime_required") is not None
            else validation_profile.get("regime_required")
            if validation_profile.get("regime_required") is not None
            else hypothesis_artifact.get("regime_required"),
            default=objective_profile == "high_precision",
        ),
        "cost_robust_required": _normalize_boolish(
            (profile or {}).get("cost_robust_required")
            if (profile or {}).get("cost_robust_required") is not None
            else validation_profile.get("cost_robust_required")
            if validation_profile.get("cost_robust_required") is not None
            else hypothesis_artifact.get("cost_robust_required"),
            default=objective_profile == "high_precision",
        ),
        "preferred_regime": _strip_text(
            market_regime_assumption.get("preferred_regime")
            or validation_profile.get("preferred_regime")
        ) or None,
        "avoid_regime": _strip_text(
            market_regime_assumption.get("avoid_regime")
            or validation_profile.get("avoid_regime")
        ) or None,
        "holding_rationale": _strip_text(
            hypothesis_artifact.get("holding_rationale")
            or _strategy_payload_value(payload, "holding_rationale")
            or payload.get("holding_rationale")
        ) or None,
        "failure_mode": hypothesis_artifact.get("failure_mode")
        or _strategy_payload_value(payload, "failure_mode")
        or payload.get("failure_mode"),
        "cost_sensitivity_grid": dict(
            hypothesis_artifact.get("cost_sensitivity_grid")
            or _strategy_payload_value(payload, "cost_sensitivity_grid")
            or payload.get("cost_sensitivity_grid")
            or {}
        ),
        "event_prefilter_summary": event_prefilter_summary,
    }


def _evaluate_high_precision_admission(
    strategy: dict,
    profile: dict[str, Any],
    gate_payload: Optional[dict[str, Any]],
    *,
    backtest_metrics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = _resolve_high_precision_context(strategy, profile)
    objective_profile = _normalize_text(context.get("objective_profile"))
    if objective_profile != "high_precision":
        return {
            "available": False,
            "decision": "pass",
            "blocking_reasons": [],
            "warnings": [],
            "precision_readiness": None,
            "regime_validation_summary": {},
            "cost_robustness_summary": {},
            "trade_density_summary": {},
            "objective_profile": None,
        }

    metrics = dict(gate_payload or {})
    if backtest_metrics:
        metrics = {**dict(backtest_metrics or {}), **metrics}
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    preferred_regime = _strip_text(context.get("preferred_regime")) or None
    avoid_regime = _strip_text(context.get("avoid_regime")) or None
    holding_rationale = _strip_text(context.get("holding_rationale")) or None
    failure_mode = context.get("failure_mode")
    cost_sensitivity_grid = dict(context.get("cost_sensitivity_grid") or {})
    event_prefilter_summary = dict(context.get("event_prefilter_summary") or {})
    event_anchor_summary = dict(event_prefilter_summary.get("event_anchor") or {})
    trade_density_preference = _normalize_text(context.get("trade_density_preference")) or "low"
    entry_selectivity = _normalize_text(context.get("entry_selectivity")) or None
    regime_required = bool(context.get("regime_required"))
    cost_robust_required = bool(context.get("cost_robust_required"))
    trade_density = safe_metric_value(metrics, "trade_density")
    density_limit = 0.75 if trade_density_preference == "low" else 1.05
    density_passed = trade_density <= density_limit if trade_density > 0 else bool(entry_selectivity)

    if not holding_rationale:
        blocking_reasons.append("high_precision_missing_holding_rationale")
    if failure_mode in (None, "", [], {}):
        blocking_reasons.append("high_precision_missing_failure_mode")
    if regime_required:
        if not preferred_regime:
            blocking_reasons.append("high_precision_missing_preferred_regime")
        if not avoid_regime:
            blocking_reasons.append("high_precision_missing_avoid_regime")
    if not entry_selectivity:
        blocking_reasons.append("high_precision_missing_entry_selectivity")
    if trade_density > 0 and not density_passed:
        blocking_reasons.append("high_precision_trade_density_exceeds_preference")
    if cost_robust_required and not cost_sensitivity_grid:
        blocking_reasons.append("high_precision_missing_cost_sensitivity_grid")
    if event_prefilter_summary.get("required"):
        if not event_anchor_summary:
            blocking_reasons.append("high_precision_missing_event_prefilter_signal")
        elif not bool(event_prefilter_summary.get("passed")):
            blocking_reasons.append("high_precision_event_prefilter_not_confirmed")

    cost_scenarios = dict(metrics.get("cost_sensitivity_results") or metrics.get("cost_scenarios") or {})
    observed_bps: list[float] = []
    stress_post_cost_sharpe = None
    if cost_scenarios:
        for raw_key, raw_value in cost_scenarios.items():
            row = dict(raw_value or {})
            parsed_bps = safe_metric_value({"bps": raw_key}, "bps")
            if parsed_bps <= 0 and row.get("slippage_bps") is not None:
                parsed_bps = safe_metric_value(row, "slippage_bps")
            if parsed_bps > 0 and parsed_bps not in observed_bps:
                observed_bps.append(parsed_bps)
        if observed_bps:
            max_bps = max(observed_bps)
            stress_row = {}
            for raw_value in cost_scenarios.values():
                row = dict(raw_value or {})
                if safe_metric_value(row, "slippage_bps") == max_bps:
                    stress_row = row
                    break
            stress_post_cost_sharpe = safe_metric_value(stress_row, "post_cost_sharpe")
    if cost_robust_required and cost_sensitivity_grid and not observed_bps:
        warnings.append("high_precision_cost_observation_pending")
    if cost_robust_required and stress_post_cost_sharpe is not None and stress_post_cost_sharpe <= 0.0:
        blocking_reasons.append("high_precision_cost_fragility")

    post_cost_sharpe = safe_metric_value(metrics, "post_cost_sharpe")
    trade_count = safe_metric_value(metrics, "trade_count", "trades_count")
    regime_validation_summary = {
        "available": True,
        "objective_profile": objective_profile,
        "preferred_regime": preferred_regime,
        "avoid_regime": avoid_regime,
        "regime_required": regime_required,
        "passed": (not regime_required) or bool(preferred_regime and avoid_regime),
    }
    cost_robustness_summary = {
        "available": bool(cost_sensitivity_grid),
        "required": cost_robust_required,
        "observed_bps": sorted(observed_bps),
        "stress_post_cost_sharpe": round(float(stress_post_cost_sharpe), 4)
        if stress_post_cost_sharpe is not None
        else None,
        "passed": bool(cost_sensitivity_grid) and (stress_post_cost_sharpe is None or stress_post_cost_sharpe > 0.0),
    }
    trade_density_summary = {
        "available": True,
        "preference": trade_density_preference,
        "entry_selectivity": entry_selectivity,
        "max_trade_density": round(density_limit, 4),
        "observed_trade_density": round(trade_density, 4) if trade_density > 0 else None,
        "passed": bool(density_passed),
    }
    if blocking_reasons:
        decision = "reject" if "high_precision_trade_density_exceeds_preference" in blocking_reasons and trade_density > density_limit * 1.5 else "revise"
    else:
        decision = "pass"
    if decision != "pass":
        precision_readiness = decision
    elif post_cost_sharpe >= 0.8 and trade_count >= 6 and density_passed:
        precision_readiness = "strong"
    elif post_cost_sharpe >= 0.45 and trade_count >= 3:
        precision_readiness = "candidate"
    else:
        precision_readiness = "observe"
    return {
        "available": True,
        "decision": decision,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "precision_readiness": precision_readiness,
        "regime_validation_summary": regime_validation_summary,
        "cost_robustness_summary": cost_robustness_summary,
        "trade_density_summary": trade_density_summary,
        "event_prefilter_summary": event_prefilter_summary,
        "event_anchor_summary": event_anchor_summary,
        "objective_profile": objective_profile,
    }


def _resolve_research_protocol_observed_payload(
    strategy: dict,
    *,
    backtest_metrics: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    metrics = dict(backtest_metrics or {})
    params = dict(strategy.get("params") or {})
    candidate_provenance = dict(
        _strategy_payload_value(strategy, "candidate_provenance")
        or strategy.get("candidate_provenance")
        or {}
    )
    contract_snapshot = dict(
        _strategy_payload_value(strategy, "candidate_contract_snapshot")
        or strategy.get("candidate_contract_snapshot")
        or {}
    )
    strategy_profile = dict(contract_snapshot.get("strategy_profile") or {})
    cost_assumptions = dict(metrics.get("cost_assumptions") or {})
    implementation_shortfall = dict(metrics.get("implementation_shortfall_components") or {})
    cash_sleeve = dict(
        metrics.get("cash_sleeve")
        or _strategy_payload_value(strategy, "cash_sleeve")
        or _strategy_payload_value(strategy, "cash_sleeve_policy")
        or {}
    )
    return {
        "oos_cagr": (
            metrics.get("oos_cagr")
            if metrics.get("oos_cagr") is not None
            else metrics.get("target_layer_oos_return")
        ),
        "benchmark_oos_cagr": (
            metrics.get("benchmark_oos_cagr")
            if metrics.get("benchmark_oos_cagr") is not None
            else metrics.get("benchmark_target_layer_oos_return")
        ),
        "oos_max_drawdown": (
            metrics.get("oos_max_drawdown")
            if metrics.get("oos_max_drawdown") is not None
            else metrics.get("max_drawdown")
        ),
        "benchmark_oos_max_drawdown": (
            metrics.get("benchmark_oos_max_drawdown")
            if metrics.get("benchmark_oos_max_drawdown") is not None
            else metrics.get("benchmark_max_drawdown")
        ),
        "total_return": metrics.get("total_return"),
        "post_cost_sharpe": metrics.get("post_cost_sharpe"),
        "effective_total_bps": (
            implementation_shortfall.get("effective_total_bps")
            if implementation_shortfall.get("effective_total_bps") is not None
            else cost_assumptions.get("slippage_bps")
        ),
        "cost_sensitivity_results": dict(
            metrics.get("cost_sensitivity_results")
            or metrics.get("cost_scenarios")
            or metrics.get("cost_sensitivity_grid_results")
            or {}
        ),
        "cash_sleeve": cash_sleeve,
        "family": (
            candidate_provenance.get("candidate_family")
            or candidate_provenance.get("candidate_family_id")
            or strategy_profile.get("candidate_family")
            or strategy.get("strategy_type")
        ),
        "holding_bucket": (
            candidate_provenance.get("holding_period_bucket")
            or strategy_profile.get("holding_period_bucket")
            or _strategy_payload_value(strategy, "holding_period_bucket")
        ),
        "artifact_ids": _normalize_symbol_list(
            _strategy_payload_value(strategy, "artifact_ids"),
            candidate_provenance.get("artifact_ids"),
            params.get("artifact_ids"),
            limit=16,
        ),
        "retrieval_context_ids": _normalize_symbol_list(
            _strategy_payload_value(strategy, "retrieval_context_ids"),
            candidate_provenance.get("retrieval_context_ids"),
            params.get("retrieval_context_ids"),
            limit=16,
        ),
        "prediction_trace_id": (
            _strategy_payload_value(strategy, "prediction_trace_id")
            or _strategy_payload_value(strategy, "trace_id")
            or params.get("prediction_trace_id")
            or params.get("trace_id")
        ),
        "trace_id": (
            _strategy_payload_value(strategy, "trace_id")
            or _strategy_payload_value(strategy, "prediction_trace_id")
            or params.get("trace_id")
            or params.get("prediction_trace_id")
        ),
    }
