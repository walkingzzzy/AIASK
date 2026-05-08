from __future__ import annotations

import asyncio

from strategy_factory.application.services.stress_test import STRESS_SCENARIOS, run_stress_test_simple


def test_stress_test_uses_backtest_fn_for_each_historical_scenario():
    calls: list[dict] = []

    async def _backtest_fn(strategy: dict, *, start_date: str, end_date: str):
        calls.append({"strategy_id": strategy["id"], "start_date": start_date, "end_date": end_date})
        if start_date in {"2015-06-12", "2016-01-04"}:
            return {"max_drawdown": 0.5, "sharpe_ratio": -4.0, "total_return": -0.3}
        return {"max_drawdown": 0.12, "sharpe_ratio": 0.5, "total_return": 0.04}

    result = asyncio.run(
        run_stress_test_simple(
            {"id": "s1", "strategy_type": "momentum"},
            backtest_fn=_backtest_fn,
        )
    )

    assert result.overall_verdict == "reject"
    assert result.evidence_mode == "historical_backtest"
    assert result.diagnostic_only is False
    assert len(calls) == len(STRESS_SCENARIOS)
    assert calls[0] == {"strategy_id": "s1", "start_date": "2015-06-12", "end_date": "2015-08-26"}
    assert calls[-1] == {"strategy_id": "s1", "start_date": "2024-01-29", "end_date": "2024-02-05"}


def test_stress_test_proxy_fallback_is_review_not_pass():
    result = asyncio.run(
        run_stress_test_simple(
            {"id": "s1", "strategy_type": "momentum"},
            backtest_metrics={"max_drawdown": 0.02, "sharpe_ratio": 2.0, "total_return": 0.2},
        )
    )

    assert result.overall_verdict == "review"
    assert result.evidence_mode == "backtest_metrics_proxy"
    assert result.diagnostic_only is True
    assert all(item.evidence_mode == "backtest_metrics_proxy" for item in result.scenarios)


def test_stress_test_proxy_fallback_can_reject_bad_metrics():
    result = asyncio.run(
        run_stress_test_simple(
            {"id": "s1", "strategy_type": "momentum"},
            backtest_metrics={"max_drawdown": 0.5, "sharpe_ratio": -4.0, "total_return": -0.3},
        )
    )

    assert result.overall_verdict == "reject"
    assert result.evidence_mode == "backtest_metrics_proxy"
    assert result.diagnostic_only is True
