"""Research plane artifact contracts for strategy factory runs.

P1 goal: let factor research, task planning, and autonomy execution expose a
stable research-plane output that can be observed independently from the
submission / incubation pipeline.
"""

from __future__ import annotations

from typing import Any

from .services.readiness_service import resolve_governed_pool_state

RESEARCH_PLANE_CONTRACT_VERSION = "strategy_factory.research_plane.v1"
RESEARCH_ARTIFACT_CONTRACT_VERSION = "strategy_factory.research_artifact.v1"
TASK_ARTIFACT_CONTRACT_VERSION = "strategy_factory.task_artifact.v1"
CANDIDATE_ARTIFACT_CONTRACT_VERSION = "strategy_factory.candidate_artifact.v1"
RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION = "strategy_factory.research_evidence_artifact.v1"


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


def _count_by(items: list[dict[str, Any]], resolver) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in list(items or []):
        key = _normalized_text(resolver(dict(item or {})))
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def _resolve_contract_artifact(
    payload: dict[str, Any] | None,
    *,
    expected_version: str,
) -> dict[str, Any]:
    artifact = dict(payload or {})
    if str(artifact.get("contract_version") or "").strip() != expected_version:
        return {}
    return artifact


def _candidate_family(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    research_task = dict(payload.get("research_task") or {})
    params = dict(payload.get("params") or {})
    provenance = dict(params.get("candidate_provenance") or {})
    return (
        _normalized_text(
            payload.get("candidate_family")
            or research_task.get("candidate_family")
            or provenance.get("candidate_family")
            or payload.get("strategy_type")
        )
        or "unknown"
    )


def _candidate_task_source(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    research_task = dict(payload.get("research_task") or {})
    return _normalized_text(research_task.get("task_source") or payload.get("task_source")) or "unknown"


def _candidate_generator_mode(candidate: dict[str, Any]) -> str:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    provenance = dict(params.get("candidate_provenance") or {})
    return (
        _normalized_text(
            payload.get("generator_mode")
            or payload.get("generator_type")
            or provenance.get("generator_mode")
            or provenance.get("generator_type")
        )
        or "unknown"
    )


def _compact_task_brief(task: dict[str, Any]) -> dict[str, Any]:
    payload = dict(task or {})
    return {
        "task_id": _string(payload.get("task_id") or payload.get("task_key")) or None,
        "task_source": _string(payload.get("task_source")) or None,
        "opportunity_type": _string(payload.get("opportunity_type")) or None,
        "candidate_family": _string(payload.get("candidate_family")) or None,
        "factor_name": _string(payload.get("factor_name")) or None,
        "target_symbols": _compact_list(payload.get("target_symbols"), limit=12),
        "generation_limit": _safe_int(payload.get("generation_limit")),
        "event_id": _string(payload.get("event_id")) or None,
        "theme_code": _string(payload.get("theme_code")) or None,
    }


def _compact_task_result_brief(task_result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(task_result or {})
    brief = _compact_task_brief(payload.get("task") or {})
    brief.update(
        {
            "task_run_id": payload.get("task_run_id"),
            "status": _string(payload.get("status")) or None,
            "generated_count": _safe_int(payload.get("generated_count")),
            "reviewed_count": _safe_int(payload.get("reviewed_count")),
            "evidence_count": _safe_int(payload.get("evidence_count")),
            "external_llm_status": _string(payload.get("external_llm_status")) or None,
        }
    )
    return brief


def _compact_candidate_brief(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    provenance = dict(params.get("candidate_provenance") or {})
    contract_snapshot = dict(payload.get("candidate_contract_snapshot") or {})
    targeting = dict(contract_snapshot.get("targeting") or {})
    evidence_status = dict(
        payload.get("candidate_evidence_status")
        or provenance.get("candidate_evidence_status")
        or {}
    )
    return {
        "name": _string(payload.get("name")) or None,
        "strategy_type": _string(payload.get("strategy_type")) or None,
        "candidate_family": _candidate_family(payload),
        "task_source": _candidate_task_source(payload),
        "generator_mode": _candidate_generator_mode(payload),
        "target_pool_id": _string(
            payload.get("target_pool_id")
            or targeting.get("target_pool_id")
        )
        or None,
        "target_symbols": _compact_list(
            payload.get("target_symbols")
            or targeting.get("target_symbols"),
            limit=12,
        ),
        "experiment_id": _string(payload.get("experiment_id")) or None,
        "candidate_contract_ready": bool(contract_snapshot),
        "evidence_ready": bool(evidence_status or payload.get("evidence_bundle")),
    }


def _compact_experiment_brief(experiment: dict[str, Any]) -> dict[str, Any]:
    payload = dict(experiment or {})
    return {
        "experiment_id": _string(payload.get("experiment_id") or payload.get("id")) or None,
        "task_id": _string(payload.get("task_id")) or None,
        "strategy_id": _string(payload.get("strategy_id")) or None,
        "status": _string(payload.get("status")) or None,
        "generator_mode": _string(payload.get("generator_mode")) or None,
    }


def build_research_artifact(
    *,
    factor_research: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = dict(factor_research or {})
    summary = dict(artifact.get("summary") or {})
    readiness_payload = dict(readiness or {})
    governed_pool_state = resolve_governed_pool_state(summary)
    lifecycle_feedback_input = dict(artifact.get("lifecycle_feedback_input") or {})
    top_candidate_lineage = [
        {
            "artifact_id": _string(item.get("artifact_id")) or None,
            "name": _string(item.get("name")) or None,
            "family": _string(item.get("family")) or None,
            "registry_stage": _string(item.get("registry_stage")) or None,
            "latest_validation_at": item.get("latest_validation_at"),
        }
        for item in list(artifact.get("top_candidate_lineage") or [])[:3]
        if isinstance(item, dict)
    ]
    return {
        "contract_version": RESEARCH_ARTIFACT_CONTRACT_VERSION,
        "available": bool(artifact),
        "factor_source_mode": summary.get("factor_source_mode"),
        "degraded": bool(artifact.get("degraded")),
        "stale": bool(summary.get("stale")),
        "active_factor_count": _safe_int(summary.get("active_factor_count")),
        "active_candidate_count": _safe_int(summary.get("active_candidate_count")),
        "active_family_names": _compact_list(summary.get("active_family_names"), limit=12),
        "active_regime_names": _compact_list(summary.get("active_regime_names"), limit=12),
        "top_factor_names": _compact_list(summary.get("top_factor_names"), limit=8),
        "top_candidate_names": _compact_list(summary.get("top_candidate_names"), limit=8),
        "governed_candidate_pool_active": bool(governed_pool_state.get("active")),
        "governed_candidate_pool_mode": summary.get("governed_candidate_pool_mode"),
        "governed_candidate_pool_provisional": bool(summary.get("governed_candidate_pool_provisional")),
        "stock_family_allocation_count": _safe_int(summary.get("stock_family_allocation_count")),
        "factor_llm_provider_health_status": summary.get("factor_llm_provider_health_status"),
        "factor_llm_provider_ready": bool(summary.get("factor_llm_provider_ready")),
        "lifecycle_feedback_input_contract_version": lifecycle_feedback_input.get("contract_version"),
        "lifecycle_feedback_input_available": bool(lifecycle_feedback_input.get("available")),
        "lifecycle_feedback_family_count": _safe_int(summary.get("budget_feedback_family_count")),
        "lifecycle_feedback_strategy_count": _safe_int(summary.get("budget_feedback_strategy_count")),
        "lifecycle_feedback_target_pool_scope_count": _safe_int(
            summary.get("budget_feedback_target_pool_scope_count")
        ),
        "lifecycle_feedback_generator_mode_scope_count": _safe_int(
            summary.get("budget_feedback_generator_mode_scope_count")
        ),
        "lifecycle_feedback_runtime_alert_count": _safe_int(
            summary.get("budget_feedback_runtime_alert_count")
        ),
        "lifecycle_feedback_runtime_risk_event_count": _safe_int(
            summary.get("budget_feedback_runtime_risk_event_count")
        ),
        "lifecycle_feedback_promotion_review_count": _safe_int(
            summary.get("budget_feedback_promotion_review_count")
        ),
        "lifecycle_feedback_promotion_review_status_counts": dict(
            summary.get("budget_feedback_promotion_review_status_counts") or {}
        ),
        "source_chain": list(artifact.get("source_chain") or []),
        "readiness_reference": {
            "decision": readiness_payload.get("decision"),
            "readiness_score": readiness_payload.get("readiness_score"),
            "can_proceed": bool(readiness_payload.get("can_proceed", True)),
            "blocking_reason_codes": list(readiness_payload.get("blocking_reason_codes") or []),
        },
        "top_candidate_lineage_preview": top_candidate_lineage,
    }


def build_task_artifact(autonomy_stage: dict[str, Any] | None = None) -> dict[str, Any]:
    stage = dict(autonomy_stage or {})
    task_scan = dict(stage.get("task_scan") or {})
    task_scan_summary = dict(task_scan.get("summary") or {})
    task_source_counts = dict(stage.get("task_source_counts") or task_scan_summary.get("task_sources") or {})
    event_task_count = _safe_int(
        stage.get("event_task_count"),
        _safe_int(task_scan_summary.get("event_task_count")),
    )
    bulk_stock_task_count = _safe_int(
        stage.get("bulk_stock_task_count"),
        _safe_int(task_scan_summary.get("bulk_stock_task_count")),
    )
    snapshot_task_count = _safe_int(
        stage.get("snapshot_task_count"),
        _safe_int(task_source_counts.get("snapshot")),
    )
    planned_tasks = [
        _compact_task_brief(task)
        for task in list(task_scan.get("tasks") or [])[:12]
        if isinstance(task, dict)
    ]
    task_results = [
        _compact_task_result_brief(task_result)
        for task_result in list(stage.get("task_results") or [])[:12]
        if isinstance(task_result, dict)
    ]
    return {
        "contract_version": TASK_ARTIFACT_CONTRACT_VERSION,
        "available": bool(autonomy_stage),
        "planned_task_count": len(list(task_scan.get("tasks") or [])),
        "executed_task_count": len(list(stage.get("task_results") or [])),
        "completed_task_count": _safe_int(stage.get("completed_task_count")),
        "failed_task_count": _safe_int(stage.get("failed_task_count")),
        "generated_candidate_count": _safe_int(stage.get("generated_count")),
        "task_source_counts": task_source_counts,
        "event_task_count": event_task_count,
        "snapshot_task_count": snapshot_task_count,
        "bulk_stock_task_count": bulk_stock_task_count,
        "bulk_stock_matrix_enabled": bool(task_scan_summary.get("bulk_stock_matrix_enabled")),
        "bulk_stock_matrix_stock_count": _safe_int(task_scan_summary.get("bulk_stock_matrix_stock_count")),
        "bulk_stock_matrix_eligible_stock_count": _safe_int(
            task_scan_summary.get("bulk_stock_matrix_eligible_stock_count")
        ),
        "feedback_control_mode_counts": dict(stage.get("selected_feedback_control_mode_counts") or {}),
        "feedback_target_pool_control_mode_counts": dict(
            stage.get("selected_feedback_target_pool_control_mode_counts") or {}
        ),
        "feedback_generator_mode_control_mode_counts": dict(
            stage.get("selected_feedback_generator_mode_control_mode_counts") or {}
        ),
        "planned_task_briefs": planned_tasks,
        "task_result_briefs": task_results,
    }


def build_candidate_artifact(candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    items = [dict(item or {}) for item in list(candidates or []) if isinstance(item, dict)]
    briefs = [_compact_candidate_brief(item) for item in items[:12]]
    targeted_candidate_count = sum(1 for item in items if list(item.get("target_symbols") or []))
    experiment_linked_count = sum(1 for item in items if _string(item.get("experiment_id")))
    contract_ready_count = sum(1 for item in items if bool(item.get("candidate_contract_snapshot")))
    evidence_ready_count = sum(
        1
        for item in items
        if bool(
            item.get("evidence_bundle")
            or item.get("candidate_evidence_status")
            or dict(dict(item.get("params") or {}).get("candidate_provenance") or {}).get(
                "candidate_evidence_status"
            )
        )
    )
    return {
        "contract_version": CANDIDATE_ARTIFACT_CONTRACT_VERSION,
        "available": bool(items),
        "candidate_count": len(items),
        "targeted_candidate_count": targeted_candidate_count,
        "experiment_linked_count": experiment_linked_count,
        "candidate_contract_ready_count": contract_ready_count,
        "candidate_evidence_ready_count": evidence_ready_count,
        "generator_type_counts": _count_by(items, _candidate_generator_mode),
        "task_source_counts": _count_by(items, _candidate_task_source),
        "family_counts": _count_by(items, _candidate_family),
        "candidate_briefs": briefs,
    }


def build_research_evidence_artifact(
    autonomy_stage: dict[str, Any] | None = None,
    *,
    experiments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stage = dict(autonomy_stage or {})
    experiment_rows = [dict(item or {}) for item in list(experiments or []) if isinstance(item, dict)]
    task_results = [dict(item or {}) for item in list(stage.get("task_results") or []) if isinstance(item, dict)]
    task_status_counts = _count_by(task_results, lambda item: item.get("status"))
    return {
        "contract_version": RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
        "available": bool(stage or experiment_rows),
        "task_evidence_count": _safe_int(stage.get("event_evidence_count")),
        "task_run_count": len(list(stage.get("task_run_ids") or [])),
        "task_run_ids": list(stage.get("task_run_ids") or [])[:12],
        "task_result_status_counts": task_status_counts,
        "experiment_count": _safe_int(stage.get("experiment_count"), len(experiment_rows)),
        "experiment_briefs": [_compact_experiment_brief(item) for item in experiment_rows[:12]],
        "external_llm_status": stage.get("external_llm_status"),
        "external_llm_status_counts": dict(stage.get("external_llm_status_counts") or {}),
        "external_llm_attempt_count": _safe_int(stage.get("external_llm_attempt_count")),
        "external_llm_network_request_count": _safe_int(stage.get("external_llm_network_request_count")),
        "external_llm_real_request_count": _safe_int(stage.get("external_llm_real_request_count")),
        "external_llm_selected_count": _safe_int(stage.get("external_llm_selected_count")),
        "external_llm_compatibility_skip_count": _safe_int(
            stage.get("external_llm_compatibility_skip_count")
        ),
        "external_llm_cooldown_skip_count": _safe_int(stage.get("external_llm_cooldown_skip_count")),
        "external_llm_compatibility_failure_count": _safe_int(
            stage.get("external_llm_compatibility_failure_count")
        ),
        "external_llm_effective_response_count": _safe_int(
            stage.get("external_llm_effective_response_count")
        ),
        "external_llm_empty_200_response_count": _safe_int(
            stage.get("external_llm_empty_200_response_count")
        ),
        "external_llm_effective_response_ratio": round(
            _safe_float(stage.get("external_llm_effective_response_ratio")),
            4,
        ),
        "external_llm_provider_health_status": stage.get("external_llm_provider_health_status"),
        "persistence_failure_count": _safe_int(stage.get("persistence_failure_count")),
        "last_error_type": stage.get("external_llm_last_error_type"),
        "last_error": stage.get("external_llm_last_error"),
    }


def build_research_plane_artifact(
    *,
    factor_research: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
    autonomy_stage: dict[str, Any] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    experiments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    autonomy_payload = dict(autonomy_stage or {})
    factor_payload = dict(factor_research or {})
    prebuilt_research_artifact = _resolve_contract_artifact(
        factor_payload.get("research_artifact"),
        expected_version=RESEARCH_ARTIFACT_CONTRACT_VERSION,
    )
    research_artifact = (
        prebuilt_research_artifact
        if bool(prebuilt_research_artifact.get("available"))
        else build_research_artifact(
            factor_research=factor_research,
            readiness=readiness,
        )
    )
    prebuilt_task_artifact = _resolve_contract_artifact(
        autonomy_payload.get("task_artifact"),
        expected_version=TASK_ARTIFACT_CONTRACT_VERSION,
    )
    task_artifact = (
        prebuilt_task_artifact
        if bool(prebuilt_task_artifact.get("available"))
        else build_task_artifact(autonomy_stage)
    )
    prebuilt_candidate_artifact = _resolve_contract_artifact(
        autonomy_payload.get("candidate_artifact"),
        expected_version=CANDIDATE_ARTIFACT_CONTRACT_VERSION,
    )
    candidate_artifact = (
        prebuilt_candidate_artifact
        if bool(prebuilt_candidate_artifact.get("available"))
        else build_candidate_artifact(candidates)
    )
    prebuilt_evidence_artifact = _resolve_contract_artifact(
        autonomy_payload.get("evidence_artifact"),
        expected_version=RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION,
    )
    evidence_artifact = (
        prebuilt_evidence_artifact
        if bool(prebuilt_evidence_artifact.get("available"))
        else build_research_evidence_artifact(
            autonomy_stage,
            experiments=experiments,
        )
    )
    available = any(
        bool(item.get("available"))
        for item in (
            research_artifact,
            task_artifact,
            candidate_artifact,
            evidence_artifact,
        )
    )
    source_chain = list(research_artifact.get("source_chain") or [])
    if task_artifact.get("available"):
        source_chain.append("autonomy.task_artifact")
    if candidate_artifact.get("available"):
        source_chain.append("research.candidate_artifact")
    if evidence_artifact.get("available"):
        source_chain.append("research.evidence_artifact")
    return {
        "contract_version": RESEARCH_PLANE_CONTRACT_VERSION,
        "available": available,
        "plane": "research",
        "research_artifact": research_artifact,
        "task_artifact": task_artifact,
        "candidate_artifact": candidate_artifact,
        "evidence_artifact": evidence_artifact,
        "source_chain": source_chain,
    }


__all__ = [
    "CANDIDATE_ARTIFACT_CONTRACT_VERSION",
    "RESEARCH_ARTIFACT_CONTRACT_VERSION",
    "RESEARCH_EVIDENCE_ARTIFACT_CONTRACT_VERSION",
    "RESEARCH_PLANE_CONTRACT_VERSION",
    "TASK_ARTIFACT_CONTRACT_VERSION",
    "build_candidate_artifact",
    "build_research_artifact",
    "build_research_evidence_artifact",
    "build_research_plane_artifact",
    "build_task_artifact",
]
