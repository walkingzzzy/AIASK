

def synthesize_confidence_contract(
    candidate: Optional[Mapping[str, Any]],
    *,
    signal_quality: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    payload = dict(candidate or {})
    collected = _collect_probability_payloads(payload)
    existing_contract = dict(collected.get("existing_contract") or {})
    prediction_quality_payload = dict(collected.get("prediction_quality") or {})
    prediction_interval_payload = dict(collected.get("prediction_interval") or {})
    raw_probs = list(collected.get("raw_probs") or [])
    calibrated_probs = list(collected.get("calibrated_probs") or [])
    support_samples = max(
        [0, *[int(value) for value in list(collected.get("support_samples") or []) if int(value) > 0]],
        default=0,
    )
    if support_samples <= 0:
        support_samples = _safe_int(dict(signal_quality or {}).get("primary_effective_n"), 0)

    raw_probability = (
        round(sum(raw_probs) / len(raw_probs), 6)
        if raw_probs
        else _safe_float(
            _first_non_empty(
                prediction_quality_payload.get("raw_probability"),
                existing_contract.get("raw_probability"),
                existing_contract.get("probability"),
            )
        )
    )
    calibrated_probability = (
        round(sum(calibrated_probs) / len(calibrated_probs), 6)
        if calibrated_probs
        else _safe_float(
            _first_non_empty(
                prediction_quality_payload.get("calibrated_probability"),
                existing_contract.get("calibrated_probability"),
            )
        )
    )
    calibration_method = _string(
        _first_non_empty(
            prediction_quality_payload.get("calibration_method"),
            existing_contract.get("calibration_method"),
        )
    ) or ("none" if calibrated_probability is None else "system_blend")
    ece = _safe_float(collected.get("ece"))
    brier_score = _safe_float(collected.get("brier_score"))
    calibration_gap = _safe_float(collected.get("calibration_gap"))
    quality = _string(
        _first_non_empty(
            prediction_quality_payload.get("quality"),
            existing_contract.get("quality"),
        )
    ).lower() or _quality_band(
        support_samples=support_samples,
        brier_score=brier_score,
        ece=ece,
    )
    lower = _safe_float(
        _first_non_empty(
            prediction_interval_payload.get("lower"),
            existing_contract.get("lower"),
        )
    )
    upper = _safe_float(
        _first_non_empty(
            prediction_interval_payload.get("upper"),
            existing_contract.get("upper"),
        )
    )
    coverage_target = _safe_float(
        _first_non_empty(
            prediction_interval_payload.get("coverage_target"),
            existing_contract.get("coverage_target"),
        )
    )
    observed_coverage = _safe_float(
        _first_non_empty(
            prediction_interval_payload.get("observed_coverage"),
            existing_contract.get("observed_coverage"),
        )
    )
    coverage_proxy = _safe_float(
        _first_non_empty(
            prediction_interval_payload.get("coverage_proxy"),
            existing_contract.get("coverage_proxy"),
        )
    )
    coverage_gap = _safe_float(
        _first_non_empty(
            prediction_interval_payload.get("coverage_gap"),
            existing_contract.get("coverage_gap"),
        )
    )
    interval_method = _string(
        _first_non_empty(
            prediction_interval_payload.get("method"),
            existing_contract.get("prediction_interval_method"),
            existing_contract.get("interval_method"),
        )
    ) or "system_blend"

    warnings = [
        _string(item)
        for item in list(existing_contract.get("warnings") or [])
        if _string(item)
    ]
    if support_samples <= 0:
        warnings.append("缺少稳定 support_samples，confidence_contract 仅作诊断用途")
    if calibrated_probability is None:
        warnings.append("缺少 calibrated_probability，当前以原始置信度近似")
    if calibration_method in {"none", "raw"}:
        warnings.append("概率未经显式校准，可能存在系统性偏差")
    warnings = list(dict.fromkeys(warnings))

    return {
        "contract_version": _CONFIDENCE_CONTRACT_VERSION,
        "producer": "system",
        "prediction_quality": {
            "raw_probability": raw_probability,
            "calibrated_probability": calibrated_probability,
            "support_samples": support_samples,
            "calibration_method": calibration_method,
            "ece": ece,
            "brier_score": brier_score,
            "calibration_gap": calibration_gap,
            "quality": quality,
            "contract_version": _CONFIDENCE_CONTRACT_VERSION,
            "contract_version_stable": True,
        },
        "prediction_interval": {
            "lower": lower,
            "upper": upper,
            "coverage_target": coverage_target,
            "observed_coverage": observed_coverage,
            "coverage_proxy": coverage_proxy,
            "coverage_gap": coverage_gap,
            "method": interval_method,
        },
        "warnings": warnings,
        "source_inputs": {
            "llm": existing_contract,
            "prediction_contract": {
                "claim_count": len(list(collected.get("claims") or [])),
            },
            "evidence_chain": {
                "evidence_count": len(list(collected.get("evidences") or [])),
            },
            "signal_quality": {
                "primary_effective_n": _safe_int(dict(signal_quality or {}).get("primary_effective_n"), 0),
            },
        },
    }


def normalize_semantic_contract_fields(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    evidence_chain = _as_dict(_candidate_value(payload, "evidence_chain"))
    prediction_contract = _as_dict(_candidate_value(payload, "prediction_contract"))
    confidence_contract = synthesize_confidence_contract(payload)
    evidence_alignment_audit = _as_dict(_candidate_value(payload, "evidence_alignment_audit"))
    dsl_support_audit = _as_dict(_candidate_value(payload, "dsl_support_audit"))
    legacy_semantic_contract = _candidate_value(payload, "legacy_semantic_contract")
    contradiction_count = _candidate_value(payload, "contradiction_count")
    proxy_dependency_score = _candidate_value(payload, "proxy_dependency_score")
    return {
        "evidence_chain": evidence_chain,
        "prediction_contract": prediction_contract,
        "confidence_contract": confidence_contract,
        "evidence_alignment_audit": evidence_alignment_audit,
        "dsl_support_audit": dsl_support_audit,
        "legacy_semantic_contract": bool(legacy_semantic_contract) if legacy_semantic_contract is not None else None,
        "contradiction_count": (
            _safe_int(contradiction_count)
            if contradiction_count is not None
            else None
        ),
        "proxy_dependency_score": (
            round(_safe_float(proxy_dependency_score), 4)
            if proxy_dependency_score is not None
            else None
        ),
    }


def _contract_target_symbols(candidate: Mapping[str, Any]) -> list[str]:
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    research_task = _as_dict(_candidate_value(payload, "research_task"))
    sources = (
        payload.get("target_symbols"),
        params.get("target_symbols"),
        _as_dict(payload.get("stock_pool")).get("codes"),
        _as_dict(params.get("stock_pool")).get("codes"),
        research_task.get("target_symbols"),
    )
    ordered: list[str] = []
    seen: set[str] = set()
    for source in sources:
        values = [source] if isinstance(source, str) else _as_list(source)
        for item in values:
            token = _string(item)
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
            if len(ordered) >= 12:
                return ordered
    return ordered


def _default_expected_move(strategy_type: Optional[str]) -> str:
    normalized = _string(strategy_type).lower()
    if normalized in {"rsi", "gap_fill", "mean_reversion_short", "value_factor"}:
        return "up"
    if normalized in {"ma_cross", "momentum", "volatility_breakout", "event_structure_breakout"}:
        return "up"
    return "up"


def _default_horizon_days(candidate: Mapping[str, Any]) -> int:
    holding_horizon = _as_dict(_candidate_value(candidate, "holding_horizon"))
    risk_rules = _as_dict(_candidate_value(candidate, "risk_rules"))
    trade_plan = _as_dict(_candidate_value(candidate, "trade_plan"))
    return max(
        1,
        _safe_int(
            _first_non_empty(
                holding_horizon.get("max_days"),
                holding_horizon.get("alpha_half_life"),
                risk_rules.get("max_holding_days"),
                trade_plan.get("max_holding_days"),
            ),
            20,
        ),
    )


def _ensure_trade_plan_nodes(candidate: Mapping[str, Any], strategy_type: str) -> dict[str, Any]:
    trade_plan = _as_dict(_candidate_value(candidate, "trade_plan"))
    if not trade_plan:
        trade_plan = {
            "entry_bias": "signal_confirmed",
            "exit_bias": "signal_invalidated_or_time_stop",
        }

    entry = _as_dict(trade_plan.get("entry"))
    exit_payload = _as_dict(trade_plan.get("exit"))
    if not entry:
        entry = {
            "summary": _string(trade_plan.get("entry_bias")) or f"{strategy_type} entry signal confirmed",
        }
    if not exit_payload:
        exit_payload = {
            "summary": _string(trade_plan.get("exit_bias")) or f"{strategy_type} exit signal or risk stop",
        }
    entry.setdefault("node_id", "entry_step_1")
    entry.setdefault("phase", "entry")
    entry.setdefault("claim_ids", ["claim_entry"])
    entry.setdefault("evidence_ids", ["ev_entry_signal"])
    exit_payload.setdefault("node_id", "exit_step_1")
    exit_payload.setdefault("phase", "exit")
    exit_payload.setdefault("claim_ids", ["claim_exit"])
    exit_payload.setdefault("evidence_ids", ["ev_exit_risk"])
    trade_plan["entry"] = entry
    trade_plan["exit"] = exit_payload
    trade_plan.setdefault("semantic_generation_mode", "factory_semantic_contract_backfill")
    trade_plan.setdefault("strategy_type", strategy_type)
    return trade_plan


def _ensure_dsl_mapping(candidate: Mapping[str, Any], trade_plan: Mapping[str, Any]) -> dict[str, Any]:
    dsl = _as_dict(_candidate_value(candidate, "dsl"))
    if not dsl:
        return {}
    payload = dict(dsl)
    entry = _as_dict(payload.get("entry"))
    exit_payload = _as_dict(payload.get("exit"))
    entry_node_id = _string(_as_dict(trade_plan.get("entry")).get("node_id")) or "entry_step_1"
    exit_node_id = _string(_as_dict(trade_plan.get("exit")).get("node_id")) or "exit_step_1"
    if entry:
        entry.setdefault("trade_plan_node_id", entry_node_id)
        payload["entry"] = entry
    if exit_payload:
        exit_payload.setdefault("trade_plan_node_id", exit_node_id)
        payload["exit"] = exit_payload
    return payload


def _build_default_evidence_chain(
    candidate: Mapping[str, Any],
    *,
    strategy_type: str,
    target_symbols: list[str],
    horizon_days: int,
) -> dict[str, Any]:
    name = _string(_candidate_value(candidate, "name") or dict(candidate).get("name")) or strategy_type
    hypothesis = _string(_candidate_value(candidate, "hypothesis") or dict(candidate).get("hypothesis"))
    description = _string(dict(candidate).get("description"))
    params = _as_dict(dict(candidate).get("params"))
    generation_reason = _as_dict(dict(candidate).get("generation_reason") or params.get("generation_reason"))
    source = _string(
        generation_reason.get("source")
        or dict(candidate).get("generator_type")
        or params.get("generator_type")
        or "strategy_factory"
    ).lower() or "strategy_factory"
    thesis = hypothesis or description or f"{name} candidate generated by Strategy Factory"
    return {
        "contract_version": "strategy_factory.semantic_contract.v1",
        "producer": "strategy_factory",
        "generation_mode": "factory_semantic_contract_backfill",
        "thesis": thesis,
        "evidences": [
            {
                "evidence_id": "ev_entry_signal",
                "source_type": "strategy_logic",
                "direction": "up",
                "summary": thesis,
                "proxy_only": False,
                "target_symbols": list(target_symbols),
                "horizon_days": int(horizon_days),
                "claim_ids": ["claim_entry"],
                "support_metric": {
                    "strategy_type": strategy_type,
                    "source": source,
                },
            },
            {
                "evidence_id": "ev_exit_risk",
                "source_type": "risk_contract",
                "direction": "down",
                "summary": "Exit when the entry thesis is invalidated by risk rules or signal decay.",
                "proxy_only": False,
                "target_symbols": list(target_symbols),
                "horizon_days": max(1, int(horizon_days // 2)),
                "claim_ids": ["claim_exit"],
            },
        ],
    }


def _build_default_prediction_contract(
    candidate: Mapping[str, Any],
    *,
    strategy_type: str,
    target_symbols: list[str],
    horizon_days: int,
) -> dict[str, Any]:
    name = _string(_candidate_value(candidate, "name") or dict(candidate).get("name")) or strategy_type
    thesis = _string(_candidate_value(candidate, "hypothesis") or dict(candidate).get("description")) or name
    return {
        "contract_version": "strategy_factory.prediction_contract.v1",
        "producer": "strategy_factory",
        "generation_mode": "factory_semantic_contract_backfill",
        "primary_horizon_days": int(horizon_days),
        "target": "forward_return_positive",
        "conflict_resolution_rule": {
            "policy": "risk_first_when_exit_evidence_present",
            "tie_breaker": "exit_claim_over_entry_claim",
        },
        "claims": [
            {
                "claim_id": "claim_entry",
                "claim_type": "entry",
                "summary": thesis,
                "expected_move": _default_expected_move(strategy_type),
                "expected_horizon": int(horizon_days),
                "evidence_ids": ["ev_entry_signal"],
                "failure_condition": "entry thesis invalidated by exit signal, stop loss, or time stop",
                "conflict_resolution_rule": {"policy": "risk_first_when_exit_evidence_present"},
                "target_symbols": list(target_symbols),
            },
            {
                "claim_id": "claim_exit",
                "claim_type": "exit",
                "summary": "Risk or signal invalidation exits the position.",
                "expected_move": "down",
                "expected_horizon": max(1, int(horizon_days // 2)),
                "evidence_ids": ["ev_exit_risk"],
                "failure_condition": "entry thesis restored",
                "conflict_resolution_rule": {"policy": "risk_first"},
                "target_symbols": list(target_symbols),
            },
        ],
    }


def _attach_semantic_fields(payload: dict[str, Any], fields: Mapping[str, Any]) -> dict[str, Any]:
    params = _as_dict(payload.get("params"))
    for key, value in dict(fields or {}).items():
        if value in _EMPTY_VALUES:
            continue
        payload[key] = value
        params[key] = value
    payload["params"] = params
    return payload


def ensure_candidate_semantic_contract(candidate: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Return a candidate with complete evidence, prediction, and confidence contracts.

    This is a deterministic factory-side backfill. It preserves explicit LLM or
    DSL contracts, and only fills the missing pieces needed for G3 to audit the
    candidate instead of treating absent contracts as absent evidence.
    """
    payload = dict(candidate or {})
    params = _as_dict(payload.get("params"))
    strategy_type = _normalized_strategy_type(payload) or "strategy"
    target_symbols = _contract_target_symbols(payload)
    horizon_days = _default_horizon_days(payload)

    trade_plan = _ensure_trade_plan_nodes(payload, strategy_type)
    dsl = _ensure_dsl_mapping(payload, trade_plan)
    evidence_chain = _as_dict(_candidate_value(payload, "evidence_chain"))
    prediction_contract = _as_dict(_candidate_value(payload, "prediction_contract"))
    if not evidence_chain:
        evidence_chain = _build_default_evidence_chain(
            payload,
            strategy_type=strategy_type,
            target_symbols=target_symbols,
            horizon_days=horizon_days,
        )
    if not prediction_contract:
        prediction_contract = _build_default_prediction_contract(
            payload,
            strategy_type=strategy_type,
            target_symbols=target_symbols,
            horizon_days=horizon_days,
        )
    confidence_contract = synthesize_confidence_contract(
        {
            **payload,
            "trade_plan": trade_plan,
            "dsl": dsl or _as_dict(_candidate_value(payload, "dsl")),
            "evidence_chain": evidence_chain,
            "prediction_contract": prediction_contract,
        }
    )
    claim_to_trade_plan_map = _as_dict(_candidate_value(payload, "claim_to_trade_plan_map"))
    if not claim_to_trade_plan_map:
        entry_node_id = _string(_as_dict(trade_plan.get("entry")).get("node_id")) or "entry_step_1"
        exit_node_id = _string(_as_dict(trade_plan.get("exit")).get("node_id")) or "exit_step_1"
        claim_to_trade_plan_map = {
            "claim_to_trade_step_ids": {
                "claim_entry": [entry_node_id],
                "claim_exit": [exit_node_id],
            },
            "trade_step_to_claim_ids": {
                entry_node_id: ["claim_entry"],
                exit_node_id: ["claim_exit"],
            },
            "mapped_claim_count": 2,
        }

    payload = _attach_semantic_fields(
        payload,
        {
            "trade_plan": trade_plan,
            "dsl": dsl,
            "evidence_chain": evidence_chain,
            "prediction_contract": prediction_contract,
            "confidence_contract": confidence_contract,
            "claim_to_trade_plan_map": claim_to_trade_plan_map,
            "semantic_contract_backfilled": True,
        },
    )
    return payload


def _normalize_evidences(evidence_chain: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidences = []
    for item in _as_list(evidence_chain.get("evidences")):
        payload = _as_dict(item)
        evidence_id = _string(payload.get("evidence_id") or payload.get("id"))
        if not evidence_id:
            continue
        evidences.append(
            {
                **payload,
                "evidence_id": evidence_id,
                "source_type": _string(payload.get("source_type")) or None,
                "direction": _string(payload.get("direction")).lower() or None,
                "horizon_days": (
                    _safe_int(payload.get("horizon_days"))
                    if payload.get("horizon_days") is not None
                    else None
                ),
                "raw_confidence": (
                    round(_safe_float(payload.get("raw_confidence")), 4)
                    if payload.get("raw_confidence") is not None
                    else None
                ),
                "calibrated_confidence": (
                    round(_safe_float(payload.get("calibrated_confidence")), 4)
                    if payload.get("calibrated_confidence") is not None
                    else None
                ),
                "proxy_only": bool(payload.get("proxy_only")),
                "event_type": _string(payload.get("event_type")) or None,
                "summary": _string(payload.get("summary")) or None,
                "doc_uid": _string(payload.get("doc_uid")) or None,
                "headline_label_id": _string(payload.get("headline_label_id")) or None,
                "freshness_ts": _coerce_iso_ts(payload.get("freshness_ts")),
                "support_metric": payload.get("support_metric"),
                "target_symbols": [
                    _string(symbol)
                    for symbol in _as_list(payload.get("target_symbols"))
                    if _string(symbol)
                ],
            }
        )
    return evidences


def inspect_strategy_dsl_support(raw_dsl: Any) -> dict[str, Any]:
    unsupported_fields: set[str] = set()
    unsupported_indicators: set[str] = set()
    unsupported_compare_ops: set[str] = set()
    unsupported_binary_ops: set[str] = set()
    malformed_node_count = 0
    fallback_node_count = 0

    def _walk_expr(node: Any) -> None:
        nonlocal malformed_node_count, fallback_node_count
        if node in _EMPTY_VALUES:
            return
        if isinstance(node, (int, float)):
            return
        if isinstance(node, str):
            token = _string(node).lower()
            if token and token not in _SUPPORTED_DSL_FIELDS:
                try:
                    float(token)
                except Exception:
                    fallback_node_count += 1
            return
        if not isinstance(node, Mapping):
            malformed_node_count += 1
            return
        payload = dict(node)
        indicator = _string(payload.get("indicator")).lower()
        if indicator:
            if indicator not in _SUPPORTED_DSL_INDICATORS:
                unsupported_indicators.add(indicator)
            field_name = _string(payload.get("field") or payload.get("column")).lower()
            if field_name and field_name not in _SUPPORTED_DSL_FIELDS:
                unsupported_fields.add(field_name)
            return
        field_name = _string(payload.get("field") or payload.get("column")).lower()
        if field_name:
            if field_name not in _SUPPORTED_DSL_FIELDS:
                unsupported_fields.add(field_name)
            return
        if "value" in payload:
            return
        binary_payload = payload.get("binary") if isinstance(payload.get("binary"), Mapping) else None
        if binary_payload is not None:
            _walk_expr(binary_payload)
            return
        op = _string(payload.get("op")).lower()
        if op and ("left" in payload or "right" in payload):
            if op not in _SUPPORTED_DSL_BINARY_OPS:
                unsupported_binary_ops.add(op)
            _walk_expr(payload.get("left"))
            _walk_expr(payload.get("right"))
            return
        shorthand_binary_keys = [
            key for key in payload.keys() if _string(key).lower() in _SUPPORTED_DSL_BINARY_OPS
        ]
        if shorthand_binary_keys:
            for key in shorthand_binary_keys:
                nested = payload.get(key)
                if isinstance(nested, (list, tuple)) and len(nested) >= 2:
                    _walk_expr(nested[0])
                    _walk_expr(nested[1])
                elif isinstance(nested, Mapping):
                    _walk_expr(dict(nested).get("left") or dict(nested).get("a"))
                    _walk_expr(dict(nested).get("right") or dict(nested).get("b"))
                else:
                    malformed_node_count += 1
            return
        shorthand_indicators = [
            key for key in payload.keys()
            if _string(key).lower() not in {"left", "right", "value", "binary", "field", "column", "window", "period"}
            and _string(key).lower() not in _SUPPORTED_DSL_COMPARE_OPS
            and _string(key).lower() not in {"all", "any", "not"}
        ]
        known_indicator_keys = [key for key in shorthand_indicators if _string(key).lower() in _SUPPORTED_DSL_INDICATORS]
        if known_indicator_keys:
            for key in known_indicator_keys:
                _walk_expr({"indicator": _string(key).lower(), **(_as_dict(payload.get(key)))})
            return
        if shorthand_indicators:
            for key in shorthand_indicators:
                unsupported_indicators.add(_string(key).lower())
            return
        fallback_node_count += 1

    def _walk_condition(node: Any) -> None:
        nonlocal malformed_node_count, fallback_node_count
        if node in _EMPTY_VALUES:
            return
        if not isinstance(node, Mapping):
            malformed_node_count += 1
            return
        payload = dict(node)
        if "all" in payload:
            for item in _as_list(payload.get("all")):
                _walk_condition(item)
            return
        if "any" in payload:
            for item in _as_list(payload.get("any")):
                _walk_condition(item)
            return
        if "not" in payload:
            _walk_condition(payload.get("not"))
            return
        op = _string(payload.get("op")).lower()
        if op:
            if op not in _SUPPORTED_DSL_COMPARE_OPS:
                unsupported_compare_ops.add(op)
            _walk_expr(payload.get("left"))
            _walk_expr(payload.get("right"))
            return
        shorthand_compare_keys = [
            key for key in payload.keys() if _string(key).lower() in _SUPPORTED_DSL_COMPARE_OPS
        ]
        if shorthand_compare_keys:
            for key in shorthand_compare_keys:
                nested = payload.get(key)
                if isinstance(nested, (list, tuple)) and len(nested) >= 2:
                    _walk_expr(nested[0])
                    _walk_expr(nested[1])
                elif isinstance(nested, Mapping):
                    nested_payload = dict(nested)
                    _walk_expr(nested_payload.get("left") or nested_payload.get("a"))
                    _walk_expr(nested_payload.get("right") or nested_payload.get("b"))
                else:
                    malformed_node_count += 1
            return
        fallback_node_count += 1

    payload = _as_dict(raw_dsl)
    entry = payload.get("entry")
    exit_payload = payload.get("exit")
    if entry in _EMPTY_VALUES:
        fallback_node_count += 1
    else:
        _walk_condition(entry)
    if exit_payload not in _EMPTY_VALUES:
        _walk_condition(exit_payload)

    unsupported_rule_count = (
        len(unsupported_fields)
        + len(unsupported_indicators)
        + len(unsupported_compare_ops)
        + len(unsupported_binary_ops)
        + malformed_node_count
        + fallback_node_count
    )
    return {
        "unsupported_rule_count": int(unsupported_rule_count),
        "unsupported_fields": sorted(unsupported_fields),
        "unsupported_indicators": sorted(unsupported_indicators),
        "unsupported_compare_ops": sorted(unsupported_compare_ops),
        "unsupported_binary_ops": sorted(unsupported_binary_ops),
        "malformed_node_count": int(malformed_node_count),
        "fallback_node_count": int(fallback_node_count),
    }


def _normalize_claims(prediction_contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for item in _as_list(prediction_contract.get("claims")):
        payload = _as_dict(item)
        claim_id = _string(payload.get("claim_id") or payload.get("id"))
        if not claim_id:
            continue
        claims.append(
            {
                **payload,
                "claim_id": claim_id,
                "evidence_ids": _dedup_strings(
                    [
                        _string(value)
                        for value in _as_list(payload.get("evidence_ids"))
                    ]
                ),
                "expected_move": _string(payload.get("expected_move")).lower() or None,
                "expected_horizon": (
                    _safe_int(payload.get("expected_horizon"))
                    if payload.get("expected_horizon") is not None
                    else None
                ),
                "conflict_resolution_rule": _normalize_conflict_resolution_rule(
                    payload.get("conflict_resolution_rule")
                ),
            }
        )
    return claims


def _normalized_trade_plan_nodes(trade_plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def _append_node(node: Mapping[str, Any], *, phase: Optional[str] = None, index: int = 0) -> None:
        payload = _as_dict(node)
        if not payload:
            return
        node_id = _string(
            payload.get("node_id")
            or payload.get("plan_node_id")
            or payload.get("trade_plan_node_id")
            or payload.get("id")
        ) or f"{phase or 'node'}_{index}"
        claim_ids = _dedup_strings(_as_list(payload.get("claim_ids")))
        evidence_ids = _dedup_strings(_as_list(payload.get("evidence_ids")))
        nodes.append(
            {
                **payload,
                "node_id": node_id,
                "phase": phase or _string(payload.get("phase")).lower() or "node",
                "claim_ids": claim_ids,
                "evidence_ids": evidence_ids,
            }
        )

    entry = _as_dict(trade_plan.get("entry"))
    exit_payload = _as_dict(trade_plan.get("exit"))
    if entry:
        _append_node(entry, phase="entry")
    if exit_payload:
        _append_node(exit_payload, phase="exit")

    for phase in ("entries", "exits", "nodes", "steps"):
        for index, item in enumerate(_as_list(trade_plan.get(phase))):
            node_phase = "entry" if phase == "entries" else "exit" if phase == "exits" else phase
            _append_node(_as_dict(item), phase=node_phase, index=index)

    if not nodes and trade_plan:
        _append_node(trade_plan, phase="node")
    return nodes


def _collect_trade_plan_node_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, Mapping):
        payload = dict(value)
        for key in (
            "trade_plan_node_id",
            "trade_plan_step_id",
            "plan_node_id",
            "mapped_trade_plan_node_id",
            "node_id",
        ):
            token = _string(payload.get(key))
            if token:
                refs.append(token)
        for key in ("trade_plan_node_ids", "claim_ids", "mapped_trade_plan_node_ids"):
            refs.extend(_dedup_strings(_as_list(payload.get(key))))
        for child in payload.values():
            refs.extend(_collect_trade_plan_node_refs(child))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_collect_trade_plan_node_refs(item))
    return _dedup_strings(refs)
