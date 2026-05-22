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
    FACTORY_ENGINE_VERSION,
    build_artifact_refs,
    build_run_artifacts,
    build_run_header,
)
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
    execution_mode: str = "legacy_primary"
    engine_version: str = FACTORY_ENGINE_VERSION
    parity_role: str = "primary"
    read_only: bool = False
    target_codes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FactoryCycleOutcome:
    result: FactoryRunResult
    persistence_failures: list[dict[str, Any]] = field(default_factory=list)

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
