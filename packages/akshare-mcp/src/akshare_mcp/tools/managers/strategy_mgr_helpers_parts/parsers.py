
import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from strategy_factory.api import normalize_run_result_to_detail, normalize_run_result_to_summary
from strategy_factory import (
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    DEPRECATION_THRESHOLDS,
    PROMOTION_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
    QUALITY_GATE_THRESHOLDS,
    RISK_REPORT_THRESHOLDS,
)
from strategy_factory.api.quality_reporting import (
    build_quality_report as _shared_build_quality_report,
    normalize_quality_gate_result as _shared_normalize_quality_gate_result,
    quality_gate_reason_code as _shared_quality_gate_reason_code,
)

from ...services.strategy_lifecycle_shared import (
    LIFECYCLE_TRANSITIONS,
    build_incubation_overview,
    evaluate_confidence_contract,
    get_latest_quality_report,
    list_quality_reports,
    metric_bucket_value,
    normalize_status_alias,
    update_status,
    validate_transition,
)

logger = logging.getLogger(__name__)

_FACTORY_SUMMARY_OBSERVABILITY_FIELDS = (
    "execution_mode",
    "engine_version",
    "parity_status",
    "artifact_refs",
    "external_llm_provider_health_status",
    "external_llm_provider_control_mode",
    "external_llm_provider_control_reasons",
    "suppressed_generator_modes",
    "feedback_generator_mode_control_mode_counts",
    "external_llm_provider_suppressed",
    "external_llm_provider_cooldown",
    "candidate_local_attempt_count",
    "task_local_attempt_count",
    "cohort_effective_trials",
    "refresh_existing_count",
    "spawn_revision_from_existing_count",
    "unique_family_holding_universe_count",
    "economic_semantics_missing_count",
    "research_only_count",
    "deferred_submission_count",
    "validation_grade_distribution",
    "raw_validation_grade_distribution",
    "effective_validation_grade_distribution",
    "raw_validation_total_score_mean",
    "raw_validation_total_score_p50",
    "raw_validation_total_score_p90",
    "raw_validation_a_rate",
    "raw_validation_b_rate",
    "raw_validation_c_rate",
    "raw_validation_d_rate",
    "strict_incubation_ready_count",
    "strict_incubation_ready_rate",
    "live_candidate_ready_count",
    "live_candidate_ready_rate",
    "raw_b_or_above_count",
    "raw_b_or_above_rate",
    "strict_ready_given_raw_b_count",
    "strict_ready_given_raw_b_rate",
    "live_ready_given_raw_b_count",
    "live_ready_given_raw_b_rate",
    "strict_live_alignment_gap_count",
    "strict_live_alignment_gap_rate",
    "strict_live_alignment_status_counts",
    "validation_family_quality_panel",
    "prediction_quality_distribution",
    "execution_quality_distribution",
    "evidence_alignment_distribution",
    "confidence_contract_ready_rate",
)

