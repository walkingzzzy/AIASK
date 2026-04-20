

def _direction_bucket(value: Any) -> Optional[str]:
    token = _string(value).lower()
    if not token:
        return None
    if any(word in token for word in ("up", "long", "bull", "buy", "rise", "rebound")):
        return "up"
    if any(word in token for word in ("down", "short", "bear", "sell", "fall", "drop")):
        return "down"
    return None


def _condition_contains_compare_op(node: Any, ops: set[str]) -> bool:
    if node in _EMPTY_VALUES:
        return False
    if isinstance(node, Mapping):
        payload = dict(node)
        op = _string(payload.get("op")).lower()
        if op in ops:
            return True
        if "all" in payload:
            return any(_condition_contains_compare_op(item, ops) for item in _as_list(payload.get("all")))
        if "any" in payload:
            return any(_condition_contains_compare_op(item, ops) for item in _as_list(payload.get("any")))
        if "not" in payload:
            return _condition_contains_compare_op(payload.get("not"), ops)
        return any(_condition_contains_compare_op(item, ops) for item in payload.values())
    if isinstance(node, list):
        return any(_condition_contains_compare_op(item, ops) for item in node)
    return False


def _has_unquantified_regime_language(text: str) -> bool:
    normalized = _string(text).lower()
    if not normalized:
        return False
    if any(ch.isdigit() for ch in normalized):
        return False
    if any(symbol in normalized for symbol in (">", "<", ">=", "<=", "%")):
        return False
    return any(token in normalized for token in _AMBIGUOUS_REGIME_TOKENS)


def _audit_lagging_entry_without_lead_evidence(
    *,
    strategy_type: Optional[str],
    claims: list[dict[str, Any]],
    evidences: list[dict[str, Any]],
    trade_plan: Mapping[str, Any],
    dsl: Mapping[str, Any],
) -> dict[str, Any]:
    if strategy_type not in _TREND_EXECUTABLE_DSL_TYPES:
        return {
            "applies": False,
            "status": "not_applicable",
            "lagging_entry_detected": False,
            "lead_evidence_count": 0,
            "reasons": [],
        }
    entry_node = _as_dict(trade_plan.get("entry"))
    entry_text = " ".join(
        [
            _string(entry_node.get("summary")),
            _string(entry_node.get("entry_bias")),
            _string(entry_node.get("setup")),
            _string(entry_node.get("trigger")),
            _string(entry_node.get("condition")),
            _string(trade_plan.get("entry_bias")),
        ]
    ).lower()
    lagging_entry_detected = _condition_contains_compare_op(
        dsl.get("entry"),
        {"cross_above", "cross_below"},
    ) or any(
        token in entry_text
        for token in ("golden cross", "death cross", "cross", "金叉", "死叉", "confirmation", "确认", "上穿", "下穿")
    )

    lead_evidence_count = 0
    for evidence in evidences:
        source_type = _normalized_source_type(evidence.get("source_type"))
        if source_type not in {"price_action", "technical", "volume", "kline"}:
            lead_evidence_count += 1
            continue
        if _string(evidence.get("event_type")) or _string(evidence.get("doc_uid")) or _string(evidence.get("headline_label_id")):
            lead_evidence_count += 1
            continue
        support_metric = _string(evidence.get("support_metric")).lower()
        if support_metric and support_metric not in {"price", "close", "volume"}:
            lead_evidence_count += 1

    claim_failure_condition_count = sum(1 for claim in claims if _string(claim.get("failure_condition")))
    reasons: list[str] = []
    if lagging_entry_detected and lead_evidence_count <= 0:
        reasons.append("lagging_entry_has_no_lead_evidence")
    if lagging_entry_detected and claim_failure_condition_count <= 0:
        reasons.append("lagging_entry_claim_missing_failure_condition")
    status = "failed" if reasons else "passed"
    return {
        "applies": True,
        "status": status,
        "lagging_entry_detected": lagging_entry_detected,
        "lead_evidence_count": lead_evidence_count,
        "claim_failure_condition_count": claim_failure_condition_count,
        "reasons": reasons,
    }


