from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from akshare_mcp.services import incubation as incubation_mod
from akshare_mcp.services.backtest.engine import BacktestEngine
from akshare_mcp.services.incubation import StrategyIncubationService

from ._strategy_factory_test_support import _StrategyDB


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


def test_dsl_rule_reduce_event_does_not_force_full_exit():
    prices = [10.0] * 25 + [10.6, 10.8, 11.0, 10.7, 10.3, 10.0, 9.7, 9.4, 9.2, 9.0, 9.1, 9.3, 9.5, 9.8, 10.2, 10.5]
    klines = [
        {
            "date": f"2025-02-{(i % 28) + 1:02d}",
            "open": price,
            "high": round(price * 1.01, 2),
            "low": round(price * 0.99, 2),
            "close": round(price, 2),
            "volume": 2_000_000.0,
        }
        for i, price in enumerate(prices)
    ]
    dsl = {
        "version": "1.0",
        "timeframe": "daily",
        "entry": {
            "any": [
                {
                    "op": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                }
            ]
        },
        "exit": {"any": []},
    }
    runtime_playbook = {
        "adverse_move_policy": {
            "loss_bands": [
                {"threshold_pct": 0.08, "action": "reduce", "label": "primary_reduce"},
                {"threshold_pct": 0.12, "action": "freeze_reentry", "label": "hard_stop_band"},
            ]
        },
        "reentry_policy": {"cooldown_days": 3},
    }

    result = BacktestEngine.run_backtest(
        "600519",
        klines,
        "dsl_rule",
        {
            "dsl": dsl,
            "runtime_playbook": runtime_playbook,
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "fixed",
        },
        return_trades=True,
    )

    assert result["success"] is True
    trades = result["data"]["trades"]
    reduce_trades = [item for item in trades if item.get("action") == "reduce"]
    exit_trades = [item for item in trades if item.get("action") == "exit"]
    round_trip_positions = result["data"]["round_trip_positions"]
    assert reduce_trades, trades
    assert exit_trades, trades
    buy_trades = [item for item in trades if item.get("signal") == 1]
    assert buy_trades, trades
    assert reduce_trades[0]["shares"] < buy_trades[0]["shares"]
    assert exit_trades[-1]["shares"] <= buy_trades[0]["shares"]
    assert result["data"]["trades_count"] >= 3
    assert result["data"]["closed_round_trip_count"] >= 1
    assert round_trip_positions
    assert round_trip_positions[0]["partial_exit_count"] >= 1
    assert round_trip_positions[0]["entry_qty"] > round_trip_positions[0]["remaining_qty"]
    assert round_trip_positions[0]["status"] == "closed"


def test_portfolio_backtest_reduce_event_keeps_position_open_until_final_exit():
    def _pattern(start: float) -> list[dict]:
        prices = [start] * 25 + [start * 1.06, start * 1.08, start * 1.10, start * 1.07, start * 1.03, start, start * 0.97, start * 0.94, start * 0.92, start * 0.90, start * 0.91, start * 0.93, start * 0.95, start * 0.98, start * 1.02, start * 1.05]
        return [
            {
                "date": f"2025-03-{(i % 28) + 1:02d}",
                "open": round(price, 2),
                "high": round(price * 1.01, 2),
                "low": round(price * 0.99, 2),
                "close": round(price, 2),
                "volume": 2_000_000.0,
            }
            for i, price in enumerate(prices)
        ]

    market_data = {
        "600519": _pattern(10.0),
        "000858": _pattern(12.0),
    }
    dsl = {
        "version": "1.0",
        "timeframe": "daily",
        "entry": {
            "any": [
                {
                    "op": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                }
            ]
        },
        "exit": {"any": []},
    }
    runtime_playbook = {
        "adverse_move_policy": {
            "loss_bands": [
                {"threshold_pct": 0.05, "action": "reduce", "label": "portfolio_reduce"},
                {"threshold_pct": 0.10, "action": "freeze_reentry", "label": "portfolio_hard_stop"},
            ]
        },
        "reentry_policy": {"cooldown_days": 3},
    }

    result = BacktestEngine.run_portfolio_backtest(
        market_data,
        "dsl_rule",
        {
            "dsl": dsl,
            "runtime_playbook": runtime_playbook,
            "initial_capital": 200000,
            "commission": 0.0003,
            "target_weight_scheme": "equal_weight",
            "position_assumption": "equal_weight_proxy",
        },
        return_trades=True,
    )

    assert result["success"] is True
    trades = result["data"]["trades"]
    assert any(item.get("action") == "reduce" for item in trades), trades
    assert any(item.get("action") == "exit" for item in trades), trades


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


