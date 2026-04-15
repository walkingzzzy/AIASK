from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from akshare_mcp.services import incubation as incubation_mod
from akshare_mcp.services import strategy_lifecycle_shared as lifecycle_mod
from akshare_mcp.services.incubation import StrategyIncubationService
from akshare_mcp.services.strategy_lifecycle_shared import build_execution_quality

from ._strategy_factory_test_support import _StrategyDB


@pytest.mark.asyncio
async def test_phase_5_trade_linkage_persists_signal_and_position_ids():
    db = _StrategyDB()

    await db.save_paper_order(
        {
            "id": 101,
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "signal_id": "sig_phase5_1",
            "position_id": "pos_phase5_1",
            "signal_date": "2026-04-10",
            "code": "600519",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "status": "filled",
        }
    )
    await db.save_paper_trade(
        {
            "id": "trade_phase5_1",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "101",
            "signal_id": "sig_phase5_1",
            "position_id": "pos_phase5_1",
            "stock_code": "600519",
            "trade_type": "buy",
            "quantity": 100,
            "price": 10.0,
            "amount": 1000.0,
            "commission": 1.0,
            "trade_time": "2026-04-10T10:00:00+00:00",
        }
    )

    orders = await db.list_strategy_paper_orders("strat_phase5")
    trades = await db.list_strategy_paper_trades("strat_phase5")

    assert orders[0]["signal_id"] == "sig_phase5_1"
    assert orders[0]["position_id"] == "pos_phase5_1"
    assert trades[0]["signal_id"] == "sig_phase5_1"
    assert trades[0]["position_id"] == "pos_phase5_1"


@pytest.mark.asyncio
async def test_phase_5_sync_signals_persists_signal_evidence_rows():
    db = _StrategyDB()
    service = StrategyIncubationService()
    signal_date = date(2026, 4, 10)
    db.get_signals = AsyncMock(
        return_value=[
            {
                "id": "sig_phase5_signal_1",
                "code": "600519",
                "signal": 1,
            }
        ]
    )

    strategy = {
        "id": "strat_phase5_signal_evidence",
        "name": "phase5-signal-evidence",
        "strategy_type": "event_driven",
        "target_symbols": ["600519"],
        "params": {
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev_signal_1",
                        "source_type": "news",
                        "direction": "up",
                        "raw_confidence": 0.81,
                        "claim_ids": ["claim_1"],
                        "proxy_only": False,
                        "target_symbols": ["600519"],
                    }
                ]
            }
        },
    }

    result = await service.sync_signals_to_orders(db, strategy, signal_date)
    orders = await db.list_strategy_paper_orders(strategy["id"], signal_date)
    evidence_rows = await db.list_strategy_signal_evidence(
        signal_id="sig_phase5_signal_1",
        strategy_id=strategy["id"],
    )

    assert result["created_count"] == 1
    assert orders[0]["signal_id"] == "sig_phase5_signal_1"
    assert orders[0]["position_id"].startswith("pos_")
    assert len(evidence_rows) == 1
    assert evidence_rows[0]["signal_id"] == "sig_phase5_signal_1"
    assert evidence_rows[0]["strategy_id"] == strategy["id"]
    assert evidence_rows[0]["evidence_id"] == "ev_signal_1"
    assert evidence_rows[0]["payload"]["signal_id"] == "sig_phase5_signal_1"
    assert evidence_rows[0]["payload"]["proxy_only"] is False
    assert str(evidence_rows[0]["signal_date"]) == "2026-04-10"


@pytest.mark.asyncio
async def test_phase_5_sync_signals_filters_codes_outside_strategy_target_universe():
    db = _StrategyDB()
    service = StrategyIncubationService()
    signal_date = date(2026, 4, 10)
    db.get_signals = AsyncMock(
        return_value=[
            {
                "id": "sig_wrong_code",
                "code": "000063",
                "signal": 1,
            },
            {
                "id": "sig_right_code",
                "code": "600519",
                "signal": 1,
            },
        ]
    )

    strategy = {
        "id": "strat_phase5_target_filter",
        "name": "phase5-target-filter",
        "strategy_type": "momentum",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "params": {
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "semantic_runtime_match": True,
            "execution_readiness_tier": "formal_runtime_ready",
            "instrument_profile": {
                "measurement_source": "realized_market_profile",
                "measured_profile_complete": True,
            },
        },
    }

    result = await service.sync_signals_to_orders(db, strategy, signal_date)
    orders = await db.list_strategy_paper_orders(strategy["id"], signal_date)

    assert result["created_count"] == 1
    assert len(orders) == 1
    assert orders[0]["code"] == "600519"
    assert orders[0]["signal_id"] == "sig_right_code"