def _audit_temporal_coherence(
    *,
    claims: list[dict[str, Any]],
    holding_horizon: Mapping[str, Any],
    risk_rules: Mapping[str, Any],
    rebalance_rule: Mapping[str, Any],
    trade_plan: Mapping[str, Any],
) -> dict[str, Any]:
    expected_horizons = [
        _safe_int(item.get("expected_horizon"))
        for item in claims
        if _safe_int(item.get("expected_horizon")) > 0
    ]
    max_claim_horizon = max(expected_horizons, default=0)
    min_claim_horizon = min(expected_horizons, default=0) if expected_horizons else 0
    max_holding_days = max(
        _safe_int(holding_horizon.get("max_days")),
        _safe_int(risk_rules.get("max_holding_days")),
        0,
    )
    rebalance_interval_days = _safe_int(
        rebalance_rule.get("frequency_days")
        or rebalance_rule.get("rebalance_interval_days")
    )
    signal_validity_days = _safe_int(
        _as_dict(trade_plan.get("entry")).get("signal_validity_days")
        or trade_plan.get("signal_validity_days")
    )

    reasons: list[str] = []
    if max_claim_horizon > 0 and max_holding_days > 0 and max_claim_horizon > max_holding_days:
        reasons.append("claim_expected_horizon_exceeds_holding_horizon")
    if min_claim_horizon > 0 and rebalance_interval_days > 0 and rebalance_interval_days > max(min_claim_horizon, max_holding_days or min_claim_horizon):
        reasons.append("rebalance_interval_exceeds_claim_horizon")
    if signal_validity_days > 0 and max_holding_days > 0 and signal_validity_days > max_holding_days:
        reasons.append("signal_validity_exceeds_holding_horizon")

    return {
        "status": "failed" if reasons else "passed",
        "reasons": reasons,
        "max_claim_horizon": max_claim_horizon or None,
        "min_claim_horizon": min_claim_horizon or None,
        "max_holding_days": max_holding_days or None,
        "rebalance_interval_days": rebalance_interval_days or None,
        "signal_validity_days": signal_validity_days or None,
    }


