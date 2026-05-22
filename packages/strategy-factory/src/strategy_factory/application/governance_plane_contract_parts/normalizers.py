
from __future__ import annotations

from typing import Any

GOVERNANCE_PLANE_CONTRACT_VERSION = "strategy_factory.governance_plane.v1"
GATE_ARTIFACT_CONTRACT_VERSION = "strategy_factory.gate_artifact.v1"
GOVERNANCE_PLANE_V2_CONTRACT_VERSION = "strategy_factory.governance_plane.v2"
GATE_ARTIFACT_V2_CONTRACT_VERSION = "strategy_factory.gate_artifact.v2"
PREDICTION_TRACE_CONTRACT_VERSION = "strategy_factory.prediction_trace.v2"
PREDICTION_TRACE_LEDGER_CONTRACT_VERSION = "strategy_factory.prediction_trace_ledger.v2"
DEDUP_ARTIFACT_CONTRACT_VERSION = "strategy_factory.dedup_artifact.v1"
SUBMISSION_ARTIFACT_CONTRACT_VERSION = "strategy_factory.submission_artifact.v1"
GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION = "strategy_factory.governance_evidence_artifact.v1"


def _string(value: Any) -> str:
    return str(value or "").strip()


def _normalized_text(value: Any) -> str:
    return _string(value).lower()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _confidence_contract_status(confidence_contract: dict[str, Any]) -> str | None:
    contract = dict(confidence_contract or {})
    if not contract:
        return None
    prediction_quality = dict(
        contract.get("prediction_quality")
        or contract.get("probability_quality")
        or {}
    )
    support_samples = _safe_int(
        prediction_quality.get("support_samples")
        or prediction_quality.get("sample_size")
        or contract.get("support_samples")
        or contract.get("sample_size"),
        0,
    )
    contract_version = _normalized_text(
        prediction_quality.get("contract_version")
        or contract.get("contract_version")
        or prediction_quality.get("version")
        or contract.get("version")
    )
    explicit_stable = prediction_quality.get("contract_version_stable")
    if explicit_stable is None:
        explicit_stable = contract.get("contract_version_stable")
    version_stable = (
        bool(explicit_stable)
        if explicit_stable is not None
        else bool(contract_version)
        and not any(token in contract_version for token in ("draft", "unstable", "experimental", "preview", "beta", "alpha"))
    )
    if support_samples < 50:
        return "insufficient"
    if support_samples < 100:
        return "diagnostic_ready"
    return "comparable_ready" if version_stable else "diagnostic_ready"


def _compact_list(values: Any, *, limit: int = 8) -> list[str]:
    items: list[str] = []
    for value in list(values or []):
        token = _string(value)
        if token and token not in items:
            items.append(token)
        if len(items) >= limit:
            break
    return items


