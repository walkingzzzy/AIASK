"""Builder sub-steps extracted from factor research artifact construction."""

from __future__ import annotations

from datetime import date
from typing import Any, List

from ...domain.constants import FACTORY_RESEARCH_FACTORS
from .._budget_feedback import (
    extract_feedback_root,
    normalize_feedback_input_contract,
)


def _enrich_governed_candidate(
    builder_cls,
    item: dict[str, Any],
    *,
    snapshot_date: date | None,
) -> dict[str, Any]:
    payload = dict(item or {})
    latest_validation_at = payload.get("latest_validation_at") or payload.get("updated_at") or payload.get("created_at")
    latest_validation_age_days = (
        builder_cls._days_since(
            builder_cls._parse_date(latest_validation_at),
            reference_date=snapshot_date,
        )
        if snapshot_date is not None
        else None
    )
    expected_regime = [
        str(value).strip()
        for value in list(payload.get("expected_regime") or [])
        if str(value).strip()
    ]
    risk_audit = dict(payload.get("risk_audit") or {})
    evidence_status = {
        "required_audits_complete": bool(risk_audit.get("required_audits_complete")),
        "lookahead_available": bool(risk_audit.get("lookahead_available")),
        "multiple_testing_available": bool(risk_audit.get("multiple_testing_available")),
        "overall_risk_level": str(risk_audit.get("overall_risk_level") or "").strip().lower() or None,
        "blocked": bool(risk_audit.get("blocked")),
    }
    payload["expected_regime"] = expected_regime
    payload["expected_holding_period"] = payload.get("expected_holding_period")
    payload["latest_validation_at"] = latest_validation_at
    payload["latest_validation_age_days"] = latest_validation_age_days
    payload["admission_block_reasons"] = list(
        payload.get("admission_block_reasons") or risk_audit.get("block_reasons") or []
    )
    payload["evidence_status"] = evidence_status
    return payload