_FACTORY_BASELINE_FORWARD_DAYS = (1, 5, 10, 20)
_FACTORY_GENERATION_LANE_DEFINITION = (
    "按持久化的 generator_mode / candidate_lane / quota_fill 证据切分生成层级；"
    "若 submitted 策略未保留 historical_guided 痕迹，L1 会并入 L0 规则层。"
)
_FACTORY_GENERATION_LANE_SORT_ORDER = {
    "l0_local_rule": 0,
    "l1_historical_guided": 1,
    "l2_external_known_type": 2,
    "l2_hypothesis_lowering": 3,
    "l3_open_dsl": 4,
    "unknown": 99,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    p = max(0.0, min(float(percentile), 1.0))
    index = p * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    result = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(result, 4)


def _grade_rates(distribution: dict[str, int], total: int) -> dict[str, float]:
    denominator = max(int(total or 0), 1)
    return {
        "raw_validation_a_rate": round(int(distribution.get("A") or 0) / denominator, 4) if total else 0.0,
        "raw_validation_b_rate": round(int(distribution.get("B") or 0) / denominator, 4) if total else 0.0,
        "raw_validation_c_rate": round(int(distribution.get("C") or 0) / denominator, 4) if total else 0.0,
        "raw_validation_d_rate": round(int(distribution.get("D") or 0) / denominator, 4) if total else 0.0,
    }


def _rate(count: int, total: int) -> float:
    return round(int(count or 0) / int(total or 0), 4) if total else 0.0


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _is_raw_b_or_above(grade: str) -> bool:
    return str(grade or "").strip().upper() in {"A", "B"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _brief_holding_bucket(payload: dict[str, Any]) -> str:
    return str(
        payload.get("holding_period_bucket")
        or payload.get("holding_bucket")
        or "unknown"
    ).strip().lower() or "unknown"


def _brief_target_universe_key(payload: dict[str, Any]) -> str:
    target_pool_id = str(payload.get("target_pool_id") or "").strip()
    if target_pool_id:
        return target_pool_id
    task_signature = str(payload.get("task_signature") or "").strip()
    if task_signature:
        return task_signature
    validation_focus = str(
        payload.get("validation_focus")
        or dict(payload.get("validation_profile") or {}).get("validation_focus")
        or ""
    ).strip()
    if validation_focus:
        return f"focus:{validation_focus}"
    return "unknown"


def _high_confidence_text(payload: dict[str, Any], key: str) -> str | None:
    record = dict(payload or {})
    params = dict(record.get("params") or {})
    incubation_overview = dict(record.get("incubation_overview") or {})
    for value in (
        record.get(key),
        incubation_overview.get(key),
        params.get(key),
    ):
        token = str(value or "").strip().lower()
        if token:
            return token
    return None


def _high_confidence_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    record = dict(payload or {})
    params = dict(record.get("params") or {})
    incubation_overview = dict(record.get("incubation_overview") or {})
    for value in (
        record.get(key),
        incubation_overview.get(key),
        params.get(key),
    ):
        if isinstance(value, dict):
            return dict(value)
    return {}


def _resolve_confidence_contract_status(payload: dict[str, Any]) -> str | None:
    explicit = _high_confidence_text(payload, "confidence_contract_status")
    contract = _high_confidence_mapping(payload, "confidence_contract")
    if contract:
        status, _ = evaluate_confidence_contract(contract)
        return status
    if explicit:
        return explicit
    if not contract:
        return None
    return None


def _resolve_evidence_alignment_status(payload: dict[str, Any]) -> str | None:
    record = dict(payload or {})
    params = dict(record.get("params") or {})
    audit = dict(
        record.get("evidence_alignment_audit")
        or params.get("evidence_alignment_audit")
        or {}
    )
    status = str(
        audit.get("evidence_alignment_status") or record.get("evidence_alignment_status") or ""
    ).strip().lower()
    if status:
        return status
    if record.get("legacy_semantic_contract") is True or params.get("legacy_semantic_contract") is True:
        return "legacy"
    return None


def _summarize_high_confidence_quality(records: list[dict[str, Any]]) -> dict[str, Any]:
    prediction_quality_distribution: dict[str, int] = {}
    execution_quality_distribution: dict[str, int] = {}
    evidence_alignment_distribution: dict[str, int] = {}
    confidence_contract_ready_count = 0
    total = len(records)
    for record in list(records or []):
        payload = dict(record or {})
        prediction_label = _high_confidence_text(payload, "prediction_quality_label")
        execution_label = _high_confidence_text(payload, "execution_quality_label")
        evidence_alignment_status = _resolve_evidence_alignment_status(payload)
        confidence_contract_status = _resolve_confidence_contract_status(payload)
        if prediction_label:
            prediction_quality_distribution[prediction_label] = (
                prediction_quality_distribution.get(prediction_label, 0) + 1
            )
        if execution_label:
            execution_quality_distribution[execution_label] = (
                execution_quality_distribution.get(execution_label, 0) + 1
            )
        if evidence_alignment_status:
            evidence_alignment_distribution[evidence_alignment_status] = (
                evidence_alignment_distribution.get(evidence_alignment_status, 0) + 1
            )
        if confidence_contract_status in {"diagnostic_ready", "comparable_ready"}:
            confidence_contract_ready_count += 1
    return {
        "prediction_quality_distribution": prediction_quality_distribution,
        "execution_quality_distribution": execution_quality_distribution,
        "evidence_alignment_distribution": evidence_alignment_distribution,
        "confidence_contract_ready_rate": (
            round(confidence_contract_ready_count / total, 4) if total else 0.0
        ),
    }


def _build_family_quality_panel(overviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for overview in list(overviews or []):
        payload = dict(overview or {})
        family = str(payload.get("candidate_family") or payload.get("strategy_type") or "unknown").strip().lower() or "unknown"
        holding_bucket = str(payload.get("holding_period_bucket") or "unknown").strip().lower() or "unknown"
        validation_focus = str(payload.get("validation_focus") or "unknown").strip().lower() or "unknown"
        key = (family, holding_bucket, validation_focus)
        bucket = buckets.setdefault(
            key,
            {
                "strategy_family": family,
                "holding_period_bucket": holding_bucket,
                "validation_focus": validation_focus,
                "strategy_count": 0,
                "raw_validation_grade_distribution": {},
                "effective_validation_grade_distribution": {},
                "raw_validation_total_scores": [],
                "strict_incubation_ready_count": 0,
                "live_candidate_ready_count": 0,
                "raw_b_or_above_count": 0,
                "strict_ready_given_raw_b_count": 0,
                "live_ready_given_raw_b_count": 0,
                "trade_density_values": [],
                "post_cost_sharpe_values": [],
                "deflated_sharpe_ratio_values": [],
                "pbo_values": [],
            },
        )
        bucket["strategy_count"] += 1
        raw_grade = str(payload.get("raw_validation_grade") or payload.get("validation_grade") or "").strip().upper()
        effective_grade = str(
            payload.get("effective_validation_grade") or payload.get("validation_grade") or ""
        ).strip().upper()
        if raw_grade:
            bucket["raw_validation_grade_distribution"][raw_grade] = (
                bucket["raw_validation_grade_distribution"].get(raw_grade, 0) + 1
            )
        if effective_grade:
            bucket["effective_validation_grade_distribution"][effective_grade] = (
                bucket["effective_validation_grade_distribution"].get(effective_grade, 0) + 1
            )
        if payload.get("raw_validation_total_score") is not None:
            bucket["raw_validation_total_scores"].append(_safe_float(payload.get("raw_validation_total_score")))
        strict_ready = payload.get("strict_incubation_ready") is True
        live_ready = payload.get("live_candidate_ready") is True
        if strict_ready:
            bucket["strict_incubation_ready_count"] += 1
        if live_ready:
            bucket["live_candidate_ready_count"] += 1
        if _is_raw_b_or_above(raw_grade):
            bucket["raw_b_or_above_count"] += 1
            if strict_ready:
                bucket["strict_ready_given_raw_b_count"] += 1
            if live_ready:
                bucket["live_ready_given_raw_b_count"] += 1
        for metric_key, bucket_key in (
            ("trade_density", "trade_density_values"),
            ("post_cost_sharpe", "post_cost_sharpe_values"),
            ("deflated_sharpe_ratio", "deflated_sharpe_ratio_values"),
            ("pbo", "pbo_values"),
        ):
            if payload.get(metric_key) is not None:
                bucket[bucket_key].append(_safe_float(payload.get(metric_key)))

    panel: list[dict[str, Any]] = []
    for bucket in buckets.values():
        strategy_count = int(bucket.get("strategy_count") or 0)
        raw_distribution = dict(bucket.get("raw_validation_grade_distribution") or {})
        raw_scores = list(bucket.get("raw_validation_total_scores") or [])
        trade_density_values = list(bucket.get("trade_density_values") or [])
        post_cost_sharpe_values = list(bucket.get("post_cost_sharpe_values") or [])
        dsr_values = list(bucket.get("deflated_sharpe_ratio_values") or [])
        pbo_values = list(bucket.get("pbo_values") or [])
        raw_b_or_above_count = int(bucket.get("raw_b_or_above_count") or 0)
        strict_ready_given_raw_b_count = int(
            bucket.get("strict_ready_given_raw_b_count") or 0
        )
        live_ready_given_raw_b_count = int(bucket.get("live_ready_given_raw_b_count") or 0)
        item = {
            "strategy_family": bucket.get("strategy_family"),
            "holding_period_bucket": bucket.get("holding_period_bucket"),
            "validation_focus": bucket.get("validation_focus"),
            "strategy_count": strategy_count,
            "raw_validation_grade_distribution": raw_distribution,
            "effective_validation_grade_distribution": dict(
                bucket.get("effective_validation_grade_distribution") or {}
            ),
            "raw_validation_total_score_mean": round(sum(raw_scores) / len(raw_scores), 4) if raw_scores else 0.0,
            "strict_incubation_ready_count": int(bucket.get("strict_incubation_ready_count") or 0),
            "strict_incubation_ready_rate": round(
                int(bucket.get("strict_incubation_ready_count") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "live_candidate_ready_count": int(bucket.get("live_candidate_ready_count") or 0),
            "live_candidate_ready_rate": round(
                int(bucket.get("live_candidate_ready_count") or 0) / strategy_count,
                4,
            ) if strategy_count else 0.0,
            "raw_b_or_above_count": raw_b_or_above_count,
            "raw_b_or_above_rate": _rate(raw_b_or_above_count, strategy_count),
            "strict_ready_given_raw_b_count": strict_ready_given_raw_b_count,
            "strict_ready_given_raw_b_rate": _rate(
                strict_ready_given_raw_b_count,
                raw_b_or_above_count,
            ),
            "live_ready_given_raw_b_count": live_ready_given_raw_b_count,
            "live_ready_given_raw_b_rate": _rate(
                live_ready_given_raw_b_count,
                raw_b_or_above_count,
            ),
            "mean_trade_density": round(sum(trade_density_values) / len(trade_density_values), 4)
            if trade_density_values else 0.0,
            "mean_post_cost_sharpe": round(sum(post_cost_sharpe_values) / len(post_cost_sharpe_values), 4)
            if post_cost_sharpe_values else 0.0,
            "mean_deflated_sharpe_ratio": round(sum(dsr_values) / len(dsr_values), 4)
            if dsr_values else 0.0,
            "mean_pbo": round(sum(pbo_values) / len(pbo_values), 4) if pbo_values else 0.0,
        }
        item.update(_grade_rates(raw_distribution, strategy_count))
        item.update(
            {
                "family_raw_a_rate": item.get("raw_validation_a_rate", 0.0),
                "family_raw_b_rate": item.get("raw_validation_b_rate", 0.0),
                "family_raw_c_rate": item.get("raw_validation_c_rate", 0.0),
                "family_raw_d_rate": item.get("raw_validation_d_rate", 0.0),
                "family_strict_incubation_ready_rate": item.get(
                    "strict_incubation_ready_rate",
                    0.0,
                ),
                "family_live_candidate_ready_rate": item.get(
                    "live_candidate_ready_rate",
                    0.0,
                ),
                "family_mean_trade_density": item.get("mean_trade_density", 0.0),
                "family_mean_post_cost_sharpe": item.get("mean_post_cost_sharpe", 0.0),
                "family_mean_dsr": item.get("mean_deflated_sharpe_ratio", 0.0),
                "family_mean_pbo": item.get("mean_pbo", 0.0),
            }
        )
        panel.append(item)
    panel.sort(
        key=lambda item: (
            int(item.get("strategy_count") or 0),
            float(item.get("raw_validation_b_rate") or 0.0),
            float(item.get("raw_validation_a_rate") or 0.0),
            str(item.get("strategy_family") or ""),
        ),
        reverse=True,
    )
    return panel[:24]


def _extract_generation_lane(payload: dict[str, Any]) -> dict[str, str]:
    data = dict(payload or {})
    params = dict(data.get("params") or {})
    candidate_provenance = dict(
        data.get("candidate_provenance")
        or params.get("candidate_provenance")
        or {}
    )
    quota_fill = dict(data.get("quota_fill") or params.get("quota_fill") or {})
    tags = {
        _normalized_text(tag)
        for tag in [*list(data.get("tags") or []), *list(params.get("tags") or [])]
        if _normalized_text(tag)
    }

    generator_mode = (
        _normalized_text(data.get("generator_mode"))
        or _normalized_text(data.get("generator_type"))
        or _normalized_text(params.get("generator_mode"))
        or _normalized_text(params.get("generator_type"))
        or _normalized_text(candidate_provenance.get("generator_mode"))
        or _normalized_text(candidate_provenance.get("generator_type"))
    )
    candidate_lane = (
        _normalized_text(data.get("candidate_lane"))
        or _normalized_text(params.get("candidate_lane"))
        or _normalized_text(candidate_provenance.get("candidate_lane"))
    )
    parameter_source = (
        _normalized_text(data.get("parameter_source"))
        or _normalized_text(params.get("parameter_source"))
        or _normalized_text(quota_fill.get("parameter_source"))
    )
    fill_source_mode = (
        _normalized_text(data.get("fill_source_mode"))
        or _normalized_text(params.get("fill_source_mode"))
        or _normalized_text(quota_fill.get("fill_source_mode"))
    )

    if (
        candidate_lane == "l3_open_dsl"
        or generator_mode in {"llm_defined", "open_dsl", "llm_defined_dsl"}
        or "llm_defined" in tags
        or "open_dsl" in tags
    ):
        return {
            "lane_key": "l3_open_dsl",
            "lane_label": "L3 Open DSL",
            "generation_tier": "L3",
            "generator_mode": generator_mode or "llm_defined",
        }
    if (
        candidate_lane == "l2_hypothesis_lowering"
        or generator_mode in {"llm_hypothesis_compiler", "hypothesis_replay"}
    ):
        return {
            "lane_key": "l2_hypothesis_lowering",
            "lane_label": "L2 Hypothesis Lowering",
            "generation_tier": "L2",
            "generator_mode": generator_mode or "llm_hypothesis_compiler",
        }
    if parameter_source == "historical_distribution" or fill_source_mode == "historical_guided":
        return {
            "lane_key": "l1_historical_guided",
            "lane_label": "L1 Historical Guided Rule",
            "generation_tier": "L1",
            "generator_mode": generator_mode or "rule",
        }
    if (
        generator_mode in {
            "external_llm",
            "pipeline_staged",
            "llm_proxy",
            "llm_proxy_fallback",
            "external_llm_open_dsl",
            "rl_bandit",
        }
        or "external_llm" in tags
        or "ai_generated" in tags
    ):
        return {
            "lane_key": "l2_external_known_type",
            "lane_label": "L2 External Known-Type",
            "generation_tier": "L2",
            "generator_mode": generator_mode or "external_llm",
        }
    if (
        generator_mode in {"bulk_stock_matrix", "rule", "local_rule", "local_rule_v1"}
        or "rule" in tags
        or data.get("generation_reason")
        or data.get("spawn_reason")
    ):
        return {
            "lane_key": "l0_local_rule",
            "lane_label": "L0 Local Rule",
            "generation_tier": "L0",
            "generator_mode": generator_mode or "rule",
        }
    return {
        "lane_key": "unknown",
        "lane_label": "Unknown / Unlabeled",
        "generation_tier": "unknown",
        "generator_mode": generator_mode or "unknown",
    }
