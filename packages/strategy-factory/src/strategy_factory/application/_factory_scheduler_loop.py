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
    apply_feedback_controls_to_task,
    collect_generator_mode_feedback_controls,
    extract_feedback_root,
    normalize_text as _normalize_feedback_text,
    summarize_task_feedback_controls,
)
from .utils import _extract_event_context as _local_extract_event_context
from .stock_strategy_matrix import StockStrategyMatrixPlanner
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

        @staticmethod
        def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
            try:
                return max(0, int(value))
            except Exception:
                return max(0, int(default))

        @classmethod
        def _extract_bulk_stock_cursor(
            cls,
            summary: Optional[dict[str, Any]],
            *,
            source: str,
            run_id: Optional[str] = None,
        ) -> dict[str, Any]:
            payload = dict(summary or {})
            known_keys = {
                "bulk_stock_matrix_enabled",
                "bulk_stock_matrix_universe_limit",
                "bulk_stock_matrix_requested_universe_offset",
                "bulk_stock_matrix_effective_universe_offset",
                "bulk_stock_matrix_universe_offset_fallback",
                "bulk_stock_matrix_eligible_stock_count",
                "bulk_stock_matrix_next_universe_offset",
                "bulk_stock_matrix_cursor_wrapped",
                "bulk_stock_matrix_requested_task_offset",
                "bulk_stock_matrix_effective_task_offset",
                "bulk_stock_matrix_task_offset_fallback",
                "bulk_stock_matrix_next_task_offset",
                "bulk_stock_matrix_task_cursor_wrapped",
                "bulk_stock_matrix_planned_task_count",
            }
            available = any(key in payload for key in known_keys)
            universe_limit = max(
                1,
                cls._coerce_non_negative_int(
                    payload.get("bulk_stock_matrix_universe_limit"),
                    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                ),
            )
            enabled = bool(payload.get("bulk_stock_matrix_enabled"))
            requested_offset = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_requested_universe_offset"),
            )
            effective_offset = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_effective_universe_offset"),
            )
            offset_fallback = bool(payload.get("bulk_stock_matrix_universe_offset_fallback"))
            eligible_stock_count = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_eligible_stock_count"),
            )
            next_offset_raw = payload.get("bulk_stock_matrix_next_universe_offset")
            if next_offset_raw is None:
                if not enabled or eligible_stock_count <= 0:
                    next_universe_offset = 0
                    cursor_wrapped = False
                elif offset_fallback:
                    next_universe_offset = universe_limit
                    cursor_wrapped = True
                elif eligible_stock_count < universe_limit:
                    next_universe_offset = 0
                    cursor_wrapped = True
                else:
                    next_universe_offset = effective_offset + universe_limit
                    cursor_wrapped = False
            else:
                next_universe_offset = cls._coerce_non_negative_int(next_offset_raw)
                if "bulk_stock_matrix_cursor_wrapped" in payload:
                    cursor_wrapped = bool(payload.get("bulk_stock_matrix_cursor_wrapped"))
                else:
                    cursor_wrapped = bool(
                        enabled and eligible_stock_count > 0 and (offset_fallback or next_universe_offset == 0)
                    )
            requested_task_offset = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_requested_task_offset"),
                requested_offset,
            )
            effective_task_offset = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_effective_task_offset"),
                effective_offset,
            )
            task_offset_fallback = bool(
                payload.get("bulk_stock_matrix_task_offset_fallback")
                if "bulk_stock_matrix_task_offset_fallback" in payload
                else offset_fallback
            )
            planned_task_count = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_planned_task_count"),
            )
            next_task_offset = cls._coerce_non_negative_int(
                payload.get("bulk_stock_matrix_next_task_offset"),
                next_universe_offset,
            )
            task_cursor_wrapped = bool(
                payload.get("bulk_stock_matrix_task_cursor_wrapped")
                if "bulk_stock_matrix_task_cursor_wrapped" in payload
                else cursor_wrapped
            )
            return {
                "available": available,
                "source": str(source or "default"),
                "resume_from_run_id": str(run_id or "").strip() or None,
                "enabled": enabled,
                "universe_limit": universe_limit,
                "requested_universe_offset": requested_offset,
                "effective_universe_offset": effective_offset,
                "universe_offset_fallback": offset_fallback,
                "eligible_stock_count": eligible_stock_count,
                "next_universe_offset": next_universe_offset,
                "cursor_wrapped": cursor_wrapped,
                "cursor_mode": str(payload.get("bulk_stock_matrix_cursor_mode") or "task_offset").strip() or "task_offset",
                "requested_task_offset": requested_task_offset,
                "effective_task_offset": effective_task_offset,
                "task_offset_fallback": task_offset_fallback,
                "planned_task_count": planned_task_count,
                "next_task_offset": next_task_offset,
                "task_cursor_wrapped": task_cursor_wrapped,
            }

        async def _resolve_bulk_stock_matrix_cursor(self, db) -> dict[str, Any]:
            last_result = dict(self.last_result or {})
            last_cursor = self._extract_bulk_stock_cursor(
                (last_result.get("summary") or {}),
                source="last_result",
                run_id=last_result.get("run_id"),
            )
            if last_cursor.get("available"):
                return last_cursor

            try:
                latest_run = await _call_optional_async(db, "get_latest_strategy_factory_run", default=None)
            except Exception as exc:
                logger.warning(
                    "StrategyFactory: failed to resolve persisted bulk cursor, falling back to default: %s",
                    exc,
                )
                latest_run = None
            latest_cursor = self._extract_bulk_stock_cursor(
                ((latest_run or {}).get("summary") or {}),
                source="persisted_run",
                run_id=(latest_run or {}).get("run_id"),
            )
            if latest_cursor.get("available"):
                return latest_cursor

            return self._extract_bulk_stock_cursor({}, source="default")

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
            try:
                return await asyncio.wait_for(
                    autonomy_gateway.generate_factory_candidates(
                        gateway_db,
                        snapshot,
                        limit=limit,
                        research_task=effective_task,
                        source=source,
                    ),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError as exc:
                task_id = str(effective_task.get("task_id") or effective_task.get("task_key") or source).strip() or source
                raise RuntimeError(
                    f"research task {task_id} timed out after {timeout_sec:g}s"
                ) from exc

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
            provider = dict(provider_control or {})
            mode_controls = {
                _normalize_feedback_text(key): dict(value or {})
                for key, value in dict(generator_mode_controls or {}).items()
                if _normalize_feedback_text(key)
            }
            provider_mode = _normalize_feedback_text(provider.get("control_mode")) or "normal"
            provider_reason = (
                (list(provider.get("control_reasons") or []) or [provider.get("scheduler_skip_reason")])[0]
                if provider_mode != "normal"
                else None
            )
            resolved: list[dict[str, Any]] = []
            for item in list(tasks or []):
                task = apply_feedback_controls_to_task(item, feedback_root)
                task_source = _normalize_feedback_text(task.get("task_source"))
                task["external_llm_provider_control_mode"] = provider_mode
                if provider_mode in {"suppress", "freeze"}:
                    task["disable_external_llm"] = True
                    task["external_llm_skip_reason"] = provider_reason or "provider_control_suppress"
                elif provider_mode == "cooldown" and task_source == "bulk_stock_matrix":
                    task["disable_external_llm"] = True
                    task["external_llm_skip_reason"] = provider_reason or "provider_control_cooldown"

                external_mode_control = dict(mode_controls.get("external_llm") or {})
                external_mode = _normalize_feedback_text(external_mode_control.get("control_mode")) or "normal"
                if external_mode != "normal":
                    task["disable_external_llm"] = True
                    task["external_llm_skip_reason"] = (
                        (list(external_mode_control.get("control_reasons") or []) or ["external_llm_mode_control"])[0]
                    )

                pipeline_mode_control = dict(mode_controls.get("pipeline_staged") or {})
                pipeline_mode = _normalize_feedback_text(pipeline_mode_control.get("control_mode")) or "normal"
                if pipeline_mode != "normal":
                    task["disable_pipeline_staged"] = True
                    task["pipeline_staged_skip_reason"] = (
                        (list(pipeline_mode_control.get("control_reasons") or []) or ["pipeline_staged_mode_control"])[0]
                    )

                optimizer_mode_control = dict(mode_controls.get("rl_bandit") or {})
                optimizer_mode = _normalize_feedback_text(optimizer_mode_control.get("control_mode")) or "normal"
                if optimizer_mode != "normal":
                    task["disable_optimizer"] = True
                    task["optimizer_skip_reason"] = (
                        (list(optimizer_mode_control.get("control_reasons") or []) or ["rl_bandit_mode_control"])[0]
                    )

                resolved.append(task)
            return resolved

        @classmethod
        def _merge_autonomy_tasks_with_budget(
            cls,
            scanner,
            scan_tasks: list[dict[str, Any]],
            bulk_tasks: list[dict[str, Any]],
        ) -> tuple[list[dict[str, Any]], dict[str, int]]:
            """Keep scan and bulk lanes on separate task budgets."""

            def _task_family_key(task: dict[str, Any]) -> str:
                payload = dict(task or {})
                research_task = dict(payload.get("research_task") or {})
                for source in (payload, research_task):
                    for key in ("candidate_family", "candidate_family_id", "strategy_family", "family"):
                        value = str(source.get(key) or "").strip().lower()
                        if value:
                            return value
                return str(
                    payload.get("opportunity_type")
                    or payload.get("strategy_type")
                    or payload.get("task_source")
                    or "unknown"
                ).strip().lower() or "unknown"

            def _interleave_by_family(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
                buckets: dict[str, list[dict[str, Any]]] = {}
                order: list[str] = []
                for task in list(tasks or []):
                    family = _task_family_key(task)
                    if family not in buckets:
                        buckets[family] = []
                        order.append(family)
                    buckets[family].append(task)
                if len(order) <= 1:
                    return list(tasks or [])
                interleaved: list[dict[str, Any]] = []
                remaining = sum(len(bucket) for bucket in buckets.values())
                while remaining > 0:
                    progressed = False
                    for family in order:
                        bucket = buckets.get(family) or []
                        if not bucket:
                            continue
                        interleaved.append(bucket.pop(0))
                        remaining -= 1
                        progressed = True
                    if not progressed:
                        break
                return interleaved

            def _safe_int(value: Any) -> int:
                try:
                    return int(value or 0)
                except Exception:
                    return 0

            def _safe_float(value: Any) -> float:
                try:
                    return float(value or 0.0)
                except Exception:
                    return 0.0

            def _feedback_blocked(task: dict[str, Any]) -> bool:
                return bool(
                    dict(task or {}).get("feedback_generation_blocked")
                    or _normalize_feedback_text(dict(task or {}).get("feedback_control_mode")) in {"suppress", "freeze"}
                )

            def _uses_bulk_matrix_plan(task: dict[str, Any]) -> bool:
                payload = dict(task or {})
                if str(payload.get("task_source") or "").strip().lower() != "bulk_stock_matrix":
                    return False
                if any(
                    _safe_int(payload.get(key)) > 0
                    for key in (
                        "matrix_budget_slot",
                        "matrix_plan_slot",
                        "matrix_allocation_pass",
                        "matrix_family_rank",
                        "matrix_stock_rank",
                        "matrix_shard_id",
                        "matrix_batch_id",
                    )
                ):
                    return True
                return (
                    _safe_float(payload.get("stock_family_priority")) > 0.0
                    or bool(payload.get("stock_family_allocation_source"))
                )

            def _bulk_task_plan_key(task: dict[str, Any]) -> tuple[Any, ...]:
                payload = dict(task or {})
                if _uses_bulk_matrix_plan(payload):
                    return (
                        0,
                        _safe_int(payload.get("matrix_budget_slot")) or 10**9,
                        _safe_int(payload.get("matrix_plan_slot")) or 10**9,
                        _safe_int(payload.get("matrix_allocation_pass")) or 10**9,
                        _safe_int(payload.get("matrix_family_rank")) or 10**9,
                        _safe_int(payload.get("matrix_stock_rank")) or 10**9,
                        _safe_int(payload.get("matrix_shard_id")) or 10**9,
                        _safe_int(payload.get("matrix_batch_id")) or 10**9,
                        -_safe_float(payload.get("stock_family_priority")),
                        -_safe_float(payload.get("matrix_priority_score")),
                        -_safe_float(payload.get("priority")),
                        str(payload.get("task_id") or payload.get("task_key") or ""),
                    )
                return (
                    1,
                    -_safe_float(scanner._task_sort_key(payload)),
                    str(payload.get("task_id") or payload.get("task_key") or ""),
                )

            planning_feedback_summary = summarize_task_feedback_controls([*list(scan_tasks or []), *list(bulk_tasks or [])])

            normalized_scan_tasks = [
                task
                for task in scanner._deduplicate_tasks(list(scan_tasks or []))
                if not _feedback_blocked(task)
            ]
            normalized_scan_tasks.sort(key=scanner._task_sort_key, reverse=True)
            normalized_bulk_tasks = [
                task
                for task in scanner._deduplicate_tasks(list(bulk_tasks or []))
                if not _feedback_blocked(task)
            ]
            bulk_selection_mode = "family_interleave"
            if any(_uses_bulk_matrix_plan(task) for task in normalized_bulk_tasks):
                normalized_bulk_tasks.sort(key=_bulk_task_plan_key)
                bulk_selection_mode = "matrix_plan_slot"
            else:
                normalized_bulk_tasks.sort(key=scanner._task_sort_key, reverse=True)
            scan_task_budget = max(0, int(AUTONOMY_MAX_RESEARCH_TASKS))
            bulk_task_budget = 0
            if normalized_bulk_tasks:
                bulk_task_budget = min(
                    len(normalized_bulk_tasks),
                    max(0, int(AUTONOMY_MAX_BULK_RESEARCH_TASKS)),
                )
            if len(normalized_scan_tasks) > scan_task_budget:
                normalized_scan_tasks = normalized_scan_tasks[:scan_task_budget]
            selected_bulk_tasks = list(normalized_bulk_tasks[:bulk_task_budget])
            if bulk_selection_mode == "family_interleave":
                selected_bulk_tasks = _interleave_by_family(selected_bulk_tasks)

            merged_tasks = scanner._deduplicate_tasks([*normalized_scan_tasks, *selected_bulk_tasks])
            selected_feedback_summary = summarize_task_feedback_controls(merged_tasks)

            selected_bulk_count = len(
                [
                    task
                    for task in merged_tasks
                    if str((task or {}).get("task_source") or "").strip().lower() == "bulk_stock_matrix"
                ]
            )
            selected_scan_count = max(0, len(merged_tasks) - selected_bulk_count)
            planned_bulk_count = len(normalized_bulk_tasks)
            return merged_tasks, {
                "max_research_tasks": int(scan_task_budget),
                "max_bulk_research_tasks": int(bulk_task_budget),
                "combined_research_task_budget": int(scan_task_budget + bulk_task_budget),
                "scan_research_task_budget": int(scan_task_budget),
                "reserved_bulk_task_budget": int(bulk_task_budget or AUTONOMY_RESERVED_BULK_RESEARCH_TASKS),
                "selected_scan_task_count": int(selected_scan_count),
                "selected_bulk_task_count": int(selected_bulk_count),
                "planned_bulk_task_count": int(planned_bulk_count),
                "clipped_bulk_task_count": int(max(0, planned_bulk_count - selected_bulk_count)),
                "bulk_selection_mode": bulk_selection_mode,
                "planned_feedback_control_mode_counts": dict(
                    planning_feedback_summary.get("feedback_control_mode_counts") or {}
                ),
                "planned_feedback_target_pool_control_mode_counts": dict(
                    planning_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                ),
                "planned_feedback_generator_mode_control_mode_counts": dict(
                    planning_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                ),
                "planned_feedback_cooldown_task_count": int(
                    planning_feedback_summary.get("feedback_cooldown_task_count") or 0
                ),
                "blocked_feedback_task_count": int(
                    planning_feedback_summary.get("feedback_blocked_task_count") or 0
                ),
                "suppressed_families": list(planning_feedback_summary.get("suppressed_families") or []),
                "suppressed_target_pools": list(planning_feedback_summary.get("suppressed_target_pools") or []),
                "suppressed_generator_modes": list(planning_feedback_summary.get("suppressed_generator_modes") or []),
                "selected_feedback_control_mode_counts": dict(
                    selected_feedback_summary.get("feedback_control_mode_counts") or {}
                ),
                "selected_feedback_target_pool_control_mode_counts": dict(
                    selected_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                ),
                "selected_feedback_generator_mode_control_mode_counts": dict(
                    selected_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                ),
            }

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
            bulk_report: dict[str, Any] = {
                "summary": {
                    "enabled": bool(bulk_window_state.get("run_window_active")),
                    "configured_enabled": bool(bulk_window_state.get("configured_enabled")),
                    "task_count": 0,
                    "stock_count": 0,
                    "family_counts": {},
                    "planned_family_counts": {},
                    "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                    "batch_size": STOCK_STRATEGY_MATRIX_BATCH_SIZE,
                    "bulk_concurrency": STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY,
                    "requested_universe_offset": int(bulk_cursor.get("next_universe_offset") or 0),
                    "effective_universe_offset": 0,
                    "universe_offset_fallback": False,
                    "next_universe_offset": 0,
                    "cursor_wrapped": False,
                    "cursor_mode": bulk_cursor.get("cursor_mode") or "task_offset",
                    "requested_task_offset": int(bulk_cursor.get("next_task_offset") or 0),
                    "effective_task_offset": 0,
                    "task_offset_fallback": False,
                    "next_task_offset": 0,
                    "task_cursor_wrapped": False,
                    "planned_task_count": int(bulk_cursor.get("planned_task_count") or 0),
                    "planned_candidate_count": 0,
                    "loaded_stock_count": 0,
                    "pages_loaded": 0,
                    "analysis_complete": False,
                    "analysis_stock_coverage_ratio": 0.0,
                    "cursor_source": bulk_cursor.get("source"),
                    "cursor_resume_from_run_id": bulk_cursor.get("resume_from_run_id"),
                    "run_window": bulk_window_state.get("run_window"),
                    "run_window_active": bool(bulk_window_state.get("run_window_active")),
                    "run_window_current_period": bulk_window_state.get("current_period"),
                    "skip_reason": bulk_window_state.get("skip_reason"),
                    "selected_shard_count": 0,
                    "selected_shard_ids": [],
                },
                "tasks": [],
            }
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
                    bulk_report = {
                        "summary": {
                            "enabled": False,
                            "configured_enabled": bool(bulk_window_state.get("configured_enabled")),
                            "task_count": 0,
                            "stock_count": 0,
                            "family_counts": {},
                            "planned_family_counts": {},
                            "universe_limit": STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
                            "batch_size": STOCK_STRATEGY_MATRIX_BATCH_SIZE,
                            "bulk_concurrency": STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY,
                            "requested_universe_offset": int(bulk_cursor.get("next_universe_offset") or 0),
                            "effective_universe_offset": 0,
                            "universe_offset_fallback": False,
                            "next_universe_offset": 0,
                            "cursor_wrapped": False,
                            "cursor_mode": bulk_cursor.get("cursor_mode") or "task_offset",
                            "requested_task_offset": int(bulk_cursor.get("next_task_offset") or 0),
                            "effective_task_offset": 0,
                            "task_offset_fallback": False,
                            "next_task_offset": 0,
                            "task_cursor_wrapped": False,
                            "planned_task_count": int(bulk_cursor.get("planned_task_count") or 0),
                            "planned_candidate_count": 0,
                            "loaded_stock_count": 0,
                            "pages_loaded": 0,
                            "analysis_complete": False,
                            "analysis_stock_coverage_ratio": 0.0,
                            "cursor_source": bulk_cursor.get("source"),
                            "cursor_resume_from_run_id": bulk_cursor.get("resume_from_run_id"),
                            "run_window": bulk_window_state.get("run_window"),
                            "run_window_active": bool(bulk_window_state.get("run_window_active")),
                            "run_window_current_period": bulk_window_state.get("current_period"),
                            "skip_reason": "planner_error",
                            "selected_shard_count": 0,
                            "selected_shard_ids": [],
                            "error": str(exc),
                        },
                        "tasks": [],
                    }
            bulk_summary = dict(bulk_report.get("summary") or {})
            bulk_summary.setdefault("configured_enabled", bool(bulk_window_state.get("configured_enabled")))
            bulk_summary.setdefault("universe_limit", STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT)
            bulk_summary.setdefault("batch_size", STOCK_STRATEGY_MATRIX_BATCH_SIZE)
            bulk_summary.setdefault("bulk_concurrency", STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY)
            bulk_summary.setdefault("requested_universe_offset", int(bulk_cursor.get("next_universe_offset") or 0))
            bulk_summary.setdefault("effective_universe_offset", 0)
            bulk_summary.setdefault("universe_offset_fallback", False)
            bulk_summary.setdefault("next_universe_offset", 0)
            bulk_summary.setdefault("cursor_wrapped", False)
            bulk_summary.setdefault("cursor_mode", bulk_cursor.get("cursor_mode") or "task_offset")
            bulk_summary.setdefault("requested_task_offset", int(bulk_cursor.get("next_task_offset") or 0))
            bulk_summary.setdefault("effective_task_offset", 0)
            bulk_summary.setdefault("task_offset_fallback", False)
            bulk_summary.setdefault("next_task_offset", 0)
            bulk_summary.setdefault("task_cursor_wrapped", False)
            bulk_summary.setdefault("planned_task_count", int(bulk_cursor.get("planned_task_count") or 0))
            bulk_summary.setdefault("planned_candidate_count", 0)
            bulk_summary.setdefault("loaded_stock_count", 0)
            bulk_summary.setdefault("pages_loaded", 0)
            bulk_summary.setdefault("analysis_complete", False)
            bulk_summary.setdefault("analysis_stock_coverage_ratio", 0.0)
            bulk_summary.setdefault("planned_family_counts", {})
            bulk_summary.setdefault("selected_shard_count", 0)
            bulk_summary.setdefault("selected_shard_ids", [])
            bulk_summary.setdefault("cursor_source", bulk_cursor.get("source"))
            bulk_summary.setdefault("cursor_resume_from_run_id", bulk_cursor.get("resume_from_run_id"))
            bulk_summary.setdefault("run_window", bulk_window_state.get("run_window"))
            bulk_summary.setdefault("run_window_active", bool(bulk_window_state.get("run_window_active")))
            bulk_summary.setdefault("run_window_current_period", bulk_window_state.get("current_period"))
            bulk_summary.setdefault("skip_reason", bulk_window_state.get("skip_reason"))
            bulk_report = {**bulk_report, "summary": bulk_summary}
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
                planning_feedback_summary = summarize_task_feedback_controls(scan_tasks)
                selected_feedback_summary = summarize_task_feedback_controls(tasks)
                task_budget_meta = {
                    "max_research_tasks": int(AUTONOMY_MAX_RESEARCH_TASKS),
                    "max_bulk_research_tasks": 0,
                    "combined_research_task_budget": int(AUTONOMY_MAX_RESEARCH_TASKS),
                    "scan_research_task_budget": int(AUTONOMY_MAX_RESEARCH_TASKS),
                    "reserved_bulk_task_budget": 0,
                    "selected_scan_task_count": int(len(tasks)),
                    "selected_bulk_task_count": 0,
                    "planned_bulk_task_count": 0,
                    "clipped_bulk_task_count": 0,
                    "planned_feedback_control_mode_counts": dict(
                        planning_feedback_summary.get("feedback_control_mode_counts") or {}
                    ),
                    "planned_feedback_target_pool_control_mode_counts": dict(
                        planning_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "planned_feedback_generator_mode_control_mode_counts": dict(
                        planning_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "planned_feedback_cooldown_task_count": int(
                        planning_feedback_summary.get("feedback_cooldown_task_count") or 0
                    ),
                    "blocked_feedback_task_count": int(
                        planning_feedback_summary.get("feedback_blocked_task_count") or 0
                    ),
                    "suppressed_families": list(planning_feedback_summary.get("suppressed_families") or []),
                    "suppressed_target_pools": list(
                        planning_feedback_summary.get("suppressed_target_pools") or []
                    ),
                    "suppressed_generator_modes": list(
                        planning_feedback_summary.get("suppressed_generator_modes") or []
                    ),
                    "selected_feedback_control_mode_counts": dict(
                        selected_feedback_summary.get("feedback_control_mode_counts") or {}
                    ),
                    "selected_feedback_target_pool_control_mode_counts": dict(
                        selected_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                    ),
                    "selected_feedback_generator_mode_control_mode_counts": dict(
                        selected_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                    ),
                }
            task_source_counts = dict(scan_summary.get("task_sources") or scanner._build_task_source_counts(tasks))
            if bulk_tasks:
                task_source_counts = scanner._build_task_source_counts(tasks)
            event_task_count = int(scan_summary.get("event_task_count") or task_source_counts.get("event_driven", 0))
            task_type_counts: Dict[str, int] = {}
            for task in tasks:
                opportunity_type = str(task.get("opportunity_type") or "unknown")
                task_type_counts[opportunity_type] = task_type_counts.get(opportunity_type, 0) + 1
            combined_scan_report = {
                "summary": {
                    **scan_summary,
                    "task_count": len(tasks),
                    "task_types": task_type_counts,
                    "task_sources": dict(task_source_counts),
                    "event_task_count": event_task_count,
                    "bulk_stock_task_count": len(bulk_tasks),
                    "bulk_stock_matrix_enabled": bool((bulk_report.get("summary") or {}).get("enabled")),
                    "bulk_stock_matrix_configured_enabled": bool((bulk_report.get("summary") or {}).get("configured_enabled")),
                    "bulk_stock_matrix_stock_count": int((bulk_report.get("summary") or {}).get("stock_count") or 0),
                    "bulk_stock_matrix_eligible_stock_count": int((bulk_report.get("summary") or {}).get("eligible_stock_count") or 0),
                    "bulk_stock_matrix_loaded_stock_count": int((bulk_report.get("summary") or {}).get("loaded_stock_count") or 0),
                    "bulk_stock_matrix_pages_loaded": int((bulk_report.get("summary") or {}).get("pages_loaded") or 0),
                    "bulk_stock_matrix_analysis_complete": bool((bulk_report.get("summary") or {}).get("analysis_complete")),
                    "bulk_stock_matrix_analysis_stock_coverage_ratio": (bulk_report.get("summary") or {}).get("analysis_stock_coverage_ratio"),
                    "bulk_stock_matrix_family_counts": dict((bulk_report.get("summary") or {}).get("family_counts") or {}),
                    "bulk_stock_matrix_planned_family_counts": dict((bulk_report.get("summary") or {}).get("planned_family_counts") or {}),
                    "bulk_stock_matrix_universe_limit": int((bulk_report.get("summary") or {}).get("universe_limit") or STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT),
                    "bulk_stock_matrix_batch_size": int((bulk_report.get("summary") or {}).get("batch_size") or STOCK_STRATEGY_MATRIX_BATCH_SIZE),
                    "bulk_stock_matrix_batch_count": int((bulk_report.get("summary") or {}).get("batch_count") or 0),
                    "bulk_stock_matrix_selected_batch_count": int((bulk_report.get("summary") or {}).get("selected_batch_count") or 0),
                    "bulk_stock_matrix_bulk_concurrency": int((bulk_report.get("summary") or {}).get("bulk_concurrency") or STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY),
                    "bulk_stock_matrix_run_window": (bulk_report.get("summary") or {}).get("run_window"),
                    "bulk_stock_matrix_run_window_active": bool((bulk_report.get("summary") or {}).get("run_window_active")),
                    "bulk_stock_matrix_run_window_current_period": (bulk_report.get("summary") or {}).get("run_window_current_period"),
                    "bulk_stock_matrix_skip_reason": (bulk_report.get("summary") or {}).get("skip_reason"),
                    "bulk_stock_matrix_requested_universe_offset": int((bulk_report.get("summary") or {}).get("requested_universe_offset") or 0),
                    "bulk_stock_matrix_effective_universe_offset": int((bulk_report.get("summary") or {}).get("effective_universe_offset") or 0),
                    "bulk_stock_matrix_universe_offset_fallback": bool((bulk_report.get("summary") or {}).get("universe_offset_fallback")),
                    "bulk_stock_matrix_next_universe_offset": int((bulk_report.get("summary") or {}).get("next_universe_offset") or 0),
                    "bulk_stock_matrix_cursor_wrapped": bool((bulk_report.get("summary") or {}).get("cursor_wrapped")),
                    "bulk_stock_matrix_cursor_mode": (bulk_report.get("summary") or {}).get("cursor_mode") or "task_offset",
                    "bulk_stock_matrix_requested_task_offset": int((bulk_report.get("summary") or {}).get("requested_task_offset") or 0),
                    "bulk_stock_matrix_effective_task_offset": int((bulk_report.get("summary") or {}).get("effective_task_offset") or 0),
                    "bulk_stock_matrix_task_offset_fallback": bool((bulk_report.get("summary") or {}).get("task_offset_fallback")),
                    "bulk_stock_matrix_next_task_offset": int((bulk_report.get("summary") or {}).get("next_task_offset") or 0),
                    "bulk_stock_matrix_task_cursor_wrapped": bool((bulk_report.get("summary") or {}).get("task_cursor_wrapped")),
                    "bulk_stock_matrix_cursor_source": (bulk_report.get("summary") or {}).get("cursor_source") or bulk_cursor.get("source"),
                    "bulk_stock_matrix_cursor_resume_from_run_id": (bulk_report.get("summary") or {}).get("cursor_resume_from_run_id") or bulk_cursor.get("resume_from_run_id"),
                    "bulk_stock_matrix_effective_task_budget": int((bulk_report.get("summary") or {}).get("effective_task_budget") or 0),
                    "bulk_stock_matrix_max_candidates_per_run": int((bulk_report.get("summary") or {}).get("max_candidates_per_run") or 0),
                    "bulk_stock_matrix_estimated_candidate_count": int((bulk_report.get("summary") or {}).get("estimated_candidate_count") or 0),
                    "bulk_stock_matrix_planned_task_count": int((bulk_report.get("summary") or {}).get("planned_task_count") or 0),
                    "bulk_stock_matrix_planned_candidate_count": int((bulk_report.get("summary") or {}).get("planned_candidate_count") or 0),
                    "bulk_stock_matrix_tasks_per_shard": int((bulk_report.get("summary") or {}).get("tasks_per_shard") or 0),
                    "bulk_stock_matrix_shard_count": int((bulk_report.get("summary") or {}).get("shard_count") or 0),
                    "bulk_stock_matrix_selected_shard_count": int((bulk_report.get("summary") or {}).get("selected_shard_count") or 0),
                    "bulk_stock_matrix_selected_shard_ids": list((bulk_report.get("summary") or {}).get("selected_shard_ids") or []),
                    "bulk_stock_matrix_stock_coverage_ratio": (bulk_report.get("summary") or {}).get("stock_coverage_ratio"),
                    "bulk_stock_matrix_allocation_mode": (bulk_report.get("summary") or {}).get("allocation_mode"),
                    "bulk_stock_matrix_allocation_pass_counts": dict((bulk_report.get("summary") or {}).get("allocation_pass_counts") or {}),
                    "bulk_stock_matrix_planned_allocation_pass_counts": dict((bulk_report.get("summary") or {}).get("planned_allocation_pass_counts") or {}),
                    "bulk_stock_matrix_overflow_task_count": int((bulk_report.get("summary") or {}).get("overflow_task_count") or 0),
                    "max_research_tasks": int(task_budget_meta.get("max_research_tasks") or AUTONOMY_MAX_RESEARCH_TASKS),
                    "max_bulk_research_tasks": int(task_budget_meta.get("max_bulk_research_tasks") or 0),
                    "combined_research_task_budget": int(
                        task_budget_meta.get("combined_research_task_budget")
                        or task_budget_meta.get("max_research_tasks")
                        or AUTONOMY_MAX_RESEARCH_TASKS
                    ),
                    "scan_research_task_budget": int(task_budget_meta.get("scan_research_task_budget") or AUTONOMY_MAX_RESEARCH_TASKS),
                    "reserved_bulk_task_budget": int(task_budget_meta.get("reserved_bulk_task_budget") or 0),
                    "selected_scan_task_count": int(task_budget_meta.get("selected_scan_task_count") or 0),
                    "selected_bulk_task_count": int(task_budget_meta.get("selected_bulk_task_count") or 0),
                    "planned_bulk_task_count": int(task_budget_meta.get("planned_bulk_task_count") or 0),
                    "clipped_bulk_task_count": int(task_budget_meta.get("clipped_bulk_task_count") or 0),
                    "planned_feedback_control_mode_counts": dict(
                        task_budget_meta.get("planned_feedback_control_mode_counts") or {}
                    ),
                    "planned_feedback_target_pool_control_mode_counts": dict(
                        task_budget_meta.get("planned_feedback_target_pool_control_mode_counts") or {}
                    ),
                    "planned_feedback_generator_mode_control_mode_counts": dict(
                        task_budget_meta.get("planned_feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "planned_feedback_cooldown_task_count": int(
                        task_budget_meta.get("planned_feedback_cooldown_task_count") or 0
                    ),
                    "blocked_feedback_task_count": int(task_budget_meta.get("blocked_feedback_task_count") or 0),
                    "suppressed_families": list(task_budget_meta.get("suppressed_families") or []),
                    "suppressed_target_pools": list(task_budget_meta.get("suppressed_target_pools") or []),
                    "suppressed_generator_modes": list(task_budget_meta.get("suppressed_generator_modes") or []),
                    "selected_feedback_control_mode_counts": dict(
                        task_budget_meta.get("selected_feedback_control_mode_counts") or {}
                    ),
                    "selected_feedback_target_pool_control_mode_counts": dict(
                        task_budget_meta.get("selected_feedback_target_pool_control_mode_counts") or {}
                    ),
                    "selected_feedback_generator_mode_control_mode_counts": dict(
                        task_budget_meta.get("selected_feedback_generator_mode_control_mode_counts") or {}
                    ),
                    "external_llm_provider_control_mode": external_provider_control.get("control_mode"),
                    "external_llm_provider_control_reasons": list(
                        external_provider_control.get("control_reasons") or []
                    ),
                    "generator_mode_controls": dict(generator_mode_controls or {}),
                },
                "tasks": tasks,
                "opportunity_scan": scan_report,
                "bulk_stock_matrix": bulk_report,
            }
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
                evidence_rows: List[dict] = []
                task_run: dict[str, Any] = {"id": None}
                enriched_task = dict(task or {})
                failed_phase = "preparing"
                task_source = str(enriched_task.get("task_source") or "").strip().lower()
                task_sem = bulk_sem if task_source == "bulk_stock_matrix" else sem
                async with task_sem:
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
                            "external_llm_attempt_count": 0,
                            "external_llm_network_request_count": 0,
                            "external_llm_compatibility_skip_count": 0,
                            "external_llm_cooldown_skip_count": 0,
                            "external_llm_request_status_counts": {},
                            "llm_generation": llm_generation,
                            "lifecycle": lifecycle,
                            "lifecycle_summary": lifecycle_summary,
                        }
                        task_requests = list(external_provider.get("requests") or [])
                        task_level_attempt = len(task_requests)
                        task_level_request_status_counts = self._summarize_external_request_status_counts(task_requests)
                        task_level_network_request_count = self._count_external_network_requests(task_requests)
                        task_level_real_request_count = self._count_external_real_requests(task_requests)
                        task_level_compatibility_skip_count = int(task_level_request_status_counts.get("compatibility_skip", 0))
                        task_level_cooldown_skip_count = int(task_level_request_status_counts.get("cooldown_skip", 0))
                        task_level_compatibility_failure_count = sum(
                            1 for item in task_requests if self._request_is_compatibility_failure(item)
                        )
                        task_level_effective_response_count = sum(
                            1
                            for item in task_requests
                            if self._normalize_external_request_status(dict(item or {}).get("status")) == "succeeded"
                        )
                        task_level_empty_200_response_count = sum(
                            1 for item in task_requests if self._request_is_empty_200_response(item)
                        )
                        task_level_selected = int(external_provider.get("selected_count") or 0)
                        task_result["external_llm_attempt_count"] = task_level_attempt
                        task_result["external_llm_network_request_count"] = task_level_network_request_count
                        task_result["external_llm_real_request_count"] = task_level_real_request_count
                        task_result["external_llm_compatibility_skip_count"] = task_level_compatibility_skip_count
                        task_result["external_llm_cooldown_skip_count"] = task_level_cooldown_skip_count
                        task_result["external_llm_compatibility_failure_count"] = task_level_compatibility_failure_count
                        task_result["external_llm_effective_response_count"] = task_level_effective_response_count
                        task_result["external_llm_empty_200_response_count"] = task_level_empty_200_response_count
                        task_result["external_llm_compatibility_failure_ratio"] = (
                            round(task_level_compatibility_failure_count / task_level_real_request_count, 4)
                            if task_level_real_request_count
                            else 0.0
                        )
                        task_result["external_llm_effective_response_ratio"] = (
                            round(task_level_effective_response_count / task_level_real_request_count, 4)
                            if task_level_real_request_count
                            else 0.0
                        )
                        task_result["external_llm_request_status_counts"] = task_level_request_status_counts
                        task_result_summary = self._build_research_task_run_result_summary(task_result)
                        async with _agg_lock:
                            for candidate in self._extract_cycle_candidates(cycle):
                                enriched = self._enrich_candidate_targeting(candidate, enriched_task)
                                params = dict(enriched.get("params") or {})
                                params["task_attempt_count"] = task_level_attempt
                                params["task_stage_attempt_count"] = task_level_attempt
                                params["task_network_request_count"] = task_level_network_request_count
                                params["task_real_request_count"] = task_level_real_request_count
                                params["task_compatibility_skip_count"] = task_level_compatibility_skip_count
                                params["task_cooldown_skip_count"] = task_level_cooldown_skip_count
                                params["task_compatibility_failure_count"] = task_level_compatibility_failure_count
                                params["task_effective_response_count"] = task_level_effective_response_count
                                params["task_empty_200_response_count"] = task_level_empty_200_response_count
                                params["task_compatibility_failure_ratio"] = (
                                    round(task_level_compatibility_failure_count / task_level_real_request_count, 4)
                                    if task_level_real_request_count
                                    else 0.0
                                )
                                params["task_effective_response_ratio"] = (
                                    round(task_level_effective_response_count / task_level_real_request_count, 4)
                                    if task_level_real_request_count
                                    else 0.0
                                )
                                params["task_selected_count"] = task_level_selected
                                enriched["params"] = params
                                generated_candidates.append(enriched)
                            all_experiments.extend(self._extract_cycle_experiments(cycle))
                            external_status_counts[status] = external_status_counts.get(status, 0) + 1
                            total_attempt_count += task_level_attempt
                            total_network_request_count += task_level_network_request_count
                            total_real_request_count += task_level_real_request_count
                            total_compatibility_skip_count += task_level_compatibility_skip_count
                            total_cooldown_skip_count += task_level_cooldown_skip_count
                            total_compatibility_failure_count += task_level_compatibility_failure_count
                            total_effective_response_count += task_level_effective_response_count
                            total_empty_200_response_count += task_level_empty_200_response_count
                            for request_status, count in task_level_request_status_counts.items():
                                total_request_status_counts[request_status] = (
                                    total_request_status_counts.get(request_status, 0) + int(count or 0)
                                )
                            total_selected_count += task_level_selected
                            total_evidence_count += len(evidence_rows)
                            if external_provider.get("last_error_type"):
                                last_error_type = external_provider.get("last_error_type")
                                last_error = external_provider.get("last_error")
                            elapsed_seconds += float(external_provider.get("elapsed_seconds") or 0.0)
                            task_results.append(task_result_summary)
                        if task_run.get("id") is not None:
                            try:
                                await _call_optional_async(
                                    db,
                                    "update_strategy_task_run",
                                    task_run["id"],
                                    status="completed",
                                    result=task_result_summary,
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
                        task_result_summary = self._build_research_task_run_result_summary(task_result)
                        async with _agg_lock:
                            task_results.append(task_result_summary)
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
                                    result=task_result_summary,
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
            selected_feedback_summary = summarize_task_feedback_controls(tasks)
            stage = {
                "task_count": len(tasks),
                "task_source_counts": task_source_counts,
                "event_task_count": event_task_count,
                "snapshot_task_count": int(task_source_counts.get("snapshot", 0)),
                "bulk_stock_task_count": int(task_source_counts.get("bulk_stock_matrix", 0)),
                "bulk_stock_matrix_eligible_stock_count": int((bulk_report.get("summary") or {}).get("eligible_stock_count") or 0),
                "bulk_stock_matrix_loaded_stock_count": int((bulk_report.get("summary") or {}).get("loaded_stock_count") or 0),
                "bulk_stock_matrix_pages_loaded": int((bulk_report.get("summary") or {}).get("pages_loaded") or 0),
                "bulk_stock_matrix_analysis_complete": bool((bulk_report.get("summary") or {}).get("analysis_complete")),
                "bulk_stock_matrix_analysis_stock_coverage_ratio": (bulk_report.get("summary") or {}).get("analysis_stock_coverage_ratio"),
                "bulk_stock_matrix_universe_limit": int((bulk_report.get("summary") or {}).get("universe_limit") or STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT),
                "bulk_stock_matrix_batch_count": int((bulk_report.get("summary") or {}).get("batch_count") or 0),
                "bulk_stock_matrix_selected_batch_count": int((bulk_report.get("summary") or {}).get("selected_batch_count") or 0),
                "bulk_stock_matrix_requested_universe_offset": int((bulk_report.get("summary") or {}).get("requested_universe_offset") or 0),
                "bulk_stock_matrix_effective_universe_offset": int((bulk_report.get("summary") or {}).get("effective_universe_offset") or 0),
                "bulk_stock_matrix_universe_offset_fallback": bool((bulk_report.get("summary") or {}).get("universe_offset_fallback")),
                "bulk_stock_matrix_next_universe_offset": int((bulk_report.get("summary") or {}).get("next_universe_offset") or 0),
                "bulk_stock_matrix_cursor_wrapped": bool((bulk_report.get("summary") or {}).get("cursor_wrapped")),
                "bulk_stock_matrix_cursor_mode": (bulk_report.get("summary") or {}).get("cursor_mode") or "task_offset",
                "bulk_stock_matrix_requested_task_offset": int((bulk_report.get("summary") or {}).get("requested_task_offset") or 0),
                "bulk_stock_matrix_effective_task_offset": int((bulk_report.get("summary") or {}).get("effective_task_offset") or 0),
                "bulk_stock_matrix_task_offset_fallback": bool((bulk_report.get("summary") or {}).get("task_offset_fallback")),
                "bulk_stock_matrix_next_task_offset": int((bulk_report.get("summary") or {}).get("next_task_offset") or 0),
                "bulk_stock_matrix_task_cursor_wrapped": bool((bulk_report.get("summary") or {}).get("task_cursor_wrapped")),
                "bulk_stock_matrix_cursor_source": (bulk_report.get("summary") or {}).get("cursor_source") or bulk_cursor.get("source"),
                "bulk_stock_matrix_cursor_resume_from_run_id": (bulk_report.get("summary") or {}).get("cursor_resume_from_run_id") or bulk_cursor.get("resume_from_run_id"),
                "bulk_stock_matrix_effective_task_budget": int((bulk_report.get("summary") or {}).get("effective_task_budget") or 0),
                "bulk_stock_matrix_estimated_candidate_count": int((bulk_report.get("summary") or {}).get("estimated_candidate_count") or 0),
                "bulk_stock_matrix_planned_task_count": int((bulk_report.get("summary") or {}).get("planned_task_count") or 0),
                "bulk_stock_matrix_planned_candidate_count": int((bulk_report.get("summary") or {}).get("planned_candidate_count") or 0),
                "bulk_stock_matrix_shard_count": int((bulk_report.get("summary") or {}).get("shard_count") or 0),
                "bulk_stock_matrix_selected_shard_count": int((bulk_report.get("summary") or {}).get("selected_shard_count") or 0),
                "bulk_stock_matrix_selected_shard_ids": list((bulk_report.get("summary") or {}).get("selected_shard_ids") or []),
                "event_evidence_count": total_evidence_count,
                "completed_task_count": completed_task_count,
                "failed_task_count": failed_task_count,
                "task_scan": combined_scan_report,
                "task_results": task_results,
                "generated_count": len(generated_candidates),
                "experiment_count": len(all_experiments),
                "task_run_ids": [item.get("task_run_id") for item in task_results if item.get("task_run_id") is not None],
                "external_llm_status": overall_status,
                "external_llm_status_counts": external_status_counts,
                "external_llm_attempt_count": total_attempt_count,
                "external_llm_stage_attempt_count": total_attempt_count,
                "external_llm_network_request_count": total_network_request_count,
                "external_llm_real_request_count": total_real_request_count,
                "external_llm_compatibility_skip_count": total_compatibility_skip_count,
                "external_llm_cooldown_skip_count": total_cooldown_skip_count,
                "external_llm_compatibility_failure_count": total_compatibility_failure_count,
                "external_llm_compatibility_failure_ratio": round(
                    total_compatibility_failure_count / total_real_request_count,
                    4,
                )
                if total_real_request_count
                else 0.0,
                "external_llm_effective_response_count": total_effective_response_count,
                "external_llm_effective_response_ratio": round(
                    total_effective_response_count / total_real_request_count,
                    4,
                )
                if total_real_request_count
                else 0.0,
                "external_llm_empty_200_response_count": total_empty_200_response_count,
                "external_llm_request_status_counts": total_request_status_counts,
                "external_llm_selected_count": total_selected_count,
                "external_llm_last_error_type": last_error_type,
                "external_llm_last_error": last_error,
                "external_llm_elapsed_seconds": round(elapsed_seconds, 4),
                "external_llm_provider_health_status": external_provider_health.get("health_status"),
                "external_llm_provider_scheduler_should_disable": bool(
                    external_provider_health.get("scheduler_should_disable")
                ),
                "external_llm_provider_scheduler_skip_reason": external_provider_health.get("scheduler_skip_reason"),
                "external_llm_provider_cooldown_active": bool(
                    external_provider_health.get("compatibility_cooldown_active")
                ),
                "research_task_concurrency": effective_research_concurrency,
                "configured_research_task_concurrency": RESEARCH_TASK_CONCURRENCY,
                "bulk_task_concurrency": effective_bulk_research_concurrency if has_bulk_tasks else 0,
                "configured_bulk_task_concurrency": int(STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY) if has_bulk_tasks else 0,
                "bulk_tasks_use_external_llm": bool(self._bulk_tasks_use_external_llm(autonomy_gateway)) if has_bulk_tasks else False,
                "research_task_timeout_sec": round(self._resolve_research_task_timeout_sec(), 4),
                "max_research_tasks": int(task_budget_meta.get("max_research_tasks") or AUTONOMY_MAX_RESEARCH_TASKS),
                "max_bulk_research_tasks": int(task_budget_meta.get("max_bulk_research_tasks") or 0),
                "combined_research_task_budget": int(
                    task_budget_meta.get("combined_research_task_budget")
                    or task_budget_meta.get("max_research_tasks")
                    or AUTONOMY_MAX_RESEARCH_TASKS
                ),
                "scan_research_task_budget": int(task_budget_meta.get("scan_research_task_budget") or AUTONOMY_MAX_RESEARCH_TASKS),
                "reserved_bulk_task_budget": int(task_budget_meta.get("reserved_bulk_task_budget") or 0),
                "selected_scan_task_count": int(task_budget_meta.get("selected_scan_task_count") or 0),
                "selected_bulk_task_count": int(task_budget_meta.get("selected_bulk_task_count") or 0),
                "planned_bulk_task_count": int(task_budget_meta.get("planned_bulk_task_count") or 0),
                "clipped_bulk_task_count": int(task_budget_meta.get("clipped_bulk_task_count") or 0),
                "planned_feedback_control_mode_counts": dict(
                    task_budget_meta.get("planned_feedback_control_mode_counts") or {}
                ),
                "planned_feedback_target_pool_control_mode_counts": dict(
                    task_budget_meta.get("planned_feedback_target_pool_control_mode_counts") or {}
                ),
                "planned_feedback_generator_mode_control_mode_counts": dict(
                    task_budget_meta.get("planned_feedback_generator_mode_control_mode_counts") or {}
                ),
                "planned_feedback_cooldown_task_count": int(
                    task_budget_meta.get("planned_feedback_cooldown_task_count") or 0
                ),
                "blocked_feedback_task_count": int(task_budget_meta.get("blocked_feedback_task_count") or 0),
                "suppressed_families": list(task_budget_meta.get("suppressed_families") or []),
                "suppressed_target_pools": list(task_budget_meta.get("suppressed_target_pools") or []),
                "suppressed_generator_modes": list(task_budget_meta.get("suppressed_generator_modes") or []),
                "selected_feedback_control_mode_counts": dict(
                    selected_feedback_summary.get("feedback_control_mode_counts") or {}
                ),
                "selected_feedback_target_pool_control_mode_counts": dict(
                    selected_feedback_summary.get("feedback_target_pool_control_mode_counts") or {}
                ),
                "selected_feedback_generator_mode_control_mode_counts": dict(
                    selected_feedback_summary.get("feedback_generator_mode_control_mode_counts") or {}
                ),
                "external_llm_provider_control_mode": external_provider_control.get("control_mode"),
                "external_llm_provider_control_reasons": list(
                    external_provider_control.get("control_reasons") or []
                ),
                "external_llm_provider_control_metrics": {
                    key: external_provider_control.get(key)
                    for key in (
                        "stage_attempt_count",
                        "real_request_count",
                        "compatibility_skip_count",
                        "compatibility_skip_ratio",
                        "compatibility_failure_count",
                        "compatibility_failure_ratio",
                        "effective_response_count",
                        "effective_response_ratio",
                        "empty_200_response_count",
                        "empty_200_response_ratio",
                    )
                },
                "generator_mode_controls": dict(generator_mode_controls or {}),
                "shared_generation_context_preloaded": shared_generation_context_preloaded,
                "persistence_failures": persistence_failures,
                "persistence_failure_count": len(persistence_failures),
                **lifecycle_metrics,
            }
            task_artifact = build_task_artifact(stage)
            candidate_artifact = build_candidate_artifact(generated_candidates)
            evidence_artifact = build_research_evidence_artifact(
                stage,
                experiments=all_experiments,
            )
            stage.update(
                {
                    "scan_task_artifact": scan_task_artifact,
                    "bulk_task_artifact": bulk_task_artifact,
                    "task_artifact": task_artifact,
                    "candidate_artifact": candidate_artifact,
                    "evidence_artifact": evidence_artifact,
                    "scan_task_artifact_contract_version": scan_task_artifact.get("contract_version"),
                    "scan_task_artifact_available": bool(scan_task_artifact.get("available")),
                    "bulk_task_artifact_contract_version": bulk_task_artifact.get("contract_version"),
                    "bulk_task_artifact_available": bool(bulk_task_artifact.get("available")),
                    "task_artifact_contract_version": task_artifact.get("contract_version"),
                    "task_artifact_available": bool(task_artifact.get("available")),
                    "candidate_artifact_contract_version": candidate_artifact.get("contract_version"),
                    "candidate_artifact_available": bool(candidate_artifact.get("available")),
                    "evidence_artifact_contract_version": evidence_artifact.get("contract_version"),
                    "evidence_artifact_available": bool(evidence_artifact.get("available")),
                }
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
