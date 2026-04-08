"""Governance plane artifact contracts for strategy factory runs.

P2 goal: make gates, dedup, submission, and governance evidence observable as
an explicit governance plane instead of remaining an implicit by-product of the
submission pipeline.
"""

from __future__ import annotations

from typing import Any

GOVERNANCE_PLANE_CONTRACT_VERSION = "strategy_factory.governance_plane.v1"
GATE_ARTIFACT_CONTRACT_VERSION = "strategy_factory.gate_artifact.v1"
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


def _compact_committee_review(value: Any) -> dict[str, Any]:
    payload = dict(value or {})
    if not payload:
        return {}
    result = _compact_mapping(
        payload,
        allowed_keys=(
            "decision",
            "final_score",
            "rank",
            "is_champion",
            "execution_score",
            "capacity_score",
            "task_alignment_score",
            "novelty_score",
        ),
        limit=8,
    )
    for key in ("alignment_issues", "execution_issues", "capacity_issues", "accept_blockers"):
        items = _compact_list(payload.get(key), limit=4)
        if items:
            result[key] = items
    return result


def _strategy_brief(strategy: dict[str, Any]) -> dict[str, Any]:
    payload = dict(strategy or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or {})
    constraint_check = _compact_mapping(
        payload.get("constraint_check"),
        allowed_keys=(
            "constraint_violation",
            "intersection_ratio",
            "expansion_applied",
            "expansion_reason",
            "expansion_source",
            "alignment_contract_violation",
        ),
        limit=6,
    )
    validation_profile = _compact_mapping(
        payload.get("validation_profile"),
        allowed_keys=("profile", "validation_focus", "primary_validation_layer"),
        limit=3,
    )
    event_window_config = _compact_mapping(payload.get("event_window_config"), limit=6)
    cost_assumptions = _compact_mapping(payload.get("cost_assumptions"), limit=6)
    explicit_cost_breakdown = _compact_mapping(payload.get("explicit_cost_breakdown"), limit=6)
    implicit_cost_breakdown = _compact_mapping(payload.get("implicit_cost_breakdown"), limit=6)
    attempt_adjustment = _compact_mapping(
        payload.get("attempt_adjustment"),
        allowed_keys=("attempt_count", "selected_count", "selection_ratio", "penalty", "applied"),
        limit=5,
    )
    primary_validation_layer = (
        _string(payload.get("primary_validation_layer"))
        or _string(validation_profile.get("primary_validation_layer"))
        or None
    )
    refresh_mode = _string(payload.get("refresh_mode")) or None
    position_assumption = _string(payload.get("position_assumption")) or None
    task_signature = _string(payload.get("task_signature")) or None
    committee_review = _compact_committee_review(payload.get("committee_review"))
    return {
        "strategy_id": _string(payload.get("strategy_id")) or None,
        "name": _string(payload.get("name")) or None,
        "status": _string(payload.get("status")) or None,
        "submission_lane": _string(payload.get("submission_lane")) or None,
        "submission_action_type": _string(payload.get("submission_action_type")) or None,
        "primary_validation_layer": primary_validation_layer,
        "refresh_mode": refresh_mode,
        "position_assumption": position_assumption,
        "task_signature": task_signature,
        "candidate_family": (
            _string(payload.get("candidate_family"))
            or _string(candidate_provenance.get("candidate_family"))
            or None
        ),
        "generator_mode": (
            _string(payload.get("generator_mode"))
            or _string(candidate_provenance.get("generator_mode"))
            or None
        ),
        "source_candidate_artifact_id": _string(payload.get("source_candidate_artifact_id")) or None,
        "target_pool_id": _string(payload.get("target_pool_id")) or None,
        "vector_profile_id": _string(payload.get("vector_profile_id")) or None,
        "multiple_testing_registry_record_id": (
            _string(payload.get("multiple_testing_registry_record_id")) or None
        ),
        "constraint_check": constraint_check,
        "validation_profile": validation_profile,
        "event_window_config": event_window_config,
        "cost_assumptions": cost_assumptions,
        "explicit_cost_breakdown": explicit_cost_breakdown,
        "implicit_cost_breakdown": implicit_cost_breakdown,
        "attempt_adjustment": attempt_adjustment,
        "committee_review": committee_review,
        "has_constraint_check": bool(constraint_check),
        "has_validation_profile": bool(validation_profile),
        "has_event_window_config": bool(event_window_config),
        "has_cost_assumptions": bool(cost_assumptions),
        "has_explicit_cost_breakdown": bool(explicit_cost_breakdown),
        "has_implicit_cost_breakdown": bool(implicit_cost_breakdown),
        "has_attempt_adjustment": bool(attempt_adjustment),
        "has_committee_review": bool(committee_review),
        "created_strategy_pool": bool(payload.get("created_strategy_pool")),
        "created_audit_only": bool(payload.get("created_audit_only")),
        "refreshed_existing": bool(payload.get("refreshed_existing")),
        "live_candidate_ready": bool(payload.get("live_candidate_ready")),
        "live_review_ready": bool(payload.get("live_review_ready")),
        "direct_trade_candidate": bool(payload.get("direct_trade_candidate")),
    }


