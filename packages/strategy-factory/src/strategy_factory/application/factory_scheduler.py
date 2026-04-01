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

from ._factory_scheduler_analysis import _StrategyFactorySchedulerAnalysisMixin
from ._factory_scheduler_runtime import _StrategyFactorySchedulerRuntimeMixin
from ._factory_scheduler_loop import _StrategyFactorySchedulerLoopMixin


class StrategyFactoryScheduler(_StrategyFactorySchedulerAnalysisMixin, _StrategyFactorySchedulerRuntimeMixin, _StrategyFactorySchedulerLoopMixin):
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
