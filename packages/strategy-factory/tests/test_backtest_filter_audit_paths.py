import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import strategy_factory.application.backtest_filter as backtest_filter_module
from strategy_factory.application.backtest_filter import BacktestFilter


def _make_klines(n: int = 140) -> list[dict]:
    return [
        {
            "date": f"2025-02-{(idx % 28) + 1:02d}",
            "open": 10.0 + idx * 0.02,
            "high": 10.1 + idx * 0.02,
            "low": 9.9 + idx * 0.02,
            "close": 10.0 + idx * 0.02,
            "volume": 1_000_000.0,
        }
        for idx in range(n)
    ]


class _FakeBacktestEngine:
    @staticmethod
    def run_backtest(code, klines, strategy_type, params):
        return {
            "success": True,
            "data": {
                "code": code,
                "strategy": strategy_type,
                "sharpe_ratio": 0.9,
                "total_return": 0.12,
                "max_drawdown": 0.08,
                "win_rate": 0.6,
                "trades_count": 6,
                "avg_holding_days": 9.0,
                "turnover_proxy": 1.8,
                "cost_assumptions": {
                    "commission_rate": params.get("commission"),
                    "implementation_shortfall_proxy": 18.4,
                    "implementation_shortfall_model_source": "estimated",
                },
                "explicit_cost_breakdown": {"commission_rate": params.get("commission")},
                "implicit_cost_breakdown": {"implementation_shortfall_proxy": 18.4},
                "tradability_summary": {
                    "tradability_filter": params.get("tradability_filter"),
                    "tradable_ratio": 0.92,
                },
                "capacity_summary": {
                    "capacity_participation_rate": params.get("capacity_participation_rate"),
                    "adv_utilization": 1.5,
                },
                "implementation_shortfall_model_source": "estimated",
                "implementation_shortfall_components": {
                    "capacity_bps": 11.2,
                    "effective_total_bps": 18.4,
                },
                "position_assumption": params.get("position_assumption"),
            },
        }


def _patch_runtime(monkeypatch):
    monkeypatch.setattr(backtest_filter_module, "get_backtest_engine_class", lambda: _FakeBacktestEngine)
    monkeypatch.setattr(backtest_filter_module, "_get_strategy_factory_package", lambda: SimpleNamespace(asyncio=asyncio))


@pytest.mark.asyncio
async def test_backtest_filter_propagates_execution_audit_fields(monkeypatch):
    _patch_runtime(monkeypatch)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858", "000001"],
        },
        "execution_assumptions": {
            "commission_rate": 0.00025,
            "tradability_filter": True,
            "capacity_participation_rate": 0.15,
            "adv_ratio_limit": 0.10,
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    metrics = passed[0]["backtest_metrics"]
    assert metrics["implementation_shortfall_model_source"] == "estimated"
    assert metrics["implementation_shortfall_components"]["capacity_bps"] == pytest.approx(11.2)
    assert metrics["tradability_summary"]["tradable_ratio"] == pytest.approx(0.92)
    assert metrics["capacity_summary"]["adv_utilization"] == pytest.approx(1.5)
    assert metrics["backtest_assumptions"]["target_weight_scheme"] == "equal_weight"
    assert metrics["avg_holding_days"] == pytest.approx(9.0)
    assert metrics["turnover_proxy"] == pytest.approx(1.8)


@pytest.mark.asyncio
async def test_backtest_filter_event_target_only_excludes_representative_contamination(monkeypatch):
    _patch_runtime(monkeypatch)
    db = MagicMock()
    db.get_klines = AsyncMock(return_value=_make_klines())

    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858", "000001"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "baijiu",
            "target_symbols": ["600519", "000858", "000001"],
            "validation_focus": "event_target_only",
        },
    }

    passed = await BacktestFilter().filter([candidate], db)

    assert len(passed) == 1
    result = passed[0]["backtest_result"]
    assert result["validation_focus"] == "event_target_only"
    assert result["primary_validation_layer"] == "target"
    assert result["contamination_summary"]["representative_included"] is False
    assert result["layers"]["representative"]["sample_count"] == 0
