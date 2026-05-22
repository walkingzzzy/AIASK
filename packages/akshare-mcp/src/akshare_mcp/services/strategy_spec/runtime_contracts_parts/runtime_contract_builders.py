

def _build_parameter_coherence_audit(
    strategy_type: str,
    *,
    holding_horizon: Optional[dict[str, Any]],
    rebalance_rule: Optional[dict[str, Any]],
    runtime_playbook: Optional[dict[str, Any]],
    instrument_profile: Optional[dict[str, Any]],
    backtest_metrics: Optional[dict[str, Any]],
) -> dict[str, Any]:
    holding = dict(holding_horizon or {})
    rebalance = dict(rebalance_rule or {})
    playbook = dict(runtime_playbook or {})
    entry_policy = dict(playbook.get("entry_policy") or {})
    exit_policy = dict(playbook.get("exit_policy") or {})
    reentry_policy = dict(playbook.get("reentry_policy") or {})
    incubation_policy = dict(playbook.get("incubation_policy") or {})
    profile = dict(instrument_profile or {})
    metrics = dict(backtest_metrics or {})
    issues: list[dict[str, Any]] = []

    atr14_pct = _instrument_profile_metric(
        profile,
        "atr14_pct_realized",
        "atr14_pct",
        default=0.03,
        minimum=0.01,
        maximum=0.12,
    )
    initial_stop = abs(_safe_float(exit_policy.get("initial_stop_loss_pct"), 0.0))
    if initial_stop > 0:
        stop_vs_atr = round(initial_stop / max(atr14_pct, 1e-6), 4)
        if stop_vs_atr < 1.2:
            issues.append(
                {
                    "code": "stop_vs_atr_too_tight",
                    "severity": "blocker",
                    "message": "initial stop loss is tighter than 1.2x ATR for the measured instrument profile",
                    "metric": "stop_vs_atr",
                    "value": stop_vs_atr,
                }
            )
        elif stop_vs_atr > 4.5:
            issues.append(
                {
                    "code": "stop_vs_atr_too_loose",
                    "severity": "warning",
                    "message": "initial stop loss is looser than 4.5x ATR and may dilute thesis invalidation timing",
                    "metric": "stop_vs_atr",
                    "value": stop_vs_atr,
                }
            )

    max_holding_days = max(
        _safe_int(holding.get("max_days"), 0),
        _safe_int(exit_policy.get("time_stop_days"), 0),
    )
    rebalance_interval_days = _safe_int(
        rebalance.get("frequency_days") or rebalance.get("rebalance_interval_days"),
        0,
    )
    if rebalance_interval_days > 0 and max_holding_days > 0 and rebalance_interval_days > max_holding_days:
        issues.append(
            {
                "code": "holding_horizon_shorter_than_rebalance_interval",
                "severity": "blocker",
                "message": "rebalance interval exceeds maximum holding horizon",
                "metric": "rebalance_interval_days",
                "value": rebalance_interval_days,
            }
        )

    observed_trade_count = max(
        _safe_float(metrics.get("trade_count"), 0.0),
        _safe_float(metrics.get("trades_count"), 0.0),
        _safe_float(metrics.get("total_trades"), 0.0),
    )
    expected_trade_interval_days = (
        round(252.0 / observed_trade_count, 2)
        if observed_trade_count > 0
        else float(max(6, max_holding_days or 20))
    )
    cooldown_days = _safe_int(reentry_policy.get("cooldown_days"), 0)
    if cooldown_days > 0 and expected_trade_interval_days > 0 and cooldown_days > expected_trade_interval_days * 1.5:
        issues.append(
            {
                "code": "cooldown_exceeds_expected_trade_interval",
                "severity": "warning",
                "message": "cooldown is materially longer than expected trade interval and may suppress re-entry evidence accumulation",
                "metric": "cooldown_days",
                "value": cooldown_days,
            }
        )

    warmup_target_signals = _safe_int(incubation_policy.get("warmup_target_signals"), 0)
    expected_annual_signals = max(1.0, observed_trade_count or round(252.0 / max(expected_trade_interval_days, 1.0), 2))
    if warmup_target_signals > max(8, expected_annual_signals * 1.25):
        issues.append(
            {
                "code": "warmup_target_exceeds_signal_density",
                "severity": "blocker" if strategy_type in _TREND_EXECUTABLE_DSL_TYPES else "warning",
                "message": "warmup target signals exceeds expected annual signal density and may deadlock incubation",
                "metric": "warmup_target_signals",
                "value": warmup_target_signals,
            }
        )

    volume_confirmation = dict(entry_policy.get("volume_confirmation") or {})
    volume_ratio_floor = _safe_float(volume_confirmation.get("volume_ratio_floor"), 0.0)
    volume_ratio_p90 = _instrument_profile_metric(
        profile,
        "volume_ratio_p90",
        default=1.18,
        minimum=1.0,
        maximum=3.0,
    )
    if volume_ratio_floor > 0 and volume_ratio_floor > volume_ratio_p90 + 0.05:
        issues.append(
            {
                "code": "volume_filter_exceeds_observed_distribution",
                "severity": "warning",
                "message": "volume confirmation floor is above observed p90 and may create signal vacuum",
                "metric": "volume_ratio_floor",
                "value": volume_ratio_floor,
            }
        )

    trade_density = _safe_float(metrics.get("trade_density"), 0.0)
    implementation_shortfall_proxy = _safe_float(metrics.get("implementation_shortfall_proxy"), 0.0)
    if trade_density > 0 and implementation_shortfall_proxy > 0 and trade_density * implementation_shortfall_proxy > 0.12:
        issues.append(
            {
                "code": "trade_density_cost_pressure_high",
                "severity": "warning",
                "message": "expected trade density and implementation shortfall imply elevated round-trip cost drag",
                "metric": "trade_density_cost_pressure",
                "value": round(trade_density * implementation_shortfall_proxy, 4),
            }
        )

    blockers = [issue["code"] for issue in issues if issue.get("severity") == "blocker"]
    warnings = [issue["code"] for issue in issues if issue.get("severity") == "warning"]
    return {
        "status": "failed" if blockers else "passed_with_warnings" if warnings else "passed",
        "issues": issues,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": {
            "stop_vs_atr": round(initial_stop / max(atr14_pct, 1e-6), 4) if initial_stop > 0 else None,
            "expected_trade_interval_days": expected_trade_interval_days,
            "warmup_target_signals": warmup_target_signals or None,
            "expected_annual_signals": round(expected_annual_signals, 2),
            "volume_ratio_floor": round(volume_ratio_floor, 4) if volume_ratio_floor > 0 else None,
            "volume_ratio_p90": round(volume_ratio_p90, 4),
        },
    }


