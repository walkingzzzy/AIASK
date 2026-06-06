"""策略工厂候选提交。"""


from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import time as _time
from collections import Counter
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import uuid4

from ..candidate_contract import (
    apply_resolved_candidate_envelope,
    build_candidate_contract_hash,
    build_candidate_identity_signature,
    build_execution_contract_hash,
    build_portfolio_candidate_contract,
    build_resolved_candidate_envelope,
    build_tested_object_hash,
    candidate_contract_value,
)
from ..incubation_budgeter import IncubationBudgeter
from ..compact_contracts import compact_event_window_metrics, compact_json, compact_scalar_metrics
from ..quality_gates import _VALID_STRATEGY_TYPES, build_completed_gate_3_report
from ..quality_reporting import build_quality_report, normalize_quality_gate_result
from ..semantic_contract import (
    audit_candidate_semantic_contract,
    build_candidate_evidence_records,
    ensure_candidate_semantic_contract,
    normalize_semantic_contract_fields,
    synthesize_confidence_contract,
)
from ..submission_gate import run_submission_quality_gate as _local_run_submission_quality_gate
from ..trade_prediction_promotion_gate import (
    evaluate_trade_prediction_promotion_gate,
)
from ..utils import (
    _auto_name as _local_auto_name,
    _extract_event_context as _local_extract_event_context,
    _update_strategy_status as _local_update_strategy_status,
    get_strategy_factory_package as _local_get_strategy_factory_package,
)
from ..research_protocol_contract import (
    adapt_research_validation_contract_for_submission,
    normalize_prediction_trace_id,
)
from ..services.submission_coordinator import SubmissionExecutionOptions
from ..services.admission_authority import SubmissionAdmissionAuthority
from .._runtime_toggles import (
    diagnostic_observation_batch_limit as _diagnostic_observation_batch_limit,
    diagnostic_observation_dedupe_enabled as _diagnostic_observation_dedupe_enabled,
    diagnostic_observation_enabled as _diagnostic_observation_enabled,
    diagnostic_observation_final_status as _diagnostic_observation_final_status,
    diagnostic_observation_health_guard_enabled as _diagnostic_observation_health_guard_enabled,
    diagnostic_observation_health_max_age_hours as _diagnostic_observation_health_max_age_hours,
    diagnostic_observation_min_trade_count as _diagnostic_observation_min_trade_count,
    diagnostic_observation_min_win_rate as _diagnostic_observation_min_win_rate,
    diagnostic_observation_ttl_days as _diagnostic_observation_ttl_days,
    observe_first_enabled as _observe_first_enabled,
    observe_d_grade_enabled as _observe_d_grade_enabled,
    wide_intake_observe_enabled as _wide_intake_observe_enabled,
)
from ...domain.constants import (
    FACTORY_SUBMISSION_MIN_BACKTEST_TRADES,
    FACTORY_SUBMISSION_MIN_EVENT_TARGET_COVERAGE,
    FACTORY_SUBMISSION_REJECT_GENERIC_AI_NAMES,
    FACTORY_SUBMISSION_REQUIRE_STRICT_PASS_FOR_REFRESH,
    FACTORY_SUBMISSION_REQUIRE_TASK_PREFERENCE_MATCH,
    STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE,
    STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED,
    SUBMIT_CONCURRENCY,
)
from ...domain.targets import _build_task_signature, _normalize_research_task_contract, _normalize_target_codes
from ...infrastructure.mcp_services import (
    build_strategy_vector_profile,
    get_strategy_promotion_pipeline_service,
    get_strategy_runtime_control_service,
)

if TYPE_CHECKING:
    from ...api.contracts import IncubationGateway, RiskGateway, ValidationGateway

logger = logging.getLogger(__name__)


def _compact_unique(values: Any, *, limit: int = 12) -> list[str]:
    items: list[str] = []
    for value in list(values or []):
        token = str(value or "").strip()
        if token and token not in items:
            items.append(token)
        if len(items) >= max(1, int(limit or 12)):
            break
    return items


def _candidate_trace_ids(candidate: dict[str, Any]) -> list[str]:
    trace_id = normalize_prediction_trace_id(
        candidate.get("prediction_trace_id"),
        candidate.get("trace_id"),
        fallback=dict(candidate.get("params") or {}).get("prediction_trace_id"),
    )
    return [trace_id] if trace_id else []


