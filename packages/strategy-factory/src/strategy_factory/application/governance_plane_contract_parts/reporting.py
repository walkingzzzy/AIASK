

def build_gate_c_artifact(
    *,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(submit_result or {})
    strategies = [dict(item or {}) for item in list(payload.get("strategies") or []) if isinstance(item, dict)]
    signal_quality_counts = _count_by(
        strategies,
        lambda item: dict(item.get("signal_quality_snapshot") or {}).get("status") or item.get("signal_quality"),
    )
    execution_quality_counts = _count_by(
        strategies,
        lambda item: dict(item.get("execution_quality_snapshot") or {}).get("status") or item.get("execution_quality"),
    )
    execution_audit_counts = _count_by(strategies, lambda item: item.get("execution_audit_gate_status"))
    hard_gate_counts = _count_by(strategies, lambda item: item.get("hard_gate_result"))
    promotion_ready_count = sum(1 for item in strategies if bool(item.get("promotion_ready")))
    gate_blocker_counts: dict[str, int] = {}
    evidence_refs: list[str] = []
    evidence_gap_codes: list[str] = []
    hard_failures: list[dict[str, Any]] = []
    artifact_ids: list[str] = []
    retrieval_context_ids: list[str] = []
    for item in strategies:
        trace_id = _string(item.get("prediction_trace_id") or item.get("trace_id"))
        if trace_id and trace_id not in evidence_refs:
            evidence_refs.append(trace_id)
        for reason in list(item.get("gate_blockers") or item.get("reasons") or []):
            code = _string(reason)
            if code:
                gate_blocker_counts[code] = gate_blocker_counts.get(code, 0) + 1
                failure = _normalize_hard_failure_entry(code, issue="promotion_gate_blocker")
                if failure:
                    hard_failures.append(failure)
        execution_audit_gate_status = _normalized_text(item.get("execution_audit_gate_status"))
        if execution_audit_gate_status in {
            "missing",
            "bootstrap_pending",
            "insufficient_samples",
            "bootstrap_ready",
            "insufficient_evidence",
        }:
            evidence_gap_codes.append(f"execution_audit_gate:{execution_audit_gate_status}")
        for code in list(item.get("evidence_gap_codes") or []):
            token = _string(code)
            if token:
                evidence_gap_codes.append(token)
        for artifact_id in _candidate_artifact_ids(item):
            if artifact_id not in artifact_ids:
                artifact_ids.append(artifact_id)
        for context_id in _candidate_retrieval_context_ids(item):
            if context_id not in retrieval_context_ids:
                retrieval_context_ids.append(context_id)
    blocked = bool(gate_blocker_counts)
    hard_failures = _unique_hard_failures(hard_failures)
    return {
        "contract_version": GATE_ARTIFACT_V2_CONTRACT_VERSION,
        "gate_name": "gate_c",
        "stage": "gate_c",
        "decision": "block" if blocked else "observe" if strategies else "pending",
        "status": "blocked" if blocked else "observe" if strategies else "pending",
        "hard_failures": hard_failures,
        "evidence_gap_codes": _compact_list(evidence_gap_codes, limit=16),
        "artifact_ids": artifact_ids[:16],
        "retrieval_context_ids": retrieval_context_ids[:16],
        "trace_ids": evidence_refs[:12],
        "family_outcome_summary": _family_outcome_summary(strategies),
        "blocking_reasons": _top_counts(gate_blocker_counts, label_key="reason_code"),
        "warnings": [],
        "evidence_refs": evidence_refs[:12],
        "legacy_gate_mapping": [
            "signal_quality",
            "execution_quality",
            "execution_audit_gate_status",
            "hard_gate_result",
            "promotion_ready",
        ],
        "signal_quality_distribution": signal_quality_counts,
        "execution_quality_distribution": execution_quality_counts,
        "execution_audit_gate_status_distribution": execution_audit_counts,
        "hard_gate_result_distribution": hard_gate_counts,
        "promotion_ready_count": promotion_ready_count,
        "promotion_ready_rate": round(promotion_ready_count / max(len(strategies), 1), 4) if strategies else 0.0,
    }


def _build_protocol_version_summary(
    *,
    candidates: list[dict[str, Any]] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_items = [dict(item or {}) for item in list(candidates or []) if isinstance(item, dict)]
    strategy_items = [dict(item or {}) for item in list(dict(submit_result or {}).get("strategies") or []) if isinstance(item, dict)]
    research_protocol_counts = _count_by(
        [*candidate_items, *strategy_items],
        lambda item: _candidate_research_protocol_version(item) or item.get("research_protocol_version"),
    )
    candidate_contract_counts = _count_by(
        [*candidate_items, *strategy_items],
        lambda item: _candidate_contract_version(item) or item.get("candidate_contract_version"),
    )
    spec_completeness_counts = _count_by(
        [*candidate_items, *strategy_items],
        lambda item: _candidate_spec_completeness(item) or item.get("spec_completeness"),
    )
    return {
        "research_protocol_version_counts": research_protocol_counts,
        "candidate_contract_version_counts": candidate_contract_counts,
        "spec_completeness_counts": spec_completeness_counts,
    }


def _build_prediction_trace_summary(
    *,
    candidates: list[dict[str, Any]] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_items = [dict(item or {}) for item in list(candidates or []) if isinstance(item, dict)]
    strategy_items = [dict(item or {}) for item in list(dict(submit_result or {}).get("strategies") or []) if isinstance(item, dict)]
    trace_ids: list[str] = []
    for item in [*candidate_items, *strategy_items]:
        trace_id = _candidate_prediction_trace_id(item) or _string(item.get("prediction_trace_id") or item.get("trace_id"))
        if trace_id and trace_id not in trace_ids:
            trace_ids.append(trace_id)
    total = len(candidate_items) + len(strategy_items)
    return {
        "contract_version": PREDICTION_TRACE_CONTRACT_VERSION,
        "trace_count": len(trace_ids),
        "missing_count": max(total - len(trace_ids), 0),
        "sample_trace_ids": trace_ids[:12],
    }


def _default_prediction_trace_gate_decisions() -> dict[str, Any]:
    return {
        "execution_audit_gate_status": None,
        "promotion_ready": False,
        "hard_gate_passed": False,
        "failure_reasons": [],
    }


def _default_prediction_trace_node(*, source_mode: str = "summary_fallback") -> dict[str, Any]:
    return {
        "available": False,
        "source_mode": source_mode,
        "count": 0,
        "ids": [],
    }


def _normalize_prediction_trace_gate_decisions(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {
            **_default_prediction_trace_gate_decisions(),
            "failure_reasons": _compact_list(value, limit=16),
        }
    payload = dict(value or {})
    return {
        "execution_audit_gate_status": _string(payload.get("execution_audit_gate_status")) or None,
        "promotion_ready": bool(payload.get("promotion_ready")),
        "hard_gate_passed": bool(payload.get("hard_gate_passed")),
        "failure_reasons": _compact_list(payload.get("failure_reasons") or [], limit=16),
    }


def _normalize_prediction_trace_node(
    value: Any,
    *,
    default_source_mode: str = "summary_fallback",
) -> dict[str, Any]:
    payload = dict(value or {})
    count = _safe_int(
        payload.get("count")
        or payload.get("signal_evidence_count")
        or payload.get("order_count")
        or payload.get("trade_count")
        or payload.get("realized_trade_count")
        or payload.get("position_count")
        or payload.get("mapped_position_count")
        or payload.get("nav_row_count")
    )
    ids = _compact_list(
        payload.get("ids")
        or payload.get("recent_signal_ids")
        or payload.get("order_ids")
        or payload.get("trade_ids")
        or payload.get("position_ids")
        or [],
        limit=8,
    )
    result: dict[str, Any] = {
        "available": bool(payload.get("available")),
        "source_mode": _string(payload.get("source_mode")) or default_source_mode,
        "count": count,
        "ids": ids,
    }
    if _string(payload.get("status")):
        result["status"] = _string(payload.get("status"))
    if _string(payload.get("as_of")):
        result["as_of"] = _string(payload.get("as_of"))
    for key, raw in payload.items():
        if key in {"available", "source_mode", "count", "ids", "status", "as_of"}:
            continue
        if raw in (None, "", [], {}):
            continue
        if isinstance(raw, list):
            result[key] = _compact_list(raw, limit=16 if key == "failure_reasons" else 8)
        else:
            result[key] = raw
    return result


def _merge_count_maps(existing: Any, incoming: Any) -> dict[str, int]:
    result = {
        _string(key): _safe_int(value)
        for key, value in dict(existing or {}).items()
        if _string(key)
    }
    for key, value in dict(incoming or {}).items():
        token = _string(key)
        if not token:
            continue
        result[token] = result.get(token, 0) + _safe_int(value)
    return result


def _merge_prediction_trace_node(existing: Any, incoming: Any) -> dict[str, Any]:
    left = _normalize_prediction_trace_node(existing)
    right = _normalize_prediction_trace_node(incoming, default_source_mode=left.get("source_mode") or "summary_fallback")
    result = dict(left)
    result["available"] = bool(left.get("available")) or bool(right.get("available"))
    result["source_mode"] = (
        "entity_backed"
        if "entity_backed" in {_string(left.get("source_mode")), _string(right.get("source_mode"))}
        else _string(right.get("source_mode")) or _string(left.get("source_mode")) or "summary_fallback"
    )
    result["count"] = max(_safe_int(left.get("count")), _safe_int(right.get("count")))
    result["ids"] = _compact_list([*list(left.get("ids") or []), *list(right.get("ids") or [])], limit=8)
    if _string(right.get("status")):
        result["status"] = _string(right.get("status"))
    elif _string(left.get("status")):
        result["status"] = _string(left.get("status"))
    if _string(right.get("as_of")):
        result["as_of"] = _string(right.get("as_of"))
    elif _string(left.get("as_of")):
        result["as_of"] = _string(left.get("as_of"))

    for key in set(left.keys()) | set(right.keys()):
        if key in {"available", "source_mode", "count", "ids", "status", "as_of"}:
            continue
        left_value = left.get(key)
        right_value = right.get(key)
        if isinstance(left_value, dict) or isinstance(right_value, dict):
            result[key] = _merge_count_maps(left_value, right_value)
        elif isinstance(left_value, list) or isinstance(right_value, list):
            result[key] = _compact_list([*list(left_value or []), *list(right_value or [])], limit=16)
        elif right_value not in (None, "", [], {}):
            result[key] = right_value
        elif left_value not in (None, "", [], {}):
            result[key] = left_value
    return result


def _merge_prediction_trace_gate_decisions(existing: Any, incoming: Any) -> dict[str, Any]:
    left = _normalize_prediction_trace_gate_decisions(existing)
    right = _normalize_prediction_trace_gate_decisions(incoming)
    return {
        "execution_audit_gate_status": _string(right.get("execution_audit_gate_status"))
        or _string(left.get("execution_audit_gate_status"))
        or None,
        "promotion_ready": bool(left.get("promotion_ready")) or bool(right.get("promotion_ready")),
        "hard_gate_passed": bool(left.get("hard_gate_passed")) or bool(right.get("hard_gate_passed")),
        "failure_reasons": _compact_list(
            [*list(left.get("failure_reasons") or []), *list(right.get("failure_reasons") or [])],
            limit=16,
        ),
    }


def _prediction_trace_entry_template(trace_id: str | None) -> dict[str, Any]:
    return {
        "prediction_trace_id": trace_id or None,
        "source_count": 0,
        "artifact_ids": [],
        "retrieval_context_ids": [],
        "family_outcome_summary": {"family_counts": {}, "status_counts": {}, "submission_lane_counts": {}},
        "hypothesis_spec": _default_prediction_trace_node(),
        "signal_event": _default_prediction_trace_node(),
        "intended_order": _default_prediction_trace_node(),
        "actual_fill": _default_prediction_trace_node(),
        "position_round_trip": _default_prediction_trace_node(),
        "pnl_audit_summary": _default_prediction_trace_node(),
        "gate_decisions": _default_prediction_trace_gate_decisions(),
        "evidence_gap_codes": [],
    }


def _build_prediction_trace_ledger_fallback_entry(item: dict[str, Any]) -> dict[str, Any]:
    signal_quality = dict(item.get("signal_quality_snapshot") or item.get("signal_quality") or {})
    execution_quality = dict(item.get("execution_quality_snapshot") or item.get("execution_quality") or {})
    audit = dict(execution_quality.get("audit") or {})
    trace_id = _candidate_prediction_trace_id(item) or _string(item.get("prediction_trace_id") or item.get("trace_id")) or None
    research_protocol_version = _candidate_research_protocol_version(item) or None
    candidate_contract_version = _candidate_contract_version(item) or None
    dsl_signature = _string(item.get("dsl_signature") or _candidate_payload_value(item, "dsl_signature")) or None
    order_count = _safe_int(
        execution_quality.get("order_count")
        or execution_quality.get("filled_order_count")
        or execution_quality.get("trade_count")
    )
    trade_count = _safe_int(execution_quality.get("trade_count"))
    realized_trade_count = _safe_int(
        execution_quality.get("realized_trade_count")
        or audit.get("realized_trade_count")
    )
    mapped_position_count = _safe_int(
        execution_quality.get("mapped_position_count")
        or audit.get("mapped_position_count")
    )
    position_count = _safe_int(execution_quality.get("position_count"))
    closed_position_count = _safe_int(execution_quality.get("closed_position_count"))
    incomplete_position_count = _safe_int(
        execution_quality.get("incomplete_position_count")
        or audit.get("incomplete_position_count")
    )
    nav_row_count = _safe_int(execution_quality.get("nav_row_count"))
    realized_pnl_total = execution_quality.get("realized_pnl_total")
    if realized_pnl_total in (None, ""):
        realized_pnl_total = audit.get("realized_pnl_total")
    trade_expectancy = execution_quality.get("trade_expectancy")
    execution_audit_gate_status = _string(
        item.get("execution_audit_gate_status")
        or execution_quality.get("execution_audit_gate_status")
        or audit.get("execution_audit_gate_status")
    ) or None
    failure_reasons = _compact_list(
        list(dict(item.get("hard_gate_result") or {}).get("failure_reasons") or [])
        or list(dict(item.get("hard_gate_result") or {}).get("reasons") or [])
        or list(item.get("execution_audit_gate_reasons") or []),
        limit=16,
    )
    evidence_gap_codes = _compact_list(item.get("evidence_gap_codes") or execution_quality.get("evidence_gap_codes") or [], limit=16)
    result = {
        "prediction_trace_id": trace_id,
        "hypothesis_spec": {
            "available": bool(research_protocol_version or candidate_contract_version or dsl_signature),
            "source_mode": "summary_fallback",
            "count": 1 if (research_protocol_version or candidate_contract_version or dsl_signature) else 0,
            "research_protocol_version": research_protocol_version,
            "candidate_contract_version": candidate_contract_version,
            "dsl_signature": dsl_signature,
        },
        "signal_event": {
            "available": bool(signal_quality),
            "source_mode": "summary_fallback",
            "count": 1 if signal_quality else 0,
            "status": _string(signal_quality.get("status") or signal_quality.get("coverage_status")) or None,
        },
        "intended_order": {
            "available": order_count > 0,
            "source_mode": "summary_fallback",
            "count": order_count,
            "order_count": order_count,
            "paper_account_id": _string(item.get("paper_account_id") or item.get("incubation_account_id")) or None,
        },
        "actual_fill": {
            "available": trade_count > 0 or realized_trade_count > 0,
            "source_mode": "summary_fallback",
            "count": max(trade_count, realized_trade_count),
            "trade_count": trade_count,
            "realized_trade_count": realized_trade_count,
        },
        "position_round_trip": {
            "available": position_count > 0 or mapped_position_count > 0 or closed_position_count > 0,
            "source_mode": "summary_fallback",
            "count": max(position_count, mapped_position_count, closed_position_count),
            "position_count": position_count,
            "mapped_position_count": mapped_position_count,
            "closed_position_count": closed_position_count,
            "round_trip_close_rate": execution_quality.get("round_trip_close_rate"),
            "incomplete_position_count": incomplete_position_count,
        },
        "pnl_audit_summary": {
            "available": nav_row_count > 0 or realized_pnl_total not in (None, "") or trade_expectancy not in (None, ""),
            "source_mode": "summary_fallback",
            "count": max(nav_row_count, realized_trade_count),
            "nav_row_count": nav_row_count,
            "realized_pnl_total": realized_pnl_total,
            "trade_expectancy": trade_expectancy,
            "pnl_conversion_efficiency": execution_quality.get("pnl_conversion_efficiency"),
            "execution_conversion_efficiency": execution_quality.get("execution_conversion_efficiency"),
            "execution_audit_gate_status": execution_audit_gate_status,
        },
        "gate_decisions": {
            "execution_audit_gate_status": execution_audit_gate_status,
            "promotion_ready": bool(item.get("promotion_ready") or dict(item.get("hard_gate_result") or {}).get("promotion_ready")),
            "hard_gate_passed": bool(
                dict(item.get("hard_gate_result") or {}).get("passed")
                or item.get("execution_hard_gate_passed")
            ),
            "failure_reasons": failure_reasons,
        },
        "evidence_gap_codes": evidence_gap_codes,
    }
    if not trace_id:
        result["evidence_gap_codes"] = _compact_list([*result["evidence_gap_codes"], "missing_prediction_trace_id"], limit=16)
    if not bool(result["signal_event"]["available"]):
        result["evidence_gap_codes"] = _compact_list([*result["evidence_gap_codes"], "missing_signal_event"], limit=16)
    if not bool(result["intended_order"]["available"]):
        result["evidence_gap_codes"] = _compact_list([*result["evidence_gap_codes"], "missing_intended_order"], limit=16)
    if not bool(result["actual_fill"]["available"]):
        result["evidence_gap_codes"] = _compact_list([*result["evidence_gap_codes"], "missing_actual_fill"], limit=16)
    if not bool(result["position_round_trip"]["available"]):
        result["evidence_gap_codes"] = _compact_list([*result["evidence_gap_codes"], "missing_position_round_trip"], limit=16)
    if not bool(result["pnl_audit_summary"]["available"]):
        result["evidence_gap_codes"] = _compact_list([*result["evidence_gap_codes"], "missing_pnl_audit_summary"], limit=16)
    return result


def _build_prediction_trace_ledger(
    *,
    candidates: list[dict[str, Any]] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_items = [dict(item or {}) for item in list(candidates or []) if isinstance(item, dict)]
    strategy_items = [dict(item or {}) for item in list(dict(submit_result or {}).get("strategies") or []) if isinstance(item, dict)]
    all_items = [*candidate_items, *strategy_items]
    entries_by_trace: dict[str, dict[str, Any]] = {}
    missing_trace_count = 0
    for index, item in enumerate(all_items):
        trace_id = _candidate_prediction_trace_id(item) or _string(item.get("prediction_trace_id") or item.get("trace_id"))
        entry_key = trace_id or f"missing:{index}"
        if not trace_id:
            missing_trace_count += 1
        entry = entries_by_trace.setdefault(entry_key, _prediction_trace_entry_template(trace_id or None))
        entry["source_count"] = _safe_int(entry.get("source_count")) + 1
        for artifact_id in _candidate_artifact_ids(item):
            if artifact_id not in entry["artifact_ids"]:
                entry["artifact_ids"].append(artifact_id)
        for context_id in _candidate_retrieval_context_ids(item):
            if context_id not in entry["retrieval_context_ids"]:
                entry["retrieval_context_ids"].append(context_id)

        family_summary = _family_outcome_summary([item])
        for bucket_name in ("family_counts", "status_counts", "submission_lane_counts"):
            bucket = dict(entry["family_outcome_summary"].get(bucket_name) or {})
            for key, value in dict(family_summary.get(bucket_name) or {}).items():
                bucket[key] = bucket.get(key, 0) + _safe_int(value)
            entry["family_outcome_summary"][bucket_name] = bucket

        strategy_ledger = dict(item.get("prediction_trace_ledger") or {})
        incoming_entry = (
            {
                "prediction_trace_id": _string(strategy_ledger.get("prediction_trace_id")) or trace_id or None,
                "hypothesis_spec": strategy_ledger.get("hypothesis_spec"),
                "signal_event": strategy_ledger.get("signal_event"),
                "intended_order": strategy_ledger.get("intended_order"),
                "actual_fill": strategy_ledger.get("actual_fill"),
                "position_round_trip": strategy_ledger.get("position_round_trip"),
                "pnl_audit_summary": strategy_ledger.get("pnl_audit_summary"),
                "gate_decisions": strategy_ledger.get("gate_decisions"),
                "evidence_gap_codes": list(strategy_ledger.get("evidence_gap_codes") or []),
            }
            if strategy_ledger
            else _build_prediction_trace_ledger_fallback_entry(item)
        )
        if incoming_entry.get("prediction_trace_id") and not entry.get("prediction_trace_id"):
            entry["prediction_trace_id"] = incoming_entry.get("prediction_trace_id")
        for node_name in (
            "hypothesis_spec",
            "signal_event",
            "intended_order",
            "actual_fill",
            "position_round_trip",
            "pnl_audit_summary",
        ):
            entry[node_name] = _merge_prediction_trace_node(entry.get(node_name), incoming_entry.get(node_name))
        entry["gate_decisions"] = _merge_prediction_trace_gate_decisions(
            entry.get("gate_decisions"),
            incoming_entry.get("gate_decisions"),
        )
        entry["evidence_gap_codes"] = _compact_list(
            [*list(entry.get("evidence_gap_codes") or []), *list(incoming_entry.get("evidence_gap_codes") or [])],
            limit=16,
        )

    entries: list[dict[str, Any]] = []
    for entry in entries_by_trace.values():
        if not entry.get("prediction_trace_id") and "missing_prediction_trace_id" not in entry["evidence_gap_codes"]:
            entry["evidence_gap_codes"].append("missing_prediction_trace_id")
        if not bool(dict(entry.get("signal_event") or {}).get("available")):
            entry["evidence_gap_codes"].append("missing_signal_event")
        if not bool(dict(entry.get("intended_order") or {}).get("available")):
            entry["evidence_gap_codes"].append("missing_intended_order")
        if not bool(dict(entry.get("actual_fill") or {}).get("available")):
            entry["evidence_gap_codes"].append("missing_actual_fill")
        if not bool(dict(entry.get("position_round_trip") or {}).get("available")):
            entry["evidence_gap_codes"].append("missing_position_round_trip")
        if not bool(dict(entry.get("pnl_audit_summary") or {}).get("available")):
            entry["evidence_gap_codes"].append("missing_pnl_audit_summary")
        entry["evidence_gap_codes"] = _compact_list(entry.get("evidence_gap_codes") or [], limit=16)
        entry["artifact_ids"] = _compact_list(entry.get("artifact_ids") or [], limit=16)
        entry["retrieval_context_ids"] = _compact_list(entry.get("retrieval_context_ids") or [], limit=16)
        entry["gate_decisions"] = _normalize_prediction_trace_gate_decisions(entry.get("gate_decisions"))
        entries.append(entry)

    entries.sort(key=lambda item: (_string(item.get("prediction_trace_id")) == "", _string(item.get("prediction_trace_id"))))
    return {
        "contract_version": PREDICTION_TRACE_LEDGER_CONTRACT_VERSION,
        "trace_count": len(entries_by_trace),
        "missing_trace_count": missing_trace_count,
        "entries": entries[:24],
    }


def build_gate_artifact_v2(
    *,
    candidates: list[dict[str, Any]] | None = None,
    quality_gate_report: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_a = build_gate_a_artifact(
        candidates=candidates,
        quality_gate_report=quality_gate_report,
    )
    gate_b = build_gate_b_artifact(
        quality_gate_report=quality_gate_report,
        backtest_report=backtest_report,
        submit_result=submit_result,
    )
    gate_c = build_gate_c_artifact(
        submit_result=submit_result,
    )
    return {
        "contract_version": GATE_ARTIFACT_V2_CONTRACT_VERSION,
        "available": any(
            gate.get("status") not in {"pending", ""}
            for gate in (gate_a, gate_b, gate_c)
        ),
        "gate_a": gate_a,
        "gate_b": gate_b,
        "gate_c": gate_c,
        "legacy_gate_mapping": _legacy_gate_mapping(
            quality_gate_report=quality_gate_report,
            submit_result=submit_result,
        ),
        "protocol_versions": _build_protocol_version_summary(
            candidates=candidates,
            submit_result=submit_result,
        ),
        "prediction_trace_summary": _build_prediction_trace_summary(
            candidates=candidates,
            submit_result=submit_result,
        ),
        "prediction_trace_ledger": _build_prediction_trace_ledger(
            candidates=candidates,
            submit_result=submit_result,
        ),
    }
