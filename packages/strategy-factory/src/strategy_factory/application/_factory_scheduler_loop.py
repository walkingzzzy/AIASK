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
from .factory_execution import (
    FACTORY_ENGINE_VERSION,
    FactoryExecutionMode,
    build_artifact_refs,
    build_run_artifacts,
    build_shadow_parity_result,
    resolve_factory_engine_version,
    resolve_factory_execution_mode,
)
from .factory_market_views import build_portfolio_candidate_from_topn
from .runtime import (
    _call_optional_async as _runtime_call_optional_async,
    get_strategy_factory_package as _runtime_get_strategy_factory_package,
)
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

def _extract_event_context(*args, **kwargs):
    return _local_extract_event_context(*args, **kwargs)


def get_strategy_factory_package():
    return _runtime_get_strategy_factory_package()


async def _call_optional_async(target: Any, method_name: str, *args, default=None, **kwargs):
    return await _runtime_call_optional_async(target, method_name, *args, default=default, **kwargs)

from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    '_factory_scheduler_loop_parts',
    'class _StrategyFactorySchedulerLoopMixin:\n        @staticmethod\n',
    ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py'],
    future_annotations=True,
)