@pytest.mark.asyncio
async def test_phase_5_sync_signals_does_not_autotrade_proxy_runtime_strategy():
    db = _StrategyDB()
    service = StrategyIncubationService()
    signal_date = date(2026, 4, 10)
    db.get_signals = AsyncMock(
        return_value=[
            {
                "id": "sig_proxy_quality",
                "code": "601988",
                "signal": 1,
            }
        ]
    )

    strategy = {
        "id": "strat_phase5_proxy_runtime",
        "name": "phase5-proxy-runtime",
        "strategy_type": "quality_factor",
        "target_symbols": ["601988"],
        "params": {
            "target_symbols": ["601988"],
            "proxy_runtime_used": True,
            "diagnostic_only": True,
            "execution_readiness_tier": "observe_diagnostic_only",
            "runtime_family_data_source": "price_proxy_runtime",
        },
    }

    result = await service.sync_signals_to_orders(db, strategy, signal_date)
    orders = await db.list_strategy_paper_orders(strategy["id"], signal_date)

    assert result["created_count"] == 0
    assert result["blocked_by_execution_guard"] == 1
    assert result["execution_guard"]["allow_signal_entries"] is False
    assert result["execution_guard"]["proxy_runtime_used"] is True
    assert orders == []


@pytest.mark.asyncio
async def test_phase_5_audit_summary_uses_only_complete_position_samples():
    db = _StrategyDB()
    await db.save_paper_account(
        {
            "id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "initial_capital": 100000.0,
            "current_capital": 100000.0,
            "total_value": 100000.0,
        }
    )

    trade_rows = [
        {
            "id": "trade_entry_complete",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "201",
            "signal_id": None,
            "position_id": None,
            "stock_code": "600519",
            "trade_type": "buy",
            "quantity": 100,
            "price": 10.0,
            "amount": 1000.0,
            "commission": 1.0,
            "trade_time": "2026-04-10T09:31:00+00:00",
        },
        {
            "id": "trade_exit_complete",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "202",
            "signal_id": None,
            "position_id": None,
            "stock_code": "600519",
            "trade_type": "sell",
            "quantity": 100,
            "price": 12.0,
            "amount": 1200.0,
            "commission": 1.0,
            "trade_time": "2026-04-12T09:31:00+00:00",
        },
        {
            "id": "trade_entry_open",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "203",
            "signal_id": None,
            "position_id": None,
            "stock_code": "000001",
            "trade_type": "buy",
            "quantity": 50,
            "price": 8.0,
            "amount": 400.0,
            "commission": 1.0,
            "trade_time": "2026-04-13T09:31:00+00:00",
        },
        {
            "id": "trade_orphan",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "missing-order",
            "signal_id": None,
            "position_id": None,
            "stock_code": "300750",
            "trade_type": "buy",
            "quantity": 30,
            "price": 20.0,
            "amount": 600.0,
            "commission": 1.0,
            "trade_time": "2026-04-14T09:31:00+00:00",
        },
    ]
    order_rows = [
        {
            "id": 201,
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "signal_id": "sig_complete",
            "position_id": "pos_complete",
            "signal_date": "2026-04-10",
            "code": "600519",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "status": "filled",
        },
        {
            "id": 202,
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "signal_id": "sig_complete",
            "position_id": "pos_complete",
            "signal_date": "2026-04-12",
            "code": "600519",
            "direction": "sell",
            "shares": 100,
            "price": 12.0,
            "status": "filled",
        },
        {
            "id": 203,
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "signal_id": "sig_open",
            "position_id": "pos_open",
            "signal_date": "2026-04-13",
            "code": "000001",
            "direction": "buy",
            "shares": 50,
            "price": 8.0,
            "status": "filled",
        },
    ]

    for row in order_rows:
        await db.save_paper_order(row)
    for row in trade_rows:
        await db.save_paper_trade(row)

    backfill = await db.backfill_trade_position_links("strat_phase5")
    summary = await db.get_strategy_trade_audit_summary("strat_phase5")
    complete_position = await db.get_strategy_trade_position("pos_complete")
    open_position = await db.get_strategy_trade_position("pos_open")

    assert backfill["position_count"] == 2
    assert backfill["fill_count"] == 3
    assert complete_position["status"] == "closed"
    assert complete_position["audit_eligible"] is True
    assert complete_position["execution_conversion_efficiency"] == pytest.approx(1.0)
    assert open_position["status"] == "open"
    assert open_position["audit_eligible"] is False
    assert summary["mapped_position_count"] == 2
    assert summary["realized_trade_count"] == 1
    assert summary["incomplete_position_count"] == 1
    assert summary["execution_conversion_efficiency"] == pytest.approx(1.0)
    assert summary["trade_expectancy"] == pytest.approx((1199.0 - 1001.0) / 1001.0, abs=1e-6)
    assert summary["pnl_conversion_efficiency"] == pytest.approx((1199.0 - 1001.0) / 1001.0, abs=1e-6)
    assert summary["audit_ready_for_hard_gate"] is False