def _audit_ambiguous_regime_condition(
    *,
    market_regime_assumption: Mapping[str, Any],
    regime_filter_contract: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _as_dict(market_regime_assumption)
    quantified_filters = _as_list(
        regime_filter_contract.get("filters")
        or regime_filter_contract.get("quantified_filters")
        or payload.get("quantified_filters")
        or payload.get("conditions")
    )
    ambiguous_fields: list[str] = []
    for field_name in ("summary", "preferred_regime", "avoid_regime", "regime_note", "avoid_note"):
        if _has_unquantified_regime_language(_string(payload.get(field_name))):
            ambiguous_fields.append(field_name)
    reasons: list[str] = []
    if ambiguous_fields and not quantified_filters:
        reasons.append("ambiguous_regime_condition_not_allowed")
    return {
        "status": "failed" if reasons else "passed",
        "ambiguous_fields": ambiguous_fields,
        "quantified_filter_count": len(quantified_filters),
        "reasons": reasons,
    }


def audit_candidate_semantic_contract(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    strategy_type = _normalized_strategy_type(payload)
    evidence_chain = _as_dict(_candidate_value(payload, "evidence_chain"))
    prediction_contract = _as_dict(_candidate_value(payload, "prediction_contract"))
    confidence_contract = _as_dict(_candidate_value(payload, "confidence_contract"))
    trade_plan = _as_dict(_candidate_value(payload, "trade_plan"))
    dsl = _as_dict(_candidate_value(payload, "dsl"))
    holding_horizon = _as_dict(_candidate_value(payload, "holding_horizon"))
    risk_rules = _as_dict(_candidate_value(payload, "risk_rules"))
    rebalance_rule = _as_dict(_candidate_value(payload, "rebalance_rule"))
    market_regime_assumption = _as_dict(_candidate_value(payload, "market_regime_assumption"))
    regime_filter_contract = _as_dict(_candidate_value(payload, "regime_filter_contract"))
    research_task = _as_dict(_candidate_value(payload, "research_task"))
    event_context = _as_dict(_candidate_value(payload, "event_context"))
    dsl_support_audit = _as_dict(
        _candidate_value(payload, "dsl_support_audit")
    ) or inspect_strategy_dsl_support(dsl)

    evidences = _normalize_evidences(evidence_chain)
    evidence_by_id = {item["evidence_id"]: item for item in evidences}
    claims = _normalize_claims(prediction_contract)
    trade_plan_nodes = _normalized_trade_plan_nodes(trade_plan)
    contract_conflict_resolution_rule = _normalize_conflict_resolution_rule(
        prediction_contract.get("conflict_resolution_rule")
        or confidence_contract.get("conflict_resolution_rule")
    )

    using_new_contract = bool(prediction_contract)
    legacy_semantic_contract = not using_new_contract
    event_driven_strategy = (
        _string(research_task.get("task_source")).lower() == "event_driven"
        or bool(research_task.get("event_id"))
        or bool(event_context)
    )
    claim_missing_evidence_ids = 0
    claim_missing_evidence_refs = 0
    mapped_claims = 0
    contradiction_count = 0
    conflicting_claim_count = 0
    conflict_resolution_rule_missing_count = 0
    proxy_claim_count = 0
    proxy_only_event_claim_count = 0
    referenced_evidence_count = 0
    trade_plan_missing_claim_ids = 0
    trade_plan_missing_evidence_refs = 0

    for claim in claims:
        evidence_ids = list(claim.get("evidence_ids") or [])
        if not evidence_ids:
            claim_missing_evidence_ids += 1
            continue
        mapped_claims += 1
        referenced_evidence_count += len(evidence_ids)
        evidence_refs = [evidence_by_id.get(evidence_id) for evidence_id in evidence_ids]
        if any(item is None for item in evidence_refs):
            claim_missing_evidence_refs += sum(1 for item in evidence_refs if item is None)
        expected_direction = _direction_bucket(claim.get("expected_move"))
        claim_conflict_resolution_rule = (
            claim.get("conflict_resolution_rule") or contract_conflict_resolution_rule
        )
        resolved_evidence_refs = [item for item in evidence_refs if item is not None]
        if resolved_evidence_refs and all(bool(_as_dict(item).get("proxy_only")) for item in resolved_evidence_refs):
            proxy_claim_count += 1
        if (
            event_driven_strategy
            and resolved_evidence_refs
            and all(bool(_as_dict(item).get("proxy_only")) for item in resolved_evidence_refs)
            and all(
                _normalized_source_type(_as_dict(item).get("source_type")) in {"news", "sentiment"}
                for item in resolved_evidence_refs
            )
        ):
            proxy_only_event_claim_count += 1

        direction_buckets = [
            _direction_bucket(_as_dict(evidence).get("direction"))
            for evidence in resolved_evidence_refs
        ]
        same_direction_count = 0
        opposite_direction_count = 0
        non_null_direction_buckets = [direction for direction in direction_buckets if direction]
        if expected_direction:
            same_direction_count = sum(1 for direction in non_null_direction_buckets if direction == expected_direction)
            opposite_direction_count = sum(1 for direction in non_null_direction_buckets if direction != expected_direction)
            if same_direction_count > 0 and opposite_direction_count > 0:
                conflicting_claim_count += 1
                if not claim_conflict_resolution_rule:
                    conflict_resolution_rule_missing_count += 1
            elif opposite_direction_count > 0 and same_direction_count <= 0:
                contradiction_count += 1
        elif len(set(non_null_direction_buckets)) > 1:
            conflicting_claim_count += 1
            if not claim_conflict_resolution_rule:
                conflict_resolution_rule_missing_count += 1

    claim_id_set = {item.get("claim_id") for item in claims if item.get("claim_id")}
    for node in trade_plan_nodes:
        claim_ids = [claim_id for claim_id in list(node.get("claim_ids") or []) if claim_id]
        evidence_ids = [evidence_id for evidence_id in list(node.get("evidence_ids") or []) if evidence_id]
        if using_new_contract and not claim_ids:
            trade_plan_missing_claim_ids += 1
        if claim_ids and any(claim_id not in claim_id_set for claim_id in claim_ids):
            trade_plan_missing_claim_ids += sum(1 for claim_id in claim_ids if claim_id not in claim_id_set)
        if evidence_ids and any(evidence_id not in evidence_by_id for evidence_id in evidence_ids):
            trade_plan_missing_evidence_refs += sum(1 for evidence_id in evidence_ids if evidence_id not in evidence_by_id)

    dsl_entry_refs = _collect_trade_plan_node_refs(dsl.get("entry"))
    dsl_exit_refs = _collect_trade_plan_node_refs(dsl.get("exit"))
    available_entry_nodes = {
        node.get("node_id")
        for node in trade_plan_nodes
        if str(node.get("phase") or "").lower() in {"entry", "entries"}
    }
    available_exit_nodes = {
        node.get("node_id")
        for node in trade_plan_nodes
        if str(node.get("phase") or "").lower() in {"exit", "exits"}
    }
    dsl_entry_mapped = bool(dsl.get("entry")) and (
        bool(available_entry_nodes and set(dsl_entry_refs).intersection(available_entry_nodes))
        or bool(_as_dict(trade_plan.get("entry")))
    )
    dsl_exit_mapped = bool(dsl.get("exit")) and (
        bool(available_exit_nodes and set(dsl_exit_refs).intersection(available_exit_nodes))
        or bool(_as_dict(trade_plan.get("exit")))
    )

    claim_alignment_ratio = round(mapped_claims / max(1, len(claims)), 4) if claims else 0.0
    trade_plan_claim_ratio = round(
        sum(1 for node in trade_plan_nodes if node.get("claim_ids")) / max(1, len(trade_plan_nodes)),
        4,
    ) if trade_plan_nodes else 0.0
    dsl_mapping_ratio = round(
        (
            (1.0 if dsl_entry_mapped else 0.0)
            + (1.0 if dsl_exit_mapped else 0.0)
        ) / 2.0,
        4,
    ) if dsl.get("entry") or dsl.get("exit") else 0.0
    proxy_dependency_score = round(proxy_claim_count / max(1, mapped_claims), 4) if mapped_claims else 0.0
    evidence_alignment_score = round(
        (claim_alignment_ratio + trade_plan_claim_ratio + dsl_mapping_ratio) / 3.0,
        4,
    ) if using_new_contract else 0.0
    semantic_integrity_score = round(
        max(0.0, evidence_alignment_score - min(0.5, contradiction_count * 0.25)),
        4,
    ) if using_new_contract else 0.0
    lagging_entry_audit = _audit_lagging_entry_without_lead_evidence(
        strategy_type=strategy_type,
        claims=claims,
        evidences=evidences,
        trade_plan=trade_plan,
        dsl=dsl,
    )
    temporal_coherence_audit = _audit_temporal_coherence(
        claims=claims,
        holding_horizon=holding_horizon,
        risk_rules=risk_rules,
        rebalance_rule=rebalance_rule,
        trade_plan=trade_plan,
    )
    ambiguous_regime_condition_audit = _audit_ambiguous_regime_condition(
        market_regime_assumption=market_regime_assumption,
        regime_filter_contract=regime_filter_contract,
    )

    hard_fail_reasons: list[str] = []
    if using_new_contract and claim_missing_evidence_ids > 0:
        hard_fail_reasons.append("prediction_contract_claim_missing_evidence_ids")
    if using_new_contract and conflict_resolution_rule_missing_count > 0:
        hard_fail_reasons.append("prediction_contract_conflict_resolution_rule_missing")
    if using_new_contract and trade_plan_missing_claim_ids > 0:
        hard_fail_reasons.append("trade_plan_node_missing_claim_ids")
    if using_new_contract and not dsl_entry_mapped:
        hard_fail_reasons.append("dsl_entry_not_mapped_to_trade_plan")
    if using_new_contract and not dsl_exit_mapped:
        hard_fail_reasons.append("dsl_exit_not_mapped_to_trade_plan")
    if using_new_contract and contradiction_count > 0:
        hard_fail_reasons.append("semantic_contract_contradiction_detected")
    if using_new_contract and proxy_only_event_claim_count > 0:
        hard_fail_reasons.append("proxy_only_event_evidence_not_allowed")
    if using_new_contract and _safe_int(dsl_support_audit.get("unsupported_rule_count"), 0) > 0:
        hard_fail_reasons.append("dsl_contains_unsupported_rules")
    if using_new_contract and lagging_entry_audit.get("status") == "failed":
        hard_fail_reasons.append("lagging_entry_without_lead_evidence")
    if using_new_contract and temporal_coherence_audit.get("status") == "failed":
        hard_fail_reasons.append("temporal_coherence_audit_failed")
    if using_new_contract and ambiguous_regime_condition_audit.get("status") == "failed":
        hard_fail_reasons.append("ambiguous_regime_condition_not_allowed")

    alignment_status = "legacy" if legacy_semantic_contract else "aligned"
    if using_new_contract and hard_fail_reasons:
        alignment_status = "failed"
    elif using_new_contract and evidence_alignment_score < 0.75:
        alignment_status = "partial"

    return {
        "using_new_contract": using_new_contract,
        "legacy_semantic_contract": legacy_semantic_contract,
        "evidence_count": len(evidences),
        "claim_count": len(claims),
        "trade_plan_node_count": len(trade_plan_nodes),
        "claim_alignment_ratio": claim_alignment_ratio,
        "trade_plan_claim_ratio": trade_plan_claim_ratio,
        "dsl_mapping_ratio": dsl_mapping_ratio,
        "evidence_alignment_score": evidence_alignment_score,
        "semantic_integrity_score": semantic_integrity_score,
        "proxy_dependency_score": proxy_dependency_score,
        "contradiction_count": contradiction_count,
        "conflicting_claim_count": conflicting_claim_count,
        "conflict_resolution_rule_missing_count": conflict_resolution_rule_missing_count,
        "unsupported_rule_count": _safe_int(dsl_support_audit.get("unsupported_rule_count"), 0),
        "dsl_support_audit": dsl_support_audit,
        "proxy_only_event_claim_count": proxy_only_event_claim_count,
        "event_driven_strategy": event_driven_strategy,
        "claim_missing_evidence_ids": claim_missing_evidence_ids,
        "claim_missing_evidence_refs": claim_missing_evidence_refs,
        "trade_plan_missing_claim_ids": trade_plan_missing_claim_ids,
        "trade_plan_missing_evidence_refs": trade_plan_missing_evidence_refs,
        "dsl_entry_mapped": dsl_entry_mapped,
        "dsl_exit_mapped": dsl_exit_mapped,
        "referenced_evidence_count": referenced_evidence_count,
        "evidence_alignment_status": alignment_status,
        "lagging_entry_without_lead_evidence": lagging_entry_audit,
        "temporal_coherence_audit": temporal_coherence_audit,
        "ambiguous_regime_condition_audit": ambiguous_regime_condition_audit,
        "hard_fail_reasons": hard_fail_reasons,
    }
