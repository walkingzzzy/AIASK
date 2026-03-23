import asyncio

import pytest

from strategy_factory.application.elimination import EliminationChecker


class _ConcurrentDB:
    def __init__(self):
        self.max_active = 0
        self._active = 0

    async def list_strategies(self, status: str, limit: int = 500):
        return [
            {"id": "s1", "strategy_type": "momentum"},
            {"id": "s2", "strategy_type": "momentum"},
            {"id": "s3", "strategy_type": "momentum"},
        ]

    async def get_strategy_metrics(self, strategy_id: str):
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        await asyncio.sleep(0.02)
        self._active -= 1
        return [
            {"strategy_id": strategy_id, "period": "backtest", "max_drawdown": 0.05, "sharpe_ratio": 1.0, "win_rate": 0.55},
            {"strategy_id": strategy_id, "period": "validation", "grade": "A"},
            {"strategy_id": strategy_id, "period": "risk", "var_percent": 1.0, "cvar_percent": 1.5, "stress_loss_percent": -8.0},
        ]

    async def get_signal_stats(self, strategy_id: str):
        return {"strategy_id": strategy_id, "hit_rate": {}, "total_signals": 0}


@pytest.mark.asyncio
async def test_elimination_checker_processes_listed_strategies_with_bounded_concurrency():
    checker = EliminationChecker()
    db = _ConcurrentDB()

    eliminated = await checker.check(db, "neutral")

    assert eliminated == []
    assert db.max_active >= 2
