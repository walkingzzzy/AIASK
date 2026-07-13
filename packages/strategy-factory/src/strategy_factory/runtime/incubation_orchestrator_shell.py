"""P2 S5a skeleton: incubation phase orchestration policy shell.

Ownership:
- Phase names / timeouts / required flags: ``incubation_phases``
- I/O implementations remain host-side (akshare-mcp IncubationFactoryRunner)
  until PR-S5b ports phases one-by-one.

This module intentionally does **not** import akshare_mcp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from .incubation_phases import (
    INCUBATION_ONCE_PHASES,
    IncubationPhaseSpec,
    get_phase_timeout,
    incubation_phase_names,
    required_phase_names,
)


PhaseHandler = Callable[[], Awaitable[Mapping[str, Any] | dict[str, Any] | None]]


@dataclass
class PhaseRunResult:
    name: str
    required: bool
    timeout_sec: float
    success: bool
    skipped: bool = False
    dry_run: bool = False
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CyclePlan:
    phases: tuple[IncubationPhaseSpec, ...]
    dry_run: bool = False

    def names(self) -> list[str]:
        return [p.name for p in self.phases]


def build_once_cycle_plan(*, dry_run: bool = False) -> CyclePlan:
    return CyclePlan(phases=INCUBATION_ONCE_PHASES, dry_run=bool(dry_run))


async def run_phase_plan(
    plan: CyclePlan,
    handlers: Mapping[str, PhaseHandler],
    *,
    stop_on_required_failure: bool = True,
) -> dict[str, Any]:
    """Execute handlers for each planned phase without owning host I/O.

    Missing handlers for optional phases are skipped; missing handlers for
    required phases are failures.
    """
    results: list[PhaseRunResult] = []
    for phase in plan.phases:
        handler = handlers.get(phase.name)
        timeout = float(get_phase_timeout(phase.name, phase.timeout_sec))
        if handler is None:
            # dry-run is a plan walk: missing handlers are still "planned".
            if plan.dry_run:
                results.append(
                    PhaseRunResult(
                        name=phase.name,
                        required=phase.required,
                        timeout_sec=timeout,
                        success=True,
                        skipped=True,
                        dry_run=True,
                        payload={"planned": True, "handler_missing": True},
                    )
                )
                continue
            result = PhaseRunResult(
                name=phase.name,
                required=phase.required,
                timeout_sec=timeout,
                success=not phase.required,
                skipped=True,
                dry_run=False,
                error=None if not phase.required else "phase_handler_missing",
            )
            results.append(result)
            if phase.required and stop_on_required_failure:
                break
            continue
        if plan.dry_run:
            results.append(
                PhaseRunResult(
                    name=phase.name,
                    required=phase.required,
                    timeout_sec=timeout,
                    success=True,
                    skipped=False,
                    dry_run=True,
                    payload={"planned": True, "handler": getattr(handler, "__name__", "handler")},
                )
            )
            continue
        try:
            raw = await handler()
            payload = dict(raw or {}) if isinstance(raw, Mapping) else {"result": raw}
            success = bool(payload.get("success", True))
            results.append(
                PhaseRunResult(
                    name=phase.name,
                    required=phase.required,
                    timeout_sec=timeout,
                    success=success,
                    dry_run=False,
                    error=None if success else str(payload.get("error") or "phase_failed"),
                    payload=payload,
                )
            )
            if phase.required and not success and stop_on_required_failure:
                break
        except Exception as exc:  # noqa: BLE001 - host handlers may raise freely
            results.append(
                PhaseRunResult(
                    name=phase.name,
                    required=phase.required,
                    timeout_sec=timeout,
                    success=False,
                    dry_run=False,
                    error=f"{type(exc).__name__}:{exc}",
                )
            )
            if phase.required and stop_on_required_failure:
                break

    required_failed = [
        r.name for r in results if r.required and not r.success and not (r.skipped and not r.required)
    ]
    required_failed = [r.name for r in results if r.required and not r.success]
    return {
        "success": not required_failed,
        "dry_run": plan.dry_run,
        "phase_names": incubation_phase_names(),
        "required_phases": required_phase_names(),
        "required_failed": required_failed,
        "results": [
            {
                "name": r.name,
                "required": r.required,
                "timeout_sec": r.timeout_sec,
                "success": r.success,
                "skipped": r.skipped,
                "dry_run": r.dry_run,
                "error": r.error,
                "payload": r.payload,
            }
            for r in results
        ],
    }


__all__ = [
    "CyclePlan",
    "PhaseRunResult",
    "build_once_cycle_plan",
    "run_phase_plan",
]
