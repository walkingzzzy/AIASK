from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import akshare_mcp.services.strategy_factory.runtime as legacy_runtime

from strategy_factory.application.quality_gates import gate_0_structural, gate_1_fast_screen


def test_gate_0_structural_compiles_dsl_with_strategy_dsl_module():
    candidate = {
        "strategy_type": "dsl_rule",
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 9}},
            }
        },
    }

    result = gate_0_structural(candidate)

    assert result.passed is True
    assert result.reasons == []


@pytest.mark.asyncio
async def test_gate_1_fast_screen_uses_backtest_engine_run_backtest(monkeypatch):
    calls = []

    class _FakeBacktestEngine:
        @staticmethod
        def run_backtest(code, klines, strategy, params):
            calls.append(
                {
                    "code": code,
                    "klines_len": len(klines),
                    "strategy": strategy,
                    "params": dict(params or {}),
                }
            )
            return {"success": True, "data": {"sharpe_ratio": 1.25}}

    monkeypatch.setattr(
        legacy_runtime,
        "get_strategy_factory_package",
        lambda: SimpleNamespace(BacktestEngine=_FakeBacktestEngine),
    )

    db = SimpleNamespace(
        get_klines=AsyncMock(
            side_effect=[
                [{"close": float(i + 1), "volume": 1000.0} for i in range(40)],
                [{"close": float(i + 2), "volume": 1000.0} for i in range(40)],
            ]
        )
    )

    result = await gate_1_fast_screen(
        {"strategy_type": "momentum", "params": {"lookback": 20, "threshold": 0.02}},
        db,
    )

    assert result.passed is True
    assert result.metrics["avg_sharpe"] == 1.25
    assert [item["code"] for item in calls] == ["600519", "000858"]
