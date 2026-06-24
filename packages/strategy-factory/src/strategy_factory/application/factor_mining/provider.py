"""Factor Mining provider interface - defines what host must provide."""

from __future__ import annotations

from typing import Any, Protocol


class FactorMiningProvider(Protocol):
    """Provider interface for factor mining runtime capabilities.

    Host process (e.g., akshare-mcp) must implement this interface to provide
    concrete engine scheduling, evolution, validation, and persistence.
    """

    async def get_db(self) -> Any:
        """Return initialized database connection."""
        ...

    async def ensure_persistent_pool(self, db: Any) -> None:
        """Ensure factor pool tables exist and load active pool from DB."""
        ...

    async def build_mining_context(
        self,
        db: Any,
        *,
        codes: list[str] | None = None,
    ) -> Any:
        """Build mining context with validation universe and metadata."""
        ...

    async def search_candidates(
        self,
        context: Any,
        *,
        engines: list[str] | None = None,
        candidate_count: int = 30,
    ) -> list[Any]:
        """Search for raw factor candidates using configured engines."""
        ...

    async def evolve_candidates(
        self,
        candidates: list[Any],
        context: Any,
        *,
        generations: int = 5,
        ic_evaluator: Any = None,
    ) -> list[Any]:
        """Evolve candidates through evolutionary optimization."""
        ...

    async def quick_filter_candidates(
        self,
        candidates: list[Any],
        context: Any,
    ) -> list[Any]:
        """Apply quick evidence filters to candidates."""
        ...

    async def validate_batch(
        self,
        db: Any,
        candidates: list[Any],
        context: Any,
    ) -> list[Any]:
        """Run full validation on candidate batch."""
        ...

    async def admit_batch(
        self,
        validated: list[Any],
    ) -> list[Any]:
        """Admit validated factors to active pool."""
        ...

    async def persist_admitted_factors(
        self,
        db: Any,
        admitted: list[Any],
    ) -> None:
        """Persist admitted factors to database."""
        ...

    async def persist_mining_run(
        self,
        db: Any,
        report: dict[str, Any],
    ) -> None:
        """Persist mining run report to database."""
        ...

    async def reappraise_quarantine_factors(
        self,
        db: Any,
        *,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Reappraise factors in quarantine for potential promotion."""
        ...

    async def record_feedback(
        self,
        run_id: str,
        raw_candidates: list[Any],
        evolved: list[Any],
        validated: list[Any],
        admitted: list[Any],
    ) -> None:
        """Record quality feedback for engine tuning."""
        ...

    def get_active_pool_size(self) -> int:
        """Get current active factor pool size."""
        ...

    def get_last_engines_used(self) -> list[str]:
        """Get list of engines used in last search."""
        ...

    def install_quick_evidence_evaluators(
        self,
        db: Any,
        context: Any,
    ) -> Any:
        """Install quick IC evaluators for evolution."""
        ...
