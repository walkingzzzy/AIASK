"""Incubation contracts and DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncubationResult:
    """Result of an incubation cycle run."""

    success: bool
    run_id: str | None = None
    intake_accepted: int = 0
    intake_rejected: int = 0
    signals_generated: int = 0
    verification_completed: int = 0
    metrics_recorded: int = 0
    orders_settled: int = 0
    pipeline_transitions: int = 0
    auto_promotions: int = 0
    auto_terminations: int = 0
    phase_results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    runtime_universe: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
