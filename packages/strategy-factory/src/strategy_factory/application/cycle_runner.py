"""Single-cycle strategy factory runner."""


from __future__ import annotations

import logging
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ._cycle_success_summary import build_success_run_summary
from .factory_market_views import build_research_window_status
from .factory_execution import (
    DEFAULT_FACTORY_EXECUTION_MODE,
    FACTORY_ENGINE_VERSION,
    build_artifact_refs,
    build_run_artifacts,
    build_run_header,
)
from .compact_contracts import compact_backtest_report, compact_quality_gate_report
from .governance_plane_contract import build_governance_plane_artifact
from .research.runner import ResearchPlaneRunner
from .services.candidate_pipeline import CandidatePipeline
from .run_models import FactoryRunStatus, StageStatus, summarize_stage_results
from .services.readiness_service import (
    READINESS_CONTRACT_VERSION,
    ReadinessService,
    build_readiness_authority,
)
from ..domain.constants import (
    is_factory_readiness_hard_block_enabled,
    is_factory_runtime_enabled,
    resolve_event_runtime_mode,
)

logger = logging.getLogger(__name__)

FactoryRunResult = dict[str, Any]


@dataclass(slots=True)
class FactoryRunContext:
    db: Any
    factory_pkg: Any
    runtime_adapters: Any
    start: datetime
    trace_id: str
    run_id: str
    execution_mode: str = DEFAULT_FACTORY_EXECUTION_MODE.value
    engine_version: str = FACTORY_ENGINE_VERSION
    parity_role: str = "primary"
    read_only: bool = False
    target_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FactoryCycleOutcome:
    result: FactoryRunResult
    persistence_failures: list[dict[str, Any]] = field(default_factory=list)


def _build_warmup_error_topn(
    warmup_result: dict[str, Any] | None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Extract a structured top-N list of warmup task failures.

    Reads ``warmup_result["schedules"]`` (produced by
    ``run_runtime_data_warmup``) and returns at most ``limit`` entries,
    each with ``task_type / schedule_id / task_id / error_message /
    error_kind``. The shape is what ``factory_runs.summary`` and the
    console warning use; keep it stable.
    """
    if not isinstance(warmup_result, dict):
        return []
    schedules = warmup_result.get("schedules") or []
    if not isinstance(schedules, list):
        return []

    out: list[dict[str, Any]] = []
    for entry in schedules:
        if not isinstance(entry, dict):
            continue
        task = entry.get("task") if isinstance(entry.get("task"), dict) else {}
        status = str(task.get("status") or "").strip().lower()
        if status in {"completed", "success"}:
            continue

        msg = task.get("error_message")
        if not msg and isinstance(task.get("results"), dict):
            errs = task["results"].get("errors") or []
            if errs:
                msg = "; ".join(str(e) for e in errs[:3])

        # Cheap classification so dashboards can group later. Pure
        # string match — keep it conservative; the underlying message
        # itself remains the source of truth.
        msg_str = str(msg or "")
        if "脚本不存在" in msg_str or "script_missing" in msg_str:
            error_kind: str | None = "script_missing"
        elif "timeout" in msg_str.lower():
            error_kind = "timeout"
        elif msg_str:
            error_kind = "exception"
        else:
            error_kind = None

        out.append({
            "task_type": entry.get("task_type") or task.get("task_type"),
            "schedule_id": entry.get("schedule_id"),
            "task_id": task.get("task_id"),
            "error_message": (msg_str or None) and msg_str[:500],
            "error_kind": error_kind,
        })
        if len(out) >= max(1, int(limit or 5)):
            break
    return out


from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    'cycle_runner_parts',
    'class FactoryCycleRunner:\n',
    ['normalizers.py'],
    future_annotations=True,
)


from .cycle_pipeline import FactoryCyclePipeline, FactoryStageResult


_legacy_factory_cycle_runner_run = FactoryCycleRunner.run


async def _pipeline_factory_cycle_runner_run(self) -> FactoryCycleOutcome:
    return await FactoryCyclePipeline(
        self,
        legacy_run=getattr(self, "_run_legacy_cycle", _legacy_factory_cycle_runner_run),
    ).run()


FactoryCycleRunner._run_legacy_cycle = _legacy_factory_cycle_runner_run
FactoryCycleRunner.run = _pipeline_factory_cycle_runner_run


__all__ = [
    "FactoryCycleOutcome",
    "FactoryCyclePipeline",
    "FactoryCycleRunner",
    "FactoryRunContext",
    "FactoryRunResult",
    "FactoryStageResult",
]
