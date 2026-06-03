

def build_candidate_evidence_records(
    candidate: Optional[Mapping[str, Any]],
    *,
    strategy_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    payload = dict(candidate or {})
    evidence_chain = _as_dict(_candidate_value(payload, "evidence_chain"))
    if not evidence_chain:
        return []
    research_task = _as_dict(_candidate_value(payload, "research_task"))
    target_symbols = [
        _string(symbol)
        for symbol in _as_list(_candidate_value(payload, "target_symbols"))
        if _string(symbol)
    ]
    task_key = (
        _string(research_task.get("task_signature"))
        or _string(research_task.get("task_key"))
        or _string(_candidate_value(payload, "task_signature"))
        or _string(strategy_id)
    )
    if not task_key:
        return []

    records: list[dict[str, Any]] = []
    candidate_id = (
        _string(payload.get("candidate_id") or payload.get("id"))
        or _string(strategy_id)
        or task_key
    )
    candidate_artifact_id = _string(
        _first_non_empty(
            payload.get("candidate_artifact_id"),
            payload.get("source_candidate_artifact_id"),
            payload.get("hypothesis_artifact_id"),
        )
    ) or None
    experiment_id = _string(payload.get("experiment_id")) or None
    for evidence in _normalize_evidences(evidence_chain):
        evidence_symbols = list(evidence.get("target_symbols") or [])
        source_type = _string(evidence.get("source_type")) or "candidate_evidence"
        headline_label_id = _string(evidence.get("headline_label_id")) or None
        doc_uid = _string(evidence.get("doc_uid")) or None
        records.append(
            {
                "id": f"{candidate_id}:{evidence.get('evidence_id')}",
                "candidate_id": candidate_id,
                "strategy_id": strategy_id,
                "candidate_artifact_id": candidate_artifact_id,
                "experiment_id": experiment_id,
                "evidence_id": evidence.get("evidence_id"),
                "source_type": source_type,
                "event_type": _string(evidence.get("event_type") or research_task.get("event_type")) or None,
                "target_symbols": evidence_symbols or target_symbols,
                "direction": evidence.get("direction"),
                "horizon_days": evidence.get("horizon_days"),
                "raw_confidence": evidence.get("raw_confidence"),
                "calibrated_confidence": evidence.get("calibrated_confidence"),
                "freshness_ts": evidence.get("freshness_ts"),
                "proxy_only": bool(evidence.get("proxy_only")),
                "support_metric": evidence.get("support_metric"),
                "doc_uid": doc_uid,
                "headline_label_id": headline_label_id,
                "source_task_key": task_key,
                "task_key": task_key,
                "event_id": research_task.get("event_id"),
                "theme_code": _string(research_task.get("theme_code")),
                "symbol": (evidence_symbols or target_symbols or [None])[0],
                "evidence_type": source_type,
                "weight": _safe_float(evidence.get("raw_confidence"), 0.0),
                "evidence_payload": {
                    **evidence,
                    "strategy_id": strategy_id,
                    "candidate_id": candidate_id or None,
                    "candidate_artifact_id": candidate_artifact_id,
                    "experiment_id": experiment_id,
                    "headline_label_id": headline_label_id,
                    "doc_uid": doc_uid,
                },
            }
        )
    return records


# INVERT-DESIGN P1 改动D：信号 evidence 的市场状态（regime）维度。
_REGIME_DIMENSIONS: tuple[str, ...] = ("trend_regime", "vol_regime", "sentiment_regime")


def _normalize_regime_labels(regime: Optional[Mapping[str, Any]]) -> dict[str, str]:
    """把传入的 regime 字典规整为三维标签，缺失维度填 'unknown'。"""
    source = dict(regime or {})
    labels: dict[str, str] = {}
    for dimension in _REGIME_DIMENSIONS:
        label = str(source.get(dimension) or "").strip().lower()
        labels[dimension] = label or "unknown"
    return labels


def _build_proxy_signal_evidence_records(
    payload: Mapping[str, Any],
    *,
    params: Mapping[str, Any],
    signal_id: Optional[str],
    position_id: Optional[str],
    account_id: Optional[str],
    signal_date: Any,
    code: Optional[str],
    regime_labels: Mapping[str, str],
) -> list[dict[str, Any]]:
    """INVERT-DESIGN P1 改动A 配套：为缺 evidence_chain 的宽进 observe 策略合成
    一条最小代理 evidence，使前向测量可进行。proxy_only=True，明确标记非正式语义契约。
    方向取 prediction_contract.direction，缺省按策略类型推 long(=up)。
    """
    strategy_id = _string(payload.get("id")) or None
    normalized_signal_id = _string(signal_id) or None
    if not strategy_id or not normalized_signal_id:
        return []
    prediction_contract = _as_dict(
        payload.get("prediction_contract") or dict(params or {}).get("prediction_contract")
    )
    direction = _string(prediction_contract.get("direction")).lower() or "up"
    if direction in {"long", "buy", "1"}:
        direction = "up"
    elif direction in {"short", "sell", "-1"}:
        direction = "down"
    resolved_code = (
        _string(code)
        or _string((list(payload.get("target_symbols") or params.get("target_symbols") or []) or [None])[0])
        or None
    )
    candidate_artifact_id = _string(
        _first_non_empty(
            payload.get("candidate_artifact_id"),
            payload.get("source_candidate_artifact_id"),
            dict(params or {}).get("source_candidate_artifact_id"),
        )
    ) or None
    experiment_id = _string(
        _first_non_empty(payload.get("experiment_id"), dict(params or {}).get("experiment_id"))
    ) or None
    signal_ts = _coerce_signal_ts(_first_non_empty(payload.get("signal_ts"), dict(params or {}).get("signal_ts"), signal_date))
    evidence_id = "wide_intake_observe_proxy"
    record_id = f"{normalized_signal_id}:{evidence_id}:proxy"
    return [
        {
            "id": record_id,
            "strategy_id": strategy_id,
            "signal_id": normalized_signal_id,
            "position_id": _string(position_id) or None,
            "account_id": _string(account_id) or None,
            "signal_date": signal_date,
            "signal_ts": signal_ts,
            "code": resolved_code,
            "symbol": resolved_code,
            "candidate_artifact_id": candidate_artifact_id,
            "experiment_id": experiment_id,
            "applied_claim_id": "wide_intake_observe_proxy_claim",
            "applied_trade_step_id": "wide_intake_observe_proxy_step",
            "evidence_id": evidence_id,
            "claim_ids": [],
            "evidence_type": "wide_intake_observe_proxy",
            "source_type": "wide_intake_observe_proxy",
            "direction": direction,
            "horizon_days": None,
            "raw_confidence": None,
            "calibrated_confidence": None,
            "proxy_only": True,
            "doc_uid": None,
            "headline_label_id": None,
            "weight": 0.0,
            **dict(regime_labels),
            "evidence_payload": {
                "build_mode": "wide_intake_observe_proxy",
                "strategy_id": strategy_id,
                "signal_id": normalized_signal_id,
                "signal_ts": signal_ts,
                "code": resolved_code,
                "direction": direction,
                "proxy_only": True,
                **dict(regime_labels),
            },
        }
    ]


def build_signal_evidence_records(
    strategy: Optional[Mapping[str, Any]],
    *,
    signal_id: Optional[str],
    position_id: Optional[str] = None,
    account_id: Optional[str] = None,
    signal_date: Any = None,
    code: Optional[str] = None,
    regime: Optional[Mapping[str, Any]] = None,
) -> list[dict[str, Any]]:
    payload = dict(strategy or {})
    params = _as_dict(payload.get("params"))
    evidence_chain = _as_dict(payload.get("evidence_chain") or params.get("evidence_chain"))
    prediction_contract = _as_dict(payload.get("prediction_contract") or params.get("prediction_contract"))
    # INVERT-DESIGN P1 改动D：解析当日市场状态标签（regime），写入每条 evidence。
    # 缺失时各维度归入 "unknown"，ForwardVerifier 据此分 regime 聚合命中率。
    regime_labels = _normalize_regime_labels(regime)
    claim_to_trade_plan_map = _as_dict(
        payload.get("claim_to_trade_plan_map") or params.get("claim_to_trade_plan_map")
    )
    claim_to_trade_step_ids = _as_dict(claim_to_trade_plan_map.get("claim_to_trade_step_ids"))
    if not evidence_chain:
        # INVERT-DESIGN P1 改动A 配套：宽进 observe 策略通常没有语义 evidence_chain
        # （fixed_defaults 填充物）。当 WIDE_INTAKE_OBSERVE 开启时，合成一条最小代理
        # evidence，使 ForwardVerifier 仍能对其做向前命中率测量（proxy_only=True，
        # 不冒充正式语义契约）。默认 OFF 时保持原 [] 行为，零变化。
        if str(os.getenv("STRATEGY_FACTORY_WIDE_INTAKE_OBSERVE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}:
            return _build_proxy_signal_evidence_records(
                payload,
                params=params,
                signal_id=signal_id,
                position_id=position_id,
                account_id=account_id,
                signal_date=signal_date,
                code=code,
                regime_labels=regime_labels,
            )
        return []
    strategy_id = _string(payload.get("id")) or None
    normalized_signal_id = _string(signal_id) or None
    if not strategy_id or not normalized_signal_id:
        return []
    signal_ts = _coerce_signal_ts(_first_non_empty(payload.get("signal_ts"), params.get("signal_ts"), signal_date))
    target_symbols = [
        _string(symbol)
        for symbol in _as_list(payload.get("target_symbols") or params.get("target_symbols"))
        if _string(symbol)
    ]
    claims = _normalize_claims(prediction_contract)
    claim_refs_by_evidence: dict[str, list[str]] = {}
    for claim in claims:
        claim_id = _string(claim.get("claim_id"))
        if not claim_id:
            continue
        for evidence_id in _as_list(claim.get("evidence_ids")):
            token = _string(evidence_id)
            if not token:
                continue
            claim_refs_by_evidence.setdefault(token, []).append(claim_id)
    candidate_artifact_id = _string(
        _first_non_empty(
            payload.get("candidate_artifact_id"),
            payload.get("source_candidate_artifact_id"),
            params.get("source_candidate_artifact_id"),
            payload.get("hypothesis_artifact_id"),
            params.get("hypothesis_artifact_id"),
        )
    ) or None
    experiment_id = _string(_first_non_empty(payload.get("experiment_id"), params.get("experiment_id"))) or None
    records: list[dict[str, Any]] = []
    for evidence in _normalize_evidences(evidence_chain):
        evidence_symbols = list(evidence.get("target_symbols") or [])
        applied_claim_ids = _dedup_strings(
            [
                *claim_refs_by_evidence.get(_string(evidence.get("evidence_id")), []),
                *_as_list(evidence.get("claim_ids")),
            ]
        ) or [None]
        for applied_claim_id in applied_claim_ids:
            applied_trade_step_ids = _dedup_strings(
                _as_list(claim_to_trade_step_ids.get(_string(applied_claim_id)))
            ) or [None]
            for applied_trade_step_id in applied_trade_step_ids:
                record_id_suffix = _string(applied_claim_id) or "unclaimed"
                step_id_suffix = _string(applied_trade_step_id) or "unmapped_step"
                resolved_code = _string(code) or _string((evidence_symbols or target_symbols or [None])[0]) or None
                records.append(
                    {
                        "id": f"{normalized_signal_id}:{evidence.get('evidence_id')}:{record_id_suffix}:{step_id_suffix}",
                        "strategy_id": strategy_id,
                        "signal_id": normalized_signal_id,
                        "position_id": _string(position_id) or None,
                        "account_id": _string(account_id) or None,
                        "signal_date": signal_date,
                        "signal_ts": signal_ts,
                        "code": resolved_code,
                        "symbol": resolved_code,
                        "candidate_artifact_id": candidate_artifact_id,
                        "experiment_id": experiment_id,
                        "applied_claim_id": _string(applied_claim_id) or None,
                        "applied_trade_step_id": _string(applied_trade_step_id) or None,
                        "evidence_id": evidence.get("evidence_id"),
                        "claim_ids": [applied_claim_id] if _string(applied_claim_id) else [],
                        "evidence_type": _normalized_source_type(evidence.get("source_type")) or "signal_evidence",
                        "source_type": _normalized_source_type(evidence.get("source_type")) or "signal_evidence",
                        "direction": evidence.get("direction"),
                        "horizon_days": evidence.get("horizon_days"),
                        "raw_confidence": evidence.get("raw_confidence"),
                        "calibrated_confidence": evidence.get("calibrated_confidence"),
                        "proxy_only": bool(evidence.get("proxy_only")),
                        "doc_uid": _string(evidence.get("doc_uid")) or None,
                        "headline_label_id": _string(evidence.get("headline_label_id")) or None,
                        "weight": _safe_float(evidence.get("raw_confidence"), 0.0),
                        **regime_labels,
                        "evidence_payload": {
                            **evidence,
                            "strategy_id": strategy_id,
                            "signal_id": normalized_signal_id,
                            "candidate_artifact_id": candidate_artifact_id,
                            "experiment_id": experiment_id,
                            "applied_claim_id": _string(applied_claim_id) or None,
                            "applied_trade_step_id": _string(applied_trade_step_id) or None,
                            "signal_ts": signal_ts,
                            "code": resolved_code,
                            **regime_labels,
                        },
                    }
                )
    return records


__all__ = [
    "audit_candidate_semantic_contract",
    "build_candidate_evidence_records",
    "build_signal_evidence_records",
    "ensure_candidate_semantic_contract",
    "inspect_strategy_dsl_support",
    "normalize_semantic_contract_fields",
    "synthesize_confidence_contract",
]
