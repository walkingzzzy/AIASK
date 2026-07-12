"""Incubation factory phase order + default timeouts (ownership table).

Host runner (akshare-mcp IncubationFactoryRunner) imports this table for
phase names / timeouts so orchestration policy lives in Strategy Factory.
I/O implementations remain host-side.

Phase *names* must match runner ``_run_phase("...")`` call sites.
"""

from __future__ import annotations

from dataclasses import dataclass


STRATEGY_TIMEOUT_SEC: float = 30.0
BATCH_TIMEOUT_SEC: float = 600.0
ERROR_BACKOFF_SEC: float = 300.0
HEARTBEAT_INTERVAL_SEC: float = 3600.0


@dataclass(frozen=True)
class IncubationPhaseSpec:
    name: str
    timeout_sec: float
    required: bool = True
    description: str = ""


# Ordered once-cycle phases — names locked to IncubationFactoryRunner.run_once.
INCUBATION_ONCE_PHASES: tuple[IncubationPhaseSpec, ...] = (
    IncubationPhaseSpec("intake", BATCH_TIMEOUT_SEC, True, "Accept / intake candidates"),
    IncubationPhaseSpec(
        "recompile_remediation",
        BATCH_TIMEOUT_SEC,
        False,
        "Contract recompile remediation",
    ),
    IncubationPhaseSpec(
        "trade_prediction_outcomes",
        BATCH_TIMEOUT_SEC,
        False,
        "Trade prediction daily outcomes",
    ),
    IncubationPhaseSpec(
        "paper_execution_backlog",
        BATCH_TIMEOUT_SEC,
        False,
        "Paper execution backlog",
    ),
    IncubationPhaseSpec(
        "exit_signal_paper_execution",
        BATCH_TIMEOUT_SEC,
        True,
        "Exit signal paper execution",
    ),
    IncubationPhaseSpec(
        "stale_paper_position_closure",
        BATCH_TIMEOUT_SEC,
        False,
        "Stale paper position closure",
    ),
    IncubationPhaseSpec(
        "native_execution_evidence_backfill",
        BATCH_TIMEOUT_SEC,
        False,
        "Native execution evidence backfill",
    ),
    IncubationPhaseSpec(
        "execution_audit_acceptance",
        BATCH_TIMEOUT_SEC,
        True,
        "Execution audit acceptance",
    ),
    IncubationPhaseSpec(
        "execution_audit_remediation",
        BATCH_TIMEOUT_SEC,
        False,
        "Execution audit remediation",
    ),
    IncubationPhaseSpec("pipeline", BATCH_TIMEOUT_SEC, True, "Incubation pipeline evaluate"),
    IncubationPhaseSpec("hit_rate_report", BATCH_TIMEOUT_SEC, False, "Hit-rate report"),
    IncubationPhaseSpec("feedback_write", BATCH_TIMEOUT_SEC, False, "Feedback write"),
    IncubationPhaseSpec("acceleration", BATCH_TIMEOUT_SEC, False, "Incubation acceleration"),
    IncubationPhaseSpec("alert_check", STRATEGY_TIMEOUT_SEC, False, "Alert monitor"),
    IncubationPhaseSpec("heartbeat", STRATEGY_TIMEOUT_SEC, False, "Heartbeat"),
)


def incubation_phase_names() -> list[str]:
    return [p.name for p in INCUBATION_ONCE_PHASES]


def get_phase_timeout(name: str, default: float | None = None) -> float:
    for phase in INCUBATION_ONCE_PHASES:
        if phase.name == name:
            return float(phase.timeout_sec)
    return float(BATCH_TIMEOUT_SEC if default is None else default)


def required_phase_names() -> list[str]:
    return [p.name for p in INCUBATION_ONCE_PHASES if p.required]


__all__ = [
    "BATCH_TIMEOUT_SEC",
    "ERROR_BACKOFF_SEC",
    "HEARTBEAT_INTERVAL_SEC",
    "INCUBATION_ONCE_PHASES",
    "IncubationPhaseSpec",
    "STRATEGY_TIMEOUT_SEC",
    "get_phase_timeout",
    "incubation_phase_names",
    "required_phase_names",
]
