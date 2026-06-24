"""Incubation provider interface - defines what host must provide."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class IncubationProvider(Protocol):
    """Provider interface for incubation runtime capabilities.

    Host process (e.g., akshare-mcp) must implement this interface to provide
    concrete signal generation, verification, metrics, pipeline, and paper trading.
    """

    async def get_db(self) -> Any:
        """Return initialized database connection."""
        ...

    async def scan_and_accept_strategies(
        self,
        db: Any,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Scan and accept strategies into incubation (Phase 1: Intake)."""
        ...

    async def list_incubating_strategies(
        self,
        db: Any,
        *,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """List strategies currently in incubation."""
        ...

    async def generate_signals(
        self,
        db: Any,
        strategy: dict[str, Any],
        *,
        as_of: date,
    ) -> dict[str, Any]:
        """Generate trading signals for a strategy (Phase 2)."""
        ...

    async def verify_forward_returns(
        self,
        db: Any,
        strategy: dict[str, Any],
    ) -> dict[str, Any]:
        """Verify forward returns for strategy signals (Phase 3)."""
        ...

    async def record_metrics(
        self,
        db: Any,
        strategy: dict[str, Any],
        verification_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Record incubation metrics (Phase 4)."""
        ...

    async def settle_orders(
        self,
        db: Any,
        strategy: dict[str, Any],
        signal_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Settle paper trading orders (Phase 5)."""
        ...

    async def run_pipeline(
        self,
        db: Any,
        strategies: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run incubation pipeline transitions (Phase 6)."""
        ...

    async def generate_hit_rate_report(
        self,
        db: Any,
        strategies: list[dict[str, Any]],
        verification_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate hit rate report (Phase 7)."""
        ...

    def paper_runtime_status(self) -> dict[str, Any]:
        """Get paper runtime (matching engine, NAV engine) status."""
        ...

    async def start_paper_runtime(self) -> None:
        """Start paper runtime engines."""
        ...

    async def stop_paper_runtime(self) -> None:
        """Stop paper runtime engines."""
        ...
