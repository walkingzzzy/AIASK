"""Factor mining factory orchestration.

The factory consumes market data only through the SQLite storage adapter. TDX
is upstream of this component and may only populate the DB through sync tasks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .quality import compute_quality_score, evaluate_validation_evidence

logger = logging.getLogger(__name__)


class FactorMiningFactory:
    """Full factor mining cycle: search, evolve, validate, admit, persist."""

    def __init__(self):
        self._initialized = False
        self._engine_scheduler = None
        self._evolutionary_optimizer = None
        self._active_pool = None
        self._decay_monitor = None
        self._meta_learner = None
        self._last_run_at: Optional[datetime] = None
        self._run_count: int = 0
        self._pool_loaded_from_db = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        from .engines import EngineScheduler
        from .evolution.optimizer import EvolutionaryOptimizer
        from .pool.active_pool import ActiveFactorPool
        from .feedback.decay_monitor import DecayMonitor
        from .feedback.meta_learner import FactorMetaLearner

        self._engine_scheduler = EngineScheduler()
        self._evolutionary_optimizer = EvolutionaryOptimizer()
        self._active_pool = ActiveFactorPool()
        self._decay_monitor = DecayMonitor()
        self._meta_learner = FactorMetaLearner()
        self._initialized = True

    async def _get_db(self):
        from ...storage import get_db

        db = get_db()
        await db.initialize()
        return db

    async def _ensure_persistent_pool(self, db) -> None:
        from .pool.storage import ensure_factor_pool_tables, load_active_pool_from_db

        await ensure_factor_pool_tables(db)
        if self._pool_loaded_from_db:
            return
        records = await load_active_pool_from_db(db)
        hydrate = getattr(self._active_pool, "hydrate", None)
        if callable(hydrate):
            hydrate(records)
        self._pool_loaded_from_db = True

    async def run_mining_cycle(
        self,
        *,
        trigger: str = "scheduled",
        engines: list[str] | None = None,
        candidate_count: int = 30,
        evolution_generations: int = 5,
        codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run one complete DB-only factor mining cycle."""
        self._ensure_initialized()
        db = await self._get_db()
        await self._ensure_persistent_pool(db)

        run_id = f"mining_{int(datetime.now().timestamp())}_{uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc)
        logger.info("FactorMiningFactory: starting cycle run_id=%s trigger=%s", run_id, trigger)

        try:
            context = await self._build_mining_context(db=db, codes=codes)
            if len(getattr(context, "validation_codes", []) or []) < 120:
                report = {
                    "success": True,
                    "skipped": True,
                    "reason": "data_universe_insufficient",
                    "run_id": run_id,
                    "trigger": trigger,
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "raw_candidate_count": 0,
                    "evolved_count": 0,
                    "validated_count": 0,
                    "admitted_count": 0,
                    "quarantine_count": 0,
                    "active_promoted_count": 0,
                    "pool_size": self._active_pool.size,
                    "engines_used": [],
                    "validation_universe_health": getattr(
                        context,
                        "validation_universe_health",
                        {},
                    ),
                    "quality_summary": {
                        "reject_reasons": {"data_universe_insufficient": 1},
                    },
                }
                await self._persist_mining_run(db, report)
                return report
            quick_evaluator = self._build_quick_evidence_evaluator(db, context)
            setattr(context, "quick_evidence_evaluator", quick_evaluator.evaluate)
            setattr(context, "quick_ic_evaluator", quick_evaluator.ic_value)
            raw_candidates = await self._engine_scheduler.search(
                context=context,
                engines=engines,
                candidate_count=candidate_count,
            )
            logger.info("FactorMiningFactory: raw candidates=%d", len(raw_candidates))

            evolved = await self._evolutionary_optimizer.evolve(
                candidates=raw_candidates,
                context=context,
                generations=evolution_generations,
                ic_evaluator=quick_evaluator.ic_value,
            )
            logger.info("FactorMiningFactory: evolved candidates=%d", len(evolved))

            quick_passed = await self._quick_filter_candidates(evolved, context)
            logger.info(
                "FactorMiningFactory: quick evidence passed=%d/%d",
                len(quick_passed),
                len(evolved),
            )

            validated = await self._validate_batch(db, quick_passed, context)
            logger.info("FactorMiningFactory: validated candidates=%d", len(validated))

            admitted = await self._active_pool.admit_batch(validated)
            await self._persist_admitted_factors(db, admitted)
            quality_summary = self._build_quality_summary(
                raw_candidates,
                evolved,
                validated,
                admitted,
                context,
            )
            if hasattr(self._engine_scheduler, "record_quality_feedback"):
                self._engine_scheduler.record_quality_feedback(
                    raw_candidates,
                    validated,
                    admitted,
                )
            logger.info(
                "FactorMiningFactory: admitted=%d pool_size=%d",
                len(admitted),
                self._active_pool.size,
            )

            await self._record_feedback(run_id, raw_candidates, evolved, validated, admitted)

            self._last_run_at = datetime.now(timezone.utc)
            self._run_count += 1
            report = {
                "success": True,
                "run_id": run_id,
                "trigger": trigger,
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "raw_candidate_count": len(raw_candidates),
                "evolved_count": len(evolved),
                "validated_count": len(validated),
                "admitted_count": len(admitted),
                "quarantine_count": quality_summary.get("quarantine_count", 0),
                "active_promoted_count": quality_summary.get("active_promoted_count", 0),
                "pool_size": self._active_pool.size,
                "engines_used": self._engine_scheduler.last_engines_used,
                "validation_universe_health": getattr(context, "validation_universe_health", {}),
                "quality_summary": quality_summary,
            }
            await self._persist_mining_run(db, report)
            return report
        except Exception as exc:
            logger.error("FactorMiningFactory: cycle failed: %s", exc, exc_info=True)
            report = {
                "success": False,
                "run_id": run_id,
                "trigger": trigger,
                "error": str(exc),
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._persist_mining_run(db, report)
            return report

    async def run_maintenance(self) -> dict[str, Any]:
        """Run daily factor pool maintenance and persist decay measurements."""
        self._ensure_initialized()
        db = await self._get_db()
        await self._ensure_persistent_pool(db)
        decay_report = await self._decay_monitor.daily_check(self._active_pool, db=db)
        await self._persist_decay_report(db, decay_report)
        await self._persist_decay_updates(db, decay_report)
        promotion_report = await self._promote_quarantine_factors(db)
        qc_report = await self._run_qc_pipeline(db)
        return {
            "decay_report": decay_report,
            "promotion_report": promotion_report,
            "qc_pipeline_report": qc_report,
            "pool_size": self._active_pool.size,
            "maintained_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _run_qc_pipeline(self, db) -> dict[str, Any]:
        """P2-1：toggle ON 时，对活跃因子池跑残酷质检流水线并打标签/(可选)自动上下架。

        默认 OFF（qc_pipeline_enabled() False）→ 直接返回 skipped，零变化。
        runner 由现有 MCP 工具构造（validate_factor_oos / backtest_factor /
        factor_robustness_check），closure 捕获验证 universe；任一工具失败该项跳过。
        """
        from .qc_pipeline import (
            apply_qc_to_record,
            qc_autoshelf_enabled,
            qc_pipeline_enabled,
            run_factor_qc,
        )

        if not qc_pipeline_enabled():
            return {"enabled": False, "skipped": True}

        from .pool.storage import load_factor_pool_from_db, save_factor_to_pool

        try:
            from ...tools.quant_analysis import (
                run_factor_group_backtest,
                run_factor_oos_validation,
            )
            from ...tools._quant_analysis_support import run_factor_robustness_check
        except Exception as exc:  # noqa: BLE001
            logger.warning("qc_pipeline: tool import failed: %s", exc)
            return {"enabled": True, "skipped": True, "reason": f"tool_import_failed:{exc}"}

        # 验证 universe：复用挖矿上下文的 validation_codes（数据充足才有意义）。
        try:
            context = await self._build_mining_context(db=db)
            codes = list(getattr(context, "validation_codes", []) or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("qc_pipeline: build context failed: %s", exc)
            codes = []
        if len(codes) < 120:
            return {"enabled": True, "skipped": True, "reason": "data_universe_insufficient"}

        rows = await load_factor_pool_from_db(db, statuses=("active", "quarantine"), limit=200)
        if not rows:
            return {"enabled": True, "skipped": True, "reason": "empty_pool"}

        def _name(rec: dict) -> str:
            return str(rec.get("name") or "").strip()

        def _oos_runner(name):
            async def _run(_factor):
                resp = await run_factor_oos_validation(codes=codes, factor=name)
                return dict(resp.get("data") or {}) if isinstance(resp, dict) else None
            return _run

        def _layered_runner(name):
            async def _run(_factor):
                resp = await run_factor_group_backtest(codes=codes, factor=name)
                return dict(resp.get("data") or {}) if isinstance(resp, dict) else None
            return _run

        def _robust_runner(name):
            async def _run(_factor):
                resp = await run_factor_robustness_check(codes=codes, factor=name)
                return dict(resp.get("data") or {}) if isinstance(resp, dict) else None
            return _run

        decisions: dict[str, int] = {}
        processed = 0
        autoshelf = qc_autoshelf_enabled()
        for record in rows:
            name = _name(record)
            if not name:
                continue
            qc_result = await run_factor_qc(
                name,
                oos_runner=_oos_runner(name),
                layered_runner=_layered_runner(name),
                robustness_runner=_robust_runner(name),
                multiple_testing_runner=None,  # multiple_testing 嵌在 OOS 输出，单列不必重复跑
            )
            updated = apply_qc_to_record(record, qc_result)
            decision = str((qc_result.get("shelf_decision") or {}).get("decision") or "unknown")
            decisions[decision] = decisions.get(decision, 0) + 1
            try:
                await save_factor_to_pool(db, updated)
            except Exception as exc:  # noqa: BLE001
                logger.warning("qc_pipeline: save failed for %s: %s", name, exc)
            processed += 1

        return {
            "enabled": True,
            "skipped": False,
            "autoshelf_applied": autoshelf,
            "processed": processed,
            "decisions": decisions,
        }

    def status(self) -> dict[str, Any]:
        return {
            "initialized": self._initialized,
            "last_run_at": self._last_run_at.isoformat() if self._last_run_at else None,
            "run_count": self._run_count,
            "pool_size": self._active_pool.size if self._active_pool else 0,
            "engines": self._engine_scheduler.status() if self._engine_scheduler else {},
            "pool_loaded_from_db": self._pool_loaded_from_db,
        }

    async def _build_mining_context(self, *, db, codes: list[str] | None = None) -> "MiningContext":
        from .engines.context import MiningContext

        context = await MiningContext.build(db=db, codes=codes, active_pool=self._active_pool)
        memory = {}
        if self._meta_learner is not None and hasattr(self._meta_learner, "get_pattern_memory"):
            memory = self._meta_learner.get_pattern_memory()
        context.failed_pattern_memory = list(memory.get("failed_pattern_memory") or [])
        context.successful_pattern_memory = list(memory.get("successful_pattern_memory") or [])
        try:
            from .blueprints import AlphaBlueprintLibrary

            context.alpha_blueprints = AlphaBlueprintLibrary().build_context_blueprints(
                failed_pattern_memory=context.failed_pattern_memory,
                successful_pattern_memory=context.successful_pattern_memory,
            )
        except Exception:
            pass
        return context

    def _build_quick_evidence_evaluator(self, db, context):
        from .quick_evidence import QuickEvidenceEvaluator

        return QuickEvidenceEvaluator(
            db,
            codes=getattr(context, "validation_codes", None) or [],
            horizon_days=10,
            max_codes=120,
            max_evaluations=32,
        )

    async def _quick_filter_candidates(self, candidates: list, context) -> list:
        evaluator = getattr(context, "quick_evidence_evaluator", None)
        if evaluator is None:
            return list(candidates or [])

        import inspect

        passed = []
        for candidate in candidates or []:
            evidence = dict(getattr(candidate, "quick_evidence", None) or {})
            if not evidence:
                try:
                    result = evaluator(candidate)
                    if inspect.isawaitable(result):
                        result = await result
                    evidence = dict(result or {}) if isinstance(result, dict) else {}
                    candidate.quick_evidence = evidence
                except Exception as exc:
                    evidence = {
                        "available": False,
                        "passed": False,
                        "fail_reasons": [f"quick_filter_failed:{type(exc).__name__}"],
                    }
                    candidate.quick_evidence = evidence
            if evidence.get("passed"):
                passed.append(candidate)
        return passed

    async def _validate_batch(self, db, candidates: list, context) -> list:
        from ..factor_validation_pipeline import validate_factor_candidate_pipeline

        validated = []
        validation_codes = context.validation_codes
        for candidate in candidates:
            generation_trace = dict(getattr(candidate, "generation_trace", None) or {})
            generation_trace["strict_validation_attempted"] = True
            candidate.generation_trace = generation_trace
            try:
                result = await validate_factor_candidate_pipeline(
                    db,
                    candidate.to_validation_dict(),
                    codes=validation_codes,
                    stage="strict",
                    lookback_bars=220,
                    horizon_days=10,
                    min_cross_section=30,
                    persist_outputs=True,
                    factor_key=candidate.name,
                    persist_ic_history=True,
                )
                generation_trace = dict(getattr(candidate, "generation_trace", None) or {})
                generation_trace["strict_validation_success"] = bool(result.get("success"))
                generation_trace["strict_validation_stage"] = result.get("stage")
                candidate.generation_trace = generation_trace
                if result.get("success"):
                    candidate.validation_result = result
                    rating = result.get("rating", {})
                    generation_trace = dict(getattr(candidate, "generation_trace", None) or {})
                    candidate.fitness = compute_quality_score(
                        result,
                        structural_score=float(
                            generation_trace.get("evolution_structural_score", 0.0)
                            or 0.0
                        ),
                    )
                    if (
                        rating.get("grade") in ("A", "B")
                        and self._has_admissible_ic_evidence(result)
                    ):
                        validated.append(candidate)
            except Exception as exc:
                generation_trace = dict(getattr(candidate, "generation_trace", None) or {})
                generation_trace["strict_validation_success"] = False
                generation_trace["strict_validation_error"] = f"{type(exc).__name__}: {exc}"
                candidate.generation_trace = generation_trace
                candidate.validation_result = {
                    "success": False,
                    "stage": "strict",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "candidate": candidate.to_validation_dict()
                    if hasattr(candidate, "to_validation_dict")
                    else {},
                }
                logger.debug("Validation failed for %s: %s", candidate.name, exc)
        return validated

    @staticmethod
    def _has_admissible_ic_evidence(result: dict[str, Any]) -> bool:
        return bool(evaluate_validation_evidence(result).get("passed"))

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _build_ic_evaluator(self, db, context):
        async def _evaluate(candidate) -> float:
            from ..factor_validation_pipeline import validate_factor_candidate_pipeline

            try:
                result = await validate_factor_candidate_pipeline(
                    db,
                    candidate.to_validation_dict(),
                    codes=getattr(context, "validation_codes", None) or [],
                    lookback_bars=180,
                    horizon_days=10,
                    max_dates=80,
                    min_cross_section=30,
                    persist_outputs=False,
                    persist_ic_history=False,
                )
                metrics = dict(result.get("metrics") or {})
                cross_section = dict(result.get("cross_section") or {})
                summary = dict(cross_section.get("summary") or {})
                if int(summary.get("sample_dates") or metrics.get("sample_dates") or 0) < 20:
                    return 0.0
                value = (
                    metrics.get("rank_ic_mean")
                    or summary.get("rank_ic_mean")
                    or metrics.get("normal_ic_mean")
                    or summary.get("normal_ic_mean")
                    or 0.0
                )
                return float(value or 0.0)
            except Exception as exc:
                logger.debug("IC evaluator failed for %s: %s", getattr(candidate, "name", ""), exc)
                return 0.0

        return _evaluate

    def _build_quality_summary(
        self,
        raw: list[Any],
        evolved: list[Any],
        validated: list[Any],
        admitted: list[dict[str, Any]],
        context: Any,
    ) -> dict[str, Any]:
        reject_reasons: dict[str, int] = {}
        diagnostic_counts: dict[str, int] = {}
        quick_evaluated_count = 0
        quick_passed_count = 0
        for candidate in evolved or []:
            quick = dict(getattr(candidate, "quick_evidence", None) or {})
            if quick:
                quick_evaluated_count += 1
                if quick.get("passed"):
                    quick_passed_count += 1
                else:
                    for reason in list(quick.get("fail_reasons") or []):
                        reject_reasons[str(reason)] = reject_reasons.get(str(reason), 0) + 1
                for key, value in dict(quick.get("diagnostic_counts") or {}).items():
                    diagnostic_counts[str(key)] = diagnostic_counts.get(str(key), 0) + int(value or 0)
            result = getattr(candidate, "validation_result", None)
            if not result:
                continue
            evidence = evaluate_validation_evidence(result)
            if evidence.get("passed"):
                pass
            else:
                for reason in list(evidence.get("reasons") or []):
                    reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
            coverage = dict(result.get("coverage") or {})
            for key, value in dict(coverage.get("diagnostic_counts") or {}).items():
                diagnostic_counts[str(key)] = diagnostic_counts.get(str(key), 0) + int(value or 0)

        quarantine_count = 0
        active_promoted_count = 0
        by_engine: dict[str, dict[str, int]] = {}
        by_blueprint: dict[str, dict[str, int]] = {}
        strict_candidate_results = self._strict_candidate_results(
            evolved,
            validated,
            admitted,
        )
        for candidate in raw or []:
            engine = str(getattr(candidate, "generation_engine", "") or "unknown")
            by_engine.setdefault(engine, {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0})
            by_engine[engine]["raw"] += 1
            blueprint = str(getattr(candidate, "blueprint_id", "") or "none")
            by_blueprint.setdefault(
                blueprint,
                {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0},
            )
            by_blueprint[blueprint]["raw"] += 1
        for candidate in evolved or []:
            engine = str(getattr(candidate, "generation_engine", "") or "unknown")
            by_engine.setdefault(engine, {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0})
            blueprint = str(getattr(candidate, "blueprint_id", "") or "none")
            by_blueprint.setdefault(
                blueprint,
                {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0},
            )
            if (getattr(candidate, "quick_evidence", None) or {}).get("passed"):
                by_engine[engine]["quick_passed"] += 1
                by_blueprint[blueprint]["quick_passed"] += 1
        for candidate in validated or []:
            engine = str(getattr(candidate, "generation_engine", "") or "unknown")
            by_engine.setdefault(engine, {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0})
            by_engine[engine]["validated"] += 1
            blueprint = str(getattr(candidate, "blueprint_id", "") or "none")
            by_blueprint.setdefault(
                blueprint,
                {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0},
            )
            by_blueprint[blueprint]["validated"] += 1
        for item in admitted or []:
            record = dict((item or {}).get("record") or {})
            engine = str(record.get("generation_engine") or "unknown")
            by_engine.setdefault(engine, {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0})
            by_engine[engine]["accepted"] += 1
            generation_trace = dict(record.get("generation_trace") or {})
            blueprint = str(generation_trace.get("blueprint_id") or "none")
            by_blueprint.setdefault(
                blueprint,
                {"raw": 0, "quick_passed": 0, "validated": 0, "accepted": 0},
            )
            by_blueprint[blueprint]["accepted"] += 1
            validation_summary = dict(record.get("validation_summary") or {})
            if validation_summary.get("quality_status") == "quarantine":
                quarantine_count += 1
            if validation_summary.get("quality_status") == "promoted":
                active_promoted_count += 1

        return {
            "raw_candidate_count": len(raw or []),
            "evolved_count": len(evolved or []),
            "quick_evaluated_count": quick_evaluated_count,
            "quick_passed_count": quick_passed_count,
            "evidence_passed_count": len(validated or []),
            "quarantine_count": quarantine_count,
            "active_promoted_count": active_promoted_count,
            "reject_reasons": reject_reasons,
            "diagnostic_counts": diagnostic_counts,
            "quality_funnel": {
                "generated": len(raw or []),
                "evolved": len(evolved or []),
                "quick_evaluated": quick_evaluated_count,
                "quick_passed": quick_passed_count,
                "strict_validated": len(validated or []),
                "quarantine": quarantine_count,
                "promoted": active_promoted_count,
            },
            "by_engine": by_engine,
            "by_blueprint": by_blueprint,
            "strict_candidate_results": strict_candidate_results,
            "validation_universe_health": getattr(context, "validation_universe_health", {}),
        }

    def _strict_candidate_results(
        self,
        evolved: list[Any],
        validated: list[Any],
        admitted: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        validated_ids = {id(candidate) for candidate in validated or []}
        admitted_names = {
            str(dict((item or {}).get("record") or {}).get("name") or "")
            for item in admitted or []
        }
        rows: list[dict[str, Any]] = []
        for candidate in evolved or []:
            trace = dict(getattr(candidate, "generation_trace", None) or {})
            result = getattr(candidate, "validation_result", None)
            if not trace.get("strict_validation_attempted") and not result:
                continue
            rows.append(
                self._strict_candidate_result_payload(
                    candidate,
                    strict_gate_passed=id(candidate) in validated_ids,
                    admitted=str(getattr(candidate, "name", "") or "") in admitted_names,
                )
            )
        return rows

    def _strict_candidate_result_payload(
        self,
        candidate: Any,
        *,
        strict_gate_passed: bool,
        admitted: bool,
    ) -> dict[str, Any]:
        result = getattr(candidate, "validation_result", None)
        result = dict(result or {})
        evidence = evaluate_validation_evidence(result) if result else {
            "passed": False,
            "reasons": ["missing_validation_result"],
            "summary": {},
        }
        rating = dict(result.get("rating") or {})
        governance = dict(rating.get("governance") or {})
        grade = str(rating.get("grade") or "")
        blockers: list[str] = []
        if not result.get("success"):
            blockers.append("strict_validation_failed")
        if not evidence.get("passed"):
            blockers.extend(str(item) for item in list(evidence.get("reasons") or []))
        if grade not in {"A", "B"}:
            blockers.append(f"rating_grade_not_admissible:{grade or 'missing'}")
        if governance.get("admission_blocked"):
            blockers.extend(
                str(item)
                for item in list(governance.get("admission_block_reasons") or [])
            )
        blockers = list(dict.fromkeys(item for item in blockers if item))
        return {
            "name": str(getattr(candidate, "name", "") or ""),
            "generation_engine": str(getattr(candidate, "generation_engine", "") or ""),
            "blueprint_id": str(getattr(candidate, "blueprint_id", "") or ""),
            "family": str(
                getattr(candidate, "factor_family", "")
                or getattr(candidate, "family", "")
                or ""
            ),
            "expression_dsl": str(getattr(candidate, "expression_dsl", "") or ""),
            "fitness": float(getattr(candidate, "fitness", 0.0) or 0.0),
            "quick_evidence": dict(getattr(candidate, "quick_evidence", None) or {}),
            "admission_decision": {
                "strict_gate_passed": bool(strict_gate_passed),
                "admitted": bool(admitted),
                "evidence_passed": bool(evidence.get("passed")),
                "evidence_reasons": list(evidence.get("reasons") or []),
                "evidence_summary": dict(evidence.get("summary") or {}),
                "rating_grade": grade,
                "rating_recommendation": rating.get("recommendation"),
                "governance_admission_blocked": bool(governance.get("admission_blocked")),
                "governance_block_reasons": list(
                    governance.get("admission_block_reasons") or []
                ),
                "blockers": blockers,
            },
            "generation_trace": dict(getattr(candidate, "generation_trace", None) or {}),
            "validation_result": result,
        }

    async def _persist_admitted_factors(self, db, admitted: list[dict[str, Any]]) -> None:
        from .pool.storage import save_factor_to_pool

        for item in admitted or []:
            record = item.get("record") if isinstance(item, dict) else None
            if isinstance(record, dict):
                await save_factor_to_pool(db, record)

    async def _persist_mining_run(self, db, report: dict[str, Any]) -> None:
        from .pool.storage import save_mining_run

        await save_mining_run(db, report)

    async def _persist_decay_report(self, db, decay_report: dict[str, Any]) -> None:
        from .pool.storage import save_decay_measurement

        candidates = []
        if isinstance(decay_report, dict):
            for key in ("measurements", "decay_measurements", "items"):
                value = decay_report.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
        for item in candidates:
            if isinstance(item, dict) and item.get("factor_id"):
                item.setdefault("measured_at", datetime.now(timezone.utc).isoformat())
                await save_decay_measurement(db, item)

    async def _persist_decay_updates(self, db, decay_report: dict[str, Any]) -> None:
        from .pool.storage import save_factor_to_pool

        if not isinstance(decay_report, dict):
            return
        for record in list(decay_report.get("updated_records") or []):
            if isinstance(record, dict) and record.get("factor_id"):
                await save_factor_to_pool(db, record)

    async def _promote_quarantine_factors(self, db) -> dict[str, Any]:
        from .pool.storage import load_factor_pool_from_db, save_factor_to_pool

        rows = await load_factor_pool_from_db(
            db,
            statuses=("quarantine",),
            limit=200,
        )
        promoted: list[str] = []
        rejected: dict[str, int] = {}
        for record in rows:
            evidence_result = await self._build_quarantine_evidence_result(db, record)
            evidence = evaluate_validation_evidence(evidence_result)
            if not evidence.get("passed"):
                for reason in list(evidence.get("reasons") or []):
                    rejected[reason] = rejected.get(reason, 0) + 1
                validation_summary = dict(record.get("validation_summary") or {})
                validation_summary["quality_status"] = "quarantine"
                validation_summary["evidence_summary"] = dict(evidence.get("summary") or {})
                validation_summary["promotion_block_reasons"] = list(evidence.get("reasons") or [])
                record["validation_summary"] = validation_summary
                await save_factor_to_pool(db, record)
                continue

            validation_summary = dict(record.get("validation_summary") or {})
            validation_summary["quality_status"] = "promoted"
            validation_summary["evidence_summary"] = dict(evidence.get("summary") or {})
            validation_summary["promotion_block_reasons"] = []
            record["validation_summary"] = validation_summary
            record["status"] = "active"
            record["current_ic"] = (evidence.get("summary") or {}).get("rank_ic_mean")
            record["fitness"] = compute_quality_score(evidence_result)
            record["last_evaluated_at"] = datetime.now(timezone.utc).isoformat()
            await save_factor_to_pool(db, record)
            hydrate = getattr(self._active_pool, "hydrate", None)
            if callable(hydrate):
                hydrate([record])
            promoted.append(str(record.get("factor_id") or ""))

        return {
            "checked": len(rows),
            "promoted": promoted,
            "promoted_count": len(promoted),
            "rejected_reasons": rejected,
        }

    async def _build_quarantine_evidence_result(self, db, record: dict[str, Any]) -> dict[str, Any]:
        name = str(record.get("name") or "").strip()
        if not name:
            return {}
        rows = []
        try:
            if hasattr(db, "get_factor_ic_history"):
                rows = await db.get_factor_ic_history(name, "10", 60)
            elif hasattr(db, "acquire"):
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM factor_ic_history
                        WHERE factor_name = $1
                        ORDER BY ic_date DESC
                        LIMIT 60
                        """,
                        name,
                    )
            else:
                raw_conn = getattr(db, "conn", None) or getattr(db, "connection", None)
                if raw_conn is not None:
                    cursor = raw_conn.execute(
                        """
                        SELECT * FROM factor_ic_history
                        WHERE factor_name = ?
                        ORDER BY ic_date DESC
                        LIMIT 60
                        """,
                        (name,),
                    )
                    columns = [desc[0] for desc in cursor.description]
                    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception:
            rows = []
        rows = [dict(row) for row in rows or []]
        values = [float(row.get("rank_ic") or 0.0) for row in rows]
        sample_sizes = [int(row.get("sample_size") or 0) for row in rows]
        if not values:
            return {
                "metrics": {"sample_dates": 0},
                "coverage": {"avg_cross_section_n": 0.0},
                "persisted_outputs": {"enabled": True, "ic_history_rows": 0},
                "lookahead_audit": {"risk_level": "unknown"},
            }
        import numpy as np

        std = float(np.std(values)) if len(values) > 1 else 0.0
        mean = float(np.mean(values))
        return {
            "metrics": {
                "sample_dates": len(values),
                "rank_ic_mean": mean,
                "rank_ic_ir": mean / std if std > 1e-12 else 0.0,
                "positive_ratio": float(np.mean(np.array(values) > 0.0)),
            },
            "coverage": {
                "avg_cross_section_n": float(np.mean(sample_sizes)) if sample_sizes else 0.0,
            },
            "persisted_outputs": {"enabled": True, "ic_history_rows": len(values)},
            "lookahead_audit": {"risk_level": "low"},
        }

    async def _record_feedback(self, run_id, raw, evolved, validated, admitted):
        await self._meta_learner.record_cycle(
            run_id=run_id,
            raw_count=len(raw),
            evolved_count=len(evolved),
            validated_count=len(validated),
            admitted_count=len(admitted),
            candidates=raw + evolved,
        )