@pytest.mark.asyncio
async def test_phase_5_execution_audit_verification_reports_schema_migrations_and_round_trip_health():
    db = _StrategyDB()
    db._market_schema_migrations.update(
        {
            "paper_trades_best_effort_position_backfill_v1",
            "strategy_candidate_evidence_native_backfill_v1",
            "strategy_signal_evidence_native_backfill_v1",
            "strategy_trade_positions_roundtrip_backfill_v1",
        }
    )
    await db.save_strategy_candidate_evidence(
        {
            "id": "cand_ev_1",
            "candidate_id": "cand_1",
            "strategy_id": "strat_phase5_verify",
            "evidence_id": "ev_1",
            "evidence_type": "news",
        }
    )
    await db.save_strategy_signal_evidence(
        {
            "id": "sig_ev_1",
            "signal_id": "sig_verify",
            "strategy_id": "strat_phase5_verify",
            "signal_date": "2026-04-10",
            "evidence_id": "ev_1",
            "payload": {"signal_id": "sig_verify"},
        }
    )
    await db.save_paper_order(
        {
            "id": 401,
            "account_id": "paper_acc_verify",
            "strategy_id": "strat_phase5_verify",
            "signal_id": "sig_verify",
            "position_id": "pos_verify",
            "signal_date": "2026-04-10",
            "code": "600519",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "status": "filled",
        }
    )
    await db.save_paper_order(
        {
            "id": 402,
            "account_id": "paper_acc_verify",
            "strategy_id": "strat_phase5_verify",
            "signal_id": "sig_verify",
            "position_id": "pos_verify",
            "signal_date": "2026-04-12",
            "code": "600519",
            "direction": "sell",
            "shares": 100,
            "price": 12.0,
            "status": "filled",
        }
    )
    await db.save_paper_trade(
        {
            "id": "trade_verify_entry",
            "account_id": "paper_acc_verify",
            "strategy_id": "strat_phase5_verify",
            "source_order_id": "401",
            "signal_id": "sig_verify",
            "position_id": "pos_verify",
            "stock_code": "600519",
            "trade_type": "buy",
            "quantity": 100,
            "price": 10.0,
            "amount": 1000.0,
            "commission": 1.0,
            "trade_time": "2026-04-10T09:31:00+00:00",
        }
    )
    await db.save_paper_trade(
        {
            "id": "trade_verify_exit",
            "account_id": "paper_acc_verify",
            "strategy_id": "strat_phase5_verify",
            "source_order_id": "402",
            "signal_id": "sig_verify",
            "position_id": "pos_verify",
            "stock_code": "600519",
            "trade_type": "sell",
            "quantity": 100,
            "price": 12.0,
            "amount": 1200.0,
            "commission": 1.0,
            "trade_time": "2026-04-12T09:31:00+00:00",
        }
    )

    verification = await db.get_execution_audit_verification("strat_phase5_verify")

    assert verification["status"] == "ok"
    assert verification["schema"]["all_required_tables_present"] is True
    assert verification["schema"]["all_required_columns_present"] is True
    assert verification["migrations"]["all_required_keys_applied"] is True
    assert verification["coverage"]["paper_orders"]["position_id_ratio"] == pytest.approx(1.0)
    assert verification["coverage"]["paper_trades"]["position_id_ratio"] == pytest.approx(1.0)
    assert verification["coverage"]["strategy_candidate_evidence_count"] == 1
    assert verification["coverage"]["strategy_signal_evidence_count"] == 1
    assert verification["trade_round_trip"]["position_status_counts"]["closed"] == 1
    assert verification["trade_round_trip"]["audit_summary"]["realized_trade_count"] == 1
    assert verification["recommendations"] == []


