def _build_default_prediction_contract(
    candidate: Mapping[str, Any],
    *,
    strategy_type: str,
    target_symbols: list[str],
    horizon_days: int,
) -> dict[str, Any]:
    name = _string(_candidate_value(candidate, "name") or dict(candidate).get("name")) or strategy_type
    thesis = _string(_candidate_value(candidate, "hypothesis") or dict(candidate).get("description")) or name
    direction = _semantic_contract_direction(candidate, strategy_type)
    confidence = _semantic_contract_confidence(candidate, default=0.45)
    confidence_calibration = _as_dict(_candidate_value(candidate, "confidence_calibration"))
    direction_resolution = _as_dict(_candidate_value(candidate, "direction_resolution"))
    target = (
        "forward_return_positive"
        if direction == "up"
        else "forward_return_negative"
        if direction == "down"
        else "forward_return_neutral"
    )
    return {
        "contract_version": "strategy_factory.prediction_contract.v1",
        "producer": "strategy_factory",
        "generation_mode": "factory_semantic_contract_backfill",
        "primary_horizon_days": int(horizon_days),
        "target": target,
        "direction": direction,
        "confidence": confidence,
        "direction_source": direction_resolution.get("direction_source") or "semantic_contract_backfill",
        "confidence_source": confidence_calibration.get("confidence_source") or "semantic_contract_backfill",
        "evidence_quality_score": confidence_calibration.get("evidence_quality_score"),
        "conflict_count": direction_resolution.get("conflict_count"),
        "template_fallback_used": _safe_float(_as_dict(_candidate_value(candidate, "market_evidence_pack")).get("template_dominance_score")) > 0,
        "conflict_resolution_rule": {
            "policy": "evidence_vote_with_neutral_on_conflict",
            "tie_breaker": "neutral_when_margin_small",
        },
        "claims": [
            {
                "claim_id": "claim_entry",
                "claim_type": "entry",
                "summary": thesis,
                "expected_move": direction,
                "expected_horizon": int(horizon_days),
                "confidence": confidence,
                "calibrated_confidence": confidence,
                "evidence_ids": ["ev_entry_signal"],
                "failure_condition": "entry thesis invalidated by exit signal, stop loss, or time stop",
                "conflict_resolution_rule": {"policy": "evidence_vote_with_neutral_on_conflict"},
                "target_symbols": list(target_symbols),
            },
            {
                "claim_id": "claim_exit",
                "claim_type": "exit",
                "summary": "Risk or signal invalidation exits the position.",
                "expected_move": "down" if direction == "up" else "up" if direction == "down" else "neutral",
                "expected_horizon": max(1, int(horizon_days // 2)),
                "evidence_ids": ["ev_exit_risk"],
                "failure_condition": "entry thesis restored",
                "conflict_resolution_rule": {"policy": "risk_first"},
                "target_symbols": list(target_symbols),
            },
        ],
    }


def _claim_direction_bucket(value: Any) -> Optional[str]:
    token = _string(value).lower()
    if not token:
        return None
    if any(word in token for word in ("up", "long", "bull", "buy", "rise", "rebound")):
        return "up"
    if any(word in token for word in ("down", "short", "bear", "sell", "fall", "drop")):
        return "down"
    return None


def _claim_type_bucket(claim: Mapping[str, Any]) -> str:
    return _string(claim.get("claim_type") or claim.get("type") or claim.get("phase")).lower()


def _trade_plan_phase_bucket(phase: Optional[str], node: Mapping[str, Any]) -> str:
    text = " ".join(
        [
            _string(phase),
            _string(node.get("phase")),
            _string(node.get("node_id")),
            _string(node.get("summary")),
            _string(node.get("exit_bias")),
            _string(node.get("entry_bias")),
            _string(node.get("condition")),
            _string(node.get("trigger")),
        ]
    ).lower()
    if any(token in text for token in ("exit", "risk", "stop", "invalid", "sell")):
        return "exit"
    return "entry"


def _select_claim_ids_for_trade_plan_node(
    *,
    phase: str,
    claims: list[dict[str, Any]],
    primary_entry_claim_id: str,
) -> list[str]:
    if not claims:
        return []
    if phase == "exit":
        for claim in claims:
            claim_type = _claim_type_bucket(claim)
            if claim_type in {"exit", "risk", "stop", "invalidation"}:
                return [str(claim["claim_id"])]
        for claim in claims:
            if _claim_direction_bucket(claim.get("expected_move")) == "down":
                return [str(claim["claim_id"])]
        return [primary_entry_claim_id] if primary_entry_claim_id else [str(claims[0]["claim_id"])]

    for claim in claims:
        claim_type = _claim_type_bucket(claim)
        if claim_type in {"entry", "signal", "thesis"}:
            return [str(claim["claim_id"])]
    for claim in claims:
        if _claim_direction_bucket(claim.get("expected_move")) == "up":
            return [str(claim["claim_id"])]
    return [primary_entry_claim_id] if primary_entry_claim_id else [str(claims[0]["claim_id"])]


def _claim_evidence_ids(claims_by_id: Mapping[str, Mapping[str, Any]], claim_ids: list[str]) -> list[str]:
    evidence_ids: list[str] = []
    for claim_id in claim_ids:
        evidence_ids.extend(
            _string(item)
            for item in _as_list(_as_dict(claims_by_id.get(claim_id)).get("evidence_ids"))
            if _string(item)
        )
    return _dedup_strings(evidence_ids)


def _trade_plan_claim_ids_replaceable(claim_ids: list[str], claim_id_set: set[str]) -> bool:
    if not claim_ids:
        return True
    placeholder_ids = {"claim_entry", "claim_exit"}
    return all(claim_id in placeholder_ids and claim_id not in claim_id_set for claim_id in claim_ids)


def _backfill_trade_plan_claim_links(
    trade_plan: Mapping[str, Any],
    prediction_contract: Mapping[str, Any],
    existing_claim_to_trade_plan_map: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    claims = _normalize_claims(prediction_contract)
    claim_id_set = {str(claim.get("claim_id")) for claim in claims if claim.get("claim_id")}
    claims_by_id = {str(claim["claim_id"]): claim for claim in claims if claim.get("claim_id")}
    payload = dict(trade_plan or {})
    changed = False
    if not claims:
        return payload, _as_dict(existing_claim_to_trade_plan_map), changed

    primary_entry_claim_id = ""
    for claim in claims:
        if _claim_type_bucket(claim) in {"entry", "signal", "thesis"}:
            primary_entry_claim_id = str(claim["claim_id"])
            break
    if not primary_entry_claim_id:
        for claim in claims:
            if _claim_direction_bucket(claim.get("expected_move")) == "up":
                primary_entry_claim_id = str(claim["claim_id"])
                break
    if not primary_entry_claim_id:
        primary_entry_claim_id = str(claims[0]["claim_id"])

    def _repair_node(node: Mapping[str, Any], *, phase: Optional[str] = None, index: int = 0) -> dict[str, Any]:
        nonlocal changed
        node_payload = _as_dict(node)
        if not node_payload:
            return {}
        phase_bucket = _trade_plan_phase_bucket(phase, node_payload)
        existing_node_id = _string(
            node_payload.get("node_id")
            or node_payload.get("plan_node_id")
            or node_payload.get("trade_plan_node_id")
            or node_payload.get("id")
        )
        fallback_node_id = (
            f"{phase_bucket}_step_1"
            if phase in {"entry", "exit"} and phase_bucket in {"entry", "exit"}
            else f"{phase_bucket}_{index}"
        )
        node_id = existing_node_id or fallback_node_id
        if node_payload.get("node_id") != node_id:
            node_payload["node_id"] = node_id
            changed = True
        if not _string(node_payload.get("phase")):
            node_payload["phase"] = phase_bucket
            changed = True
        claim_ids = _dedup_strings(_as_list(node_payload.get("claim_ids")))
        if _trade_plan_claim_ids_replaceable(claim_ids, claim_id_set):
            selected_claim_ids = _select_claim_ids_for_trade_plan_node(
                phase=phase_bucket,
                claims=claims,
                primary_entry_claim_id=primary_entry_claim_id,
            )
            if selected_claim_ids and claim_ids != selected_claim_ids:
                node_payload["claim_ids"] = selected_claim_ids
                claim_ids = selected_claim_ids
                changed = True
        evidence_ids = _dedup_strings(_as_list(node_payload.get("evidence_ids")))
        if not evidence_ids and claim_ids and all(claim_id in claim_id_set for claim_id in claim_ids):
            selected_evidence_ids = _claim_evidence_ids(claims_by_id, claim_ids)
            if selected_evidence_ids:
                node_payload["evidence_ids"] = selected_evidence_ids
                changed = True
        return node_payload

    if _as_dict(payload.get("entry")):
        payload["entry"] = _repair_node(_as_dict(payload.get("entry")), phase="entry")
    if _as_dict(payload.get("exit")):
        payload["exit"] = _repair_node(_as_dict(payload.get("exit")), phase="exit")

    for key, default_phase in (
        ("entries", "entry"),
        ("exits", "exit"),
        ("nodes", None),
        ("steps", None),
    ):
        if key not in payload:
            continue
        repaired_items = []
        for index, item in enumerate(_as_list(payload.get(key))):
            repaired = _repair_node(_as_dict(item), phase=default_phase, index=index)
            if repaired:
                repaired_items.append(repaired)
        if repaired_items != _as_list(payload.get(key)):
            payload[key] = repaired_items
            changed = True

    trade_step_to_claim_ids: dict[str, list[str]] = {}
    claim_to_trade_step_ids: dict[str, list[str]] = {claim_id: [] for claim_id in sorted(claim_id_set)}
    for node in _normalized_trade_plan_nodes(payload):
        node_id = _string(node.get("node_id"))
        if not node_id:
            continue
        node_claim_ids = _dedup_strings(_as_list(node.get("claim_ids")))
        if not node_claim_ids:
            continue
        trade_step_to_claim_ids[node_id] = node_claim_ids
        for claim_id in node_claim_ids:
            if claim_id in claim_to_trade_step_ids:
                claim_to_trade_step_ids[claim_id].append(node_id)

    claim_to_trade_plan_map = {
        **_as_dict(existing_claim_to_trade_plan_map),
        "claim_to_trade_step_ids": {
            claim_id: _dedup_strings(step_ids)
            for claim_id, step_ids in claim_to_trade_step_ids.items()
        },
        "trade_step_to_claim_ids": trade_step_to_claim_ids,
    }
    claim_to_trade_plan_map["mapped_claim_count"] = sum(
        1 for step_ids in claim_to_trade_plan_map["claim_to_trade_step_ids"].values() if step_ids
    )
    claim_to_trade_plan_map["trade_step_count"] = len(trade_step_to_claim_ids)
    claim_to_trade_plan_map["unmapped_claim_ids"] = [
        claim_id
        for claim_id, step_ids in claim_to_trade_plan_map["claim_to_trade_step_ids"].items()
        if not step_ids
    ]
    return payload, claim_to_trade_plan_map, changed


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
            "evidence_chain": evidence_chain,
            "prediction_contract": prediction_contract,
        }
    )
    claim_to_trade_plan_map = _as_dict(_candidate_value(payload, "claim_to_trade_plan_map"))
    trade_plan, claim_to_trade_plan_map, claim_ids_backfilled = _backfill_trade_plan_claim_links(
        trade_plan,
        prediction_contract,
        claim_to_trade_plan_map,
    )
    dsl = _ensure_dsl_mapping(payload, trade_plan)
    confidence_contract = synthesize_confidence_contract(
        {
            **payload,
            "trade_plan": trade_plan,
            "dsl": dsl or _as_dict(_candidate_value(payload, "dsl")),
            "evidence_chain": evidence_chain,
            "prediction_contract": prediction_contract,
        }
    )

    payload = _attach_semantic_fields(
        payload,
        {
            "trade_plan": trade_plan,
            "dsl": dsl,
            "evidence_chain": evidence_chain,
            "prediction_contract": prediction_contract,
            "confidence_contract": confidence_contract,
            "claim_to_trade_plan_map": claim_to_trade_plan_map,
            "semantic_contract_claim_ids_backfilled": bool(claim_ids_backfilled),
            "semantic_contract_backfill_source": (
                "prediction_contract_claims" if claim_ids_backfilled else "none"
            ),
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