async def load_research_runtime_context(
    builder_cls,
    db,
    snapshot: dict[str, Any],
    *,
    lightweight_mock_fallback: bool,
    snapshot_date: date | None,
    scheduler_provider,
) -> dict[str, Any]:
    if lightweight_mock_fallback:
        governed_pool = {
            "available": False,
            "reason": "lightweight_mock_fallback",
        }
    else:
        governed_pool = dict(await builder_cls._load_governed_candidate_pool(snapshot) or {})

    active_candidate_pool = dict(governed_pool.get("active_pool") or {})
    governed_registry_summary = dict(governed_pool.get("summary") or {})
    governed_candidate_pool_mode = (
        str(active_candidate_pool.get("active_pool_mode") or "").strip().lower() or None
    )
    governed_candidate_pool_provisional = governed_candidate_pool_mode == "provisional_validated_watch"
    governed_candidate_pool_strict_count = int(active_candidate_pool.get("strict_count") or 0)
    governed_candidate_pool_provisional_count = int(active_candidate_pool.get("provisional_count") or 0)
    governed_candidate_pool_provisional_spillover_count = int(
        active_candidate_pool.get("provisional_spillover_count") or 0
    )
    governed_candidate_pool_provisional_spillover_policy = dict(
        active_candidate_pool.get("provisional_spillover_policy") or {}
    )
    governed_top_candidates = [
        dict(item or {})
        for item in list(active_candidate_pool.get("top_candidates") or [])
        if isinstance(item, dict)
    ]
    governed_excluded_candidates = [
        dict(item or {})
        for item in list(active_candidate_pool.get("excluded_candidates") or [])
        if isinstance(item, dict)
    ]
    governed_family_summary = [
        dict(item or {})
        for item in list(active_candidate_pool.get("family_summary") or [])
        if isinstance(item, dict)
    ]
    governed_regime_summary = [
        dict(item or {})
        for item in list(active_candidate_pool.get("regime_summary") or [])
        if isinstance(item, dict)
    ]
    if lightweight_mock_fallback:
        model_registry_lineage = {
            "available": False,
            "reason": "lightweight_mock_fallback",
        }
    else:
        model_registry_lineage = dict(
            await builder_cls._load_model_registry_lineage(governed_top_candidates[:5]) or {}
        )
    model_lineage_summary = dict(model_registry_lineage.get("summary") or {})
    model_lineage_by_validation_id = dict(model_registry_lineage.get("by_validation_artifact_id") or {})

    if lightweight_mock_fallback:
        seed_feedback_root = extract_feedback_root(snapshot.get("family_gate_feedback") or {})
        budget_feedback_payload = normalize_feedback_input_contract(
            {"feedback": seed_feedback_root},
            available=bool(seed_feedback_root),
            reason="lightweight_mock_fallback" if not seed_feedback_root else None,
            summary={
                "family_count": len(seed_feedback_root),
                "seeded_family_count": len(seed_feedback_root),
                "strategy_count": 0,
                "runtime_alert_count": 0,
                "runtime_risk_event_count": 0,
                "target_pool_scope_count": 0,
                "generator_mode_scope_count": 0,
            },
        )
    else:
        budget_feedback_payload = await builder_cls._load_budget_feedback(db, snapshot)
    lifecycle_feedback_input = normalize_feedback_input_contract(budget_feedback_payload)
    budget_feedback_root = dict(lifecycle_feedback_input.get("feedback") or {})
    budget_feedback_summary = dict(lifecycle_feedback_input.get("summary") or {})

    governed_source_candidate_count = int(
        active_candidate_pool.get("source_count")
        or governed_registry_summary.get("count")
        or 0
    )
    governed_active_registry_candidate_count = int(
        governed_registry_summary.get("active_count")
        or active_candidate_pool.get("count")
        or 0
    )
    blocked_excluded_count = active_candidate_pool.get("blocked_excluded_count")
    governed_blocked_candidate_count = (
        int(blocked_excluded_count or 0)
        if blocked_excluded_count is not None
        else int(governed_registry_summary.get("blocked_active_count") or 0)
    )
    if governed_blocked_candidate_count <= 0:
        governed_blocked_candidate_count = sum(
            1
            for item in list(active_candidate_pool.get("excluded_candidates") or [])
            if bool((item or {}).get("admission_blocked"))
            or bool(dict((item or {}).get("risk_audit") or {}).get("blocked"))
        )
    pending_excluded_count = active_candidate_pool.get("pending_excluded_count")
    governed_pending_candidate_count = (
        int(pending_excluded_count or 0)
        if pending_excluded_count is not None
        else max(
            int(active_candidate_pool.get("excluded_count") or 0) - governed_blocked_candidate_count,
            0,
        )
    )
    ineligible_excluded_count = active_candidate_pool.get("ineligible_excluded_count")
    governed_ineligible_candidate_count = (
        int(ineligible_excluded_count or 0)
        if ineligible_excluded_count is not None
        else max(
            int(active_candidate_pool.get("excluded_count") or 0)
            - governed_blocked_candidate_count
            - governed_pending_candidate_count,
            0,
        )
    )
    governed_exclusion_reason_counts = {
        str(key): int(value or 0)
        for key, value in dict(active_candidate_pool.get("exclusion_reason_counts") or {}).items()
        if str(key).strip()
    }
    governed_blocking_reason_counts = {
        str(key): int(value or 0)
        for key, value in dict(active_candidate_pool.get("blocked_exclusion_reason_counts") or {}).items()
        if str(key).strip()
    }
    governed_pending_reason_counts = {
        str(key): int(value or 0)
        for key, value in dict(active_candidate_pool.get("pending_exclusion_reason_counts") or {}).items()
        if str(key).strip()
    }
    governed_ineligible_reason_counts = {
        str(key): int(value or 0)
        for key, value in dict(active_candidate_pool.get("ineligible_exclusion_reason_counts") or {}).items()
        if str(key).strip()
    }
    governed_candidate_pool_provisional_pending_count = int(
        governed_candidate_pool_provisional_spillover_policy.get("pending_provisional_count") or 0
    )
    governed_candidate_pool_strict_shortfall_count = int(
        governed_candidate_pool_provisional_spillover_policy.get("strict_shortfall_count") or 0
    )
    governed_candidate_pool_provisional_spillover_policy_status = (
        str(governed_candidate_pool_provisional_spillover_policy.get("status") or "").strip().lower() or None
    )

    governed_top_candidates = [
        _enrich_governed_candidate(builder_cls, item, snapshot_date=snapshot_date)
        for item in governed_top_candidates
    ]
    governed_excluded_candidates = [
        _enrich_governed_candidate(builder_cls, item, snapshot_date=snapshot_date)
        for item in governed_excluded_candidates
    ]
    active_candidate_pool["top_candidates"] = governed_top_candidates
    active_candidate_pool["excluded_candidates"] = governed_excluded_candidates

    governed_latest_candidate_at = (
        active_candidate_pool.get("latest_active_candidate_updated_at")
        or active_candidate_pool.get("latest_candidate_updated_at")
    )
    governed_latest_candidate_date = builder_cls._parse_date(governed_latest_candidate_at)
    governed_freshness_days = builder_cls._days_since(
        governed_latest_candidate_date,
        reference_date=snapshot_date,
    )
    governed_blocked_ratio = (
        round(governed_blocked_candidate_count / max(governed_source_candidate_count, 1), 6)
        if governed_source_candidate_count > 0
        else 0.0
    )
    governed_pending_ratio = (
        round(governed_pending_candidate_count / max(governed_source_candidate_count, 1), 6)
        if governed_source_candidate_count > 0
        else 0.0
    )
    governed_ineligible_ratio = (
        round(governed_ineligible_candidate_count / max(governed_source_candidate_count, 1), 6)
        if governed_source_candidate_count > 0
        else 0.0
    )

    if lightweight_mock_fallback:
        scheduler_status = {}
        scheduler_quality_flags = []
        scheduler_recent_success = False
        scheduler_llm_validation_status = None
        scheduler_llm_provider = {}
        scheduler_llm_provider_health_status = None
    else:
        scheduler = scheduler_provider()
        scheduler_status = dict(scheduler.status() or {})
        scheduler_last_result = dict(scheduler_status.get("last_result") or {})
        scheduler_llm_validation = dict(scheduler_last_result.get("llm_validation") or {})
        scheduler_llm_provider = dict(scheduler_status.get("llm_provider") or {})
        scheduler_quality_flags = list(scheduler_status.get("quality_flags") or [])
        scheduler_freshness_sec = builder_cls._safe_float(scheduler_status.get("freshness_sec"))
        scheduler_recent_success = bool(
            scheduler_status.get("last_run")
            and scheduler_freshness_sec
            <= float(getattr(scheduler, "STALE_AFTER_SEC", 24 * 60 * 60))
            and "failed" not in scheduler_quality_flags
        )
        if not bool(governed_pool.get("available")):
            scheduler_recent_success = False
        scheduler_llm_validation_status = (
            str(scheduler_llm_validation.get("status") or "").strip().lower() or None
        )
        scheduler_llm_provider_health_status = (
            str(scheduler_llm_provider.get("health_status") or "").strip().lower() or None
        )

    return {
        "governed_pool": governed_pool,
        "active_candidate_pool": active_candidate_pool,
        "governed_registry_summary": governed_registry_summary,
        "governed_candidate_pool_mode": governed_candidate_pool_mode,
        "governed_candidate_pool_provisional": governed_candidate_pool_provisional,
        "governed_candidate_pool_strict_count": governed_candidate_pool_strict_count,
        "governed_candidate_pool_provisional_count": governed_candidate_pool_provisional_count,
        "governed_candidate_pool_provisional_spillover_count": governed_candidate_pool_provisional_spillover_count,
        "governed_candidate_pool_provisional_spillover_policy": governed_candidate_pool_provisional_spillover_policy,
        "governed_candidate_pool_provisional_pending_count": governed_candidate_pool_provisional_pending_count,
        "governed_candidate_pool_strict_shortfall_count": governed_candidate_pool_strict_shortfall_count,
        "governed_candidate_pool_provisional_spillover_policy_status": governed_candidate_pool_provisional_spillover_policy_status,
        "governed_top_candidates": governed_top_candidates,
        "governed_excluded_candidates": governed_excluded_candidates,
        "governed_family_summary": governed_family_summary,
        "governed_regime_summary": governed_regime_summary,
        "model_registry_lineage": model_registry_lineage,
        "model_lineage_summary": model_lineage_summary,
        "model_lineage_by_validation_id": model_lineage_by_validation_id,
        "lifecycle_feedback_input": lifecycle_feedback_input,
        "budget_feedback_root": budget_feedback_root,
        "budget_feedback_summary": budget_feedback_summary,
        "governed_source_candidate_count": governed_source_candidate_count,
        "governed_active_registry_candidate_count": governed_active_registry_candidate_count,
        "governed_blocked_candidate_count": governed_blocked_candidate_count,
        "governed_pending_candidate_count": governed_pending_candidate_count,
        "governed_ineligible_candidate_count": governed_ineligible_candidate_count,
        "governed_exclusion_reason_counts": governed_exclusion_reason_counts,
        "governed_blocking_reason_counts": governed_blocking_reason_counts,
        "governed_pending_reason_counts": governed_pending_reason_counts,
        "governed_ineligible_reason_counts": governed_ineligible_reason_counts,
        "governed_latest_candidate_at": governed_latest_candidate_at,
        "governed_freshness_days": governed_freshness_days,
        "governed_blocked_ratio": governed_blocked_ratio,
        "governed_pending_ratio": governed_pending_ratio,
        "governed_ineligible_ratio": governed_ineligible_ratio,
        "scheduler_status": scheduler_status,
        "scheduler_quality_flags": scheduler_quality_flags,
        "scheduler_recent_success": scheduler_recent_success,
        "scheduler_llm_validation_status": scheduler_llm_validation_status,
        "scheduler_llm_provider": scheduler_llm_provider,
        "scheduler_llm_provider_health_status": scheduler_llm_provider_health_status,
    }


