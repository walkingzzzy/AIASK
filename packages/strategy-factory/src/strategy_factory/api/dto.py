"""Stable Data Transfer Objects for the strategy factory product interface.

These DTOs decouple the BFF / MCP tool layer from the raw run result dicts,
providing versioned, stable contracts for:

- FactoryStatusDTO        → factory_status tool
- FactoryRunSummaryDTO    → factory_runs list item
- FactoryRunDetailDTO     → factory_run_detail tool
- StageResultDTO          → single stage within a run detail

P5 implementation: product layer reads from DTOs, not from raw run dicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..application.run_models import FactoryRunStatus, StageStatus, normalize_run_status, normalize_stage_status


# ---------------------------------------------------------------------------
# Stage DTO
# ---------------------------------------------------------------------------

@dataclass
class StageResultDTO:
    """DTO for a single stage within a factory run."""

    stage: str
    status: str
    ok: bool
    hard_failure: bool
    degraded: bool
    skip_reason: Optional[str]
    warning_count: int
    blocker_count: int
    persistence_failure_count: int

    @classmethod
    def from_dict(cls, stage: str, data: dict[str, Any]) -> "StageResultDTO":
        d = dict(data or {})
        status_enum = normalize_stage_status(d.get("status"))
        return cls(
            stage=stage,
            status=status_enum.value,
            ok=bool(d.get("ok", True)),
            hard_failure=bool(d.get("hard_failure")),
            degraded=bool(d.get("degraded")),
            skip_reason=d.get("skip_reason"),
            warning_count=int(d.get("warning_count") or 0),
            blocker_count=int(d.get("blocker_count") or 0),
            persistence_failure_count=int(d.get("persistence_failure_count") or 0),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "stage": self.stage,
            "status": self.status,
            "ok": self.ok,
            "hard_failure": self.hard_failure,
            "degraded": self.degraded,
            "warning_count": self.warning_count,
            "blocker_count": self.blocker_count,
            "persistence_failure_count": self.persistence_failure_count,
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        return result


# ---------------------------------------------------------------------------
# Factory run summary DTO (list item)
# ---------------------------------------------------------------------------

@dataclass
class FactoryRunSummaryDTO:
    """DTO for a factory run summary as shown in the factory_runs list."""

    run_id: str
    trace_id: str
    status: str
    started_at: str
    completed_at: Optional[str]
    elapsed_seconds: float
    candidates_spawned: int
    submitted: int
    eliminated: int
    hard_failure_count: int
    degraded_stage_count: int
    persistence_failure_count: int
    skip_reason: Optional[str]
    error: Optional[str]
    readiness_score: Optional[float]
    readiness_can_proceed: Optional[bool]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryRunSummaryDTO":
        d = dict(data or {})
        summary = dict(d.get("summary") or {})
        audit = dict(d.get("_run_audit") or {})
        status = normalize_run_status(d.get("status"), default=FactoryRunStatus.FAILED).value
        return cls(
            run_id=str(d.get("run_id") or ""),
            trace_id=str(d.get("trace_id") or summary.get("trace_id") or ""),
            status=status,
            started_at=str(d.get("started_at") or ""),
            completed_at=d.get("completed_at"),
            elapsed_seconds=float(d.get("elapsed_seconds") or 0.0),
            candidates_spawned=int(summary.get("candidates_spawned") or 0),
            submitted=int(summary.get("submitted") or 0),
            eliminated=int(summary.get("eliminated") or 0),
            hard_failure_count=int(audit.get("hard_failure_count") or 0),
            degraded_stage_count=int(audit.get("degraded_stage_count") or 0),
            persistence_failure_count=int(audit.get("persistence_failure_count") or 0),
            skip_reason=summary.get("skip_reason"),
            error=d.get("error"),
            readiness_score=summary.get("factory_readiness_score"),
            readiness_can_proceed=summary.get("factory_readiness_can_proceed"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "candidates_spawned": self.candidates_spawned,
            "submitted": self.submitted,
            "eliminated": self.eliminated,
            "hard_failure_count": self.hard_failure_count,
            "degraded_stage_count": self.degraded_stage_count,
            "persistence_failure_count": self.persistence_failure_count,
            "readiness_score": self.readiness_score,
            "readiness_can_proceed": self.readiness_can_proceed,
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        if self.error:
            result["error"] = self.error
        return result


# ---------------------------------------------------------------------------
# Factory run detail DTO
# ---------------------------------------------------------------------------

@dataclass
class FactoryRunDetailDTO:
    """DTO for a complete factory run detail, including per-stage breakdown."""

    summary: FactoryRunSummaryDTO
    stages: list[StageResultDTO] = field(default_factory=list)
    snapshot_summary: dict[str, Any] = field(default_factory=dict)
    quality_gate: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryRunDetailDTO":
        d = dict(data or {})
        summary_dto = FactoryRunSummaryDTO.from_dict(d)
        raw_stages = dict(d.get("stages") or {})
        stages = [
            StageResultDTO.from_dict(name, payload)
            for name, payload in raw_stages.items()
        ]
        return cls(
            summary=summary_dto,
            stages=stages,
            snapshot_summary=dict(d.get("snapshot_summary") or {}),
            quality_gate=dict(d.get("quality_gate") or d.get("gate_report") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary.to_dict(),
            "stages": {s.stage: s.to_dict() for s in self.stages},
            "snapshot_summary": self.snapshot_summary,
            "quality_gate": self.quality_gate,
        }

    def get_stage(self, name: str) -> Optional[StageResultDTO]:
        for s in self.stages:
            if s.stage == name:
                return s
        return None

    def failed_stages(self) -> list[str]:
        return [s.stage for s in self.stages if s.status == StageStatus.FAILED.value]

    def partial_stages(self) -> list[str]:
        return [s.stage for s in self.stages if s.status == StageStatus.PARTIAL.value]


# ---------------------------------------------------------------------------
# Factory status DTO (scheduler status)
# ---------------------------------------------------------------------------

@dataclass
class FactoryStatusDTO:
    """DTO for the scheduler-level factory status (factory_status tool)."""

    running: bool
    schedule_mode: str
    runtime_enabled: bool
    event_runtime_mode: str
    last_run: Optional[str]
    last_status: Optional[str]
    daily_run_count: int
    max_daily_runs: int
    cycle_count: int
    factor_auto_refresh_enabled: bool
    readiness_hard_block_enabled: bool
    readiness_min_score: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FactoryStatusDTO":
        d = dict(data or {})
        last_result = dict(d.get("last_result") or {})
        return cls(
            running=bool(d.get("running")),
            schedule_mode=str(d.get("schedule_mode") or "continuous"),
            runtime_enabled=bool(d.get("runtime_enabled")),
            event_runtime_mode=str(d.get("event_runtime_mode") or ""),
            last_run=str(d["last_run"]) if d.get("last_run") else None,
            last_status=str(last_result.get("status") or "") or None,
            daily_run_count=int(d.get("daily_run_count") or 0),
            max_daily_runs=int(d.get("max_daily_runs") or 0),
            cycle_count=int(d.get("cycle_count") or 0),
            factor_auto_refresh_enabled=bool(d.get("factor_auto_refresh_enabled")),
            readiness_hard_block_enabled=bool(d.get("readiness_hard_block_enabled")),
            readiness_min_score=float(d.get("readiness_min_score") or 0.0),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "schedule_mode": self.schedule_mode,
            "runtime_enabled": self.runtime_enabled,
            "event_runtime_mode": self.event_runtime_mode,
            "last_run": self.last_run,
            "last_status": self.last_status,
            "daily_run_count": self.daily_run_count,
            "max_daily_runs": self.max_daily_runs,
            "cycle_count": self.cycle_count,
            "factor_auto_refresh_enabled": self.factor_auto_refresh_enabled,
            "readiness_hard_block_enabled": self.readiness_hard_block_enabled,
            "readiness_min_score": self.readiness_min_score,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_run_result_to_detail(data: dict[str, Any]) -> FactoryRunDetailDTO:
    """Convert a raw cycle-runner result dict to a stable detail DTO."""
    return FactoryRunDetailDTO.from_dict(data)


def normalize_run_result_to_summary(data: dict[str, Any]) -> FactoryRunSummaryDTO:
    """Convert a raw cycle-runner result dict to a stable summary DTO."""
    return FactoryRunSummaryDTO.from_dict(data)


__all__ = [
    "FactoryRunDetailDTO",
    "FactoryRunSummaryDTO",
    "FactoryStatusDTO",
    "StageResultDTO",
    "normalize_run_result_to_detail",
    "normalize_run_result_to_summary",
]
