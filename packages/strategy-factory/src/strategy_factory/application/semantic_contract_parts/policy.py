

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


def _semantic_direction_bucket(value: Any) -> Optional[str]:
    token = _string(value).lower().replace("-", "_").replace(" ", "_")
    if not token:
        return None
    if token in {"up", "bullish", "long", "buy", "rise", "rising", "positive"}:
        return "up"
    if token in {"down", "bearish", "short", "sell", "fall", "falling", "negative"}:
        return "down"
    if token in {"neutral", "flat", "sideways", "hold"}:
        return "neutral"
    if any(part in token for part in ("short", "bear", "sell", "risk_off", "negative")):
        return "down"
    if any(part in token for part in ("neutral", "hedge", "sideways")):
        return "neutral"
    if any(part in token for part in ("long", "bull", "buy", "repair", "breakout", "positive", "rebound")):
        return "up"
    return None


def _semantic_contract_direction(candidate: Mapping[str, Any], strategy_type: Optional[str]) -> str:
    params = _as_dict(dict(candidate).get("params"))
    trade_plan = _as_dict(_candidate_value(candidate, "trade_plan"))
    direction_resolution = _as_dict(_candidate_value(candidate, "direction_resolution"))
    alpha_thesis = _as_dict(_candidate_value(candidate, "alpha_thesis"))
    prediction_contract = _as_dict(_candidate_value(candidate, "prediction_contract"))
    claims = _as_list(prediction_contract.get("claims"))
    first_claim = _as_dict(claims[0]) if claims else {}
    return (
        _semantic_direction_bucket(direction_resolution.get("direction"))
        or _semantic_direction_bucket(alpha_thesis.get("direction"))
        or _semantic_direction_bucket(dict(candidate).get("direction"))
        or _semantic_direction_bucket(params.get("direction"))
        or _semantic_direction_bucket(prediction_contract.get("direction"))
        or _semantic_direction_bucket(first_claim.get("direction"))
        or _semantic_direction_bucket(first_claim.get("expected_direction"))
        or _semantic_direction_bucket(first_claim.get("expected_move"))
        or _semantic_direction_bucket(trade_plan.get("direction"))
        or _semantic_direction_bucket(trade_plan.get("entry_bias"))
        or "neutral"
    )


def _semantic_contract_confidence(candidate: Mapping[str, Any], default: float = 0.45) -> float:
    params = _as_dict(dict(candidate).get("params"))
    confidence_calibration = _as_dict(_candidate_value(candidate, "confidence_calibration"))
    alpha_thesis = _as_dict(_candidate_value(candidate, "alpha_thesis"))
    prediction_contract = _as_dict(_candidate_value(candidate, "prediction_contract"))
    claims = _as_list(prediction_contract.get("claims"))
    first_claim = _as_dict(claims[0]) if claims else {}
    return round(
        max(
            0.0,
            min(
                1.0,
                _safe_float(
                    _first_non_empty(
                        confidence_calibration.get("confidence"),
                        alpha_thesis.get("confidence"),
                        dict(candidate).get("confidence"),
                        params.get("confidence"),
                        prediction_contract.get("confidence"),
                        first_claim.get("calibrated_confidence"),
                        first_claim.get("confidence"),
                        default,
                    ),
                    default,
                ),
            ),
        ),
        6,
    )


def _default_expected_move(strategy_type: Optional[str]) -> str:
    return "neutral"


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
    exit_payload.setdefault("node_id", "exit_step_1")
    exit_payload.setdefault("phase", "exit")
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
    direction = _semantic_contract_direction(candidate, strategy_type)
    confidence = _semantic_contract_confidence(candidate, default=0.45)
    market_evidence_pack = _as_dict(_candidate_value(candidate, "market_evidence_pack"))
    template_dominance_score = _safe_float(market_evidence_pack.get("template_dominance_score"))
    non_proxy_evidence_ratio = _safe_float(market_evidence_pack.get("non_proxy_evidence_ratio"))
    # 诚实判定:这是 default/backfill 兜底构造器,ev_entry_signal 默认就是模板派生的 proxy。
    # 仅当候选带真实 market_evidence_pack 且其中有非模板证据(template_dominance<=阈值
    # 且 non_proxy_evidence_ratio>0)时才标 price_volume_confirmation。
    # 历史 bug:旧阈值 >=0.999 把无 pack(score=0,_safe_float(None)=0.0)与高模板主导
    # (0<score<0.999)的候选都错标成 proxy_only=False,伪装真实价量证据。
    has_real_evidence_backing = (
        bool(market_evidence_pack)
        and template_dominance_score <= _TEMPLATE_FALLBACK_DOMINANCE_THRESHOLD
        and non_proxy_evidence_ratio > 0.0
    )
    is_template_proxy = not has_real_evidence_backing
    return {
        "contract_version": "strategy_factory.semantic_contract.v1",
        "producer": "strategy_factory",
        "generation_mode": "factory_semantic_contract_backfill",
        "thesis": thesis,
        "evidences": [
            {
                "evidence_id": "ev_entry_signal",
                "source_type": "template_fallback" if is_template_proxy else "price_volume_confirmation",
                "direction": direction,
                "summary": thesis,
                "proxy_only": is_template_proxy,
                "raw_confidence": confidence,
                "calibrated_confidence": confidence,
                "target_symbols": list(target_symbols),
                "horizon_days": int(horizon_days),
                "claim_ids": ["claim_entry"],
                "support_metric": {
                    "strategy_type": strategy_type,
                    "source": source,
                    "direction_source": _as_dict(_candidate_value(candidate, "direction_resolution")).get("direction_source"),
                    "template_dominance_score": template_dominance_score,
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
