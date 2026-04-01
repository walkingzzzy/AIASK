"""策略工厂调度器实现。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import inspect
import logging
import os
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from .legacy_bridge import get_compat_symbol
from ..domain.constants import (
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_STARTUP_DELAY_SEC,
    FACTORY_DAILY_RUN_TIME,
    FACTORY_ERROR_BACKOFF_SEC,
    FACTORY_EVENT_RUNTIME_MODE,
    FACTORY_FACTOR_AUTO_REFRESH,
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    FACTORY_MARKET_HOURS_INTERVAL_SEC,
    FACTORY_MAX_DAILY_RUNS,
    FACTORY_OFF_HOURS_INTERVAL_SEC,
    FACTORY_READINESS_HARD_BLOCK,
    FACTORY_READINESS_MIN_COMPLETION_RATIO,
    FACTORY_READINESS_MIN_SCORE,
    FACTORY_RUNTIME_ENABLED,
    FACTORY_SCHEDULE_MODE,
    FACTORY_STARTUP_WARMUP_ENABLED,
    FACTORY_STARTUP_WARMUP_FORCE,
    FACTORY_STARTUP_WARMUP_LIMIT,
    FACTORY_STARTUP_WARMUP_TASK_TYPE,
    RESEARCH_TASK_CONCURRENCY,
    is_factory_factor_auto_refresh_enabled,
    is_factory_readiness_hard_block_enabled,
    is_factory_runtime_enabled,
    resolve_event_runtime_mode,
)
from .cycle_runner import FactoryCycleRunner, FactoryRunContext
from .run_models import (
    FactoryRunStatus,
    StageStatus,
    build_stage_result,
    resolve_run_status,
    summarize_stage_results,
)
from .utils import _extract_event_context as _local_extract_event_context
from ..domain.targets import _extract_target_codes_from_payload, _normalize_target_codes
from ..infrastructure.mcp_services import get_autonomy_lifecycle_runtime, get_runtime_warmup_runner

if TYPE_CHECKING:
    from ..api.contracts import (
        AutonomyGateway,
        FactorResearchGateway,
        IncubationGateway,
        RiskGateway,
        ValidationGateway,
        VectorSearchGateway,
    )
    from ..infrastructure.mcp_adapters import MCPRuntimeAdapters

logger = logging.getLogger(__name__)

_MARKET_TIMEZONE_NAME = str(os.getenv("STRATEGY_MARKET_TIMEZONE") or "Asia/Shanghai").strip() or "Asia/Shanghai"
try:
    _MARKET_TIMEZONE = ZoneInfo(_MARKET_TIMEZONE_NAME)
except Exception:
    _MARKET_TIMEZONE = timezone(timedelta(hours=8))

_FALLBACK_AUTONOMY_PHASE_ORDER = (
    "prepared",
    "generating",
    "reviewing",
    "recording",
    "submitting",
    "completed",
)


def _summarize_autonomy_lifecycle_fallback(lifecycle: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(lifecycle or {})
    return {
        "state": payload.get("state"),
        "current_phase": payload.get("current_phase"),
        "failed_phase": payload.get("failed_phase"),
        "terminal_phase": payload.get("terminal_phase"),
        "phase_status_counts": dict(payload.get("phase_status_counts") or {}),
        "completed_phase_count": int(payload.get("completed_phase_count") or 0),
        "event_count": int(payload.get("event_count") or len(payload.get("events") or [])),
        "phase_order": list(payload.get("phase_order") or _FALLBACK_AUTONOMY_PHASE_ORDER),
    }


def _load_autonomy_lifecycle_runtime():
    try:
        return get_autonomy_lifecycle_runtime()
    except Exception:
        return SimpleNamespace(
            AUTONOMY_PHASE_ORDER=_FALLBACK_AUTONOMY_PHASE_ORDER,
            summarize_autonomy_lifecycle=_summarize_autonomy_lifecycle_fallback,
        )


_AUTONOMY_LIFECYCLE_RUNTIME = _load_autonomy_lifecycle_runtime()
AUTONOMY_PHASE_ORDER = _AUTONOMY_LIFECYCLE_RUNTIME.AUTONOMY_PHASE_ORDER
summarize_autonomy_lifecycle = _AUTONOMY_LIFECYCLE_RUNTIME.summarize_autonomy_lifecycle

_LEGACY_FACTORY_SCHEDULER_MODULE = "akshare_mcp.services.strategy_factory.factory_scheduler"
_LEGACY_UTILS_MODULE = "akshare_mcp.services.strategy_factory.utils"

def _extract_event_context(*args, **kwargs):
    return get_compat_symbol(
        _LEGACY_UTILS_MODULE,
        "_extract_event_context",
        _local_extract_event_context,
    )(*args, **kwargs)


def get_strategy_factory_package():
    from .runtime import get_strategy_factory_package as _runtime_get_strategy_factory_package

    target = get_compat_symbol(
        _LEGACY_FACTORY_SCHEDULER_MODULE,
        "get_strategy_factory_package",
        _runtime_get_strategy_factory_package,
        exclude=get_strategy_factory_package,
    )
    return target()


async def _call_optional_async(target: Any, method_name: str, *args, default=None, **kwargs):
    compat = get_compat_symbol(
        _LEGACY_FACTORY_SCHEDULER_MODULE,
        "_call_optional_async",
        None,
        exclude=_call_optional_async,
    )
    if callable(compat):
        result = compat(target, method_name, *args, default=default, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    from .runtime import _call_optional_async as _runtime_call_optional_async

    return await _runtime_call_optional_async(target, method_name, *args, default=default, **kwargs)


class _StrategyFactorySchedulerLoopMixin:
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
                target = datetime.combine(now.date(), self.run_time, tzinfo=self._market_timezone)
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
                    now = self._now()
                    today_str = now.strftime("%Y-%m-%d")

                    # 日期变更 → 重置每日计数
                    if self._daily_run_date != today_str:
                        self._daily_run_date = today_str
                        self._daily_run_count = 0

                    # 达到每日上限 → 睡到午夜
                    if self._daily_run_count >= self.max_daily_runs:
                        tomorrow = datetime.combine(now.date() + timedelta(days=1), time(0, 0), tzinfo=self._market_timezone)
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

        async def _generate_for_research_task(self, autonomy_gateway, db, snapshot: dict, task: dict) -> dict:
            limit = max(1, min(int(task.get("generation_limit") or AUTONOMY_CANDIDATES_PER_TASK), 10))
            source = f"strategy_factory:{task.get('opportunity_type') or 'general'}"
            gateway_db = self._adapt_gateway_repository(db)
            return await autonomy_gateway.generate_factory_candidates(
                gateway_db,
                snapshot,
                limit=limit,
                research_task=task,
                source=source,
            )

        async def _persist_run_result(
            self,
            db,
            results: dict[str, Any],
            *,
            persistence_failures: list[dict[str, Any]],
        ) -> None:
            if not hasattr(db, "save_strategy_factory_run"):
                return
            try:
                await db.save_strategy_factory_run(results)
            except Exception as exc:
                logger.warning("StrategyFactory: failed to persist run %s: %s", results.get("run_id"), exc)
                self._record_persistence_failure(
                    persistence_failures,
                    "save_strategy_factory_run",
                    exc,
                    stage="run",
                )
                self._apply_run_audit(results, persistence_failures=persistence_failures)

        async def _prepare_shared_generation_context(self, autonomy_gateway, db, snapshot: dict[str, Any]) -> bool:
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            builder = getattr(generation_service, "build_shared_generation_context", None)
            if not callable(builder):
                return False
            try:
                snapshot["_shared_generation_context"] = await _call_optional_async(
                    generation_service,
                    "build_shared_generation_context",
                    db,
                    snapshot=snapshot,
                    default={},
                )
                return bool(snapshot.get("_shared_generation_context"))
            except Exception as exc:
                logger.warning("StrategyFactory: shared generation context preload failed: %s", exc)
                return False

        @staticmethod
        def _resolve_external_llm_concurrency_limit(autonomy_gateway) -> Optional[int]:
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            llm_generator = getattr(generation_service, "llm_generator", None) or getattr(autonomy_target, "llm_generator", None)
            external_provider = getattr(llm_generator, "external_provider", None)
            if external_provider is None:
                return None
            try:
                if callable(getattr(external_provider, "is_enabled", None)) and not external_provider.is_enabled():
                    return None
            except Exception:
                return None
            try:
                limit = int(getattr(getattr(external_provider, "config", None), "max_concurrency", 0) or 0)
            except Exception:
                return None
            return max(1, limit) if limit > 0 else None

        @classmethod
        def _resolve_research_task_concurrency(cls, autonomy_gateway) -> int:
            effective = RESEARCH_TASK_CONCURRENCY
            provider_limit = cls._resolve_external_llm_concurrency_limit(autonomy_gateway)
            if provider_limit is not None:
                effective = min(effective, provider_limit)
            return max(1, effective)

        async def _run_autonomy_batches(self, db, snapshot: dict) -> dict:
            factory_pkg = get_strategy_factory_package()
            scanner = factory_pkg.MarketOpportunityScanner()
            scan_report = await scanner.scan(db, snapshot)
            tasks = list(scan_report.get("tasks") or [])
            scan_summary = dict(scan_report.get("summary") or {})
            task_source_counts = dict(scan_summary.get("task_sources") or self._build_task_source_counts(tasks))
            event_task_count = int(scan_summary.get("event_task_count") or task_source_counts.get("event_driven", 0))
            autonomy_gateway = self._get_autonomy_gateway()
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
            persistence_failures: List[dict[str, Any]] = []
            _agg_lock = asyncio.Lock()
            shared_generation_context_preloaded = await self._prepare_shared_generation_context(autonomy_gateway, db, snapshot)
            effective_research_concurrency = self._resolve_research_task_concurrency(autonomy_gateway)

            sem = asyncio.Semaphore(effective_research_concurrency)

            async def _run_one_task(task: dict) -> None:
                nonlocal total_attempt_count, total_selected_count, total_evidence_count
                nonlocal last_error_type, last_error, elapsed_seconds
                evidence_rows: List[dict] = []
                task_run: dict[str, Any] = {"id": None}
                enriched_task = dict(task or {})
                failed_phase = "preparing"
                async with sem:
                    try:
                        try:
                            evidence_rows = await self._persist_task_evidence(
                                db,
                                {**task, "snapshot_date": snapshot.get("date")},
                            )
                        except Exception as exc:
                            async with _agg_lock:
                                self._record_persistence_failure(
                                    persistence_failures,
                                    "save_factory_task_evidence",
                                    exc,
                                    stage="autonomy",
                                )
                            evidence_rows = []
                        event_context = _extract_event_context(task)
                        try:
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
                        except Exception as exc:
                            async with _agg_lock:
                                self._record_persistence_failure(
                                    persistence_failures,
                                    "save_strategy_task_run",
                                    exc,
                                    stage="autonomy",
                                )
                            task_run = {"id": None}
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
                        failed_phase = "generating"
                        cycle = await self._generate_for_research_task(autonomy_gateway, db, snapshot, enriched_task)
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
                        task_level_attempt = len(external_provider.get("requests") or [])
                        task_level_selected = int(external_provider.get("selected_count") or 0)
                        async with _agg_lock:
                            for candidate in self._extract_cycle_candidates(cycle):
                                enriched = self._enrich_candidate_targeting(candidate, enriched_task)
                                params = dict(enriched.get("params") or {})
                                params["task_attempt_count"] = task_level_attempt
                                params["task_selected_count"] = task_level_selected
                                enriched["params"] = params
                                generated_candidates.append(enriched)
                            all_experiments.extend(self._extract_cycle_experiments(cycle))
                            external_status_counts[status] = external_status_counts.get(status, 0) + 1
                            total_attempt_count += task_level_attempt
                            total_selected_count += task_level_selected
                            total_evidence_count += len(evidence_rows)
                            if external_provider.get("last_error_type"):
                                last_error_type = external_provider.get("last_error_type")
                                last_error = external_provider.get("last_error")
                            elapsed_seconds += float(external_provider.get("elapsed_seconds") or 0.0)
                            task_results.append(task_result)
                        if task_run.get("id") is not None:
                            try:
                                await _call_optional_async(
                                    db,
                                    "update_strategy_task_run",
                                    task_run["id"],
                                    status="completed",
                                    result=task_result,
                                )
                            except Exception as exc:
                                logger.warning("StrategyFactory: update task_run completed failed: %s", exc)
                                async with _agg_lock:
                                    self._record_persistence_failure(
                                        persistence_failures,
                                        "update_strategy_task_run",
                                        exc,
                                        stage="autonomy",
                                    )
                    except Exception as exc:
                        failure_lifecycle = dict(getattr(exc, "autonomy_lifecycle", {}) or {})
                        if not failure_lifecycle:
                            failure_lifecycle = {
                                "state": "failed",
                                "current_phase": failed_phase,
                                "failed_phase": failed_phase,
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
                            try:
                                await _call_optional_async(
                                    db,
                                    "update_strategy_task_run",
                                    task_run["id"],
                                    status="failed",
                                    error=str(exc),
                                    result=task_result,
                                )
                            except Exception as update_exc:
                                logger.warning("StrategyFactory: update task_run failed failed: %s", update_exc)
                                async with _agg_lock:
                                    self._record_persistence_failure(
                                        persistence_failures,
                                        "update_strategy_task_run",
                                        update_exc,
                                        stage="autonomy",
                                    )

            # 有界并发执行所有研究任务
            if tasks:
                logger.info(
                    "StrategyFactory: running %d research tasks with concurrency=%d",
                    len(tasks), effective_research_concurrency,
                )
                await asyncio.gather(*[_run_one_task(t) for t in tasks])

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
                "research_task_concurrency": effective_research_concurrency,
                "configured_research_task_concurrency": RESEARCH_TASK_CONCURRENCY,
                "shared_generation_context_preloaded": shared_generation_context_preloaded,
                "persistence_failures": persistence_failures,
                "persistence_failure_count": len(persistence_failures),
                **lifecycle_metrics,
            }
            return {"stage": stage, "candidates": generated_candidates, "experiments": all_experiments}

        async def run_once(self, db=None) -> dict:
            """执行一次完整的策略工厂流程。"""
            db = self._load_db() if db is None else db
            start = self._now()
            context = FactoryRunContext(
                db=db,
                factory_pkg=get_strategy_factory_package(),
                runtime_adapters=self._runtime_adapters,
                start=start,
                trace_id=f"strategy_factory:{uuid4().hex[:12]}",
                run_id=f"factory_run_{int(start.timestamp())}_{uuid4().hex[:8]}",
            )
            from . import factory_scheduler as scheduler_module

            outcome = await scheduler_module.FactoryCycleRunner(self, context).run()
            results = outcome.result
            self.last_run = self._now()
            self.last_result = results
            await self._persist_run_result(
                db,
                results,
                persistence_failures=outcome.persistence_failures,
            )
            return results

        def status(self) -> dict:
            return {
                "running": self._running,
                "schedule_mode": self.schedule_mode,
                "run_time": str(self.run_time),
                "runtime_enabled": is_factory_runtime_enabled(),
                "event_runtime_mode": resolve_event_runtime_mode(),
                "factor_auto_refresh_enabled": is_factory_factor_auto_refresh_enabled(),
                "factor_refresh_timeout_sec": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
                "readiness_hard_block_enabled": is_factory_readiness_hard_block_enabled(),
                "readiness_min_score": FACTORY_READINESS_MIN_SCORE,
                "readiness_min_completion_ratio": FACTORY_READINESS_MIN_COMPLETION_RATIO,
                "last_run": str(self.last_run) if self.last_run else None,
                "last_result": self.last_result,
                "last_summary": (self.last_result or {}).get("summary") if self.last_result else None,
                "daily_run_count": self._daily_run_count,
                "max_daily_runs": self.max_daily_runs,
                "cycle_count": self._cycle_count,
            }
