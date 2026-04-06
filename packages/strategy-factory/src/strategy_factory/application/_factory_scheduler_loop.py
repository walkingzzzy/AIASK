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
from .utils import _extract_event_context as _local_extract_event_context
from .stock_strategy_matrix import StockStrategyMatrixPlanner
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
            limit = max(1, min(int(task.get("generation_limit") or AUTONOMY_CANDIDATES_PER_TASK), AUTONOMY_TASK_HARD_CAP))
            source = f"strategy_factory:{task.get('opportunity_type') or 'general'}"
            gateway_db = self._adapt_gateway_repository(db)
            timeout_sec = self._resolve_research_task_timeout_sec()
            try:
                return await asyncio.wait_for(
                    autonomy_gateway.generate_factory_candidates(
                        gateway_db,
                        snapshot,
                        limit=limit,
                        research_task=task,
                        source=source,
                    ),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError as exc:
                task_id = str(task.get("task_id") or task.get("task_key") or source).strip() or source
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

            normalized_scan_tasks = scanner._deduplicate_tasks(list(scan_tasks or []))
            normalized_scan_tasks.sort(key=scanner._task_sort_key, reverse=True)
            normalized_bulk_tasks = scanner._deduplicate_tasks(list(bulk_tasks or []))
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
            }

        async def _run_autonomy_batches(self, db, snapshot: dict) -> dict:
            factory_pkg = get_strategy_factory_package()
            scanner = factory_pkg.MarketOpportunityScanner()
            scan_report = await scanner.scan(db, snapshot)
            scan_tasks = list(scan_report.get("tasks") or [])
            tasks = list(scan_tasks)
            scan_summary = dict(scan_report.get("summary") or {})
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
            bulk_tasks = list(bulk_report.get("tasks") or [])
            if bulk_tasks:
                tasks, task_budget_meta = self._merge_autonomy_tasks_with_budget(
                    scanner,
                    scan_tasks,
                    bulk_tasks,
                )
            else:
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
                nonlocal total_attempt_count, total_selected_count, total_evidence_count
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
                "external_llm_selected_count": total_selected_count,
                "external_llm_last_error_type": last_error_type,
                "external_llm_last_error": last_error,
                "external_llm_elapsed_seconds": round(elapsed_seconds, 4),
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
            previous_result = self.last_result
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
            self._attach_runtime_governance(results, previous_result=previous_result)
            self.last_run = self._now()
            self.last_result = results
            await self._persist_run_result(
                db,
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
