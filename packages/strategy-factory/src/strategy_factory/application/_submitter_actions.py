"""策略工厂候选提交。"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
import time as _time
from collections import Counter
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import uuid4

from .candidate_contract import (
    apply_resolved_candidate_envelope,
    build_candidate_contract_hash,
    build_candidate_identity_signature,
    build_execution_contract_hash,
    build_portfolio_candidate_contract,
    build_resolved_candidate_envelope,
    build_tested_object_hash,
    candidate_contract_value,
)
from .legacy_bridge import call_compat_async, get_compat_symbol, get_compat_value
from .incubation_budgeter import IncubationBudgeter
from .quality_gates import _VALID_STRATEGY_TYPES, build_completed_gate_3_report
from .quality_reporting import build_quality_report, normalize_quality_gate_result
from .semantic_contract import (
    audit_candidate_semantic_contract,
    build_candidate_evidence_records,
    normalize_semantic_contract_fields,
    synthesize_confidence_contract,
)
from .submission_gate import run_submission_quality_gate as _local_run_submission_quality_gate
from .utils import (
    _auto_name as _local_auto_name,
    _extract_event_context as _local_extract_event_context,
    _update_strategy_status as _local_update_strategy_status,
    get_strategy_factory_package as _local_get_strategy_factory_package,
)
from .research_protocol_contract import (
    adapt_research_validation_contract_for_submission,
    normalize_prediction_trace_id,
)
from ..domain.constants import (
    FACTORY_SUBMISSION_MIN_BACKTEST_TRADES,
    FACTORY_SUBMISSION_MIN_EVENT_TARGET_COVERAGE,
    FACTORY_SUBMISSION_REJECT_GENERIC_AI_NAMES,
    FACTORY_SUBMISSION_REQUIRE_STRICT_PASS_FOR_REFRESH,
    FACTORY_SUBMISSION_REQUIRE_TASK_PREFERENCE_MATCH,
    STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE,
    STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED,
    SUBMIT_CONCURRENCY,
)
from ..domain.targets import _build_task_signature, _normalize_research_task_contract, _normalize_target_codes
from ..infrastructure.mcp_services import (
    build_strategy_vector_profile,
    get_strategy_promotion_pipeline_service,
    get_strategy_runtime_control_service,
)

if TYPE_CHECKING:
    from ..api.contracts import IncubationGateway, RiskGateway, ValidationGateway

logger = logging.getLogger(__name__)

_LEGACY_SUBMITTER_MODULE = "akshare_mcp.services.strategy_factory.submitter"
_LEGACY_SUBMISSION_GATE_MODULE = "akshare_mcp.services.strategy_factory.submission_gate"
_LEGACY_UTILS_MODULE = "akshare_mcp.services.strategy_factory.utils"


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
    if execution_audit_status in {"missing", "bootstrap_pending", "insufficient_samples", "insufficient_evidence"}:
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
    return get_compat_value(_LEGACY_SUBMITTER_MODULE, name, default)


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
    return get_compat_symbol(_LEGACY_UTILS_MODULE, "_auto_name", _local_auto_name)(*args, **kwargs)


def _extract_event_context(*args, **kwargs):
    return get_compat_symbol(
        _LEGACY_UTILS_MODULE,
        "_extract_event_context",
        _local_extract_event_context,
    )(*args, **kwargs)


def get_strategy_factory_package():
    return get_compat_symbol(
        _LEGACY_UTILS_MODULE,
        "get_strategy_factory_package",
        _local_get_strategy_factory_package,
    )()


async def _update_strategy_status(*args, **kwargs):
    return await call_compat_async(
        _LEGACY_UTILS_MODULE,
        "_update_strategy_status",
        _local_update_strategy_status,
        *args,
        **kwargs,
    )


_SEMANTIC_CONTRACT_FIELDS = (
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
        factory_pkg = get_strategy_factory_package()
        return await factory_pkg._run_validation_report(strategy_type, dict(params or {}), db)


class _CompatRiskGateway:
    """Resolve risk runner through the legacy patch-point at call time."""

    async def run_risk_report(self, strategy_type: str, params: dict[str, Any], db) -> Optional[dict]:
        factory_pkg = get_strategy_factory_package()
        return await factory_pkg._run_risk_report(strategy_type, dict(params or {}), db)


class _StrategySubmitterActionsMixin:
        async def submit(self, candidates: List[dict], snapshot: dict, db) -> dict:
            """批量提交候选策略，每个策略独立处理，单个失败不影响其他。"""
            created = 0
            created_total = 0
            created_strategy_pool = 0
            created_audit_only = 0
            refreshed = 0
            submitted = 0
            gate_3_input = 0
            passed = 0
            gate_3_passed = 0
            gate_3_failed = 0
            gate_3_provisional_passed = 0
            gate_3_failure_codes: Counter[str] = Counter()
            submission_lane_counts: Counter[str] = Counter()
            submission_action_type_counts: Counter[str] = Counter()
            strict_incubation_ready_count = 0
            submitted_items: List[dict] = []
            incubation_budget_plan = IncubationBudgeter.plan(candidates, snapshot)
            incubation_budget_summary = dict(incubation_budget_plan.get("summary") or {})
            for candidate in candidates:
                marker = int(id(candidate))
                candidate["incubation_budget"] = dict(
                    (incubation_budget_plan.get("plans") or {}).get(marker) or {}
                )
            submit_concurrency = int(_compat_setting("SUBMIT_CONCURRENCY", SUBMIT_CONCURRENCY) or SUBMIT_CONCURRENCY)
            sem = asyncio.Semaphore(submit_concurrency)

            async def _submit_guarded(candidate: dict) -> Optional[dict]:
                async with sem:
                    try:
                        return await self._submit_one(candidate, snapshot, db)
                    except Exception as exc:
                        logger.warning("StrategySubmitter: failed for %s: %s", candidate.get("strategy_type"), exc)
                        return None

            results = await asyncio.gather(
                *[_submit_guarded(c) for c in candidates],
                return_exceptions=True,
            )
            for result in results:
                if result is None or isinstance(result, BaseException):
                    continue
                gate_3_input += 1
                if result.get("created_total", result.get("created", False)):
                    created_total += 1
                if result.get("created_strategy_pool", result.get("created", False)):
                    created += 1
                    created_strategy_pool += 1
                if result.get("created_audit_only"):
                    created_audit_only += 1
                if result.get("refreshed_existing"):
                    refreshed += 1
                if result.get("submitted"):
                    submitted += 1
                if result.get("passed"):
                    passed += 1
                gate_3 = dict(result.get("gate_3") or {})
                gate_a_decision = str(gate_3.get("gate_a_decision") or "").strip().lower()
                gate_a_short_circuit = gate_a_decision in {"revise", "reject"} and str(
                    gate_3.get("admission_stage") or ""
                ).strip().lower() == "gate_a"
                if gate_3.get("passed"):
                    gate_3_passed += 1
                    if gate_3.get("provisional_pass"):
                        gate_3_provisional_passed += 1
                elif not gate_a_short_circuit:
                    gate_3_failed += 1
                    for code in gate_3.get("reason_codes") or []:
                        normalized = str(code or "").strip()
                        if normalized:
                            gate_3_failure_codes[normalized] += 1
                summary = dict(result["summary"] or {})
                submission_lane = str(summary.get("submission_lane") or "").strip().lower()
                if submission_lane:
                    submission_lane_counts[submission_lane] += 1
                action_type = str(summary.get("submission_action_type") or "").strip().lower()
                if action_type:
                    submission_action_type_counts[action_type] += 1
                if bool(summary.get("strict_incubation_ready")):
                    strict_incubation_ready_count += 1
                submitted_items.append(summary)

            gate_report = build_completed_gate_3_report(
                {
                    "gate_3_input": gate_3_input,
                    "submitted": submitted,
                    "gate_3_passed": gate_3_passed,
                    "gate_3_failed": gate_3_failed,
                    "gate_3_provisional_passed": gate_3_provisional_passed,
                    "gate_3_failure_reason_topn": [
                        {"reason_code": reason_code, "count": count}
                        for reason_code, count in gate_3_failure_codes.most_common(5)
                    ],
                    "formal_incubation_count": int(submission_lane_counts.get("formal_incubation") or 0),
                    "observe_incubation_count": int(submission_lane_counts.get("observe_incubation") or 0),
                    "live_ready_review_count": int(submission_lane_counts.get("live_ready_review") or 0),
                    "deferred_submission_count": int(submission_lane_counts.get("deferred_submission") or 0),
                    "research_only_count": int(submission_action_type_counts.get("research_only") or 0),
                    "strict_incubation_ready_count": strict_incubation_ready_count,
                }
            )

            return {
                "created": created,
                "created_total": created_total,
                "created_strategy_pool": created_strategy_pool,
                "created_audit_only": created_audit_only,
                "refreshed": refreshed,
                "gate_3_input": gate_3_input,
                "submitted": submitted,
                "passed_quality_gate": passed,
                "gate_3_passed": gate_3_passed,
                "gate_3_failed": gate_3_failed,
                "gate_3_provisional_passed": gate_3_provisional_passed,
                "gate_3_failure_reason_topn": gate_report["gate_3"]["failure_reason_topn"],
                "formal_incubation_count": int(submission_lane_counts.get("formal_incubation") or 0),
                "observe_incubation_count": int(submission_lane_counts.get("observe_incubation") or 0),
                "live_ready_review_count": int(submission_lane_counts.get("live_ready_review") or 0),
                "deferred_submission_count": int(submission_lane_counts.get("deferred_submission") or 0),
                "research_only_count": int(submission_action_type_counts.get("research_only") or 0),
                "strict_incubation_ready_count": strict_incubation_ready_count,
                "quality_gate": gate_report,
                "gate_report": gate_report,
                "incubation_budget_summary": incubation_budget_summary,
                "strategies": submitted_items,
            }

        async def _submit_one(self, candidate: dict, snapshot: dict, db) -> dict:
            """处理单个候选策略的完整提交流程。"""
            candidate = apply_resolved_candidate_envelope(candidate)
            candidate = self._ensure_runtime_playbook(candidate)
            run_submission_quality_gate = get_compat_symbol(
                _LEGACY_SUBMISSION_GATE_MODULE,
                "run_submission_quality_gate",
                _local_run_submission_quality_gate,
            )

            existing_strategy = await self._resolve_existing_strategy(candidate, db)
            refresh_existing = existing_strategy is not None
            existing_status = str((existing_strategy or {}).get("status") or "draft")
            strategy_id = str((existing_strategy or {}).get("id") or f"factory_{int(_time.time())}_{uuid4().hex[:8]}")
            name = self._candidate_name(candidate, existing_strategy)
            metrics = candidate.get("backtest_metrics", {})
            semantic_audit: dict[str, Any] = {}
            if _semantic_contract_feature_enabled():
                candidate["confidence_contract"] = synthesize_confidence_contract(candidate)
                semantic_audit = audit_candidate_semantic_contract(candidate)
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            gate_a_override = _build_gate_a_spec_override(candidate)
            data = self._build_strategy_data(strategy_id, name, candidate, metrics, existing=existing_strategy)
            candidate = apply_resolved_candidate_envelope(
                {
                    **dict(candidate or {}),
                    "id": strategy_id,
                    "name": name,
                    "params": dict(data.get("params") or {}),
                    "target_symbols": list((data.get("params") or {}).get("target_symbols") or candidate.get("target_symbols") or []),
                    "stock_pool": dict((data.get("params") or {}).get("stock_pool") or candidate.get("stock_pool") or {}),
                    "research_task": dict((data.get("params") or {}).get("research_task") or candidate.get("research_task") or {}),
                    "validation_profile": dict(
                        (data.get("params") or {}).get("validation_profile")
                        or candidate.get("validation_profile")
                        or {}
                    ),
                    "targeting_policy": dict(
                        (data.get("params") or {}).get("targeting_policy")
                        or candidate.get("targeting_policy")
                        or {}
                    ),
                    "constraint_check": dict(
                        (data.get("params") or {}).get("constraint_check")
                        or candidate.get("constraint_check")
                        or {}
                    ),
                    "candidate_contract_snapshot": dict((data.get("params") or {}).get("candidate_contract_snapshot") or {}),
                    "candidate_contract_hash": str((data.get("params") or {}).get("candidate_contract_hash") or ""),
                    "execution_contract_hash": str((data.get("params") or {}).get("execution_contract_hash") or ""),
                    "tested_object_hash": str((data.get("params") or {}).get("tested_object_hash") or ""),
                    "candidate_identity_signature": str((data.get("params") or {}).get("candidate_identity_signature") or ""),
                    "candidate_lineage_contract": dict((data.get("params") or {}).get("candidate_lineage_contract") or {}),
                    "logic_signature": str((data.get("params") or {}).get("logic_signature") or ""),
                    "dsl_signature": str((data.get("params") or {}).get("dsl_signature") or ""),
                    "factor_signature": str((data.get("params") or {}).get("factor_signature") or ""),
                    "entry_exit_signature": str((data.get("params") or {}).get("entry_exit_signature") or ""),
                    "prediction_trace_id": str(
                        (data.get("params") or {}).get("prediction_trace_id")
                        or candidate.get("prediction_trace_id")
                        or ""
                    ),
                    "trace_id": str(
                        (data.get("params") or {}).get("trace_id")
                        or candidate.get("trace_id")
                        or ""
                    ),
                    "research_validation_contract": dict(
                        (data.get("params") or {}).get("research_validation_contract")
                        or candidate.get("research_validation_contract")
                        or {}
                    ),
                    "research_validation_contract_submission_adapter": dict(
                        (data.get("params") or {}).get("research_validation_contract_submission_adapter")
                        or candidate.get("research_validation_contract_submission_adapter")
                        or {}
                    ),
                    "research_protocol_version": str(
                        (data.get("params") or {}).get("research_protocol_version")
                        or candidate.get("research_protocol_version")
                        or ""
                    ),
                    "candidate_contract_version": str(
                        (data.get("params") or {}).get("candidate_contract_version")
                        or candidate.get("candidate_contract_version")
                        or ""
                    ),
                    "spec_completeness": str(
                        (data.get("params") or {}).get("spec_completeness")
                        or candidate.get("spec_completeness")
                        or ""
                    ),
                    "field_provenance": dict(
                        (data.get("params") or {}).get("field_provenance")
                        or candidate.get("field_provenance")
                        or {}
                    ),
                    "field_provenance_summary": dict(
                        (data.get("params") or {}).get("field_provenance_summary")
                        or candidate.get("field_provenance_summary")
                        or {}
                    ),
                    "completion_issues": list(
                        (data.get("params") or {}).get("completion_issues")
                        or candidate.get("completion_issues")
                        or []
                    ),
                    "hard_failures": list(
                        (data.get("params") or {}).get("hard_failures")
                        or candidate.get("hard_failures")
                        or []
                    ),
                }
            )
            if _semantic_contract_feature_enabled():
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            validation_report = None
            risk_report = None
            if gate_a_override is None:
                validation_report, risk_report = await self._evaluate_reports(candidate, db)
                gate = await run_submission_quality_gate(
                    db,
                    {**data, "status": existing_status if refresh_existing else "submitted"},
                    validation_report=validation_report,
                    risk_report=risk_report,
                    backtest_metrics={
                        **dict(metrics or {}),
                        "trade_count": metrics.get("trade_count"),
                        "trades_count": metrics.get("trades_count"),
                    },
                    incubation_budget_track=str(candidate.get("incubation_budget", {}).get("track") or "formal_incubation"),
                )
            else:
                gate = dict(gate_a_override)
            gate = self._apply_factory_submission_policy(
                candidate,
                name=name,
                gate=gate,
                backtest_metrics=metrics,
                refresh_existing=refresh_existing,
            )
            if _semantic_contract_feature_enabled():
                gate = _apply_semantic_contract_gate(gate, semantic_audit)
            candidate_provenance = self._candidate_provenance(candidate, existing_strategy)
            strategy_profile = dict(candidate_provenance.get("strategy_profile") or {})
            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(incubation_budget.get("track") or "formal_incubation").strip().lower()

            submission_action = self._resolve_submission_action_plan(
                gate,
                candidate=candidate,
                refresh_existing=refresh_existing,
                existing_status=existing_status,
                incubation_budget_track=incubation_budget_track,
            )
            submission_lane = str(submission_action.get("submission_lane") or "deferred_submission")
            final_status = str(submission_action.get("final_status") or "submitted")
            candidate = self._apply_runtime_bootstrap_contract(
                candidate,
                submission_lane=submission_lane,
                runtime_bootstrap_eligible=bool(submission_action.get("runtime_bootstrap_eligible")),
                runtime_bootstrap_budget_tier=str(submission_action.get("runtime_bootstrap_budget_tier") or "") or None,
            )
            data = self._build_strategy_data(strategy_id, name, candidate, metrics, existing=existing_strategy)
            candidate = apply_resolved_candidate_envelope(
                {
                    **dict(candidate or {}),
                    "id": strategy_id,
                    "name": name,
                    "params": dict(data.get("params") or {}),
                    "target_symbols": list((data.get("params") or {}).get("target_symbols") or candidate.get("target_symbols") or []),
                    "stock_pool": dict((data.get("params") or {}).get("stock_pool") or candidate.get("stock_pool") or {}),
                    "research_task": dict((data.get("params") or {}).get("research_task") or candidate.get("research_task") or {}),
                    "validation_profile": dict(
                        (data.get("params") or {}).get("validation_profile")
                        or candidate.get("validation_profile")
                        or {}
                    ),
                    "targeting_policy": dict(
                        (data.get("params") or {}).get("targeting_policy")
                        or candidate.get("targeting_policy")
                        or {}
                    ),
                    "constraint_check": dict(
                        (data.get("params") or {}).get("constraint_check")
                        or candidate.get("constraint_check")
                        or {}
                    ),
                    "candidate_contract_snapshot": dict((data.get("params") or {}).get("candidate_contract_snapshot") or {}),
                    "candidate_contract_hash": str((data.get("params") or {}).get("candidate_contract_hash") or ""),
                    "execution_contract_hash": str((data.get("params") or {}).get("execution_contract_hash") or ""),
                    "tested_object_hash": str((data.get("params") or {}).get("tested_object_hash") or ""),
                    "candidate_identity_signature": str((data.get("params") or {}).get("candidate_identity_signature") or ""),
                    "candidate_lineage_contract": dict((data.get("params") or {}).get("candidate_lineage_contract") or {}),
                    "logic_signature": str((data.get("params") or {}).get("logic_signature") or ""),
                    "dsl_signature": str((data.get("params") or {}).get("dsl_signature") or ""),
                    "factor_signature": str((data.get("params") or {}).get("factor_signature") or ""),
                    "entry_exit_signature": str((data.get("params") or {}).get("entry_exit_signature") or ""),
                    "prediction_trace_id": str(
                        (data.get("params") or {}).get("prediction_trace_id")
                        or candidate.get("prediction_trace_id")
                        or ""
                    ),
                    "trace_id": str(
                        (data.get("params") or {}).get("trace_id")
                        or candidate.get("trace_id")
                        or ""
                    ),
                    "research_validation_contract": dict(
                        (data.get("params") or {}).get("research_validation_contract")
                        or candidate.get("research_validation_contract")
                        or {}
                    ),
                    "research_validation_contract_submission_adapter": dict(
                        (data.get("params") or {}).get("research_validation_contract_submission_adapter")
                        or candidate.get("research_validation_contract_submission_adapter")
                        or {}
                    ),
                    "research_protocol_version": str(
                        (data.get("params") or {}).get("research_protocol_version")
                        or candidate.get("research_protocol_version")
                        or ""
                    ),
                    "candidate_contract_version": str(
                        (data.get("params") or {}).get("candidate_contract_version")
                        or candidate.get("candidate_contract_version")
                        or ""
                    ),
                    "spec_completeness": str(
                        (data.get("params") or {}).get("spec_completeness")
                        or candidate.get("spec_completeness")
                        or ""
                    ),
                    "field_provenance": dict(
                        (data.get("params") or {}).get("field_provenance")
                        or candidate.get("field_provenance")
                        or {}
                    ),
                    "field_provenance_summary": dict(
                        (data.get("params") or {}).get("field_provenance_summary")
                        or candidate.get("field_provenance_summary")
                        or {}
                    ),
                    "completion_issues": list(
                        (data.get("params") or {}).get("completion_issues")
                        or candidate.get("completion_issues")
                        or []
                    ),
                    "hard_failures": list(
                        (data.get("params") or {}).get("hard_failures")
                        or candidate.get("hard_failures")
                        or []
                    ),
                }
            )
            should_persist_strategy = not refresh_existing or bool(gate.get("passed"))
            if should_persist_strategy:
                await db.save_strategy(data)
                await self._persist_metrics(strategy_id, metrics, validation_report, risk_report, db)
            if not refresh_existing and should_persist_strategy:
                await _update_strategy_status(
                    db,
                    strategy_id,
                    "submitted",
                    actor_id="strategy_factory",
                    reason="factory_submit",
                    metadata={
                        "spawn_reason": candidate.get("spawn_reason"),
                        "dedup_result": candidate.get("dedup_result") or {},
                        "incubation_budget": incubation_budget,
                    },
                )
            quality_report = self._build_quality_report(
                strategy_id=strategy_id,
                candidate=candidate,
                snapshot=snapshot,
                backtest_metrics=metrics,
                quality_gate=gate,
                validation_report=validation_report,
                risk_report=risk_report,
                final_status=final_status,
                submission_lane=submission_lane,
            )
            quality_report = _enrich_quality_report_v2(
                quality_report,
                candidate=candidate,
                gate=gate,
                final_status=final_status,
            )
            quality_summary = dict(quality_report.get("summary") or {})
            quality_summary["candidate_contract_hash"] = candidate.get("candidate_contract_hash")
            quality_summary["execution_contract_hash"] = candidate.get("execution_contract_hash")
            quality_summary["tested_object_hash"] = candidate.get("tested_object_hash")
            quality_summary["candidate_identity_signature"] = candidate.get("candidate_identity_signature")
            quality_summary["target_pool_id"] = (
                dict((candidate.get("candidate_contract_snapshot") or {}).get("targeting") or {}).get("target_pool_id")
            )
            quality_summary["lineage_id"] = (
                dict((candidate.get("candidate_contract_snapshot") or {}).get("lineage") or {}).get("lineage_id")
            )
            quality_summary["multiple_testing_registry"] = dict(gate.get("multiple_testing_registry") or {})
            quality_report["summary"] = quality_summary
            quality_report["candidate_contract_hash"] = candidate.get("candidate_contract_hash")
            quality_report["execution_contract_hash"] = candidate.get("execution_contract_hash")
            quality_report["tested_object_hash"] = candidate.get("tested_object_hash")
            quality_report["candidate_identity_signature"] = candidate.get("candidate_identity_signature")
            quality_report["candidate_contract_snapshot"] = dict(candidate.get("candidate_contract_snapshot") or {})
            quality_report["candidate_lineage_contract"] = dict(candidate.get("candidate_lineage_contract") or {})
            quality_report["logic_signature"] = candidate.get("logic_signature")
            quality_report["dsl_signature"] = candidate.get("dsl_signature")
            quality_report["factor_signature"] = candidate.get("factor_signature")
            quality_report["entry_exit_signature"] = candidate.get("entry_exit_signature")

            multiple_testing_registry = dict(gate.get("multiple_testing_registry") or {})
            multiple_testing_registry_record_id = None
            if refresh_existing:
                post_gate = await self._handle_existing_refresh(
                    strategy_id,
                    name,
                    candidate,
                    gate,
                    quality_report,
                    metrics,
                    snapshot,
                    validation_report,
                    risk_report,
                    db,
                    existing_status=existing_status,
                    submission_lane=submission_lane,
                    submission_action=submission_action,
                )
            else:
                post_gate = await self._handle_post_gate(
                    strategy_id,
                    name,
                    candidate,
                    data,
                    gate,
                    quality_report,
                    metrics,
                    snapshot,
                    validation_report,
                    risk_report,
                    db,
                    submission_lane=submission_lane,
                    submission_action=submission_action,
                )
                try:
                    parent_strategy_id = (
                        str((candidate.get("dedup_result") or {}).get("parent_strategy_id") or "").strip()
                        or str(candidate.get("parent_strategy_id") or "").strip()
                        or None
                    )
                    await self._save_strategy_lineage_record(
                        db,
                        strategy_id=strategy_id,
                        parent_strategy_id=parent_strategy_id,
                        reason=str(candidate.get("spawn_reason") or ""),
                        snapshot=snapshot,
                        candidate={**dict(candidate or {}), "multiple_testing_registry": multiple_testing_registry},
                    )
                except Exception as exc:
                    logger.warning("StrategySubmitter: save lineage failed for %s: %s", strategy_id, exc)
                if multiple_testing_registry and callable(getattr(db, "save_factory_task_evidence", None)):
                    research_task = _normalize_research_task_contract(candidate.get("research_task") or {})
                    evidence_payload = {
                        "task_key": str(
                            multiple_testing_registry.get("task_key")
                            or multiple_testing_registry.get("registry_key")
                            or multiple_testing_registry.get("task_signature")
                            or strategy_id
                        ).strip(),
                        "event_id": research_task.get("event_id"),
                        "theme_code": str(research_task.get("theme_code") or "").strip(),
                        "symbol": next(iter(_normalize_target_codes(candidate.get("target_symbols") or [])), None),
                        "evidence_type": "multiple_testing_registry",
                        "weight": float((multiple_testing_registry.get("selection_ratio") or 0.0) or 0.0),
                        "evidence_payload": {
                            **multiple_testing_registry,
                            "strategy_id": strategy_id,
                            "status": str(post_gate.get("final_status") or final_status),
                        },
                    }
                    try:
                        persisted_registry = db.save_factory_task_evidence(evidence_payload)
                        if inspect.isawaitable(persisted_registry):
                            persisted_registry = await persisted_registry
                        if isinstance(persisted_registry, dict):
                            multiple_testing_registry_record_id = persisted_registry.get("id")
                            multiple_testing_registry = {
                                **multiple_testing_registry,
                                "evidence_record_id": multiple_testing_registry_record_id,
                            }
                    except Exception as exc:
                        logger.warning(
                            "StrategySubmitter: save multiple-testing registry failed for %s: %s",
                            strategy_id,
                            exc,
                        )
            if _semantic_contract_feature_enabled():
                candidate_evidence_rows = build_candidate_evidence_records(
                    candidate,
                    strategy_id=strategy_id,
                )
                if callable(getattr(db, "save_strategy_candidate_evidence", None)):
                    for evidence_payload in candidate_evidence_rows:
                        try:
                            persisted_candidate_evidence = db.save_strategy_candidate_evidence(
                                {
                                    "id": evidence_payload.get("id"),
                                    "candidate_id": evidence_payload.get("candidate_id"),
                                    "strategy_id": strategy_id,
                                    "candidate_artifact_id": evidence_payload.get("candidate_artifact_id"),
                                    "experiment_id": evidence_payload.get("experiment_id"),
                                    "evidence_id": evidence_payload.get("evidence_id"),
                                    "evidence_type": evidence_payload.get("evidence_type"),
                                    "source_type": evidence_payload.get("source_type"),
                                    "event_type": evidence_payload.get("event_type"),
                                    "target_symbols": evidence_payload.get("target_symbols") or [],
                                    "direction": evidence_payload.get("direction"),
                                    "horizon_days": evidence_payload.get("horizon_days"),
                                    "raw_confidence": evidence_payload.get("raw_confidence"),
                                    "calibrated_confidence": evidence_payload.get("calibrated_confidence"),
                                    "freshness_ts": evidence_payload.get("freshness_ts"),
                                    "proxy_only": evidence_payload.get("proxy_only"),
                                    "support_metric": evidence_payload.get("support_metric") or {},
                                    "doc_uid": evidence_payload.get("doc_uid"),
                                    "headline_label_id": evidence_payload.get("headline_label_id"),
                                    "source_task_key": evidence_payload.get("source_task_key") or evidence_payload.get("task_key"),
                                    "payload": evidence_payload.get("evidence_payload") or evidence_payload,
                                }
                            )
                            if inspect.isawaitable(persisted_candidate_evidence):
                                await persisted_candidate_evidence
                        except Exception as exc:
                            logger.warning(
                                "StrategySubmitter: save candidate evidence failed for %s: %s",
                                strategy_id,
                                exc,
                            )
            final_status = str(post_gate.get("final_status") or final_status)
            submission_lane = str(post_gate.get("submission_lane") or submission_lane)
            if self._get_optional_db_method(db, "save_strategy_quality_report") is not None:
                await db.save_strategy_quality_report(strategy_id, "submission", quality_report)

            resolved_submission_action = dict(post_gate.get("submission_action") or submission_action.get("submission_action") or {})
            resolved_submission_action_type = post_gate.get("submission_action_type", submission_action.get("submission_action_type"))
            resolved_submission_action_trigger = post_gate.get("submission_action_trigger", submission_action.get("submission_action_trigger"))
            resolved_submission_action_gaps = list(
                post_gate.get("submission_action_gaps", submission_action.get("submission_action_gaps") or [])
                or []
            )
            resolved_submission_action_fallback_conditions = list(
                post_gate.get(
                    "submission_action_fallback_conditions",
                    submission_action.get("submission_action_fallback_conditions") or [],
                )
                or []
            )
            resolved_submission_action_next_step = post_gate.get(
                "submission_action_next_step",
                submission_action.get("submission_action_next_step"),
            )
            dedup_result = dict(candidate.get("dedup_result") or {})
            constraint_check = dict(candidate.get("constraint_check") or {})
            validation_profile = dict(candidate.get("validation_profile") or {})
            precompile_validation = dict(candidate.get("_generator_precompile_validation") or {})
            precompile_constraint_check = dict(precompile_validation.get("constraint_check") or {})
            feedback_metrics = dict(incubation_budget.get("feedback_metrics") or {})
            target_alignment_violation = (
                str(
                    constraint_check.get("alignment_contract_violation")
                    or precompile_constraint_check.get("alignment_contract_violation")
                    or ""
                ).strip().lower()
                or None
            )
            generator_precompile_reject_reason = (
                str(precompile_validation.get("generator_precompile_reject_reason") or "").strip() or None
            )
            contract_reject_reasons = [
                str(reason).strip()
                for reason in list(precompile_validation.get("contract_reject_reasons") or [])
                if str(reason).strip()
            ]
            feedback_control_mode = str(
                feedback_metrics.get("control_mode")
                or incubation_budget.get("feedback_control_mode")
                or "normal"
            ).strip().lower() or "normal"
            feedback_target_pool_control_mode = str(
                feedback_metrics.get("target_pool_control_mode") or "normal"
            ).strip().lower() or "normal"
            feedback_generator_mode_control_mode = str(
                feedback_metrics.get("generator_mode_control_mode") or "normal"
            ).strip().lower() or "normal"
            prediction_trace_id = normalize_prediction_trace_id(
                candidate.get("prediction_trace_id"),
                candidate.get("trace_id"),
                fallback=quality_summary.get("prediction_trace_id"),
            )
            gate_a_summary = _gate_a_payload(candidate)
            gate_b_summary = _gate_b_payload(candidate, gate)
            gate_c_summary = _gate_c_payload({**candidate, **post_gate}, gate, final_status)

            summary = {
                "strategy_id": strategy_id,
                "prediction_trace_id": prediction_trace_id or None,
                "trace_id": prediction_trace_id or None,
                "experiment_id": candidate.get("experiment_id"),
                "generator_type": candidate.get("generator_type"),
                "name": name,
                "status": final_status,
                "passed": bool(gate.get("passed")),
                "passed_strict": bool(gate.get("passed_strict", gate.get("passed"))),
                "provisional_pass": bool(gate.get("provisional_pass")),
                "admission_stage": gate.get("admission_stage"),
                "incubation_pass_mode": gate.get("incubation_pass_mode"),
                "research_candidate_ready": bool(gate.get("research_candidate_ready")),
                "incubation_candidate_ready": bool(gate.get("incubation_candidate_ready")),
                "live_candidate_ready": bool(gate.get("live_candidate_ready")),
                "gate_b_review_decision": gate.get("gate_b_review_decision"),
                "business_admission_decision": dict(gate.get("business_admission_decision") or {}),
                "benchmark_comparison": dict(gate.get("benchmark_comparison") or {}),
                "cost_sensitivity_summary": dict(gate.get("cost_sensitivity_summary") or {}),
                "cash_sleeve_audit": dict(gate.get("cash_sleeve_audit") or {}),
                "family_holding_bucket": dict(gate.get("family_holding_bucket") or {}),
                "submission_lane": submission_lane,
                "formal_track_requested": bool(
                    post_gate.get("formal_track_requested", submission_action.get("formal_track_requested"))
                ),
                "formal_track_eligible": bool(
                    post_gate.get("formal_track_eligible", submission_action.get("formal_track_eligible"))
                ),
                "formal_track_blockers": list(
                    post_gate.get("formal_track_blockers", submission_action.get("formal_track_blockers") or [])
                ),
                "runtime_bootstrap_reason": post_gate.get(
                    "runtime_bootstrap_reason",
                    submission_action.get("runtime_bootstrap_reason"),
                ),
                "submission_action_type": resolved_submission_action_type,
                "submission_action_trigger": resolved_submission_action_trigger,
                "submission_action_gaps": resolved_submission_action_gaps,
                "submission_action_fallback_conditions": resolved_submission_action_fallback_conditions,
                "submission_action_next_step": resolved_submission_action_next_step,
                "submission_action_completed": bool(
                    post_gate.get("submission_action_completed", submission_action.get("submission_action_completed"))
                ),
                "submission_action": resolved_submission_action,
                "direct_trade_candidate": bool(gate.get("live_candidate_ready")),
                "pool_admission_applied": bool(post_gate.get("pool_admission_applied")),
                "promotion_applied_transition": dict(post_gate.get("promotion_applied_transition") or {}),
                "admission_block_reasons": list(gate.get("admission_block_reasons") or []),
                "admission_evaluations": dict(gate.get("admission_evaluations") or {}),
                "reasons": gate.get("reasons") or [],
                "reason_codes": gate.get("reason_codes") or [],
                "warning_codes": gate.get("warning_codes") or [],
                "gate_3": dict(gate or {}),
                "dedup_result": dedup_result,
                "refresh_mode": dedup_result.get("refresh_mode"),
                "refresh_decision_basis": dedup_result.get("refresh_decision_basis"),
                "revision_trigger_reason": dedup_result.get("revision_trigger_reason"),
                "tested_object_hash_changed": dedup_result.get(
                    "tested_object_hash_changed",
                    dedup_result.get("tested_object_changed"),
                ),
                "existing_identity_available": bool(dedup_result.get("existing_identity_available")),
                "existing_tested_object_available": bool(dedup_result.get("existing_tested_object_available")),
                "constraint_check": constraint_check,
                "validation_profile": validation_profile,
                "target_alignment_violation": target_alignment_violation,
                "generator_precompile_reject_reason": generator_precompile_reject_reason,
                "contract_reject_reasons": contract_reject_reasons,
                "feedback_control_mode": feedback_control_mode,
                "feedback_target_pool_control_mode": feedback_target_pool_control_mode,
                "feedback_generator_mode_control_mode": feedback_generator_mode_control_mode,
                "primary_validation_layer": gate.get("primary_validation_layer"),
                "quality_summary": quality_summary,
                "validation_grade": quality_summary.get("validation_grade"),
                "raw_validation_grade": quality_summary.get("raw_validation_grade"),
                "effective_validation_grade": quality_summary.get("effective_validation_grade"),
                "validation_grade_adjustment_reason": quality_summary.get(
                    "validation_grade_adjustment_reason"
                ),
                "validation_total_score": quality_summary.get("validation_total_score"),
                "raw_validation_total_score": quality_summary.get("raw_validation_total_score"),
                "strict_incubation_ready": bool(
                    quality_summary.get("strict_incubation_ready", gate.get("strict_incubation_ready"))
                ),
                "strict_incubation_blocked": bool(
                    quality_summary.get("strict_incubation_blocked", gate.get("strict_incubation_blocked"))
                ),
                "event_window_config": dict(metrics.get("event_window_config") or {}),
                "event_window_metrics": dict(metrics.get("event_window_metrics") or {}),
                "position_assumption": metrics.get("position_assumption"),
                "cost_assumptions": dict(metrics.get("cost_assumptions") or {}),
                "explicit_cost_breakdown": dict(metrics.get("explicit_cost_breakdown") or {}),
                "implicit_cost_breakdown": dict(metrics.get("implicit_cost_breakdown") or {}),
                "backtest_assumptions": dict(metrics.get("backtest_assumptions") or {}),
                "execution_reality": dict(quality_report.get("execution_reality") or {}),
                "attempt_adjustment": dict(gate.get("attempt_adjustment") or {}),
                "committee_review": dict(candidate.get("committee_review") or {}),
                "run_correction": {
                    "mode": gate.get("run_correction_mode"),
                    "deflated_sharpe_proxy": gate.get("deflated_sharpe_proxy"),
                    "pbo_proxy": gate.get("pbo_proxy"),
                    "reality_check_pvalue_proxy": gate.get("reality_check_pvalue_proxy"),
                    "spa_pvalue_proxy": gate.get("spa_pvalue_proxy"),
                    "multiple_testing_mode": gate.get("multiple_testing_mode"),
                    "deflated_sharpe_ratio": gate.get("deflated_sharpe_ratio"),
                    "deflated_sharpe_reference_sharpe": gate.get("deflated_sharpe_reference_sharpe"),
                    "deflated_sharpe_effective_trials": gate.get("deflated_sharpe_effective_trials"),
                    "pbo": gate.get("pbo"),
                    "white_reality_check_pvalue": gate.get("white_reality_check_pvalue"),
                    "hansen_spa_pvalue": gate.get("hansen_spa_pvalue"),
                    "multiple_testing": dict(gate.get("multiple_testing") or {}),
                },
                "multiple_testing_registry": multiple_testing_registry,
                "multiple_testing_registry_record_id": multiple_testing_registry_record_id,
                "task_preference": dict(gate.get("task_preference") or {}),
                "task_signature": _build_task_signature(candidate.get("research_task") or {}),
                "candidate_contract_hash": candidate.get("candidate_contract_hash"),
                "execution_contract_hash": candidate.get("execution_contract_hash"),
                "tested_object_hash": candidate.get("tested_object_hash"),
                "candidate_identity_signature": candidate.get("candidate_identity_signature"),
                "research_protocol_version": candidate.get("research_protocol_version"),
                "candidate_contract_version": candidate.get("candidate_contract_version"),
                "spec_completeness": candidate.get("spec_completeness"),
                "field_provenance_summary": dict(candidate.get("field_provenance_summary") or {}),
                "completion_issues": list(candidate.get("completion_issues") or []),
                "hard_failures": list(candidate.get("hard_failures") or []),
                "gate_a": gate_a_summary,
                "gate_b": gate_b_summary,
                "gate_c": gate_c_summary,
                "candidate_contract_snapshot": dict(candidate.get("candidate_contract_snapshot") or {}),
                "candidate_lineage_contract": dict(candidate.get("candidate_lineage_contract") or {}),
                "logic_signature": candidate.get("logic_signature"),
                "dsl_signature": candidate.get("dsl_signature"),
                "factor_signature": candidate.get("factor_signature"),
                "entry_exit_signature": candidate.get("entry_exit_signature"),
                "target_pool_id": (
                    dict((candidate.get("candidate_contract_snapshot") or {}).get("targeting") or {}).get("target_pool_id")
                ),
                "candidate_provenance": candidate_provenance,
                "strategy_profile": strategy_profile,
                "source_candidate_artifact_id": candidate_provenance.get("source_candidate_artifact_id"),
                "source_generation_artifact_id": candidate_provenance.get("source_generation_artifact_id"),
                "source_validation_artifact_id": candidate_provenance.get("source_validation_artifact_id"),
                "candidate_memory_record_id": candidate_provenance.get("memory_record_id"),
                "candidate_family": candidate_provenance.get("candidate_family"),
                "candidate_family_id": candidate_provenance.get("candidate_family_id"),
                "holding_period_bucket": candidate_provenance.get("holding_period_bucket"),
                "alpha_source": candidate_provenance.get("alpha_source"),
                "risk_level": candidate_provenance.get("risk_level"),
                "regime_fit": candidate_provenance.get("regime_fit"),
                "generator_mode": candidate_provenance.get("generator_mode"),
                "direction_bias": candidate_provenance.get("direction_bias"),
                "validation_profile_name": candidate_provenance.get("validation_profile"),
                "target_symbol_count": candidate_provenance.get("target_symbol_count"),
                "candidate_registry_stage": candidate_provenance.get("candidate_registry_stage"),
                "candidate_validation_score": candidate_provenance.get("validation_score"),
                "expected_regime": list(candidate_provenance.get("expected_regime") or []),
                "expected_holding_period": candidate_provenance.get("expected_holding_period"),
                "candidate_latest_validation_at": candidate_provenance.get("latest_validation_at"),
                "candidate_latest_validation_age_days": candidate_provenance.get("latest_validation_age_days"),
                "incubation_budget": incubation_budget,
                "incubation_budget_track": incubation_budget_track,
                "incubation_budget_rank": incubation_budget.get("rank"),
                "incubation_budget_priority_score": incubation_budget.get("priority_score"),
                "incubation_budget_exploration_candidate": bool(incubation_budget.get("exploration_candidate")),
                **post_gate,
            }
            created_total = bool(not refresh_existing)
            created_strategy_pool = bool(created_total and final_status in {"submitted", "incubating"})
            created_audit_only = bool(created_total and not created_strategy_pool)
            summary.update(
                {
                    "created_total": created_total,
                    "created_strategy_pool": created_strategy_pool,
                    "created_audit_only": created_audit_only,
                }
            )
            for field_name in _SEMANTIC_CONTRACT_FIELDS:
                _assign_optional_payload(summary, field_name, candidate.get(field_name))
            return {
                "created": created_strategy_pool,
                "created_total": created_total,
                "created_strategy_pool": created_strategy_pool,
                "created_audit_only": created_audit_only,
                "refreshed_existing": refresh_existing,
                "submitted": bool(gate.get("passed")),
                "passed": bool(gate.get("passed")),
                "gate_3": dict(gate or {}),
                "summary": summary,
            }

        @staticmethod
        async def _resolve_existing_strategy(candidate: dict, db) -> Optional[dict]:
            dedup_result = dict(candidate.get("dedup_result") or {})
            if not dedup_result.get("refresh_existing"):
                return None
            if str(dedup_result.get("refresh_mode") or "").strip().lower() == "spawn_revision_from_existing":
                return None
            strategy_id = str(dedup_result.get("matched_strategy_id") or "").strip()
            if not strategy_id or not hasattr(db, "get_strategy"):
                return None
            try:
                existing = await db.get_strategy(strategy_id)
            except Exception as exc:
                logger.warning("StrategySubmitter: load existing strategy failed for %s: %s", strategy_id, exc)
                return None
            return dict(existing or {}) if existing else None

        @classmethod
        async def _save_strategy_lineage_record(
            cls,
            db,
            *,
            strategy_id: str,
            parent_strategy_id: Optional[str],
            reason: str,
            snapshot: dict,
            candidate: Optional[dict] = None,
        ) -> None:
            save_lineage = cls._get_optional_db_method(db, "save_strategy_lineage")
            if save_lineage is None:
                return
            contract_snapshot = dict((candidate or {}).get("candidate_contract_snapshot") or {})
            targeting = dict(contract_snapshot.get("targeting") or {})
            lineage_metadata = {
                "candidate_contract_hash": (candidate or {}).get("candidate_contract_hash"),
                "execution_contract_hash": (candidate or {}).get("execution_contract_hash"),
                "tested_object_hash": (candidate or {}).get("tested_object_hash"),
                "candidate_identity_signature": (candidate or {}).get("candidate_identity_signature"),
                "candidate_contract_snapshot": contract_snapshot,
                "candidate_lineage_contract": dict((candidate or {}).get("candidate_lineage_contract") or contract_snapshot.get("lineage") or {}),
                "logic_signature": (candidate or {}).get("logic_signature"),
                "dsl_signature": (candidate or {}).get("dsl_signature"),
                "factor_signature": (candidate or {}).get("factor_signature"),
                "entry_exit_signature": (candidate or {}).get("entry_exit_signature"),
                "target_pool_id": targeting.get("target_pool_id"),
                "task_signature": dict(contract_snapshot.get("lineage") or {}).get("task_signature"),
                "validation_profile": dict(contract_snapshot.get("validation_profile") or {}),
                "lineage_id": dict(contract_snapshot.get("lineage") or {}).get("lineage_id"),
                "multiple_testing_registry": dict((candidate or {}).get("multiple_testing_registry") or {}),
            }
            accepts_metadata = False
            try:
                signature = inspect.signature(save_lineage)
                params = list(signature.parameters.values())
                accepts_metadata = (
                    "metadata" in signature.parameters
                    or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
                )
            except (TypeError, ValueError):
                accepts_metadata = False
            result = (
                save_lineage(strategy_id, parent_strategy_id, reason, snapshot, metadata=lineage_metadata)
                if accepts_metadata
                else save_lineage(strategy_id, parent_strategy_id, reason, snapshot)
            )
            if inspect.isawaitable(result):
                await result

        @classmethod
        def _build_strategy_data(
            cls,
            strategy_id: str,
            name: str,
            candidate: dict,
            metrics: dict,
            existing: Optional[dict] = None,
        ) -> dict:
            """构建策略记录数据。"""
            candidate = apply_resolved_candidate_envelope(candidate)
            existing = dict(existing or {})
            description = f"{name}\n生成原因: {candidate.get('spawn_reason', '')}"
            if metrics:
                description += f"\n回测: Sharpe {metrics.get('sharpe_ratio', 0):.2f} | "
                description += f"收益 {metrics.get('total_return', 0):.1%} | "
                description += f"回撤 {metrics.get('max_drawdown', 0):.1%}"

            existing_params = dict(existing.get("params") or {})
            normalized_task = _normalize_research_task_contract(candidate.get("research_task") or existing_params.get("research_task") or {})
            candidate_provenance = cls._candidate_provenance(candidate, existing)
            research_validation_contract = dict(
                candidate.get("research_validation_contract")
                or existing_params.get("research_validation_contract")
                or {}
            )
            research_validation_contract_submission_adapter = adapt_research_validation_contract_for_submission(
                research_validation_contract
            )
            prediction_trace_id = normalize_prediction_trace_id(
                candidate.get("prediction_trace_id"),
                candidate.get("trace_id"),
                fallback=existing_params.get("prediction_trace_id") or existing_params.get("trace_id"),
            )

            def _assign_if_present(target: dict, key: str, value) -> None:
                if value not in (None, [], {}, ""):
                    target[key] = value

            stored_params = {
                **existing_params,
                **dict(candidate["params"] or {}),
                "target_symbols": list(candidate.get("target_symbols") or existing_params.get("target_symbols") or []),
                "stock_pool": dict(candidate.get("stock_pool") or existing_params.get("stock_pool") or {}),
                "research_task": normalized_task,
                "hypothesis": candidate.get("hypothesis") or existing_params.get("hypothesis"),
                "holding_horizon": dict(candidate.get("holding_horizon") or existing_params.get("holding_horizon") or {}),
                "trade_plan": dict(candidate.get("trade_plan") or existing_params.get("trade_plan") or {}),
                "risk_rules": dict(candidate.get("risk_rules") or existing_params.get("risk_rules") or {}),
                "position_sizing": dict(candidate.get("position_sizing") or existing_params.get("position_sizing") or {}),
                "execution_notes": candidate.get("execution_notes") or existing_params.get("execution_notes"),
                "rebalance_rule": dict(candidate.get("rebalance_rule") or existing_params.get("rebalance_rule") or {}),
                "portfolio_spec": dict(candidate.get("portfolio_spec") or existing_params.get("portfolio_spec") or {}),
                "execution_assumptions": dict(candidate.get("execution_assumptions") or existing_params.get("execution_assumptions") or {}),
                "runtime_playbook": dict(candidate.get("runtime_playbook") or existing_params.get("runtime_playbook") or {}),
                "validation_profile": dict(candidate.get("validation_profile") or existing_params.get("validation_profile") or {}),
                "targeting_policy": dict(candidate.get("targeting_policy") or existing_params.get("targeting_policy") or {}),
                "constraint_check": dict(candidate.get("constraint_check") or existing_params.get("constraint_check") or {}),
                "task_signature": _build_task_signature(normalized_task),
            }
            if research_validation_contract_submission_adapter:
                stored_params["validation_profile"] = {
                    **dict(research_validation_contract_submission_adapter.get("validation_profile") or {}),
                    **dict(stored_params.get("validation_profile") or {}),
                }
            _assign_if_present(stored_params, "research_validation_contract", research_validation_contract)
            _assign_if_present(
                stored_params,
                "research_validation_contract_submission_adapter",
                research_validation_contract_submission_adapter,
            )
            _assign_if_present(
                stored_params,
                "research_protocol_version",
                candidate.get("research_protocol_version")
                or existing_params.get("research_protocol_version")
                or research_validation_contract_submission_adapter.get("research_protocol_version"),
            )
            _assign_if_present(
                stored_params,
                "candidate_contract_version",
                candidate.get("candidate_contract_version") or existing_params.get("candidate_contract_version"),
            )
            _assign_if_present(
                stored_params,
                "spec_completeness",
                candidate.get("spec_completeness") or existing_params.get("spec_completeness"),
            )
            _assign_if_present(
                stored_params,
                "field_provenance",
                dict(candidate.get("field_provenance") or existing_params.get("field_provenance") or {}),
            )
            _assign_if_present(
                stored_params,
                "field_provenance_summary",
                dict(
                    candidate.get("field_provenance_summary")
                    or existing_params.get("field_provenance_summary")
                    or research_validation_contract_submission_adapter.get("field_provenance_summary")
                    or {}
                ),
            )
            _assign_if_present(
                stored_params,
                "completion_issues",
                list(
                    candidate.get("completion_issues")
                    or existing_params.get("completion_issues")
                    or research_validation_contract_submission_adapter.get("completion_issues")
                    or []
                ),
            )
            _assign_if_present(
                stored_params,
                "hard_failures",
                list(candidate.get("hard_failures") or existing_params.get("hard_failures") or []),
            )
            _assign_if_present(stored_params, "prediction_trace_id", prediction_trace_id)
            _assign_if_present(stored_params, "trace_id", prediction_trace_id)
            _assign_if_present(
                stored_params,
                "evidence_chain",
                dict(candidate.get("evidence_chain") or existing_params.get("evidence_chain") or {}),
            )
            _assign_if_present(
                stored_params,
                "prediction_contract",
                dict(candidate.get("prediction_contract") or existing_params.get("prediction_contract") or {}),
            )
            _assign_if_present(
                stored_params,
                "confidence_contract",
                dict(candidate.get("confidence_contract") or existing_params.get("confidence_contract") or {}),
            )
            _assign_if_present(
                stored_params,
                "evidence_alignment_audit",
                dict(candidate.get("evidence_alignment_audit") or existing_params.get("evidence_alignment_audit") or {}),
            )
            _assign_if_present(
                stored_params,
                "dsl_support_audit",
                dict(candidate.get("dsl_support_audit") or existing_params.get("dsl_support_audit") or {}),
            )
            if candidate.get("legacy_semantic_contract") is not None:
                stored_params["legacy_semantic_contract"] = bool(candidate.get("legacy_semantic_contract"))
            if candidate.get("contradiction_count") is not None:
                stored_params["contradiction_count"] = int(candidate.get("contradiction_count") or 0)
            if candidate.get("proxy_dependency_score") is not None:
                stored_params["proxy_dependency_score"] = candidate.get("proxy_dependency_score")
            for field_name in (
                "semantic_runtime_match",
                "runtime_family_data_source",
                "proxy_runtime_used",
                "diagnostic_only",
                "execution_readiness_tier",
                "semantic_contract_missing_fields",
                "execution_semantic_gap_reasons",
            ):
                value = candidate.get(field_name)
                if value in (None, "", [], {}):
                    value = existing_params.get(field_name)
                _assign_if_present(stored_params, field_name, value)
            if candidate_provenance:
                stored_params["candidate_provenance"] = candidate_provenance
                if candidate_provenance.get("source_candidate_artifact_id"):
                    stored_params["source_candidate_artifact_id"] = candidate_provenance.get("source_candidate_artifact_id")
                if candidate_provenance.get("source_generation_artifact_id"):
                    stored_params["source_generation_artifact_id"] = candidate_provenance.get("source_generation_artifact_id")
                if candidate_provenance.get("source_validation_artifact_id"):
                    stored_params["source_validation_artifact_id"] = candidate_provenance.get("source_validation_artifact_id")
                if candidate_provenance.get("memory_record_id"):
                    stored_params["candidate_memory_record_id"] = candidate_provenance.get("memory_record_id")
                _assign_if_present(
                    stored_params,
                    "strategy_profile",
                    dict(candidate_provenance.get("strategy_profile") or stored_params.get("strategy_profile") or {}),
                )
                if candidate_provenance.get("candidate_family"):
                    stored_params["candidate_family"] = candidate_provenance.get("candidate_family")
                _assign_if_present(stored_params, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(stored_params, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(stored_params, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(stored_params, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(stored_params, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(stored_params, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(stored_params, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(stored_params, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(stored_params, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                if candidate_provenance.get("candidate_registry_stage"):
                    stored_params["candidate_registry_stage"] = candidate_provenance.get("candidate_registry_stage")
                if candidate_provenance.get("validation_score") is not None:
                    stored_params["candidate_validation_score"] = candidate_provenance.get("validation_score")
                if candidate_provenance.get("expected_regime"):
                    stored_params["expected_regime"] = list(candidate_provenance.get("expected_regime") or [])
                if candidate_provenance.get("expected_holding_period") is not None:
                    stored_params["expected_holding_period"] = candidate_provenance.get("expected_holding_period")
                if candidate_provenance.get("latest_validation_at"):
                    stored_params["candidate_latest_validation_at"] = candidate_provenance.get("latest_validation_at")
                if candidate_provenance.get("latest_validation_age_days") is not None:
                    stored_params["candidate_latest_validation_age_days"] = candidate_provenance.get("latest_validation_age_days")
                if candidate_provenance.get("admission_block_reasons"):
                    stored_params["candidate_admission_block_reasons"] = list(
                        candidate_provenance.get("admission_block_reasons") or []
                    )
                if candidate_provenance.get("candidate_evidence_status"):
                    stored_params["candidate_evidence_status"] = dict(candidate_provenance.get("candidate_evidence_status") or {})
            if candidate.get("selection_logic") or existing_params.get("selection_logic"):
                stored_params["selection_logic"] = list(candidate.get("selection_logic") or existing_params.get("selection_logic") or [])
            if candidate.get("incubation_budget"):
                stored_params["incubation_budget"] = dict(candidate.get("incubation_budget") or {})
            contract_source = {
                **existing,
                **dict(candidate or {}),
                "id": strategy_id,
                "name": name,
                "strategy_type": candidate["strategy_type"],
                "params": dict(stored_params),
                "target_symbols": list(stored_params.get("target_symbols") or []),
                "stock_pool": dict(stored_params.get("stock_pool") or {}),
                "research_task": dict(stored_params.get("research_task") or {}),
            }
            contract_snapshot = build_portfolio_candidate_contract(contract_source)
            resolved_candidate_envelope = build_resolved_candidate_envelope(contract_source)
            stored_params["candidate_contract_snapshot"] = contract_snapshot
            stored_params["candidate_contract_hash"] = build_candidate_contract_hash(contract=contract_snapshot)
            stored_params["execution_contract_hash"] = (
                str(resolved_candidate_envelope.get("execution_contract_hash") or "").strip()
                or build_execution_contract_hash(contract=contract_snapshot)
            )
            stored_params["tested_object_hash"] = (
                str(resolved_candidate_envelope.get("tested_object_hash") or "").strip()
                or build_tested_object_hash(contract_source)
            )
            stored_params["candidate_identity_signature"] = build_candidate_identity_signature(contract_source)
            stored_params["candidate_lineage_contract"] = dict(contract_snapshot.get("lineage") or {})
            stored_params["logic_signature"] = str(resolved_candidate_envelope.get("logic_signature") or "")
            stored_params["dsl_signature"] = str(resolved_candidate_envelope.get("dsl_signature") or "")
            stored_params["factor_signature"] = str(resolved_candidate_envelope.get("factor_signature") or "")
            stored_params["entry_exit_signature"] = str(resolved_candidate_envelope.get("entry_exit_signature") or "")
            stored_params["resolved_candidate_envelope"] = resolved_candidate_envelope
            return {
                "id": strategy_id,
                "name": name,
                "description": description,
                "author_id": existing.get("author_id") or "strategy_factory",
                "strategy_type": candidate["strategy_type"],
                "params": stored_params,
                "factor_weights": dict((candidate["params"] or {}).get("factor_weights", existing.get("factor_weights") or {})),
                "status": existing.get("status") or "draft",
                "prediction_trace_id": prediction_trace_id or None,
                "trace_id": prediction_trace_id or None,
                "research_protocol_version": stored_params.get("research_protocol_version"),
                "candidate_contract_version": stored_params.get("candidate_contract_version"),
                "spec_completeness": stored_params.get("spec_completeness"),
                "field_provenance_summary": dict(stored_params.get("field_provenance_summary") or {}),
                "completion_issues": list(stored_params.get("completion_issues") or []),
                "hard_failures": list(stored_params.get("hard_failures") or []),
                "tags": list(
                    dict.fromkeys([*(existing.get("tags") or []), "auto_generated", "factory", candidate["strategy_type"], *(candidate.get("tags") or [])])
                ),
            }

        async def _evaluate_reports(self, candidate: dict, db) -> tuple[Optional[dict], Optional[dict]]:
            """先计算验证/风险报告，避免在 Gate-3 前产生持久化副作用。"""
            report_params = self._candidate_report_params(candidate)
            validation_report = None
            try:
                validation_report = await self._get_validation_gateway().run_validation_report(
                    candidate["strategy_type"],
                    report_params,
                    db,
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: validation report failed for %s: %s", candidate.get("strategy_type"), exc)

            risk_report = None
            try:
                risk_report = await self._get_risk_gateway().run_risk_report(
                    candidate["strategy_type"],
                    report_params,
                    db,
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: risk report failed for %s: %s", candidate.get("strategy_type"), exc)

            return validation_report, risk_report

        async def _persist_metrics(
            self,
            strategy_id: str,
            metrics: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
        ) -> None:
            """Gate-3 决策后再落库指标，避免未通过候选提前写入。"""
            if metrics:
                try:
                    await db.save_strategy_metrics(
                        strategy_id,
                        "backtest",
                        {
                            "sharpe_ratio": metrics.get("sharpe_ratio"),
                            "total_return": metrics.get("total_return"),
                            "max_drawdown": metrics.get("max_drawdown"),
                            "win_rate": metrics.get("win_rate"),
                            "trade_count": int(metrics.get("trades_count", 0)),
                        },
                    )
                except Exception as exc:
                    logger.warning("StrategySubmitter: save backtest metrics failed for %s: %s", strategy_id, exc)

            if validation_report:
                try:
                    rating = validation_report.get("rating", {})
                    await db.save_strategy_metrics(
                        strategy_id,
                        "validation",
                        {
                            "grade": rating.get("grade"),
                            "total_score": rating.get("total_score"),
                            "oos_rank_ic": validation_report.get("walk_forward", {}).get("oos_rank_ic_mean"),
                            "recommendation": rating.get("recommendation"),
                        },
                    )
                except Exception as exc:
                    logger.warning("StrategySubmitter: save validation metrics failed for %s: %s", strategy_id, exc)

            if risk_report:
                try:
                    await db.save_strategy_metrics(strategy_id, "risk", risk_report)
                except Exception as exc:
                    logger.warning("StrategySubmitter: save risk metrics failed for %s: %s", strategy_id, exc)

        @staticmethod
        def _normalized_validation_grade(gate: Optional[dict[str, Any]]) -> str:
            normalized_gate = dict(gate or {})
            return str(
                normalized_gate.get("effective_validation_grade")
                or normalized_gate.get("validation_grade")
                or normalized_gate.get("raw_validation_grade")
                or ""
            ).strip().upper()

        @staticmethod
        def _strategy_type_registered(candidate: Optional[dict[str, Any]]) -> bool:
            strategy_type = str(
                candidate_contract_value(candidate or {}, "strategy_type")
                or dict(candidate or {}).get("strategy_type")
                or ""
            ).strip().lower()
            return bool(strategy_type) and strategy_type in _VALID_STRATEGY_TYPES

        @staticmethod
        def _default_runtime_holding_horizon(strategy_type: str) -> dict[str, Any]:
            normalized = str(strategy_type or "").strip().lower()
            if normalized in {"quality_factor", "value_factor"}:
                return {"min_days": 30, "max_days": 84, "cooldown_window_days": 7}
            if normalized in {"momentum", "ma_cross", "volatility_breakout"}:
                return {"min_days": 14, "max_days": 48, "cooldown_window_days": 5}
            return {"min_days": 5, "max_days": 20, "cooldown_window_days": 5}

        @staticmethod
        def _default_runtime_trade_plan(strategy_type: str) -> dict[str, Any]:
            normalized = str(strategy_type or "").strip().lower()
            if normalized == "momentum":
                return {
                    "entry_bias": "trend_persistence_confirmation",
                    "exit_bias": "false_breakout_or_momentum_decay",
                }
            if normalized == "ma_cross":
                return {
                    "entry_bias": "adaptive_cross_with_volume_confirmation",
                    "exit_bias": "range_reentry_or_cross_failure",
                }
            if normalized in {"quality_factor", "value_factor"}:
                return {
                    "entry_bias": "cross_sectional_rank",
                    "exit_bias": "rank_decay_or_periodic_rebalance",
                }
            return {
                "entry_bias": "signal_confirmed",
                "exit_bias": "signal_or_time_stop",
            }

        @classmethod
        def _default_runtime_risk_rules(cls, strategy_type: str, holding_horizon: dict[str, Any]) -> dict[str, Any]:
            normalized = str(strategy_type or "").strip().lower()
            max_holding_days = int(holding_horizon.get("max_days") or 20)
            if normalized in {"quality_factor", "value_factor"}:
                return {
                    "stop_loss_pct": 0.08,
                    "take_profit_pct": 0.18,
                    "max_holding_days": max(max_holding_days, 42),
                    "cooldown_days": max(5, int(holding_horizon.get("cooldown_window_days") or 7)),
                }
            return {
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.20,
                "max_holding_days": max_holding_days,
                "cooldown_days": max(3, int(holding_horizon.get("cooldown_window_days") or 5)),
            }

        @staticmethod
        def _default_runtime_execution_assumptions() -> dict[str, Any]:
            return {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            }

        @classmethod
        def _runtime_playbook_from_contract(cls, candidate: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(candidate or {})
            playbook = dict(candidate_contract_value(payload, "runtime_playbook", {}) or {})
            if playbook:
                return playbook
            holding_horizon = dict(candidate_contract_value(payload, "holding_horizon", {}) or {})
            trade_plan = dict(candidate_contract_value(payload, "trade_plan", {}) or {})
            risk_rules = dict(candidate_contract_value(payload, "risk_rules", {}) or {})
            execution_assumptions = dict(candidate_contract_value(payload, "execution_assumptions", {}) or {})
            portfolio_spec = dict(candidate_contract_value(payload, "portfolio_spec", {}) or {})
            if not holding_horizon and not trade_plan and not risk_rules and not execution_assumptions:
                return {}

            strategy_type = str(payload.get("strategy_type") or "").strip().lower()
            stop_loss_pct = abs(float(risk_rules.get("stop_loss_pct") or risk_rules.get("stop_loss") or 0.08) or 0.08)
            take_profit_pct = abs(
                float(risk_rules.get("take_profit_pct") or risk_rules.get("take_profit") or max(stop_loss_pct * 2.0, 0.12))
                or max(stop_loss_pct * 2.0, 0.12)
            )
            time_stop_days = max(1, int(risk_rules.get("max_holding_days") or holding_horizon.get("max_days") or 20))
            cooldown_days = max(
                1,
                int(
                    risk_rules.get("cooldown_days")
                    or risk_rules.get("cooldown_window_days")
                    or trade_plan.get("cooldown_window_days")
                    or holding_horizon.get("cooldown_window_days")
                    or 5
                ),
            )
            max_position_pct = min(
                0.35,
                max(
                    0.02,
                    float(
                        portfolio_spec.get("max_position_pct")
                        or risk_rules.get("max_position_pct")
                        or 0.18
                    )
                    or 0.18,
                ),
            )
            family = "default"
            if strategy_type in {"momentum", "ma_cross", "volatility_breakout"}:
                family = "trend"
            elif strategy_type in {"quality_factor", "value_factor"}:
                family = "slow_factor"
                time_stop_days = max(time_stop_days, 42)
            failure_exit_rule = (
                "opposite_signal_or_breakout_failure"
                if family == "trend"
                else "quality_drift_or_rank_decay"
                if family == "slow_factor"
                else "signal_or_time_stop"
            )
            playbook = {
                "entry_policy": {
                    "order_style": "marketable_limit",
                    "signal_validity_days": max(1, min(5, max(1, time_stop_days // 5))),
                    "max_slippage_bps": float(
                        execution_assumptions.get("max_slippage_bps")
                        or execution_assumptions.get("slippage_bps")
                        or 5.0
                    ),
                    "tradability_guard": bool(
                        execution_assumptions.get("tradability_filter")
                        if execution_assumptions.get("tradability_filter") is not None
                        else True
                    ),
                },
                "exit_policy": {
                    "initial_stop_loss_pct": round(max(0.02, stop_loss_pct), 4),
                    "take_profit_pct": round(max(take_profit_pct, stop_loss_pct), 4),
                    "trailing_stop_pct": round(max(0.03, min(stop_loss_pct * (0.8 if family == "trend" else 1.0), 0.12)), 4),
                    "trailing_activation_profit_pct": round(max(stop_loss_pct, 0.05), 4),
                    "time_stop_days": int(time_stop_days),
                    "failure_exit_rule": failure_exit_rule,
                },
                "adverse_move_policy": {
                    "loss_bands": [
                        {
                            "threshold_pct": round(max(0.01, stop_loss_pct * 0.5), 4),
                            "action": "hold",
                            "label": "soft_drawdown_watch",
                        },
                        {
                            "threshold_pct": round(max(0.02, stop_loss_pct), 4),
                            "action": "reduce" if family == "slow_factor" else "exit",
                            "label": "primary_stop_band",
                        },
                        {
                            "threshold_pct": round(max(0.03, stop_loss_pct * 1.2), 4),
                            "action": "freeze_reentry",
                            "label": "hard_stop_band",
                        },
                    ],
                    "average_down": "forbid",
                    "freeze_after_stop": True,
                    "reduce_on_drawdown": family == "slow_factor",
                },
                "reentry_policy": {
                    "cooldown_days": int(cooldown_days),
                    "reclaim_condition": (
                        "reclaim_fast_ma_and_break_recent_high"
                        if family == "trend"
                        else "recover_rank_and_trend_alignment"
                        if family == "slow_factor"
                        else "signal_reconfirm_after_cooldown"
                    ),
                    "max_retries_per_20d": 1 if family == "slow_factor" else 2,
                },
                "position_policy": {
                    "budget_mode": "fixed_fraction",
                    "base_budget_pct": 0.05 if family == "slow_factor" else 0.04,
                    "max_position_pct": round(max_position_pct, 4),
                    "max_concurrent_positions": 2 if family in {"trend", "slow_factor"} else 1,
                    "scale_in": {"enabled": False, "mode": "forbid"},
                    "scale_out": {
                        "enabled": family == "slow_factor",
                        "mode": "reduce_then_exit" if family == "slow_factor" else "take_profit_or_trailing",
                    },
                },
                "incubation_policy": {
                    "warmup_target_signals": 20,
                    "warmup_soft_timeout_days": 5,
                    "warmup_hard_timeout_days": 20,
                    "warmup_max_days": 30,
                },
            }
            return playbook

        @classmethod
        def _ensure_runtime_playbook(cls, candidate: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(candidate or {})
            params = dict(payload.get("params") or {})
            strategy_type = str(payload.get("strategy_type") or "").strip().lower()
            holding_horizon = dict(candidate_contract_value(payload, "holding_horizon", {}) or {})
            if not holding_horizon:
                holding_horizon = cls._default_runtime_holding_horizon(strategy_type)
            trade_plan = dict(candidate_contract_value(payload, "trade_plan", {}) or {})
            if not trade_plan:
                trade_plan = cls._default_runtime_trade_plan(strategy_type)
            risk_rules = dict(candidate_contract_value(payload, "risk_rules", {}) or {})
            if not risk_rules:
                risk_rules = cls._default_runtime_risk_rules(strategy_type, holding_horizon)
            execution_assumptions = dict(candidate_contract_value(payload, "execution_assumptions", {}) or {})
            if not execution_assumptions:
                execution_assumptions = cls._default_runtime_execution_assumptions()
            payload["holding_horizon"] = holding_horizon
            payload["trade_plan"] = trade_plan
            payload["risk_rules"] = risk_rules
            payload["execution_assumptions"] = execution_assumptions
            params.update(
                {
                    "holding_horizon": dict(holding_horizon),
                    "trade_plan": dict(trade_plan),
                    "risk_rules": dict(risk_rules),
                    "execution_assumptions": dict(execution_assumptions),
                }
            )
            playbook = cls._runtime_playbook_from_contract(payload)
            if not playbook:
                payload["params"] = params
                return payload
            params["runtime_playbook"] = dict(playbook)
            payload["params"] = params
            payload["runtime_playbook"] = dict(playbook)
            return payload

        @classmethod
        def _runtime_bootstrap_context(
            cls,
            gate: Optional[dict[str, Any]],
            *,
            candidate: Optional[dict[str, Any]],
        ) -> dict[str, Any]:
            normalized_gate = dict(gate or {})
            payload = cls._ensure_runtime_playbook(candidate)
            validation_grade = cls._normalized_validation_grade(normalized_gate)
            strategy_type_registered = cls._strategy_type_registered(payload)
            missing_runtime_fields = [
                field_name
                for field_name in _RUNTIME_BOOTSTRAP_REQUIRED_FIELDS
                if candidate_contract_value(payload, field_name) in _EMPTY_CONTRACT_VALUES
            ]
            runtime_playbook_present = bool(candidate_contract_value(payload, "runtime_playbook", {}))
            execution_semantic_mode = str(
                candidate_contract_value(payload, "execution_semantic_mode") or ""
            ).strip().lower() or None
            execution_semantic_gap = bool(candidate_contract_value(payload, "execution_semantic_gap"))
            execution_semantic_gap_reasons = [
                str(item or "").strip()
                for item in list(candidate_contract_value(payload, "execution_semantic_gap_reasons", []) or [])
                if str(item or "").strip()
            ]
            dsl_required = bool(candidate_contract_value(payload, "dsl_required"))
            dsl_compiled = bool(candidate_contract_value(payload, "dsl_compiled"))
            semantic_runtime_match = bool(
                candidate_contract_value(payload, "semantic_runtime_match", True)
            )
            runtime_family_data_source = str(
                candidate_contract_value(payload, "runtime_family_data_source") or ""
            ).strip().lower() or None
            proxy_runtime_used = bool(candidate_contract_value(payload, "proxy_runtime_used"))
            diagnostic_only = bool(candidate_contract_value(payload, "diagnostic_only"))
            execution_readiness_tier = str(
                candidate_contract_value(payload, "execution_readiness_tier") or ""
            ).strip().lower() or None
            semantic_contract_missing_fields = [
                str(item or "").strip()
                for item in list(candidate_contract_value(payload, "semantic_contract_missing_fields", []) or [])
                if str(item or "").strip()
            ]
            semantic_hard_fail = bool(
                list(
                    dict(payload.get("evidence_alignment_audit") or {}).get("hard_fail_reasons") or []
                )
            )
            quality_passed = bool(normalized_gate.get("passed"))
            runtime_bootstrap_eligible = (
                quality_passed
                and validation_grade != "D"
                and strategy_type_registered
                and not missing_runtime_fields
                and not semantic_hard_fail
            )
            if runtime_bootstrap_eligible:
                runtime_bootstrap_reason = (
                    "execution_semantic_gap_observe_only"
                    if execution_semantic_gap
                    else "proxy_runtime_observe_only"
                    if proxy_runtime_used
                    else "diagnostic_only_observe"
                    if diagnostic_only
                    else "quality_passed_non_d_candidate_with_complete_runtime_contract"
                )
            elif not quality_passed:
                runtime_bootstrap_reason = "quality_gate_failed"
            elif validation_grade == "D":
                runtime_bootstrap_reason = "validation_grade_d_not_allowed_for_runtime"
            elif not strategy_type_registered:
                runtime_bootstrap_reason = "strategy_type_not_registered"
            elif missing_runtime_fields:
                runtime_bootstrap_reason = f"missing_runtime_contract:{','.join(missing_runtime_fields)}"
            elif semantic_hard_fail:
                runtime_bootstrap_reason = "semantic_hard_fail"
            else:
                runtime_bootstrap_reason = "runtime_bootstrap_blocked"
            budget_tier = None
            if runtime_bootstrap_eligible:
                budget_tier = (
                    "micro"
                    if execution_semantic_gap or proxy_runtime_used or diagnostic_only
                    else "standard" if validation_grade in {"A", "B"} else "micro"
                )
            return {
                "runtime_bootstrap_eligible": runtime_bootstrap_eligible,
                "runtime_bootstrap_reason": runtime_bootstrap_reason,
                "runtime_bootstrap_budget_tier": budget_tier,
                "runtime_playbook_present": runtime_playbook_present,
                "runtime_contract_missing_fields": missing_runtime_fields,
                "strategy_type_registered": strategy_type_registered,
                "execution_semantic_mode": execution_semantic_mode,
                "execution_semantic_gap": execution_semantic_gap,
                "execution_semantic_gap_reasons": execution_semantic_gap_reasons,
                "dsl_required": dsl_required,
                "dsl_compiled": dsl_compiled,
                "semantic_runtime_match": semantic_runtime_match,
                "runtime_family_data_source": runtime_family_data_source,
                "proxy_runtime_used": proxy_runtime_used,
                "diagnostic_only": diagnostic_only,
                "execution_readiness_tier": execution_readiness_tier,
                "semantic_contract_missing_fields": semantic_contract_missing_fields,
            }

        @classmethod
        def _apply_runtime_bootstrap_contract(
            cls,
            candidate: Optional[dict[str, Any]],
            *,
            submission_lane: str,
            runtime_bootstrap_eligible: bool,
            runtime_bootstrap_budget_tier: Optional[str],
        ) -> dict[str, Any]:
            payload = cls._ensure_runtime_playbook(candidate)
            if (
                str(submission_lane or "").strip().lower() != "observe_incubation"
                or not runtime_bootstrap_eligible
                or runtime_bootstrap_budget_tier not in {"standard", "micro"}
            ):
                return payload
            playbook = dict(payload.get("runtime_playbook") or {})
            entry_policy = dict(playbook.get("entry_policy") or {})
            position_policy = dict(playbook.get("position_policy") or {})
            entry_policy["order_style"] = "marketable_limit"
            if runtime_bootstrap_budget_tier == "standard":
                position_policy["base_budget_pct"] = 0.06
                position_policy["max_concurrent_positions"] = 2
            else:
                position_policy["base_budget_pct"] = 0.03
                position_policy["max_concurrent_positions"] = 1
            playbook["entry_policy"] = entry_policy
            playbook["position_policy"] = position_policy
            params = dict(payload.get("params") or {})
            params["runtime_playbook"] = dict(playbook)
            payload["params"] = params
            payload["runtime_playbook"] = dict(playbook)
            return payload

        @classmethod
        def _should_bootstrap_observe_candidate(
            cls,
            gate: Optional[dict[str, Any]],
            *,
            incubation_budget_track: str,
        ) -> bool:
            normalized_gate = dict(gate or {})
            track = str(incubation_budget_track or "").strip().lower()
            if track not in {"", "deferred_budget_queue", "deferred_submission"}:
                return False
            if not bool(normalized_gate.get("passed")):
                return False
            if bool(normalized_gate.get("live_candidate_ready")):
                return False
            if bool(normalized_gate.get("research_only_due_to_trade_audit_gap")):
                return False
            if not bool(normalized_gate.get("research_candidate_ready")):
                return False
            if not bool(normalized_gate.get("strict_incubation_ready")):
                return False
            if str(normalized_gate.get("incubation_pass_mode") or "").strip().lower() != "strict":
                return False
            if bool(normalized_gate.get("provisional_pass")):
                return False
            validation_grade = cls._normalized_validation_grade(normalized_gate)
            return validation_grade in {"A", "B"}

        @classmethod
        def _allow_observe_trade_audit_bootstrap(
            cls,
            gate: Optional[dict[str, Any]],
            *,
            incubation_budget_track: str,
        ) -> bool:
            normalized_gate = dict(gate or {})
            if str(incubation_budget_track or "").strip().lower() != "observe_incubation":
                return False
            if not bool(normalized_gate.get("passed")):
                return False
            if not bool(normalized_gate.get("research_candidate_ready")):
                return False
            if bool(normalized_gate.get("live_candidate_ready")):
                return False
            validation_grade = cls._normalized_validation_grade(normalized_gate)
            return validation_grade != "D"

        @classmethod
        def _resolve_submission_action_plan(
            cls,
            gate: dict,
            *,
            candidate: Optional[dict[str, Any]] = None,
            refresh_existing: bool,
            existing_status: str,
            incubation_budget_track: str,
        ) -> dict[str, Any]:
            normalized_gate = dict(gate or {})
            runtime_bootstrap = cls._runtime_bootstrap_context(
                normalized_gate,
                candidate=candidate,
            )
            gate_a_decision = str(normalized_gate.get("gate_a_decision") or "").strip().lower()
            readiness_fields = (
                "research_candidate_ready",
                "incubation_candidate_ready",
                "live_candidate_ready",
                "research_only_due_to_trade_audit_gap",
            )
            if bool(normalized_gate.get("passed")) and not any(field in normalized_gate for field in readiness_fields):
                normalized_gate["research_candidate_ready"] = True
                normalized_gate["incubation_candidate_ready"] = True
            admission_block_reasons = list(normalized_gate.get("admission_block_reasons") or normalized_gate.get("reasons") or [])
            strict_formal_ready = bool(normalized_gate.get("strict_incubation_ready")) or (
                str(normalized_gate.get("incubation_pass_mode") or "").strip().lower() == "strict"
            )
            formal_track_requested = str(incubation_budget_track or "").strip().lower() == "formal_incubation"
            formal_track_blockers: list[str] = []
            if formal_track_requested:
                if not bool(runtime_bootstrap.get("runtime_bootstrap_eligible")):
                    formal_track_blockers.append(
                        str(runtime_bootstrap.get("runtime_bootstrap_reason") or "runtime_bootstrap_not_eligible")
                    )
                if bool(runtime_bootstrap.get("execution_semantic_gap")):
                    formal_track_blockers.extend(
                        list(runtime_bootstrap.get("execution_semantic_gap_reasons") or [])
                        or ["execution_semantic_gap"]
                    )
                if not bool(runtime_bootstrap.get("semantic_runtime_match")):
                    formal_track_blockers.append("semantic_runtime_mismatch")
                if bool(runtime_bootstrap.get("proxy_runtime_used")):
                    formal_track_blockers.append("proxy_runtime_not_allowed_for_formal_incubation")
                if bool(runtime_bootstrap.get("diagnostic_only")):
                    formal_track_blockers.append("diagnostic_only_runtime")
                readiness_tier = (
                    str(runtime_bootstrap.get("execution_readiness_tier") or "").strip().lower() or "unknown"
                )
                if readiness_tier != "formal_runtime_ready":
                    formal_track_blockers.append(f"execution_readiness_tier:{readiness_tier}")
                if not strict_formal_ready:
                    formal_track_blockers.append("strict_incubation_pass_required_for_formal_track")
            formal_track_blockers = list(
                dict.fromkeys([item for item in formal_track_blockers if str(item).strip()])
            )
            formal_track_eligible = bool(formal_track_requested and not formal_track_blockers)
            if refresh_existing:
                action_type = "refresh_existing"
                submission_lane = "refresh_existing"
                final_status = str(existing_status or "draft")
                trigger = "existing_strategy_refresh"
                gaps = []
                fallback_conditions = ["manual_review_if_contract_changes"]
                next_step = "existing_status_preserved"
                completed = True
            elif gate_a_decision == "revise" and not bool(normalized_gate.get("passed")):
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "draft"
                trigger = "gate_a_revision_required"
                gaps = admission_block_reasons
                fallback_conditions = ["supply_required_research_protocol_fields_and_replay_submission"]
                next_step = "research"
                completed = True
            elif gate_a_decision == "reject" and not bool(normalized_gate.get("passed")):
                action_type = "research_only"
                submission_lane = "rejected"
                final_status = "rejected"
                trigger = "gate_a_reject"
                gaps = admission_block_reasons
                fallback_conditions = ["restore_required_research_protocol_fields_before_submission_replay"]
                next_step = "research"
                completed = True
            elif not bool(normalized_gate.get("passed")):
                action_type = "research_only"
                submission_lane = "rejected"
                final_status = "rejected"
                trigger = "quality_gate_failed"
                gaps = admission_block_reasons
                fallback_conditions = ["re_enter_after_quality_gaps_closed"]
                next_step = "incubation"
                completed = True
            elif bool(normalized_gate.get("live_candidate_ready")) and not bool(runtime_bootstrap.get("execution_semantic_gap")):
                formal_runtime_ready = (
                    bool(runtime_bootstrap.get("semantic_runtime_match"))
                    and not bool(runtime_bootstrap.get("proxy_runtime_used"))
                    and not bool(runtime_bootstrap.get("diagnostic_only"))
                    and str(runtime_bootstrap.get("execution_readiness_tier") or "").strip().lower() == "formal_runtime_ready"
                )
                if not formal_runtime_ready:
                    action_type = "paper"
                    submission_lane = "observe_incubation"
                    final_status = "submitted"
                    trigger = str(
                        runtime_bootstrap.get("runtime_bootstrap_reason")
                        or "formal_lane_requires_semantic_runtime_match"
                    )
                    gaps = list(
                        dict.fromkeys(
                            [
                                *admission_block_reasons,
                                trigger,
                            ]
                        )
                    )
                    fallback_conditions = [
                        "promote_after_runtime_data_source_and_semantic_contract_are_repaired",
                    ]
                    next_step = "runtime_review"
                    completed = False
                else:
                    action_type = "runtime_review"
                    submission_lane = "live_ready_review"
                    final_status = "submitted"
                    trigger = "live_candidate_ready"
                    gaps = []
                    fallback_conditions = [
                        "downgrade_to_paper_if_runtime_review_fails",
                        "return_to_research_if_runtime_alerts_fire",
                    ]
                    next_step = "pool_admission"
                    completed = False
            elif formal_track_eligible:
                action_type = "incubation"
                submission_lane = "formal_incubation"
                final_status = "incubating"
                trigger = "strict_incubation_ready_and_budget_formal"
                gaps = admission_block_reasons
                fallback_conditions = [
                    "downgrade_to_observe_if_signal_quality_or_execution_evidence_weakens",
                    "return_to_research_if_runtime_risk_accumulates",
                ]
                next_step = "paper"
                completed = False
            elif runtime_bootstrap.get("runtime_bootstrap_eligible"):
                action_type = "paper"
                submission_lane = "observe_incubation"
                final_status = "submitted"
                trigger = "runtime_bootstrap_observe"
                gaps = admission_block_reasons
                fallback_conditions = [
                    "promote_to_formal_after_signal_quality_and_execution_conversion_improve",
                    "return_to_research_if_runtime_bootstrap_evidence_turns_negative",
                ]
                next_step = "runtime_review"
                completed = False
            elif formal_track_requested:
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted" if bool(normalized_gate.get("research_candidate_ready")) else "rejected"
                trigger = "formal_incubation_requires_bootstrap_or_strict_gate"
                gaps = list(
                    dict.fromkeys(
                        [
                            *list(admission_block_reasons),
                            *formal_track_blockers,
                        ]
                    )
                )
                fallback_conditions = [
                    "promote_after_runtime_contract_is_repaired_or_quality_improves",
                    "observe_track_allowed_after_runtime_bootstrap_eligibility_is_restored",
                ]
                next_step = "research"
                completed = True
            elif str(incubation_budget_track or "").strip().lower() == "observe_incubation":
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted" if bool(normalized_gate.get("research_candidate_ready")) else "rejected"
                trigger = str(runtime_bootstrap.get("runtime_bootstrap_reason") or "observe_track_runtime_contract_incomplete")
                gaps = list(dict.fromkeys([*admission_block_reasons, trigger]))
                fallback_conditions = ["repair_runtime_contract_and_replay_submission"]
                next_step = "research"
                completed = True
            else:
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted"
                trigger = str(runtime_bootstrap.get("runtime_bootstrap_reason") or "budget_deferred_research_only")
                gaps = list(dict.fromkeys([*admission_block_reasons, trigger]))
                fallback_conditions = ["promote_to_observe_after_runtime_bootstrap_eligibility_is_restored"]
                next_step = "incubation"
                completed = True

            plan = {
                "type": action_type,
                "trigger_reason": trigger,
                "gaps": list(gaps),
                "fallback_conditions": list(fallback_conditions),
                "next_step": next_step,
                "submission_lane": submission_lane,
                "final_status": final_status,
                "completed": bool(completed),
                "formal_track_requested": formal_track_requested,
                "formal_track_eligible": formal_track_eligible,
                "formal_track_blockers": list(formal_track_blockers),
                **runtime_bootstrap,
            }
            return {
                "submission_action": plan,
                "submission_action_type": action_type,
                "submission_action_trigger": trigger,
                "submission_action_gaps": list(gaps),
                "submission_action_fallback_conditions": list(fallback_conditions),
                "submission_action_next_step": next_step,
                "submission_action_completed": bool(completed),
                "submission_lane": submission_lane,
                "final_status": final_status,
                "formal_track_requested": formal_track_requested,
                "formal_track_eligible": formal_track_eligible,
                "formal_track_blockers": list(formal_track_blockers),
                **runtime_bootstrap,
            }

        @classmethod
        def _resolve_submission_lane(
            cls,
            gate: dict,
            *,
            candidate: Optional[dict[str, Any]] = None,
            refresh_existing: bool,
            existing_status: str,
            incubation_budget_track: str,
        ) -> tuple[str, str]:
            plan = cls._resolve_submission_action_plan(
                gate,
                candidate=candidate,
                refresh_existing=refresh_existing,
                existing_status=existing_status,
                incubation_budget_track=incubation_budget_track,
            )
            return str(plan.get("submission_lane") or "deferred_submission"), str(plan.get("final_status") or "submitted")

        @staticmethod
        def _apply_submission_action_audit(
            quality_report: Optional[dict],
            *,
            final_status: str,
            submission_lane: str,
            submission_audit: Optional[dict] = None,
        ) -> dict:
            report = quality_report if isinstance(quality_report, dict) else {}
            summary = dict(report.get("summary") or {})
            audit = dict(submission_audit or {})
            summary["status_after_review"] = final_status
            summary["submission_lane"] = submission_lane
            report["submission_lane"] = submission_lane
            field_names = (
                "live_review_ready",
                "paper_lane_ready",
                "paper_account_id",
                "paper_account_status",
                "live_review_account_id",
                "runtime_control_mode",
                "runtime_control_status",
                "promotion_review_id",
                "promotion_review_status",
                "promotion_review_recommendation",
                "promotion_review_score",
                "pool_admission_applied",
                "promotion_applied_transition",
                "runtime_bootstrap_eligible",
                "runtime_bootstrap_reason",
                "runtime_bootstrap_budget_tier",
                "runtime_playbook_present",
                "formal_track_requested",
                "formal_track_eligible",
                "formal_track_blockers",
                "execution_semantic_mode",
                "execution_semantic_gap",
                "execution_semantic_gap_reasons",
                "dsl_required",
                "dsl_compiled",
                "semantic_runtime_match",
                "runtime_family_data_source",
                "proxy_runtime_used",
                "diagnostic_only",
                "execution_readiness_tier",
                "semantic_contract_missing_fields",
                "submission_action",
                "submission_action_type",
                "submission_action_trigger",
                "submission_action_gaps",
                "submission_action_fallback_conditions",
                "submission_action_next_step",
                "submission_action_completed",
            )
            clearable_fields = {"submission_action_next_step"}
            for field_name in field_names:
                if field_name not in audit:
                    continue
                value = audit.get(field_name)
                if value in (None, [], {}, "") and field_name not in clearable_fields:
                    continue
                summary[field_name] = value
                report[field_name] = value
            report["summary"] = summary
            return report

        async def _enqueue_paper_observation(
            self,
            db,
            strategy: dict,
            snapshot: dict,
        ) -> dict:
            paper_account_id = None
            paper_account_status = None
            incubation_gateway = self._get_incubation_gateway()

            try:
                binding = await incubation_gateway.ensure_account(
                    db,
                    strategy,
                    source_run_id=snapshot.get("date"),
                    stage="paper",
                )
                paper_account_id = (
                    ((binding or {}).get("account") or {}).get("id")
                    or ((binding or {}).get("binding") or {}).get("account_id")
                )
                if paper_account_id:
                    updated = await self._call_optional_db_method(
                        db,
                        "update_paper_account_status",
                        paper_account_id,
                        "active",
                        stage="paper",
                        promotion_candidate=False,
                    )
                    paper_account_status = (updated or {}).get("status") if isinstance(updated, dict) else "active"
            except Exception as exc:
                logger.warning("StrategyFactory: ensure paper observation account failed for %s: %s", strategy.get("id"), exc)

            return {
                "paper_lane_ready": bool(paper_account_id),
                "paper_account_id": paper_account_id,
                "paper_account_status": paper_account_status or ("active" if paper_account_id else None),
            }

        async def _enqueue_live_ready_review(
            self,
            db,
            strategy: dict,
            snapshot: dict,
            gate: dict,
        ) -> dict:
            review_account_id = None
            runtime_control = None
            promotion_review = None
            incubation_gateway = self._get_incubation_gateway()

            try:
                binding = await incubation_gateway.ensure_account(
                    db,
                    strategy,
                    source_run_id=snapshot.get("date"),
                    stage="candidate",
                )
                review_account_id = (
                    ((binding or {}).get("account") or {}).get("id")
                    or ((binding or {}).get("binding") or {}).get("account_id")
                )
                if review_account_id:
                    await self._call_optional_db_method(
                        db,
                        "update_paper_account_status",
                        review_account_id,
                        "active",
                        stage="candidate",
                        promotion_candidate=True,
                    )
            except Exception as exc:
                logger.warning("StrategyFactory: ensure live-ready paper account failed for %s: %s", strategy.get("id"), exc)

            try:
                runtime_control = await get_strategy_runtime_control_service().set_control(
                    db,
                    strategy,
                    control_mode="monitor",
                    source="strategy_factory_live_ready_review",
                    reason="live_candidate_ready_submission",
                    trigger_event_type="factory_live_ready_submission",
                    action_summary={
                        "submission_lane": "live_ready_review",
                        "direct_trade_candidate": bool(gate.get("live_candidate_ready")),
                    },
                    metadata={
                        "submission_lane": "live_ready_review",
                        "snapshot_date": snapshot.get("date"),
                        "admission_stage": gate.get("admission_stage"),
                        "incubation_pass_mode": gate.get("incubation_pass_mode"),
                    },
                    apply_runtime_changes=True,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: set live-ready runtime control failed for %s: %s", strategy.get("id"), exc)

            try:
                promotion_review = await get_strategy_promotion_pipeline_service().review(
                    db,
                    strategy,
                    source="strategy_factory_live_ready_review",
                    auto_apply=True,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: trigger live-ready promotion review failed for %s: %s", strategy.get("id"), exc)

            review_payload = dict((promotion_review or {}).get("review") or {})
            applied_transition = dict((promotion_review or {}).get("applied_transition") or {})
            applied_status = str(applied_transition.get("to") or "").strip().lower()
            action_audit: dict[str, Any] = {}
            if applied_status:
                action_audit["final_status"] = applied_status
                action_audit["pool_admission_applied"] = applied_status == "listed"
                action_audit["promotion_applied_transition"] = applied_transition
            if applied_status == "listed":
                action_audit.update(
                    {
                        "submission_action": {
                            "type": "pool_admission",
                            "trigger_reason": "live_candidate_ready_pool_admission",
                            "gaps": [],
                            "fallback_conditions": ["return_to_runtime_review_if_post_admission_controls_fail"],
                            "next_step": None,
                            "submission_lane": "live_ready_review",
                            "final_status": applied_status,
                            "completed": True,
                        },
                        "submission_action_type": "pool_admission",
                        "submission_action_trigger": "live_candidate_ready_pool_admission",
                        "submission_action_gaps": [],
                        "submission_action_fallback_conditions": [
                            "return_to_runtime_review_if_post_admission_controls_fail"
                        ],
                        "submission_action_next_step": None,
                        "submission_action_completed": True,
                    }
                )
            return {
                "live_review_ready": bool(review_account_id or runtime_control or review_payload),
                "paper_account_id": review_account_id,
                "live_review_account_id": review_account_id,
                "runtime_control_mode": (runtime_control or {}).get("control_mode"),
                "runtime_control_status": (runtime_control or {}).get("status"),
                "promotion_review_id": review_payload.get("id"),
                "promotion_review_status": review_payload.get("status"),
                "promotion_review_recommendation": review_payload.get("recommendation"),
                "promotion_review_score": review_payload.get("score"),
                **action_audit,
            }

        async def _handle_existing_refresh(
            self,
            strategy_id: str,
            name: str,
            candidate: dict,
            gate: dict,
            quality_report: dict,
            backtest_metrics: Optional[dict],
            snapshot: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
            *,
            existing_status: str,
            submission_lane: str,
            submission_action: Optional[dict[str, Any]] = None,
        ) -> dict:
            """复用已有策略时，仅刷新质量报告与实验留痕。"""
            self._apply_submission_action_audit(
                quality_report,
                final_status=existing_status,
                submission_lane=submission_lane,
                submission_audit=dict(submission_action or {}),
            )
            await self._record_experiment(
                db,
                candidate,
                strategy_id,
                name,
                snapshot,
                gate,
                "accepted" if gate.get("passed") else "rejected",
                validation_report,
                risk_report,
                quality_report,
                backtest_metrics,
                None,
            )
            return {
                "refreshed_existing": True,
                "reused_existing_strategy_id": strategy_id,
                "existing_status": existing_status,
                "submission_lane": submission_lane,
                "final_status": existing_status,
                **dict(submission_action or {}),
            }

        async def _handle_post_gate(
            self,
            strategy_id: str,
            name: str,
            candidate: dict,
            data: dict,
            gate: dict,
            quality_report: dict,
            backtest_metrics: Optional[dict],
            snapshot: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
            submission_lane: str,
            submission_action: Optional[dict[str, Any]] = None,
        ) -> dict:
            """质检通过后：创建孵化账户、运行孵化 pipeline、构建向量画像、记录实验。"""
            incubation_binding = None
            incubation_pipeline = None
            vector_profile = None
            vector_audit: dict = {}
            live_review_action: dict = {}
            paper_action: dict = {}
            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(incubation_budget.get("track") or "formal_incubation").strip().lower()
            final_status = "rejected"
            action_audit = dict(submission_action or {})

            if gate.get("passed"):
                enriched_data = {**data, "id": strategy_id, "name": name}
                if submission_lane == "formal_incubation":
                    final_status = "incubating"
                    incubation_gateway = self._get_incubation_gateway()
                    await _update_strategy_status(
                        db,
                        strategy_id,
                        "incubating",
                        actor_id="strategy_factory",
                        reason="quality_gate_provisional_passed" if gate.get("provisional_pass") else "quality_gate_passed",
                        metadata={
                            "quality_gate": gate,
                            "validation_grade": quality_report["summary"].get("validation_grade"),
                            "incubation_budget": incubation_budget,
                        },
                    )
                    try:
                        incubation_binding = await incubation_gateway.ensure_account(
                            db,
                            enriched_data,
                            source_run_id=snapshot.get("date"),
                        )
                    except Exception as exc:
                        logger.warning("StrategyFactory: ensure incubation account failed for %s: %s", strategy_id, exc)
                    try:
                        incubation_pipeline = await incubation_gateway.run_pipeline(
                            db,
                            {**enriched_data, "status": "incubating"},
                            source="strategy_factory_submit",
                            auto_apply_review=False,
                        )
                    except Exception as exc:
                        logger.warning("StrategyFactory: initial incubation pipeline failed for %s: %s", strategy_id, exc)
                    try:
                        vector_profile = await build_strategy_vector_profile(db, enriched_data)
                        vector_audit = dict((vector_profile or {}).get("metadata") or {}).get("audit") or {}
                    except Exception as exc:
                        logger.warning("StrategyFactory: build vector profile failed for %s: %s", strategy_id, exc)
                    self._apply_submission_action_audit(
                        quality_report,
                        final_status=final_status,
                        submission_lane=submission_lane,
                        submission_audit={
                            **action_audit,
                            "paper_account_id": ((incubation_binding or {}).get("account") or {}).get("id"),
                            "submission_action_completed": True,
                        },
                    )
                    action_audit = {**action_audit, "submission_action_completed": True}
                else:
                    final_status = "submitted"
                    if submission_lane == "live_ready_review":
                        queue_reason = "quality_gate_live_ready"
                    elif submission_lane == "observe_incubation":
                        queue_reason = "paper_observation_queue"
                    else:
                        queue_reason = "incubation_budget_deferred_queue"
                    await _update_strategy_status(
                        db,
                        strategy_id,
                        "submitted",
                        actor_id="strategy_factory",
                        reason=queue_reason,
                        metadata={
                            "quality_gate": gate,
                            "validation_grade": quality_report["summary"].get("validation_grade"),
                            "incubation_budget": incubation_budget,
                            "submission_lane": submission_lane,
                            "live_candidate_ready": bool(gate.get("live_candidate_ready")),
                        },
                    )
                    if submission_lane == "live_ready_review":
                        live_review_action = await self._enqueue_live_ready_review(
                            db,
                            {**enriched_data, "status": final_status},
                            snapshot,
                            gate,
                        )
                        final_status = str(live_review_action.get("final_status") or final_status)
                    elif submission_lane == "observe_incubation":
                        paper_action = await self._enqueue_paper_observation(
                            db,
                            {**enriched_data, "status": final_status},
                            snapshot,
                        )
                    self._apply_submission_action_audit(
                        quality_report,
                        final_status=final_status,
                        submission_lane=submission_lane,
                        submission_audit={
                            **action_audit,
                            **paper_action,
                            **live_review_action,
                            "submission_action_completed": bool(
                                live_review_action
                                or paper_action
                                or action_audit.get("submission_action_completed")
                            ),
                        },
                    )
                    action_audit = {
                        **action_audit,
                        **paper_action,
                        **live_review_action,
                        "submission_action_completed": bool(
                            live_review_action
                            or paper_action
                            or action_audit.get("submission_action_completed")
                        ),
                    }
                await self._record_experiment(
                    db,
                    candidate,
                    strategy_id,
                    name,
                    snapshot,
                    gate,
                    "accepted",
                    validation_report,
                    risk_report,
                    quality_report,
                    backtest_metrics,
                    incubation_pipeline,
                )
            else:
                final_status = str(action_audit.get("final_status") or "rejected")
                transition_reason = str(action_audit.get("submission_action_trigger") or "quality_gate_failed")
                await _update_strategy_status(
                    db,
                    strategy_id,
                    final_status,
                    actor_id="strategy_factory",
                    reason=transition_reason,
                    metadata={"quality_gate": gate, "validation_grade": quality_report["summary"].get("validation_grade")},
                )
                self._apply_submission_action_audit(
                    quality_report,
                    final_status=final_status,
                    submission_lane=submission_lane,
                    submission_audit=dict(action_audit or {}),
                )
                await self._record_experiment(
                    db,
                    candidate,
                    strategy_id,
                    name,
                    snapshot,
                    gate,
                    "rejected",
                    validation_report,
                    risk_report,
                    quality_report,
                    backtest_metrics,
                    None,
                )

            return {
                "incubation_account_id": ((incubation_binding or {}).get("account") or {}).get("id"),
                "incubation_pipeline_stage": ((incubation_pipeline or {}).get("snapshot") or {}).get("pipeline_stage"),
                "incubation_pipeline_status": ((incubation_pipeline or {}).get("snapshot") or {}).get("pipeline_status"),
                "incubation_readiness_score": ((incubation_pipeline or {}).get("snapshot") or {}).get("readiness_score"),
                "incubation_task_run_id": (incubation_pipeline or {}).get("task_run_id"),
                "incubation_budget_track": incubation_budget_track,
                "incubation_budget_rank": incubation_budget.get("rank"),
                "incubation_budget_priority_score": incubation_budget.get("priority_score"),
                "submission_lane": submission_lane,
                "vector_profile_id": (vector_profile or {}).get("id"),
                "vector_backend": (vector_profile or {}).get("backend"),
                "vector_backend_requested": (vector_audit or {}).get("backend_requested"),
                "vector_backend_used": (vector_audit or {}).get("backend_used"),
                "vector_fallback_used": (vector_audit or {}).get("fallback_used"),
                "vector_fallback_reason": (vector_audit or {}).get("fallback_reason"),
                "vector_latency_ms": (vector_audit or {}).get("latency_ms"),
                **paper_action,
                **live_review_action,
                **action_audit,
                "final_status": final_status,
            }

        @classmethod
        def _build_replay_candidate(
            cls,
            strategy: dict,
            *,
            latest_report: Optional[dict],
            backtest_metrics: Optional[dict],
        ) -> dict[str, Any]:
            payload = dict(strategy or {})
            params = dict(payload.get("params") or {})
            report = dict(latest_report or {})
            summary = dict(report.get("summary") or {})
            quality_gate = dict(report.get("quality_gate") or {})
            candidate = apply_resolved_candidate_envelope(
                {
                    **payload,
                    "id": payload.get("id"),
                    "name": payload.get("name"),
                    "strategy_type": payload.get("strategy_type"),
                    "params": params,
                    "spawn_reason": (
                        summary.get("spawn_reason")
                        or payload.get("spawn_reason")
                        or params.get("spawn_reason")
                    ),
                    "dedup_result": dict(
                        report.get("dedup_report")
                        or payload.get("dedup_result")
                        or params.get("dedup_result")
                        or {}
                    ),
                    "committee_review": dict(
                        report.get("committee_review")
                        or summary.get("committee_review")
                        or payload.get("committee_review")
                        or params.get("committee_review")
                        or {}
                    ),
                    "backtest_metrics": dict(backtest_metrics or report.get("backtest_metrics") or {}),
                }
            )
            incubation_budget = dict(
                candidate.get("incubation_budget")
                or params.get("incubation_budget")
                or summary.get("incubation_budget")
                or {}
            )
            summary_track = str(summary.get("incubation_budget_track") or "").strip()
            if summary_track and not incubation_budget.get("track"):
                incubation_budget["track"] = summary_track
            if summary.get("incubation_budget_rank") is not None and incubation_budget.get("rank") is None:
                incubation_budget["rank"] = summary.get("incubation_budget_rank")
            if (
                summary.get("incubation_budget_priority_score") is not None
                and incubation_budget.get("priority_score") is None
            ):
                incubation_budget["priority_score"] = summary.get("incubation_budget_priority_score")
            if (
                summary.get("incubation_budget_exploration_candidate") is not None
                and incubation_budget.get("exploration_candidate") is None
            ):
                incubation_budget["exploration_candidate"] = bool(
                    summary.get("incubation_budget_exploration_candidate")
                )
            if incubation_budget:
                candidate["incubation_budget"] = incubation_budget
            for field_name in _SEMANTIC_CONTRACT_FIELDS:
                value = candidate.get(field_name)
                if value in (None, "", [], {}):
                    value = params.get(field_name)
                if value in (None, "", [], {}):
                    value = summary.get(field_name)
                if value in (None, "", [], {}):
                    value = quality_gate.get(field_name)
                if value not in (None, "", [], {}):
                    candidate[field_name] = value
            return cls._ensure_runtime_playbook(candidate)

        async def replay_existing_submission(
            self,
            strategy: dict,
            snapshot: dict,
            db,
            *,
            validation_report: Optional[dict] = None,
            risk_report: Optional[dict] = None,
            backtest_metrics: Optional[dict] = None,
            latest_report: Optional[dict] = None,
        ) -> dict[str, Any]:
            strategy_payload = dict(strategy or {})
            strategy_id = str(strategy_payload.get("id") or "").strip()
            if not strategy_id:
                raise ValueError("strategy_id is required for replay_existing_submission")
            name = str(strategy_payload.get("name") or strategy_id).strip()
            report = dict(latest_report or {})
            metrics = dict(backtest_metrics or report.get("backtest_metrics") or {})
            candidate = self._build_replay_candidate(
                strategy_payload,
                latest_report=report,
                backtest_metrics=metrics,
            )
            semantic_audit: dict[str, Any] = {}
            if _semantic_contract_feature_enabled():
                candidate["confidence_contract"] = synthesize_confidence_contract(candidate)
                semantic_audit = audit_candidate_semantic_contract(candidate)
                candidate = _apply_candidate_semantic_contract(candidate, semantic_audit)
            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(
                incubation_budget.get("track")
                or dict(report.get("summary") or {}).get("incubation_budget_track")
                or "formal_incubation"
            ).strip().lower() or "formal_incubation"
            run_submission_quality_gate = get_compat_symbol(
                _LEGACY_SUBMISSION_GATE_MODULE,
                "run_submission_quality_gate",
                _local_run_submission_quality_gate,
            )
            gate = await run_submission_quality_gate(
                db,
                {**strategy_payload, "status": strategy_payload.get("status")},
                validation_report=validation_report,
                risk_report=risk_report,
                backtest_metrics={
                    **dict(metrics or {}),
                    "trade_count": metrics.get("trade_count"),
                    "trades_count": metrics.get("trades_count"),
                },
                incubation_budget_track=incubation_budget_track,
            )
            gate = self._apply_factory_submission_policy(
                candidate,
                name=name,
                gate=gate,
                backtest_metrics=metrics,
                refresh_existing=False,
            )
            if _semantic_contract_feature_enabled():
                gate = _apply_semantic_contract_gate(gate, semantic_audit)
            submission_action = self._resolve_submission_action_plan(
                gate,
                candidate=candidate,
                refresh_existing=False,
                existing_status=str(strategy_payload.get("status") or "submitted"),
                incubation_budget_track=incubation_budget_track,
            )
            submission_lane = str(submission_action.get("submission_lane") or "deferred_submission")
            final_status = str(submission_action.get("final_status") or strategy_payload.get("status") or "submitted")
            candidate = self._apply_runtime_bootstrap_contract(
                candidate,
                submission_lane=submission_lane,
                runtime_bootstrap_eligible=bool(submission_action.get("runtime_bootstrap_eligible")),
                runtime_bootstrap_budget_tier=str(submission_action.get("runtime_bootstrap_budget_tier") or "") or None,
            )
            strategy_payload = {
                **strategy_payload,
                "params": {
                    **dict(strategy_payload.get("params") or {}),
                    "runtime_playbook": dict(candidate.get("runtime_playbook") or {}),
                },
            }
            quality_report = self._build_quality_report(
                strategy_id=strategy_id,
                candidate=candidate,
                snapshot=snapshot,
                backtest_metrics=metrics,
                quality_gate=gate,
                validation_report=validation_report,
                risk_report=risk_report,
                final_status=final_status,
                submission_lane=submission_lane,
            )
            quality_report = _enrich_quality_report_v2(
                quality_report,
                candidate=candidate,
                gate=gate,
                final_status=final_status,
            )
            post_gate = await self._handle_post_gate(
                strategy_id,
                name,
                candidate,
                strategy_payload,
                gate,
                quality_report,
                metrics,
                snapshot,
                validation_report,
                risk_report,
                db,
                submission_lane=submission_lane,
                submission_action=submission_action,
            )
            final_status = str(post_gate.get("final_status") or final_status)
            submission_lane = str(post_gate.get("submission_lane") or submission_lane)
            if self._get_optional_db_method(db, "save_strategy_quality_report") is not None:
                await db.save_strategy_quality_report(strategy_id, "submission", quality_report)
            return {
                "strategy_id": strategy_id,
                "name": name,
                "status": final_status,
                "submission_lane": submission_lane,
                "incubation_budget_track": incubation_budget_track,
                "gate": dict(gate or {}),
                "quality_report": quality_report,
                **dict(post_gate or {}),
            }

        @classmethod
        async def _record_experiment(
            cls,
            db,
            candidate: dict,
            strategy_id: str,
            name: str,
            snapshot: dict,
            gate: dict,
            status: str,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            quality_report: Optional[dict],
            backtest_metrics: Optional[dict],
            incubation_pipeline: Optional[dict],
        ) -> None:
            """记录策略生成实验（通过/未通过共用）。"""
            experiment_id = candidate.get("experiment_id")
            if not experiment_id or not hasattr(db, "save_strategy_generation_experiment"):
                return

            def _assign_if_present(target: dict, key: str, value) -> None:
                if value not in (None, [], {}, ""):
                    target[key] = value

            try:
                existing = await db.get_strategy_generation_experiment(experiment_id) if hasattr(db, "get_strategy_generation_experiment") else None
                existing = dict(existing or {})
                existing_spec = dict(existing.get("strategy_spec") or {})
                existing_evaluation = dict(existing.get("evaluation") or {})
                existing_result = dict(existing.get("result") or {})
                candidate_provenance = cls._candidate_provenance(candidate)
                quality_payload = dict(quality_report or {})
                backtest_payload = dict(backtest_metrics or {})
                event_window_config = dict(
                    quality_payload.get("event_window_config")
                    or backtest_payload.get("event_window_config")
                    or {}
                )
                event_window_metrics = dict(
                    quality_payload.get("event_window_metrics")
                    or backtest_payload.get("event_window_metrics")
                    or {}
                )
                cost_assumptions = dict(
                    quality_payload.get("cost_assumptions")
                    or backtest_payload.get("cost_assumptions")
                    or {}
                )
                backtest_assumptions = dict(
                    quality_payload.get("backtest_assumptions")
                    or backtest_payload.get("backtest_assumptions")
                    or {}
                )
                execution_reality = dict(quality_payload.get("execution_reality") or {})
                quality_summary = dict(quality_payload.get("summary") or {})

                research_task = _normalize_research_task_contract(
                    dict(candidate.get("research_task") or {})
                    or dict(existing_spec.get("research_task") or {})
                    or dict(existing_evaluation.get("research_task") or {})
                )
                contract_snapshot = dict(candidate.get("candidate_contract_snapshot") or {})
                try:
                    contract_snapshot = build_portfolio_candidate_contract(
                        {
                            **dict(candidate or {}),
                            "research_task": research_task,
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "StrategySubmitter: rebuild candidate contract snapshot failed for %s: %s",
                        strategy_id,
                        exc,
                    )
                    if research_task:
                        contract_snapshot = {
                            **contract_snapshot,
                            "research_task": research_task,
                        }
                candidate_lineage_contract = dict(
                    candidate.get("candidate_lineage_contract")
                    or contract_snapshot.get("lineage")
                    or {}
                )
                event_context = (
                    dict(candidate.get("event_context") or {})
                    or _extract_event_context(research_task)
                    or dict(existing_spec.get("event_context") or {})
                    or dict(existing_evaluation.get("event_context") or {})
                )
                parameters = {
                    **dict(existing.get("parameters") or {}),
                    **dict(candidate.get("params") or {}),
                }
                _assign_if_present(parameters, "target_symbols", list(candidate.get("target_symbols") or parameters.get("target_symbols") or []))
                _assign_if_present(parameters, "stock_pool", dict(candidate.get("stock_pool") or parameters.get("stock_pool") or {}))
                _assign_if_present(parameters, "research_task", research_task)
                _assign_if_present(parameters, "event_context", event_context)
                _assign_if_present(parameters, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(parameters, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(parameters, "candidate_provenance", candidate_provenance)
                _assign_if_present(parameters, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(parameters, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(parameters, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(parameters, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(parameters, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(parameters, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(parameters, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(parameters, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(parameters, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(parameters, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(parameters, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(parameters, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(parameters, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(parameters, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(parameters, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(parameters, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(parameters, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(parameters, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(parameters, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(parameters, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(parameters, field_name, candidate.get(field_name))

                strategy_spec = dict(existing_spec)
                _assign_if_present(strategy_spec, "strategy_type", candidate.get("strategy_type"))
                _assign_if_present(strategy_spec, "name", name)
                _assign_if_present(strategy_spec, "params", candidate.get("params") or existing_spec.get("params"))
                _assign_if_present(strategy_spec, "target_symbols", list(candidate.get("target_symbols") or existing_spec.get("target_symbols") or []))
                _assign_if_present(strategy_spec, "stock_pool", dict(candidate.get("stock_pool") or existing_spec.get("stock_pool") or {}))
                _assign_if_present(strategy_spec, "selection_logic", list(candidate.get("selection_logic") or existing_spec.get("selection_logic") or []))
                _assign_if_present(strategy_spec, "research_scope", dict(candidate.get("research_scope") or existing_spec.get("research_scope") or {}))
                _assign_if_present(strategy_spec, "research_task", research_task)
                _assign_if_present(strategy_spec, "event_context", event_context)
                _assign_if_present(strategy_spec, "candidate_provenance", candidate_provenance)
                _assign_if_present(strategy_spec, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(strategy_spec, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(strategy_spec, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(strategy_spec, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(strategy_spec, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(strategy_spec, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(strategy_spec, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(strategy_spec, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(strategy_spec, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(strategy_spec, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(strategy_spec, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(strategy_spec, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(strategy_spec, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(strategy_spec, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(strategy_spec, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(strategy_spec, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(strategy_spec, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(strategy_spec, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(strategy_spec, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(strategy_spec, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(strategy_spec, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(strategy_spec, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(strategy_spec, field_name, candidate.get(field_name))

                evaluation = dict(existing_evaluation)
                _assign_if_present(evaluation, "generation_reason", candidate.get("generation_reason") or existing_evaluation.get("generation_reason"))
                _assign_if_present(evaluation, "llm_prompt", candidate.get("llm_prompt") or existing_evaluation.get("llm_prompt"))
                _assign_if_present(evaluation, "llm_response", candidate.get("llm_response") or existing_evaluation.get("llm_response"))
                _assign_if_present(evaluation, "target_symbols", list(candidate.get("target_symbols") or strategy_spec.get("target_symbols") or []))
                _assign_if_present(evaluation, "stock_pool", dict(candidate.get("stock_pool") or strategy_spec.get("stock_pool") or {}))
                _assign_if_present(evaluation, "selection_logic", list(candidate.get("selection_logic") or strategy_spec.get("selection_logic") or []))
                _assign_if_present(evaluation, "research_scope", dict(candidate.get("research_scope") or strategy_spec.get("research_scope") or {}))
                _assign_if_present(evaluation, "research_task", research_task)
                _assign_if_present(evaluation, "event_context", event_context)
                _assign_if_present(evaluation, "candidate_provenance", candidate_provenance)
                _assign_if_present(evaluation, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(evaluation, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(evaluation, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(evaluation, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(evaluation, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(evaluation, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(evaluation, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(evaluation, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(evaluation, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(evaluation, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(evaluation, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(evaluation, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(evaluation, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(evaluation, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(evaluation, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(evaluation, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(evaluation, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(evaluation, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(evaluation, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(evaluation, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(evaluation, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(evaluation, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(evaluation, field_name, candidate.get(field_name))
                evaluation["quality_gate"] = gate
                if validation_report is not None or "validation_report" not in evaluation:
                    evaluation["validation_report"] = validation_report or {}
                if risk_report is not None or "risk_report" not in evaluation:
                    evaluation["risk_report"] = risk_report or {}
                _assign_if_present(evaluation, "quality_summary", quality_summary)
                _assign_if_present(evaluation, "backtest_metrics", backtest_payload)
                _assign_if_present(evaluation, "event_window_config", event_window_config)
                _assign_if_present(evaluation, "event_window_metrics", event_window_metrics)
                _assign_if_present(evaluation, "position_assumption", quality_payload.get("position_assumption") or backtest_payload.get("position_assumption"))
                _assign_if_present(evaluation, "cost_assumptions", cost_assumptions)
                _assign_if_present(evaluation, "backtest_assumptions", backtest_assumptions)
                _assign_if_present(evaluation, "execution_reality", execution_reality)
                _assign_if_present(evaluation, "constraint_check", quality_payload.get("constraint_check") or backtest_payload.get("constraint_check"))
                _assign_if_present(evaluation, "admission_stage", gate.get("admission_stage"))
                _assign_if_present(evaluation, "incubation_pass_mode", gate.get("incubation_pass_mode"))
                _assign_if_present(
                    evaluation,
                    "submission_lane",
                    quality_payload.get("submission_lane") or quality_summary.get("submission_lane"),
                )
                evaluation["research_candidate_ready"] = bool(gate.get("research_candidate_ready"))
                evaluation["incubation_candidate_ready"] = bool(gate.get("incubation_candidate_ready"))
                evaluation["live_candidate_ready"] = bool(gate.get("live_candidate_ready"))
                evaluation["direct_trade_candidate"] = bool(
                    quality_payload.get("direct_trade_candidate") or quality_summary.get("direct_trade_candidate")
                )
                evaluation["admission_block_reasons"] = list(gate.get("admission_block_reasons") or [])
                evaluation["admission_evaluations"] = dict(gate.get("admission_evaluations") or {})

                result = dict(existing_result)
                result.update({"strategy_id": strategy_id, "generated_strategy_id": strategy_id, "status": status})
                _assign_if_present(result, "candidate_provenance", candidate_provenance)
                _assign_if_present(result, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(result, "candidate_family", candidate_provenance.get("candidate_family"))
                _assign_if_present(result, "strategy_profile", candidate_provenance.get("strategy_profile"))
                _assign_if_present(result, "candidate_family_id", candidate_provenance.get("candidate_family_id"))
                _assign_if_present(result, "holding_period_bucket", candidate_provenance.get("holding_period_bucket"))
                _assign_if_present(result, "alpha_source", candidate_provenance.get("alpha_source"))
                _assign_if_present(result, "risk_level", candidate_provenance.get("risk_level"))
                _assign_if_present(result, "regime_fit", candidate_provenance.get("regime_fit"))
                _assign_if_present(result, "generator_mode", candidate_provenance.get("generator_mode"))
                _assign_if_present(result, "direction_bias", candidate_provenance.get("direction_bias"))
                _assign_if_present(result, "validation_profile_name", candidate_provenance.get("validation_profile"))
                _assign_if_present(result, "target_symbol_count", candidate_provenance.get("target_symbol_count"))
                _assign_if_present(result, "candidate_contract_hash", candidate.get("candidate_contract_hash"))
                _assign_if_present(result, "execution_contract_hash", candidate.get("execution_contract_hash"))
                _assign_if_present(result, "tested_object_hash", candidate.get("tested_object_hash"))
                _assign_if_present(result, "candidate_identity_signature", candidate.get("candidate_identity_signature"))
                _assign_if_present(result, "candidate_contract_snapshot", contract_snapshot)
                _assign_if_present(result, "candidate_lineage_contract", candidate_lineage_contract)
                _assign_if_present(result, "logic_signature", candidate.get("logic_signature"))
                _assign_if_present(result, "dsl_signature", candidate.get("dsl_signature"))
                _assign_if_present(result, "factor_signature", candidate.get("factor_signature"))
                _assign_if_present(result, "entry_exit_signature", candidate.get("entry_exit_signature"))
                for field_name in _SEMANTIC_CONTRACT_FIELDS:
                    _assign_if_present(result, field_name, candidate.get(field_name))
                _assign_if_present(result, "quality_summary", quality_summary)
                _assign_if_present(result, "backtest_metrics", backtest_payload)
                _assign_if_present(result, "event_window_config", event_window_config)
                _assign_if_present(result, "event_window_metrics", event_window_metrics)
                _assign_if_present(result, "position_assumption", quality_payload.get("position_assumption") or backtest_payload.get("position_assumption"))
                _assign_if_present(result, "cost_assumptions", cost_assumptions)
                _assign_if_present(result, "backtest_assumptions", backtest_assumptions)
                _assign_if_present(result, "execution_reality", execution_reality)
                _assign_if_present(result, "constraint_check", quality_payload.get("constraint_check") or backtest_payload.get("constraint_check"))
                _assign_if_present(result, "admission_stage", gate.get("admission_stage"))
                _assign_if_present(result, "incubation_pass_mode", gate.get("incubation_pass_mode"))
                _assign_if_present(
                    result,
                    "submission_lane",
                    quality_payload.get("submission_lane") or quality_summary.get("submission_lane"),
                )
                result["research_candidate_ready"] = bool(gate.get("research_candidate_ready"))
                result["incubation_candidate_ready"] = bool(gate.get("incubation_candidate_ready"))
                result["live_candidate_ready"] = bool(gate.get("live_candidate_ready"))
                result["direct_trade_candidate"] = bool(
                    quality_payload.get("direct_trade_candidate") or quality_summary.get("direct_trade_candidate")
                )
                result["admission_block_reasons"] = list(gate.get("admission_block_reasons") or [])
                result["admission_evaluations"] = dict(gate.get("admission_evaluations") or {})
                if incubation_pipeline:
                    evaluation["incubation_pipeline"] = (incubation_pipeline or {}).get("snapshot") or {}
                    result["incubation_pipeline"] = (incubation_pipeline or {}).get("snapshot") or {}

                parent_strategy_id = existing.get("parent_strategy_id") or candidate.get("parent_strategy_id")
                experiment_strategy_id = existing.get("strategy_id") or parent_strategy_id or strategy_id
                prompt_payload = existing.get("prompt") or (str(candidate.get("llm_prompt")) if candidate.get("llm_prompt") else str(snapshot.get("date") or ""))

                await db.save_strategy_generation_experiment(
                    {
                        **existing,
                        "experiment_id": experiment_id,
                        "strategy_id": experiment_strategy_id,
                        "parent_strategy_id": parent_strategy_id,
                        "generated_strategy_id": strategy_id,
                        "task_run_id": candidate.get("task_run_id") or existing.get("task_run_id"),
                        "source": candidate.get("source") or existing.get("source") or "strategy_factory",
                        "generator_type": candidate.get("generator_type") or existing.get("generator_type") or "rule",
                        "optimizer_type": candidate.get("optimizer_type") or existing.get("optimizer_type"),
                        "status": status,
                        "hypothesis": candidate.get("spawn_reason") or existing.get("hypothesis"),
                        "prompt": prompt_payload,
                        "parameters": parameters,
                        "strategy_spec": strategy_spec,
                        "evaluation": evaluation,
                        "result": result,
                        "parent_experiment_id": existing.get("parent_experiment_id"),
                        "artifact_id": existing.get("artifact_id"),
                    }
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: record experiment failed for %s: %s", strategy_id, exc)