def _candidate_artifact_ids(candidate: dict[str, Any]) -> list[str]:
    provenance = dict(candidate.get("candidate_provenance") or {})
    params = dict(candidate.get("params") or {})
    return _compact_unique(
        [
            provenance.get("source_candidate_artifact_id"),
            provenance.get("source_generation_artifact_id"),
            provenance.get("source_validation_artifact_id"),
            provenance.get("memory_record_id"),
            candidate.get("hypothesis_artifact_id"),
            candidate.get("experiment_id"),
            candidate.get("multiple_testing_registry_record_id"),
            params.get("source_candidate_artifact_id"),
            params.get("source_generation_artifact_id"),
            params.get("source_validation_artifact_id"),
            params.get("candidate_memory_record_id"),
            params.get("multiple_testing_registry_record_id"),
            params.get("task_run_id"),
        ]
    )


def _candidate_retrieval_context_ids(candidate: dict[str, Any]) -> list[str]:
    provenance = dict(candidate.get("candidate_provenance") or {})
    research_task = dict(candidate.get("research_task") or {})
    params = dict(candidate.get("params") or {})
    return _compact_unique(
        [
            research_task.get("task_id"),
            research_task.get("event_id"),
            candidate.get("task_run_id"),
            candidate.get("multiple_testing_registry_record_id"),
            provenance.get("memory_record_id"),
            params.get("task_run_id"),
            params.get("multiple_testing_registry_record_id"),
            params.get("candidate_memory_record_id"),
            params.get("vector_profile_id"),
        ]
    )


def _candidate_family_outcome_summary(
    candidate: dict[str, Any],
    *,
    final_status: str | None = None,
) -> dict[str, Any]:
    provenance = dict(candidate.get("candidate_provenance") or {})
    family = (
        provenance.get("candidate_family")
        or candidate.get("candidate_family")
        or dict(candidate.get("params") or {}).get("candidate_family")
        or candidate.get("strategy_type")
    )
    return {
        "candidate_family": str(family or "").strip().lower() or None,
        "strategy_type": str(candidate.get("strategy_type") or "").strip().lower() or None,
        "spec_completeness": str(candidate.get("spec_completeness") or "").strip().lower() or None,
        "final_status": str(final_status or "").strip().lower() or None,
    }