def _compact_mapping(
    value: Any,
    *,
    allowed_keys: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    payload = dict(value or {})
    if not payload:
        return {}
    items = (
        [(key, payload.get(key)) for key in allowed_keys]
        if allowed_keys is not None
        else list(payload.items())
    )
    result: dict[str, Any] = {}
    for key, raw in items:
        if raw in (None, "", [], {}):
            continue
        result[key] = raw
        if limit is not None and len(result) >= limit:
            break
    return result


def _candidate_payload_value(candidate: dict[str, Any], key: str, default: Any = None) -> Any:
    payload = dict(candidate or {})
    if key in payload and payload.get(key) is not None:
        return payload.get(key)
    params = dict(payload.get("params") or {})
    if key in params and params.get(key) is not None:
        return params.get(key)
    return default


def _candidate_prediction_trace_id(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    return _string(
        payload.get("prediction_trace_id")
        or payload.get("trace_id")
        or _candidate_payload_value(payload, "prediction_trace_id")
        or _candidate_payload_value(payload, "trace_id")
    )


def _candidate_trace_ids(candidate: dict[str, Any]) -> list[str]:
    trace_id = _candidate_prediction_trace_id(candidate)
    return [trace_id] if trace_id else []


def _candidate_research_protocol_version(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    contract = dict(
        payload.get("research_validation_contract")
        or _candidate_payload_value(payload, "research_validation_contract")
        or {}
    )
    return _string(
        payload.get("research_protocol_version")
        or _candidate_payload_value(payload, "research_protocol_version")
        or contract.get("contract_version")
    )


def _candidate_contract_version(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    return _string(
        payload.get("candidate_contract_version")
        or _candidate_payload_value(payload, "candidate_contract_version")
    )


def _candidate_spec_completeness(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    contract = dict(
        payload.get("research_validation_contract")
        or _candidate_payload_value(payload, "research_validation_contract")
        or {}
    )
    return _string(
        payload.get("spec_completeness")
        or _candidate_payload_value(payload, "spec_completeness")
        or contract.get("spec_completeness")
    )


def _candidate_field_provenance_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate or {})
    contract = dict(
        payload.get("research_validation_contract")
        or _candidate_payload_value(payload, "research_validation_contract")
        or {}
    )
    return _compact_mapping(
        payload.get("field_provenance_summary")
        or _candidate_payload_value(payload, "field_provenance_summary")
        or contract.get("field_provenance_summary")
        or {},
    )


def _candidate_family(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or params.get("candidate_provenance") or {})
    return _normalized_text(
        candidate_provenance.get("candidate_family")
        or payload.get("candidate_family")
        or params.get("candidate_family")
        or payload.get("strategy_type")
    )


def _candidate_artifact_ids(candidate: dict[str, Any]) -> list[str]:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or params.get("candidate_provenance") or {})
    return _compact_list(
        [
            payload.get("strategy_id"),
            payload.get("id"),
            payload.get("source_candidate_artifact_id"),
            payload.get("source_generation_artifact_id"),
            payload.get("source_validation_artifact_id"),
            payload.get("candidate_memory_record_id"),
            payload.get("hypothesis_artifact_id"),
            payload.get("multiple_testing_registry_record_id"),
            payload.get("vector_profile_id"),
            payload.get("paper_account_id"),
            payload.get("incubation_account_id"),
            payload.get("promotion_review_id"),
            candidate_provenance.get("source_candidate_artifact_id"),
            candidate_provenance.get("source_generation_artifact_id"),
            candidate_provenance.get("source_validation_artifact_id"),
            candidate_provenance.get("memory_record_id"),
            params.get("source_candidate_artifact_id"),
            params.get("source_generation_artifact_id"),
            params.get("source_validation_artifact_id"),
            params.get("candidate_memory_record_id"),
            params.get("multiple_testing_registry_record_id"),
            params.get("vector_profile_id"),
        ],
        limit=16,
    )


def _candidate_retrieval_context_ids(candidate: dict[str, Any]) -> list[str]:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or params.get("candidate_provenance") or {})
    research_task = dict(payload.get("research_task") or params.get("research_task") or {})
    return _compact_list(
        [
            research_task.get("task_id"),
            research_task.get("event_id"),
            payload.get("task_run_id"),
            payload.get("multiple_testing_registry_record_id"),
            payload.get("candidate_memory_record_id"),
            payload.get("vector_profile_id"),
            candidate_provenance.get("memory_record_id"),
            params.get("task_run_id"),
            params.get("multiple_testing_registry_record_id"),
            params.get("candidate_memory_record_id"),
            params.get("vector_profile_id"),
        ],
        limit=16,
    )


def _normalize_hard_failure_entry(
    reason_code: Any,
    *,
    issue: str,
    field: Any = None,
    detail: Any = None,
) -> dict[str, Any] | None:
    code = _string(reason_code)
    field_name = _string(field)
    if not code:
        return None
    payload = {
        "reason_code": code,
        "issue": issue,
        "severity": "reject",
        "decision": "reject",
    }
    if field_name:
        payload["field"] = field_name
    if _string(detail):
        payload["detail"] = _string(detail)
    return payload


def _unique_hard_failures(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(entries or []):
        payload = dict(item or {})
        reason_code = _string(payload.get("reason_code"))
        field_name = _string(payload.get("field"))
        if not reason_code:
            continue
        dedupe_key = (field_name, reason_code)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(payload)
    return unique


def _family_outcome_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    family_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    for item in list(items or []):
        family = _candidate_family(item)
        if family:
            family_counts[family] = family_counts.get(family, 0) + 1
        status = _normalized_text(item.get("status") or item.get("final_status"))
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
        lane = _normalized_text(item.get("submission_lane"))
        if lane:
            lane_counts[lane] = lane_counts.get(lane, 0) + 1
    return {
        "family_counts": family_counts,
        "status_counts": status_counts,
        "submission_lane_counts": lane_counts,
    }


def _top_counts(counts: dict[str, int], *, label_key: str = "name", limit: int = 5) -> list[dict[str, Any]]:
    items = [
        {label_key: _string(name), "count": _safe_int(count)}
        for name, count in dict(counts or {}).items()
        if _string(name) and _safe_int(count) > 0
    ]
    items.sort(key=lambda item: (-_safe_int(item.get("count")), _string(item.get(label_key))))
    return items[: max(1, int(limit or 5))]


def _count_by(items: list[dict[str, Any]], resolver) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in list(items or []):
        key = _normalized_text(resolver(dict(item or {})))
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _compact_reason_topn(items: Any, *, limit: int = 5) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(items or [])[:limit]:
        payload = dict(item or {})
        reason = _string(payload.get("reason_code") or payload.get("reason"))
        if not reason:
            continue
        result.append(
            {
                "reason": reason,
                "count": _safe_int(payload.get("count"), 0),
            }
        )
    return result


def _has_mapping(item: dict[str, Any], key: str) -> bool:
    return bool(_compact_mapping(dict(item or {}).get(key)))


def _has_text(item: dict[str, Any], key: str) -> bool:
    return bool(_string(dict(item or {}).get(key)))


def _primary_validation_layer(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    validation_profile = dict(payload.get("validation_profile") or {})
    return _string(payload.get("primary_validation_layer") or validation_profile.get("primary_validation_layer"))


def _validation_profile_name(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    validation_profile = dict(payload.get("validation_profile") or {})
    return _string(validation_profile.get("profile"))


def _constraint_violation(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    constraint_check = dict(payload.get("constraint_check") or {})
    return _string(constraint_check.get("constraint_violation"))


def _committee_decision(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    committee_review = dict(payload.get("committee_review") or {})
    return _string(committee_review.get("decision"))


def _candidate_family(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    return _string(
        payload.get("candidate_family")
        or candidate_provenance.get("candidate_family")
        or quality_summary.get("candidate_family")
        or payload.get("strategy_type")
    )


def _holding_bucket(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    return _string(
        payload.get("holding_period_bucket")
        or candidate_provenance.get("holding_period_bucket")
        or quality_summary.get("holding_period_bucket")
    )


def _target_universe_key(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    contract_snapshot = dict(payload.get("candidate_contract_snapshot") or {})
    targeting = dict(contract_snapshot.get("targeting") or {})
    target_pool_id = _string(payload.get("target_pool_id") or targeting.get("target_pool_id"))
    if target_pool_id:
        return target_pool_id
    target_symbols = _compact_list(
        payload.get("target_symbols") or targeting.get("target_symbols"),
        limit=12,
    )
    return ",".join(target_symbols)


def _validation_grade(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    admission_review_context = dict(gate.get("admission_review_context") or {})
    incubation_review_context = dict(
        dict((gate.get("admission_evaluations") or {}).get("incubation") or {}).get("review_context") or {}
    )
    return (
        _string(
            payload.get("validation_grade")
            or quality_summary.get("validation_grade")
            or gate.get("validation_grade")
            or admission_review_context.get("validation_grade")
            or incubation_review_context.get("validation_grade")
        ).upper()
    )


def _raw_validation_grade(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    admission_review_context = dict(gate.get("admission_review_context") or {})
    incubation_review_context = dict(
        dict((gate.get("admission_evaluations") or {}).get("incubation") or {}).get("review_context") or {}
    )
    return (
        _string(
            payload.get("raw_validation_grade")
            or quality_summary.get("raw_validation_grade")
            or gate.get("raw_validation_grade")
            or admission_review_context.get("validation_grade")
            or incubation_review_context.get("validation_grade")
            or payload.get("validation_grade")
            or quality_summary.get("validation_grade")
            or gate.get("validation_grade")
        ).upper()
    )


def _effective_validation_grade(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    admission_review_context = dict(gate.get("admission_review_context") or {})
    incubation_review_context = dict(
        dict((gate.get("admission_evaluations") or {}).get("incubation") or {}).get("review_context") or {}
    )
    return (
        _string(
            payload.get("effective_validation_grade")
            or quality_summary.get("effective_validation_grade")
            or gate.get("effective_validation_grade")
            or payload.get("validation_grade")
            or quality_summary.get("validation_grade")
            or gate.get("validation_grade")
            or admission_review_context.get("validation_grade")
            or incubation_review_context.get("validation_grade")
        ).upper()
    )


def _validation_grade_adjustment_reason(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    trade_quality_adjustment = dict(payload.get("trade_quality_adjustment") or {})
    admission_review_context = dict(gate.get("admission_review_context") or {})
    incubation_review_context = dict(
        dict((gate.get("admission_evaluations") or {}).get("incubation") or {}).get("review_context")
        or {}
    )
    return _string(
        payload.get("validation_grade_adjustment_reason")
        or quality_summary.get("validation_grade_adjustment_reason")
        or gate.get("validation_grade_adjustment_reason")
        or admission_review_context.get("validation_grade_adjustment_reason")
        or incubation_review_context.get("validation_grade_adjustment_reason")
        or trade_quality_adjustment.get("adjustment_reason")
    )


def _validation_focus(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    validation_profile = dict(payload.get("validation_profile") or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    return _string(
        payload.get("validation_focus")
        or validation_profile.get("validation_focus")
        or quality_summary.get("validation_focus")
        or gate.get("validation_focus")
    )


def _validation_total_score(item: dict[str, Any], *, raw: bool) -> float | None:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    keys = (
        (
            "raw_validation_total_score",
            "validation_total_score",
            "raw_total_score",
            "total_score",
            "candidate_validation_score",
        )
        if raw
        else ("validation_total_score", "effective_validation_total_score", "total_score")
    )
    for source in (payload, quality_summary, gate):
        for key in keys:
            value = source.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except Exception:
                continue
    return None


def _bool_payload(item: dict[str, Any], *keys: str) -> bool:
    payload = dict(item or {})
    quality_summary = dict(payload.get("quality_summary") or {})
    gate = dict(payload.get("gate_3") or {})
    for source in (payload, quality_summary, gate):
        for key in keys:
            if key in source and source.get(key) is not None:
                return bool(source.get(key))
    return False
