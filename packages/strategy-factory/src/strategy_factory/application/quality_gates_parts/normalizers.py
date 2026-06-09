
from __future__ import annotations

import asyncio
import json
import logging
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..domain.constants import (
    BACKTEST_CONCURRENCY,
    FACTORY_PRE_GATE_ENABLED,
    GATE1_PASS_RATIO,
    GATE1_REPRESENTATIVE_COUNT,
    GATE1_SHARPE_MIN,
    GATE2_TOPK_FLOOR,
    GATE2_TOPK_USE_CEIL,
    REPRESENTATIVE_STOCKS,
)
from ..domain.strategy_profile import candidate_signature, infer_candidate_strategy_profile
from ..domain.targets import _build_target_alignment_contract
from ..domain.targets import _extract_target_codes_from_payload
from ..domain.targets import _normalize_target_codes
from ..domain.targets import _normalize_research_task_contract
from ..infrastructure.mcp_services import get_strategy_dsl_compiler
from .backtest_filter import build_target_quality_gate_summary
from .candidate_contract import (
    apply_resolved_candidate_envelope,
    build_candidate_contract_hash,
    build_factory_backtest_assumptions,
    build_portfolio_candidate_contract,
    build_tested_object_hash,
    candidate_contract_value,
)
from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package

logger = logging.getLogger(__name__)

_PRE_GATE_SIGNAL_DENSITY_MIN = 4.0
_PRE_GATE_SIGNAL_DENSITY_MAX = 100.0
_PRE_GATE_FAMILY_QUOTA_DEFAULT = 8
_PRE_GATE_PER_STOCK_QUOTA_DEFAULT = 5
_GATE_0_BATCH_SIZE = 100
_SNAPSHOT_ALIGNMENT_HARD_BLOCK_COVERAGE = 0.05
_SNAPSHOT_ALIGNMENT_HARD_BLOCK_INTERSECTION = 0.05
_SNAPSHOT_ALIGNMENT_SOFT_COVERAGE = 0.35
_SNAPSHOT_ALIGNMENT_SOFT_INTERSECTION = 0.25
_SNAPSHOT_HIGH_TURNOVER_THRESHOLD = 1.25
_SNAPSHOT_VERY_HIGH_TURNOVER_THRESHOLD = 1.75
_SNAPSHOT_LOW_EDGE_BUFFER = 0.12
_PIPELINE_MA_CROSS_GATE1_REPRESENTATIVE_FLOOR = 5
_PIPELINE_RSI_GATE1_REPRESENTATIVE_FLOOR = 4
_PIPELINE_RSI_ALIGNMENT_HARD_BLOCK_INTERSECTION = 0.5
_PIPELINE_MA_CROSS_HIGH_TURNOVER_THRESHOLD = 1.5
_PIPELINE_MA_CROSS_VERY_HIGH_TURNOVER_THRESHOLD = 2.0
_PIPELINE_MA_CROSS_EDGE_RETURN_FLOOR = 0.01
_RL_BANDIT_ALIGNMENT_HARD_BLOCK_COVERAGE = 0.3
_RL_BANDIT_ALIGNMENT_HARD_BLOCK_INTERSECTION = 0.45
_RL_BANDIT_ALIGNMENT_SOFT_COVERAGE = 0.4
_RL_BANDIT_ALIGNMENT_SOFT_INTERSECTION = 0.5
_RL_BANDIT_VOLATILITY_BREAKOUT_ALIGNMENT_HARD_BLOCK_INTERSECTION = 0.15
_RL_BANDIT_VOLATILITY_BREAKOUT_ALIGNMENT_MIN_TARGET_COUNT = 10
_PRE_GATE_MARKET_CAP_THRESHOLDS = {
    "high": 20_000_000_000.0,
    "medium": 8_000_000_000.0,
    "low": 2_000_000_000.0,
    "all": 0.0,
}
_PRE_GATE_TURNOVER_THRESHOLDS = {
    "high": 1_500_000_000.0,
    "medium": 300_000_000.0,
    "low": 50_000_000.0,
    "all": 0.0,
}

def _compat_setting(name: str, default):
    return default


async def _compat_gate_1_fast_screen(candidate: dict, db, *, kline_cache: Optional[Dict[str, list]] = None):
    return await gate_1_fast_screen(candidate, db, kline_cache=kline_cache)


def get_strategy_factory_package():
    return _runtime_get_strategy_factory_package()


