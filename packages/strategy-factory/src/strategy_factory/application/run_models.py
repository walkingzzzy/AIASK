"""Run/stage status helpers for strategy factory execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class StageStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"


class FactoryRunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    FAILED = "failed"


_STAGE_STATUS_ALIASES = {
    "completed": StageStatus.COMPLETED,
    "complete": StageStatus.COMPLETED,
    "success": StageStatus.COMPLETED,
    "succeeded": StageStatus.COMPLETED,
    "done": StageStatus.COMPLETED,
    "partial": StageStatus.PARTIAL,
    "degraded": StageStatus.PARTIAL,
    "warning": StageStatus.PARTIAL,
    "warnings": StageStatus.PARTIAL,
    "skipped": StageStatus.SKIPPED,
    "disabled": StageStatus.SKIPPED,
    "noop": StageStatus.SKIPPED,
    "failed": StageStatus.FAILED,
    "error": StageStatus.FAILED,
}

_RUN_STATUS_ALIASES = {
    "success": FactoryRunStatus.SUCCESS,
    "partial": FactoryRunStatus.PARTIAL,
    "skipped": FactoryRunStatus.SKIPPED,
    "failed": FactoryRunStatus.FAILED,
}
STAGE_RESULT_CONTRACT_VERSION = 1


def normalize_stage_status(value: Any, default: StageStatus = StageStatus.COMPLETED) -> StageStatus:
    if isinstance(value, StageStatus):
        return value
    token = str(value or "").strip().lower()
    return _STAGE_STATUS_ALIASES.get(token, default)


def normalize_run_status(value: Any, default: FactoryRunStatus = FactoryRunStatus.SUCCESS) -> FactoryRunStatus:
    if isinstance(value, FactoryRunStatus):
        return value
    token = str(value or "").strip().lower()
    return _RUN_STATUS_ALIASES.get(token, default)


@dataclass(slots=True)
class StageResult:
    stage: str
    trace_id: str
    status: StageStatus
    ok: bool
    hard_failure: bool = False
    degraded: bool = False
    skip_reason: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.payload)
        raw_status = data.pop("status", None)
        data.pop("ok", None)
        data.pop("hard_failure", None)
        data.pop("degraded", None)
        data.pop("skip_reason", None)
        warnings = list(data.get("warnings") or [])
        blockers = list(data.get("blockers") or [])
        persistence_failures = list(data.get("persistence_failures") or [])
        result = {
            "stage": self.stage,
            "trace_id": self.trace_id,
            "stage_contract_version": STAGE_RESULT_CONTRACT_VERSION,
            "status": self.status.value,
            "ok": bool(self.ok),
            "hard_failure": bool(self.hard_failure),
            "degraded": bool(self.degraded),
            "warning_count": int(data.get("warning_count") or len(warnings)),
            "blocker_count": int(data.get("blocker_count") or len(blockers)),
            "persistence_failure_count": int(
                data.get("persistence_failure_count") or len(persistence_failures)
            ),
            **data,
        }
        if self.skip_reason:
            result["skip_reason"] = self.skip_reason
        if raw_status is not None and normalize_stage_status(raw_status) != self.status:
            result["raw_status"] = raw_status
        return result


def build_stage_result(
    stage: str,
    trace_id: str,
    payload: Optional[Mapping[str, Any]] = None,
    *,
    status: StageStatus | str,
    ok: Optional[bool] = None,
    hard_failure: bool = False,
    degraded: Optional[bool] = None,
    skip_reason: Optional[str] = None,
) -> dict[str, Any]:
    effective_status = normalize_stage_status(status)
    effective_payload = dict(payload or {})
    effective_skip_reason = str(
        skip_reason or effective_payload.get("skip_reason") or ""
    ).strip() or None
    effective_degraded = bool(
        effective_payload.get("degraded")
        if degraded is None
        else degraded
    ) or effective_status == StageStatus.PARTIAL
    effective_ok = (
        effective_status != StageStatus.FAILED
        if ok is None
        else bool(ok)
    )
    return StageResult(
        stage=stage,
        trace_id=trace_id,
        status=effective_status,
        ok=effective_ok,
        hard_failure=bool(hard_failure),
        degraded=effective_degraded,
        skip_reason=effective_skip_reason,
        payload=effective_payload,
    ).to_dict()


def summarize_stage_results(stages: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    counts = {item.value: 0 for item in StageStatus}
    failed_stages: list[str] = []
    partial_stages: list[str] = []
    skipped_stages: list[str] = []
    hard_failure_count = 0
    degraded_stage_count = 0
    skip_reasons: list[str] = []

    for stage_name, payload in dict(stages or {}).items():
        stage_payload = dict(payload or {})
        status = normalize_stage_status(stage_payload.get("status"))
        counts[status.value] = counts.get(status.value, 0) + 1
        if status == StageStatus.FAILED:
            failed_stages.append(stage_name)
        elif status == StageStatus.PARTIAL:
            partial_stages.append(stage_name)
        elif status == StageStatus.SKIPPED:
            skipped_stages.append(stage_name)
        if bool(stage_payload.get("hard_failure")):
            hard_failure_count += 1
        if bool(stage_payload.get("degraded")) or status == StageStatus.PARTIAL:
            degraded_stage_count += 1
        reason = str(stage_payload.get("skip_reason") or "").strip()
        if reason:
            skip_reasons.append(reason)

    return {
        "stage_status_counts": counts,
        "failed_stage_count": len(failed_stages),
        "partial_stage_count": len(partial_stages),
        "skipped_stage_count": len(skipped_stages),
        "hard_failure_count": hard_failure_count,
        "degraded_stage_count": degraded_stage_count,
        "failed_stages": failed_stages,
        "partial_stages": partial_stages,
        "skipped_stages": skipped_stages,
        "skip_reasons": skip_reasons,
    }


def resolve_run_status(
    current_status: FactoryRunStatus | str,
    stages: Mapping[str, Mapping[str, Any]],
    *,
    persistence_failure_count: int = 0,
) -> FactoryRunStatus:
    normalized_current = normalize_run_status(current_status)
    if normalized_current in {FactoryRunStatus.SKIPPED, FactoryRunStatus.FAILED}:
        return normalized_current

    stage_summary = summarize_stage_results(stages)
    if (
        stage_summary["failed_stage_count"] > 0
        or stage_summary["partial_stage_count"] > 0
        or int(persistence_failure_count or 0) > 0
    ):
        return FactoryRunStatus.PARTIAL
    return FactoryRunStatus.SUCCESS


__all__ = [
    "FactoryRunStatus",
    "StageResult",
    "STAGE_RESULT_CONTRACT_VERSION",
    "StageStatus",
    "build_stage_result",
    "normalize_run_status",
    "normalize_stage_status",
    "resolve_run_status",
    "summarize_stage_results",
]
