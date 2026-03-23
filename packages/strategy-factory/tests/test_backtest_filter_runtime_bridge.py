import akshare_mcp.services.strategy_factory.runtime as legacy_runtime
import pytest

from strategy_factory.api import FactoryBacktestAssumptions
from strategy_factory.application.backtest_filter import BacktestFilter, _get_strategy_factory_package


def test_backtest_filter_uses_legacy_runtime_patch_point(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(legacy_runtime, "get_strategy_factory_package", lambda: sentinel)

    assert _get_strategy_factory_package() is sentinel


@pytest.mark.asyncio
async def test_backtest_filter_reports_candidate_level_exceptions(monkeypatch):
    async def _noop_preload(self, db, codes=None):
        return None

    async def _fake_test_one(self, candidate, db, engine):
        if candidate.get("strategy_type") == "broken":
            raise RuntimeError("boom")
        return {"passed": True, "metrics": {"sharpe_ratio": 1.0}, "reason_code": "passed"}

    monkeypatch.setattr(BacktestFilter, "preload_klines", _noop_preload)
    monkeypatch.setattr(BacktestFilter, "_test_one", _fake_test_one)
    monkeypatch.setattr(
        "strategy_factory.application.backtest_filter.get_backtest_engine_class",
        lambda: object(),
    )

    backtest_filter = BacktestFilter()
    candidates = [
        {"strategy_type": "broken", "params": {}},
        {"strategy_type": "momentum", "params": {}},
    ]

    passed = await backtest_filter.filter(candidates, db=object())
    report = backtest_filter.get_last_report()

    assert [item["strategy_type"] for item in passed] == ["momentum"]
    assert report["summary"]["failed_count"] == 1
    assert report["failed"][0]["backtest_result"]["reason_code"] == "candidate_exception"


def test_backtest_filter_builds_normalized_factory_backtest_assumptions():
    assumptions = BacktestFilter._build_backtest_assumptions(
        {
            "target_symbols": ["600519", "000858"],
            "research_task": {"task_source": "event_driven"},
            "execution_assumptions": {
                "initial_capital": 200000,
                "commission_rate": 0.0003,
                "slippage_bps": 12,
                "market_impact_bps": 6,
                "arrival_price_policy": "close_proxy",
                "implementation_shortfall_proxy": 18,
                "tradability_filter": True,
                "slippage_model": "volume",
                "capacity_participation_rate": 0.15,
                "adv_ratio_limit": 0.08,
                "capacity_bucket": "mid",
            },
            "portfolio_spec": {
                "position_assumption": "equal_weight_proxy",
                "target_weight_scheme": "equal_weight",
                "max_position_pct": 0.35,
            },
        }
    )

    assert isinstance(assumptions, FactoryBacktestAssumptions)
    assert assumptions.position_assumption == "equal_weight_proxy"
    assert assumptions.target_weight_scheme == "equal_weight"
    kwargs = assumptions.to_backtest_kwargs()
    audit = assumptions.to_audit_dict()
    assert kwargs["slippage"] == pytest.approx(0.0012)
    assert kwargs["commission"] == pytest.approx(0.0003)
    assert audit["slippage_bps"] == pytest.approx(12.0)
    assert audit["validation_focus"] == "event_target_only"