@pytest.mark.asyncio
async def test_backtest_and_incubation_runtime_share_reduce_freeze_semantics(monkeypatch):
    start = date(2026, 4, 1)
    prices = [10.0] * 25 + [10.6, 10.8, 11.0, 10.7, 10.3, 10.0, 9.7, 9.4, 9.2, 9.0, 9.1, 9.3, 9.5, 9.8, 10.2, 10.5]
    klines = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": round(price, 2),
            "high": round(price * 1.01, 2),
            "low": round(price * 0.99, 2),
            "close": round(price, 2),
            "volume": 2_000_000.0,
        }
        for index, price in enumerate(prices)
    ]
    runtime_playbook = {
        "adverse_move_policy": {
            "loss_bands": [
                {"threshold_pct": 0.05, "action": "reduce", "label": "primary_reduce"},
                {"threshold_pct": 0.10, "action": "freeze_reentry", "label": "hard_stop_band"},
            ],
        },
        "reentry_policy": {"cooldown_days": 3},
    }
    dsl = {
        "version": "1.0",
        "timeframe": "daily",
        "entry": {
            "any": [
                {
                    "op": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                }
            ]
        },
        "exit": {"any": []},
    }

    backtest = BacktestEngine.run_backtest(
        "600519",
        klines,
        "dsl_rule",
        {
            "dsl": dsl,
            "runtime_playbook": runtime_playbook,
            "initial_capital": 100000,
            "commission": 0.0003,
            "slippage_model": "fixed",
        },
        return_trades=True,
    )

    assert backtest["success"] is True
    trades = backtest["data"]["trades"]
    first_round_trip = backtest["data"]["round_trip_positions"][0]
    backtest_reduce_actions = [item for item in trades if item.get("action") == "reduce"]
    assert len(backtest_reduce_actions) == 1
    assert first_round_trip["partial_exit_count"] == 1
    assert first_round_trip["exit_reason"] == "hard_stop_band"
    buy_trade_times = [item.get("time") for item in trades if item.get("signal") == 1]
    assert len(buy_trade_times) >= 2
    assert (
        date.fromisoformat(str(buy_trade_times[1]))
        - date.fromisoformat(str(first_round_trip["exit_time"]))
    ).days >= 3

    db = _StrategyDB()
    service = StrategyIncubationService()

    class FrozenDateTime(datetime):
        current = datetime(2026, 6, 1, 9, 35, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            value = cls.current
            if tz is not None:
                return value.astimezone(tz)
            return value

    monkeypatch.setattr(incubation_mod, "datetime", FrozenDateTime)

    current_price = {"value": 10.8}

    async def _latest_price(_db, _code: str):
        return current_price["value"]

    async def _signals(_sid, start_date=None, end_date=None, limit=100):
        signal_day = str(start_date or end_date or "")
        return [
            {
                "id": f"sig_runtime_{signal_day}",
                "code": "600519",
                "signal": 1,
            }
        ]

    db.get_signals = AsyncMock(side_effect=_signals)
    original_latest_price = service._latest_price
    service._latest_price = _latest_price

    strategy = {
        "id": "strat_runtime_contract",
        "name": "runtime-contract",
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "params": {
            "runtime_playbook": {
                **runtime_playbook,
                "position_policy": {
                    "base_budget_pct": 0.06,
                    "max_position_pct": 0.20,
                    "max_concurrent_positions": 1,
                },
            },
        },
    }
    runtime_days = [
        ("2026-06-01", 10.8),
        ("2026-06-02", 10.0),
        ("2026-06-03", 9.4),
        ("2026-06-04", 9.1),
        ("2026-06-05", 9.3),
        ("2026-06-06", 9.5),
        ("2026-06-07", 10.5),
    ]

    try:
        sync_results = []
        for raw_day, price in runtime_days:
            signal_day = date.fromisoformat(raw_day)
            FrozenDateTime.current = datetime.combine(
                signal_day,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ).replace(hour=9, minute=35)
            current_price["value"] = price
            sync_results.append(await service.sync_signals_to_orders(db, strategy, signal_day))
            await service.settle_orders(db, strategy, signal_day)
    finally:
        service._latest_price = original_latest_price

    orders = await db.list_strategy_paper_orders(strategy["id"])
    buy_orders = sorted(
        [item for item in orders if item.get("direction") == "buy"],
        key=lambda item: str(item.get("signal_date") or ""),
    )
    sell_orders = sorted(
        [item for item in orders if item.get("direction") == "sell"],
        key=lambda item: str(item.get("signal_date") or ""),
    )
    positions = await db.list_strategy_trade_positions(strategy_id=strategy["id"], limit=20)
    closed_positions = [row for row in positions if row.get("status") == "closed"]
    fills = await db.list_strategy_trade_position_fills(
        position_id=closed_positions[0]["position_id"],
        limit=20,
    )
    entry_fill = next(item for item in fills if item.get("fill_side") == "buy")
    sell_fills = [item for item in fills if item.get("fill_side") == "sell"]

    assert sync_results[0]["created_count"] == 1
    assert sync_results[1]["created_count"] == 1
    assert sync_results[2]["created_count"] == 1
    assert sync_results[3]["created_count"] == 0
    assert sync_results[4]["created_count"] == 0
    assert sync_results[5]["created_count"] == 0
    assert sync_results[6]["created_count"] == 1

    assert len(buy_orders) == 2
    assert len(sell_orders) == 2
    assert sell_orders[0]["reason"] == "runtime_playbook_primary_reduce"
    assert sell_orders[1]["reason"] == "runtime_playbook_hard_stop_band"
    assert len(sell_fills) == 2
    assert int(sell_fills[0]["quantity"]) < int(entry_fill["quantity"])
    assert sum(int(item["quantity"]) for item in sell_fills) == int(entry_fill["quantity"])
    assert len(closed_positions) == 1
    assert (
        date.fromisoformat(str(buy_orders[1]["signal_date"]))
        - date.fromisoformat(str(sell_orders[1]["signal_date"]))
    ).days >= 3
