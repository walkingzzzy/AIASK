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
)
from .legacy_bridge import call_compat_async, get_compat_symbol, get_compat_value
from .incubation_budgeter import IncubationBudgeter
from .quality_gates import build_completed_gate_3_report
from .quality_reporting import build_quality_report, normalize_quality_gate_result
from .submission_gate import run_submission_quality_gate as _local_run_submission_quality_gate
from .utils import (
    _auto_name as _local_auto_name,
    _extract_event_context as _local_extract_event_context,
    _update_strategy_status as _local_update_strategy_status,
    get_strategy_factory_package as _local_get_strategy_factory_package,
)
from ..domain.constants import (
    FACTORY_SUBMISSION_MIN_BACKTEST_TRADES,
    FACTORY_SUBMISSION_MIN_EVENT_TARGET_COVERAGE,
    FACTORY_SUBMISSION_REJECT_GENERIC_AI_NAMES,
    FACTORY_SUBMISSION_REQUIRE_STRICT_PASS_FOR_REFRESH,
    FACTORY_SUBMISSION_REQUIRE_TASK_PREFERENCE_MATCH,
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

def _compat_setting(name: str, default):
    return get_compat_value(_LEGACY_SUBMITTER_MODULE, name, default)


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
                if gate_3.get("passed"):
                    gate_3_passed += 1
                    if gate_3.get("provisional_pass"):
                        gate_3_provisional_passed += 1
                else:
                    gate_3_failed += 1
                    for code in gate_3.get("reason_codes") or []:
                        normalized = str(code or "").strip()
                        if normalized:
                            gate_3_failure_codes[normalized] += 1
                submitted_items.append(result["summary"])

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
                "quality_gate": gate_report,
                "gate_report": gate_report,
                "incubation_budget_summary": incubation_budget_summary,
                "strategies": submitted_items,
            }

        async def _submit_one(self, candidate: dict, snapshot: dict, db) -> dict:
            """处理单个候选策略的完整提交流程。"""
            candidate = apply_resolved_candidate_envelope(candidate)
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
                }
            )
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
            gate = self._apply_factory_submission_policy(
                candidate,
                name=name,
                gate=gate,
                backtest_metrics=metrics,
                refresh_existing=refresh_existing,
            )
            candidate_provenance = self._candidate_provenance(candidate, existing_strategy)
            strategy_profile = dict(candidate_provenance.get("strategy_profile") or {})
            incubation_budget = dict(candidate.get("incubation_budget") or {})
            incubation_budget_track = str(incubation_budget.get("track") or "formal_incubation").strip().lower()

            submission_action = self._resolve_submission_action_plan(
                gate,
                refresh_existing=refresh_existing,
                existing_status=existing_status,
                incubation_budget_track=incubation_budget_track,
            )
            submission_lane = str(submission_action.get("submission_lane") or "deferred_submission")
            final_status = str(submission_action.get("final_status") or "submitted")
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

            summary = {
                "strategy_id": strategy_id,
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
                "submission_lane": submission_lane,
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
                "validation_profile": dict(candidate.get("validation_profile") or existing_params.get("validation_profile") or {}),
                "targeting_policy": dict(candidate.get("targeting_policy") or existing_params.get("targeting_policy") or {}),
                "constraint_check": dict(candidate.get("constraint_check") or existing_params.get("constraint_check") or {}),
                "task_signature": _build_task_signature(normalized_task),
            }
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
        def _resolve_submission_action_plan(
            gate: dict,
            *,
            refresh_existing: bool,
            existing_status: str,
            incubation_budget_track: str,
        ) -> dict[str, Any]:
            normalized_gate = dict(gate or {})
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
            if refresh_existing:
                action_type = "refresh_existing"
                submission_lane = "refresh_existing"
                final_status = str(existing_status or "draft")
                trigger = "existing_strategy_refresh"
                gaps = []
                fallback_conditions = ["manual_review_if_contract_changes"]
                next_step = "existing_status_preserved"
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
            elif bool(normalized_gate.get("live_candidate_ready")):
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
            elif bool(normalized_gate.get("research_only_due_to_trade_audit_gap")) or not bool(normalized_gate.get("incubation_candidate_ready")):
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted" if bool(normalized_gate.get("research_candidate_ready")) else "rejected"
                trigger = (
                    "research_only_due_to_trade_audit_gap"
                    if bool(normalized_gate.get("research_only_due_to_trade_audit_gap"))
                    else "incubation_admission_not_ready"
                )
                gaps = admission_block_reasons
                fallback_conditions = ["promote_after_trade_audit_completed"]
                next_step = "research"
                completed = True
            elif str(incubation_budget_track or "").strip().lower() == "formal_incubation":
                action_type = "incubation"
                submission_lane = "formal_incubation"
                final_status = "incubating"
                trigger = "strict_incubation_ready_and_budget_formal"
                gaps = admission_block_reasons
                fallback_conditions = [
                    "downgrade_to_paper_if_incubation_readiness_drops",
                    "return_to_research_if_runtime_risk_accumulates",
                ]
                next_step = "paper"
                completed = False
            elif str(incubation_budget_track or "").strip().lower() == "observe_incubation":
                action_type = "paper"
                submission_lane = "observe_incubation"
                final_status = "submitted"
                trigger = "observe_track_paper_route"
                gaps = admission_block_reasons
                fallback_conditions = [
                    "return_to_research_if_paper_fill_quality_weak",
                    "promote_to_runtime_review_after_paper_pass",
                ]
                next_step = "runtime_review"
                completed = False
            else:
                action_type = "research_only"
                submission_lane = "deferred_submission"
                final_status = "submitted"
                trigger = "budget_deferred_research_only"
                gaps = admission_block_reasons
                fallback_conditions = ["promote_to_incubation_after_budget_released"]
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
            }

        @classmethod
        def _resolve_submission_lane(
            cls,
            gate: dict,
            *,
            refresh_existing: bool,
            existing_status: str,
            incubation_budget_track: str,
        ) -> tuple[str, str]:
            plan = cls._resolve_submission_action_plan(
                gate,
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
                        observation_candidate=True,
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
                await _update_strategy_status(
                    db,
                    strategy_id,
                    "rejected",
                    actor_id="strategy_factory",
                    reason="quality_gate_failed",
                    metadata={"quality_gate": gate, "validation_grade": quality_report["summary"].get("validation_grade")},
                )
                final_status = "rejected"
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
