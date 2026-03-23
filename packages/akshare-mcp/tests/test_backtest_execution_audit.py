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