@pytest.mark.asyncio
async def test_phase_5_execution_quality_adds_audit_metrics_without_replacing_proxy(monkeypatch):
    monkeypatch.setattr(lifecycle_mod, "STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED", True)
    db = _StrategyDB()
    await db.save_paper_account(
        {
            "id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "initial_capital": 100000.0,
            "current_capital": 100000.0,
            "total_value": 100000.0,
        }
    )
    await db.save_paper_nav(
        {
            "account_id": "paper_acc_1",
            "nav_date": "2026-04-12",
            "total_value": 100500.0,
            "cash": 80500.0,
            "market_value": 20000.0,
            "daily_return": 0.005,
        }
    )
    await db.save_paper_nav(
        {
            "account_id": "paper_acc_1",
            "nav_date": "2026-04-10",
            "total_value": 100000.0,
            "cash": 100000.0,
            "market_value": 0.0,
            "daily_return": 0.0,
        }
    )
    await db.save_paper_order(
        {
            "id": 301,
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "signal_id": "sig_complete",
            "position_id": "pos_complete",
            "signal_date": "2026-04-10",
            "code": "600519",
            "direction": "buy",
            "shares": 100,
            "price": 10.0,
            "status": "filled",
        }
    )
    await db.save_paper_order(
        {
            "id": 302,
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "signal_id": "sig_complete",
            "position_id": "pos_complete",
            "signal_date": "2026-04-12",
            "code": "600519",
            "direction": "sell",
            "shares": 100,
            "price": 12.0,
            "status": "filled",
        }
    )
    await db.save_paper_trade(
        {
            "id": "trade_301",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "301",
            "stock_code": "600519",
            "trade_type": "buy",
            "quantity": 100,
            "price": 10.0,
            "amount": 1000.0,
            "commission": 1.0,
            "trade_time": "2026-04-10T09:31:00+00:00",
        }
    )
    await db.save_paper_trade(
        {
            "id": "trade_302",
            "account_id": "paper_acc_1",
            "strategy_id": "strat_phase5",
            "source_order_id": "302",
            "stock_code": "600519",
            "trade_type": "sell",
            "quantity": 100,
            "price": 12.0,
            "amount": 1200.0,
            "commission": 1.0,
            "trade_time": "2026-04-12T09:31:00+00:00",
        }
    )

    quality = await build_execution_quality(
        db,
        {"id": "strat_phase5"},
        signal_quality={"primary_skill_lcb": 0.05, "primary_horizon": 5},
        total_signals=4,
    )

    assert quality["signal_to_fill_ratio"] == pytest.approx(0.5)
    assert quality["filled_order_ratio"] == pytest.approx(1.0)
    assert quality["audit"]["realized_trade_count"] == 1
    assert quality["execution_conversion_efficiency"] == pytest.approx(1.0)
    assert quality["audit_ready_for_hard_gate"] is False
    assert quality["audit_source_tables"] == [
        "paper_orders",
        "paper_trades",
        "strategy_trade_positions",
        "strategy_trade_position_fills",
    ]


@pytest.mark.asyncio
async def test_execution_quality_marks_bootstrap_pending_when_runtime_evidence_exists_without_realized_trades():
    db = _StrategyDB()
    await db.save_paper_account(
        {
            "id": "paper_acc_bootstrap",
            "strategy_id": "strat_bootstrap_pending",
            "initial_capital": 100000.0,
            "current_capital": 100000.0,
            "total_value": 100000.0,
        }
    )
    await db.save_paper_nav(
        {
            "account_id": "paper_acc_bootstrap",
            "nav_date": "2026-04-13",
            "total_value": 100000.0,
            "cash": 100000.0,
            "market_value": 0.0,
            "daily_return": 0.0,
        }
    )

    quality = await build_execution_quality(
        db,
        {"id": "strat_bootstrap_pending"},
        signal_quality={"primary_skill_lcb": 0.03, "primary_horizon": 5},
        total_signals=0,
    )

    assert quality["account_id"] == "paper_acc_bootstrap"
    assert quality["evidence_status"] == "ready"
    assert quality["execution_audit_gate_status"] == "bootstrap_pending"
    assert "execution_audit_bootstrap_pending" in quality["execution_audit_gate_reasons"]