def _resolve_source_label(*labeled_values: tuple[str, Any]) -> str:
    for label, value in labeled_values:
        if isinstance(value, dict) and value:
            return label
        if isinstance(value, (list, tuple, set)) and value:
            return label
        if value not in (None, "", [], {}):
            return label
    return "default"


def _normalize_symbol_tokens(*values: Any) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                token = str(item or "").strip()
                if token:
                    tokens.append(token)
        else:
            token = str(value or "").strip()
            if token:
                tokens.append(token)
    return list(dict.fromkeys(tokens))


def _merge_contract_payloads(*payloads: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            token = str(key or "").strip()
            if not token:
                continue
            if isinstance(value, dict) and isinstance(merged.get(token), dict):
                merged[token] = _merge_contract_payloads(merged[token], value)
            elif isinstance(value, dict):
                merged[token] = _merge_contract_payloads(value)
            elif isinstance(value, list):
                merged[token] = list(value)
            else:
                merged[token] = value
    return merged


def _resolve_nonmissing_field_provenance(source: Any) -> str:
    token = normalize_field_provenance_token(source)
    return token if token != "missing" else "derived"


def _should_use_510300_default_research_protocol(
    *,
    strategy_type: str,
    target_symbols: list[str],
    research_task: Optional[dict[str, Any]] = None,
    candidate_family: Any = None,
) -> bool:
    del strategy_type
    symbol_tokens = {token.lower() for token in _normalize_symbol_tokens(target_symbols)}
    if symbol_tokens.intersection({"510300", "159919", "510310"}):
        return True
    task = dict(research_task or {})
    family_tokens = {
        str(candidate_family or "").strip().lower(),
        str(task.get("candidate_family") or "").strip().lower(),
        str(task.get("family") or "").strip().lower(),
    }
    return any("510300" in token for token in family_tokens if token)


def _generic_default_research_validation_contract_payload(
    *,
    validation_profile: Optional[dict[str, Any]] = None,
    family: str | None = None,
    holding_bucket: str = "medium",
) -> dict[str, Any]:
    return {
        "contract_version": "strategy_factory.research_protocol.v2",
        "walk_forward_config": {"train_months": 60, "test_months": 12, "step_months": 12},
        "baseline_reference": {
            "name": "cn_equity_generic_baseline",
            "baseline_slippage_bps": 5.0,
            "stress_slippage_bps": 10.0,
        },
        "cash_sleeve_policy": {
            "enabled": False,
            "schedule_clock": "prev_close_signal_next_open_execute_same_close_cash_rebuild",
        },
        "cost_sensitivity_grid": {
            "base_slippage_bps": 5.0,
            "stress_slippage_bps": 10.0,
            "main_scenario_slippage_bps": 5.0,
            "control_scenario_slippage_bps": 0.0,
        },
        "capacity_execution": {
            "schedule_clock": "prev_close_signal_next_open_execute_same_close_cash_rebuild",
        },
        "multiple_testing": {
            "mode": "formal_runtime",
            "white_reality_check_enabled": True,
            "hansen_spa_enabled": True,
            "pbo_enabled": True,
        },
        "admission_thresholds": {
            "validation_profile": dict(validation_profile or {}),
        },
        "family_holding_bucket": {
            "family": str(family or "default").strip().lower() or "default",
            "holding_bucket": str(holding_bucket or "medium").strip().lower() or "medium",
            "enable_enhancements": False,
            "enforce_family_alignment": False,
            "enforce_holding_bucket_alignment": False,
        },
    }


def _default_research_validation_contract_payload(
    *,
    strategy_type: str,
    target_symbols: list[str],
    research_task: Optional[dict[str, Any]] = None,
    validation_profile: Optional[dict[str, Any]] = None,
    candidate_family: Any = None,
    holding_bucket: str = "medium",
) -> dict[str, Any]:
    if _should_use_510300_default_research_protocol(
        strategy_type=strategy_type,
        target_symbols=target_symbols,
        research_task=research_task,
        candidate_family=candidate_family,
    ):
        try:
            from .research_510300_v3 import build_default_research_validation_contract

            return dict(build_default_research_validation_contract() or {})
        except Exception:
            pass
    return _generic_default_research_validation_contract_payload(
        validation_profile=validation_profile,
        family=str(candidate_family or "").strip().lower() or str(strategy_type or "").strip().lower(),
        holding_bucket=holding_bucket,
    )


def _classify_holding_bucket(holding_horizon: dict[str, Any]) -> str:
    max_days = _safe_int(dict(holding_horizon or {}).get("max_days"), 0)
    if max_days <= 5:
        return "short"
    if max_days <= 15:
        return "medium"
    return "long"


def _trade_plan_nodes_for_provenance(trade_plan: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def _append(node: Any, *, phase: str, index: int = 0) -> None:
        if not isinstance(node, dict):
            return
        node_id = str(
            node.get("node_id")
            or node.get("plan_node_id")
            or node.get("trade_plan_node_id")
            or node.get("trade_plan_step_id")
            or node.get("id")
            or f"{phase}_{index}"
        ).strip()
        claim_ids = [
            str(item).strip()
            for item in list(node.get("claim_ids") or [])
            if str(item).strip()
        ]
        nodes.append(
            {
                **node,
                "node_id": node_id,
                "phase": phase,
                "claim_ids": list(dict.fromkeys(claim_ids)),
            }
        )

    payload = dict(trade_plan or {})
    if isinstance(payload.get("entry"), dict):
        _append(payload.get("entry"), phase="entry")
    if isinstance(payload.get("exit"), dict):
        _append(payload.get("exit"), phase="exit")
    for phase_name in ("entries", "exits", "nodes", "steps"):
        for index, item in enumerate(list(payload.get(phase_name) or [])):
            resolved_phase = "entry" if phase_name == "entries" else "exit" if phase_name == "exits" else phase_name
            _append(item, phase=resolved_phase, index=index)
    if not nodes and payload:
        _append(payload, phase="node")
    return nodes


def _claim_ids_from_prediction_contract(prediction_contract: dict[str, Any]) -> list[str]:
    claim_ids: list[str] = []
    for item in list(dict(prediction_contract or {}).get("claims") or []):
        if not isinstance(item, dict):
            continue
        claim_id = str(item.get("claim_id") or item.get("id") or "").strip()
        if claim_id:
            claim_ids.append(claim_id)
    return list(dict.fromkeys(claim_ids))


def _trade_step_ids_from_trade_plan_to_dsl_map(trade_plan_to_dsl_map: dict[str, Any]) -> list[str]:
    step_ids: list[str] = []
    for key in (
        "trade_step_to_dsl_sections",
        "trade_step_to_claim_ids",
    ):
        payload = dict(trade_plan_to_dsl_map.get(key) or {})
        step_ids.extend(str(item).strip() for item in payload.keys() if str(item).strip())
    return list(dict.fromkeys(step_ids))


def _claim_ids_from_claim_map(claim_to_trade_plan_map: dict[str, Any]) -> list[str]:
    payload = dict(claim_to_trade_plan_map.get("claim_to_trade_step_ids") or {})
    return list(dict.fromkeys(str(item).strip() for item in payload.keys() if str(item).strip()))


def _enrich_runtime_playbook_provenance(
    runtime_playbook: dict[str, Any],
    *,
    strategy_type: str,
    prediction_contract: dict[str, Any],
    trade_plan: dict[str, Any],
    claim_to_trade_plan_map: dict[str, Any],
    trade_plan_to_dsl_map: dict[str, Any],
    source_priority: dict[str, str],
    runtime_playbook_source: str,
) -> dict[str, Any]:
    playbook = dict(runtime_playbook or {})
    existing_provenance = dict(playbook.get("_provenance") or {})
    trade_plan_nodes = _trade_plan_nodes_for_provenance(trade_plan)
    derived_claim_ids = list(
        dict.fromkeys(
            [
                *_claim_ids_from_prediction_contract(prediction_contract),
                *_claim_ids_from_claim_map(claim_to_trade_plan_map),
                *[
                    str(claim_id).strip()
                    for node in trade_plan_nodes
                    for claim_id in list(node.get("claim_ids") or [])
                    if str(claim_id).strip()
                ],
            ]
        )
    )
    derived_trade_step_ids = list(
        dict.fromkeys(
            [
                *[
                    str(node.get("node_id") or "").strip()
                    for node in trade_plan_nodes
                    if str(node.get("node_id") or "").strip()
                ],
                *_trade_step_ids_from_trade_plan_to_dsl_map(trade_plan_to_dsl_map),
            ]
        )
    )
    source_claim_ids = list(
        dict.fromkeys(
            [
                *[
                    str(item).strip()
                    for item in list(playbook.get("source_claim_ids") or [])
                    if str(item).strip()
                ],
                *[
                    str(item).strip()
                    for item in list(existing_provenance.get("source_claim_ids") or [])
                    if str(item).strip()
                ],
                *derived_claim_ids,
            ]
        )
    )
    source_trade_step_ids = list(
        dict.fromkeys(
            [
                *[
                    str(item).strip()
                    for item in list(playbook.get("source_trade_step_ids") or [])
                    if str(item).strip()
                ],
                *[
                    str(item).strip()
                    for item in list(existing_provenance.get("source_trade_step_ids") or [])
                    if str(item).strip()
                ],
                *derived_trade_step_ids,
            ]
        )
    )
    derived_from_defaults = bool(
        existing_provenance.get("derived_from_defaults")
        if existing_provenance.get("derived_from_defaults") is not None
        else playbook.get("derived_from_defaults")
        if playbook.get("derived_from_defaults") is not None
        else runtime_playbook_source == "default"
    )
    family_label = _runtime_playbook_family(strategy_type)
    derivation_labels = list(
        dict.fromkeys(
            [
                *[
                    str(item).strip()
                    for item in list(playbook.get("derivation_labels") or [])
                    if str(item).strip()
                ],
                *[
                    str(item).strip()
                    for item in list(existing_provenance.get("derivation_labels") or [])
                    if str(item).strip()
                ],
                "default_runtime_playbook" if derived_from_defaults else "runtime_playbook_provided",
                "trade_plan_driven" if source_trade_step_ids else "trade_plan_missing",
                "claim_linked" if source_claim_ids else "claim_mapping_missing",
                f"family_template:{family_label}",
            ]
        )
    )
    provenance = {
        **existing_provenance,
        "source_claim_ids": source_claim_ids,
        "source_trade_step_ids": source_trade_step_ids,
        "derived_from_defaults": derived_from_defaults,
        "derivation_labels": derivation_labels,
        "source_priority": dict(source_priority),
        "runtime_playbook_source": runtime_playbook_source,
    }
    return {
        **playbook,
        "source_claim_ids": source_claim_ids,
        "source_trade_step_ids": source_trade_step_ids,
        "derived_from_defaults": derived_from_defaults,
        "derivation_labels": derivation_labels,
        "_provenance": provenance,
    }


def _default_validation_profile(
    strategy_type: str,
    research_task: dict[str, Any],
    task_source: str,
) -> dict[str, Any]:
    default_focus = (
        "candidate_target_only"
        if strategy_type == "event_structure_breakout"
        else "event_target_only"
        if task_source == "event_driven"
        else "candidate_target_only" if strategy_type == "quality_factor"
        else "target_plus_representative"
    )
    validation_focus = str(
        research_task.get("validation_focus") or default_focus
    ).strip().lower()
    if strategy_type == "quality_factor" and validation_focus in {
        "candidate_target_only",
        "target_only",
        "target_plus_family_peer",
    }:
        profile = "trade_rule_validation"
    elif strategy_type in _FACTOR_VALIDATION_TYPES:
        profile = "factor_rank_validation"
    elif strategy_type == "macro_timing":
        profile = "macro_regime_validation"
    elif strategy_type == "event_structure_breakout" or task_source == "event_driven" or validation_focus in {"event_target_only", "candidate_target_only"}:
        profile = "event_trade_validation"
    else:
        profile = "trade_rule_validation"
    profile_payload = {
        "profile": profile,
        "validation_focus": validation_focus,
        "primary_validation_layer": "target" if validation_focus in {"event_target_only", "candidate_target_only", "target_only"} else "combined",
    }
    if strategy_type == "event_structure_breakout":
        profile_payload.update(
            {
                "objective_profile": "high_precision",
                "trade_density_preference": "low",
                "regime_required": True,
                "cost_robust_required": True,
                "entry_selectivity": "strict_event_breakout",
                "preferred_regime": "event_follow_through_with_structure_confirmation",
                "avoid_regime": "false_breakout_or_post_event_mean_reversion",
                "event_prefilter_required": True,
                "event_prefilter_profile": "announcement_flow_sector_v1",
                "event_prefilter_min_confirmations": 1,
            }
        )
    return profile_payload
