from __future__ import annotations

from pathlib import Path

import pytest

from strategy_factory.application.candidate_contract import build_factory_backtest_assumptions
from strategy_factory.application.futures_calendar_research import (
    DEFAULT_SC_DATA_PATH,
    FuturesCalendarResearchAdapter,
    TrendConfig,
)


def _adapter() -> FuturesCalendarResearchAdapter:
    return FuturesCalendarResearchAdapter(
        data_path=DEFAULT_SC_DATA_PATH,
        output_dir=Path("/tmp/sc_calendar_research_tests"),
    )


def test_load_curve_frame_reconstructs_prices_and_contract_offsets():
    adapter = _adapter()
    frame = adapter.load_curve_frame(adapter.data_path)

    first_row = frame.iloc[0]

    assert first_row["price_02"] == pytest.approx(first_row["price_01"] - first_row["spread_1_2"])
    assert first_row["price_03"] == pytest.approx(first_row["price_02"] - first_row["spread_2_3"])
    assert first_row["contract_02"] == "sc1810"
    assert first_row["contract_03"] == "sc1811"


def test_add_features_marks_regime_and_price_trend_columns():
    adapter = _adapter()
    enriched = adapter.add_features(adapter.load_curve_frame(adapter.data_path))

    assert {"backwardation", "contango_or_flat"} == set(enriched["regime"].unique())
    assert (enriched["backwardation_flag"] == (enriched["spread_1_2"] > 0).astype(int)).all()
    assert "price_uptrend" in enriched.columns
    assert "price_downtrend" in enriched.columns
    assert enriched.loc[0, "regime"] == "backwardation"


def test_build_candidate_keeps_futures_specific_fields():
    adapter = _adapter()
    frame = adapter.add_features(adapter.load_curve_frame(adapter.data_path)).iloc[:180].reset_index(drop=True)
    config = TrendConfig(
        leg_month=4,
        carry_threshold=1.0,
        volatility_cap=0.03,
        price_to_ma60_cap=1.12,
        stop_loss_pct=0.05,
    )
    execution_profile = adapter._trend_execution_profile(config)
    backtest = {
        "summary": {
            "annualized_return": 0.12,
            "total_return": 0.35,
            "sharpe_ratio": 0.9,
            "post_cost_sharpe": 0.8,
            "max_drawdown": -0.15,
            "win_rate": 0.6,
            "trade_count": 8,
            "trade_density": 1.2,
            "forward_sharpe_5d": 1.0,
            "alpha_decay": 0.0,
            "ending_equity": 1_350_000.0,
        },
        "regime_panel": {
            "overall": {
                "annualized_return": 0.12,
                "sharpe_ratio": 0.9,
                "post_cost_sharpe": 0.8,
                "max_drawdown": -0.15,
                "win_rate": 0.6,
                "trade_count": 8,
            },
            "backwardation": {
                "annualized_return": 0.18,
                "sharpe_ratio": 1.0,
                "max_drawdown": -0.10,
                "trade_count": 5,
                "win_rate": 0.7,
            },
            "contango_or_flat": {
                "annualized_return": 0.04,
                "sharpe_ratio": 0.3,
                "max_drawdown": -0.08,
                "trade_count": 3,
                "win_rate": 0.4,
            },
        },
        "trades": [],
        "signal_series": frame["price_04"].astype(float),
    }
    capacity_panel = [
        {
            "capital": 1_000_000,
            "annualized_return": 0.12,
            "post_cost_sharpe": 0.8,
            "max_drawdown": -0.15,
            "win_rate": 0.6,
            "trade_count": 8,
            "capacity_limit_contracts": 6,
            "binding_constraint": "participation",
            "participation_cap": 6,
            "margin_cap": 8,
            "max_contracts_cap": 20,
            "drawdown_cap": 9,
        }
    ]

    candidate, raw_dsl, _compiled_dsl = adapter._build_candidate(
        frame,
        family="trend",
        config=config,
        execution_profile=execution_profile,
        backtest=backtest,
        capacity_panel=capacity_panel,
    )

    assert candidate["status"] == "submitted"
    assert candidate["instrument_profile"]["asset_class"] == "futures"
    assert candidate["instrument_profile"]["underlying"] == "SC"
    assert candidate["portfolio_spec"]["position_assumption"] == "single_futures_directional"
    assert candidate["execution_assumptions"]["margin_rate"] == pytest.approx(execution_profile.margin_rate)
    assert candidate["execution_assumptions"]["contract_multiplier"] == execution_profile.contract_multiplier
    assert candidate["execution_assumptions"]["liquidity_bucket"] == execution_profile.liquidity_bucket
    assert candidate["execution_assumptions"]["max_contracts_per_rebalance"] == execution_profile.max_contracts_per_rebalance
    assert candidate["dsl"]["metadata"]["instrument_profile"]["asset_class"] == "futures"
    assert raw_dsl["metadata"]["signal_reference_series"] == "price_04"


def test_build_factory_backtest_assumptions_preserves_futures_execution_fields():
    candidate = {
        "target_symbols": ["SC"],
        "portfolio_spec": {
            "position_assumption": "paired_futures_spread",
            "target_weight_scheme": "paired_margin_budget",
            "max_position_pct": 0.7,
        },
        "execution_assumptions": {
            "initial_capital": 1_000_000,
            "commission_rate": 0.00004,
            "slippage_bps": 3.5,
            "slippage_model": "fixed_plus_capacity_scaled",
            "market_impact_bps": 1.2,
            "capacity_participation_rate": 0.08,
            "margin_rate": 0.15,
            "contract_multiplier": 1000,
            "liquidity_bucket": "mid_far_medium",
            "max_contracts_per_rebalance": 16,
            "market_ruleset": "cn_futures",
            "min_trade_lot": 1,
            "t_plus_one": False,
        },
        "validation_profile": {
            "profile": "trade_rule_validation",
            "validation_focus": "candidate_target_only",
            "primary_validation_layer": "target",
        },
    }

    assumptions = build_factory_backtest_assumptions(candidate)

    assert assumptions.margin_rate == pytest.approx(0.15)
    assert assumptions.contract_multiplier == 1000
    assert assumptions.liquidity_bucket == "mid_far_medium"
    assert assumptions.max_contracts_per_rebalance == 16
    assert assumptions.market_ruleset == "cn_futures"
    assert assumptions.position_assumption == "paired_futures_spread"
