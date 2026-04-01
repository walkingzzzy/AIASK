"""策略工厂候选提交。"""

from __future__ import annotations

import asyncio
import logging
import re
import time as _time
from collections import Counter
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import uuid4

from .legacy_bridge import call_compat_async, get_compat_symbol, get_compat_value
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
from ..infrastructure.mcp_services import build_strategy_vector_profile

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
            refreshed = 0
            submitted = 0
            passed = 0
            gate_3_passed = 0
            gate_3_failed = 0
            gate_3_provisional_passed = 0
            gate_3_failure_codes: Counter[str] = Counter()
            submitted_items: List[dict] = []
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
                if result.get("created", True):
                    created += 1
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
                "refreshed": refreshed,
                "submitted": submitted,
                "passed_quality_gate": passed,
                "gate_3_passed": gate_3_passed,
                "gate_3_failed": gate_3_failed,
                "gate_3_provisional_passed": gate_3_provisional_passed,
                "gate_3_failure_reason_topn": gate_report["gate_3"]["failure_reason_topn"],
                "quality_gate": gate_report,
                "gate_report": gate_report,
                "strategies": submitted_items,
            }

        async def _submit_one(self, candidate: dict, snapshot: dict, db) -> dict:
            """处理单个候选策略的完整提交流程。"""
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
            )
            gate = self._apply_factory_submission_policy(
                candidate,
                name=name,
                gate=gate,
                backtest_metrics=metrics,
                refresh_existing=refresh_existing,
            )
            candidate_provenance = self._candidate_provenance(candidate, existing_strategy)

            final_status = existing_status if refresh_existing else ("incubating" if gate.get("passed") else "rejected")
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
            )
            if hasattr(db, "save_strategy_quality_report"):
                await db.save_strategy_quality_report(strategy_id, "submission", quality_report)

            if refresh_existing:
                post_gate = await self._handle_existing_refresh(
                    strategy_id,
                    name,
                    candidate,
                    gate,
                    snapshot,
                    validation_report,
                    risk_report,
                    db,
                    existing_status=existing_status,
                )
            else:
                post_gate = await self._handle_post_gate(
                    strategy_id,
                    name,
                    candidate,
                    data,
                    gate,
                    quality_report,
                    snapshot,
                    validation_report,
                    risk_report,
                    db,
                )

                try:
                    parent_strategy_id = (
                        str((candidate.get("dedup_result") or {}).get("parent_strategy_id") or "").strip()
                        or str(candidate.get("parent_strategy_id") or "").strip()
                        or None
                    )
                    await db.save_strategy_lineage(strategy_id, parent_strategy_id, candidate.get("spawn_reason", ""), snapshot)
                except Exception as exc:
                    logger.warning("StrategySubmitter: save lineage failed for %s: %s", strategy_id, exc)

            summary = {
                "strategy_id": strategy_id,
                "experiment_id": candidate.get("experiment_id"),
                "generator_type": candidate.get("generator_type"),
                "name": name,
                "status": final_status,
                "passed": bool(gate.get("passed")),
                "passed_strict": bool(gate.get("passed_strict", gate.get("passed"))),
                "provisional_pass": bool(gate.get("provisional_pass")),
                "reasons": gate.get("reasons") or [],
                "reason_codes": gate.get("reason_codes") or [],
                "warning_codes": gate.get("warning_codes") or [],
                "gate_3": dict(gate or {}),
                "dedup_result": candidate.get("dedup_result") or {},
                "refresh_mode": (candidate.get("dedup_result") or {}).get("refresh_mode"),
                "constraint_check": dict(candidate.get("constraint_check") or {}),
                "validation_profile": dict(candidate.get("validation_profile") or {}),
                "primary_validation_layer": gate.get("primary_validation_layer"),
                "event_window_config": dict(metrics.get("event_window_config") or {}),
                "position_assumption": metrics.get("position_assumption"),
                "cost_assumptions": dict(metrics.get("cost_assumptions") or {}),
                "explicit_cost_breakdown": dict(metrics.get("explicit_cost_breakdown") or {}),
                "implicit_cost_breakdown": dict(metrics.get("implicit_cost_breakdown") or {}),
                "backtest_assumptions": dict(metrics.get("backtest_assumptions") or {}),
                "attempt_adjustment": dict(gate.get("attempt_adjustment") or {}),
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
                "task_preference": dict(gate.get("task_preference") or {}),
                "task_signature": _build_task_signature(candidate.get("research_task") or {}),
                "candidate_provenance": candidate_provenance,
                "source_candidate_artifact_id": candidate_provenance.get("source_candidate_artifact_id"),
                "source_generation_artifact_id": candidate_provenance.get("source_generation_artifact_id"),
                "source_validation_artifact_id": candidate_provenance.get("source_validation_artifact_id"),
                "candidate_memory_record_id": candidate_provenance.get("memory_record_id"),
                "candidate_family": candidate_provenance.get("candidate_family"),
                "candidate_registry_stage": candidate_provenance.get("candidate_registry_stage"),
                "candidate_validation_score": candidate_provenance.get("validation_score"),
                "expected_regime": list(candidate_provenance.get("expected_regime") or []),
                "expected_holding_period": candidate_provenance.get("expected_holding_period"),
                "candidate_latest_validation_at": candidate_provenance.get("latest_validation_at"),
                "candidate_latest_validation_age_days": candidate_provenance.get("latest_validation_age_days"),
                **post_gate,
            }
            return {
                "created": not refresh_existing,
                "refreshed_existing": refresh_existing,
                "submitted": True,
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
        def _build_strategy_data(
            cls,
            strategy_id: str,
            name: str,
            candidate: dict,
            metrics: dict,
            existing: Optional[dict] = None,
        ) -> dict:
            """构建策略记录数据。"""
            existing = dict(existing or {})
            description = f"{name}\n生成原因: {candidate.get('spawn_reason', '')}"
            if metrics:
                description += f"\n回测: Sharpe {metrics.get('sharpe_ratio', 0):.2f} | "
                description += f"收益 {metrics.get('total_return', 0):.1%} | "
                description += f"回撤 {metrics.get('max_drawdown', 0):.1%}"

            existing_params = dict(existing.get("params") or {})
            normalized_task = _normalize_research_task_contract(candidate.get("research_task") or existing_params.get("research_task") or {})
            candidate_provenance = cls._candidate_provenance(candidate, existing)
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
                if candidate_provenance.get("candidate_family"):
                    stored_params["candidate_family"] = candidate_provenance.get("candidate_family")
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
            validation_report = None
            try:
                validation_report = await self._get_validation_gateway().run_validation_report(
                    candidate["strategy_type"],
                    candidate.get("params", {}),
                    db,
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: validation report failed for %s: %s", candidate.get("strategy_type"), exc)

            risk_report = None
            try:
                risk_report = await self._get_risk_gateway().run_risk_report(
                    candidate["strategy_type"],
                    candidate.get("params", {}),
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

        async def _handle_existing_refresh(
            self,
            strategy_id: str,
            name: str,
            candidate: dict,
            gate: dict,
            snapshot: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
            *,
            existing_status: str,
        ) -> dict:
            """复用已有策略时，仅刷新质量报告与实验留痕。"""
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
                None,
            )
            return {
                "refreshed_existing": True,
                "reused_existing_strategy_id": strategy_id,
                "existing_status": existing_status,
            }

        async def _handle_post_gate(
            self,
            strategy_id: str,
            name: str,
            candidate: dict,
            data: dict,
            gate: dict,
            quality_report: dict,
            snapshot: dict,
            validation_report: Optional[dict],
            risk_report: Optional[dict],
            db,
        ) -> dict:
            """质检通过后：创建孵化账户、运行孵化 pipeline、构建向量画像、记录实验。"""
            incubation_binding = None
            incubation_pipeline = None
            vector_profile = None
            vector_audit: dict = {}

            if gate.get("passed"):
                incubation_gateway = self._get_incubation_gateway()
                await _update_strategy_status(
                    db,
                    strategy_id,
                    "incubating",
                    actor_id="strategy_factory",
                    reason="quality_gate_provisional_passed" if gate.get("provisional_pass") else "quality_gate_passed",
                    metadata={"quality_gate": gate, "validation_grade": quality_report["summary"].get("validation_grade")},
                )
                enriched_data = {**data, "id": strategy_id, "name": name}
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
                    None,
                )

            return {
                "incubation_account_id": ((incubation_binding or {}).get("account") or {}).get("id"),
                "incubation_pipeline_stage": ((incubation_pipeline or {}).get("snapshot") or {}).get("pipeline_stage"),
                "incubation_pipeline_status": ((incubation_pipeline or {}).get("snapshot") or {}).get("pipeline_status"),
                "incubation_readiness_score": ((incubation_pipeline or {}).get("snapshot") or {}).get("readiness_score"),
                "incubation_task_run_id": (incubation_pipeline or {}).get("task_run_id"),
                "vector_profile_id": (vector_profile or {}).get("id"),
                "vector_backend": (vector_profile or {}).get("backend"),
                "vector_backend_requested": (vector_audit or {}).get("backend_requested"),
                "vector_backend_used": (vector_audit or {}).get("backend_used"),
                "vector_fallback_used": (vector_audit or {}).get("fallback_used"),
                "vector_fallback_reason": (vector_audit or {}).get("fallback_reason"),
                "vector_latency_ms": (vector_audit or {}).get("latency_ms"),
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

                research_task = (
                    dict(candidate.get("research_task") or {})
                    or dict(existing_spec.get("research_task") or {})
                    or dict(existing_evaluation.get("research_task") or {})
                )
                event_context = (
                    dict(candidate.get("event_context") or {})
                    or _extract_event_context(research_task)
                    or dict(existing_spec.get("event_context") or {})
                    or dict(existing_evaluation.get("event_context") or {})
                )

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
                evaluation["quality_gate"] = gate
                if validation_report is not None or "validation_report" not in evaluation:
                    evaluation["validation_report"] = validation_report or {}
                if risk_report is not None or "risk_report" not in evaluation:
                    evaluation["risk_report"] = risk_report or {}

                result = dict(existing_result)
                result.update({"strategy_id": strategy_id, "generated_strategy_id": strategy_id, "status": status})
                _assign_if_present(result, "candidate_provenance", candidate_provenance)
                _assign_if_present(result, "source_candidate_artifact_id", candidate_provenance.get("source_candidate_artifact_id"))
                _assign_if_present(result, "candidate_family", candidate_provenance.get("candidate_family"))
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
                        "parameters": candidate.get("params") or existing.get("parameters") or {},
                        "strategy_spec": strategy_spec,
                        "evaluation": evaluation,
                        "result": result,
                        "parent_experiment_id": existing.get("parent_experiment_id"),
                        "artifact_id": existing.get("artifact_id"),
                    }
                )
            except Exception as exc:
                logger.warning("StrategySubmitter: record experiment failed for %s: %s", strategy_id, exc)
