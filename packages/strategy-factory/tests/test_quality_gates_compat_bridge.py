from unittest.mock import MagicMock

import pytest

import akshare_mcp.services.strategy_factory.quality_gates as legacy_quality_gates

from strategy_factory.application.quality_gates import GateResult, run_gated_filter


class _DummyBacktestFilter:
    async def filter(self, candidates, _db):
        return list(candidates)

    def get_last_report(self):
        return {"summary": {"passed_count": 1}}


@pytest.mark.asyncio
async def test_run_gated_filter_uses_legacy_gate_1_patch_point(monkeypatch):
    async def _fake_gate_1_fast_screen(_candidate, _db, *, kline_cache=None):
        del kline_cache
        return GateResult(
            passed=True,
            gate="gate_1",
            reasons=[],
            metrics={"avg_sharpe": 1.23},
        )

    monkeypatch.setattr(legacy_quality_gates, "gate_1_fast_screen", _fake_gate_1_fast_screen)

    result = await run_gated_filter(
        [{"strategy_type": "momentum", "params": {"lookback": 20}}],
        MagicMock(),
        _DummyBacktestFilter(),
    )

    assert len(result["passed"]) == 1
    assert result["gate_report"]["gate_1"]["passed_candidates"][0]["avg_sharpe"] == 1.23