@pytest.mark.asyncio
async def test_sync_signals_to_orders_raises_budget_to_minimum_lot_when_affordable():
    db = _StrategyDB()
    service = StrategyIncubationService()
    signal_date = date(2026, 4, 13)
    db.get_signals = AsyncMock(
        return_value=[
            {
                "id": "sig_bootstrap_min_lot",
                "code": "601138",
                "signal": 1,
            }
        ]
    )

    strategy = {
        "id": "strat_min_lot_affordable",
        "name": "min-lot-affordable",
        "strategy_type": "momentum",
        "target_symbols": ["601138"],
        "params": {
            "semantic_runtime_match": True,
            "execution_readiness_tier": "formal_runtime_ready",
            "instrument_profile": {
                "measurement_source": "realized_market_profile",
                "measured_profile_complete": True,
            },
            "runtime_playbook": {
                "entry_policy": {"order_style": "marketable_limit", "max_slippage_bps": 5.0},
                "position_policy": {
                    "base_budget_pct": 0.04,
                    "max_position_pct": 0.18,
                    "max_concurrent_positions": 2,
                },
                "reentry_policy": {"cooldown_days": 0},
                "exit_policy": {},
                "adverse_move_policy": {},
            }
        },
    }

    original_latest_price = service._latest_price

    async def _latest_price(_db, code: str):
        if code == "601138":
            return 56.52
        return await original_latest_price(_db, code)

    service._latest_price = _latest_price
    try:
        result = await service.sync_signals_to_orders(db, strategy, signal_date)
    finally:
        service._latest_price = original_latest_price

    orders = await db.list_strategy_paper_orders(strategy["id"], signal_date)
    assert result["created_count"] == 1
    assert orders[0]["shares"] == 100
    assert orders[0]["code"] == "601138"


@pytest.mark.asyncio
async def test_phase_5_signal_evidence_persists_one_row_per_trade_step():
    db = _StrategyDB()
    service = StrategyIncubationService()
    signal_date = date(2026, 4, 13)
    db.get_signals = AsyncMock(
        return_value=[
            {
                "id": "sig_step_lineage",
                "code": "600519",
                "signal": 1,
            }
        ]
    )

    strategy = {
        "id": "strat_phase5_step_lineage",
        "name": "phase5-step-lineage",
        "strategy_type": "event_driven",
        "target_symbols": ["600519"],
        "params": {
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev_step_lineage_1",
                        "source_type": "news",
                        "direction": "up",
                        "raw_confidence": 0.82,
                        "claim_ids": ["claim_growth"],
                        "target_symbols": ["600519"],
                    }
                ]
            },
            "claim_to_trade_plan_map": {
                "claim_to_trade_step_ids": {
                    "claim_growth": ["entry_step_1", "exit_step_reduce"],
                },
            },
            "trade_plan_to_dsl_map": {
                "trade_step_to_dsl_sections": {
                    "entry_step_1": ["entry"],
                    "exit_step_reduce": ["exit"],
                },
            },
        },
    }

    result = await service.sync_signals_to_orders(db, strategy, signal_date)
    evidence_rows = await db.list_strategy_signal_evidence(
        signal_id="sig_step_lineage",
        strategy_id=strategy["id"],
    )

    assert result["created_count"] == 1
    assert len(evidence_rows) == 2
    assert {row["applied_claim_id"] for row in evidence_rows} == {"claim_growth"}
    assert {row["applied_trade_step_id"] for row in evidence_rows} == {
        "entry_step_1",
        "exit_step_reduce",
    }
    assert all(
        row["payload"]["applied_trade_step_id"] in {"entry_step_1", "exit_step_reduce"}
        for row in evidence_rows
    )


