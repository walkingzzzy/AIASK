"""Strategy factory application services.

Each service handles a single stage of the factory pipeline:

- ReadinessService    – evaluates snapshot + factor readiness
- TaskOrchestrator   – schedules and runs autonomy research tasks
- CandidatePipeline  – spawn → gate-0/1/2 → dedup → gate-3 submission
"""

from .candidate_pipeline import CandidatePipeline
from .alpha_research_service import AlphaResearchService
from .readiness_service import ReadinessService
from .task_orchestrator import TaskOrchestrator

__all__ = [
    "AlphaResearchService",
    "CandidatePipeline",
    "ReadinessService",
    "TaskOrchestrator",
]
