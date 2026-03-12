"""策略工厂候选提交。"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import List, Optional
from uuid import uuid4

from .constants import SUBMIT_CONCURRENCY
from .utils import _auto_name, _extract_event_context, _update_strategy_status, get_strategy_factory_package

logger = logging.getLogger(__name__)


class StrategySubmitter:
    """创建策略记录并提交质检。"""

    @staticmethod
    def _build_quality_report(
        strategy_id: str,
        candidate: dict,
        snapshot: dict,
        backtest_metrics: dict,
        quality_gate: dict,
        validation_report: Optional[dict],
        risk_report: Optional[dict],
        final_status: str,
    ) -> dict:
        from ...tools.managers.strategy_manager import _build_quality_report

        return _build_quality_report(
            strategy_id=strategy_id,
            strategy_type=candidate.get("strategy_type"),
            quality_gate=quality_gate,
            validation_report=validation_report,
            risk_report=risk_report,
            dedup_report=candidate.get("dedup_result") or {},
            backtest_metrics=backtest_metrics or {},
            snapshot={
                "date": snapshot.get("date"),
                "fg_level": snapshot.get("fg_level"),
                "fear_greed_index": snapshot.get("fear_greed_index"),
            },
            status_after_review=final_status,
            review_source="strategy_factory_submit",
            report_type="submission",
            spawn_reason=candidate.get("spawn_reason"),
        )

    async def submit(self, candidates: List[dict], snapshot: dict, db) -> dict:
        """批量提交候选策略，每个策略独立处理，单个失败不影响其他。"""
        created = 0
        refreshed = 0
        submitted = 0
        passed = 0
        submitted_items: List[dict] = []
        sem = asyncio.Semaphore(SUBMIT_CONCURRENCY)

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
            submitted_items.append(result["summary"])

        return {
            "created": created,
            "refreshed": refreshed,
            "submitted": submitted,
            "passed_quality_gate": passed,
            "strategies": submitted_items,
        }

    async def _submit_one(self, candidate: dict, snapshot: dict, db) -> dict:
        """处理单个候选策略的完整提交流程。"""
        from ...tools.managers.strategy_manager import (
            _maybe_grant_provisional_incubation,
            _normalize_quality_gate_result,
            _run_quality_gate,
        )

        existing_strategy = await self._resolve_existing_strategy(candidate, db)
        refresh_existing = existing_strategy is not None
        existing_status = str((existing_strategy or {}).get("status") or "draft")
        strategy_id = str((existing_strategy or {}).get("id") or f"factory_{int(_time.time())}_{uuid4().hex[:8]}")
        name = str((existing_strategy or {}).get("name") or _auto_name(candidate["strategy_type"], candidate["params"]))
        metrics = candidate.get("backtest_metrics", {})
        data = self._build_strategy_data(strategy_id, name, candidate, metrics, existing=existing_strategy)
        await db.save_strategy(data)

        validation_report, risk_report = await self._save_metrics(strategy_id, candidate, metrics, db)

        if not refresh_existing:
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
        gate = await _run_quality_gate(db, {**data, "status": existing_status if refresh_existing else "submitted"})
        gate = _maybe_grant_provisional_incubation(
            data,
            gate,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics={
                **dict(metrics or {}),
                "trade_count": metrics.get("trade_count"),
                "trades_count": metrics.get("trades_count"),
            },
        )

        final_status = existing_status if refresh_existing else ("incubating" if gate.get("passed") else "rejected")
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
                await db.save_strategy_lineage(strategy_id, None, candidate.get("spawn_reason", ""), snapshot)
            except Exception as exc:
                logger.warning("StrategySubmitter: save lineage failed for %s: %s", strategy_id, exc)

        summary = {
            "strategy_id": strategy_id,
            "experiment_id": candidate.get("experiment_id"),
            "generator_type": candidate.get("generator_type"),
            "name": name,
            "status": final_status,
            "passed": bool(gate.get("passed")),
            "reasons": gate.get("reasons") or [],
            "dedup_result": candidate.get("dedup_result") or {},
            **post_gate,
        }
        return {
            "created": not refresh_existing,
            "refreshed_existing": refresh_existing,
            "submitted": True,
            "passed": bool(gate.get("passed")),
            "summary": summary,
        }

    @staticmethod
    async def _resolve_existing_strategy(candidate: dict, db) -> Optional[dict]:
        dedup_result = dict(candidate.get("dedup_result") or {})
        if not dedup_result.get("refresh_existing"):
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

    @staticmethod
    def _build_strategy_data(strategy_id: str, name: str, candidate: dict, metrics: dict, existing: Optional[dict] = None) -> dict:
        """构建策略记录数据。"""
        existing = dict(existing or {})
        description = f"{name}\n生成原因: {candidate.get('spawn_reason', '')}"
        if metrics:
            description += f"\n回测: Sharpe {metrics.get('sharpe_ratio', 0):.2f} | "
            description += f"收益 {metrics.get('total_return', 0):.1%} | "
            description += f"回撤 {metrics.get('max_drawdown', 0):.1%}"

        existing_params = dict(existing.get("params") or {})
        stored_params = {
            **existing_params,
            **dict(candidate["params"] or {}),
            "target_symbols": list(candidate.get("target_symbols") or existing_params.get("target_symbols") or []),
            "stock_pool": dict(candidate.get("stock_pool") or existing_params.get("stock_pool") or {}),
        }
        if candidate.get("selection_logic") or existing_params.get("selection_logic"):
            stored_params["selection_logic"] = list(candidate.get("selection_logic") or existing_params.get("selection_logic") or [])
        if candidate.get("research_task") or existing_params.get("research_task"):
            stored_params["research_task"] = dict(candidate.get("research_task") or existing_params.get("research_task") or {})
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

    @staticmethod
    async def _save_metrics(strategy_id: str, candidate: dict, metrics: dict, db) -> tuple:
        """保存回测/验证/风险指标，每步独立容错。返回 (validation_report, risk_report)。"""
        factory_pkg = get_strategy_factory_package()

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

        validation_report = None
        try:
            validation_report = await factory_pkg._run_validation_report(
                candidate["strategy_type"],
                candidate.get("params", {}),
                db,
            )
            if validation_report:
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
            logger.warning("StrategySubmitter: validation report failed for %s: %s", strategy_id, exc)

        risk_report = None
        try:
            risk_report = await factory_pkg._run_risk_report(
                candidate["strategy_type"],
                candidate.get("params", {}),
                db,
            )
            if risk_report:
                await db.save_strategy_metrics(strategy_id, "risk", risk_report)
        except Exception as exc:
            logger.warning("StrategySubmitter: risk report failed for %s: %s", strategy_id, exc)

        return validation_report, risk_report

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

        if gate.get("passed"):
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
                from ..incubation import get_strategy_incubation_service

                incubation_binding = await get_strategy_incubation_service().ensure_account(
                    db,
                    enriched_data,
                    source_run_id=snapshot.get("date"),
                )
            except Exception as exc:
                logger.warning("StrategyFactory: ensure incubation account failed for %s: %s", strategy_id, exc)
            try:
                from ..incubation_pipeline import get_strategy_incubation_pipeline_service

                incubation_pipeline = await get_strategy_incubation_pipeline_service().run_strategy(
                    db,
                    {**enriched_data, "status": "incubating"},
                    source="strategy_factory_submit",
                    auto_apply_review=False,
                )
            except Exception as exc:
                logger.warning("StrategyFactory: initial incubation pipeline failed for %s: %s", strategy_id, exc)
            try:
                from ..vector_platform import get_strategy_vector_platform

                vector_profile = await get_strategy_vector_platform().build_strategy_profile(db, enriched_data)
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
        }

    @staticmethod
    async def _record_experiment(
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
            evaluation["quality_gate"] = gate
            if validation_report is not None or "validation_report" not in evaluation:
                evaluation["validation_report"] = validation_report or {}
            if risk_report is not None or "risk_report" not in evaluation:
                evaluation["risk_report"] = risk_report or {}

            result = dict(existing_result)
            result.update({"strategy_id": strategy_id, "generated_strategy_id": strategy_id, "status": status})
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
