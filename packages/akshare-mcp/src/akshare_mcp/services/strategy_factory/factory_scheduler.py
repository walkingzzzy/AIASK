"""策略工厂调度器实现。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_STARTUP_DELAY_SEC,
    FACTORY_DAILY_RUN_TIME,
    FACTORY_ERROR_BACKOFF_SEC,
    FACTORY_MARKET_HOURS_INTERVAL_SEC,
    FACTORY_MAX_DAILY_RUNS,
    FACTORY_OFF_HOURS_INTERVAL_SEC,
    FACTORY_SCHEDULE_MODE,
    RESEARCH_TASK_CONCURRENCY,
)
from .runtime import _call_optional_async, get_strategy_factory_package
from .utils import _extract_event_context
from ..strategy_autonomy_lifecycle import AUTONOMY_PHASE_ORDER, summarize_autonomy_lifecycle

logger = logging.getLogger(__name__)


class StrategyFactoryScheduler:
    """策略工厂调度器，支持 continuous（24/7循环）和 daily（每日定时）两种模式。"""

    def __init__(self, run_time: Optional[time] = None):
        self.schedule_mode: str = FACTORY_SCHEDULE_MODE if FACTORY_SCHEDULE_MODE in ("continuous", "daily") else "continuous"
        # daily 模式的运行时间
        if run_time is not None:
            self.run_time = run_time
        else:
            try:
                parts = FACTORY_DAILY_RUN_TIME.split(":")
                self.run_time = time(int(parts[0]), int(parts[1]))
            except Exception:
                self.run_time = time(19, 0)
        self.max_daily_runs: int = FACTORY_MAX_DAILY_RUNS
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None
        self._daily_run_count: int = 0
        self._daily_run_date: Optional[str] = None  # "YYYY-MM-DD"
        self._cycle_count: int = 0

    def start(self):
        if self._running:
            logger.warning("StrategyFactory already running")
            return
        self._running = True
        self._task = asyncio.ensure_future(self._loop())
        logger.info(
            "StrategyFactory started, mode=%s, market_interval=%ds, off_hours_interval=%ds, max_daily_runs=%d",
            self.schedule_mode,
            FACTORY_MARKET_HOURS_INTERVAL_SEC,
            FACTORY_OFF_HOURS_INTERVAL_SEC,
            self.max_daily_runs,
        )

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("StrategyFactory stopped")

    @staticmethod
    def _build_task_source_counts(tasks: List[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in list(tasks or []):
            source = str((task or {}).get("task_source") or "unknown").strip() or "unknown"
            counts[source] = counts.get(source, 0) + 1
        return counts

    @staticmethod
    def _extract_cycle_candidates(cycle: dict) -> list[dict]:
        generation = dict((cycle or {}).get("generation") or {})
        candidates = generation.get("candidates")
        if isinstance(candidates, list):
            return list(candidates)
        return list((cycle or {}).get("candidates") or [])

    @staticmethod
    def _extract_cycle_experiments(cycle: dict) -> list[dict]:
        experiments = (cycle or {}).get("experiments")
        if isinstance(experiments, dict):
            return list(experiments.get("items") or [])
        if isinstance(experiments, list):
            return list(experiments)
        return list((cycle or {}).get("experiment_records") or [])

    @staticmethod
    def _extract_cycle_llm_generation(cycle: dict) -> dict:
        llm_generation = (cycle or {}).get("llm_generation")
        if isinstance(llm_generation, dict):
            return dict(llm_generation)
        generation = dict((cycle or {}).get("generation") or {})
        return dict(generation.get("llm_generation") or {})

    @staticmethod
    def _extract_cycle_generated_count(cycle: dict) -> int:
        value = (cycle or {}).get("generated_count")
        if value is None:
            value = dict((cycle or {}).get("generation") or {}).get("count")
        if value is None:
            value = len(StrategyFactoryScheduler._extract_cycle_candidates(cycle))
        return int(value or 0)

    @staticmethod
    def _extract_cycle_reviewed_count(cycle: dict) -> int:
        value = (cycle or {}).get("reviewed_count")
        if value is None:
            value = dict((cycle or {}).get("review") or {}).get("reviewed_count")
        return int(value or 0)

    @staticmethod
    def _extract_cycle_lifecycle(cycle: dict) -> dict:
        lifecycle = (cycle or {}).get("lifecycle")
        return dict(lifecycle) if isinstance(lifecycle, dict) else {}

    @staticmethod
    def _aggregate_task_lifecycle_metrics(task_results: List[dict]) -> dict:
        lifecycle_state_counts: dict[str, int] = {}
        phase_status_counts: dict[str, int] = {}
        failed_phase_counts: dict[str, int] = {}
        observable_phases: list[str] = []
        for item in list(task_results or []):
            lifecycle_summary = dict(item.get("lifecycle_summary") or {})
            state = str(lifecycle_summary.get("state") or "unknown")
            lifecycle_state_counts[state] = lifecycle_state_counts.get(state, 0) + 1
            for status, count in dict(lifecycle_summary.get("phase_status_counts") or {}).items():
                phase_status_counts[str(status)] = phase_status_counts.get(str(status), 0) + int(count or 0)
            failed_phase = str(lifecycle_summary.get("failed_phase") or "").strip()
            if failed_phase:
                failed_phase_counts[failed_phase] = failed_phase_counts.get(failed_phase, 0) + 1
            phase_order = list(lifecycle_summary.get("phase_order") or [])
            if phase_order:
                observable_phases = phase_order
        return {
            "lifecycle_state_counts": lifecycle_state_counts,
            "phase_status_counts": phase_status_counts,
            "failed_phase_counts": failed_phase_counts,
            "observable_phases": observable_phases or list(AUTONOMY_PHASE_ORDER),
        }

    @staticmethod
    def _with_stage_meta(stage_name: str, trace_id: str, payload: Optional[dict], *, default_ok: bool = True) -> dict:
        data = dict(payload or {})
        ok = bool(data.pop("ok", default_ok))
        status = str(data.pop("status", "completed" if ok else "failed"))
        return {
            "stage": stage_name,
            "trace_id": trace_id,
            "status": status,
            "ok": ok,
            **data,
        }

    @staticmethod
    def _aggregate_vector_submission_metrics(submission_result: Optional[dict]) -> dict:
        items = list((submission_result or {}).get("strategies") or [])
        backend_counts: dict[str, int] = {}
        requested_backend_counts: dict[str, int] = {}
        fallback_count = 0
        latencies: list[float] = []
        profile_count = 0
        for item in items:
            profile_id = item.get("vector_profile_id")
            if profile_id:
                profile_count += 1
            backend = str(item.get("vector_backend_used") or item.get("vector_backend") or "").strip()
            if backend:
                backend_counts[backend] = backend_counts.get(backend, 0) + 1
            requested_backend = str(item.get("vector_backend_requested") or "").strip()
            if requested_backend:
                requested_backend_counts[requested_backend] = requested_backend_counts.get(requested_backend, 0) + 1
            if item.get("vector_fallback_used"):
                fallback_count += 1
            latency = item.get("vector_latency_ms")
            if latency is not None:
                try:
                    latencies.append(float(latency))
                except Exception:
                    pass
        return {
            "vector_profile_count": profile_count,
            "vector_backend_counts": backend_counts,
            "vector_backend_requested_counts": requested_backend_counts,
            "vector_fallback_count": fallback_count,
            "vector_latency_ms_avg": round(sum(latencies) / len(latencies), 3) if latencies else None,
            "vector_latency_ms_max": round(max(latencies), 3) if latencies else None,
        }

    @staticmethod
    def _build_event_task_evidence_items(task: dict) -> List[dict]:
        event_context = _extract_event_context(task)
        task_key = str((task or {}).get("task_key") or (task or {}).get("task_id") or "").strip()
        event_id = str(event_context.get("event_id") or "").strip()
        if not task_key or not event_id:
            return []

        evidence_bundle = dict((task or {}).get("evidence_bundle") or {})
        score_summary = dict(event_context.get("score_summary") or {})
        theme_code = str(event_context.get("theme_code") or "").strip()
        supporting_reasons = list(event_context.get("supporting_reasons") or [])
        target_symbols = list(event_context.get("target_symbols") or [])
        symbol_details = {
            str((item or {}).get("code") or (item or {}).get("symbol") or "").strip(): dict(item or {})
            for item in list(evidence_bundle.get("symbol_details") or [])
            if str((item or {}).get("code") or (item or {}).get("symbol") or "").strip()
        }
        summary_weight = float(score_summary.get("avg_final_score") or 0.0)
        items: List[dict] = [
            {
                "task_key": task_key,
                "event_id": event_id,
                "theme_code": theme_code,
                "symbol": None,
                "evidence_type": "event_theme_context",
                "weight": summary_weight,
                "evidence_payload": {**event_context, "snapshot_date": (task or {}).get("snapshot_date")},
            }
        ]
        for reason in supporting_reasons[:4]:
            items.append({
                "task_key": task_key,
                "event_id": event_id,
                "theme_code": theme_code,
                "symbol": None,
                "evidence_type": "supporting_reason",
                "weight": summary_weight,
                "evidence_payload": {
                    "reason": reason,
                    "event_id": event_id,
                    "theme_code": theme_code,
                    "direction": event_context.get("direction"),
                    "horizon": event_context.get("horizon"),
                },
            })
        for rank, symbol in enumerate(target_symbols[:5], 1):
            detail = symbol_details.get(symbol) or {}
            items.append({
                "task_key": task_key,
                "event_id": event_id,
                "theme_code": theme_code,
                "symbol": symbol,
                "evidence_type": "target_symbol",
                "weight": round(max(summary_weight - (rank - 1) * 0.05, 0.0), 4),
                "evidence_payload": {
                    "symbol": symbol,
                    "rank": rank,
                    "event_id": event_id,
                    "theme_code": theme_code,
                    "event_summary": event_context.get("event_summary"),
                    "direction": event_context.get("direction"),
                    "horizon": event_context.get("horizon"),
                    "score_summary": score_summary,
                    "symbol_detail": detail,
                },
            })
        return items

    async def _persist_task_evidence(self, db, task: dict) -> List[dict]:
        saved_rows: List[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for item in self._build_event_task_evidence_items(task):
            dedupe_key = (
                str(item.get("task_key") or ""),
                str(item.get("evidence_type") or ""),
                str(item.get("symbol") or ""),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            row = await _call_optional_async(db, "save_factory_task_evidence", item, default=None)
            if row is not None:
                saved_rows.append(dict(row))
        return saved_rows

    @staticmethod
    def _is_market_hours(now: datetime) -> bool:
        """判断是否为 A 股盘中时间（工作日 9:30-15:00）。"""
        if now.weekday() >= 5:  # 周六日
            return False
        t = now.time()
        return time(9, 30) <= t < time(15, 0)

    def _compute_next_wait(self, now: datetime) -> float:
        """根据调度模式和当前时间计算下一次运行的等待秒数。"""
        # 首次运行使用启动延迟
        if self._cycle_count == 0:
            return float(AUTONOMY_STARTUP_DELAY_SEC)

        if self.schedule_mode == "daily":
            target = datetime.combine(now.date(), self.run_time)
            if target <= now:
                target += timedelta(days=1)
            return (target - now).total_seconds()

        # continuous 模式
        if now.weekday() >= 5:
            # 周末
            return float(FACTORY_OFF_HOURS_INTERVAL_SEC)
        if self._is_market_hours(now):
            return float(FACTORY_MARKET_HOURS_INTERVAL_SEC)
        return float(FACTORY_OFF_HOURS_INTERVAL_SEC)

    async def _loop(self):
        while self._running:
            try:
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")

                # 日期变更 → 重置每日计数
                if self._daily_run_date != today_str:
                    self._daily_run_date = today_str
                    self._daily_run_count = 0

                # 达到每日上限 → 睡到午夜
                if self._daily_run_count >= self.max_daily_runs:
                    tomorrow = datetime.combine(now.date() + timedelta(days=1), time(0, 0))
                    sleep_sec = (tomorrow - now).total_seconds() + 1
                    logger.info(
                        "StrategyFactory: daily limit reached (%d/%d), sleeping %.0fs until midnight",
                        self._daily_run_count, self.max_daily_runs, sleep_sec,
                    )
                    await asyncio.sleep(sleep_sec)
                    continue

                wait = self._compute_next_wait(now)
                logger.info(
                    "StrategyFactory [%s]: cycle #%d, today %d/%d runs, next in %.0fs",
                    self.schedule_mode, self._cycle_count, self._daily_run_count,
                    self.max_daily_runs, wait,
                )
                await asyncio.sleep(wait)

                if self._running:
                    await self.run_once()
                    self._daily_run_count += 1
                    self._cycle_count += 1
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("StrategyFactory loop error: %s", exc, exc_info=True)
                await asyncio.sleep(FACTORY_ERROR_BACKOFF_SEC)

    async def _generate_for_research_task(self, autonomy_service, db, snapshot: dict, task: dict) -> dict:
        limit = max(1, min(int(task.get("generation_limit") or AUTONOMY_CANDIDATES_PER_TASK), 10))
        source = f"strategy_factory:{task.get('opportunity_type') or 'general'}"
        try:
            return await autonomy_service.generate_factory_candidates(
                db,
                snapshot,
                limit=limit,
                research_task=task,
                source=source,
            )
        except TypeError:
            return await autonomy_service.generate_factory_candidates(db, snapshot, limit=limit)

    async def _run_autonomy_batches(self, db, snapshot: dict) -> dict:
        from ..strategy_autonomy import get_strategy_autonomy_service

        factory_pkg = get_strategy_factory_package()
        scanner = factory_pkg.MarketOpportunityScanner()
        scan_report = await scanner.scan(db, snapshot)
        tasks = list(scan_report.get("tasks") or [])
        scan_summary = dict(scan_report.get("summary") or {})
        task_source_counts = dict(scan_summary.get("task_sources") or self._build_task_source_counts(tasks))
        event_task_count = int(scan_summary.get("event_task_count") or task_source_counts.get("event_driven", 0))
        autonomy_service = get_strategy_autonomy_service()
        generated_candidates: List[dict] = []
        all_experiments: List[dict] = []
        task_results: List[dict] = []
        external_status_counts: Dict[str, int] = {}
        total_attempt_count = 0
        total_selected_count = 0
        total_evidence_count = 0
        last_error_type = None
        last_error = None
        elapsed_seconds = 0.0
        _agg_lock = asyncio.Lock()

        sem = asyncio.Semaphore(RESEARCH_TASK_CONCURRENCY)

        async def _run_one_task(task: dict) -> None:
            nonlocal total_attempt_count, total_selected_count, total_evidence_count
            nonlocal last_error_type, last_error, elapsed_seconds

            async with sem:
                evidence_rows = await self._persist_task_evidence(db, {**task, "snapshot_date": snapshot.get("date")})
                event_context = _extract_event_context(task)
                task_run = (
                    await _call_optional_async(
                        db,
                        "save_strategy_task_run",
                        {
                            "strategy_id": None,
                            "task_name": "strategy_research_task",
                            "task_scope": "strategy_factory",
                            "task_key": task.get("task_key") or task.get("task_id"),
                            "status": "running",
                            "trace_id": uuid4().hex[:12],
                            "payload": {
                                "research_task": task,
                                "event_context": event_context,
                                "task_source": task.get("task_source"),
                                "evidence_count": len(evidence_rows),
                                "snapshot_date": snapshot.get("date"),
                            },
                        },
                        default={"id": None},
                    )
                    or {"id": None}
                )
                enriched_task = {
                    **task,
                    "task_run_id": task_run.get("id"),
                    "event_context": event_context,
                    "evidence_count": len(evidence_rows),
                    "evidence_refs": [
                        {
                            "id": item.get("id"),
                            "evidence_type": item.get("evidence_type"),
                            "symbol": item.get("symbol"),
                            "weight": item.get("weight"),
                        }
                        for item in evidence_rows
                    ],
                }
                try:
                    cycle = await self._generate_for_research_task(autonomy_service, db, snapshot, enriched_task)
                    llm_generation = self._extract_cycle_llm_generation(cycle)
                    lifecycle = self._extract_cycle_lifecycle(cycle)
                    lifecycle_summary = summarize_autonomy_lifecycle(lifecycle)
                    external_provider = dict(llm_generation.get("external_provider") or {})
                    status = str(external_provider.get("status") or "unknown")
                    task_result = {
                        "task": enriched_task,
                        "task_run_id": task_run.get("id"),
                        "task_source": enriched_task.get("task_source"),
                        "event_id": enriched_task.get("event_id"),
                        "theme_code": enriched_task.get("theme_code"),
                        "evidence_count": len(evidence_rows),
                        "status": "completed",
                        "generated_count": self._extract_cycle_generated_count(cycle),
                        "reviewed_count": self._extract_cycle_reviewed_count(cycle),
                        "external_llm_status": status,
                        "llm_generation": llm_generation,
                        "lifecycle": lifecycle,
                        "lifecycle_summary": lifecycle_summary,
                    }
                    async with _agg_lock:
                        generated_candidates.extend(self._extract_cycle_candidates(cycle))
                        all_experiments.extend(self._extract_cycle_experiments(cycle))
                        external_status_counts[status] = external_status_counts.get(status, 0) + 1
                        total_attempt_count += len(external_provider.get("requests") or [])
                        total_selected_count += int(external_provider.get("selected_count") or 0)
                        total_evidence_count += len(evidence_rows)
                        if external_provider.get("last_error_type"):
                            last_error_type = external_provider.get("last_error_type")
                            last_error = external_provider.get("last_error")
                        elapsed_seconds += float(external_provider.get("elapsed_seconds") or 0.0)
                        task_results.append(task_result)
                    if task_run.get("id") is not None:
                        await _call_optional_async(
                            db,
                            "update_strategy_task_run",
                            task_run["id"],
                            status="completed",
                            result=task_result,
                        )
                except Exception as exc:
                    failure_lifecycle = dict(getattr(exc, "autonomy_lifecycle", {}) or {})
                    if not failure_lifecycle:
                        failure_lifecycle = {
                            "state": "failed",
                            "current_phase": "generating",
                            "failed_phase": "generating",
                            "terminal_phase": "failed",
                            "phase_order": list(AUTONOMY_PHASE_ORDER),
                            "phase_status_counts": {"failed": 1},
                            "completed_phase_count": 0,
                            "event_count": 0,
                            "events": [],
                        }
                    lifecycle_summary = summarize_autonomy_lifecycle(failure_lifecycle)
                    task_result = {
                        "task": enriched_task,
                        "task_run_id": getattr(exc, "autonomy_task_run_id", None) or task_run.get("id"),
                        "task_source": enriched_task.get("task_source"),
                        "event_id": enriched_task.get("event_id"),
                        "theme_code": enriched_task.get("theme_code"),
                        "evidence_count": len(evidence_rows),
                        "status": "failed",
                        "generated_count": 0,
                        "error": str(exc),
                        "lifecycle": failure_lifecycle,
                        "lifecycle_summary": lifecycle_summary,
                    }
                    async with _agg_lock:
                        task_results.append(task_result)
                        external_status_counts["failed"] = external_status_counts.get("failed", 0) + 1
                        total_evidence_count += len(evidence_rows)
                        last_error_type = exc.__class__.__name__
                        last_error = str(exc)
                    if task_run.get("id") is not None:
                        await _call_optional_async(
                            db,
                            "update_strategy_task_run",
                            task_run["id"],
                            status="failed",
                            error=str(exc),
                            result=task_result,
                        )

        # 有界并发执行所有研究任务
        if tasks:
            logger.info(
                "StrategyFactory: running %d research tasks with concurrency=%d",
                len(tasks), RESEARCH_TASK_CONCURRENCY,
            )
            await asyncio.gather(*[_run_one_task(t) for t in tasks], return_exceptions=True)

        completed_task_count = len([item for item in task_results if item.get("status") == "completed"])
        failed_task_count = len([item for item in task_results if item.get("status") == "failed"])
        positive_provider = sum(external_status_counts.get(key, 0) for key in ("succeeded", "fallback_only"))
        failed_provider = int(external_status_counts.get("failed", 0))
        skipped_provider = int(external_status_counts.get("skipped", 0))
        if not task_results:
            overall_status = "skipped"
        elif positive_provider > 0 and failed_provider == 0 and failed_task_count == 0:
            overall_status = "succeeded"
        elif failed_provider > 0 and positive_provider == 0 and skipped_provider == 0:
            overall_status = "failed"
        elif failed_provider > 0 or failed_task_count > 0:
            overall_status = "partial" if completed_task_count > 0 else "failed"
        elif skipped_provider == len(task_results) and failed_task_count == 0:
            overall_status = "succeeded"
        else:
            overall_status = "partial" if completed_task_count else "failed"
        lifecycle_metrics = self._aggregate_task_lifecycle_metrics(task_results)
        stage = {
            "ok": True,
            "task_count": len(tasks),
            "task_source_counts": task_source_counts,
            "event_task_count": event_task_count,
            "snapshot_task_count": int(task_source_counts.get("snapshot", 0)),
            "event_evidence_count": total_evidence_count,
            "completed_task_count": completed_task_count,
            "failed_task_count": failed_task_count,
            "task_scan": scan_report,
            "task_results": task_results,
            "generated_count": len(generated_candidates),
            "experiment_count": len(all_experiments),
            "task_run_ids": [item.get("task_run_id") for item in task_results if item.get("task_run_id") is not None],
            "external_llm_status": overall_status,
            "external_llm_status_counts": external_status_counts,
            "external_llm_attempt_count": total_attempt_count,
            "external_llm_selected_count": total_selected_count,
            "external_llm_last_error_type": last_error_type,
            "external_llm_last_error": last_error,
            "external_llm_elapsed_seconds": round(elapsed_seconds, 4),
            "research_task_concurrency": RESEARCH_TASK_CONCURRENCY,
            **lifecycle_metrics,
        }
        return {"stage": stage, "candidates": generated_candidates, "experiments": all_experiments}


    async def run_once(self) -> dict:
        """执行一次完整的策略工厂流程。"""
        from ...storage import get_db

        factory_pkg = get_strategy_factory_package()
        db = get_db()
        start = datetime.now()
        trace_id = f"strategy_factory:{uuid4().hex[:12]}"
        results: Dict[str, Any] = {
            "run_id": f"factory_run_{int(start.timestamp())}_{uuid4().hex[:8]}",
            "trace_id": trace_id,
            "started_at": start.isoformat(),
            "status": "running",
            "summary": {},
            "stages": {},
        }

        logger.info("StrategyFactory: starting daily cycle")

        try:
            collector = factory_pkg.DataCollector()
            snapshot = await collector.collect(db)
            results["snapshot_summary"] = {
                "date": snapshot.get("date"),
                "fear_greed": snapshot.get("fear_greed_index"),
                "fear_greed_index": snapshot.get("fear_greed_index"),
                "fg_level": snapshot.get("fg_level"),
                "listed_count": snapshot.get("listed_count", 0),
                "incubating_count": snapshot.get("incubating_count", 0),
                "degraded": bool(snapshot.get("degraded")),
                "completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "missing_sources": (snapshot.get("completeness") or {}).get("missing_sources") or [],
                "failure_reason_count": len(snapshot.get("failure_reasons") or []),
            }
            results["stages"]["collect"] = self._with_stage_meta("collect", trace_id, {
                **results["snapshot_summary"],
                "completeness": snapshot.get("completeness") or {},
            })

            factor_research = {}
            try:
                factor_builder_cls = getattr(factory_pkg, "FactorResearchBuilder", None)
                if factor_builder_cls is not None:
                    factor_research = await factor_builder_cls.build(db, snapshot)
                snapshot["factor_research"] = dict(factor_research or {})
                factor_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
                results["stages"]["factor_research"] = self._with_stage_meta("factor_research", trace_id, {
                    "active_factor_count": int(factor_summary.get("active_factor_count") or 0),
                    "ranked_factor_count": int(factor_summary.get("ranked_factor_count") or 0),
                    "top_factor_names": list(factor_summary.get("top_factor_names") or []),
                    "preferred_strategy_types": list(factor_summary.get("preferred_strategy_types") or []),
                    "degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                    "source_chain": list((snapshot.get("factor_research") or {}).get("source_chain") or []),
                })
            except Exception as exc:
                logger.warning("StrategyFactory: factor research stage failed: %s", exc)
                snapshot["factor_research"] = {
                    "active_factors": [],
                    "ranked_factors": [],
                    "positive_rising_factors": [],
                    "preferred_strategy_types": [],
                    "research_rationale": [str(exc)],
                    "source_chain": ["factor_research_error"],
                    "degraded": True,
                    "summary": {
                        "active_factor_count": 0,
                        "ranked_factor_count": 0,
                        "top_factor_names": [],
                        "preferred_strategy_types": [],
                        "degraded": True,
                    },
                }
                results["stages"]["factor_research"] = self._with_stage_meta("factor_research", trace_id, {
                    "active_factor_count": 0,
                    "ranked_factor_count": 0,
                    "top_factor_names": [],
                    "preferred_strategy_types": [],
                    "degraded": True,
                    "error": str(exc),
                }, default_ok=False)

            spawner = factory_pkg.StrategySpawner()
            candidates = spawner.spawn(snapshot)
            spawn_report = (
                spawner.get_last_report()
                if hasattr(spawner, "get_last_report")
                else {"summary": {"candidate_count": len(candidates)}}
            )
            results["stages"]["spawn"] = self._with_stage_meta("spawn", trace_id, {"count": len(candidates), **spawn_report})

            autonomy_batch = {"stage": {"generated_count": 0}, "candidates": [], "experiments": []}
            try:
                autonomy_batch = await self._run_autonomy_batches(db, snapshot)
                ai_candidates = autonomy_batch.get("candidates") or []
                candidates = [*candidates, *ai_candidates]
                results["stages"]["autonomy"] = self._with_stage_meta("autonomy", trace_id, autonomy_batch.get("stage") or {
                    "ok": True,
                    "generated_count": len(ai_candidates),
                })
            except Exception as exc:
                logger.warning("StrategyFactory: autonomy cycle failed: %s", exc)
                results["stages"]["autonomy"] = self._with_stage_meta(
                    "autonomy",
                    trace_id,
                    {"error": str(exc), "generated_count": 0},
                    default_ok=False,
                )

            backtest_filter = factory_pkg.BacktestFilter()
            supports_unified_gate_runner = bool(
                candidates
                and hasattr(factory_pkg, "run_gated_filter")
                and inspect.iscoroutinefunction(getattr(db, "get_klines", None))
            )
            deduplicator = factory_pkg.Deduplicator()
            submitter = factory_pkg.StrategySubmitter()
            supports_unified_submission_runner = bool(
                supports_unified_gate_runner
                and hasattr(factory_pkg, "run_gated_submission_pipeline")
            )

            if supports_unified_submission_runner:
                pipeline_run = await factory_pkg.run_gated_submission_pipeline(
                    candidates,
                    snapshot,
                    db,
                    backtest_filter=backtest_filter,
                    deduplicator=deduplicator,
                    submitter=submitter,
                    gated_runner=factory_pkg.run_gated_filter,
                    kline_cache=getattr(backtest_filter, "_kline_cache", None),
                )
                passed = list(pipeline_run.get("passed") or [])
                unique = list(pipeline_run.get("unique") or [])
                quality_gate_report = dict(pipeline_run.get("gate_report") or pipeline_run.get("quality_gate") or {})
                backtest_report = dict(pipeline_run.get("backtest_report") or {})
                submit_result = dict(pipeline_run.get("submit_result") or {})
            else:
                if supports_unified_gate_runner:
                    gate_run = await factory_pkg.run_gated_filter(
                        candidates,
                        db,
                        backtest_filter,
                        kline_cache=getattr(backtest_filter, "_kline_cache", None),
                    )
                    passed = list(gate_run.get("passed") or [])
                    quality_gate_report = dict(gate_run.get("gate_report") or gate_run.get("quality_gate") or {})
                else:
                    passed = await backtest_filter.filter(candidates, db)
                    quality_gate_report = {}

                backtest_report = (
                    (quality_gate_report.get("gate_2") or {}).get("report")
                    or (
                        backtest_filter.get_last_report()
                        if hasattr(backtest_filter, "get_last_report")
                        else {
                            "summary": {
                                "input_count": len(candidates),
                                "passed_count": len(passed),
                                "failed_count": max(len(candidates) - len(passed), 0),
                                "failed_reason_counts": {},
                                "thresholds_by_type": {},
                            },
                            "passed": [],
                            "failed": [],
                        }
                    )
                )
                if not quality_gate_report:
                    quality_gate_report = factory_pkg.build_legacy_gate_report(candidates, passed, backtest_report)

                unique = await deduplicator.deduplicate(passed, db)
                submit_result = await submitter.submit(unique, snapshot, db)
                quality_gate_report = factory_pkg.finalize_gate_report(quality_gate_report, submit_result)

            backtest_summary = backtest_report.get("summary") or {}
            results["stages"]["quality_gate"] = self._with_stage_meta("quality_gate", trace_id, quality_gate_report)
            results["stages"]["backtest"] = self._with_stage_meta("backtest", trace_id, {
                "input_count": backtest_summary.get("input_count", len(candidates)),
                "passed_count": backtest_summary.get("passed_count", len(passed)),
                "failed_count": backtest_summary.get("failed_count", max(len(candidates) - len(passed), 0)),
                **backtest_report,
            })
            results["stages"]["deduplicate"] = self._with_stage_meta("deduplicate", trace_id, deduplicator.get_last_report())
            results["stages"]["submit"] = self._with_stage_meta("submit", trace_id, submit_result)
            results["quality_gate"] = quality_gate_report
            results["gate_report"] = quality_gate_report

            eliminator = factory_pkg.EliminationChecker()
            eliminated = await eliminator.check(db, snapshot.get("fg_level", "neutral"))
            results["stages"]["elimination"] = self._with_stage_meta("elimination", trace_id, {"count": len(eliminated), "items": eliminated})

            elapsed = (datetime.now() - start).total_seconds()
            results["status"] = "success"
            results["completed_at"] = datetime.now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            autonomy_summary = results.get("stages", {}).get("autonomy") or {}
            vector_summary = self._aggregate_vector_submission_metrics(submit_result)
            task_scan_summary = dict((autonomy_summary.get("task_scan") or {}).get("summary") or {})
            task_source_counts = dict(
                autonomy_summary.get("task_source_counts")
                or task_scan_summary.get("task_sources")
                or {}
            )
            snapshot_task_count = int(
                autonomy_summary.get("snapshot_task_count")
                or task_source_counts.get("snapshot", 0)
            )
            autonomy_task_briefs = [
                {
                    "task_id": (item.get("task") or {}).get("task_id"),
                    "task_source": (item.get("task") or {}).get("task_source"),
                    "opportunity_type": (item.get("task") or {}).get("opportunity_type"),
                    "generation_limit": (item.get("task") or {}).get("generation_limit"),
                    "generated_count": item.get("generated_count", 0),
                }
                for item in list(autonomy_summary.get("task_results") or [])
            ]
            factor_research_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
            gate_0_summary = dict(quality_gate_report.get("gate_0") or {})
            gate_1_summary = dict(quality_gate_report.get("gate_1") or {})
            gate_2_summary = dict(quality_gate_report.get("gate_2") or {})
            results["summary"] = {
                "trace_id": trace_id,
                "fear_greed": snapshot.get("fear_greed_index"),
                "listed_count": snapshot.get("listed_count", 0),
                "snapshot_degraded": bool(snapshot.get("degraded")),
                "snapshot_completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "snapshot_failure_reason_count": len(snapshot.get("failure_reasons") or []),
                "candidates_spawned": len(candidates),
                "autonomy_generated": autonomy_summary.get("generated_count", 0),
                "autonomy_task_count": autonomy_summary.get("task_count", 0),
                "autonomy_completed_task_count": autonomy_summary.get("completed_task_count", 0),
                "autonomy_failed_task_count": autonomy_summary.get("failed_task_count", 0),
                "event_task_count": autonomy_summary.get("event_task_count", 0),
                "snapshot_task_count": snapshot_task_count,
                "task_source_counts": task_source_counts,
                "scanner_task_types": task_scan_summary.get("task_types") or {},
                "event_snapshot_mixed": bool(
                    int(autonomy_summary.get("event_task_count") or 0) > 0 and snapshot_task_count > 0
                ),
                "factor_research_used": bool(snapshot.get("factor_research")),
                "active_factor_count": int(factor_research_summary.get("active_factor_count") or 0),
                "top_factor_names": list(factor_research_summary.get("top_factor_names") or []),
                "factor_research_degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                "autonomy_task_briefs": autonomy_task_briefs,
                "event_evidence_count": autonomy_summary.get("event_evidence_count", 0),
                "autonomy_lifecycle_state_counts": autonomy_summary.get("lifecycle_state_counts") or {},
                "autonomy_phase_status_counts": autonomy_summary.get("phase_status_counts") or {},
                "autonomy_failed_phase_counts": autonomy_summary.get("failed_phase_counts") or {},
                "quota_fill_candidates": (spawn_report.get("summary") or {}).get("quota_fill_count", 0),
                "signal_trigger_candidates": (
                    (spawn_report.get("summary") or {}).get("signal_trigger_count", len(candidates))
                ),
                "gate_0_passed": gate_0_summary.get("passed_count"),
                "gate_0_failed": gate_0_summary.get("failed_count"),
                "gate_1_passed": gate_1_summary.get("passed_count"),
                "gate_1_failed": gate_1_summary.get("failed_count"),
                "gate_2_input": gate_2_summary.get("input_count", backtest_summary.get("input_count", len(candidates))),
                "gate_2_passed": gate_2_summary.get("passed_count", len(passed)),
                "candidates_passed_backtest": gate_2_summary.get("passed_count", len(passed)),
                "candidates_failed_backtest": backtest_summary.get("failed_count", max(len(candidates) - len(passed), 0)),
                "backtest_failed_reason_counts": backtest_summary.get("failed_reason_counts") or {},
                "candidates_after_dedup": len(unique),
                "submitted": submit_result.get("submitted", 0),
                "passed_quality_gate": submit_result.get("passed_quality_gate", 0),
                "gate_3_passed": submit_result.get("gate_3_passed", submit_result.get("passed_quality_gate", 0)),
                "gate_3_failed": submit_result.get(
                    "gate_3_failed",
                    max(
                        int(submit_result.get("submitted", 0)) - int(submit_result.get("passed_quality_gate", 0)),
                        0,
                    ),
                ),
                "gate_3_provisional_passed": submit_result.get("gate_3_provisional_passed", 0),
                "gate_3_failure_reason_topn": list(submit_result.get("gate_3_failure_reason_topn") or []),
                **vector_summary,
                "eliminated": len(eliminated),
                "external_llm_status": autonomy_summary.get("external_llm_status"),
                "external_llm_attempt_count": autonomy_summary.get("external_llm_attempt_count", 0),
                "external_llm_selected_count": autonomy_summary.get("external_llm_selected_count", 0),
                "external_llm_last_error_type": autonomy_summary.get("external_llm_last_error_type"),
                "external_llm_last_error": autonomy_summary.get("external_llm_last_error"),
                "external_llm_elapsed_seconds": autonomy_summary.get("external_llm_elapsed_seconds"),
                "elapsed_seconds": round(elapsed, 1),
            }

            logger.info(
                "StrategyFactory: completed in %.1fs — spawned %d, backtest passed %d, dedup %d, submitted %s, eliminated %d",
                elapsed,
                len(candidates),
                len(passed),
                len(unique),
                submit_result,
                len(eliminated),
            )
        except Exception as exc:
            elapsed = (datetime.now() - start).total_seconds()
            logger.error("StrategyFactory: run_once failed: %s", exc, exc_info=True)
            results["status"] = "failed"
            results["completed_at"] = datetime.now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            results["error"] = str(exc)
            results["summary"] = {"trace_id": trace_id, "elapsed_seconds": round(elapsed, 1), "error": str(exc)}

        results["pipeline"] = {
            "trace_id": trace_id,
            "status": results.get("status"),
            "stage_order": list(results.get("stages", {}).keys()),
            "total_stage_count": len(results.get("stages", {})),
        }

        self.last_run = datetime.now()
        self.last_result = results
        if hasattr(db, "save_strategy_factory_run"):
            try:
                await db.save_strategy_factory_run(results)
            except Exception as exc:
                logger.warning("StrategyFactory: failed to persist run %s: %s", results.get("run_id"), exc)
        return results

    def status(self) -> dict:
        return {
            "running": self._running,
            "schedule_mode": self.schedule_mode,
            "run_time": str(self.run_time),
            "last_run": str(self.last_run) if self.last_run else None,
            "last_result": self.last_result,
            "last_summary": (self.last_result or {}).get("summary") if self.last_result else None,
            "daily_run_count": self._daily_run_count,
            "max_daily_runs": self.max_daily_runs,
            "cycle_count": self._cycle_count,
        }
