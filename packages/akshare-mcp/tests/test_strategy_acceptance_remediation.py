from __future__ import annotations

import asyncio
from datetime import date

from akshare_mcp.services.incubation import _resolve_strategy_target_codes
from akshare_mcp.services.strategy_acceptance_remediation import (
    StrategyAcceptanceRemediationService,
    _build_bootstrap_lineage_fallback,
    _select_bootstrap_round_trips,
    _group_backtest_round_trips,
    build_failed_metrics_filter_patch,
    summarize_code_performance,
)


def test_resolve_strategy_target_codes_respects_excluded_symbols_and_max_active_symbols():
    strategy = {
        "params": {
            "target_symbols": ["920000", "688599", "688336"],
            "stock_pool": {
                "symbols": ["920000", "688599", "688336"],
                "filters": {
                    "excluded_symbols": ["688336"],
                    "prioritized_symbols": ["920000", "688599"],
                    "max_active_symbols": 1,
                },
            },
        }
    }

    resolved = _resolve_strategy_target_codes(strategy)

    assert resolved == {"920000"}


def test_build_failed_metrics_filter_patch_excludes_negative_codes_and_keeps_positive_core():
    strategy = {
        "id": "strategy-failed",
        "strategy_type": "margin_divergence",
        "params": {
            "target_symbols": ["920000", "688599", "688336"],
            "params": {
                "repair_rebound_pct": 0.012,
                "dryup_max_ratio": 0.9,
                "entry_volume_floor_ratio": 1.0,
                "structure_close_location_min": 0.62,
                "structure_body_return_min": 0.003,
                "max_hold_bars": 8,
                "risk_rules": {"max_holding_days": 10},
            },
            "stock_pool": {"symbols": ["920000", "688599", "688336"], "selection_mode": "explicit"},
            "runtime_playbook": {
                "entry_policy": {"signal_validity_days": 2},
                "position_policy": {"max_concurrent_positions": 3},
            },
            "research_task": {
                "target_symbols": ["920000", "688599", "688336"],
                "stock_pool": {"symbols": ["920000", "688599", "688336"], "filters": {}},
            },
        },
    }
    code_stats = [
        {"code": "920000", "trade_count": 3, "net_pnl": 237.72, "avg_return": 0.017},
        {"code": "688336", "trade_count": 2, "net_pnl": -83.01, "avg_return": -0.004},
        {"code": "688599", "trade_count": 4, "net_pnl": -309.30, "avg_return": -0.012},
    ]

    patch = build_failed_metrics_filter_patch(strategy, code_stats)

    assert patch is not None
    assert patch["kept_codes"] == ["920000"]
    assert set(patch["excluded_codes"]) == {"688336", "688599"}
    updated = patch["updated_params"]
    assert updated["target_symbols"] == ["920000"]
    assert updated["stock_pool"]["symbols"] == ["920000"]
    assert updated["stock_pool"]["filters"]["max_active_symbols"] == 1
    assert updated["stock_pool"]["filters"]["excluded_symbols"] == ["688336", "688599"]
    assert updated["runtime_playbook"]["position_policy"]["max_concurrent_positions"] == 1
    assert updated["runtime_playbook"]["entry_policy"]["signal_validity_days"] == 1
    assert updated["params"]["repair_rebound_pct"] == 0.018
    assert updated["params"]["dryup_max_ratio"] == 0.82
    assert updated["params"]["max_hold_bars"] == 4
    assert updated["params"]["risk_rules"]["max_holding_days"] == 6
    assert updated["research_task"]["target_symbols"] == ["920000"]


def test_group_backtest_round_trips_pairs_buy_and_sell_per_code():
    trades = [
        {"id": "t1", "code": "688599", "signal": 1, "time": "2024-01-02", "price": 10.0, "shares": 100},
        {"id": "t2", "code": "688303", "signal": 1, "time": "2024-01-03", "price": 20.0, "shares": 100},
        {"id": "t3", "code": "688599", "signal": -1, "time": "2024-01-04", "price": 10.8, "shares": 100},
        {"id": "t4", "code": "688303", "signal": -1, "time": "2024-01-05", "price": 19.6, "shares": 100},
    ]

    grouped = _group_backtest_round_trips(trades)

    assert len(grouped) == 2
    assert grouped[0].code == "688599"
    assert grouped[0].entry["id"] == "t1"
    assert grouped[0].exit["id"] == "t3"
    assert grouped[1].code == "688303"


def test_select_bootstrap_round_trips_prefers_positive_short_horizon_candidates():
    trades = [
        {"id": "t1", "code": "688187", "signal": 1, "time": "2022-02-24", "price": 60.0, "shares": 100},
        {"id": "t2", "code": "688187", "signal": -1, "time": "2026-04-15", "price": 50.0, "shares": 100},
        {"id": "t3", "code": "688336", "signal": 1, "time": "2024-01-02", "price": 10.0, "shares": 100},
        {"id": "t4", "code": "688336", "signal": -1, "time": "2024-01-05", "price": 11.2, "shares": 100},
        {"id": "t5", "code": "688599", "signal": 1, "time": "2024-01-03", "price": 20.0, "shares": 100},
        {"id": "t6", "code": "688599", "signal": -1, "time": "2024-01-04", "price": 19.0, "shares": 100},
    ]

    grouped = _group_backtest_round_trips(trades)
    selected, report = _select_bootstrap_round_trips(grouped, 1)

    assert len(selected) == 1
    assert selected[0].round_trip.code == "688336"
    assert selected[0].is_positive is True
    assert report["policy"] == "positive_pnl_return_short_horizon_first_v2"
    assert report["positive_candidate_count"] == 1


