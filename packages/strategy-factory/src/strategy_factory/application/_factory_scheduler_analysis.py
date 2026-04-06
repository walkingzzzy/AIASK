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

from .candidate_contract import build_candidate_contract_hash
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

        @staticmethod
        def _safe_int(value: Any, default: int = 0) -> int:
            try:
                return int(value or default)
            except Exception:
                return int(default)

        @staticmethod
        def _normalize_text(value: Any) -> str:
            return str(value or "").strip().lower()

        @classmethod
        def _safe_ratio(cls, numerator: Any, denominator: Any) -> float:
            den = cls._safe_float(denominator)
            if den <= 0.0:
                return 0.0
            return round(cls._safe_float(numerator) / den, 4)

        @staticmethod
        def _governance_status(*, critical: bool = False, warning: bool = False, available: bool = True) -> str:
            if not available:
                return "unavailable"
            if critical:
                return "critical"
            if warning:
                return "warning"
            return "healthy"

        @classmethod
        def _iso_week_label(cls, value: Any = None) -> str:
            resolved = None
            if isinstance(value, datetime):
                resolved = value
            elif value is not None:
                try:
                    resolved = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except Exception:
                    resolved = None
            if resolved is None:
                resolved = datetime.now(_MARKET_TIMEZONE)
            if resolved.tzinfo is None:
                resolved = resolved.replace(tzinfo=_MARKET_TIMEZONE)
            iso = resolved.isocalendar()
            return f"{iso.year}-W{iso.week:02d}"

        @staticmethod
        def _iter_strategy_records(results: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
            submit_stage = dict(((results or {}).get("stages") or {}).get("submit") or {})
            records = submit_stage.get("strategies")
            if isinstance(records, list):
                return [dict(item or {}) for item in records if isinstance(item, dict)]
            return []

        @staticmethod
        def _iter_backtest_records(results: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
            backtest_stage = dict(((results or {}).get("stages") or {}).get("backtest") or {})
            records: list[dict[str, Any]] = []
            for bucket_name in ("passed", "failed"):
                for item in list(backtest_stage.get(bucket_name) or []):
                    if isinstance(item, dict):
                        records.append(dict(item or {}))
            if records:
                return records
            gate_report = dict((results or {}).get("quality_gate") or (results or {}).get("gate_report") or {})
            gate_2 = dict(gate_report.get("gate_2") or {})
            for bucket_name in ("passed", "failed"):
                for item in list(gate_2.get(bucket_name) or []):
                    if isinstance(item, dict):
                        records.append(dict(item or {}))
            return records

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

        @classmethod
        def _build_scheduler_slo_summary(
            cls,
            results: dict[str, Any],
            current_summary: Optional[dict[str, Any]],
            previous_summary: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summary = dict(current_summary or {})
            previous = dict(previous_summary or {})
            alerts: list[dict[str, Any]] = []

            def _append_alert(code: str, severity: str, message: str, **payload: Any) -> None:
                alerts.append(
                    {
                        "code": str(code),
                        "severity": str(severity),
                        "message": str(message),
                        **payload,
                    }
                )

            factor_source_mode = cls._normalize_text(summary.get("factor_source_mode"))
            staleness_days = summary.get("governed_freshness_days")
            if staleness_days is None or factor_source_mode != "governed_candidate_pool":
                staleness_days = summary.get("factor_research_freshness_days")
            staleness_days = cls._safe_float(staleness_days)
            staleness_status = cls._governance_status(
                critical=bool(summary.get("factor_research_stale")) and staleness_days >= 5.0,
                warning=bool(summary.get("factor_research_stale")) or staleness_days >= 2.0,
            )
            if staleness_status != "healthy":
                _append_alert(
                    "scheduler_staleness_high",
                    "critical" if staleness_status == "critical" else "warning",
                    "Factor research freshness drifted beyond the scheduler SLO.",
                    staleness_days=round(staleness_days, 4),
                    factor_source_mode=factor_source_mode or None,
                )

            autonomy_stage = dict((results.get("stages") or {}).get("autonomy") or {})
            autonomy_status_counts = {
                str(key): cls._safe_int(value)
                for key, value in dict(autonomy_stage.get("external_llm_status_counts") or {}).items()
            }
            fallback_components: dict[str, float] = {
                "factor_source_mode": 1.0 if factor_source_mode == "seed_fallback" else 0.0,
            }
            autonomy_total = sum(autonomy_status_counts.values())
            if autonomy_total > 0:
                fallback_components["autonomy_external_llm"] = cls._safe_ratio(
                    autonomy_status_counts.get("fallback_only", 0),
                    autonomy_total,
                )
            bulk_fallback_signals = [
                1.0 if summary.get("bulk_stock_matrix_universe_offset_fallback") else 0.0,
                1.0 if summary.get("bulk_stock_matrix_task_offset_fallback") else 0.0,
            ]
            if bulk_fallback_signals:
                fallback_components["bulk_cursor"] = round(
                    sum(bulk_fallback_signals) / len(bulk_fallback_signals),
                    4,
                )
            fallback_ratio = round(
                sum(fallback_components.values()) / max(len(fallback_components), 1),
                4,
            )
            fallback_status = cls._governance_status(
                critical=fallback_ratio >= 0.65,
                warning=fallback_ratio >= 0.25,
            )
            if fallback_status != "healthy":
                _append_alert(
                    "scheduler_fallback_ratio_high",
                    "critical" if fallback_status == "critical" else "warning",
                    "Fallback paths are carrying too much of the scheduler pipeline.",
                    ratio=fallback_ratio,
                    components=fallback_components,
                )

            def _gate_rates(payload: dict[str, Any]) -> dict[str, float]:
                return {
                    "gate_0": cls._safe_ratio(payload.get("gate_0_passed"), payload.get("candidates_spawned")),
                    "pre_gate": cls._safe_ratio(payload.get("pre_gate_passed"), payload.get("gate_0_passed")),
                    "gate_1": cls._safe_ratio(payload.get("gate_1_passed"), payload.get("pre_gate_passed")),
                    "gate_2": cls._safe_ratio(payload.get("gate_2_passed"), payload.get("gate_2_input")),
                    "gate_3": cls._safe_ratio(payload.get("gate_3_passed"), payload.get("gate_3_input")),
                }

            current_gate_rates = _gate_rates(summary)
            previous_gate_rates = _gate_rates(previous) if previous else {}
            gate_rate_deltas = {
                key: round(current_gate_rates.get(key, 0.0) - previous_gate_rates.get(key, 0.0), 4)
                for key in current_gate_rates
                if previous_gate_rates
            }
            gate_drift_value = (
                round(max(abs(delta) for delta in gate_rate_deltas.values()), 4)
                if gate_rate_deltas
                else 0.0
            )
            gate_drift_status = cls._governance_status(
                critical=gate_drift_value >= 0.3,
                warning=gate_drift_value >= 0.12,
            )
            if gate_drift_status != "healthy":
                _append_alert(
                    "scheduler_gate_drift_high",
                    "critical" if gate_drift_status == "critical" else "warning",
                    "Gate conversion rates drifted sharply versus the previous run.",
                    value=gate_drift_value,
                    deltas=gate_rate_deltas,
                )

            current_refresh_ratio = cls._safe_float(
                dict(summary.get("incubation_summary") or {}).get("refresh_ratio", {}).get("ratio")
            )
            if current_refresh_ratio <= 0.0:
                current_refresh_ratio = cls._safe_ratio(
                    summary.get("refresh_metrics_only_count"),
                    summary.get("candidates_after_dedup"),
                )
            previous_refresh_ratio = cls._safe_float(
                dict(previous.get("incubation_summary") or {}).get("refresh_ratio", {}).get("ratio")
            )
            if previous_refresh_ratio <= 0.0:
                previous_refresh_ratio = cls._safe_ratio(
                    previous.get("refresh_metrics_only_count"),
                    previous.get("candidates_after_dedup"),
                )
            refresh_failed = bool(summary.get("factor_research_refresh_attempted")) and cls._normalize_text(
                summary.get("factor_research_refresh_status")
            ) not in {"success", "succeeded", "completed"}
            refresh_drift_value = abs(current_refresh_ratio - previous_refresh_ratio) if previous else 0.0
            if refresh_failed:
                refresh_drift_value = max(refresh_drift_value, 0.45)
            refresh_drift_value = round(refresh_drift_value, 4)
            refresh_drift_status = cls._governance_status(
                critical=refresh_drift_value >= 0.35,
                warning=refresh_drift_value >= 0.1,
            )
            if refresh_drift_status != "healthy":
                _append_alert(
                    "scheduler_refresh_drift_high",
                    "critical" if refresh_drift_status == "critical" else "warning",
                    "Refresh behaviour drifted versus the previous run or the latest refresh failed.",
                    value=refresh_drift_value,
                    refresh_failed=refresh_failed,
                    current_ratio=current_refresh_ratio,
                    previous_ratio=previous_refresh_ratio,
                )

            planned_bulk = cls._safe_int(summary.get("planned_bulk_task_count"))
            selected_bulk = cls._safe_int(summary.get("selected_bulk_task_count"))
            selected_batch_count = cls._safe_int(summary.get("bulk_stock_matrix_selected_batch_count"))
            batch_count = cls._safe_int(summary.get("bulk_stock_matrix_batch_count"))
            bulk_fill_ratio = cls._safe_ratio(selected_bulk, planned_bulk) if planned_bulk > 0 else 1.0
            batch_fill_ratio = cls._safe_ratio(selected_batch_count, batch_count) if batch_count > 0 else 1.0
            bulk_imbalance_value = round(
                max(0.0, 1.0 - min(bulk_fill_ratio, batch_fill_ratio)),
                4,
            ) if planned_bulk > 0 or batch_count > 0 else 0.0
            bulk_imbalance_status = cls._governance_status(
                critical=(planned_bulk > 0 or batch_count > 0) and min(bulk_fill_ratio, batch_fill_ratio) < 0.35,
                warning=(planned_bulk > 0 or batch_count > 0) and min(bulk_fill_ratio, batch_fill_ratio) < 0.8,
            )
            if bulk_imbalance_status != "healthy":
                _append_alert(
                    "bulk_queue_imbalance",
                    "critical" if bulk_imbalance_status == "critical" else "warning",
                    "Bulk stock matrix queue fill fell below the expected scheduler SLO.",
                    value=bulk_imbalance_value,
                    selected_bulk_task_count=selected_bulk,
                    planned_bulk_task_count=planned_bulk,
                    selected_batch_count=selected_batch_count,
                    batch_count=batch_count,
                )

            warmup_status = cls._normalize_text(summary.get("warmup_status"))
            warmup_failed = cls._safe_int(summary.get("warmup_failed"))
            if warmup_status in {"failed", "partial"} or warmup_failed > 0:
                _append_alert(
                    "scheduler_warmup_failed",
                    "critical" if warmup_status == "failed" or warmup_failed > 0 else "warning",
                    "Warmup did not complete cleanly before the run started.",
                    warmup_status=warmup_status or None,
                    warmup_failed=warmup_failed,
                )

            provider_health_status = cls._normalize_text(summary.get("factor_llm_provider_health_status"))
            provider_enabled = bool(summary.get("factor_llm_provider_enabled"))
            provider_ready = bool(summary.get("factor_llm_provider_ready"))
            external_llm_status = cls._normalize_text(summary.get("external_llm_status"))
            provider_degraded = provider_health_status in {"degraded", "failed", "error"} or (
                provider_enabled and not provider_ready
            ) or external_llm_status in {"failed", "partial"}
            if provider_degraded:
                _append_alert(
                    "factor_provider_degraded",
                    "critical" if provider_health_status in {"failed", "error"} or external_llm_status == "failed" else "warning",
                    "Provider health degraded during the scheduler run.",
                    factor_llm_provider_health_status=provider_health_status or None,
                    factor_llm_provider_ready=provider_ready,
                    external_llm_status=external_llm_status or None,
                )

            governed_pool_active = bool(summary.get("governed_candidate_pool_active"))
            governed_blocked_ratio = cls._safe_float(summary.get("governed_blocked_ratio"))
            if not governed_pool_active or governed_blocked_ratio >= 0.5:
                _append_alert(
                    "governed_pool_blocked",
                    "critical" if (not governed_pool_active) or governed_blocked_ratio >= 0.75 else "warning",
                    "Governed candidate pool is unavailable or heavily blocked.",
                    governed_candidate_pool_active=governed_pool_active,
                    governed_blocked_ratio=round(governed_blocked_ratio, 4),
                    factor_source_mode=factor_source_mode or None,
                )

            overall_status = "healthy"
            if any(str(item.get("severity")) == "critical" for item in alerts):
                overall_status = "critical"
            elif alerts:
                overall_status = "warning"

            return {
                "status": overall_status,
                "alert_count": len(alerts),
                "alert_codes": [str(item.get("code")) for item in alerts],
                "alerts": alerts,
                "staleness": {
                    "status": staleness_status,
                    "days": round(staleness_days, 4),
                    "factor_source_mode": factor_source_mode or None,
                },
                "fallback_ratio": {
                    "status": fallback_status,
                    "ratio": fallback_ratio,
                    "components": fallback_components,
                },
                "gate_drift": {
                    "status": gate_drift_status,
                    "value": gate_drift_value,
                    "current_rates": current_gate_rates,
                    "previous_rates": previous_gate_rates,
                    "deltas": gate_rate_deltas,
                },
                "refresh_drift": {
                    "status": refresh_drift_status,
                    "value": refresh_drift_value,
                    "current_ratio": round(current_refresh_ratio, 4),
                    "previous_ratio": round(previous_refresh_ratio, 4),
                    "refresh_failed": refresh_failed,
                },
                "bulk_queue_imbalance": {
                    "status": bulk_imbalance_status,
                    "value": bulk_imbalance_value,
                    "bulk_fill_ratio": round(bulk_fill_ratio, 4),
                    "batch_fill_ratio": round(batch_fill_ratio, 4),
                    "selected_bulk_task_count": selected_bulk,
                    "planned_bulk_task_count": planned_bulk,
                    "selected_batch_count": selected_batch_count,
                    "batch_count": batch_count,
                },
            }

        @classmethod
        def _build_factory_architecture_review(
            cls,
            results: dict[str, Any],
            current_summary: Optional[dict[str, Any]],
            previous_summary: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            del current_summary
            previous = dict(previous_summary or {})
            strategy_records = cls._iter_strategy_records(results)
            backtest_records = cls._iter_backtest_records(results)

            contract_issues: list[dict[str, Any]] = []
            contract_consistent_count = 0
            contract_missing_count = 0
            for record in strategy_records:
                strategy_id = str(record.get("strategy_id") or record.get("name") or "unknown")
                contract_hash = str(record.get("candidate_contract_hash") or "").strip()
                contract_snapshot = dict(record.get("candidate_contract_snapshot") or {})
                if not contract_hash or not contract_snapshot:
                    contract_missing_count += 1
                    contract_issues.append(
                        {
                            "strategy_id": strategy_id,
                            "issue": "missing_candidate_contract",
                        }
                    )
                    continue
                recomputed_hash = build_candidate_contract_hash(contract=contract_snapshot)
                if recomputed_hash == contract_hash:
                    contract_consistent_count += 1
                    continue
                contract_issues.append(
                    {
                        "strategy_id": strategy_id,
                        "issue": "candidate_contract_hash_mismatch",
                        "candidate_contract_hash": contract_hash,
                        "recomputed_contract_hash": recomputed_hash,
                    }
                )

            validation_issues: list[dict[str, Any]] = []
            validation_consistent_count = 0
            validation_missing_count = 0
            validation_total_count = 0
            for index, record in enumerate(backtest_records, 1):
                payload = dict(record.get("backtest_result") or record or {})
                candidate_hash = str(payload.get("candidate_contract_hash") or "").strip()
                tested_hash = str(payload.get("tested_object_hash") or "").strip()
                if not candidate_hash and not tested_hash:
                    continue
                validation_total_count += 1
                if not candidate_hash or not tested_hash:
                    validation_missing_count += 1
                    validation_issues.append(
                        {
                            "record": index,
                            "issue": "missing_tested_object_hash",
                            "candidate_contract_hash": candidate_hash or None,
                            "tested_object_hash": tested_hash or None,
                        }
                    )
                    continue
                if candidate_hash == tested_hash:
                    validation_consistent_count += 1
                    continue
                validation_issues.append(
                    {
                        "record": index,
                        "issue": "tested_object_hash_mismatch",
                        "candidate_contract_hash": candidate_hash,
                        "tested_object_hash": tested_hash,
                    }
                )

            admission_issues: list[dict[str, Any]] = []
            admission_consistent_count = 0
            for record in strategy_records:
                strategy_id = str(record.get("strategy_id") or record.get("name") or "unknown")
                admission_stage = cls._normalize_text(record.get("admission_stage"))
                action_type = cls._normalize_text(record.get("submission_action_type"))
                submission_lane = cls._normalize_text(record.get("submission_lane"))
                passed = bool(record.get("passed"))
                live_candidate_ready = bool(record.get("live_candidate_ready"))
                live_review_ready = bool(record.get("live_review_ready"))
                direct_trade_candidate = bool(record.get("direct_trade_candidate"))
                pool_admission_applied = bool(record.get("pool_admission_applied"))
                admission_block_reasons = list(record.get("admission_block_reasons") or [])

                record_issues: list[str] = []
                if pool_admission_applied and action_type != "pool_admission":
                    record_issues.append("pool_admission_action_mismatch")
                if pool_admission_applied and admission_stage != "live":
                    record_issues.append("pool_admission_stage_mismatch")
                if pool_admission_applied and admission_block_reasons:
                    record_issues.append("pool_admission_has_blockers")
                if admission_stage == "live" and not live_candidate_ready:
                    record_issues.append("live_stage_without_live_candidate")
                if action_type in {"pool_admission", "runtime_review"} and not (
                    live_candidate_ready or live_review_ready or direct_trade_candidate
                ):
                    record_issues.append("live_ready_action_without_live_ready_candidate")
                if submission_lane == "live_ready_review" and not (
                    live_candidate_ready or live_review_ready or direct_trade_candidate
                ):
                    record_issues.append("live_ready_lane_without_live_ready_candidate")
                if not passed and pool_admission_applied:
                    record_issues.append("failed_candidate_pool_admitted")
                if record_issues:
                    admission_issues.append(
                        {
                            "strategy_id": strategy_id,
                            "issues": record_issues,
                            "admission_stage": admission_stage or None,
                            "submission_action_type": action_type or None,
                            "submission_lane": submission_lane or None,
                        }
                    )
                else:
                    admission_consistent_count += 1

            def _category_payload(
                *,
                total: int,
                consistent: int,
                missing: int,
                issues: list[dict[str, Any]],
            ) -> dict[str, Any]:
                mismatch_count = len(issues)
                return {
                    "status": cls._governance_status(
                        critical=mismatch_count > 0,
                        warning=missing > 0,
                        available=total > 0,
                    ),
                    "total_count": total,
                    "consistent_count": consistent,
                    "missing_count": missing,
                    "mismatch_count": mismatch_count,
                    "issues": issues[:8],
                }

            categories = {
                "contract_consistency": _category_payload(
                    total=len(strategy_records),
                    consistent=contract_consistent_count,
                    missing=contract_missing_count,
                    issues=contract_issues,
                ),
                "validation_object_consistency": _category_payload(
                    total=validation_total_count,
                    consistent=validation_consistent_count,
                    missing=validation_missing_count,
                    issues=validation_issues,
                ),
                "admission_consistency": _category_payload(
                    total=len(strategy_records),
                    consistent=admission_consistent_count,
                    missing=0,
                    issues=admission_issues,
                ),
            }

            current_week = cls._iso_week_label((results or {}).get("completed_at") or (results or {}).get("started_at"))
            previous_review = dict(previous.get("architecture_review") or {})
            previous_review_week = str(previous_review.get("review_week") or "").strip() or None
            cadence_due = previous_review_week != current_week

            overall_status = "healthy"
            category_statuses = {payload.get("status") for payload in categories.values()}
            if "critical" in category_statuses:
                overall_status = "attention_required"
            elif "warning" in category_statuses:
                overall_status = "warning"
            elif category_statuses == {"unavailable"}:
                overall_status = "unavailable"

            return {
                "status": overall_status,
                "review_week": current_week,
                "previous_review_week": previous_review_week,
                "cadence_due": cadence_due,
                "generated_at": (results or {}).get("completed_at") or datetime.now(_MARKET_TIMEZONE).isoformat(),
                "categories": categories,
                "strategy_record_count": len(strategy_records),
                "validation_record_count": validation_total_count,
            }

        @classmethod
        def _attach_runtime_governance(
            cls,
            results: dict[str, Any],
            *,
            previous_result: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summary = dict(results.get("summary") or {})
            previous_summary = dict((previous_result or {}).get("summary") or {})
            summary["scheduler_slo"] = cls._build_scheduler_slo_summary(
                results,
                summary,
                previous_summary=previous_summary,
            )
            summary["architecture_review"] = cls._build_factory_architecture_review(
                results,
                summary,
                previous_summary=previous_summary,
            )
            results["summary"] = summary
            return results

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
            submission_action_type_counts: dict[str, int] = {}
            strategy_status_counts: dict[str, int] = {}
            live_candidate_ready_count = 0
            live_review_ready_count = 0

            def _normalized_text(value: Any) -> str:
                return str(value or "").strip().lower()

            def _count_value(bucket: dict[str, int], value: Any) -> None:
                key = _normalized_text(value)
                if not key:
                    return
                bucket[key] = bucket.get(key, 0) + 1

            def _family_value(record: dict[str, Any]) -> str:
                provenance = dict(record.get("candidate_provenance") or {})
                return _normalized_text(
                    record.get("candidate_family_id")
                    or provenance.get("candidate_family_id")
                    or record.get("candidate_family")
                    or provenance.get("candidate_family")
                    or record.get("strategy_type")
                )

            def _task_source_value(record: dict[str, Any]) -> str:
                research_task = dict(record.get("research_task") or {})
                return _normalized_text(research_task.get("task_source") or record.get("task_source"))

            def _generator_value(record: dict[str, Any]) -> str:
                provenance = dict(record.get("candidate_provenance") or {})
                return _normalized_text(
                    record.get("generator_type")
                    or record.get("generator_mode")
                    or provenance.get("generator_mode")
                    or provenance.get("generator_type")
                )

            def _refresh_mode_value(record: dict[str, Any]) -> str:
                return _normalized_text(
                    record.get("refresh_mode")
                    or dict(record.get("dedup_result") or {}).get("refresh_mode")
                )

            def _source_mix(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
                generator_counts: dict[str, int] = {}
                task_source_counts: dict[str, int] = {}
                lane_counts: dict[str, int] = {}
                for record in records:
                    _count_value(generator_counts, _generator_value(record))
                    _count_value(task_source_counts, _task_source_value(record))
                    _count_value(lane_counts, record.get("submission_lane"))
                return {
                    "generator_type_counts": generator_counts,
                    "task_source_counts": task_source_counts,
                    "submission_lane_counts": lane_counts,
                }

            def _family_mix(records: list[dict[str, Any]]) -> dict[str, int]:
                counts: dict[str, int] = {}
                for record in records:
                    _count_value(counts, _family_value(record))
                return counts

            def _refresh_ratio(records: list[dict[str, Any]]) -> dict[str, Any]:
                mode_counts: dict[str, int] = {}
                for record in records:
                    _count_value(mode_counts, _refresh_mode_value(record))
                refresh_count = sum(count for key, count in mode_counts.items() if key)
                denominator = len(records)
                return {
                    "count": refresh_count,
                    "denominator": denominator,
                    "ratio": round(refresh_count / denominator, 4) if denominator else 0.0,
                    "mode_counts": mode_counts,
                }

            def _promotion_ratio(numerator: int, denominator: int) -> dict[str, Any]:
                return {
                    "count": int(numerator),
                    "denominator": int(denominator),
                    "ratio": round(float(numerator) / float(denominator), 4) if denominator else 0.0,
                }

            for item in strategies:
                record = dict(item or {})
                if bool(record.get("live_candidate_ready")):
                    live_candidate_ready_count += 1
                if bool(record.get("live_review_ready")):
                    live_review_ready_count += 1
                submission_lane = str(record.get("submission_lane") or "").strip().lower()
                if submission_lane:
                    submission_lane_counts[submission_lane] = submission_lane_counts.get(submission_lane, 0) + 1
                submission_action_type = str(record.get("submission_action_type") or "").strip().lower()
                if submission_action_type:
                    submission_action_type_counts[submission_action_type] = (
                        submission_action_type_counts.get(submission_action_type, 0) + 1
                    )
                status = str(record.get("status") or record.get("final_status") or "").strip().lower()
                if status:
                    strategy_status_counts[status] = strategy_status_counts.get(status, 0) + 1

            research_records = [dict(item or {}) for item in strategies]
            incubation_records = [dict(item or {}) for item in strategies]
            live_ready_records = [
                dict(item or {})
                for item in strategies
                if bool((item or {}).get("live_candidate_ready"))
                or bool((item or {}).get("live_review_ready"))
                or bool((item or {}).get("direct_trade_candidate"))
                or bool((item or {}).get("promotion_review_id"))
                or bool((item or {}).get("paper_account_id"))
                or _normalized_text((item or {}).get("submission_lane")) == "live_ready_review"
            ]

            return {
                "research_summary": {
                    "runtime_enabled": bool(base.get("runtime_enabled", True)),
                    "event_runtime_mode": base.get("event_runtime_mode"),
                    "readiness_score": base.get("factory_readiness_score"),
                    "readiness_can_proceed": bool(base.get("factory_readiness_can_proceed", True)),
                    "factor_source_mode": base.get("factor_source_mode"),
                    "factor_llm_provider_health_status": base.get("factor_llm_provider_health_status"),
                    "factor_llm_provider_ready": bool(base.get("factor_llm_provider_ready")),
                    "governed_candidate_pool_active": bool(base.get("governed_candidate_pool_active")),
                    "governed_candidate_pool_runtime_state": base.get("governed_candidate_pool_runtime_state"),
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
                    "source_mix": _source_mix(research_records),
                    "family_mix": _family_mix(research_records),
                    "gate_hit": {
                        "gate_0_passed": int(base.get("gate_0_passed") or 0),
                        "pre_gate_passed": int(base.get("pre_gate_passed") or 0),
                        "gate_1_passed": int(base.get("gate_1_passed") or 0),
                        "gate_2_input": int(base.get("gate_2_input") or 0),
                        "gate_2_passed": int(base.get("gate_2_passed") or 0),
                        "gate_2_failed": int(base.get("candidates_failed_backtest") or 0),
                    },
                    "refresh_ratio": _refresh_ratio(research_records),
                    "promotion_ratio": _promotion_ratio(
                        live_candidate_ready_count,
                        len(research_records),
                    ),
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
                    "submission_action_type_counts": submission_action_type_counts,
                    "strategy_status_counts": strategy_status_counts,
                    "source_mix": _source_mix(incubation_records),
                    "family_mix": _family_mix(incubation_records),
                    "gate_hit": {
                        "gate_3_input": int(base.get("gate_3_input") or 0),
                        "gate_3_passed": int(base.get("gate_3_passed") or 0),
                        "gate_3_failed": int(base.get("gate_3_failed") or 0),
                        "submitted_count": int(base.get("submitted") or 0),
                        "created_strategy_pool_count": int(base.get("created_strategy_pool") or 0),
                    },
                    "refresh_ratio": _refresh_ratio(incubation_records),
                    "promotion_ratio": _promotion_ratio(
                        int(base.get("live_ready_review_count") or live_review_ready_count),
                        len(incubation_records),
                    ),
                },
                "live_ready_summary": {
                    "live_candidate_ready_count": live_candidate_ready_count,
                    "live_review_ready_count": live_review_ready_count,
                    "live_ready_review_count": int(base.get("live_ready_review_count") or 0),
                    "direct_trade_candidate_count": int(base.get("direct_trade_candidate_count") or 0),
                    "paper_account_bound_count": int(base.get("paper_account_bound_count") or 0),
                    "runtime_review_count": int(base.get("runtime_review_count") or 0),
                    "promotion_review_count": int(base.get("promotion_review_count") or 0),
                    "submission_action_type_counts": submission_action_type_counts,
                    "promotion_review_status_counts": dict(base.get("promotion_review_status_counts") or {}),
                    "source_mix": _source_mix(live_ready_records),
                    "family_mix": _family_mix(live_ready_records),
                    "gate_hit": {
                        "live_candidate_ready_count": live_candidate_ready_count,
                        "live_review_ready_count": live_review_ready_count,
                        "live_ready_review_count": int(base.get("live_ready_review_count") or 0),
                        "direct_trade_candidate_count": int(base.get("direct_trade_candidate_count") or 0),
                        "paper_account_bound_count": int(base.get("paper_account_bound_count") or 0),
                        "runtime_review_count": int(base.get("runtime_review_count") or 0),
                        "promotion_review_count": int(base.get("promotion_review_count") or 0),
                    },
                    "refresh_ratio": _refresh_ratio(live_ready_records),
                    "promotion_ratio": _promotion_ratio(
                        int(base.get("promotion_review_count") or 0),
                        max(
                            int(base.get("live_ready_review_count") or 0),
                            len(live_ready_records),
                        ),
                    ),
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