@pytest.mark.asyncio
async def test_phase_5_runtime_lineage_and_round_trip_verification(monkeypatch):
    db = _StrategyDB()
    service = StrategyIncubationService()

    class FrozenDateTime(datetime):
        current = datetime(2026, 4, 13, 9, 35, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            value = cls.current
            if tz is not None:
                return value.astimezone(tz)
            return value

    monkeypatch.setattr(incubation_mod, "datetime", FrozenDateTime)

    current_price = {"value": 10.0}

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
        "id": "strat_phase5_runtime_lineage",
        "name": "phase5-runtime-lineage",
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "params": {
            "runtime_playbook": {
                "adverse_move_policy": {
                    "loss_bands": [
                        {"threshold_pct": 0.05, "action": "reduce", "label": "primary_reduce"},
                        {"threshold_pct": 0.10, "action": "freeze_reentry", "label": "hard_stop_band"},
                    ],
                },
                "reentry_policy": {"cooldown_days": 3},
                "position_policy": {
                    "base_budget_pct": 0.06,
                    "max_position_pct": 0.20,
                    "max_concurrent_positions": 1,
                },
                "_provenance": {
                    "source_claim_ids": ["claim_runtime"],
                    "source_trade_step_ids": ["primary_reduce_step", "hard_stop_band_step"],
                },
            },
            "claim_to_trade_plan_map": {
                "claim_to_trade_step_ids": {
                    "claim_runtime": ["entry_step_1", "primary_reduce_step", "hard_stop_band_step"],
                },
                "trade_step_to_claim_ids": {
                    "primary_reduce_step": ["claim_runtime"],
                    "hard_stop_band_step": ["claim_runtime"],
                },
            },
            "trade_plan_to_dsl_map": {
                "trade_step_to_dsl_sections": {
                    "entry_step_1": ["entry"],
                    "primary_reduce_step": ["exit"],
                    "hard_stop_band_step": ["exit"],
                },
            },
        },
    }

    daily_prices = [
        ("2026-04-13", 10.0),
        ("2026-04-14", 9.4),
        ("2026-04-15", 8.8),
        ("2026-04-16", 9.0),
        ("2026-04-17", 9.1),
        ("2026-04-18", 9.2),
        ("2026-04-19", 9.6),
    ]

    try:
        sync_results = []
        for raw_day, price in daily_prices:
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
    evidence_rows = await db.list_strategy_signal_evidence(strategy_id=strategy["id"], limit=200)
    runtime_rows = [row for row in evidence_rows if row.get("runtime_action_reason")]
    positions = await db.list_strategy_trade_positions(strategy_id=strategy["id"], limit=20)
    closed_positions = [row for row in positions if row.get("status") == "closed"]
    open_positions = [row for row in positions if row.get("status") == "open"]

    assert sync_results[0]["created_count"] == 1
    assert sync_results[1]["created_count"] == 1
    assert sync_results[2]["created_count"] == 1
    assert sync_results[3]["created_count"] == 0
    assert sync_results[4]["created_count"] == 0
    assert sync_results[5]["created_count"] == 0
    assert sync_results[6]["created_count"] == 1

    assert len(buy_orders) == 2
    assert [str(item.get("signal_date")) for item in buy_orders] == ["2026-04-13", "2026-04-19"]
    assert [str(item.get("reason") or "") for item in sell_orders] == [
        "runtime_playbook_primary_reduce",
        "runtime_playbook_hard_stop_band",
    ]

    assert {row["runtime_action_reason"] for row in runtime_rows} == {"reduce", "freeze_reentry"}
    assert {row["applied_trade_step_id"] for row in runtime_rows} == {
        "primary_reduce_step",
        "hard_stop_band_step",
    }
    assert all(
        (row.get("payload") or {}).get("lineage_status") == "mapped_runtime_action"
        for row in runtime_rows
    )

    assert len(closed_positions) == 1
    assert len(open_positions) == 1
    first_position = closed_positions[0]
    fills = await db.list_strategy_trade_position_fills(position_id=first_position["position_id"], limit=20)
    entry_fills = [item for item in fills if item.get("fill_side") == "buy"]
    exit_fills = [item for item in fills if item.get("fill_side") == "sell"]
    assert len(entry_fills) == 1
    assert len(exit_fills) == 2
    assert int(exit_fills[0]["quantity"]) < int(entry_fills[0]["quantity"])
    assert sum(int(item["quantity"]) for item in exit_fills) == int(entry_fills[0]["quantity"])

    audit_summary = await db.get_strategy_trade_audit_summary(strategy["id"])
    verification = await db.get_execution_audit_verification(strategy_id=strategy["id"])
    assert audit_summary["realized_trade_count"] == 1
    assert audit_summary["trade_expectancy"] is not None
    assert audit_summary["execution_conversion_efficiency"] == pytest.approx(1.0)
    assert verification["coverage"]["strategy_signal_step_lineage_count"] >= 2
    assert verification["coverage"]["runtime_action_signal_count"] == 2
    assert verification["lineage_source"]["status"] == "native_ready"