def _dedup_brief(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate or {})
    dedup = dict(payload.get("dedup_result") or {})
    profile = dict(payload.get("strategy_profile") or {})
    return {
        "strategy_type": _string(payload.get("strategy_type")) or None,
        "generator_type": _string(payload.get("generator_type")) or None,
        "candidate_family_id": (
            _string(payload.get("candidate_family_id"))
            or _string(profile.get("candidate_family_id"))
            or None
        ),
        "target_symbols": _compact_list(payload.get("target_symbols"), limit=12),
        "duplicate": bool(dedup.get("duplicate")),
        "duplicate_level": _string(dedup.get("duplicate_level")) or None,
        "refresh_existing": bool(dedup.get("refresh_existing")),
        "refresh_mode": _string(dedup.get("refresh_mode")) or None,
        "matched_strategy_id": _string(dedup.get("matched_strategy_id")) or None,
        "refresh_decision_basis": _string(dedup.get("refresh_decision_basis")) or None,
        "revision_trigger_reason": _string(dedup.get("revision_trigger_reason")) or None,
        "target_overlap": round(_safe_float(dedup.get("target_overlap")), 4),
    }


def build_gate_artifact(
    *,
    quality_gate_report: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    quality = dict(quality_gate_report or {})
    backtest = dict(backtest_report or {})
    backtest_summary = dict(backtest.get("summary") or {})
    gate_0 = dict(quality.get("gate_0") or {})
    pre_gate = dict(quality.get("pre_gate") or {})
    gate_1 = dict(quality.get("gate_1") or {})
    gate_2 = dict(quality.get("gate_2") or {})
    gate_3 = dict(quality.get("gate_3") or {})
    return {
        "contract_version": GATE_ARTIFACT_CONTRACT_VERSION,
        "available": bool(quality or backtest),
        "gate_0_passed": _safe_int(gate_0.get("passed_count")),
        "gate_0_failed": _safe_int(gate_0.get("failed_count")),
        "pre_gate_passed": _safe_int(pre_gate.get("passed_count")),
        "pre_gate_failed": _safe_int(pre_gate.get("failed_count")),
        "gate_1_passed": _safe_int(gate_1.get("passed_count")),
        "gate_1_failed": _safe_int(gate_1.get("failed_count")),
        "gate_2_input": _safe_int(gate_2.get("input_count"), _safe_int(backtest_summary.get("input_count"))),
        "gate_2_passed": _safe_int(gate_2.get("passed_count"), _safe_int(backtest_summary.get("passed_count"))),
        "gate_2_failed": _safe_int(gate_2.get("failed_count"), _safe_int(backtest_summary.get("failed_count"))),
        "gate_3_input": _safe_int(gate_3.get("input_count")),
        "gate_3_pending_count": _safe_int(gate_3.get("pending_count")),
        "gate_3_passed": _safe_int(gate_3.get("passed_count")),
        "gate_3_failed": _safe_int(gate_3.get("failed_count")),
        "gate_3_provisional_passed": _safe_int(gate_3.get("provisional_passed_count")),
        "backtest_failed_reason_counts": dict(backtest_summary.get("failed_reason_counts") or {}),
        "backtest_thresholds_by_type": dict(backtest_summary.get("thresholds_by_type") or {}),
        "gate_3_failure_reason_topn": _compact_reason_topn(gate_3.get("failure_reason_topn")),
    }


def build_dedup_artifact(
    *,
    dedup_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = dict(dedup_report or {})
    summary = dict(report.get("summary") or {})
    kept = [dict(item or {}) for item in list(report.get("kept") or []) if isinstance(item, dict)]
    dropped = [dict(item or {}) for item in list(report.get("dropped") or []) if isinstance(item, dict)]
    refresh_mode_counts = _count_by([*kept, *dropped], lambda item: dict(item.get("dedup_result") or {}).get("refresh_mode"))
    duplicate_level_counts = _count_by(
        dropped,
        lambda item: dict(item.get("dedup_result") or {}).get("duplicate_level"),
    )
    return {
        "contract_version": DEDUP_ARTIFACT_CONTRACT_VERSION,
        "available": bool(report),
        "input_count": _safe_int(summary.get("input_count")),
        "existing_count": _safe_int(summary.get("existing_count")),
        "existing_scan_count": _safe_int(summary.get("existing_scan_count")),
        "kept_count": _safe_int(summary.get("kept_count"), len(kept)),
        "dropped_count": _safe_int(summary.get("dropped_count"), len(dropped)),
        "refreshed_existing_count": _safe_int(summary.get("refreshed_existing_count")),
        "vector_checks": _safe_int(summary.get("vector_checks")),
        "coarse_hit_ratio": round(_safe_float(summary.get("coarse_hit_ratio")), 4),
        "refresh_mode_counts": refresh_mode_counts,
        "duplicate_level_counts": duplicate_level_counts,
        "refresh_decision_basis_counts": dict(summary.get("refresh_decision_basis_counts") or {}),
        "revision_trigger_reason_counts": dict(summary.get("revision_trigger_reason_counts") or {}),
        "tested_object_hash_changed_count": _safe_int(summary.get("tested_object_hash_changed_count")),
        "existing_identity_available_count": _safe_int(summary.get("existing_identity_available_count")),
        "existing_tested_object_available_count": _safe_int(
            summary.get("existing_tested_object_available_count")
        ),
        "kept_briefs": [_dedup_brief(item) for item in kept[:12]],
        "dropped_briefs": [_dedup_brief(item) for item in dropped[:12]],
    }


def build_submission_artifact(
    *,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(submit_result or {})
    strategies = [dict(item or {}) for item in list(payload.get("strategies") or []) if isinstance(item, dict)]
    submission_lane_counts = _count_by(strategies, lambda item: item.get("submission_lane"))
    submission_action_type_counts = _count_by(strategies, lambda item: item.get("submission_action_type"))
    strategy_status_counts = _count_by(strategies, lambda item: item.get("status"))
    committee_decision_counts = _count_by(strategies, _committee_decision)
    refresh_mode_counts = _count_by(strategies, lambda item: item.get("refresh_mode"))
    primary_validation_layer_counts = _count_by(strategies, _primary_validation_layer)
    validation_profile_counts = _count_by(strategies, _validation_profile_name)
    constraint_violation_counts = _count_by(strategies, _constraint_violation)
    committee_review_count = sum(1 for item in strategies if _has_mapping(item, "committee_review"))
    constraint_check_count = sum(1 for item in strategies if _has_mapping(item, "constraint_check"))
    validation_profile_count = sum(1 for item in strategies if _has_mapping(item, "validation_profile"))
    event_window_config_count = sum(1 for item in strategies if _has_mapping(item, "event_window_config"))
    position_assumption_count = sum(1 for item in strategies if _has_text(item, "position_assumption"))
    cost_assumptions_count = sum(1 for item in strategies if _has_mapping(item, "cost_assumptions"))
    explicit_cost_breakdown_count = sum(
        1 for item in strategies if _has_mapping(item, "explicit_cost_breakdown")
    )
    implicit_cost_breakdown_count = sum(
        1 for item in strategies if _has_mapping(item, "implicit_cost_breakdown")
    )
    attempt_adjustment_count = sum(1 for item in strategies if _has_mapping(item, "attempt_adjustment"))
    task_signature_count = sum(1 for item in strategies if _has_text(item, "task_signature"))
    return {
        "contract_version": SUBMISSION_ARTIFACT_CONTRACT_VERSION,
        "available": bool(payload),
        "strategy_count": len(strategies),
        "created_count": _safe_int(payload.get("created")),
        "created_total_count": _safe_int(payload.get("created_total")),
        "created_strategy_pool_count": _safe_int(payload.get("created_strategy_pool")),
        "created_audit_only_count": _safe_int(payload.get("created_audit_only")),
        "refreshed_count": _safe_int(payload.get("refreshed")),
        "gate_3_input": _safe_int(payload.get("gate_3_input")),
        "submitted_count": _safe_int(payload.get("submitted")),
        "passed_quality_gate_count": _safe_int(payload.get("passed_quality_gate")),
        "gate_3_passed": _safe_int(payload.get("gate_3_passed")),
        "gate_3_failed": _safe_int(payload.get("gate_3_failed")),
        "gate_3_provisional_passed": _safe_int(payload.get("gate_3_provisional_passed")),
        "incubation_budget_summary": dict(payload.get("incubation_budget_summary") or {}),
        "gate_3_failure_reason_topn": _compact_reason_topn(payload.get("gate_3_failure_reason_topn")),
        "submission_lane_counts": submission_lane_counts,
        "submission_action_type_counts": submission_action_type_counts,
        "strategy_status_counts": strategy_status_counts,
        "committee_decision_counts": committee_decision_counts,
        "refresh_mode_counts": refresh_mode_counts,
        "committee_review_count": committee_review_count,
        "primary_validation_layer_counts": primary_validation_layer_counts,
        "validation_profile_counts": validation_profile_counts,
        "constraint_violation_counts": constraint_violation_counts,
        "constraint_check_count": constraint_check_count,
        "validation_profile_count": validation_profile_count,
        "event_window_config_count": event_window_config_count,
        "position_assumption_count": position_assumption_count,
        "cost_assumptions_count": cost_assumptions_count,
        "explicit_cost_breakdown_count": explicit_cost_breakdown_count,
        "implicit_cost_breakdown_count": implicit_cost_breakdown_count,
        "attempt_adjustment_count": attempt_adjustment_count,
        "task_signature_count": task_signature_count,
        "strategy_briefs": [_strategy_brief(item) for item in strategies[:12]],
    }


def build_governance_evidence_artifact(
    *,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(submit_result or {})
    strategies = [dict(item or {}) for item in list(payload.get("strategies") or []) if isinstance(item, dict)]

    def _has_numeric(item: dict[str, Any], key: str) -> bool:
        source = dict(item.get("backtest_assumptions") or {})
        cost = dict(item.get("cost_assumptions") or {})
        if source.get(key) is not None or cost.get(key) is not None:
            return True
        return False

    vector_backend_counts = _count_by(
        strategies,
        lambda item: item.get("vector_backend_used") or item.get("vector_backend"),
    )
    quality_report_count = len(strategies)
    multiple_testing_registry_count = sum(1 for item in strategies if _has_mapping(item, "multiple_testing_registry"))
    multiple_testing_registry_record_count = sum(
        1 for item in strategies if _string(item.get("multiple_testing_registry_record_id"))
    )
    lineage_contract_count = sum(1 for item in strategies if _has_mapping(item, "candidate_lineage_contract"))
    lineage_id_count = sum(
        1
        for item in strategies
        if _string(dict(item.get("candidate_lineage_contract") or {}).get("lineage_id"))
    )
    committee_review_count = sum(1 for item in strategies if _has_mapping(item, "committee_review"))
    constraint_check_count = sum(1 for item in strategies if _has_mapping(item, "constraint_check"))
    validation_profile_count = sum(1 for item in strategies if _has_mapping(item, "validation_profile"))
    event_window_config_count = sum(1 for item in strategies if _has_mapping(item, "event_window_config"))
    position_assumption_count = sum(1 for item in strategies if _has_text(item, "position_assumption"))
    vector_profile_count = sum(1 for item in strategies if _string(item.get("vector_profile_id")))
    cost_assumptions_count = sum(1 for item in strategies if _has_mapping(item, "cost_assumptions"))
    explicit_cost_breakdown_count = sum(1 for item in strategies if _has_mapping(item, "explicit_cost_breakdown"))
    implicit_cost_breakdown_count = sum(1 for item in strategies if _has_mapping(item, "implicit_cost_breakdown"))
    execution_reality_count = sum(1 for item in strategies if _has_mapping(item, "execution_reality"))
    attempt_adjustment_count = sum(1 for item in strategies if _has_mapping(item, "attempt_adjustment"))
    task_signature_count = sum(1 for item in strategies if _has_text(item, "task_signature"))
    refresh_mode_count = sum(1 for item in strategies if _has_text(item, "refresh_mode"))
    primary_validation_layer_count = sum(1 for item in strategies if bool(_primary_validation_layer(item)))
    slippage_assumption_count = sum(1 for item in strategies if _has_numeric(item, "slippage_bps"))
    market_impact_assumption_count = sum(1 for item in strategies if _has_numeric(item, "market_impact_bps"))
    capacity_assumption_count = sum(
        1
        for item in strategies
        if dict(item.get("backtest_assumptions") or {}).get("capacity_participation_rate") is not None
        or _string(dict(item.get("backtest_assumptions") or {}).get("capacity_bucket"))
    )
    tradability_filter_count = sum(
        1
        for item in strategies
        if dict(item.get("backtest_assumptions") or {}).get("tradability_filter") is not None
    )
    evidence_briefs = [
        {
            **_strategy_brief(item),
            "lineage_id": _string(dict(item.get("candidate_lineage_contract") or {}).get("lineage_id")) or None,
            "vector_backend": (
                _string(item.get("vector_backend_used"))
                or _string(item.get("vector_backend"))
                or None
            ),
            "has_cost_assumptions": _has_mapping(item, "cost_assumptions"),
            "has_execution_reality": _has_mapping(item, "execution_reality"),
            "has_multiple_testing_registry": _has_mapping(item, "multiple_testing_registry"),
        }
        for item in strategies[:12]
    ]
    return {
        "contract_version": GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
        "available": bool(strategies),
        "quality_report_count": quality_report_count,
        "multiple_testing_registry_count": multiple_testing_registry_count,
        "multiple_testing_registry_record_count": multiple_testing_registry_record_count,
        "lineage_contract_count": lineage_contract_count,
        "lineage_id_count": lineage_id_count,
        "committee_review_count": committee_review_count,
        "constraint_check_count": constraint_check_count,
        "validation_profile_count": validation_profile_count,
        "event_window_config_count": event_window_config_count,
        "position_assumption_count": position_assumption_count,
        "vector_profile_count": vector_profile_count,
        "vector_backend_counts": vector_backend_counts,
        "cost_assumptions_count": cost_assumptions_count,
        "explicit_cost_breakdown_count": explicit_cost_breakdown_count,
        "implicit_cost_breakdown_count": implicit_cost_breakdown_count,
        "execution_reality_count": execution_reality_count,
        "attempt_adjustment_count": attempt_adjustment_count,
        "task_signature_count": task_signature_count,
        "refresh_mode_count": refresh_mode_count,
        "primary_validation_layer_count": primary_validation_layer_count,
        "slippage_assumption_count": slippage_assumption_count,
        "market_impact_assumption_count": market_impact_assumption_count,
        "capacity_assumption_count": capacity_assumption_count,
        "tradability_filter_count": tradability_filter_count,
        "extension_interface_support": {
            "constraint_check_supported": bool(constraint_check_count),
            "validation_profile_supported": bool(validation_profile_count),
            "event_window_supported": bool(event_window_config_count),
            "position_assumption_supported": bool(position_assumption_count),
            "committee_review_supported": bool(committee_review_count),
            "cost_assumptions_supported": bool(cost_assumptions_count),
            "execution_reality_supported": bool(execution_reality_count),
            "attempt_adjustment_supported": bool(attempt_adjustment_count),
            "task_signature_supported": bool(task_signature_count),
            "refresh_mode_supported": bool(refresh_mode_count),
            "primary_validation_layer_supported": bool(primary_validation_layer_count),
            "slippage_supported": bool(slippage_assumption_count),
            "market_impact_supported": bool(market_impact_assumption_count),
            "capacity_supported": bool(capacity_assumption_count),
            "tradability_filter_supported": bool(tradability_filter_count),
        },
        "strategy_evidence_briefs": evidence_briefs,
    }


def build_governance_plane_artifact(
    *,
    quality_gate_report: dict[str, Any] | None = None,
    backtest_report: dict[str, Any] | None = None,
    dedup_report: dict[str, Any] | None = None,
    submit_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate_artifact = build_gate_artifact(
        quality_gate_report=quality_gate_report,
        backtest_report=backtest_report,
    )
    dedup_artifact = build_dedup_artifact(
        dedup_report=dedup_report,
    )
    submission_artifact = build_submission_artifact(
        submit_result=submit_result,
    )
    evidence_artifact = build_governance_evidence_artifact(
        submit_result=submit_result,
    )
    available = any(
        bool(item.get("available"))
        for item in (
            gate_artifact,
            dedup_artifact,
            submission_artifact,
            evidence_artifact,
        )
    )
    source_chain: list[str] = []
    if gate_artifact.get("available"):
        source_chain.append("governance.gate_artifact")
    if dedup_artifact.get("available"):
        source_chain.append("governance.dedup_artifact")
    if submission_artifact.get("available"):
        source_chain.append("governance.submission_artifact")
    if evidence_artifact.get("available"):
        source_chain.append("governance.evidence_artifact")
    return {
        "contract_version": GOVERNANCE_PLANE_CONTRACT_VERSION,
        "available": available,
        "plane": "governance",
        "gate_artifact": gate_artifact,
        "dedup_artifact": dedup_artifact,
        "submission_artifact": submission_artifact,
        "evidence_artifact": evidence_artifact,
        "source_chain": source_chain,
    }


__all__ = [
    "DEDUP_ARTIFACT_CONTRACT_VERSION",
    "GATE_ARTIFACT_CONTRACT_VERSION",
    "GOVERNANCE_EVIDENCE_ARTIFACT_CONTRACT_VERSION",
    "GOVERNANCE_PLANE_CONTRACT_VERSION",
    "SUBMISSION_ARTIFACT_CONTRACT_VERSION",
    "build_dedup_artifact",
    "build_gate_artifact",
    "build_governance_evidence_artifact",
    "build_governance_plane_artifact",
    "build_submission_artifact",
]