def build_ranked_factor_context(
    builder_cls,
    *,
    factor_ic: dict[str, Any],
    factor_trend: dict[str, Any],
    names: List[str],
    history_meta: dict[str, dict[str, Any]],
    governed_top_candidates: List[dict[str, Any]],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    ranked_factors: List[dict[str, Any]] = []
    for factor_name in names:
        ic_value = builder_cls._safe_float(factor_ic.get(factor_name))
        trend = builder_cls._normalize_trend(factor_trend.get(factor_name))
        trend_bonus = 0.02 if trend == "rising" else (-0.02 if trend == "falling" else 0.0)
        meta = dict(history_meta.get(str(factor_name)) or {})
        ranked_factors.append(
            {
                "factor_name": str(factor_name),
                "ic_value": round(ic_value, 6),
                "trend": trend,
                "score": round(ic_value + trend_bonus, 6),
                "preferred_strategy_types": builder_cls._preferred_types_for_factor(str(factor_name)),
                "history_count": builder_cls._safe_int(meta.get("history_count")),
                "latest_ic_date": meta.get("latest_ic_date"),
                "stability_tag": meta.get("stability_tag") or "insufficient_history",
                "decay_flag": bool(meta.get("decay_flag")),
            }
        )

    ranked_factors.sort(
        key=lambda item: (
            builder_cls._safe_float(item.get("score")),
            builder_cls._safe_float(item.get("ic_value")),
            str(item.get("factor_name") or ""),
        ),
        reverse=True,
    )

    positive_rising_factors = [
        str(item.get("factor_name") or "")
        for item in ranked_factors
        if builder_cls._normalize_trend(item.get("trend")) == "rising"
        and builder_cls._safe_float(item.get("ic_value")) > 0.0
    ]
    positive_rising_factors = [name for name in positive_rising_factors if name]

    governed_active_factors = [
        str(item.get("family") or "").strip()
        for item in governed_top_candidates
        if str(item.get("family") or "").strip()
    ]
    governed_active_factors = list(dict.fromkeys(governed_active_factors))

    active_factors = positive_rising_factors[:3]
    if not active_factors:
        active_factors = [
            str(item.get("factor_name") or "")
            for item in ranked_factors
            if abs(builder_cls._safe_float(item.get("ic_value"))) >= 0.02
        ][:3]
    if governed_active_factors:
        active_factors = list(dict.fromkeys([*governed_active_factors[:4], *active_factors]))[:4]
    active_factors = [name for name in active_factors if name]

    active_factor_set = set(active_factors)
    preferred_strategy_types: List[str] = []
    for item in governed_top_candidates:
        for strategy_type in builder_cls._preferred_types_for_factor(str(item.get("family") or "")):
            if strategy_type not in preferred_strategy_types:
                preferred_strategy_types.append(strategy_type)
    for item in ranked_factors:
        if str(item.get("factor_name") or "") not in active_factor_set:
            continue
        for strategy_type in list(item.get("preferred_strategy_types") or []):
            if strategy_type not in preferred_strategy_types:
                preferred_strategy_types.append(strategy_type)

    top_factor_names = [
        str(item.get("factor_name") or "")
        for item in ranked_factors[:3]
        if str(item.get("factor_name") or "")
    ]

    return {
        "ranked_factors": ranked_factors,
        "positive_rising_factors": positive_rising_factors,
        "active_factors": active_factors,
        "preferred_strategy_types": preferred_strategy_types,
        "top_factor_names": top_factor_names,
    }


def build_candidate_lineage_views(
    builder_cls,
    *,
    governed_top_candidates: List[dict[str, Any]],
    governed_excluded_candidates: List[dict[str, Any]],
    model_registry_lineage: dict[str, Any],
    model_lineage_by_validation_id: dict[str, Any],
) -> dict[str, Any]:
    top_candidate_names = [
        str(item.get("name") or "")
        for item in governed_top_candidates[:5]
        if str(item.get("name") or "")
    ]
    top_candidate_lineage = [
        (
            lambda entry, lineage_item: {
                "artifact_id": str(entry.get("artifact_id") or "").strip() or None,
                "name": str(entry.get("name") or "").strip() or None,
                "family": str(entry.get("family") or "").strip() or None,
                "registry_stage": str(entry.get("registry_stage") or "").strip() or None,
                "pool_entry_mode": str(entry.get("pool_entry_mode") or "").strip() or None,
                "expected_regime": [
                    str(value).strip()
                    for value in list(entry.get("expected_regime") or [])
                    if str(value).strip()
                ],
                "expected_holding_period": entry.get("expected_holding_period"),
                "source_generation_artifact_id": str(entry.get("source_generation_artifact_id") or "").strip() or None,
                "source_validation_artifact_id": (
                    str(entry.get("source_validation_artifact_id") or entry.get("artifact_id") or "").strip() or None
                ),
                "memory_record_id": str(entry.get("memory_record_id") or "").strip() or None,
                "latest_validation_at": entry.get("latest_validation_at") or entry.get("updated_at") or entry.get("created_at"),
                "latest_validation_age_days": entry.get("latest_validation_age_days"),
                "admission_block_reasons": list(entry.get("admission_block_reasons") or []),
                "evidence_status": dict(entry.get("evidence_status") or {}),
                "model_registry_artifact_ids": [
                    str(model_item.get("artifact_id") or "").strip()
                    for model_item in list((lineage_item or {}).get("model_registry_items") or [])
                    if str(model_item.get("artifact_id") or "").strip()
                ],
                "model_registry_stages": list((lineage_item or {}).get("deployment_stages") or []),
                "latest_retrain_run_status": (
                    (lineage_item.get("latest_retrain_run") or {}).get("status")
                    if isinstance(lineage_item, dict)
                    else None
                ),
                "retrain_plan_statuses": list((lineage_item or {}).get("retrain_statuses") or []),
                "retrain_plan_ids": [
                    str(plan.get("artifact_id") or plan.get("plan_id") or "").strip()
                    for plan in list((lineage_item or {}).get("retrain_plans") or [])
                    if str(plan.get("artifact_id") or plan.get("plan_id") or "").strip()
                ],
                "lineage_available": bool(model_registry_lineage.get("available")),
            }
        )(
            item,
            model_lineage_by_validation_id.get(
                str(item.get("source_validation_artifact_id") or item.get("artifact_id") or "").strip()
            ),
        )
        for item in governed_top_candidates[:5]
    ]
    blocked_candidate_lineage = [
        {
            "artifact_id": str(item.get("artifact_id") or "").strip() or None,
            "name": str(item.get("name") or "").strip() or None,
            "family": str(item.get("family") or "").strip() or None,
            "registry_stage": str(item.get("registry_stage") or "").strip() or None,
            "expected_regime": [
                str(value).strip()
                for value in list(item.get("expected_regime") or [])
                if str(value).strip()
            ],
            "expected_holding_period": item.get("expected_holding_period"),
            "source_generation_artifact_id": str(item.get("source_generation_artifact_id") or "").strip() or None,
            "source_validation_artifact_id": (
                str(item.get("source_validation_artifact_id") or item.get("artifact_id") or "").strip() or None
            ),
            "latest_validation_at": item.get("latest_validation_at") or item.get("updated_at") or item.get("created_at"),
            "latest_validation_age_days": item.get("latest_validation_age_days"),
            "admission_block_reasons": list(item.get("admission_block_reasons") or item.get("reasons") or []),
            "evidence_status": dict(item.get("evidence_status") or {}),
        }
        for item in governed_excluded_candidates[:5]
    ]
    return {
        "top_candidate_names": top_candidate_names,
        "top_candidate_lineage": top_candidate_lineage,
        "blocked_candidate_lineage": blocked_candidate_lineage,
    }


def resolve_factor_names(
    *,
    factor_ic: dict[str, Any],
    factor_trend: dict[str, Any],
    history_meta: dict[str, dict[str, Any]],
) -> List[str]:
    names = list(dict.fromkeys([*factor_ic.keys(), *factor_trend.keys(), *FACTORY_RESEARCH_FACTORS]))
    return [
        name
        for name in names
        if name in factor_ic or name in factor_trend or bool(history_meta.get(str(name)))
    ]
