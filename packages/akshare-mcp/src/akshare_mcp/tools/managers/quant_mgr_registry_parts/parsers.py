
from __future__ import annotations

import json
import os
from typing import Any, Callable

import numpy as np

from ...services import (
    get_artifact_async,
    get_factor_research_memory_service,
    list_artifacts_async,
)
from .quant_mgr_artifact_common import _payload_from_artifact_row
from .quant_mgr_helpers import _as_code_list, _safe_float


ACTIVE_REGISTRY_STAGES = {"governed", "challenger", "champion"}
STRICT_ACTIVE_POOL_MODE = "strict_governed"
PROVISIONAL_ACTIVE_POOL_MODE = "provisional_validated_watch"
EMPTY_ACTIVE_POOL_MODE = "empty"
PROVISIONAL_ACTIVE_REGISTRY_STAGE = "validated"
PROVISIONAL_ACTIVE_RECOMMENDATIONS = {"watch"}
PROVISIONAL_ACTIVE_RISK_LEVELS = {"low", "medium"}
PROVISIONAL_ACTIVE_MIN_SCORE = 45.0


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    token = str(raw).strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return default


STRICT_ACTIVE_POOL_SPILLOVER_ENABLED = _env_bool("STRATEGY_FACTORY_ACTIVE_POOL_SPILLOVER_ENABLED", True)
STRICT_ACTIVE_POOL_MIN_COUNT = _env_int(
    "STRATEGY_FACTORY_ACTIVE_POOL_MIN_COUNT",
    6,
    minimum=1,
    maximum=20,
)
STRICT_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT = _env_int(
    "STRATEGY_FACTORY_ACTIVE_POOL_PROVISIONAL_SPILLOVER_LIMIT",
    3,
    minimum=0,
    maximum=10,
)
_REGISTRY_STAGE_RANK = {
    "draft": 0,
    "validated": 1,
    "governed": 2,
    "challenger": 3,
    "champion": 4,
    "retired": -1,
}


def _dedupe_tokens(values: Any) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in list(values or []) if str(item).strip()]))


def _derive_registry_stage(
    *,
    raw_stage: str,
    explicit_registry_stage: str,
    recommendation: str,
    admission_blocked: bool,
) -> str:
    explicit = str(explicit_registry_stage or "").strip().lower()
    if explicit in {"draft", "validated", "governed", "challenger", "champion", "retired"}:
        if admission_blocked and explicit in ACTIVE_REGISTRY_STAGES:
            return "validated"
        return explicit
    preferred = str(raw_stage or "").strip().lower()
    if preferred in {"draft", "retired"}:
        return preferred
    if admission_blocked:
        return "validated"
    if recommendation in {"promote", "review"}:
        return "governed"
    return "validated"


def _normalize_validation_params(payload: dict[str, Any]) -> dict[str, int]:
    raw = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    normalized: dict[str, int] = {}
    for key in ("lookback_bars", "horizon_days", "max_dates"):
        value = raw.get(key)
        try:
            parsed = int(value)
        except Exception:
            continue
        if parsed > 0:
            normalized[key] = parsed
    return normalized


