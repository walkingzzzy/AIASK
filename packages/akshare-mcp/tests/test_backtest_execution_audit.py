import pytest

from akshare_mcp.services.backtest.engine import BacktestEngine


def _make_klines(n: int = 80, *, start: float = 10.0, volume: float = 1_000_000.0, zero_every: int = 0) -> list[dict]:
    klines: list[dict] = []
    for i in range(n):
        close = round(start + i * 0.08, 2)
        trade_volume = 0.0 if zero_every and i % zero_every == 0 else float(volume)
        klines.append(
            {
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "open": close,
                "high": round(close * 1.01, 2),
                "low": round(close * 0.99, 2),
                "close": close,
                "volume": trade_volume,
            }
        )
    return klines


def test_run_backtest_preserves_explicit_implementation_shortfall_input():
    result = BacktestEngine.run_backtest(
        "600519",
        _make_klines(),
        "buy_and_hold",
        {
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "volume_based",
            "tradability_filter": True,
            "implementation_shortfall_proxy": 42.5,
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
    )

    assert result["success"] is True
    data = result["data"]
    assert data["implementation_shortfall_proxy"] == pytest.approx(42.5)
    assert data["implementation_shortfall_model_source"] == "explicit_input"
    assert data["implementation_shortfall_components"]["override_input_bps"] == pytest.approx(42.5)
    assert data["implementation_shortfall_components"]["estimated_total_bps"] > 0
    assert data["avg_holding_days"] > 0
    assert data["turnover_proxy"] > 1.0


def test_run_backtest_keeps_implementation_shortfall_proxy_out_of_pnl_chain():
    base_params = {
        "lookback": 5,
        "threshold": 0.01,
        "initial_capital": 100000,
        "commission": 0.0003,
        "slippage_model": "fixed",
        "tradability_filter": True,
        "position_assumption": "equal_weight_proxy",
        "target_weight_scheme": "equal_weight",
    }

    base = BacktestEngine.run_backtest(
        "600519",
        _make_klines(n=120, start=10.0, volume=2_000_000.0),
        "momentum",
        dict(base_params),
    )
    stressed_audit = BacktestEngine.run_backtest(
        "600519",
        _make_klines(n=120, start=10.0, volume=2_000_000.0),
        "momentum",
        {
            **base_params,
            "implementation_shortfall_proxy": 55.0,
        },
    )

    assert base["success"] is True
    assert stressed_audit["success"] is True
    assert stressed_audit["data"]["implementation_shortfall_proxy"] == pytest.approx(55.0)
    assert stressed_audit["data"]["implementation_shortfall_model_source"] == "explicit_input"
    assert stressed_audit["data"]["total_return"] == pytest.approx(base["data"]["total_return"])
    assert stressed_audit["data"]["final_capital"] == pytest.approx(base["data"]["final_capital"])


def test_run_backtest_estimates_shortfall_from_capacity_and_tradability_pressure():
    liquid = BacktestEngine.run_backtest(
        "600519",
        _make_klines(volume=2_000_000.0),
        "buy_and_hold",
        {
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "volume_based",
            "tradability_filter": True,
            "capacity_participation_rate": 0.02,
            "adv_ratio_limit": 0.20,
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
            "arrival_price_policy": "vwap_proxy",
        },
    )
    stressed = BacktestEngine.run_backtest(
        "600519",
        _make_klines(volume=40_000.0, zero_every=7),
        "buy_and_hold",
        {
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "volume_based",
            "tradability_filter": True,
            "capacity_participation_rate": 0.30,
            "adv_ratio_limit": 0.02,
            "market_impact_bps": 12.0,
            "capacity_bucket": "small",
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
            "arrival_price_policy": "next_open_proxy",
        },
    )

    assert liquid["success"] is True
    assert stressed["success"] is True

    liquid_data = liquid["data"]
    stressed_data = stressed["data"]

    assert stressed_data["implementation_shortfall_model_source"] == "estimated"
    assert stressed_data["implementation_shortfall_proxy"] > liquid_data["implementation_shortfall_proxy"]
    assert stressed_data["implementation_shortfall_components"]["capacity_bps"] > liquid_data["implementation_shortfall_components"]["capacity_bps"]
    assert stressed_data["tradability_summary"]["tradable_ratio"] < 1.0
    assert stressed_data["capacity_summary"]["adv_utilization"] > 1.0
    assert stressed_data["avg_holding_days"] > 0
    assert stressed_data["turnover_proxy"] > 1.0


def test_run_backtest_applies_market_rules_and_position_constraints_to_pnl():
    base = BacktestEngine.run_backtest(
        "600519",
        _make_klines(n=120, start=10.0, volume=2_000_000.0),
        "momentum",
        {
            "lookback": 5,
            "threshold": 0.01,
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "fixed",
        },
    )
    constrained = BacktestEngine.run_backtest(
        "600519",
        _make_klines(n=120, start=10.0, volume=2_000_000.0),
        "momentum",
        {
            "lookback": 5,
            "threshold": 0.01,
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "fixed",
            "market_ruleset": "cn_equity",
            "sell_tax_rate": 0.001,
            "min_trade_lot": 100,
            "t_plus_one": True,
            "max_position_pct": 0.2,
            "market_impact_bps": 12.0,
            "arrival_price_policy": "next_open_proxy",
        },
    )

    assert base["success"] is True
    assert constrained["success"] is True

    base_data = base["data"]
    constrained_data = constrained["data"]

    assert constrained_data["total_return"] < base_data["total_return"]
    assert constrained_data["final_capital"] < base_data["final_capital"]
    assert constrained_data["turnover_proxy"] < base_data["turnover_proxy"]
    assert constrained_data["cost_assumptions"]["market_ruleset"] == "cn_equity"
    assert constrained_data["cost_assumptions"]["min_trade_lot"] == 100
    assert constrained_data["cost_assumptions"]["t_plus_one"] is True
    assert constrained_data["sell_tax_rate"] == pytest.approx(0.001)


def test_run_portfolio_backtest_builds_shared_cash_portfolio_metrics():
    market_data = {
        "600519": _make_klines(n=100, start=10.0, volume=2_000_000.0),
        "000858": _make_klines(n=100, start=12.0, volume=1_500_000.0),
    }

    result = BacktestEngine.run_portfolio_backtest(
        market_data,
        "buy_and_hold",
        {
            "initial_capital": 200000,
            "commission": 0.0003,
            "slippage_model": "volume_based",
            "tradability_filter": True,
            "target_weight_scheme": "equal_weight",
            "position_assumption": "equal_weight_proxy",
            "capacity_participation_rate": 0.05,
            "adv_ratio_limit": 0.20,
        },
    )

    assert result["success"] is True
    data = result["data"]
    assert data["portfolio_mode"] == "shared_cash"
    assert data["portfolio_engine_version"] == "shared_cash_v1"
    assert data["component_count"] == 2
    assert data["allocation_mode"] == "equal_weight"
    assert data["allocation_weights"]["600519"] == pytest.approx(0.5, abs=1e-6)
    assert data["allocation_weights"]["000858"] == pytest.approx(0.5, abs=1e-6)
    assert data["final_capital"] > data["initial_capital"]
    assert data["trades_count"] == 4
    assert data["avg_holding_days"] > 0
    assert data["turnover_proxy"] > 1.0
    assert data["implementation_shortfall_proxy"] > 0
    assert data["tradability_summary"]["tradability_filter"] is True
    assert data["execution_summary"]["order_attempt_count"] >= 4
    assert data["execution_summary"]["fill_rate"] > 0
    assert data["execution_summary"]["failed_fill_rate"] == pytest.approx(0.0)
    assert len(data["cash_curve"]) == len(data["equity_curve"])
    assert len(data["gross_exposure_curve"]) == len(data["equity_curve"])
    assert data["capacity_summary"]["avg_participation_rate"] >= 0
    assert len(data["equity_curve"]) >= 2


def test_run_portfolio_backtest_keeps_implementation_shortfall_proxy_out_of_pnl_chain():
    market_data = {
        "600519": _make_klines(n=100, start=10.0, volume=2_000_000.0),
        "000858": _make_klines(n=100, start=12.0, volume=1_500_000.0),
    }
    base_params = {
        "initial_capital": 200000,
        "commission": 0.0003,
        "slippage_model": "volume_based",
        "tradability_filter": True,
        "target_weight_scheme": "equal_weight",
        "position_assumption": "equal_weight_proxy",
        "capacity_participation_rate": 0.05,
        "adv_ratio_limit": 0.20,
    }

    base = BacktestEngine.run_portfolio_backtest(
        market_data,
        "buy_and_hold",
        dict(base_params),
    )
    stressed_audit = BacktestEngine.run_portfolio_backtest(
        market_data,
        "buy_and_hold",
        {
            **base_params,
            "implementation_shortfall_proxy": 48.0,
        },
    )

    assert base["success"] is True
    assert stressed_audit["success"] is True
    assert stressed_audit["data"]["implementation_shortfall_proxy"] == pytest.approx(48.0)
    assert stressed_audit["data"]["total_return"] == pytest.approx(base["data"]["total_return"])
    assert stressed_audit["data"]["final_capital"] == pytest.approx(base["data"]["final_capital"])
