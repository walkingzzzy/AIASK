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
            "count": int(active_pool.get("count") or 0),
            "top_candidates": top_candidates,
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
                "ranked_factor_count": int(summary.get("ranked_factor_count") or 0),
                "top_factor_names": list(summary.get("top_factor_names") or []),
                "top_candidate_names": list(summary.get("top_candidate_names") or []),
                "active_family_names": list(summary.get("active_family_names") or []),
                "active_regime_names": list(summary.get("active_regime_names") or []),
                "preferred_strategy_types": list(summary.get("preferred_strategy_types") or []),
                "factor_source_mode": summary.get("factor_source_mode"),
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

    async def _build_factor_research_artifact(self, factor_gateway, db, snapshot: dict[str, Any]) -> dict[str, Any]:
        gateway_db = self._adapt_gateway_repository(db)
        auto_refresh_enabled = is_factory_factor_auto_refresh_enabled()
        refresh_meta: dict[str, Any] = {
            "auto_refresh_enabled": auto_refresh_enabled,
            "refresh_attempted": False,
            "refresh_status": "not_needed",
            "refresh_trigger": None,
            "refresh_error": None,
            "refreshed_before_build": False,
            "refresh_result": {},
            "refresh_timeout_sec": FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
        }
        artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
        summary = dict(artifact.get("summary") or {})
        should_refresh = bool(auto_refresh_enabled and summary.get("stale"))
        refresh = getattr(factor_gateway, "refresh", None)
        if should_refresh:
            refresh_meta["refresh_attempted"] = True
            refresh_meta["refresh_trigger"] = "stale_artifact"
            if callable(refresh):
                try:
                    refresh_result = refresh()
                    if inspect.isawaitable(refresh_result):
                        refresh_result = await asyncio.wait_for(
                            refresh_result,
                            timeout=FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
                        )
                    refresh_meta["refresh_status"] = "success"
                    refresh_meta["refresh_result"] = self._summarize_refresh_result(refresh_result)
                    refresh_meta["refreshed_before_build"] = True
                    artifact = dict(await factor_gateway.build_artifact(gateway_db, snapshot) or {})
                except asyncio.TimeoutError:
                    refresh_meta["refresh_status"] = "timeout"
                    refresh_meta["refresh_error"] = (
                        f"factor refresh exceeded {FACTORY_FACTOR_REFRESH_TIMEOUT_SEC}s"
                    )
                except Exception as exc:
                    refresh_meta["refresh_status"] = "failed"
                    refresh_meta["refresh_error"] = str(exc)
            else:
                refresh_meta["refresh_status"] = "unsupported"
                refresh_meta["refresh_error"] = "factor gateway does not expose refresh()"
        elif not auto_refresh_enabled:
            refresh_meta["refresh_status"] = "disabled"
        return self._inject_factor_refresh_meta(artifact, refresh_meta)

    def _build_factory_readiness(
        self,
        snapshot: dict[str, Any],
        factor_research: Optional[dict],
    ) -> dict[str, Any]:
        factor_artifact = dict(factor_research or {})
        factor_summary = dict(factor_artifact.get("summary") or {})
        factor_refresh = dict(factor_artifact.get("freshness_repair") or {})
        factor_source_mode = str(factor_summary.get("factor_source_mode") or "").strip().lower()
        active_candidate_count = int(factor_summary.get("active_candidate_count") or 0)
        governed_candidate_pool_active = bool(
            factor_source_mode == "governed_candidate_pool" or active_candidate_count > 0
        )
        sources = dict(snapshot.get("sources") or {})
        event_source = dict(sources.get("event_driven") or {})
        event_state = dict(snapshot.get("event_driven") or {})
        completion = dict(snapshot.get("completeness") or {})
        completion_ratio = self._safe_float(completion.get("completion_ratio"), default=1.0)
        warnings: list[str] = []
        blockers: list[str] = []
        score = 1.0

        if bool(snapshot.get("degraded")):
            warnings.append("snapshot_degraded")
            score -= 0.12
        if completion_ratio < FACTORY_READINESS_MIN_COMPLETION_RATIO:
            blockers.append("snapshot_completion_too_low")
            score -= 0.28
        elif completion_ratio < 0.9:
            warnings.append("snapshot_completion_low")
            score -= 0.08

        event_status = str(event_source.get("status") or "unknown").strip().lower() or "unknown"
        if event_status != "success":
            warnings.append(f"event_driven_{event_status}")
            score -= 0.08 if event_status == "partial" else 0.14
        if event_status == "success" and int(event_state.get("tasks_ready_count") or 0) <= 0:
            warnings.append("event_driven_no_ready_tasks")
            score -= 0.03

        if bool(factor_summary.get("degraded")):
            warnings.append("factor_research_degraded")
            score -= 0.14
        if bool(factor_summary.get("stale")):
            if governed_candidate_pool_active:
                warnings.append("factor_research_history_stale_governed_pool_active")
                score -= 0.06
            else:
                blockers.append("factor_research_stale")
                score -= 0.32
        refresh_status = str(factor_refresh.get("refresh_status") or "").strip().lower()
        if bool(factor_refresh.get("refresh_attempted")) and refresh_status not in {"success", "not_needed"}:
            warnings.append(f"factor_refresh_{refresh_status or 'unknown'}")
            score -= 0.08

        score = max(min(round(score, 4), 1.0), 0.0)
        hard_block = is_factory_readiness_hard_block_enabled()
        can_proceed = not hard_block or (score >= FACTORY_READINESS_MIN_SCORE and not blockers)
        return {
            "runtime_enabled": is_factory_runtime_enabled(),
            "event_runtime_mode": resolve_event_runtime_mode(),
            "auto_refresh_enabled": bool(factor_refresh.get("auto_refresh_enabled")),
            "hard_block_enabled": hard_block,
            "min_score": FACTORY_READINESS_MIN_SCORE,
            "min_completion_ratio": FACTORY_READINESS_MIN_COMPLETION_RATIO,
            "readiness_score": score,
            "can_proceed": can_proceed,
            "warnings": warnings,
            "warning_count": len(warnings),
            "blockers": blockers,
            "blocker_count": len(blockers),
            "snapshot_completion_ratio": completion_ratio,
            "snapshot_degraded": bool(snapshot.get("degraded")),
            "event_status": event_status,
            "event_task_ready_count": int(event_state.get("tasks_ready_count") or 0),
            "factor_research_stale": bool(factor_summary.get("stale")),
            "factor_research_degraded": bool(factor_summary.get("degraded")),
            "factor_source_mode": factor_summary.get("factor_source_mode"),
            "governed_candidate_pool_active": governed_candidate_pool_active,
            "active_candidate_count": active_candidate_count,
            "active_family_count": len(list(factor_summary.get("active_family_names") or [])),
            "active_regime_count": len(list(factor_summary.get("active_regime_names") or [])),
            "factor_refresh_attempted": bool(factor_refresh.get("refresh_attempted")),
            "factor_refresh_status": factor_refresh.get("refresh_status"),
        }

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

    async def _persist_enriched_snapshot(self, db, snapshot: dict[str, Any]) -> None:
        try:
            await _call_optional_async(
                db,
                "save_daily_snapshot",
                snapshot.get("date") or self._now().date(),
                snapshot,
            )
        except Exception as exc:
            logger.warning("StrategyFactory: enriched snapshot persistence failed: %s", exc)

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
            "research_task_concurrency": effective_research_concurrency,
            "configured_research_task_concurrency": RESEARCH_TASK_CONCURRENCY,
            "shared_generation_context_preloaded": shared_generation_context_preloaded,
            **lifecycle_metrics,
        }
        return {"stage": stage, "candidates": generated_candidates, "experiments": all_experiments}


    async def run_once(self, db=None) -> dict:
        """执行一次完整的策略工厂流程。"""
        factory_pkg = get_strategy_factory_package()
        db = self._load_db() if db is None else db
        start = self._now()
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

        if not is_factory_runtime_enabled():
            results["status"] = "skipped"
            results["completed_at"] = self._now().isoformat()
            results["elapsed_seconds"] = 0.0
            results["stages"]["readiness"] = self._with_stage_meta(
                "readiness",
                trace_id,
                {
                    "status": "skipped",
                    "ok": False,
                    "runtime_enabled": False,
                    "event_runtime_mode": resolve_event_runtime_mode(),
                    "hard_block_enabled": is_factory_readiness_hard_block_enabled(),
                    "readiness_score": 0.0,
                    "can_proceed": False,
                    "warnings": [],
                    "warning_count": 0,
                    "blockers": ["runtime_disabled"],
                    "blocker_count": 1,
                },
                default_ok=False,
            )
            results["summary"] = {
                "trace_id": trace_id,
                "runtime_enabled": False,
                "event_runtime_mode": resolve_event_runtime_mode(),
                "factory_readiness_score": 0.0,
                "factory_readiness_can_proceed": False,
                "factory_readiness_blocker_count": 1,
                "factory_readiness_warning_count": 0,
                "skip_reason": "runtime_disabled",
                "elapsed_seconds": 0.0,
            }
            results["pipeline"] = {
                "trace_id": trace_id,
                "status": results.get("status"),
                "stage_order": list(results.get("stages", {}).keys()),
                "total_stage_count": len(results.get("stages", {})),
            }
            self.last_run = self._now()
            self.last_result = results
            if hasattr(db, "save_strategy_factory_run"):
                try:
                    await db.save_strategy_factory_run(results)
                except Exception as exc:
                    logger.warning("StrategyFactory: failed to persist skipped run %s: %s", results.get("run_id"), exc)
            return results

        try:
            warmup_result = await self._run_startup_warmup()
            results["stages"]["warmup"] = self._with_stage_meta(
                "warmup",
                trace_id,
                warmup_result,
                default_ok=bool(warmup_result.get("ok", True)),
            )

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
                factor_gateway = self._get_factor_research_gateway()
                factor_research = await self._build_factor_research_artifact(
                    factor_gateway,
                    db,
                    snapshot,
                )
                snapshot["factor_research"] = dict(factor_research or {})
                factor_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
                compact_factor_research = self._compact_factor_research_snapshot(snapshot.get("factor_research"))
                results["stages"]["factor_research"] = self._with_stage_meta("factor_research", trace_id, {
                    "active_factor_count": int(factor_summary.get("active_factor_count") or 0),
                    "active_candidate_count": int(factor_summary.get("active_candidate_count") or 0),
                    "active_family_count": len(list(factor_summary.get("active_family_names") or [])),
                    "active_regime_count": len(list(factor_summary.get("active_regime_names") or [])),
                    "ranked_factor_count": int(factor_summary.get("ranked_factor_count") or 0),
                    "top_factor_names": list(factor_summary.get("top_factor_names") or []),
                    "top_candidate_names": list(factor_summary.get("top_candidate_names") or []),
                    "active_family_names": list(factor_summary.get("active_family_names") or []),
                    "active_regime_names": list(factor_summary.get("active_regime_names") or []),
                    "preferred_strategy_types": list(factor_summary.get("preferred_strategy_types") or []),
                    "factor_source_mode": factor_summary.get("factor_source_mode"),
                    "degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                    "freshness_days": factor_summary.get("freshness_days"),
                    "latest_factor_date": factor_summary.get("latest_factor_date"),
                    "quality_flags": list(factor_summary.get("quality_flags") or []),
                    "refresh_attempted": bool(factor_summary.get("refresh_attempted")),
                    "refresh_status": factor_summary.get("refresh_status"),
                    "refresh_trigger": factor_summary.get("refresh_trigger"),
                    "refresh_error": factor_summary.get("refresh_error"),
                    "active_candidate_pool": compact_factor_research.get("active_candidate_pool") or {},
                    "source_chain": list((snapshot.get("factor_research") or {}).get("source_chain") or []),
                })
            except Exception as exc:
                logger.warning("StrategyFactory: factor research stage failed: %s", exc)
                snapshot["factor_research"] = {
                    "active_factors": [],
                    "ranked_factors": [],
                    "positive_rising_factors": [],
                    "preferred_strategy_types": [],
                    "governed_candidates": [],
                    "active_candidate_pool": {},
                    "active_family_summary": [],
                    "active_regime_summary": [],
                    "research_rationale": [str(exc)],
                    "source_chain": ["factor_research_error"],
                    "degraded": True,
                    "summary": {
                        "active_factor_count": 0,
                        "active_candidate_count": 0,
                        "ranked_factor_count": 0,
                        "top_factor_names": [],
                        "top_candidate_names": [],
                        "active_family_names": [],
                        "active_regime_names": [],
                        "preferred_strategy_types": [],
                        "factor_source_mode": "error_fallback",
                        "degraded": True,
                        "quality_flags": ["failed"],
                    },
                }
                results["stages"]["factor_research"] = self._with_stage_meta("factor_research", trace_id, {
                    "active_factor_count": 0,
                    "active_candidate_count": 0,
                    "active_family_count": 0,
                    "active_regime_count": 0,
                    "ranked_factor_count": 0,
                    "top_factor_names": [],
                    "top_candidate_names": [],
                    "active_family_names": [],
                    "active_regime_names": [],
                    "preferred_strategy_types": [],
                    "factor_source_mode": "error_fallback",
                    "degraded": True,
                    "quality_flags": ["failed"],
                    "error": str(exc),
                }, default_ok=False)

            results["snapshot_summary"] = {
                **dict(results.get("snapshot_summary") or {}),
                "factor_research": self._compact_factor_research_snapshot(snapshot.get("factor_research")),
            }

            readiness = self._build_factory_readiness(snapshot, snapshot.get("factor_research"))
            snapshot["factory_readiness"] = readiness
            results["stages"]["readiness"] = self._with_stage_meta("readiness", trace_id, readiness, default_ok=bool(readiness.get("can_proceed")))
            await self._persist_enriched_snapshot(db, snapshot)

            if not bool(readiness.get("can_proceed")):
                elapsed = (self._now() - start).total_seconds()
                results["status"] = "skipped"
                results["completed_at"] = self._now().isoformat()
                results["elapsed_seconds"] = round(elapsed, 1)
                results["summary"] = {
                    "trace_id": trace_id,
                    "runtime_enabled": bool(readiness.get("runtime_enabled")),
                    "event_runtime_mode": readiness.get("event_runtime_mode"),
                    "factory_readiness_score": readiness.get("readiness_score"),
                    "factory_readiness_can_proceed": False,
                    "factory_readiness_blocker_count": readiness.get("blocker_count", 0),
                    "factory_readiness_warning_count": readiness.get("warning_count", 0),
                    "factor_source_mode": readiness.get("factor_source_mode"),
                    "governed_candidate_pool_active": bool(readiness.get("governed_candidate_pool_active")),
                    "active_candidate_count": int(readiness.get("active_candidate_count") or 0),
                    "skip_reason": "readiness_blocked",
                    "elapsed_seconds": round(elapsed, 1),
                }
                results["pipeline"] = {
                    "trace_id": trace_id,
                    "status": results.get("status"),
                    "stage_order": list(results.get("stages", {}).keys()),
                    "total_stage_count": len(results.get("stages", {})),
                }
                logger.warning(
                    "StrategyFactory: run %s blocked by readiness controls: %s",
                    results.get("run_id"),
                    readiness.get("blockers"),
                )
                self.last_run = self._now()
                self.last_result = results
                if hasattr(db, "save_strategy_factory_run"):
                    try:
                        await db.save_strategy_factory_run(results)
                    except Exception as exc:
                        logger.warning("StrategyFactory: failed to persist blocked run %s: %s", results.get("run_id"), exc)
                return results

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
                autonomy_stage = autonomy_batch.get("stage") or {}
                factory_attempt_count = int(autonomy_stage.get("external_llm_attempt_count") or 0)
                factory_selected_count = int(autonomy_stage.get("external_llm_selected_count") or 0)
                for ai_candidate in ai_candidates:
                    params = dict(ai_candidate.get("params") or {})
                    params["factory_attempt_count"] = factory_attempt_count
                    params["factory_selected_count"] = factory_selected_count
                    ai_candidate["params"] = params
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
            deduplicator = self._build_deduplicator(factory_pkg)
            submitter = self._build_submitter(factory_pkg)
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

            elapsed = (self._now() - start).total_seconds()
            results["status"] = "success"
            results["completed_at"] = self._now().isoformat()
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
                    "candidate_family": (item.get("task") or {}).get("candidate_family"),
                    "source_candidate_artifact_id": (item.get("task") or {}).get("source_candidate_artifact_id"),
                    "factor_name": (item.get("task") or {}).get("factor_name"),
                    "generation_limit": (item.get("task") or {}).get("generation_limit"),
                    "generated_count": item.get("generated_count", 0),
                }
                for item in list(autonomy_summary.get("task_results") or [])
            ]
            factor_research_summary = dict((snapshot.get("factor_research") or {}).get("summary") or {})
            factor_refresh_summary = dict((snapshot.get("factor_research") or {}).get("freshness_repair") or {})
            gate_0_summary = dict(quality_gate_report.get("gate_0") or {})
            gate_1_summary = dict(quality_gate_report.get("gate_1") or {})
            gate_2_summary = dict(quality_gate_report.get("gate_2") or {})
            readiness_summary = dict(results.get("stages", {}).get("readiness") or {})
            warmup_summary = dict(results.get("stages", {}).get("warmup") or {})
            backtest_audit_summary = self._aggregate_backtest_audit_metrics(backtest_report)
            submission_audit_summary = self._aggregate_submission_audit_metrics(submit_result)
            results["summary"] = {
                "trace_id": trace_id,
                "runtime_enabled": bool(readiness_summary.get("runtime_enabled", True)),
                "event_runtime_mode": readiness_summary.get("event_runtime_mode"),
                "factory_readiness_score": readiness_summary.get("readiness_score"),
                "factory_readiness_can_proceed": readiness_summary.get("can_proceed"),
                "factory_readiness_blocker_count": readiness_summary.get("blocker_count", 0),
                "factory_readiness_warning_count": readiness_summary.get("warning_count", 0),
                "fear_greed": snapshot.get("fear_greed_index"),
                "listed_count": snapshot.get("listed_count", 0),
                "snapshot_degraded": bool(snapshot.get("degraded")),
                "snapshot_completion_ratio": (snapshot.get("completeness") or {}).get("completion_ratio", 1.0),
                "snapshot_failure_reason_count": len(snapshot.get("failure_reasons") or []),
                "warmup_status": warmup_summary.get("status"),
                "warmup_task_type": warmup_summary.get("task_type"),
                "warmup_matched": int(warmup_summary.get("matched") or 0),
                "warmup_executed": int(warmup_summary.get("executed") or 0),
                "warmup_failed": int(warmup_summary.get("failed") or 0),
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
                "active_candidate_count": int(factor_research_summary.get("active_candidate_count") or 0),
                "active_family_count": len(list(factor_research_summary.get("active_family_names") or [])),
                "active_regime_count": len(list(factor_research_summary.get("active_regime_names") or [])),
                "top_factor_names": list(factor_research_summary.get("top_factor_names") or []),
                "top_candidate_names": list(factor_research_summary.get("top_candidate_names") or []),
                "active_family_names": list(factor_research_summary.get("active_family_names") or []),
                "active_regime_names": list(factor_research_summary.get("active_regime_names") or []),
                "factor_source_mode": factor_research_summary.get("factor_source_mode"),
                "governed_candidate_pool_active": bool(
                    str(factor_research_summary.get("factor_source_mode") or "").strip().lower()
                    == "governed_candidate_pool"
                ),
                "factor_research_degraded": bool((snapshot.get("factor_research") or {}).get("degraded")),
                "factor_research_stale": bool(factor_research_summary.get("stale")),
                "factor_research_freshness_days": factor_research_summary.get("freshness_days"),
                "factor_research_refresh_attempted": bool(factor_refresh_summary.get("refresh_attempted")),
                "factor_research_refresh_status": factor_refresh_summary.get("refresh_status"),
                "factor_research_refresh_trigger": factor_refresh_summary.get("refresh_trigger"),
                "shared_generation_context_preloaded": bool(autonomy_summary.get("shared_generation_context_preloaded")),
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
                **submission_audit_summary,
                **backtest_audit_summary,
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
            elapsed = (self._now() - start).total_seconds()
            logger.error("StrategyFactory: run_once failed: %s", exc, exc_info=True)
            results["status"] = "failed"
            results["completed_at"] = self._now().isoformat()
            results["elapsed_seconds"] = round(elapsed, 1)
            results["error"] = str(exc)
            results["summary"] = {"trace_id": trace_id, "elapsed_seconds": round(elapsed, 1), "error": str(exc)}

        results["pipeline"] = {
            "trace_id": trace_id,
            "status": results.get("status"),
            "stage_order": list(results.get("stages", {}).keys()),
            "total_stage_count": len(results.get("stages", {})),
        }

        self.last_run = self._now()
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