async def _load_model_registry_stage_index(summary_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stage_index: dict[str, dict[str, Any]] = {}
    for row in list(summary_rows or []):
        if str(row.get("strategy") or "").strip().lower() != "quant_model_registry":
            continue
        artifact_id = str(row.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        artifact = await get_artifact_async(artifact_id)
        if not artifact:
            continue
        payload = _payload_from_artifact_row(artifact)
        validation_artifact_id = str(payload.get("source_validation_artifact_id") or "").strip()
        deployment_stage = str(payload.get("deployment_stage") or "").strip().lower()
        if not validation_artifact_id or deployment_stage not in ACTIVE_REGISTRY_STAGES:
            continue
        entry = stage_index.setdefault(
            validation_artifact_id,
            {
                "deployment_stages": [],
                "reason_codes": [],
            },
        )
        if deployment_stage not in entry["deployment_stages"]:
            entry["deployment_stages"].append(deployment_stage)
        for reason_code in _dedupe_tokens(payload.get("reason_codes")):
            if reason_code not in entry["reason_codes"]:
                entry["reason_codes"].append(reason_code)

    for entry in stage_index.values():
        entry["deployment_stages"] = sorted(
            entry["deployment_stages"],
            key=lambda stage: _REGISTRY_STAGE_RANK.get(stage, 0),
            reverse=True,
        )
        entry["primary_stage"] = entry["deployment_stages"][0] if entry["deployment_stages"] else None
    return stage_index


def _promote_registry_stage_from_model_registry(
    registry_stage: str,
    *,
    admission_blocked: bool,
    deployment_stages: list[str] | None,
) -> str:
    current = str(registry_stage or "").strip().lower()
    if admission_blocked:
        return current
    stages = [
        str(item).strip().lower()
        for item in list(deployment_stages or [])
        if str(item).strip().lower() in ACTIVE_REGISTRY_STAGES
    ]
    if not stages:
        return current
    promoted = max(stages, key=lambda stage: _REGISTRY_STAGE_RANK.get(stage, 0))
    if _REGISTRY_STAGE_RANK.get(promoted, 0) > _REGISTRY_STAGE_RANK.get(current, 0):
        return promoted
    return current


def _normalize_registry_item(
    artifact: dict,
    payload: dict,
    *,
    model_registry_context: dict[str, Any] | None = None,
) -> dict:
    candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
    rating = payload.get("rating") if isinstance(payload.get("rating"), dict) else {}
    governance = payload.get("governance") if isinstance(payload.get("governance"), dict) else {}
    if not governance:
        nested_governance = rating.get("governance")
        governance = nested_governance if isinstance(nested_governance, dict) else {}
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    candidate_resolution = payload.get("candidate_resolution") if isinstance(payload.get("candidate_resolution"), dict) else {}
    memory_record = payload.get("memory_record") if isinstance(payload.get("memory_record"), dict) else {}
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    validation_report = payload.get("factor_validation_report") if isinstance(payload.get("factor_validation_report"), dict) else {}
    lookahead_audit = payload.get("lookahead_audit") if isinstance(payload.get("lookahead_audit"), dict) else {}
    if not lookahead_audit:
        nested_lookahead = validation_report.get("lookahead_audit")
        lookahead_audit = nested_lookahead if isinstance(nested_lookahead, dict) else {}
    multiple_testing = payload.get("multiple_testing") if isinstance(payload.get("multiple_testing"), dict) else {}
    if not multiple_testing:
        nested_multiple = validation_report.get("multiple_testing")
        multiple_testing = nested_multiple if isinstance(nested_multiple, dict) else {}

    lookahead_risk = str(lookahead_audit.get("risk_level") or "unknown").strip().lower() if lookahead_audit else "unknown"
    multiple_testing_risk = (
        str(multiple_testing.get("risk_level") or "unknown").strip().lower() if multiple_testing else "unknown"
    )
    risk_rank = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
    overall_risk = "unknown"
    max_risk_rank = max(risk_rank.get(lookahead_risk, 0), risk_rank.get(multiple_testing_risk, 0))
    for name, rank in risk_rank.items():
        if rank == max_risk_rank:
            overall_risk = name
    block_reasons = []
    if lookahead_risk == "high":
        block_reasons.append("lookahead_risk_high")
    if lookahead_audit and not bool(lookahead_audit.get("available")):
        block_reasons.append("lookahead_audit_unavailable")
    if multiple_testing and not bool(multiple_testing.get("available")):
        block_reasons.append("multiple_testing_unavailable")
    if multiple_testing_risk == "high":
        block_reasons.append("multiple_testing_risk_high")
    block_reasons.extend(_dedupe_tokens(governance.get("admission_block_reasons")))
    block_reasons = _dedupe_tokens(block_reasons)
    admission_blocked = bool(governance.get("admission_blocked")) or bool(block_reasons)
    model_registry_context = dict(model_registry_context or {})
    model_registry_stages = _dedupe_tokens(model_registry_context.get("deployment_stages"))
    raw_stage = str(payload.get("stage") or "").strip().lower()
    registry_stage = _derive_registry_stage(
        raw_stage=raw_stage,
        explicit_registry_stage=str(payload.get("registry_stage") or governance.get("registry_stage") or ""),
        recommendation=str(rating.get("recommendation") or "").strip().lower(),
        admission_blocked=admission_blocked,
    )
    registry_stage = _promote_registry_stage_from_model_registry(
        registry_stage,
        admission_blocked=admission_blocked,
        deployment_stages=model_registry_stages,
    )
    source_generation_artifact_id = (
        lineage.get("source_generation_artifact_id")
        or candidate_resolution.get("artifact_id")
    )
    source_validation_artifact_id = (
        lineage.get("source_validation_artifact_id")
        or str(artifact.get("artifact_id") or payload.get("artifact_id") or "")
    )
    memory_record_id = lineage.get("memory_record_id") or memory_record.get("artifact_id")
    latest_validation_at = (
        payload.get("latest_validation_at")
        or artifact.get("updated_at")
        or payload.get("updated_at")
        or artifact.get("created_at")
        or payload.get("created_at")
    )
    validation_params = _normalize_validation_params(payload)
    warnings = list(payload.get("warnings") or [])
    return {
        "artifact_id": str(artifact.get("artifact_id") or payload.get("artifact_id") or ""),
        "strategy": str(artifact.get("strategy") or payload.get("strategy") or ""),
        "strategy_version": str(artifact.get("strategy_version") or payload.get("strategy_version") or ""),
        "created_at": artifact.get("created_at") or payload.get("created_at"),
        "updated_at": artifact.get("updated_at") or payload.get("updated_at"),
        "codes": _as_code_list(payload.get("codes")),
        "candidate": {
            "name": candidate.get("name"),
            "family": candidate.get("family"),
            "expression_dsl": candidate.get("expression_dsl"),
            "expected_regime": candidate.get("expected_regime"),
            "expected_holding_period": candidate.get("expected_holding_period"),
        },
        "rating": {
            "grade": rating.get("grade"),
            "recommendation": rating.get("recommendation"),
            "total_score": _safe_float(rating.get("total_score"), 0.0),
        },
        "metrics": {
            "rank_ic_mean": _safe_float(metrics.get("rank_ic_mean"), 0.0),
            "rank_ic_ir": _safe_float(metrics.get("rank_ic_ir"), 0.0),
            "sample_dates": int(metrics.get("sample_dates", 0) or 0),
        },
        "risk_audit": {
            "lookahead_risk_level": lookahead_risk,
            "multiple_testing_risk_level": multiple_testing_risk,
            "overall_risk_level": overall_risk,
            "lookahead_available": bool(lookahead_audit.get("available")) if lookahead_audit else False,
            "multiple_testing_available": bool(multiple_testing.get("available")) if multiple_testing else False,
            "required_audits_complete": (
                bool(governance.get("required_audits_complete"))
                if governance
                else bool(lookahead_audit.get("available")) if lookahead_audit else False
            )
            and (
                bool(governance.get("required_audits_complete"))
                if governance
                else bool(multiple_testing.get("available")) if multiple_testing else False
            ),
            "blocked": admission_blocked,
            "block_reasons": block_reasons,
            "warning_samples": warnings[:5],
        },
        "governance": {
            "registry_stage": registry_stage,
            "admission_blocked": admission_blocked,
            "admission_block_reasons": block_reasons,
            "required_audits_complete": bool(
                bool(governance.get("required_audits_complete"))
                if governance
                else (
                    (not lookahead_audit or lookahead_audit.get("available"))
                    and (not multiple_testing or multiple_testing.get("available"))
                )
            ),
            "governance_grade": governance.get("governance_grade") or rating.get("grade"),
            "governance_recommendation": governance.get("governance_recommendation") or rating.get("recommendation"),
        },
        "validation_params": validation_params,
        "warnings_count": len(warnings),
        "stage": raw_stage,
        "registry_stage": registry_stage,
        "admission_blocked": admission_blocked,
        "admission_block_reasons": block_reasons,
        "model_registry_stages": model_registry_stages,
        "source_generation_artifact_id": source_generation_artifact_id,
        "source_validation_artifact_id": source_validation_artifact_id,
        "validation_artifact_id": source_validation_artifact_id,
        "memory_record_id": memory_record_id,
        "latest_validation_at": latest_validation_at,
        "lineage": {
            "generation_artifact_id": source_generation_artifact_id,
            "validation_artifact_id": source_validation_artifact_id,
            "memory_record_id": memory_record_id,
            "resolved_from": lineage.get("resolved_from") or candidate_resolution.get("resolved_from"),
            "candidate_index": lineage.get("candidate_index", candidate_resolution.get("candidate_index")),
        },
    }


async def _list_factor_candidate_registry_items(
    *,
    limit: int = 20,
    codes: list[str] | None = None,
    family: str | None = None,
    grade: str | None = None,
    recommendation: str | None = None,
    min_score: float | None = None,
    only_active: bool = False,
    market_codes_only: bool = False,
    include_synthetic: bool = False,
    filter_market_codes: Callable[[Any], list[str]],
) -> list[dict]:
    def _looks_like_synthetic_candidate(
        artifact_id: str,
        payload: dict,
        candidate: dict,
        record_codes: list[str],
    ) -> bool:
        if include_synthetic:
            return False
        text_parts = [
            artifact_id,
            str(payload.get("strategy") or ""),
            str(payload.get("strategy_version") or ""),
            str(candidate.get("name") or ""),
            str(candidate.get("family") or ""),
            str(candidate.get("expression_dsl") or ""),
        ]
        normalized = " ".join(text_parts).strip().lower()
        synthetic_tokens = (
            "_synthetic",
            "_demo",
            "_smoke",
            "_fixture",
            "_sample",
            " demo ",
            " smoke ",
            " fixture ",
            " synthetic ",
            " sample ",
        )
        if any(token in normalized for token in synthetic_tokens):
            return True
        return market_codes_only and not filter_market_codes(record_codes)

    fetch_limit = max(50, min(1000, int(limit) * 12))
    validation_rows = await list_artifacts_async(
        limit=fetch_limit,
        strategy="quant_factor_candidate_validation",
    )
    summary_rows = validation_rows if isinstance(validation_rows, list) else []
    model_registry_rows = await list_artifacts_async(
        limit=fetch_limit,
        strategy="quant_model_registry",
    )
    model_registry_stage_index = await _load_model_registry_stage_index(
        model_registry_rows if isinstance(model_registry_rows, list) else []
    )
    items = []
    requested_codes = filter_market_codes(codes) if market_codes_only else list(codes or [])
    for row in summary_rows:
        if str(row.get("strategy") or "").strip().lower() != "quant_factor_candidate_validation":
            continue
        artifact_id = str(row.get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        artifact = await get_artifact_async(artifact_id)
        if not artifact:
            continue
        payload = _payload_from_artifact_row(artifact)
        candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
        rating = payload.get("rating") if isinstance(payload.get("rating"), dict) else {}
        record_codes = _as_code_list(payload.get("codes"))
        effective_record_codes = filter_market_codes(record_codes) if market_codes_only else record_codes
        record_family = str(candidate.get("family") or "").strip().lower()
        record_grade = str(rating.get("grade") or "").strip().upper()
        record_recommendation = str(rating.get("recommendation") or "").strip().lower()
        record_registry_stage = str(payload.get("registry_stage") or "").strip().lower()
        total_score = _safe_float(rating.get("total_score"), 0.0)

        if market_codes_only and not effective_record_codes:
            continue
        if requested_codes and not (set(requested_codes) & set(effective_record_codes)):
            continue
        if family and record_family != str(family).strip().lower():
            continue
        if grade and record_grade != str(grade).strip().upper():
            continue
        if recommendation and record_recommendation != str(recommendation).strip().lower():
            continue
        if min_score is not None and total_score < float(min_score):
            continue
        if _looks_like_synthetic_candidate(artifact_id, payload, candidate, record_codes):
            continue

        normalized = _normalize_registry_item(
            artifact,
            payload,
            model_registry_context=model_registry_stage_index.get(artifact_id) or {},
        )
        resolved_stage = str(normalized.get("registry_stage") or record_registry_stage or "").strip().lower()
        if only_active and resolved_stage not in ACTIVE_REGISTRY_STAGES:
            continue

        items.append(normalized)

    items.sort(
        key=lambda item: (
            float(((item.get("rating") or {}).get("total_score") or 0.0)),
            str(item.get("updated_at") or item.get("created_at") or ""),
        ),
        reverse=True,
    )
    return items[: max(1, int(limit))]


def _summarize_factor_candidate_registry(items: list[dict]) -> dict:
    grade_counts = {}
    recommendation_counts = {}
    registry_stage_counts = {}
    family_counts = {}
    lookahead_risk_counts = {}
    multiple_testing_risk_counts = {}
    overall_risk_counts = {}
    total_scores = []
    active_items = 0
    governed_active_items = 0
    blocked_items = 0
    blocked_active_items = 0
    for item in list(items or []):
        rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
        grade_name = str(rating.get("grade") or "").strip().upper()
        recommendation_name = str(rating.get("recommendation") or "").strip().lower()
        registry_stage = str(item.get("registry_stage") or "").strip().lower()
        family_name = str(candidate.get("family") or "").strip().lower()
        total_score = _safe_float(rating.get("total_score"), 0.0)
        lookahead_risk = str(risk_audit.get("lookahead_risk_level") or "unknown").strip().lower()
        multiple_testing_risk = str(risk_audit.get("multiple_testing_risk_level") or "unknown").strip().lower()
        overall_risk = str(risk_audit.get("overall_risk_level") or "unknown").strip().lower()
        blocked = bool(risk_audit.get("blocked"))
        if grade_name:
            grade_counts[grade_name] = int(grade_counts.get(grade_name, 0)) + 1
        if recommendation_name:
            recommendation_counts[recommendation_name] = int(recommendation_counts.get(recommendation_name, 0)) + 1
        if registry_stage:
            registry_stage_counts[registry_stage] = int(registry_stage_counts.get(registry_stage, 0)) + 1
        if family_name:
            family_counts[family_name] = int(family_counts.get(family_name, 0)) + 1
        if lookahead_risk:
            lookahead_risk_counts[lookahead_risk] = int(lookahead_risk_counts.get(lookahead_risk, 0)) + 1
        if multiple_testing_risk:
            multiple_testing_risk_counts[multiple_testing_risk] = int(multiple_testing_risk_counts.get(multiple_testing_risk, 0)) + 1
        if overall_risk:
            overall_risk_counts[overall_risk] = int(overall_risk_counts.get(overall_risk, 0)) + 1
        total_scores.append(total_score)
        if registry_stage in ACTIVE_REGISTRY_STAGES:
            active_items += 1
            if blocked:
                blocked_active_items += 1
            else:
                governed_active_items += 1
        if blocked:
            blocked_items += 1
    return {
        "count": len(list(items or [])),
        "active_count": active_items,
        "governed_active_count": governed_active_items,
        "blocked_count": blocked_items,
        "blocked_active_count": blocked_active_items,
        "grade_counts": grade_counts,
        "recommendation_counts": recommendation_counts,
        "registry_stage_counts": registry_stage_counts,
        "family_counts": family_counts,
        "lookahead_risk_counts": lookahead_risk_counts,
        "multiple_testing_risk_counts": multiple_testing_risk_counts,
        "overall_risk_counts": overall_risk_counts,
        "avg_total_score": round(float(np.mean(total_scores)), 6) if total_scores else 0.0,
        "max_total_score": round(float(max(total_scores)), 6) if total_scores else 0.0,
    }


def _evaluate_active_pool_eligibility(item: dict[str, Any]) -> dict[str, Any]:
    rating = item.get("rating") if isinstance(item.get("rating"), dict) else {}
    risk_audit = item.get("risk_audit") if isinstance(item.get("risk_audit"), dict) else {}
    registry_stage = str(item.get("registry_stage") or "").strip().lower()
    recommendation = str(rating.get("recommendation") or "").strip().lower()
    total_score = _safe_float(rating.get("total_score"), 0.0)
    lookahead_risk = str(risk_audit.get("lookahead_risk_level") or "unknown").strip().lower()
    multiple_testing_risk = str(risk_audit.get("multiple_testing_risk_level") or "unknown").strip().lower()
    required_audits_complete = bool(risk_audit.get("required_audits_complete"))
    admission_blocked = bool(item.get("admission_blocked")) or bool(risk_audit.get("blocked"))
    block_reasons = _dedupe_tokens(risk_audit.get("block_reasons"))

    strict_reasons = []
    if registry_stage not in ACTIVE_REGISTRY_STAGES:
        strict_reasons.append(f"registry_stage_{registry_stage or 'unknown'}")
    strict_reasons.extend(block_reasons)
    strict_reasons = _dedupe_tokens(strict_reasons)

    provisional_reasons = []
    if registry_stage != PROVISIONAL_ACTIVE_REGISTRY_STAGE:
        provisional_reasons.append(f"registry_stage_{registry_stage or 'unknown'}")
    if recommendation not in PROVISIONAL_ACTIVE_RECOMMENDATIONS:
        provisional_reasons.append(f"recommendation_{recommendation or 'unknown'}")
    if admission_blocked:
        provisional_reasons.extend(block_reasons or ["admission_blocked"])
    if not required_audits_complete:
        provisional_reasons.append("required_audits_incomplete")
    if lookahead_risk not in PROVISIONAL_ACTIVE_RISK_LEVELS:
        provisional_reasons.append(f"lookahead_risk_{lookahead_risk or 'unknown'}")
    if multiple_testing_risk not in PROVISIONAL_ACTIVE_RISK_LEVELS:
        provisional_reasons.append(f"multiple_testing_risk_{multiple_testing_risk or 'unknown'}")
    if total_score < PROVISIONAL_ACTIVE_MIN_SCORE:
        provisional_reasons.append("score_below_provisional_threshold")
    provisional_reasons = _dedupe_tokens(provisional_reasons)

    return {
        "strict_eligible": not strict_reasons,
        "strict_reasons": strict_reasons,
        "provisional_eligible": not provisional_reasons,
        "provisional_reasons": provisional_reasons,
    }
