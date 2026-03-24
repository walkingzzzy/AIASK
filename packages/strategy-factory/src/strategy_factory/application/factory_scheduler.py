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
from .runtime import (
    _call_optional_async as _runtime_call_optional_async,
    get_strategy_factory_package as _runtime_get_strategy_factory_package,
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
    return await _runtime_call_optional_async(target, method_name, *args, default=default, **kwargs)


class StrategyFactoryScheduler:
    """策略工厂调度器，支持 continuous（24/7循环）和 daily（每日定时）两种模式。"""

    def __init__(
        self,
        run_time: Optional[time] = None,
        *,
        db_provider: Optional[Callable[[], Any]] = None,
        vector_gateway: Optional["VectorSearchGateway"] = None,
        validation_gateway: Optional["ValidationGateway"] = None,
        risk_gateway: Optional["RiskGateway"] = None,
        incubation_gateway: Optional["IncubationGateway"] = None,
        autonomy_gateway: Optional["AutonomyGateway"] = None,
        factor_research_gateway: Optional["FactorResearchGateway"] = None,
        runtime_adapters: Optional["MCPRuntimeAdapters"] = None,
    ):
        self.schedule_mode: str = FACTORY_SCHEDULE_MODE if FACTORY_SCHEDULE_MODE in ("continuous", "daily") else "continuous"
        self._market_timezone = _MARKET_TIMEZONE
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
        self._shutdown_grace_sec: float = float(
            os.getenv("STRATEGY_FACTORY_SHUTDOWN_GRACE_SEC", "0.25") or 0.25
        )
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None
        self._daily_run_count: int = 0
        self._daily_run_date: Optional[str] = None  # "YYYY-MM-DD"
        self._cycle_count: int = 0
        self._db_provider = db_provider
        self._runtime_adapters = runtime_adapters
        self._vector_gateway = vector_gateway
        self._validation_gateway = validation_gateway
        self._risk_gateway = risk_gateway
        self._incubation_gateway = incubation_gateway
        self._autonomy_gateway = autonomy_gateway
        self._factor_research_gateway = factor_research_gateway
        if runtime_adapters is not None:
            self._vector_gateway = self._vector_gateway or getattr(runtime_adapters, "vector_search", None)
            self._validation_gateway = self._validation_gateway or getattr(runtime_adapters, "validation", None)
            self._risk_gateway = self._risk_gateway or getattr(runtime_adapters, "risk", None)
            self._incubation_gateway = self._incubation_gateway or getattr(runtime_adapters, "incubation", None)
            self._autonomy_gateway = self._autonomy_gateway or getattr(runtime_adapters, "autonomy", None)
            self._factor_research_gateway = self._factor_research_gateway or getattr(runtime_adapters, "factor_research", None)

    def _now(self) -> datetime:
        return datetime.now(self._market_timezone)

    def start(self):
        if self._running:
            logger.warning("StrategyFactory already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="strategy-factory-scheduler")
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

    async def shutdown(self):
        self._running = False
        task = self._task
        self._task = None
        if task is None:
            logger.info("StrategyFactory stopped")
            return
        if not task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(task),
                    timeout=max(0.0, self._shutdown_grace_sec),
                )
            except asyncio.TimeoutError:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        else:
            with suppress(asyncio.CancelledError):
                await task
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
    def _merge_explicit_stock_pool(base: Optional[dict], target_symbols: list[str]) -> dict:
        pool = dict(base or {})
        normalized = _normalize_target_codes(target_symbols, limit=12)
        if not normalized:
            return pool
        pool["selection_mode"] = pool.get("selection_mode") or "explicit"
        pool["symbols"] = normalized
        return pool

    @classmethod
    def _enrich_candidate_targeting(cls, candidate: Optional[dict], task: Optional[dict] = None) -> dict:
        item = dict(candidate or {})
        if not item:
            return {}

        base_task = dict(task or {})
        current_task = dict(item.get("research_task") or {})
        merged_task = {**base_task, **current_task}
        merged_task_event_context = {
            **dict(base_task.get("event_context") or {}),
            **dict(current_task.get("event_context") or {}),
        }
        if merged_task_event_context:
            merged_task["event_context"] = merged_task_event_context
        if merged_task:
            item["research_task"] = merged_task

        merged_event_context = {
            **merged_task_event_context,
            **dict(item.get("event_context") or {}),
        }
        if merged_event_context:
            item["event_context"] = merged_event_context

        target_symbols = _extract_target_codes_from_payload(item, limit=12)
        if not target_symbols:
            return item

        item["target_symbols"] = list(target_symbols)
        item["stock_pool"] = cls._merge_explicit_stock_pool(item.get("stock_pool"), target_symbols)

        params = dict(item.get("params") or {})
        if params:
            params["target_symbols"] = list(target_symbols)
            params["stock_pool"] = cls._merge_explicit_stock_pool(params.get("stock_pool"), target_symbols)
            if merged_task and not params.get("research_task"):
                params["research_task"] = dict(merged_task)
            dsl = dict(params.get("dsl") or {})
            if dsl:
                metadata = dict(dsl.get("metadata") or {})
                metadata["target_symbols"] = list(target_symbols)
                metadata["stock_pool"] = cls._merge_explicit_stock_pool(metadata.get("stock_pool"), target_symbols)
                dsl["metadata"] = metadata
                params["dsl"] = dsl
            item["params"] = params

        tags = list(item.get("tags") or [])
        if "targeted_universe" not in tags:
            item["tags"] = [*tags, "targeted_universe"]
        return item

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
    def _compact_active_candidate_pool(
        factor_research: Optional[dict[str, Any]],
        *,
        candidate_limit: int = 5,
        summary_limit: int = 5,
    ) -> dict[str, Any]:
        artifact = dict(factor_research or {})
        active_pool = dict(artifact.get("active_candidate_pool") or {})

        def _normalize_list(value: Any) -> list[str]:
            if isinstance(value, (list, tuple, set)):
                return [str(item).strip() for item in value if str(item).strip()]
            token = str(value or "").strip()
            return [token] if token else []

        def _normalize_risk_audit(value: Any) -> dict[str, Any]:
            payload = dict(value or {}) if isinstance(value, dict) else {}
            return {
                "lookahead_risk_level": str(payload.get("lookahead_risk_level") or "").strip() or None,
                "multiple_testing_risk_level": str(payload.get("multiple_testing_risk_level") or "").strip() or None,
                "overall_risk_level": str(payload.get("overall_risk_level") or "").strip() or None,
                "blocked": bool(payload.get("blocked")),
                "block_reasons": _normalize_list(payload.get("block_reasons")),
            }

        top_candidates: list[dict[str, Any]] = []
        for item in list(active_pool.get("top_candidates") or [])[: max(1, int(candidate_limit or 5))]:
            if not isinstance(item, dict):
                continue
            top_candidates.append(
                {
                    "artifact_id": str(item.get("artifact_id") or "").strip() or None,
                    "name": str(item.get("name") or "").strip() or None,
                    "family": str(item.get("family") or "").strip() or None,
                    "expected_regime": _normalize_list(item.get("expected_regime")),
                    "grade": str(item.get("grade") or "").strip() or None,
                    "recommendation": str(item.get("recommendation") or "").strip() or None,
                    "total_score": item.get("total_score"),
                    "risk_audit": _normalize_risk_audit(item.get("risk_audit")),
                }
            )

        excluded_candidates: list[dict[str, Any]] = []
        for item in list(active_pool.get("excluded_candidates") or [])[: max(1, int(candidate_limit or 5))]:
            if not isinstance(item, dict):
                continue
            excluded_candidates.append(
                {
                    "artifact_id": str(item.get("artifact_id") or "").strip() or None,
                    "name": str(item.get("name") or "").strip() or None,
                    "family": str(item.get("family") or "").strip() or None,
                    "grade": str(item.get("grade") or "").strip() or None,
                    "recommendation": str(item.get("recommendation") or "").strip() or None,
                    "total_score": item.get("total_score"),
                    "reasons": _normalize_list(item.get("reasons")),
                    "risk_audit": _normalize_risk_audit(item.get("risk_audit")),
                }
            )

        family_summary = [
            {
                "family": str(item.get("family") or "").strip() or None,
                "count": int(item.get("count") or 0),
                "promote_count": int(item.get("promote_count") or 0),
                "review_count": int(item.get("review_count") or 0),
                "avg_total_score": item.get("avg_total_score"),
                "max_total_score": item.get("max_total_score"),
            }
            for item in list(active_pool.get("family_summary") or [])[: max(1, int(summary_limit or 5))]
            if isinstance(item, dict)
        ]
        regime_summary = [
            {
                "regime": str(item.get("regime") or "").strip() or None,
                "count": int(item.get("count") or 0),
            }
            for item in list(active_pool.get("regime_summary") or [])[: max(1, int(summary_limit or 5))]
            if isinstance(item, dict)
        ]

        return {
            "source_count": int(active_pool.get("source_count") or 0),
            "count": int(active_pool.get("count") or 0),
            "excluded_count": int(active_pool.get("excluded_count") or 0),
            "top_candidates": top_candidates,
            "excluded_candidates": excluded_candidates,
            "exclusion_reason_counts": {
                str(key): int(value or 0)
                for key, value in dict(active_pool.get("exclusion_reason_counts") or {}).items()
                if str(key).strip()
            },
            "family_summary": family_summary,
            "regime_summary": regime_summary,
        }

    @classmethod
    def _compact_factor_research_snapshot(
        cls,
        factor_research: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        artifact = dict(factor_research or {})
        summary = dict(artifact.get("summary") or {})
        freshness_repair = dict(artifact.get("freshness_repair") or {})
        return {
            "summary": {
                "active_factor_count": int(summary.get("active_factor_count") or 0),
                "active_candidate_count": int(summary.get("active_candidate_count") or 0),
                "governed_source_candidate_count": int(summary.get("governed_source_candidate_count") or 0),
                "governed_blocked_candidate_count": int(summary.get("governed_blocked_candidate_count") or 0),
                "ranked_factor_count": int(summary.get("ranked_factor_count") or 0),
                "top_factor_names": list(summary.get("top_factor_names") or []),
                "top_candidate_names": list(summary.get("top_candidate_names") or []),
                "active_family_names": list(summary.get("active_family_names") or []),
                "active_regime_names": list(summary.get("active_regime_names") or []),
                "preferred_strategy_types": list(summary.get("preferred_strategy_types") or []),
                "factor_source_mode": summary.get("factor_source_mode"),
                "governed_exclusion_reason_counts": dict(summary.get("governed_exclusion_reason_counts") or {}),
                "governed_risk_counts": dict(summary.get("governed_risk_counts") or {}),
                "degraded": bool(summary.get("degraded")),
                "freshness_days": summary.get("freshness_days"),
                "latest_factor_date": summary.get("latest_factor_date"),
                "stale": bool(summary.get("stale")),
                "quality_flags": list(summary.get("quality_flags") or []),
            },
            "active_candidate_pool": cls._compact_active_candidate_pool(artifact),
            "degraded": bool(artifact.get("degraded")),
            "source_chain": list(artifact.get("source_chain") or []),
            "freshness_repair": {
                "refresh_attempted": bool(freshness_repair.get("refresh_attempted")),
                "refresh_status": freshness_repair.get("refresh_status"),
                "refresh_trigger": freshness_repair.get("refresh_trigger"),
            },
        }

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
    def _with_stage_meta(
        stage_name: str,
        trace_id: str,
        payload: Optional[dict],
        *,
        status: StageStatus | str,
        ok: Optional[bool] = None,
        hard_failure: bool = False,
        degraded: Optional[bool] = None,
        skip_reason: Optional[str] = None,
    ) -> dict:
        return build_stage_result(
            stage_name,
            trace_id,
            payload,
            status=status,
            ok=ok,
            hard_failure=hard_failure,
            degraded=degraded,
            skip_reason=skip_reason,
        )

    @staticmethod
    def _record_persistence_failure(
        failures: list[dict[str, Any]],
        operation: str,
        exc: Exception,
        *,
        stage: Optional[str] = None,
    ) -> None:
        failures.append(
            {
                "operation": str(operation or "unknown"),
                "stage": str(stage or "").strip() or None,
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    @classmethod
    def _build_pipeline_payload(
        cls,
        results: dict[str, Any],
        *,
        stage_summary: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        summary = dict(stage_summary or summarize_stage_results(results.get("stages") or {}))
        failed_stages = list(summary.get("failed_stages") or [])
        partial_stages = list(summary.get("partial_stages") or [])
        return {
            "trace_id": results.get("trace_id"),
            "status": results.get("status"),
            "stage_order": list(results.get("stages", {}).keys()),
            "total_stage_count": len(results.get("stages", {})),
            "failed_stage": failed_stages[0] if failed_stages else None,
            "partial_stage": partial_stages[0] if partial_stages else None,
            "stage_status_counts": dict(summary.get("stage_status_counts") or {}),
        }

    @classmethod
    def _apply_run_audit(
        cls,
        results: dict[str, Any],
        *,
        persistence_failures: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        failures = list(persistence_failures or [])
        stage_summary = summarize_stage_results(results.get("stages") or {})
        summary = dict(results.get("summary") or {})
        combined_skip_reasons: list[str] = []
        for reason in list(stage_summary.get("skip_reasons") or []) + list(summary.get("skip_reasons") or []):
            token = str(reason or "").strip()
            if token and token not in combined_skip_reasons:
                combined_skip_reasons.append(token)
        if summary.get("skip_reason"):
            token = str(summary.get("skip_reason") or "").strip()
            if token and token not in combined_skip_reasons:
                combined_skip_reasons.insert(0, token)

        resolved_status = resolve_run_status(
            results.get("status") or FactoryRunStatus.SUCCESS.value,
            results.get("stages") or {},
            persistence_failure_count=len(failures),
        )
        results["status"] = resolved_status.value
        summary.update(stage_summary)
        summary["skip_reasons"] = combined_skip_reasons
        summary["persistence_failure_count"] = len(failures)
        summary["persistence_failures"] = failures
        if not summary.get("skip_reason") and combined_skip_reasons:
            summary["skip_reason"] = combined_skip_reasons[0]
        results["summary"] = summary
        results["pipeline"] = cls._build_pipeline_payload(results, stage_summary=stage_summary)
        return results

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except Exception:
            return float(default)

    @classmethod
    def _summarize_refresh_result(cls, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"result_type": type(payload).__name__}
        summary: dict[str, Any] = {}
        for key in ("computed", "errors", "elapsed_seconds", "universe_size", "source", "asof_time"):
            if payload.get(key) is not None:
                summary[key] = payload.get(key)
        flags = list(payload.get("quality_flags") or [])
        if flags:
            summary["quality_flags"] = flags
        return summary

    @staticmethod
    def _aggregate_backtest_audit_metrics(backtest_report: Optional[dict]) -> dict[str, Any]:
        report = dict(backtest_report or {})
        entries = list(report.get("passed") or []) + list(report.get("failed") or [])
        contamination_warning_count = 0
        cost_audit_missing_count = 0
        for entry in entries:
            backtest_result = dict((entry or {}).get("backtest_result") or {})
            contamination = dict(backtest_result.get("contamination_summary") or {})
            validation_focus = str(backtest_result.get("validation_focus") or "").strip().lower()
            if validation_focus == "event_target_only" and (
                bool(contamination.get("representative_included")) or bool(contamination.get("mixed_layer_used"))
            ):
                contamination_warning_count += 1
            if not backtest_result.get("cost_assumptions") or not backtest_result.get("position_assumption"):
                cost_audit_missing_count += 1
        return {
            "event_window_contamination_warning_count": contamination_warning_count,
            "cost_audit_missing_count": cost_audit_missing_count,
        }

    @classmethod
    def _aggregate_submission_audit_metrics(cls, submit_result: Optional[dict]) -> dict[str, Any]:
        payload = dict(submit_result or {})
        strategies = list(payload.get("strategies") or [])
        attempt_adjusted_gate_failed = 0
        attempt_penalties: list[float] = []
        refresh_metrics_only_count = 0
        spawn_revision_from_existing_count = 0
        constraint_violation_count = 0
        intersection_ratios: list[float] = []
        universe_expansion_count = 0
        preference_mismatch_warning_count = 0
        deflated_sharpe_values: list[float] = []
        formal_deflated_sharpe_values: list[float] = []
        high_pbo_proxy_count = 0
        high_pbo_count = 0
        formal_multiple_testing_count = 0
        weak_white_reality_check_count = 0
        weak_hansen_spa_count = 0

        for item in strategies:
            summary = dict(item or {})
            gate = dict(summary.get("gate_3") or {})
            attempt_adjustment = dict(gate.get("attempt_adjustment") or {})
            penalty = cls._safe_float(attempt_adjustment.get("penalty"))
            if penalty > 0:
                attempt_penalties.append(penalty)
                if not gate.get("passed"):
                    attempt_adjusted_gate_failed += 1
            deflated_proxy = gate.get("deflated_sharpe_proxy")
            if deflated_proxy is not None:
                deflated_sharpe_values.append(cls._safe_float(deflated_proxy))
            deflated_formal = gate.get("deflated_sharpe_ratio")
            if deflated_formal is not None:
                formal_deflated_sharpe_values.append(cls._safe_float(deflated_formal))
            if cls._safe_float(gate.get("pbo_proxy")) > 0.55:
                high_pbo_proxy_count += 1
            if str(gate.get("multiple_testing_mode") or "").strip().lower() == "formal_runtime":
                formal_multiple_testing_count += 1
            pbo_effective = gate.get("pbo")
            if pbo_effective is None:
                pbo_effective = gate.get("pbo_proxy")
            if cls._safe_float(pbo_effective) > 0.55:
                high_pbo_count += 1
            white_effective = gate.get("white_reality_check_pvalue")
            if white_effective is None:
                white_effective = gate.get("reality_check_pvalue_proxy")
            if cls._safe_float(white_effective) > 0.2:
                weak_white_reality_check_count += 1
            spa_effective = gate.get("hansen_spa_pvalue")
            if spa_effective is None:
                spa_effective = gate.get("spa_pvalue_proxy")
            if cls._safe_float(spa_effective) > 0.2:
                weak_hansen_spa_count += 1

            constraint_check = dict(summary.get("constraint_check") or {})
            if constraint_check.get("constraint_violation"):
                constraint_violation_count += 1
            if constraint_check.get("expansion_applied"):
                universe_expansion_count += 1
            intersection_ratio = constraint_check.get("intersection_ratio")
            if intersection_ratio is not None:
                intersection_ratios.append(cls._safe_float(intersection_ratio))
            if any("preference" in str(code or "").lower() for code in list(summary.get("warning_codes") or [])):
                preference_mismatch_warning_count += 1

            refresh_mode = str(
                summary.get("refresh_mode")
                or dict(summary.get("dedup_result") or {}).get("refresh_mode")
                or ""
            ).strip().lower()
            if refresh_mode == "refresh_metrics_only":
                refresh_metrics_only_count += 1
            elif refresh_mode == "spawn_revision_from_existing":
                spawn_revision_from_existing_count += 1

        return {
            "constraint_violation_count": constraint_violation_count,
            "target_symbol_intersection_ratio_avg": round(sum(intersection_ratios) / len(intersection_ratios), 4)
            if intersection_ratios
            else 0.0,
            "universe_expansion_count": universe_expansion_count,
            "preference_mismatch_warning_count": preference_mismatch_warning_count,
            "attempt_adjusted_gate_failed": attempt_adjusted_gate_failed,
            "attempt_adjusted_score_avg": round(sum(attempt_penalties) / len(attempt_penalties), 4)
            if attempt_penalties
            else 0.0,
            "deflated_sharpe_proxy_avg": round(sum(deflated_sharpe_values) / len(deflated_sharpe_values), 4)
            if deflated_sharpe_values
            else 0.0,
            "deflated_sharpe_ratio_avg": round(sum(formal_deflated_sharpe_values) / len(formal_deflated_sharpe_values), 4)
            if formal_deflated_sharpe_values
            else 0.0,
            "high_pbo_proxy_count": high_pbo_proxy_count,
            "high_pbo_count": high_pbo_count,
            "formal_multiple_testing_count": formal_multiple_testing_count,
            "weak_white_reality_check_count": weak_white_reality_check_count,
            "weak_hansen_spa_count": weak_hansen_spa_count,
            "refresh_metrics_only_count": refresh_metrics_only_count,
            "spawn_revision_from_existing_count": spawn_revision_from_existing_count,
        }

    @classmethod
    def _inject_factor_refresh_meta(cls, artifact: Optional[dict], refresh_meta: dict[str, Any]) -> dict[str, Any]:
        data = dict(artifact or {})
        summary = dict(data.get("summary") or {})
        scheduler_status = dict(data.get("scheduler_status") or {})
        normalized_meta = dict(refresh_meta or {})
        summary.update(
            {
                "auto_refresh_enabled": bool(normalized_meta.get("auto_refresh_enabled")),
                "refresh_attempted": bool(normalized_meta.get("refresh_attempted")),
                "refresh_status": normalized_meta.get("refresh_status"),
                "refresh_trigger": normalized_meta.get("refresh_trigger"),
                "refresh_error": normalized_meta.get("refresh_error"),
                "refreshed_before_build": bool(normalized_meta.get("refreshed_before_build")),
            }
        )
        scheduler_status.update(
            {
                "refresh_attempted": bool(normalized_meta.get("refresh_attempted")),
                "refresh_status": normalized_meta.get("refresh_status"),
                "refresh_error": normalized_meta.get("refresh_error"),
            }
        )
        data["freshness_repair"] = normalized_meta
        data["summary"] = summary
        data["scheduler_status"] = scheduler_status
        return data

    @staticmethod
    def _filter_supported_injection_kwargs(factory: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        if not kwargs:
            return {}
        try:
            signature = inspect.signature(factory)
        except (TypeError, ValueError):
            return dict(kwargs)
        if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
            return dict(kwargs)
        allowed = {
            name
            for name, parameter in signature.parameters.items()
            if parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return {key: value for key, value in kwargs.items() if key in allowed}

    @staticmethod
    def _call_factory_with_supported_kwargs(factory: Any, kwargs: dict[str, Any]):
        filtered_kwargs = StrategyFactoryScheduler._filter_supported_injection_kwargs(factory, kwargs)
        return factory(**filtered_kwargs) if filtered_kwargs else factory()

    def _load_db(self):
        if callable(self._db_provider):
            return self._db_provider()
        from ..infrastructure.mcp_services import get_db_provider

        return get_db_provider()()

    def _adapt_gateway_repository(self, db):
        runtime_repo = getattr(self._runtime_adapters, "repository", None) if self._runtime_adapters is not None else None
        if runtime_repo is not None and getattr(runtime_repo, "raw", None) is db:
            return runtime_repo
        return db

    def _build_deduplicator(self, factory_pkg):
        deduplicator_cls = factory_pkg.Deduplicator
        kwargs = {}
        if self._vector_gateway is not None:
            kwargs["vector_gateway"] = self._vector_gateway
        return self._call_factory_with_supported_kwargs(deduplicator_cls, kwargs)

    def _build_submitter(self, factory_pkg):
        submitter_cls = factory_pkg.StrategySubmitter
        kwargs = {}
        if self._validation_gateway is not None:
            kwargs["validation_gateway"] = self._validation_gateway
        if self._risk_gateway is not None:
            kwargs["risk_gateway"] = self._risk_gateway
        if self._incubation_gateway is not None:
            kwargs["incubation_gateway"] = self._incubation_gateway
        return self._call_factory_with_supported_kwargs(submitter_cls, kwargs)

    def _get_autonomy_gateway(self) -> "AutonomyGateway":
        if self._autonomy_gateway is None:
            from ..infrastructure.mcp_adapters import MCPAutonomyGatewayImpl

            self._autonomy_gateway = MCPAutonomyGatewayImpl()
        return self._autonomy_gateway

    def _get_factor_research_gateway(self) -> "FactorResearchGateway":
        if self._factor_research_gateway is None:
            from ..infrastructure.mcp_adapters import MCPFactorResearchGatewayImpl

            factory_pkg = get_strategy_factory_package()
            self._factor_research_gateway = MCPFactorResearchGatewayImpl(
                builder=getattr(factory_pkg, "FactorResearchBuilder", None),
            )
        return self._factor_research_gateway

    async def _run_startup_warmup(self) -> dict[str, Any]:
        if not FACTORY_STARTUP_WARMUP_ENABLED:
            return {
                "ok": True,
                "status": "disabled",
                "task_type": FACTORY_STARTUP_WARMUP_TASK_TYPE,
                "force": FACTORY_STARTUP_WARMUP_FORCE,
                "matched": 0,
                "executed": 0,
                "failed": 0,
                "executed_task_ids": [],
                "failed_schedule_ids": [],
                "schedules": [],
            }

        runner = get_runtime_warmup_runner()
        try:
            return await runner(
                task_type=FACTORY_STARTUP_WARMUP_TASK_TYPE,
                force=FACTORY_STARTUP_WARMUP_FORCE,
                limit=FACTORY_STARTUP_WARMUP_LIMIT,
                source="strategy_factory",
            )
        except Exception as exc:
            return {
                "ok": False,
                "status": "failed",
                "task_type": FACTORY_STARTUP_WARMUP_TASK_TYPE,
                "force": FACTORY_STARTUP_WARMUP_FORCE,
                "matched": 0,
                "executed": 0,
                "failed": 0,
                "executed_task_ids": [],
                "failed_schedule_ids": [],
                "schedules": [],
                "error": str(exc),
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
        outcome = await FactoryCycleRunner(self, context).run()
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
