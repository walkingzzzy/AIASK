from __future__ import annotations

import asyncio
from datetime import date

from akshare_mcp.services.strategy_lifecycle_shared.overview import build_incubation_overview


class _OverviewCacheDb:
    async def get_latest_strategy_quality_report(self, strategy_id: str):
        assert strategy_id == "strategy-cache"
        return {"updated_at": "2026-04-21T08:00:00+00:00"}

    async def get_latest_execution_audit_snapshot(self, strategy_id: str):
        assert strategy_id == "strategy-cache"
        return {
            "snapshot_id": "eas-cache",
            "as_of": date.today().isoformat(),
            "correlation_id": "corr-cache",
            "factory_run_id": "factory-cache",
            "verdict": {"status": "passed", "reasons": [], "hard_gate_passed": True},
        }

    async def get_latest_strategy_closure_snapshot(self, strategy_id: str, snapshot_type: str = "incubation_overview"):
        assert strategy_id == "strategy-cache"
        assert snapshot_type == "incubation_overview"
        return {
            "snapshot_id": "cls-cache",
            "as_of": date.today().isoformat(),
            "metadata": {
                "strategy_status": "incubating",
                "quality_report_updated_at": "2026-04-21T08:00:00+00:00",
                "execution_audit_snapshot_id": "eas-cache",
            },
            "snapshot": {
                "strategy_id": strategy_id,
                "status": "incubating",
                "pipeline_stage": "candidate",
                "promotion_gate_status": "passed",
                "execution_audit_snapshot": {
                    "snapshot_id": "eas-cache",
                },
            },
        }

    async def get_strategy_metrics(self, strategy_id: str):
        raise AssertionError("cached overview should not recompute metrics")

    async def get_signal_stats(self, strategy_id: str):
        raise AssertionError("cached overview should not recompute signal stats")


def test_incubation_overview_prefers_fresh_closure_snapshot():
    result = asyncio.run(
        build_incubation_overview(
            _OverviewCacheDb(),
            {"id": "strategy-cache", "status": "incubating"},
        )
    )

    assert result["strategy_id"] == "strategy-cache"
    assert result["cached"] is True
    assert result["recomputed"] is False
    assert result["closure_snapshot_id"] == "cls-cache"
    assert result["execution_audit_snapshot_id"] == "eas-cache"
    assert result["correlation_id"] == "corr-cache"
    assert result["factory_run_id"] == "factory-cache"
