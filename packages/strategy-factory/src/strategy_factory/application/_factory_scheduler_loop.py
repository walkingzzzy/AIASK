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
    AUTONOMY_MAX_RESEARCH_TASKS,
    AUTONOMY_MAX_BULK_RESEARCH_TASKS,
    AUTONOMY_RESERVED_BULK_RESEARCH_TASKS,
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_TASK_HARD_CAP,
    AUTONOMY_STARTUP_DELAY_SEC,
    FACTORY_DAILY_RUN_TIME,
    FACTORY_ERROR_BACKOFF_SEC,
    FACTORY_EVENT_RUNTIME_MODE,
    FACTORY_FACTOR_AUTO_REFRESH,
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    FACTORY_MARKET_HOURS_INTERVAL_SEC,
    FACTORY_MAX_DAILY_RUNS,
    FACTORY_OFF_HOURS_INTERVAL_SEC,
    FACTORY_PRE_GATE_ENABLED,
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
    STOCK_STRATEGY_MATRIX_BATCH_SIZE,
    STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY,
    STOCK_STRATEGY_MATRIX_ENABLED,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
    STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
    STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
    STOCK_STRATEGY_MATRIX_RUN_WINDOW,
    STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
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
from ._budget_feedback import (
    CONTROL_MODE_SEVERITY,
    collect_generator_mode_feedback_controls,
    extract_feedback_root,
    normalize_text as _normalize_feedback_text,
    summarize_task_feedback_controls,
)
from ._autonomy_task_selection import (
    apply_scheduler_planning_controls as _apply_scheduler_planning_controls_payload,
    build_scan_only_task_budget_meta as _build_scan_only_task_budget_meta_payload,
    merge_autonomy_tasks_with_budget as _merge_autonomy_tasks_with_budget_payload,
)
from ._autonomy_task_executor import (
    AutonomyTaskExecutionContext as _AutonomyTaskExecutionContext,
    execute_autonomy_task as _execute_autonomy_task_payload,
)
from ._autonomy_stage_artifacts import (
    attach_autonomy_stage_artifacts as _attach_autonomy_stage_artifacts_payload,
)
from ._autonomy_stage_summary import (
    build_autonomy_stage_summary as _build_autonomy_stage_summary_payload,
)
from ._bulk_planner_summary import (
    build_bulk_planner_error_report as _build_bulk_planner_error_report_payload,
    build_default_bulk_report as _build_default_bulk_report_payload,
    normalize_bulk_report_summary as _normalize_bulk_report_summary_payload,
)
from ._combined_scan_report import build_combined_scan_report as _build_combined_scan_report_payload
from ._bulk_cursor import (
    extract_bulk_stock_cursor as _extract_bulk_stock_cursor_payload,
    resolve_bulk_stock_matrix_cursor as _resolve_bulk_stock_matrix_cursor_payload,
)
from .utils import _extract_event_context as _local_extract_event_context
from .research.matrix import StockStrategyMatrixPlanner
from .research_plane_contract import (
    build_candidate_artifact,
    build_research_evidence_artifact,
    build_task_artifact,
)
from ..domain.targets import (
    _extract_target_codes_from_payload,
    _normalize_research_task_contract,
    _normalize_target_codes,
)
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

        @staticmethod
        def _compact_task_mapping(
            payload: Optional[dict[str, Any]],
            *,
            keys: tuple[str, ...],
        ) -> dict[str, Any]:
            source = dict(payload or {})
            result: dict[str, Any] = {}
            for key in keys:
                value = source.get(key)
                if value in (None, "", [], {}):
                    continue
                result[key] = value
            return result

        @staticmethod
        def _build_task_scan_artifact(
            report: Optional[dict[str, Any]],
            *,
            task_source_counts: Optional[dict[str, Any]] = None,
            event_task_count: Optional[int] = None,
            snapshot_task_count: Optional[int] = None,
            bulk_stock_task_count: Optional[int] = None,
        ) -> dict[str, Any]:
            payload = dict(report or {})
            summary = dict(payload.get("summary") or {})
            source_counts = dict(task_source_counts or summary.get("task_sources") or {})
            resolved_event_task_count = (
                int(event_task_count)
                if event_task_count is not None
                else int(summary.get("event_task_count") or 0)
            )
            resolved_snapshot_task_count = (
                int(snapshot_task_count)
                if snapshot_task_count is not None
                else int(source_counts.get("snapshot") or 0)
            )
            resolved_bulk_stock_task_count = (
                int(bulk_stock_task_count)
                if bulk_stock_task_count is not None
                else int(summary.get("bulk_stock_task_count") or source_counts.get("bulk_stock_matrix") or 0)
            )
            return build_task_artifact(
                {
                    "task_scan": payload,
                    "task_source_counts": source_counts,
                    "event_task_count": resolved_event_task_count,
                    "snapshot_task_count": resolved_snapshot_task_count,
                    "bulk_stock_task_count": resolved_bulk_stock_task_count,
                }
            )

        @staticmethod
        def _normalize_external_request_status(status: Any) -> str:
            return str(status or "").strip().lower() or "unknown"

        @classmethod
        def _summarize_external_request_status_counts(
            cls,
            requests: Optional[list[dict[str, Any]]],
        ) -> dict[str, int]:
            counts: dict[str, int] = {}
            for item in list(requests or []):
                status = cls._normalize_external_request_status(dict(item or {}).get("status"))
                counts[status] = counts.get(status, 0) + 1
            return counts

        @classmethod
        def _count_external_network_requests(
            cls,
            requests: Optional[list[dict[str, Any]]],
        ) -> int:
            total = 0
            for item in list(requests or []):
                payload = dict(item or {})
                status = cls._normalize_external_request_status(payload.get("status"))
                if status in {"compatibility_skip", "cooldown_skip"}:
                    continue
                metrics = dict(payload.get("request_metrics") or {})
                try:
                    attempt_count = int(metrics.get("attempt_count") or 0)
                except Exception:
                    attempt_count = 0
                total += max(attempt_count, 1)
            return total

        @classmethod
        def _count_external_real_requests(
            cls,
            requests: Optional[list[dict[str, Any]]],
        ) -> int:
            total = 0
            for item in list(requests or []):
                status = cls._normalize_external_request_status(dict(item or {}).get("status"))
                if status in {"compatibility_skip", "cooldown_skip"}:
                    continue
                total += 1
            return total

        @classmethod
        def _request_is_compatibility_failure(
            cls,
            request: Optional[dict[str, Any]],
        ) -> bool:
            payload = dict(request or {})
            status = cls._normalize_external_request_status(payload.get("status"))
            if status in {"compatibility_skip", "cooldown_skip"}:
                return False
            metrics = dict(payload.get("request_metrics") or {})
            metric_status = cls._normalize_external_request_status(metrics.get("status"))
            error_type = str(payload.get("error_type") or metrics.get("last_error_type") or "").strip().lower()
            error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
            return (
                metric_status == "compatibility_failed"
                or error_type == "providercompatibilityerror"
                or "missing extractable content" in error_text
            )

        @classmethod
        def _request_is_empty_200_response(
            cls,
            request: Optional[dict[str, Any]],
        ) -> bool:
            payload = dict(request or {})
            metrics = dict(payload.get("request_metrics") or {})
            if bool(metrics.get("empty_200_response")):
                return True
            if not cls._request_is_compatibility_failure(payload):
                return False
            error_text = str(payload.get("error") or metrics.get("last_error") or "").strip().lower()
            return "missing extractable content" in error_text

        @classmethod
        def _summarize_task_llm_generation(cls, llm_generation: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(llm_generation or {})
            external = dict(payload.get("external_provider") or {})
            requests = list(external.get("requests") or [])
            external_summary = cls._compact_task_mapping(
                external,
                keys=(
                    "enabled",
                    "provider",
                    "model",
                    "status",
                    "selected_count",
                    "viable_selected_count",
                    "fallback_count",
                    "elapsed_seconds",
                    "last_error_type",
                    "last_error",
                    "stage_attempt_count",
                    "network_request_count",
                    "real_request_count",
                    "compatibility_skip_count",
                    "cooldown_skip_count",
                    "compatibility_failure_count",
                    "compatibility_failure_ratio",
                    "effective_response_count",
                    "effective_response_ratio",
                    "empty_200_response_count",
                ),
            )
            request_status_counts = dict(external.get("request_status_counts") or {}) or cls._summarize_external_request_status_counts(requests)
            if requests:
                real_request_count = int(external.get("real_request_count") or cls._count_external_real_requests(requests))
                compatibility_failure_count = int(
                    external.get("compatibility_failure_count")
                    or sum(1 for item in requests if cls._request_is_compatibility_failure(item))
                )
                effective_response_count = int(
                    external.get("effective_response_count")
                    or sum(
                        1
                        for item in requests
                        if cls._normalize_external_request_status(dict(item or {}).get("status")) == "succeeded"
                    )
                )
                empty_200_response_count = int(
                    external.get("empty_200_response_count")
                    or sum(1 for item in requests if cls._request_is_empty_200_response(item))
                )
                external_summary["request_count"] = len(requests)
                external_summary["stage_attempt_count"] = int(external.get("stage_attempt_count") or len(requests))
                external_summary["network_request_count"] = int(
                    external.get("network_request_count") or cls._count_external_network_requests(requests)
                )
                external_summary["real_request_count"] = real_request_count
                external_summary["compatibility_skip_count"] = int(
                    external.get("compatibility_skip_count")
                    or request_status_counts.get("compatibility_skip", 0)
                )
                external_summary["cooldown_skip_count"] = int(
                    external.get("cooldown_skip_count")
                    or request_status_counts.get("cooldown_skip", 0)
                )
                external_summary["compatibility_failure_count"] = compatibility_failure_count
                external_summary["effective_response_count"] = effective_response_count
                external_summary["empty_200_response_count"] = empty_200_response_count
                external_summary["compatibility_failure_ratio"] = (
                    external.get("compatibility_failure_ratio")
                    if external.get("compatibility_failure_ratio") is not None
                    else (round(compatibility_failure_count / real_request_count, 4) if real_request_count else 0.0)
                )
                external_summary["effective_response_ratio"] = (
                    external.get("effective_response_ratio")
                    if external.get("effective_response_ratio") is not None
                    else (round(effective_response_count / real_request_count, 4) if real_request_count else 0.0)
                )
            elif request_status_counts:
                external_summary["request_count"] = int(external.get("stage_attempt_count") or 0)
            if external.get("request_limits"):
                external_summary["request_limits"] = list(external.get("request_limits") or [])[:4]
            if request_status_counts:
                external_summary["request_status_counts"] = request_status_counts
            if requests:
                external_summary["requests_preview"] = [
                    {
                        **cls._compact_task_mapping(
                            dict(item or {}),
                            keys=(
                                "request_index",
                                "request_limit",
                                "status",
                                "returned_candidate_count",
                                "compiled_candidate_count",
                                "non_executable_candidate_count",
                                "viable_candidate_count",
                                "open_dsl_candidate_count",
                                "open_dsl_compiled_candidate_count",
                                "open_dsl_viable_candidate_count",
                                "open_dsl_rejected_count",
                                "error_type",
                                "error",
                            ),
                        ),
                        "request_metrics": cls._compact_task_mapping(
                            dict((item or {}).get("request_metrics") or {}),
                            keys=(
                                "attempt_count",
                                "prompt_chars",
                                "response_chars",
                                "elapsed_seconds",
                                "last_error_type",
                                "last_error",
                            ),
                        ),
                    }
                    for item in requests[:3]
                ]
            analysis = dict(external.get("analysis") or {})
            if analysis:
                external_summary["analysis"] = cls._compact_task_mapping(
                    analysis,
                    keys=(
                        "style_bias",
                        "market_regime",
                        "theme",
                        "direction",
                        "risk_hint",
                        "confidence",
                    ),
                )
            summary = cls._compact_task_mapping(
                payload,
                keys=(
                    "requested_limit",
                    "market_frame_ready",
                    "market_frame_rows",
                    "market_frame_source",
                    "selected_count",
                    "pipeline_run_timeout_sec",
                ),
            )
            if payload.get("selected_generators"):
                summary["selected_generators"] = dict(payload.get("selected_generators") or {})
            if payload.get("research_context_summary"):
                summary["research_context_summary"] = dict(payload.get("research_context_summary") or {})
            if external_summary:
                summary["external_provider"] = external_summary
            return {key: value for key, value in summary.items() if value not in (None, "", [], {})}

        @classmethod
        def _summarize_research_task_for_task_run(cls, task: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = _normalize_research_task_contract(task or {}) if task else {}
            summary = cls._compact_task_mapping(
                payload,
                keys=(
                    "task_id",
                    "task_key",
                    "task_source",
                    "opportunity_type",
                    "theme_code",
                    "event_id",
                    "candidate_family",
                    "factor_name",
                    "generation_limit",
                    "source_candidate_artifact_id",
                    "task_run_id",
                    "evidence_count",
                    "preference_strength",
                    "validation_focus",
                ),
            )
            target_symbols = list(payload.get("target_symbols") or [])
            if target_symbols:
                summary["target_symbols"] = target_symbols[:12]
            preferred_strategy_types = [
                str(item).strip()
                for item in list(
                    payload.get("preferred_strategy_types")
                    or payload.get("strategy_preferences")
                    or []
                )
                if str(item).strip()
            ]
            if preferred_strategy_types:
                summary["preferred_strategy_types"] = preferred_strategy_types[:6]
                summary["strategy_preferences"] = preferred_strategy_types[:6]
            allowed_strategy_types = [
                str(item).strip()
                for item in list(payload.get("allowed_strategy_types") or [])
                if str(item).strip()
            ]
            if allowed_strategy_types:
                summary["allowed_strategy_types"] = allowed_strategy_types[:6]
            evidence_refs = list(payload.get("evidence_refs") or [])
            if evidence_refs:
                summary["evidence_preview"] = [
                    cls._compact_task_mapping(
                        dict(item or {}),
                        keys=("id", "evidence_type", "symbol", "weight"),
                    )
                    for item in evidence_refs[:3]
                ]
            return summary

        @classmethod
        def _build_research_task_run_result_summary(cls, task_result: Optional[dict[str, Any]]) -> dict[str, Any]:
            payload = dict(task_result or {})
            summary = {
                "storage_mode": "summary_only",
                "task": cls._summarize_research_task_for_task_run(payload.get("task")),
                "task_run_id": payload.get("task_run_id"),
                "task_source": payload.get("task_source"),
                "event_id": payload.get("event_id"),
                "theme_code": payload.get("theme_code"),
                "evidence_count": int(payload.get("evidence_count") or 0),
                "status": payload.get("status"),
                "generated_count": int(payload.get("generated_count") or 0),
                "reviewed_count": int(payload.get("reviewed_count") or 0),
                "external_llm_status": payload.get("external_llm_status"),
                "llm_generation": cls._summarize_task_llm_generation(payload.get("llm_generation")),
                "lifecycle": dict(payload.get("lifecycle") or {}),
                "lifecycle_summary": dict(payload.get("lifecycle_summary") or {}),
            }
            if payload.get("error") not in (None, ""):
                summary["error"] = payload.get("error")
            return {key: value for key, value in summary.items() if value not in (None, "", [], {})}

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

        @classmethod
        def _bulk_stock_matrix_run_window_state(cls, now: datetime) -> dict[str, Any]:
            current_period = "market_hours" if cls._is_market_hours(now) else "off_hours"
            run_window = str(STOCK_STRATEGY_MATRIX_RUN_WINDOW or "always").strip().lower() or "always"
            configured_enabled = bool(STOCK_STRATEGY_MATRIX_ENABLED)
            run_window_active = configured_enabled and (
                run_window == "always" or run_window == current_period
            )
            skip_reason = None
            if not configured_enabled:
                skip_reason = "disabled"
            elif not run_window_active:
                skip_reason = "outside_run_window"
            return {
                "configured_enabled": configured_enabled,
                "run_window": run_window,
                "run_window_active": run_window_active,
                "current_period": current_period,
                "skip_reason": skip_reason,
            }

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

        @classmethod
        def _extract_bulk_stock_cursor(
            cls,
            summary: Optional[dict[str, Any]],
            *,
            source: str,
            run_id: Optional[str] = None,
        ) -> dict[str, Any]:
            return _extract_bulk_stock_cursor_payload(
                summary,
                source=source,
                run_id=run_id,
            )

        async def _resolve_bulk_stock_matrix_cursor(self, db) -> dict[str, Any]:
            return await _resolve_bulk_stock_matrix_cursor_payload(
                last_result=self.last_result,
                db=db,
                logger_=logger,
                call_optional_async=_call_optional_async,
            )

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
            effective_task = dict(task or {})
            provider_health = self._external_llm_health_snapshot(autonomy_gateway)
            if provider_health.get("scheduler_should_disable"):
                effective_task["disable_external_llm"] = True
                effective_task["external_llm_skip_reason"] = (
                    provider_health.get("scheduler_skip_reason") or "provider_health_blocked"
                )
            limit = max(
                1,
                min(int(effective_task.get("generation_limit") or AUTONOMY_CANDIDATES_PER_TASK), AUTONOMY_TASK_HARD_CAP),
            )
            source = f"strategy_factory:{effective_task.get('opportunity_type') or 'general'}"
            gateway_db = self._adapt_gateway_repository(db)
            timeout_sec = self._resolve_research_task_timeout_sec()
            task_id = str(effective_task.get("task_id") or effective_task.get("task_key") or source).strip() or source

            async def _run_generation(task_payload: dict[str, Any]) -> dict:
                return await asyncio.wait_for(
                    autonomy_gateway.generate_factory_candidates(
                        gateway_db,
                        snapshot,
                        limit=limit,
                        research_task=task_payload,
                        source=source,
                    ),
                    timeout=timeout_sec,
                )

            try:
                return await _run_generation(effective_task)
            except asyncio.TimeoutError as exc:
                retry_task = dict(effective_task)
                retry_applied = False
                if not retry_task.get("disable_external_llm"):
                    retry_task["disable_external_llm"] = True
                    retry_task["external_llm_skip_reason"] = "task_timeout_local_fallback"
                    retry_applied = True
                if not retry_task.get("disable_pipeline_staged"):
                    retry_task["disable_pipeline_staged"] = True
                    retry_task["pipeline_staged_skip_reason"] = "task_timeout_local_fallback"
                    retry_applied = True
                if not retry_applied:
                    raise RuntimeError(
                        f"research task {task_id} timed out after {timeout_sec:g}s"
                    ) from exc
                retry_task["task_timeout_local_fallback"] = True
                retry_task["task_timeout_local_fallback_attempts"] = int(
                    retry_task.get("task_timeout_local_fallback_attempts") or 0
                ) + 1
                try:
                    return await _run_generation(retry_task)
                except asyncio.TimeoutError as retry_exc:
                    raise RuntimeError(
                        f"research task {task_id} timed out after {timeout_sec:g}s even after local fallback retry"
                    ) from retry_exc

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
        def _get_external_llm_provider(autonomy_gateway):
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            llm_generator = getattr(generation_service, "llm_generator", None) or getattr(autonomy_target, "llm_generator", None)
            return getattr(llm_generator, "external_provider", None)

        @classmethod
        def _external_llm_health_snapshot(cls, autonomy_gateway) -> dict[str, Any]:
            external_provider = cls._get_external_llm_provider(autonomy_gateway)
            if external_provider is None:
                return {}
            snapshot_getter = getattr(external_provider, "get_health_snapshot", None)
            if not callable(snapshot_getter):
                return {}
            try:
                snapshot = snapshot_getter()
            except Exception:
                return {}
            return dict(snapshot or {})

        @classmethod
        def _external_llm_should_participate(cls, autonomy_gateway) -> bool:
            external_provider = cls._get_external_llm_provider(autonomy_gateway)
            if external_provider is None:
                return False
            try:
                if callable(getattr(external_provider, "is_enabled", None)) and not external_provider.is_enabled():
                    return False
            except Exception:
                return False
            return not bool(cls._external_llm_health_snapshot(autonomy_gateway).get("scheduler_should_disable"))

        @classmethod
        def _resolve_external_llm_concurrency_limit(cls, autonomy_gateway) -> Optional[int]:
            external_provider = cls._get_external_llm_provider(autonomy_gateway)
            if external_provider is None or not cls._external_llm_should_participate(autonomy_gateway):
                return None
            try:
                limit = int(getattr(getattr(external_provider, "config", None), "max_concurrency", 0) or 0)
            except Exception:
                return None
            return max(1, limit) if limit > 0 else None

        @staticmethod
        def _env_bool(*names: str, default: bool) -> bool:
            for name in names:
                raw = os.getenv(str(name or "").strip())
                if raw is None:
                    continue
                text = str(raw).strip().lower()
                if text in {"1", "true", "yes", "y", "on"}:
                    return True
                if text in {"0", "false", "no", "n", "off"}:
                    return False
            return bool(default)

        @classmethod
        def _bulk_tasks_use_external_llm(cls, autonomy_gateway) -> bool:
            if not cls._external_llm_should_participate(autonomy_gateway):
                return False
            autonomy_target = getattr(autonomy_gateway, "raw", autonomy_gateway)
            generation_service = getattr(autonomy_target, "generation_service", None)
            resolver = getattr(generation_service, "_bulk_llm_enabled", None)
            if callable(resolver):
                try:
                    return bool(resolver())
                except Exception:
                    pass
            return cls._env_bool(
                "STRATEGY_FACTORY_BULK_LLM_ENABLED",
                "STRATEGY_FACTORY_BULK_STOCK_MATRIX_LLM_ENABLED",
                default=False,
            )

        @classmethod
        def _resolve_research_task_concurrency(cls, autonomy_gateway, *, has_bulk_tasks: bool = False) -> int:
            effective = RESEARCH_TASK_CONCURRENCY
            provider_limit = cls._resolve_external_llm_concurrency_limit(autonomy_gateway)
            if provider_limit is not None:
                effective = min(effective, provider_limit)
            if has_bulk_tasks and cls._bulk_tasks_use_external_llm(autonomy_gateway):
                bulk_target = max(1, int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY))
                if provider_limit is not None:
                    bulk_target = min(bulk_target, provider_limit)
                effective = max(effective, bulk_target)
            return max(1, effective)

        @classmethod
        def _resolve_bulk_research_task_concurrency(cls, autonomy_gateway, *, has_bulk_tasks: bool = False) -> int:
            if not has_bulk_tasks:
                return cls._resolve_research_task_concurrency(autonomy_gateway, has_bulk_tasks=False)
            if cls._bulk_tasks_use_external_llm(autonomy_gateway):
                return cls._resolve_research_task_concurrency(autonomy_gateway, has_bulk_tasks=True)
            return max(1, int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY))

        @staticmethod
        def _resolve_research_task_timeout_sec() -> float:
            raw = str(os.getenv("STRATEGY_FACTORY_RESEARCH_TASK_TIMEOUT_SEC", "180") or "180").strip()
            try:
                value = float(raw)
            except Exception:
                value = 180.0
            return max(15.0, min(value, 1800.0))

        @staticmethod
        def _control_mode_from_severity(severity: int) -> str:
            normalized = max(0, int(severity or 0))
            if normalized >= 3:
                return "freeze"
            if normalized >= 2:
                return "suppress"
            if normalized >= 1:
                return "cooldown"
            return "normal"

        async def _load_recent_factory_run_summaries(
            self,
            db,
            *,
            limit: int = 4,
        ) -> list[dict[str, Any]]:
            summaries: list[dict[str, Any]] = []
            seen: set[str] = set()

            def _append(entry: Optional[dict[str, Any]]) -> None:
                payload = dict(entry or {})
                summary = dict(payload.get("summary") or {})
                if not summary:
                    return
                run_id = str(payload.get("run_id") or summary.get("run_id") or "").strip()
                marker = run_id or str(summary.get("trace_id") or summary.get("completed_at") or len(summaries))
                if marker in seen:
                    return
                seen.add(marker)
                summaries.append(summary)

            _append(dict(self.last_result or {}))
            fetch_limit = max(1, int(limit or 1))
            if hasattr(db, "list_strategy_factory_runs"):
                try:
                    rows = await _call_optional_async(
                        db,
                        "list_strategy_factory_runs",
                        fetch_limit,
                        default=[],
                    )
                except Exception:
                    rows = []
                for row in list(rows or []):
                    _append(dict(row or {}))
                    if len(summaries) >= fetch_limit:
                        break
            elif hasattr(db, "get_latest_strategy_factory_run"):
                try:
                    latest = await _call_optional_async(db, "get_latest_strategy_factory_run", default=None)
                except Exception:
                    latest = None
                _append(dict(latest or {}))
            return summaries[:fetch_limit]

        @classmethod
        def _build_external_provider_control(
            cls,
            recent_summaries: list[dict[str, Any]],
            provider_health: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            summaries = [dict(item or {}) for item in list(recent_summaries or []) if isinstance(item, dict)]
            health = dict(provider_health or {})
            stage_attempt_count = sum(
                int(item.get("external_llm_stage_attempt_count") or item.get("external_llm_attempt_count") or 0)
                for item in summaries
            )
            real_request_count = sum(int(item.get("external_llm_real_request_count") or 0) for item in summaries)
            compatibility_skip_count = sum(int(item.get("external_llm_compatibility_skip_count") or 0) for item in summaries)
            compatibility_failure_count = sum(
                int(item.get("external_llm_compatibility_failure_count") or 0) for item in summaries
            )
            effective_response_count = sum(
                int(item.get("external_llm_effective_response_count") or 0) for item in summaries
            )
            empty_200_response_count = sum(
                int(item.get("external_llm_empty_200_response_count") or 0) for item in summaries
            )
            compatibility_skip_ratio = (
                round(compatibility_skip_count / stage_attempt_count, 4) if stage_attempt_count else 0.0
            )
            compatibility_failure_ratio = (
                round(compatibility_failure_count / real_request_count, 4) if real_request_count else 0.0
            )
            effective_response_ratio = (
                round(effective_response_count / real_request_count, 4) if real_request_count else 0.0
            )
            empty_200_response_ratio = (
                round(empty_200_response_count / real_request_count, 4) if real_request_count else 0.0
            )

            severity = 0
            reasons: list[str] = []
            health_status = _normalize_feedback_text(health.get("health_status"))
            if bool(health.get("scheduler_should_disable")) or health_status in {"failed", "error"}:
                severity = max(severity, 2)
                reasons.append(
                    str(health.get("scheduler_skip_reason") or health_status or "provider_health_blocked")
                )
            elif health_status in {"degraded", "warning"} or bool(health.get("compatibility_cooldown_active")):
                severity = max(severity, 1)
                reasons.append("provider_health_degraded")

            if stage_attempt_count >= 3 and compatibility_skip_ratio >= 0.75:
                severity = max(severity, 2)
                reasons.append("compatibility_skip_ratio_too_high")
            elif stage_attempt_count >= 2 and compatibility_skip_ratio >= 0.4:
                severity = max(severity, 1)
                reasons.append("compatibility_skip_ratio_elevated")

            if real_request_count >= 2 and (
                effective_response_ratio <= 0.15
                or compatibility_failure_ratio >= 0.65
                or empty_200_response_ratio >= 0.5
            ):
                severity = max(severity, 2)
                reasons.append("effective_response_ratio_too_low")
            elif real_request_count >= 2 and (
                effective_response_ratio < 0.45
                or compatibility_failure_ratio >= 0.35
                or empty_200_response_ratio >= 0.25
            ):
                severity = max(severity, 1)
                reasons.append("effective_response_ratio_degraded")

            deduped_reasons: list[str] = []
            for reason in reasons:
                token = str(reason or "").strip()
                if token and token not in deduped_reasons:
                    deduped_reasons.append(token)

            control_mode = cls._control_mode_from_severity(severity)
            return {
                "control_mode": control_mode,
                "control_reasons": deduped_reasons,
                "health_status": health_status or None,
                "stage_attempt_count": stage_attempt_count,
                "real_request_count": real_request_count,
                "compatibility_skip_count": compatibility_skip_count,
                "compatibility_skip_ratio": compatibility_skip_ratio,
                "compatibility_failure_count": compatibility_failure_count,
                "compatibility_failure_ratio": compatibility_failure_ratio,
                "effective_response_count": effective_response_count,
                "effective_response_ratio": effective_response_ratio,
                "empty_200_response_count": empty_200_response_count,
                "empty_200_response_ratio": empty_200_response_ratio,
                "scheduler_should_disable": bool(health.get("scheduler_should_disable")),
                "scheduler_skip_reason": health.get("scheduler_skip_reason"),
            }

        @classmethod
        def _build_generator_mode_controls(
            cls,
            recent_summaries: list[dict[str, Any]],
            *,
            feedback_root: Any = None,
        ) -> dict[str, dict[str, Any]]:
            history_by_mode: dict[str, list[dict[str, Any]]] = {}
            for item in list(recent_summaries or []):
                summary = dict(item or {})
                mode_metrics = dict(summary.get("generator_mode_submission_metrics") or {})
                for mode_name, raw_metrics in mode_metrics.items():
                    normalized_mode = _normalize_feedback_text(mode_name)
                    if not normalized_mode:
                        continue
                    history_by_mode.setdefault(normalized_mode, []).append(dict(raw_metrics or {}))

            controls: dict[str, dict[str, Any]] = {}
            for mode_name in ("external_llm", "pipeline_staged", "rl_bandit"):
                history = history_by_mode.get(mode_name) or []
                stagnant_runs = 0
                last_metrics: dict[str, Any] = {}
                for metrics in history:
                    last_metrics = dict(metrics or {})
                    strategy_count = int(last_metrics.get("strategy_count") or 0)
                    if strategy_count <= 0:
                        break
                    created_total_count = int(last_metrics.get("created_total_count") or 0)
                    refresh_absorption_ratio = float(last_metrics.get("refresh_absorption_ratio") or 0.0)
                    tested_object_hash_changed_count = int(
                        last_metrics.get("tested_object_hash_changed_count") or 0
                    )
                    if (
                        created_total_count == 0
                        and refresh_absorption_ratio >= 0.6
                        and tested_object_hash_changed_count <= 0
                    ):
                        stagnant_runs += 1
                        continue
                    break
                if stagnant_runs <= 0:
                    continue
                severity = 2 if stagnant_runs >= 3 else 1
                controls[mode_name] = {
                    "control_mode": cls._control_mode_from_severity(severity),
                    "stagnant_runs": stagnant_runs,
                    "control_reasons": ["refresh_absorption_without_creation"],
                    "metrics": last_metrics,
                }
            feedback_controls = collect_generator_mode_feedback_controls(feedback_root)
            for mode_name, incoming_control in feedback_controls.items():
                normalized_mode = _normalize_feedback_text(mode_name)
                if not normalized_mode:
                    continue
                existing = dict(controls.get(normalized_mode) or {})
                existing_mode = _normalize_feedback_text(existing.get("control_mode")) or "normal"
                incoming_mode = _normalize_feedback_text(incoming_control.get("control_mode")) or "normal"
                existing_severity = CONTROL_MODE_SEVERITY.get(existing_mode, 0)
                incoming_severity = CONTROL_MODE_SEVERITY.get(incoming_mode, 0)
                merged_reasons: list[str] = []
                for reason in [
                    *list(existing.get("control_reasons") or []),
                    *list(incoming_control.get("control_reasons") or []),
                ]:
                    token = str(reason or "").strip()
                    if token and token not in merged_reasons:
                        merged_reasons.append(token)
                merged_sources: list[str] = []
                for source in [existing.get("source"), incoming_control.get("source")]:
                    token = str(source or "").strip()
                    if token and token not in merged_sources:
                        merged_sources.append(token)
                merged_families: list[str] = []
                for family in [
                    *list(existing.get("families") or []),
                    *list(incoming_control.get("families") or []),
                ]:
                    token = _normalize_feedback_text(family)
                    if token and token not in merged_families:
                        merged_families.append(token)
                winner = dict(existing or {})
                if incoming_severity >= existing_severity:
                    winner.update(dict(incoming_control or {}))
                winner["control_mode"] = (
                    incoming_mode if incoming_severity >= existing_severity else existing_mode
                ) or "normal"
                winner["control_reasons"] = merged_reasons
                winner["source"] = merged_sources[0] if len(merged_sources) == 1 else merged_sources
                winner["families"] = merged_families
                winner["feedback_observed_count"] = int(
                    incoming_control.get("feedback_observed_count")
                    or existing.get("feedback_observed_count")
                    or 0
                )
                controls[normalized_mode] = winner
            return controls

        @classmethod
        def _apply_scheduler_planning_controls(
            cls,
            tasks: list[dict[str, Any]],
            *,
            feedback_root: Any,
            provider_control: Optional[dict[str, Any]] = None,
            generator_mode_controls: Optional[dict[str, dict[str, Any]]] = None,
        ) -> list[dict[str, Any]]:
            return _apply_scheduler_planning_controls_payload(
                list(tasks or []),
                feedback_root=feedback_root,
                provider_control=provider_control or {},
                generator_mode_controls=generator_mode_controls or {},
            )

        @classmethod
        def _merge_autonomy_tasks_with_budget(
            cls,
            scanner,
            scan_tasks: list[dict[str, Any]],
            bulk_tasks: list[dict[str, Any]],
        ) -> tuple[list[dict[str, Any]], dict[str, int]]:
            return _merge_autonomy_tasks_with_budget_payload(
                scanner,
                scan_tasks,
                bulk_tasks,
            )

        async def _run_autonomy_batches(self, db, snapshot: dict) -> dict:
            factory_pkg = get_strategy_factory_package()
            scanner = factory_pkg.MarketOpportunityScanner()
            scan_report = await scanner.scan(db, snapshot)
            autonomy_gateway = self._get_autonomy_gateway()
            factor_research = dict(snapshot.get("factor_research") or {})
            feedback_root = extract_feedback_root(
                factor_research.get("lifecycle_feedback_input")
                or factor_research.get("budget_feedback")
                or {}
            )
            recent_run_summaries = await self._load_recent_factory_run_summaries(db, limit=4)
            external_provider_health = self._external_llm_health_snapshot(autonomy_gateway)
            external_provider_control = self._build_external_provider_control(
                recent_run_summaries,
                external_provider_health,
            )
            generator_mode_controls = self._build_generator_mode_controls(
                recent_run_summaries,
                feedback_root=feedback_root,
            )
            scan_tasks = self._apply_scheduler_planning_controls(
                list(scan_report.get("tasks") or []),
                feedback_root=feedback_root,
                provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
            )
            tasks = list(scan_tasks)
            scan_summary = dict(scan_report.get("summary") or {})
            scan_feedback_summary = summarize_task_feedback_controls(scan_tasks)
            scan_summary.update(
                {
                    "feedback_control_mode_counts": dict(scan_feedback_summary.get("feedback_control_mode_counts") or {}),
                    "feedback_target_pool_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "feedback_holding_bucket_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "feedback_generator_mode_control_mode_counts": dict(
                        scan_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "feedback_cooldown_task_count": int(
                        scan_feedback_summary.get("feedback_cooldown_task_count") or 0
                    ),
                    "feedback_blocked_task_count": int(
                        scan_feedback_summary.get("feedback_blocked_task_count") or 0
                    ),
                    "suppressed_families": list(scan_feedback_summary.get("suppressed_families") or []),
                    "suppressed_target_pools": list(scan_feedback_summary.get("suppressed_target_pools") or []),
                    "suppressed_generator_modes": list(scan_feedback_summary.get("suppressed_generator_modes") or []),
                    "external_llm_provider_control_mode": external_provider_control.get("control_mode"),
                    "external_llm_provider_control_reasons": list(
                        external_provider_control.get("control_reasons") or []
                    ),
                    "generator_mode_controls": dict(generator_mode_controls or {}),
                }
            )
            scan_report = {**scan_report, "summary": scan_summary, "tasks": scan_tasks}
            scan_task_artifact = dict(scan_report.get("task_artifact") or {})
            if not scan_task_artifact:
                scan_task_artifact = self._build_task_scan_artifact(
                    scan_report,
                    task_source_counts=dict(scan_summary.get("task_sources") or {}),
                    event_task_count=int(scan_summary.get("event_task_count") or 0),
                    snapshot_task_count=int((scan_summary.get("task_sources") or {}).get("snapshot") or 0),
                    bulk_stock_task_count=0,
                )
            scan_summary.update(
                {
                    "task_artifact_contract_version": scan_task_artifact.get("contract_version"),
                    "task_artifact_available": bool(scan_task_artifact.get("available")),
                }
            )
            scan_report = {
                **scan_report,
                "summary": scan_summary,
                "task_artifact": scan_task_artifact,
            }
            bulk_cursor = await self._resolve_bulk_stock_matrix_cursor(db)
            bulk_window_state = self._bulk_stock_matrix_run_window_state(self._now())
            resume_from_cursor = bool(
                bulk_cursor.get("available")
                and bulk_cursor.get("enabled")
                and str(bulk_cursor.get("source") or "").strip().lower() in {"last_result", "persisted_run"}
                and not bool(bulk_window_state.get("run_window_active"))
            )
            if resume_from_cursor:
                bulk_window_state = {
                    **bulk_window_state,
                    "configured_enabled": True,
                    "run_window_active": True,
                    "skip_reason": None,
                }
            bulk_report: dict[str, Any] = _build_default_bulk_report_payload(
                bulk_window_state,
                bulk_cursor,
            )
            if bool(bulk_window_state.get("run_window_active")):
                try:
                    bulk_report = await StockStrategyMatrixPlanner().plan(
                        db,
                        {
                            **snapshot,
                            "bulk_stock_matrix_task_offset": int(bulk_cursor.get("next_task_offset") or 0),
                            "bulk_stock_matrix_universe_offset": int(bulk_cursor.get("next_universe_offset") or 0),
                            "bulk_stock_matrix_cycle_index": int(self._cycle_count),
                            "bulk_stock_matrix_cursor_source": bulk_cursor.get("source"),
                            "bulk_stock_matrix_cursor_resume_from_run_id": bulk_cursor.get("resume_from_run_id"),
                        },
                    )
                except Exception as exc:
                    logger.warning("StrategyFactory: bulk stock-strategy matrix planning failed: %s", exc)
                    bulk_report = _build_bulk_planner_error_report_payload(
                        bulk_window_state,
                        bulk_cursor,
                        exc,
                    )
            bulk_report = _normalize_bulk_report_summary_payload(
                bulk_report,
                bulk_window_state,
                bulk_cursor,
            )
            bulk_summary = dict(bulk_report.get("summary") or {})
            bulk_tasks = self._apply_scheduler_planning_controls(
                list(bulk_report.get("tasks") or []),
                feedback_root=feedback_root,
                provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
            )
            bulk_feedback_summary = summarize_task_feedback_controls(bulk_tasks)
            bulk_summary.update(
                {
                    "feedback_control_mode_counts": dict(bulk_feedback_summary.get("feedback_control_mode_counts") or {}),
                    "feedback_target_pool_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "feedback_holding_bucket_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_holding_bucket_control_mode_counts") or {}
                    ),
                    "feedback_generator_mode_control_mode_counts": dict(
                        bulk_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "feedback_cooldown_task_count": int(
                        bulk_feedback_summary.get("feedback_cooldown_task_count") or 0
                    ),
                    "feedback_blocked_task_count": int(
                        bulk_feedback_summary.get("feedback_blocked_task_count") or 0
                    ),
                    "suppressed_families": list(bulk_feedback_summary.get("suppressed_families") or []),
                    "suppressed_target_pools": list(bulk_feedback_summary.get("suppressed_target_pools") or []),
                    "suppressed_generator_modes": list(bulk_feedback_summary.get("suppressed_generator_modes") or []),
                    "external_llm_provider_control_mode": external_provider_control.get("control_mode"),
                    "external_llm_provider_control_reasons": list(
                        external_provider_control.get("control_reasons") or []
                    ),
                    "generator_mode_controls": dict(generator_mode_controls or {}),
                }
            )
            bulk_report = {**bulk_report, "summary": bulk_summary, "tasks": bulk_tasks}
            bulk_task_artifact = dict(bulk_report.get("task_artifact") or {})
            if not bulk_task_artifact and bool((bulk_report.get("summary") or {}).get("enabled")):
                bulk_task_artifact = self._build_task_scan_artifact(
                    bulk_report,
                    task_source_counts={"bulk_stock_matrix": len(bulk_tasks)},
                    event_task_count=0,
                    snapshot_task_count=0,
                    bulk_stock_task_count=len(bulk_tasks),
                )
            if bulk_task_artifact:
                bulk_summary.update(
                    {
                        "task_artifact_contract_version": bulk_task_artifact.get("contract_version"),
                        "task_artifact_available": bool(bulk_task_artifact.get("available")),
                    }
                )
                bulk_report = {
                    **bulk_report,
                    "summary": bulk_summary,
                    "task_artifact": bulk_task_artifact,
                }
            if bulk_tasks:
                tasks, task_budget_meta = self._merge_autonomy_tasks_with_budget(
                    scanner,
                    scan_tasks,
                    bulk_tasks,
                )
            else:
                tasks = [
                    dict(task or {})
                    for task in list(scan_tasks or [])
                    if not bool(dict(task or {}).get("feedback_generation_blocked"))
                    and _normalize_feedback_text(dict(task or {}).get("feedback_control_mode")) not in {"suppress", "freeze"}
                ]
                task_budget_meta = _build_scan_only_task_budget_meta_payload(scan_tasks, tasks)
            task_source_counts = dict(scan_summary.get("task_sources") or scanner._build_task_source_counts(tasks))
            if bulk_tasks:
                task_source_counts = scanner._build_task_source_counts(tasks)
            event_task_count = int(scan_summary.get("event_task_count") or task_source_counts.get("event_driven", 0))
            combined_scan_report = _build_combined_scan_report_payload(
                scan_summary=scan_summary,
                tasks=tasks,
                task_source_counts=task_source_counts,
                event_task_count=event_task_count,
                bulk_tasks=bulk_tasks,
                bulk_report=bulk_report,
                bulk_cursor=bulk_cursor,
                task_budget_meta=task_budget_meta,
                external_provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
                opportunity_scan=scan_report,
            )
            autonomy_gateway = self._get_autonomy_gateway()
            generated_candidates: List[dict] = []
            all_experiments: List[dict] = []
            task_results: List[dict] = []
            external_status_counts: Dict[str, int] = {}
            total_attempt_count = 0
            total_network_request_count = 0
            total_real_request_count = 0
            total_compatibility_skip_count = 0
            total_cooldown_skip_count = 0
            total_compatibility_failure_count = 0
            total_effective_response_count = 0
            total_empty_200_response_count = 0
            total_request_status_counts: Dict[str, int] = {}
            total_selected_count = 0
            total_evidence_count = 0
            last_error_type = None
            last_error = None
            elapsed_seconds = 0.0
            persistence_failures: List[dict[str, Any]] = []
            _agg_lock = asyncio.Lock()
            shared_generation_context_preloaded = await self._prepare_shared_generation_context(autonomy_gateway, db, snapshot)
            has_bulk_tasks = bool([task for task in tasks if str(task.get("task_source") or "").strip().lower() == "bulk_stock_matrix"])
            effective_research_concurrency = self._resolve_research_task_concurrency(
                autonomy_gateway,
                has_bulk_tasks=has_bulk_tasks,
            )
            effective_bulk_research_concurrency = self._resolve_bulk_research_task_concurrency(
                autonomy_gateway,
                has_bulk_tasks=has_bulk_tasks,
            )
            split_bulk_concurrency = bool(
                has_bulk_tasks and effective_bulk_research_concurrency != effective_research_concurrency
            )
            sem = asyncio.Semaphore(effective_research_concurrency)
            bulk_sem = asyncio.Semaphore(effective_bulk_research_concurrency) if split_bulk_concurrency else sem

            async def _run_one_task(task: dict) -> None:
                nonlocal total_attempt_count, total_network_request_count
                nonlocal total_real_request_count
                nonlocal total_compatibility_skip_count, total_cooldown_skip_count
                nonlocal total_compatibility_failure_count, total_effective_response_count, total_empty_200_response_count
                nonlocal total_selected_count, total_evidence_count
                nonlocal last_error_type, last_error, elapsed_seconds
                task_source = str(dict(task or {}).get("task_source") or "").strip().lower()
                task_sem = bulk_sem if task_source == "bulk_stock_matrix" else sem
                def _record_task_persistence_failure(operation: str, exc: Exception) -> None:
                    logger.warning("StrategyFactory: %s failed: %s", operation, exc)
                    self._record_persistence_failure(
                        persistence_failures,
                        operation,
                        exc,
                        stage="autonomy",
                    )

                execution = await _execute_autonomy_task_payload(
                    _AutonomyTaskExecutionContext(
                        task=dict(task or {}),
                        task_semaphore=task_sem,
                        db=db,
                        snapshot=snapshot,
                        autonomy_gateway=autonomy_gateway,
                        persist_task_evidence=self._persist_task_evidence,
                        extract_event_context=_extract_event_context,
                        call_optional_async=_call_optional_async,
                        record_persistence_failure=_record_task_persistence_failure,
                        generate_for_research_task=self._generate_for_research_task,
                        extract_cycle_llm_generation=self._extract_cycle_llm_generation,
                        extract_cycle_lifecycle=self._extract_cycle_lifecycle,
                        extract_cycle_generated_count=self._extract_cycle_generated_count,
                        extract_cycle_reviewed_count=self._extract_cycle_reviewed_count,
                        extract_cycle_candidates=self._extract_cycle_candidates,
                        extract_cycle_experiments=self._extract_cycle_experiments,
                        enrich_candidate_targeting=self._enrich_candidate_targeting,
                        build_research_task_run_result_summary=self._build_research_task_run_result_summary,
                        summarize_request_status_counts=self._summarize_external_request_status_counts,
                        count_network_requests=self._count_external_network_requests,
                        count_real_requests=self._count_external_real_requests,
                        request_is_compatibility_failure=self._request_is_compatibility_failure,
                        request_is_empty_200_response=self._request_is_empty_200_response,
                        normalize_external_request_status=self._normalize_external_request_status,
                        summarize_autonomy_lifecycle=summarize_autonomy_lifecycle,
                        autonomy_phase_order=AUTONOMY_PHASE_ORDER,
                    )
                )
                async with _agg_lock:
                    generated_candidates.extend(execution.generated_candidates)
                    all_experiments.extend(execution.experiments)
                    external_status_counts[execution.external_status] = (
                        external_status_counts.get(execution.external_status, 0) + 1
                    )
                    total_attempt_count += int(execution.request_metrics.get("attempt_count") or 0)
                    total_network_request_count += int(
                        execution.request_metrics.get("network_request_count") or 0
                    )
                    total_real_request_count += int(execution.request_metrics.get("real_request_count") or 0)
                    total_compatibility_skip_count += int(
                        execution.request_metrics.get("compatibility_skip_count") or 0
                    )
                    total_cooldown_skip_count += int(
                        execution.request_metrics.get("cooldown_skip_count") or 0
                    )
                    total_compatibility_failure_count += int(
                        execution.request_metrics.get("compatibility_failure_count") or 0
                    )
                    total_effective_response_count += int(
                        execution.request_metrics.get("effective_response_count") or 0
                    )
                    total_empty_200_response_count += int(
                        execution.request_metrics.get("empty_200_response_count") or 0
                    )
                    for request_status, count in dict(
                        execution.request_metrics.get("request_status_counts") or {}
                    ).items():
                        total_request_status_counts[request_status] = (
                            total_request_status_counts.get(request_status, 0) + int(count or 0)
                        )
                    total_selected_count += int(execution.selected_count or 0)
                    total_evidence_count += int(execution.evidence_count or 0)
                    if execution.last_error_type:
                        last_error_type = execution.last_error_type
                        last_error = execution.last_error
                    elapsed_seconds += float(execution.elapsed_seconds or 0.0)
                    task_results.append(execution.task_result_summary)

            # 有界并发执行所有研究任务
            if tasks:
                logger.info(
                    "StrategyFactory: running %d research tasks with concurrency=%d",
                    len(tasks), effective_research_concurrency,
                )
                await asyncio.gather(*[_run_one_task(t) for t in tasks])

            lifecycle_metrics = self._aggregate_task_lifecycle_metrics(task_results)
            selected_feedback_summary = summarize_task_feedback_controls(tasks)
            stage = _build_autonomy_stage_summary_payload(
                task_results=task_results,
                task_source_counts=task_source_counts,
                event_task_count=event_task_count,
                bulk_report=bulk_report,
                bulk_cursor=bulk_cursor,
                generated_candidates=generated_candidates,
                all_experiments=all_experiments,
                external_status_counts=external_status_counts,
                total_attempt_count=total_attempt_count,
                total_network_request_count=total_network_request_count,
                total_real_request_count=total_real_request_count,
                total_compatibility_skip_count=total_compatibility_skip_count,
                total_cooldown_skip_count=total_cooldown_skip_count,
                total_compatibility_failure_count=total_compatibility_failure_count,
                total_effective_response_count=total_effective_response_count,
                total_empty_200_response_count=total_empty_200_response_count,
                total_request_status_counts=total_request_status_counts,
                total_selected_count=total_selected_count,
                total_evidence_count=total_evidence_count,
                last_error_type=last_error_type,
                last_error=last_error,
                elapsed_seconds=elapsed_seconds,
                external_provider_health=external_provider_health,
                effective_research_concurrency=effective_research_concurrency,
                has_bulk_tasks=has_bulk_tasks,
                effective_bulk_research_concurrency=effective_bulk_research_concurrency,
                bulk_tasks_use_external_llm=self._bulk_tasks_use_external_llm(autonomy_gateway),
                research_task_timeout_sec=self._resolve_research_task_timeout_sec(),
                task_budget_meta=task_budget_meta,
                selected_feedback_summary=selected_feedback_summary,
                external_provider_control=external_provider_control,
                generator_mode_controls=generator_mode_controls,
                shared_generation_context_preloaded=shared_generation_context_preloaded,
                persistence_failures=persistence_failures,
                lifecycle_metrics=lifecycle_metrics,
                combined_scan_report=combined_scan_report,
            )
            stage = _attach_autonomy_stage_artifacts_payload(
                stage=stage,
                scan_task_artifact=scan_task_artifact,
                bulk_task_artifact=bulk_task_artifact,
                generated_candidates=generated_candidates,
                all_experiments=all_experiments,
                build_task_artifact=build_task_artifact,
                build_candidate_artifact=build_candidate_artifact,
                build_research_evidence_artifact=build_research_evidence_artifact,
            )
            return {"stage": stage, "candidates": generated_candidates, "experiments": all_experiments}

        async def run_once(self, db=None) -> dict:
            """执行一次完整的策略工厂流程。"""
            run_once_lock = self._get_run_once_task_lock()
            async with run_once_lock:
                task = self._run_once_task
                if task is not None and not task.done():
                    logger.info("StrategyFactory run_once already in progress; joining in-flight execution")
                else:
                    async def _execute_once() -> dict:
                        resolved_db = self._load_db() if db is None else db
                        start = self._now()
                        previous_result = self.last_result
                        context = FactoryRunContext(
                            db=resolved_db,
                            factory_pkg=get_strategy_factory_package(),
                            runtime_adapters=self._runtime_adapters,
                            start=start,
                            trace_id=f"strategy_factory:{uuid4().hex[:12]}",
                            run_id=f"factory_run_{int(start.timestamp())}_{uuid4().hex[:8]}",
                        )
                        from . import factory_scheduler as scheduler_module

                        outcome = await scheduler_module.FactoryCycleRunner(self, context).run()
                        results = outcome.result
                        self._attach_runtime_governance(results, previous_result=previous_result)
                        self.last_run = self._now()
                        self.last_result = results
                        await self._persist_run_result(
                            resolved_db,
                            results,
                            persistence_failures=outcome.persistence_failures,
                        )

                        # P2-D：用本次孵化预算 family 计数更新反馈 EMA（α=0.3）
                        try:
                            family_counts: Dict[str, int] = dict(
                                (results.get("summary") or {}).get("incubation_budget_family_counts") or {}
                            )
                            if family_counts:
                                _alpha = 0.3
                                for family, count in family_counts.items():
                                    prev = dict(self._family_gate_feedback.get(family) or {})
                                    prev_ema = float(prev.get("ema_submit_count") or 0.0)
                                    new_ema = round(_alpha * float(count) + (1.0 - _alpha) * prev_ema, 4)
                                    self._family_gate_feedback[family] = {"ema_submit_count": new_ema}
                                # 衰减未出现的 family（惩罚持续没有产出的家族）
                                for family in list(self._family_gate_feedback):
                                    if family not in family_counts:
                                        prev_ema = float((self._family_gate_feedback[family] or {}).get("ema_submit_count") or 0.0)
                                        self._family_gate_feedback[family]["ema_submit_count"] = round(
                                            (1.0 - _alpha) * prev_ema, 4
                                        )
                        except Exception:
                            pass
                        return results

                    task = asyncio.create_task(_execute_once(), name="strategy-factory-run-once")
                    self._run_once_task = task

            try:
                return await asyncio.shield(task)
            finally:
                async with run_once_lock:
                    if self._run_once_task is task and task.done():
                        self._run_once_task = None

        def status(self) -> dict:
            bulk_window_state = self._bulk_stock_matrix_run_window_state(self._now())
            bulk_stock_matrix_cursor = self._extract_bulk_stock_cursor(
                ((self.last_result or {}).get("summary") or {}),
                source="last_result" if self.last_result else "default",
                run_id=(self.last_result or {}).get("run_id"),
            )
            bulk_stock_matrix_config = {
                "enabled": bool(STOCK_STRATEGY_MATRIX_ENABLED),
                "universe_limit": int(STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT),
                "families_per_stock": int(STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK),
                "max_tasks_per_run": int(STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN),
                "max_candidates_per_run": int(STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN),
                "generation_limit_per_task": int(STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK),
                "batch_size": int(STOCK_STRATEGY_MATRIX_BATCH_SIZE),
                "bulk_concurrency": int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY),
                "run_window": str(STOCK_STRATEGY_MATRIX_RUN_WINDOW),
                "run_window_active": bool(bulk_window_state.get("run_window_active")),
                "run_window_current_period": bulk_window_state.get("current_period"),
                "tasks_per_shard": int(STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD),
                "pre_gate_enabled": bool(FACTORY_PRE_GATE_ENABLED),
            }
            last_summary = (self.last_result or {}).get("summary") if self.last_result else None
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
                "last_summary": last_summary,
                "scheduler_slo": dict((last_summary or {}).get("scheduler_slo") or {}) if last_summary else None,
                "architecture_review": dict((last_summary or {}).get("architecture_review") or {}) if last_summary else None,
                "bulk_stock_matrix_config": bulk_stock_matrix_config,
                "bulk_stock_matrix_cursor": bulk_stock_matrix_cursor,
                "daily_run_count": self._daily_run_count,
                "max_daily_runs": self.max_daily_runs,
                "cycle_count": self._cycle_count,
            }