def _normalized_gate_3_counts(submission_result: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    payload = dict(submission_result or {})
    input_count = int(payload.get("gate_3_input", payload.get("submitted", 0)))
    submitted = int(payload.get("submitted", 0))
    passed_count = int(payload.get("gate_3_passed", payload.get("passed_quality_gate", 0)))
    failed_count = int(payload.get("gate_3_failed", max(input_count - passed_count, 0)))
    provisional_passed_count = int(payload.get("gate_3_provisional_passed", 0))
    return {
        "input_count": input_count,
        "submitted": submitted,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "provisional_passed_count": provisional_passed_count,
    }


def build_pending_gate_3_report(pending_count: int) -> Dict[str, Any]:
    return {
        "status": "pending_submission_gate",
        "input_count": int(pending_count),
        "passed_count": 0,
        "failed_count": 0,
        "pending_count": int(pending_count),
        "delegate": "submission_gate.run_submission_quality_gate",
        "reason": "gate_3_executes_during_submission",
    }


def build_completed_gate_3_report(submission_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(submission_result or {})
    counts = _normalized_gate_3_counts(payload)
    return {
        "gate_3": {
            "status": "completed_submission_gate",
            "input_count": counts["input_count"],
            "passed_count": counts["passed_count"],
            "failed_count": counts["failed_count"],
            "pending_count": 0,
            "provisional_passed_count": counts["provisional_passed_count"],
            "recorded_count": int(payload.get("gate_3_recorded") or 0),
            "quality_recorded_count": int(
                payload.get("gate3_quality_recorded")
                or payload.get("gate3_record_quality_qualified_count")
                or 0
            ),
            "diagnostic_recorded_count": int(payload.get("gate3_record_diagnostic_only_count") or 0),
            "failure_reason_topn": list(payload.get("gate_3_failure_reason_topn") or []),
            "gate3_audit_failed_count": int(payload.get("gate3_audit_failed_count") or counts["failed_count"]),
            "observe_admitted_count": int(payload.get("observe_admitted_count") or 0),
            "pre_observe_hard_reject_count": int(payload.get("pre_observe_hard_reject_count") or 0),
            "formal_incubation_count": int(payload.get("formal_incubation_count") or 0),
            "observe_incubation_count": int(payload.get("observe_incubation_count") or 0),
            "diagnostic_observation_count": int(payload.get("diagnostic_observation_count") or 0),
            "live_ready_review_count": int(payload.get("live_ready_review_count") or 0),
            "deferred_submission_count": int(payload.get("deferred_submission_count") or 0),
            "research_only_count": int(payload.get("research_only_count") or 0),
            "strict_incubation_ready_count": int(payload.get("strict_incubation_ready_count") or 0),
        },
        "final_decision": {
            "stage": "gate_3",
            "passed_count": counts["passed_count"],
            "failed_count": counts["failed_count"],
            "provisional_passed_count": counts["provisional_passed_count"],
            "recorded_count": int(payload.get("gate_3_recorded") or 0),
            "quality_recorded_count": int(
                payload.get("gate3_quality_recorded")
                or payload.get("gate3_record_quality_qualified_count")
                or 0
            ),
            "diagnostic_recorded_count": int(payload.get("gate3_record_diagnostic_only_count") or 0),
            "gate3_audit_failed_count": int(payload.get("gate3_audit_failed_count") or counts["failed_count"]),
            "observe_admitted_count": int(payload.get("observe_admitted_count") or 0),
            "pre_observe_hard_reject_count": int(payload.get("pre_observe_hard_reject_count") or 0),
            "formal_incubation_count": int(payload.get("formal_incubation_count") or 0),
            "observe_incubation_count": int(payload.get("observe_incubation_count") or 0),
            "diagnostic_observation_count": int(payload.get("diagnostic_observation_count") or 0),
            "live_ready_review_count": int(payload.get("live_ready_review_count") or 0),
            "deferred_submission_count": int(payload.get("deferred_submission_count") or 0),
            "research_only_count": int(payload.get("research_only_count") or 0),
        },
    }


def _gate_2_group_key(candidate: dict) -> str:
    payload = dict(candidate or {})
    generation_reason = dict(payload.get("generation_reason") or {})
    research_task = dict(payload.get("research_task") or {})
    parent_strategy_id = str(
        payload.get("parent_strategy_id")
        or generation_reason.get("parent_strategy_id")
        or research_task.get("parent_strategy_id")
        or ""
    ).strip()
    if parent_strategy_id:
        return f"parent:{parent_strategy_id}"

    task_key = str(research_task.get("task_key") or research_task.get("task_id") or "").strip()
    if task_key:
        return f"task:{task_key}"

    strategy_type = str(payload.get("strategy_type") or "unknown").strip().lower() or "unknown"
    target_codes = tuple(sorted(_extract_target_codes_from_payload(payload, limit=4)))
    if target_codes:
        return f"universe:{strategy_type}:{','.join(target_codes)}"
    return f"type:{strategy_type}"


def _is_bulk_stock_matrix_candidate(candidate: dict) -> bool:
    payload = dict(candidate or {})
    research_task = dict(payload.get("research_task") or {})
    task_source = str(
        research_task.get("task_source")
        or payload.get("task_source")
        or payload.get("generator_mode")
        or ""
    ).strip().lower()
    return task_source == "bulk_stock_matrix"


def _resolve_gate_1_representative_count(candidate: dict, default_count: int) -> int:
    payload = dict(candidate or {})
    research_task = dict(payload.get("research_task") or {})
    normalized_task = _normalize_research_task_contract(research_task)
    explicit = (
        payload.get("gate_1_representative_count")
        or research_task.get("gate_1_representative_count")
    )
    if explicit is not None:
        try:
            resolved = max(1, int(explicit))
        except Exception:
            resolved = max(1, int(default_count or 1))
    elif _is_bulk_stock_matrix_candidate(payload):
        resolved = 1
    else:
        resolved = max(1, int(default_count or 1))

    target_count = len(_extract_target_codes_from_payload(payload, limit=12))
    validation_focus = str(normalized_task.get("validation_focus") or "").strip().lower()
    target_alignment_contract = _build_target_alignment_contract(normalized_task, candidate=payload)
    min_target_sample_count = int(target_alignment_contract.get("min_target_sample_count") or 0)
    if (
        target_count > 1
        and _is_targeted_snapshot_candidate(
            payload,
            normalized_task,
            target_count=target_count,
            validation_focus=validation_focus,
        )
        and min_target_sample_count > 0
    ):
        resolved = max(resolved, min(target_count, min_target_sample_count))
    if (
        target_count > 1
        and _is_targeted_snapshot_candidate(
            payload,
            normalized_task,
            target_count=target_count,
            validation_focus=validation_focus,
        )
        and _is_pipeline_staged_ma_cross_candidate(payload, normalized_task)
    ):
        # Snapshot basket ma_cross routinely looked strong on a single-stock fast screen
        # and then collapsed once Gate-2 evaluated the whole basket. Widen the Gate-1
        # sample so these fragile candidates are filtered earlier.
        resolved = max(
            resolved,
            min(target_count, _PIPELINE_MA_CROSS_GATE1_REPRESENTATIVE_FLOOR),
        )

    if (
        target_count > 1
        and _is_targeted_snapshot_candidate(
            payload,
            normalized_task,
            target_count=target_count,
            validation_focus=validation_focus,
        )
        and _is_pipeline_staged_rsi_candidate(payload, normalized_task)
    ):
        # Snapshot basket RSI has become the main Gate-2 leak source. We now force a
        # wider target sample so Gate-1 can expose low-overlap / low-stability
        # baskets before they consume full-backtest capacity.
        resolved = max(
            resolved,
            min(target_count, _PIPELINE_RSI_GATE1_REPRESENTATIVE_FLOOR),
        )

    return resolved


def _resolve_gate_1_codes(
    candidate: dict,
) -> tuple[list[str], list[str], str, str, dict[str, Any]]:
    def _preferred_target_order(payload: dict) -> list[str]:
        params = dict(payload.get("params") or {})
        envelope = dict(payload.get("resolved_candidate_envelope") or {})
        preferred = []
        for source in (
            payload.get("requested_target_symbols"),
            params.get("requested_target_symbols"),
            envelope.get("requested_target_symbols"),
        ):
            preferred.extend(_normalize_target_codes(source, limit=12))
        return list(dict.fromkeys(preferred))

    def _apply_preferred_order(codes: list[str], preferred: list[str]) -> list[str]:
        if not codes or not preferred:
            return list(codes)
        preferred_set = set(codes)
        ordered = [code for code in preferred if code in preferred_set]
        ordered.extend(code for code in codes if code not in ordered)
        return ordered

    representative_stocks = list(_compat_setting("REPRESENTATIVE_STOCKS", REPRESENTATIVE_STOCKS))
    representative_count = _resolve_gate_1_representative_count(
        candidate,
        int(_compat_setting("GATE1_REPRESENTATIVE_COUNT", GATE1_REPRESENTATIVE_COUNT) or GATE1_REPRESENTATIVE_COUNT),
    )
    research_task = _normalize_research_task_contract(candidate.get("research_task"))
    validation_focus = str(research_task.get("validation_focus") or "target_plus_representative").strip().lower()
    target_codes = _extract_target_codes_from_payload(candidate, limit=max(representative_count, 12))
    target_codes = _apply_preferred_order(target_codes, _preferred_target_order(dict(candidate or {})))
    prioritized_target_codes = list(target_codes[:representative_count])
    padded_representatives = [code for code in representative_stocks if code not in prioritized_target_codes]
    if validation_focus == "event_target_only" and prioritized_target_codes:
        codes = list(prioritized_target_codes)
        code_source = "event_target_only"
    else:
        codes = list(dict.fromkeys([*prioritized_target_codes, *padded_representatives]))[
            : max(representative_count, len(prioritized_target_codes))
        ]
        code_source = "candidate_target_symbols" if prioritized_target_codes else "representative_only"
    return codes, prioritized_target_codes, code_source, validation_focus, research_task


def _collect_gate_1_preload_codes(candidates: list[dict]) -> list[str]:
    ordered_codes: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        codes, _target_codes, _code_source, _validation_focus, _research_task = _resolve_gate_1_codes(candidate)
        for code in codes:
            if code in seen:
                continue
            seen.add(code)
            ordered_codes.append(code)
    return ordered_codes


def _candidate_constraint_check(candidate: dict) -> dict[str, Any]:
    payload = dict(candidate or {})
    for source in (
        payload,
        dict(payload.get("params") or {}),
        _normalize_research_task_contract(payload.get("research_task") or {}),
    ):
        constraint_check = source.get("constraint_check")
        if isinstance(constraint_check, dict) and constraint_check:
            return dict(constraint_check)
    return {}


def _candidate_tags(candidate: dict) -> set[str]:
    payload = dict(candidate or {})
    return {
        str(tag).strip().lower()
        for tag in list(payload.get("tags") or [])
        if str(tag).strip()
    }


def _candidate_generation_mode(candidate: dict, research_task: Optional[dict] = None) -> str:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    dsl_metadata = dict((dict((payload.get("params") or {}).get("dsl") or {}).get("metadata") or {}))
    strategy_profile = dict(dsl_metadata.get("strategy_profile") or {})
    candidate_provenance = dict(payload.get("candidate_provenance") or {})
    generation_reason = dict(payload.get("generation_reason") or {})
    for source in (
        payload,
        dict(payload.get("params") or {}),
        normalized_task,
        strategy_profile,
        candidate_provenance,
        generation_reason,
    ):
        if not isinstance(source, dict):
            continue
        for key in ("generator_type", "generator_mode"):
            value = str(source.get(key) or "").strip().lower()
            if value:
                return value
    return ""


def _is_targeted_snapshot_candidate(
    candidate: dict,
    research_task: Optional[dict] = None,
    *,
    tags: Optional[set[str]] = None,
    target_count: Optional[int] = None,
    validation_focus: Optional[str] = None,
) -> bool:
    payload = dict(candidate or {})
    normalized_task = _normalize_research_task_contract(research_task or payload.get("research_task") or {})
    resolved_tags = tags if tags is not None else _candidate_tags(payload)
    candidate_target_count = int(target_count if target_count is not None else len(_extract_target_codes_from_payload(payload, limit=12)))
    task_target_count = len(list(normalized_task.get("target_symbols") or []))
    resolved_target_count = max(candidate_target_count, task_target_count)
    resolved_validation_focus = str(
        validation_focus if validation_focus is not None else normalized_task.get("validation_focus") or ""
    ).strip().lower()
    task_source = str(
        normalized_task.get("task_source")
        or payload.get("task_source")
        or payload.get("generator_mode")
        or ""
    ).strip().lower()
    return (
        task_source == "snapshot"
        and resolved_target_count > 0
        and (
            "targeted_universe" in resolved_tags
            or resolved_validation_focus in {"candidate_target_only", "event_target_only", "target_plus_representative"}
        )
    )


def _is_pipeline_staged_ma_cross_candidate(candidate: dict, research_task: Optional[dict] = None) -> bool:
    payload = dict(candidate or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    generation_mode = _candidate_generation_mode(payload, research_task)
    tags = _candidate_tags(payload)
    return strategy_type == "ma_cross" and (
        generation_mode == "pipeline_staged"
        or "pipeline_staged" in tags
        or "generator_pipeline_staged" in tags
    )


def _is_pipeline_staged_rsi_candidate(candidate: dict, research_task: Optional[dict] = None) -> bool:
    payload = dict(candidate or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    generation_mode = _candidate_generation_mode(payload, research_task)
    tags = _candidate_tags(payload)
    return strategy_type == "rsi" and (
        generation_mode == "pipeline_staged"
        or "pipeline_staged" in tags
        or "generator_pipeline_staged" in tags
    )
