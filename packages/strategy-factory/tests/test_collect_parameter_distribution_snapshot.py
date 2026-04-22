from __future__ import annotations

import asyncio

from strategy_factory.application.collect import DataCollector


class _FakeDb:
    def __init__(self) -> None:
        self.max_quality_active = 0
        self.max_signal_active = 0
        self._quality_active = 0
        self._signal_active = 0

    async def list_strategies(self, status: str, limit: int = 120):
        return [
            {
                "id": f"{status}_{index}",
                "author_id": "strategy_factory",
                "strategy_type": "momentum",
                "params": {"lookback": 10 + index},
                "tags": ["factory"],
            }
            for index in range(10)
        ]

    async def get_latest_strategy_quality_report(self, strategy_id: str):
        self._quality_active += 1
        self.max_quality_active = max(self.max_quality_active, self._quality_active)
        try:
            await asyncio.sleep(0.01)
            if strategy_id.endswith("_3"):
                raise RuntimeError("quality query failed")
            return {
                "passed": True,
                "summary": {
                    "validation_grade": "B",
                },
            }
        finally:
            self._quality_active -= 1

    async def get_signal_stats(self, strategy_id: str):
        self._signal_active += 1
        self.max_signal_active = max(self.max_signal_active, self._signal_active)
        try:
            await asyncio.sleep(0.01)
            if strategy_id.endswith("_7"):
                raise RuntimeError("signal query failed")
            return {
                "total_signals": 16,
                "hit_rate": {1: 0.5, 5: 0.55, 10: 0.57, 20: 0.6},
            }
        finally:
            self._signal_active -= 1


def test_parameter_distribution_snapshot_limits_query_concurrency_and_degrades_partially():
    collector = DataCollector()
    db = _FakeDb()

    result = asyncio.run(
        collector._collect_parameter_distribution_snapshot(
            db,
            limit_per_status=10,
            max_samples=20,
            query_concurrency=4,
        )
    )

    summary = dict(result.get("summary") or {})

    assert db.max_quality_active <= 4
    assert db.max_signal_active <= 4
    assert summary["query_concurrency"] == 4
    assert summary["quality_query_error_count"] > 0
    assert summary["signal_query_error_count"] > 0
    assert summary["sample_count"] == summary["eligible_sample_count"]
    assert summary["eligible_sample_count"] > 0
