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
from ..domain.strategy_profile import apply_candidate_strategy_profile
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


class _StrategyFactorySchedulerAnalysisMixin:
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
            return apply_candidate_strategy_profile(item, research_task=merged_task or task)

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

        @classmethod
        def _extract_cycle_generated_count(cls, cycle: dict) -> int:
            value = (cycle or {}).get("generated_count")
            if value is None:
                value = dict((cycle or {}).get("generation") or {}).get("count")
            if value is None:
                value = len(cls._extract_cycle_candidates(cycle))
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
                    "lookahead_available": bool(payload.get("lookahead_available")),
                    "multiple_testing_available": bool(payload.get("multiple_testing_available")),
                    "required_audits_complete": bool(payload.get("required_audits_complete")),
                    "blocked": bool(payload.get("blocked")),
                    "block_reasons": _normalize_list(payload.get("block_reasons")),
                }

            def _normalize_lineage(value: Any) -> dict[str, Any]:
                payload = dict(value or {}) if isinstance(value, dict) else {}
                return {
                    "generation_artifact_id": str(payload.get("generation_artifact_id") or "").strip() or None,
                    "validation_artifact_id": str(payload.get("validation_artifact_id") or "").strip() or None,
                    "memory_record_id": str(payload.get("memory_record_id") or "").strip() or None,
                    "resolved_from": str(payload.get("resolved_from") or "").strip() or None,
                    "candidate_index": payload.get("candidate_index"),
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
                        "expected_holding_period": item.get("expected_holding_period"),
                        "grade": str(item.get("grade") or "").strip() or None,
                        "recommendation": str(item.get("recommendation") or "").strip() or None,
                        "registry_stage": str(item.get("registry_stage") or "").strip() or None,
                        "pool_entry_mode": str(item.get("pool_entry_mode") or "").strip() or None,
                        "total_score": item.get("total_score"),
                        "admission_blocked": bool(item.get("admission_blocked")),
                        "admission_block_reasons": _normalize_list(item.get("admission_block_reasons")),
                        "source_generation_artifact_id": str(item.get("source_generation_artifact_id") or "").strip() or None,
                        "source_validation_artifact_id": str(item.get("source_validation_artifact_id") or "").strip() or None,
                        "memory_record_id": str(item.get("memory_record_id") or "").strip() or None,
                        "latest_validation_at": item.get("latest_validation_at"),
                        "latest_validation_age_days": item.get("latest_validation_age_days"),
                        "lineage": _normalize_lineage(item.get("lineage")),
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
                        "expected_regime": _normalize_list(item.get("expected_regime")),
                        "expected_holding_period": item.get("expected_holding_period"),
                        "grade": str(item.get("grade") or "").strip() or None,
                        "recommendation": str(item.get("recommendation") or "").strip() or None,
                        "registry_stage": str(item.get("registry_stage") or "").strip() or None,
                        "total_score": item.get("total_score"),
                        "admission_blocked": bool(item.get("admission_blocked")),
                        "admission_block_reasons": _normalize_list(item.get("admission_block_reasons")),
                        "source_generation_artifact_id": str(item.get("source_generation_artifact_id") or "").strip() or None,
                        "source_validation_artifact_id": str(item.get("source_validation_artifact_id") or "").strip() or None,
                        "memory_record_id": str(item.get("memory_record_id") or "").strip() or None,
                        "latest_validation_at": item.get("latest_validation_at"),
                        "latest_validation_age_days": item.get("latest_validation_age_days"),
                        "lineage": _normalize_lineage(item.get("lineage")),
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
                "active_pool_mode": str(active_pool.get("active_pool_mode") or "").strip() or None,
                "source_count": int(active_pool.get("source_count") or 0),
                "count": int(active_pool.get("count") or 0),
                "strict_count": int(active_pool.get("strict_count") or 0),
                "provisional_count": int(active_pool.get("provisional_count") or 0),
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
                    "governed_blocked_ratio": summary.get("governed_blocked_ratio"),
                    "governed_latest_candidate_at": summary.get("governed_latest_candidate_at"),
                    "governed_freshness_days": summary.get("governed_freshness_days"),
                    "ranked_factor_count": int(summary.get("ranked_factor_count") or 0),
                    "top_factor_names": list(summary.get("top_factor_names") or []),
                    "top_candidate_names": list(summary.get("top_candidate_names") or []),
                    "active_family_names": list(summary.get("active_family_names") or []),
                    "active_regime_names": list(summary.get("active_regime_names") or []),
                    "preferred_strategy_types": list(summary.get("preferred_strategy_types") or []),
                    "factor_source_mode": summary.get("factor_source_mode"),
                    "governed_candidate_pool_mode": summary.get("governed_candidate_pool_mode"),
                    "governed_candidate_pool_provisional": bool(summary.get("governed_candidate_pool_provisional")),
                    "governed_candidate_pool_strict_count": int(summary.get("governed_candidate_pool_strict_count") or 0),
                    "governed_candidate_pool_provisional_count": int(
                        summary.get("governed_candidate_pool_provisional_count") or 0
                    ),
                    "scheduler_last_run": summary.get("scheduler_last_run"),
                    "scheduler_freshness_sec": summary.get("scheduler_freshness_sec"),
                    "scheduler_recent_success": bool(summary.get("scheduler_recent_success")),
                    "scheduler_llm_validation_status": summary.get("scheduler_llm_validation_status"),
                    "governed_exclusion_reason_counts": dict(summary.get("governed_exclusion_reason_counts") or {}),
                    "governed_registry_stage_counts": dict(summary.get("governed_registry_stage_counts") or {}),
                    "top_candidate_lineage": list(summary.get("top_candidate_lineage") or []),
                    "governed_risk_counts": dict(summary.get("governed_risk_counts") or {}),
                    "stock_family_allocation_count": int(summary.get("stock_family_allocation_count") or 0),
                    "stock_family_allocation_family_counts": dict(summary.get("stock_family_allocation_family_counts") or {}),
                    "stock_family_allocation_entropy": summary.get("stock_family_allocation_entropy"),
                    "stock_family_allocation_avg_priority": summary.get("stock_family_allocation_avg_priority"),
                    "stock_family_allocation_source_mode": summary.get("stock_family_allocation_source_mode"),
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
            incubation_readiness_values: list[float] = []
            formal_incubation_count = 0
            observe_incubation_count = 0
            deferred_budget_queue_count = 0
            live_ready_review_count = 0
            direct_trade_candidate_count = 0
            paper_account_bound_count = 0
            runtime_review_count = 0
            promotion_review_count = 0
            promotion_review_status_counts: dict[str, int] = {}

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
                readiness_score = summary.get("incubation_readiness_score")
                if readiness_score is not None:
                    incubation_readiness_values.append(cls._safe_float(readiness_score))
                track = str(summary.get("incubation_budget_track") or "").strip().lower()
                if summary.get("passed"):
                    if track == "formal_incubation":
                        formal_incubation_count += 1
                    elif track == "observe_incubation":
                        observe_incubation_count += 1
                    elif track == "deferred_budget_queue":
                        deferred_budget_queue_count += 1
                if bool(summary.get("direct_trade_candidate")):
                    direct_trade_candidate_count += 1
                submission_lane = str(summary.get("submission_lane") or "").strip().lower()
                if submission_lane == "live_ready_review":
                    live_ready_review_count += 1
                if summary.get("paper_account_id") or summary.get("incubation_account_id"):
                    paper_account_bound_count += 1
                if str(summary.get("runtime_control_mode") or "").strip():
                    runtime_review_count += 1
                promotion_review_status = str(summary.get("promotion_review_status") or "").strip().lower()
                if summary.get("promotion_review_id") or promotion_review_status:
                    promotion_review_count += 1
                if promotion_review_status:
                    promotion_review_status_counts[promotion_review_status] = (
                        promotion_review_status_counts.get(promotion_review_status, 0) + 1
                    )

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
                "avg_incubation_readiness_score": round(
                    sum(incubation_readiness_values) / len(incubation_readiness_values),
                    4,
                )
                if incubation_readiness_values
                else 0.0,
                "formal_incubation_count": formal_incubation_count,
                "observe_incubation_count": observe_incubation_count,
                "deferred_budget_queue_count": deferred_budget_queue_count,
                "live_ready_review_count": live_ready_review_count,
                "direct_trade_candidate_count": direct_trade_candidate_count,
                "paper_account_bound_count": paper_account_bound_count,
                "runtime_review_count": runtime_review_count,
                "promotion_review_count": promotion_review_count,
                "promotion_review_status_counts": promotion_review_status_counts,
                "refresh_metrics_only_count": refresh_metrics_only_count,
                "spawn_revision_from_existing_count": spawn_revision_from_existing_count,
            }

        @classmethod
        def _build_layered_run_summary(
            cls,
            summary: Optional[dict[str, Any]],
            submit_result: Optional[dict],
        ) -> dict[str, Any]:
            base = dict(summary or {})
            strategies = list((submit_result or {}).get("strategies") or [])
            submission_lane_counts: dict[str, int] = {}
            strategy_status_counts: dict[str, int] = {}
            live_candidate_ready_count = 0
            live_review_ready_count = 0
            for item in strategies:
                record = dict(item or {})
                if bool(record.get("live_candidate_ready")):
                    live_candidate_ready_count += 1
                if bool(record.get("live_review_ready")):
                    live_review_ready_count += 1
                submission_lane = str(record.get("submission_lane") or "").strip().lower()
                if submission_lane:
                    submission_lane_counts[submission_lane] = submission_lane_counts.get(submission_lane, 0) + 1
                status = str(record.get("status") or record.get("final_status") or "").strip().lower()
                if status:
                    strategy_status_counts[status] = strategy_status_counts.get(status, 0) + 1

            return {
                "research_summary": {
                    "runtime_enabled": bool(base.get("runtime_enabled", True)),
                    "event_runtime_mode": base.get("event_runtime_mode"),
                    "readiness_score": base.get("factory_readiness_score"),
                    "readiness_can_proceed": bool(base.get("factory_readiness_can_proceed", True)),
                    "factor_source_mode": base.get("factor_source_mode"),
                    "governed_candidate_pool_active": bool(base.get("governed_candidate_pool_active")),
                    "governed_candidate_pool_mode": base.get("governed_candidate_pool_mode"),
                    "governed_candidate_pool_provisional": bool(base.get("governed_candidate_pool_provisional")),
                    "spawned_candidate_count": int(base.get("candidates_spawned") or 0),
                    "autonomy_generated_count": int(base.get("autonomy_generated") or 0),
                    "autonomy_task_count": int(base.get("autonomy_task_count") or 0),
                    "snapshot_task_count": int(base.get("snapshot_task_count") or 0),
                    "bulk_stock_task_count": int(base.get("bulk_stock_task_count") or 0),
                    "gate_0_passed": int(base.get("gate_0_passed") or 0),
                    "pre_gate_passed": int(base.get("pre_gate_passed") or 0),
                    "gate_1_passed": int(base.get("gate_1_passed") or 0),
                    "gate_2_input": int(base.get("gate_2_input") or 0),
                    "gate_2_passed": int(base.get("gate_2_passed") or 0),
                    "gate_2_failed": int(base.get("candidates_failed_backtest") or 0),
                },
                "incubation_summary": {
                    "candidates_after_dedup": int(base.get("candidates_after_dedup") or 0),
                    "gate_3_input": int(base.get("gate_3_input") or 0),
                    "gate_3_passed": int(base.get("gate_3_passed") or 0),
                    "gate_3_failed": int(base.get("gate_3_failed") or 0),
                    "submitted_count": int(base.get("submitted") or 0),
                    "created_strategy_pool_count": int(base.get("created_strategy_pool") or 0),
                    "created_audit_only_count": int(base.get("created_audit_only") or 0),
                    "formal_incubation_count": int(base.get("formal_incubation_count") or 0),
                    "observe_incubation_count": int(base.get("observe_incubation_count") or 0),
                    "deferred_budget_queue_count": int(base.get("deferred_budget_queue_count") or 0),
                    "refresh_metrics_only_count": int(base.get("refresh_metrics_only_count") or 0),
                    "spawn_revision_from_existing_count": int(base.get("spawn_revision_from_existing_count") or 0),
                    "submission_lane_counts": submission_lane_counts,
                    "strategy_status_counts": strategy_status_counts,
                },
                "live_ready_summary": {
                    "live_candidate_ready_count": live_candidate_ready_count,
                    "live_review_ready_count": live_review_ready_count,
                    "live_ready_review_count": int(base.get("live_ready_review_count") or 0),
                    "direct_trade_candidate_count": int(base.get("direct_trade_candidate_count") or 0),
                    "paper_account_bound_count": int(base.get("paper_account_bound_count") or 0),
                    "runtime_review_count": int(base.get("runtime_review_count") or 0),
                    "promotion_review_count": int(base.get("promotion_review_count") or 0),
                    "promotion_review_status_counts": dict(base.get("promotion_review_status_counts") or {}),
                },
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