def test_summarize_code_performance_aggregates_closed_positions():
    positions = [
        {"code": "688599", "status": "closed", "net_pnl": 120.0, "net_return": 0.02, "hold_days": 2},
        {"code": "688599", "status": "closed", "net_pnl": -20.0, "net_return": -0.01, "hold_days": 1},
        {"code": "920000", "status": "closed", "net_pnl": 80.0, "net_return": 0.03, "hold_days": 3},
    ]

    summary = summarize_code_performance(positions)

    assert summary[0]["code"] == "688599"
    assert summary[0]["trade_count"] == 2
    assert summary[0]["wins"] == 1
    assert summary[0]["losses"] == 1
    by_code = {item["code"]: item for item in summary}
    assert by_code["920000"]["avg_return"] == 0.03


class _SignalEvidenceCaptureDb:
    def __init__(self):
        self.saved_rows: list[dict] = []

    async def save_strategy_signal_evidence(self, evidence: dict):
        payload = dict(evidence or {})
        self.saved_rows.append(payload)
        return payload


class _BootstrapMarketDataDb:
    def __init__(self):
        self.requested_codes: list[str] = []

    async def list_strategy_trade_positions(self, *, strategy_id: str, limit: int = 20):
        assert strategy_id == "strategy-runtime-fallback"
        return [
            {"code": "000333"},
            {"code": "000063"},
        ][:limit]

    async def list_strategy_paper_trades(self, strategy_id: str, limit: int = 20):
        assert strategy_id == "strategy-runtime-fallback"
        return []

    async def list_strategy_paper_orders(self, *, strategy_id: str, limit: int = 20):
        assert strategy_id == "strategy-runtime-fallback"
        return []

    async def get_klines(self, code: str, limit: int = 250):
        self.requested_codes.append(code)
        return [
            {"date": "2026-04-20", "close": 10.0},
            {"date": "2026-04-21", "close": 10.5},
        ]


def test_build_bootstrap_lineage_fallback_generates_deterministic_native_tokens():
    fallback = _build_bootstrap_lineage_fallback(
        {
            "id": "legacy-strategy",
            "strategy_type": "mean-reversion.v2",
        },
        code="688303.SH",
        phase="entry",
        action_reason="bootstrap backtest entry",
    )

    assert fallback["applied_claim_id"] == "bootstrap_entry_mean_reversion_v2_688303_sh_claim"
    assert fallback["applied_trade_step_id"] == "bootstrap_entry_mean_reversion_v2_688303_sh_step"
    assert fallback["runtime_action_reason"] == "bootstrap_backtest_entry"
    assert fallback["runtime_action_source"] == (
        "strategy_acceptance_remediation.synthetic_bootstrap_lineage"
    )


def test_save_bootstrap_signal_evidence_synthesizes_lineage_for_legacy_contract_strategy():
    service = StrategyAcceptanceRemediationService()
    db = _SignalEvidenceCaptureDb()
    strategy = {
        "id": "legacy-bootstrap",
        "strategy_type": "momentum_rotation",
        "params": {
            "target_symbols": ["688303"],
            "holding_days": 10,
        },
    }

    asyncio.run(
        service._save_bootstrap_signal_evidence(
            db,
            strategy,
            signal_id="sig-entry",
            position_id="pos-bootstrap",
            account_id="acc-bootstrap",
            signal_date=date(2026, 4, 21),
            code="688303",
            backtest_id="bt-demo",
            source_type="backtest_bootstrap_entry",
            trade_payload={"price": 18.52, "shares": 100},
            selection_payload={"policy": "bootstrap_demo"},
        )
    )
    asyncio.run(
        service._save_bootstrap_signal_evidence(
            db,
            strategy,
            signal_id="sig-exit",
            position_id="pos-bootstrap",
            account_id="acc-bootstrap",
            signal_date=date(2026, 4, 22),
            code="688303",
            backtest_id="bt-demo",
            source_type="backtest_bootstrap_exit",
            trade_payload={"price": 19.24, "shares": 100},
            action_reason="take_profit",
            selection_payload={"policy": "bootstrap_demo"},
        )
    )

    assert len(db.saved_rows) == 2
    entry_row = db.saved_rows[0]
    exit_row = db.saved_rows[1]

    assert entry_row["applied_claim_id"] == "bootstrap_entry_momentum_rotation_688303_claim"
    assert entry_row["applied_trade_step_id"] == "bootstrap_entry_momentum_rotation_688303_step"
    assert entry_row["runtime_action_reason"] == "bootstrap_backtest_entry"
    assert entry_row["payload"]["synthetic_bootstrap_lineage"] is True

    assert exit_row["applied_claim_id"] == "bootstrap_exit_momentum_rotation_688303_claim"
    assert exit_row["applied_trade_step_id"] == "bootstrap_exit_momentum_rotation_688303_step"
    assert exit_row["runtime_action_reason"] == "take_profit"
    assert exit_row["payload"]["synthetic_bootstrap_lineage"] is True


def test_load_market_data_falls_back_to_runtime_position_codes_when_targets_missing():
    service = StrategyAcceptanceRemediationService()
    db = _BootstrapMarketDataDb()

    market_data = asyncio.run(
        service._load_market_data(
            db,
            {
                "id": "strategy-runtime-fallback",
                "strategy_type": "momentum",
                "params": {"universe": "沪深300"},
            },
        )
    )

    assert sorted(market_data.keys()) == ["000063", "000333"]
    assert db.requested_codes == ["000333", "000063"]