def _candidate_hard_failures(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    hard_failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in list(candidate.get("hard_failures") or []):
        payload = dict(raw or {})
        field_name = str(payload.get("field") or "").strip()
        reason_code = str(payload.get("reason_code") or payload.get("issue") or field_name).strip()
        if not reason_code:
            continue
        dedupe_key = (field_name, reason_code)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized = {
            "reason_code": reason_code,
            "issue": str(payload.get("issue") or "hard_failure").strip() or "hard_failure",
            "severity": "reject",
            "decision": "reject",
        }
        if field_name:
            normalized["field"] = field_name
        detail = str(payload.get("detail") or "").strip()
        if detail:
            normalized["detail"] = detail
        hard_failures.append(normalized)
    for raw in list(candidate.get("completion_issues") or []):
        payload = dict(raw or {})
        decision = str(payload.get("decision") or payload.get("severity") or "").strip().lower()
        if decision != "reject":
            continue
        field_name = str(payload.get("field") or "").strip()
        reason_code = str(payload.get("reason_code") or payload.get("issue") or field_name).strip()
        if not reason_code:
            continue
        dedupe_key = (field_name, reason_code)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized = {
            "reason_code": reason_code,
            "issue": str(payload.get("issue") or "hard_failure").strip() or "hard_failure",
            "severity": "reject",
            "decision": "reject",
        }
        if field_name:
            normalized["field"] = field_name
        hard_failures.append(normalized)
    return hard_failures


def _gate_a_revision_actions(candidate: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    for issue in list(candidate.get("completion_issues") or []):
        payload = dict(issue or {})
        field_name = str(payload.get("field") or "").strip()
        if field_name:
            action = f"provide_required_research_field:{field_name}"
            if action not in actions:
                actions.append(action)
    for field_name in list(candidate.get("semantic_contract_missing_fields") or []):
        token = str(field_name or "").strip()
        if token:
            action = f"repair_semantic_contract_field:{token}"
            if action not in actions:
                actions.append(action)
    if bool(candidate.get("execution_semantic_gap")):
        action = "repair_execution_semantic_gap"
        if action not in actions:
            actions.append(action)
    return actions


def _gate_a_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    completion_issues = [dict(item or {}) for item in list(candidate.get("completion_issues") or []) if isinstance(item, dict)]
    hard_failures = _candidate_hard_failures(candidate)
    hard_failure_codes = _compact_unique(
        [dict(item or {}).get("reason_code") for item in hard_failures]
    )
    blocking_reasons = [
        str(item.get("reason_code") or item.get("issue") or item.get("field") or "").strip()
        for item in completion_issues
        if str(item.get("reason_code") or item.get("issue") or item.get("field") or "").strip()
    ]
    if bool(candidate.get("execution_semantic_gap")) and "execution_semantic_gap" not in blocking_reasons:
        blocking_reasons.append("execution_semantic_gap")
    for field_name in list(candidate.get("semantic_contract_missing_fields") or []):
        token = str(field_name or "").strip()
        if token:
            code = f"semantic_contract_missing:{token}"
            if code not in blocking_reasons:
                blocking_reasons.append(code)
    for code in hard_failure_codes:
        if code not in blocking_reasons:
            blocking_reasons.append(code)
    evidence_gap_codes = [
        str(item.get("reason_code") or item.get("issue") or item.get("field") or "").strip()
        for item in completion_issues
        if str(item.get("decision") or item.get("severity") or "").strip().lower() != "reject"
        and str(item.get("reason_code") or item.get("issue") or item.get("field") or "").strip()
    ]
    decision = "reject" if hard_failures else "revise" if blocking_reasons else "pass"
    return {
        "contract_version": "strategy_factory.gate_artifact.v2",
        "gate_name": "gate_a",
        "stage": "gate_a",
        "decision": decision,
        "status": "blocked" if blocking_reasons else "passed",
        "hard_failures": hard_failures,
        "evidence_gap_codes": _compact_unique(evidence_gap_codes),
        "artifact_ids": _candidate_artifact_ids(candidate),
        "retrieval_context_ids": _candidate_retrieval_context_ids(candidate),
        "trace_ids": _candidate_trace_ids(candidate),
        "family_outcome_summary": _candidate_family_outcome_summary(candidate),
        "blocking_reasons": blocking_reasons,
        "warnings": ["spec_completeness_incomplete"] if str(candidate.get("spec_completeness") or "").strip() == "incomplete" else [],
        "revision_actions": _gate_a_revision_actions(candidate),
        "evidence_refs": _candidate_trace_ids(candidate),
        "legacy_gate_mapping": ["gate_0", "pre_gate", "gate_1"],
        "spec_completeness": candidate.get("spec_completeness"),
    }


def _gate_b_payload(candidate: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    blocking_reasons = [str(item).strip() for item in list(gate.get("reason_codes") or []) if str(item).strip()]
    warnings = [str(item).strip() for item in list(gate.get("warning_codes") or []) if str(item).strip()]
    review_decision = str(
        dict(gate.get("business_admission_decision") or {}).get("decision")
        or gate.get("gate_b_review_decision")
        or ("pass" if gate.get("passed") else "reject" if blocking_reasons else "pending")
    ).strip().lower() or "pending"
    decision = "block" if blocking_reasons else "pass" if gate.get("passed") else "pending"
    return {
        "contract_version": "strategy_factory.gate_artifact.v2",
        "gate_name": "gate_b",
        "stage": "gate_b",
        "decision": decision,
        "review_decision": review_decision,
        "status": "blocked" if blocking_reasons else "passed" if gate.get("passed") else "pending",
        "hard_failures": [
            {
                "reason_code": code,
                "issue": "submission_gate_blocker",
                "severity": "reject",
                "decision": "reject",
            }
            for code in blocking_reasons
        ],
        "evidence_gap_codes": warnings,
        "artifact_ids": _candidate_artifact_ids(candidate),
        "retrieval_context_ids": _candidate_retrieval_context_ids(candidate),
        "trace_ids": _candidate_trace_ids(candidate),
        "family_outcome_summary": _candidate_family_outcome_summary(candidate),
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "evidence_refs": _candidate_trace_ids(candidate),
        "legacy_gate_mapping": ["gate_2", "gate_3"],
        "business_admission_decision": dict(gate.get("business_admission_decision") or {}),
        "benchmark_comparison": dict(gate.get("benchmark_comparison") or {}),
        "cost_sensitivity_summary": dict(gate.get("cost_sensitivity_summary") or {}),
        "cash_sleeve_audit": dict(gate.get("cash_sleeve_audit") or {}),
        "family_holding_bucket": dict(gate.get("family_holding_bucket") or {}),
    }


def _gate_c_payload(candidate: dict[str, Any], gate: dict[str, Any], final_status: str) -> dict[str, Any]:
    blockers = [str(item).strip() for item in list(candidate.get("gate_blockers") or []) if str(item).strip()]
    execution_audit_status = str(
        candidate.get("execution_audit_gate_status")
        or gate.get("execution_audit_gate_status")
        or ""
    ).strip()
    evidence_gap_codes = list(candidate.get("evidence_gap_codes") or [])
    if execution_audit_status in {
        "missing",
        "bootstrap_pending",
        "insufficient_samples",
        "bootstrap_ready",
        "insufficient_evidence",
    }:
        evidence_gap_codes.append(f"execution_audit_gate:{execution_audit_status}")
    decision = "block" if blockers else "observe" if final_status else "pending"
    return {
        "contract_version": "strategy_factory.gate_artifact.v2",
        "gate_name": "gate_c",
        "stage": "gate_c",
        "decision": decision,
        "status": "blocked" if blockers else "observe" if final_status else "pending",
        "hard_failures": [
            {
                "reason_code": code,
                "issue": "promotion_gate_blocker",
                "severity": "reject",
                "decision": "reject",
            }
            for code in blockers
        ],
        "evidence_gap_codes": _compact_unique(evidence_gap_codes),
        "artifact_ids": _compact_unique(
            [
                candidate.get("paper_account_id"),
                candidate.get("incubation_account_id"),
                candidate.get("promotion_review_id"),
                candidate.get("vector_profile_id"),
            ]
        ),
        "retrieval_context_ids": _candidate_retrieval_context_ids(candidate),
        "trace_ids": _candidate_trace_ids(candidate),
        "family_outcome_summary": _candidate_family_outcome_summary(
            candidate,
            final_status=final_status,
        ),
        "blocking_reasons": blockers,
        "warnings": [],
        "evidence_refs": _candidate_trace_ids(candidate),
        "legacy_gate_mapping": [
            "signal_quality",
            "execution_quality",
            "execution_audit_gate_status",
            "hard_gate_result",
            "promotion_ready",
        ],
        "signal_quality": candidate.get("signal_quality"),
        "execution_quality": candidate.get("execution_quality"),
        "execution_audit_gate_status": execution_audit_status or None,
        "hard_gate_result": candidate.get("hard_gate_result") or gate.get("hard_gate_result"),
        "promotion_ready": bool(candidate.get("promotion_ready")),
    }


def _enrich_quality_report_v2(
    quality_report: dict[str, Any],
    *,
    candidate: dict[str, Any],
    gate: dict[str, Any],
    final_status: str,
) -> dict[str, Any]:
    report = dict(quality_report or {})
    summary = dict(report.get("summary") or {})
    prediction_trace_id = normalize_prediction_trace_id(
        candidate.get("prediction_trace_id"),
        candidate.get("trace_id"),
        fallback=summary.get("trace_id"),
    )
    gate_a = _gate_a_payload(candidate)
    gate_b = _gate_b_payload(candidate, gate)
    gate_c = _gate_c_payload(candidate, gate, final_status)
    for key, value in (
        ("prediction_trace_id", prediction_trace_id),
        ("trace_id", prediction_trace_id),
        ("research_protocol_version", candidate.get("research_protocol_version")),
        ("candidate_contract_version", candidate.get("candidate_contract_version")),
        ("spec_completeness", candidate.get("spec_completeness")),
        ("field_provenance_summary", dict(candidate.get("field_provenance_summary") or {})),
        ("completion_issues", list(candidate.get("completion_issues") or [])),
        ("hard_failures", list(candidate.get("hard_failures") or [])),
        ("gate_a", gate_a),
        ("gate_b", gate_b),
        ("gate_c", gate_c),
    ):
        if value in (None, "", [], {}):
            continue
        summary[key] = value
        report[key] = value
    report["summary"] = summary
    return report

def _compat_setting(name: str, default):
    return default


def _normalized_spec_completeness_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode not in {"warn", "revise", "reject"}:
        return "warn"
    return mode


def _spec_completeness_mode() -> str:
    return _normalized_spec_completeness_mode(
        _compat_setting("STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE", STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE)
    )


def _build_gate_a_spec_override(candidate: dict[str, Any]) -> Optional[dict[str, Any]]:
    if str(candidate.get("spec_completeness") or "complete").strip().lower() != "incomplete":
        return None
    mode = _spec_completeness_mode()
    hard_failure_codes = _compact_unique(
        [dict(item or {}).get("reason_code") for item in _candidate_hard_failures(candidate)]
    )
    if mode == "warn" and not hard_failure_codes:
        return None
    gate_a = _gate_a_payload(candidate)
    blocking_reasons = [str(item).strip() for item in list(gate_a.get("blocking_reasons") or []) if str(item).strip()]
    revision_actions = [str(item).strip() for item in list(gate_a.get("revision_actions") or []) if str(item).strip()]
    decision = "reject" if (mode == "reject" or hard_failure_codes) else "revise"
    trigger = (
        "research_protocol_hard_failure"
        if hard_failure_codes
        else "research_protocol_required_fields_rejected"
        if decision == "reject"
        else "research_protocol_required_fields_need_revision"
    )
    reasons = list(dict.fromkeys([trigger, *hard_failure_codes, *blocking_reasons]))
    warning_codes = ["spec_completeness_incomplete"]
    return normalize_quality_gate_result(
        {
            "passed": False,
            "passed_strict": False,
            "provisional_pass": False,
            "reasons": reasons,
            "reason_codes": reasons,
            "warning_codes": warning_codes,
            "warnings": warning_codes,
            "admission_stage": "gate_a",
            "incubation_pass_mode": decision,
            "research_candidate_ready": decision == "revise",
            "incubation_candidate_ready": False,
            "live_candidate_ready": False,
            "strict_incubation_ready": False,
            "strict_incubation_blocked": True,
            "admission_block_reasons": reasons,
            "gate_protocol": f"strategy_factory.research_protocol.v2:gate_a_{decision}",
            "gate_a_decision": decision,
            "spec_completeness_mode": mode,
            "spec_completeness": "incomplete",
            "completion_issues": list(candidate.get("completion_issues") or []),
            "hard_failures": list(candidate.get("hard_failures") or []),
            "revision_actions": revision_actions,
        }
    )


def _auto_name(*args, **kwargs):
    return _local_auto_name(*args, **kwargs)


def _extract_event_context(*args, **kwargs):
    return _local_extract_event_context(*args, **kwargs)


def get_strategy_factory_package():
    return _local_get_strategy_factory_package()


async def _update_strategy_status(*args, **kwargs):
    return await _local_update_strategy_status(*args, **kwargs)


_SEMANTIC_CONTRACT_FIELDS = (
    "market_evidence_pack",
    "alpha_thesis",
    "template_dominance_score",
    "non_proxy_evidence_ratio",
    "direction_resolution",
    "confidence_calibration",
    "evidence_chain",
    "prediction_contract",
    "confidence_contract",
    "evidence_alignment_audit",
    "dsl_support_audit",
    "legacy_semantic_contract",
    "contradiction_count",
    "proxy_dependency_score",
)

_RUNTIME_BOOTSTRAP_REQUIRED_FIELDS = (
    "holding_horizon",
    "trade_plan",
    "risk_rules",
    "execution_assumptions",
)
_EMPTY_CONTRACT_VALUES = (None, "", [], {})


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, "", [], {}):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value in (None, "", [], {}):
            return default
        return int(float(value))
    except Exception:
        return default


def _diagnostic_reason_codes(gate: Optional[dict[str, Any]]) -> list[str]:
    payload = dict(gate or {})
    values: list[Any] = []
    for key in (
        "reason_codes",
        "reasons",
        "admission_block_reasons",
        "warning_codes",
        "warnings",
    ):
        raw = payload.get(key)
        if isinstance(raw, (list, tuple, set)):
            values.extend(raw)
        elif raw not in (None, "", [], {}):
            values.append(raw)
    return _compact_unique([str(item or "").strip().lower() for item in values], limit=32)


def _diagnostic_metric(
    candidate: dict[str, Any],
    metrics: Optional[dict[str, Any]],
    gate: Optional[dict[str, Any]],
    *keys: str,
) -> Any:
    sources = [
        dict(metrics or {}),
        dict(candidate.get("backtest_metrics") or {}),
        dict((candidate.get("backtest_result") or {}).get("metrics") or {}),
        dict(gate or {}),
    ]
    for source in sources:
        for key in keys:
            if source.get(key) not in (None, "", [], {}):
                return source.get(key)
    return None


def _parse_win_rate_from_reason(reason: str) -> Optional[float]:
    token = str(reason or "").strip().lower()
    if not token.startswith("win_rate_"):
        return None
    nums = re.findall(r"\d+", token)
    if len(nums) < 2:
        return None
    try:
        return float(f"{int(nums[0])}.{nums[1]}")
    except Exception:
        return None


def _diagnostic_observation_target_symbols(candidate: dict[str, Any]) -> list[str]:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    return _normalize_target_codes(
        [
            payload.get("target_symbols"),
            payload.get("stock_pool"),
            params.get("target_symbols"),
            params.get("stock_pool"),
            (params.get("dsl") or {}).get("metadata") if isinstance(params.get("dsl"), dict) else None,
        ],
        limit=16,
    )


_DIAGNOSTIC_FINGERPRINT_VOLATILE_KEYS = {
    "id",
    "strategy_id",
    "trace_id",
    "prediction_trace_id",
    "correlation_id",
    "task_run_id",
    "factory_run_id",
    "experiment_id",
    "source_run_id",
    "created_at",
    "updated_at",
    "generated_at",
    "timestamp",
    "source_candidate_artifact_id",
    "source_generation_artifact_id",
    "source_validation_artifact_id",
    "candidate_memory_record_id",
    "multiple_testing_registry_record_id",
}


def _diagnostic_observation_stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        stable: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key or "").strip()
            if not key or key in _DIAGNOSTIC_FINGERPRINT_VOLATILE_KEYS:
                continue
            cleaned = _diagnostic_observation_stable_value(raw_value)
            if cleaned in (None, "", [], {}):
                continue
            stable[key] = cleaned
        return stable
    if isinstance(value, (list, tuple)):
        cleaned_items = [
            _diagnostic_observation_stable_value(item)
            for item in list(value)
        ]
        return [item for item in cleaned_items if item not in (None, "", [], {})]
    return value


def _diagnostic_observation_core_params(candidate: dict[str, Any]) -> dict[str, Any]:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    core_keys = (
        "fast_window",
        "slow_window",
        "short_window",
        "long_window",
        "lookback",
        "lookback_days",
        "period",
        "period_days",
        "rebalance_days",
        "holding_days",
        "holding_period",
        "threshold",
        "entry_threshold",
        "exit_threshold",
        "factor_name",
        "factor_names",
        "factor_weights",
        "signal_rule",
        "dsl",
    )
    compact: dict[str, Any] = {}
    for key in core_keys:
        value = params.get(key, payload.get(key))
        if value in (None, "", [], {}):
            continue
        stable_value = _diagnostic_observation_stable_value(value)
        if stable_value not in (None, "", [], {}):
            compact[key] = stable_value
    for key in ("logic_signature", "dsl_signature", "factor_signature", "entry_exit_signature"):
        value = payload.get(key) or params.get(key)
        if value not in (None, "", [], {}):
            compact[key] = value
    return compact


def _diagnostic_observation_fingerprint(candidate: dict[str, Any], reason: str) -> str:
    payload = dict(candidate or {})
    params = dict(payload.get("params") or {})
    provenance = dict(payload.get("candidate_provenance") or params.get("candidate_provenance") or {})
    fingerprint_payload = {
        "strategy_type": str(payload.get("strategy_type") or "").strip().lower(),
        "candidate_family": str(
            provenance.get("candidate_family")
            or payload.get("candidate_family")
            or params.get("candidate_family")
            or ""
        ).strip().lower(),
        "target_symbols": _diagnostic_observation_target_symbols(payload),
        "core_params": _diagnostic_observation_core_params(payload),
        "reason": str(reason or "diagnostic_observation").strip().lower(),
    }
    raw = json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"diag_{digest}"


def _has_gate_2_full_backtest_evidence(candidate: dict[str, Any]) -> bool:
    payload = dict(candidate or {})
    for key in (
        "gate_2_passed",
        "gate2_passed",
        "full_backtest_passed",
        "passed_full_backtest",
        "backtest_passed",
    ):
        if payload.get(key) is True:
            return True

    for key in ("backtest_outcome", "backtest_result", "raw_backtest_result"):
        outcome = dict(payload.get(key) or {})
        if outcome.get("passed") is True:
            return True
        if str(outcome.get("reason_code") or "").strip().lower() == "passed":
            return True

    metrics = dict(payload.get("backtest_metrics") or {})
    contract = dict(
        payload.get("backtest_metrics_contract")
        or metrics.get("backtest_metrics_contract")
        or {}
    )
    for source in (metrics, contract):
        for key in (
            "gate_2_passed",
            "gate2_passed",
            "full_backtest_passed",
            "passed_full_backtest",
            "backtest_passed",
        ):
            if source.get(key) is True:
                return True
    return False


def _is_diagnostic_observation_candidate(
    gate: Optional[dict[str, Any]],
    candidate: Optional[dict[str, Any]],
    metrics: Optional[dict[str, Any]],
    *,
    refresh_existing: bool,
    read_only: bool,
) -> tuple[bool, Optional[str]]:
    gate_payload = dict(gate or {})
    candidate_payload = dict(candidate or {})
    if bool(gate_payload.get("passed")):
        return False, None
    if refresh_existing or read_only:
        return False, None
    dedup_result = dict(candidate_payload.get("dedup_result") or {})
    if not dedup_result:
        return False, None
    if bool(dedup_result.get("duplicate")) or bool(dedup_result.get("refresh_existing")):
        return False, None
    if not _has_gate_2_full_backtest_evidence(candidate_payload):
        return False, None
    gate_a_decision = str(
        gate_payload.get("gate_a_decision") or candidate_payload.get("gate_a_decision") or ""
    ).strip().lower()
    if gate_a_decision in {"reject", "revise"}:
        return False, None

    reason_codes = _diagnostic_reason_codes(gate_payload)
    hard_tokens = {
        "not_executable",
        "non_executable",
        "runtime_contract_missing",
        "missing_runtime_contract",
        "missing_runtime",
        "semantic_hard_fail",
        "data_missing",
        "missing_data",
        "insufficient_data",
        "max_drawdown_hard",
        "max_drawdown_exceeded",
        "multiple_testing_high_risk",
        "overfitting_high_risk",
        "overfit_high_risk",
        "precompile_reject",
        "generator_hard_reject",
    }
    if any(any(token in reason for token in hard_tokens) for reason in reason_codes):
        return False, None

    for raw in list(candidate_payload.get("hard_failures") or []):
        payload = dict(raw or {})
        decision = str(payload.get("decision") or payload.get("severity") or "").strip().lower()
        if decision in {"reject", "hard_fail", "error"}:
            return False, None
    for raw in list(candidate_payload.get("completion_issues") or []):
        payload = dict(raw or {})
        decision = str(payload.get("decision") or payload.get("severity") or "").strip().lower()
        if decision == "reject":
            return False, None

    trade_count = _safe_int(
        _diagnostic_metric(candidate_payload, metrics, gate_payload, "trade_count", "trades_count", "total_trades"),
        default=0,
    ) or 0
    min_trade_count = _diagnostic_observation_min_trade_count()
    if trade_count < min_trade_count:
        return False, None
    max_drawdown = abs(
        _safe_float(
            _diagnostic_metric(candidate_payload, metrics, gate_payload, "max_drawdown", "drawdown"),
            default=0.0,
        )
        or 0.0
    )
    if max_drawdown > 0.35:
        return False, None

    win_rate = _safe_float(
        _diagnostic_metric(candidate_payload, metrics, gate_payload, "win_rate", "avg_win_rate"),
        default=None,
    )
    parsed_win_rates = [_parse_win_rate_from_reason(reason) for reason in reason_codes]
    parsed_win_rates = [value for value in parsed_win_rates if value is not None]
    if win_rate is None and parsed_win_rates:
        win_rate = parsed_win_rates[0]
    min_win_rate = _diagnostic_observation_min_win_rate()
    if win_rate is not None and min_win_rate <= float(win_rate) < 0.40:
        return True, next((r for r in reason_codes if r.startswith("win_rate_")), "win_rate_near_threshold")

    allowed_fragments = (
        "weak_wf_ic_ir",
        "weak_pkf_ic",
        "weak_bootstrap_ci_lower",
    )
    for reason in reason_codes:
        if any(fragment in reason for fragment in allowed_fragments):
            return True, reason
        if reason.startswith("period_robustness_"):
            return True, reason
        if (reason.startswith("trade_count_") or "trade_count" in reason) and trade_count >= min_trade_count:
            return True, reason
    return False, None


def _diagnostic_observation_submission_action(
    base_action: Optional[dict[str, Any]],
    *,
    reason: str,
) -> dict[str, Any]:
    ttl_days = _diagnostic_observation_ttl_days()
    final_status = _diagnostic_observation_final_status()
    trigger_reason = "observe_first_intake" if _observe_first_enabled() else "diagnostic_observation_gate3_failed"
    action = dict(base_action or {})
    nested = dict(action.get("submission_action") or {})
    nested.update(
        {
            "type": "diagnostic",
            "trigger_reason": trigger_reason,
            "next_step": "diagnostic_observation",
            "submission_lane": "diagnostic_observation",
            "final_status": final_status,
            "completed": False,
            "diagnostic_observation": True,
            "diagnostic_reason": reason,
            "diagnostic_ttl_days": ttl_days,
            "admission_layer": "diagnostic",
        }
    )
    action.update(
        {
            "submission_action": nested,
            "submission_action_type": "diagnostic",
            "submission_action_trigger": trigger_reason,
            "submission_action_next_step": "diagnostic_observation",
            "submission_action_completed": False,
            "submission_lane": "diagnostic_observation",
            "final_status": final_status,
            "admission_decision": "diagnostic",
            "admission_layer": "diagnostic",
            "diagnostic_observation": True,
            "diagnostic_reason": reason,
            "diagnostic_reason_code": reason,
            "diagnostic_ttl_days": ttl_days,
        }
    )
    return action


def _semantic_contract_feature_enabled() -> bool:
    return bool(STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED)


def _assign_optional_payload(target: dict[str, Any], key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        target[key] = value


def _apply_candidate_semantic_contract(candidate: dict[str, Any], semantic_audit: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(candidate or {})
    semantic_fields = normalize_semantic_contract_fields(payload)
    if semantic_audit is not None:
        semantic_fields["evidence_alignment_audit"] = dict(semantic_audit or {})
        semantic_fields["legacy_semantic_contract"] = bool(semantic_audit.get("legacy_semantic_contract"))
        semantic_fields["contradiction_count"] = int(semantic_audit.get("contradiction_count") or 0)
        semantic_fields["proxy_dependency_score"] = semantic_audit.get("proxy_dependency_score")
    params = dict(payload.get("params") or {})
    for field_name in _SEMANTIC_CONTRACT_FIELDS:
        _assign_optional_payload(params, field_name, semantic_fields.get(field_name))
    payload["params"] = params
    for field_name in _SEMANTIC_CONTRACT_FIELDS:
        _assign_optional_payload(payload, field_name, semantic_fields.get(field_name))
    return payload


def _apply_semantic_contract_gate(gate: Optional[dict], semantic_audit: Optional[dict[str, Any]]) -> dict[str, Any]:
    normalized_gate = normalize_quality_gate_result(gate)
    audit = dict(semantic_audit or {})
    if not audit:
        return normalized_gate
    for field_name in (
        "evidence_alignment_audit",
        "legacy_semantic_contract",
        "contradiction_count",
        "proxy_dependency_score",
    ):
        value = (
            audit
            if field_name == "evidence_alignment_audit"
            else audit.get(field_name)
        )
        _assign_optional_payload(normalized_gate, field_name, value)
    hard_fail_reasons = [
        str(reason or "").strip()
        for reason in list(audit.get("hard_fail_reasons") or [])
        if str(reason or "").strip()
    ]
    if hard_fail_reasons and bool(audit.get("using_new_contract")):
        existing_reasons = [
            str(reason or "").strip()
            for reason in list(normalized_gate.get("reasons") or [])
            if str(reason or "").strip()
        ]
        normalized_gate["passed"] = False
        normalized_gate["reasons"] = list(dict.fromkeys([*existing_reasons, *hard_fail_reasons]))
    return normalize_quality_gate_result(normalized_gate)


class _CompatValidationGateway:
    """Resolve validation runner through the legacy patch-point at call time."""

    async def run_validation_report(self, strategy_type: str, params: dict[str, Any], db) -> Optional[dict]:
        from ...api.quality_reporting import run_validation_report

        return await run_validation_report(strategy_type, dict(params or {}), db)


class _CompatRiskGateway:
    """Resolve risk runner through the legacy patch-point at call time."""

    async def run_risk_report(self, strategy_type: str, params: dict[str, Any], db) -> Optional[dict]:
        from ...api.quality_reporting import run_risk_report

        return await run_risk_report(strategy_type, dict(params or {}), db)

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'runner_parts',
    'class _StrategySubmitterActionsMixin:\n',
    ['gate_payloads.py', 'semantic_contract.py', 'submission_flow.py', 'persistence.py', 'post_gate.py', 'orchestrator.py'],
    future_annotations=True,
)
