"""Smoke tests for BacktestFilter import and basic structure."""

from __future__ import annotations

import pytest


def test_backtest_filter_import():
    from strategy_factory.application.backtest_filter import BacktestFilter

    bf = BacktestFilter()
    assert bf is not None
    assert hasattr(bf, "filter")


def test_backtest_filter_thresholds_loaded():
    from strategy_factory.domain.constants import (
        BACKTEST_DEFAULT_THRESHOLDS,
        BACKTEST_AI_PROTOTYPE_THRESHOLDS,
        BACKTEST_TYPE_THRESHOLDS,
    )

    assert BACKTEST_DEFAULT_THRESHOLDS["sharpe_min"] > 0
    assert BACKTEST_AI_PROTOTYPE_THRESHOLDS["sharpe_min"] > 0
    assert "momentum" in BACKTEST_TYPE_THRESHOLDS
    assert "ma_cross" in BACKTEST_TYPE_THRESHOLDS


def test_backtest_trade_profile_from_round_trips():
    from strategy_factory.application.backtest_filter import BacktestFilter

    payload = BacktestFilter._merge_trade_profile_metrics(
        {
            "initial_capital": 100000,
            "round_trip_positions": [
                {"status": "closed", "realized_pnl": 100.0, "realized_return": 0.01, "hold_days": 5},
                {"status": "closed", "realized_pnl": -50.0, "realized_return": -0.005, "hold_days": 3},
            ],
        }
    )

    assert payload["trade_profile_available"] is True
    assert payload["expectancy"] == 25.0
    assert payload["profit_factor"] == 2.0
    assert payload["payoff_ratio"] == 2.0
    assert payload["breakeven_win_rate"] == pytest.approx(1 / 3, abs=1e-6)
    assert payload["trade_distribution"]["sample_count"] == 2


def test_backtest_trade_profile_from_trades_fallback():
    from strategy_factory.application.backtest_filter import BacktestFilter

    payload = BacktestFilter._merge_trade_profile_metrics(
        {
            "initial_capital": 100000,
            "trades": [
                {"signal": 1, "price": 10.0, "shares": 100, "profit": 0.0},
                {"signal": -1, "price": 11.0, "shares": 100, "profit": 100.0, "holding_days": 4},
                {"signal": -1, "price": 9.5, "shares": 100, "profit": -50.0, "holding_days": 2},
            ],
        }
    )

    assert payload["trade_profile_available"] is True
    assert payload["trade_profile_source"] == "trades"
    assert payload["expectancy"] == 25.0
    assert payload["profit_factor"] == 2.0
    assert payload["trade_distribution"]["win_count"] == 1
    assert payload["trade_distribution"]["loss_count"] == 1
