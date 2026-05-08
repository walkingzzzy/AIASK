from __future__ import annotations

import asyncio

from strategy_factory.application._submitter_actions import (
    _build_risk_report_fallback,
    _build_validation_report_fallback,
)
from strategy_factory.application.backtest_filter import BacktestFilter
from strategy_factory.application.deduplicator import Deduplicator
from strategy_factory.application.quality_gates import gate_0_structural, pre_gate_screen
from strategy_factory.application.quality_reporting import build_quality_report
from strategy_factory.application.submission_gate import run_submission_quality_gate
from strategy_factory.domain.spawner import StrategySpawner
from strategy_factory.domain.strategy_identity import has_executable_params, materialize_strategy_params


class EmptyDB:
    async def list_strategies(self, status=None, limit=500):
        return []

    async def get_klines(self, code, limit=500):
        return []


STRATEGY_TYPES_WITH_CORE_PARAMS = [
    "momentum",
    "ma_cross",
    "rsi",
    "value_factor",
    "quality_factor",
    "growth_factor",
    "multi_factor",
    "macro_timing",
    "volatility_breakout",
    "event_structure_breakout",
    "gap_fill",
    "mean_reversion_short",
    "sector_rotation",
    "north_capital_track",
    "margin_divergence",
    "topn_equity_portfolio",
]


def test_materialized_params_are_executable_hashable_stable_and_slot_distinct():
    seed_context = {"snapshot_date": "2026-05-05", "source": "unit"}
    targets = ["600000", "600519", "000001"]

    for strategy_type in STRATEGY_TYPES_WITH_CORE_PARAMS:
        params_0 = materialize_strategy_params(strategy_type, {}, seed_context=seed_context, slot_index=0, targets=targets)
        params_0_repeat = materialize_strategy_params(strategy_type, {}, seed_context=seed_context, slot_index=0, targets=targets)
        params_1 = materialize_strategy_params(strategy_type, {}, seed_context=seed_context, slot_index=1, targets=targets)

        assert has_executable_params(strategy_type, params_0), strategy_type
        assert params_0["strategy_instance_hash"] == params_0_repeat["strategy_instance_hash"]
        assert params_0["candidate_contract_hash"] == params_0["strategy_instance_hash"]
        assert params_0["tested_object_hash"]
        assert params_0["param_materialization_version"]
        assert params_0["signal_rule"]
        assert params_0["strategy_instance_hash"] != params_1["strategy_instance_hash"]


def test_materialized_momentum_aliases_follow_explicit_inputs():
    params = materialize_strategy_params(
        "momentum",
        {"lookback": 42, "threshold": 0.01},
        seed_context={"snapshot_date": "2026-05-05", "source": "unit"},
        slot_index=0,
        targets=["600000"],
    )

    assert params["lookback"] == 42
    assert params["lookback_days"] == 42
    assert params["threshold"] == 0.01
    assert params["threshold_pct"] == 0.01
    assert "42" in params["signal_rule"]
    assert "0.01" in params["signal_rule"]


def test_generated_template_params_are_slot_distinct_and_refresh_signal_rule():
    seed_context = {"snapshot_date": "2026-05-05", "source": "autonomy_candidate_generation"}
    targets = ["600905", "600930", "601985"]
    base = {"lookback": 12, "rebound_window": 3, "repair_rebound_pct": 0.012, "signal_rule": "stale_rule"}

    first = materialize_strategy_params(
        "margin_divergence",
        base,
        seed_context=seed_context,
        slot_index=0,
        targets=targets,
        variant_existing=True,
        refresh_signal_rule=True,
    )
    second = materialize_strategy_params(
        "margin_divergence",
        base,
        seed_context=seed_context,
        slot_index=1,
        targets=targets,
        variant_existing=True,
        refresh_signal_rule=True,
    )

    assert first["strategy_instance_hash"] != second["strategy_instance_hash"]
    assert first["signal_rule"] != "stale_rule"
    assert str(first["lookback"]) in first["signal_rule"]
    assert str(second["rebound_window"]) in second["signal_rule"]


def test_generated_mean_reversion_materialization_stays_inside_signal_density_gate():
    params = materialize_strategy_params(
        "mean_reversion_short",
        {"rsi_period": 3, "oversold": 21, "overbought": 62, "signal_rule": "stale_rule"},
        seed_context={"snapshot_date": "2026-05-05", "source": "autonomy_candidate_generation"},
        slot_index=0,
        targets=["601988"],
        variant_existing=True,
        refresh_signal_rule=True,
    )
    candidate = {
        "strategy_type": "mean_reversion_short",
        "params": params,
        "target_symbols": ["601988"],
        "research_task": {"task_source": "bulk_stock_matrix", "target_symbols": ["601988"]},
    }

    result = pre_gate_screen(candidate, seen_signatures=set(), family_counts={}, stock_counts={})

    assert params["rsi_period"] >= 4
    assert "signal_density_too_dense" not in result.reasons


def test_spawner_materializes_params_and_hits_multi_type_coverage_across_regimes():
    snapshots = [
        {"date": "2026-05-05", "fear_greed_index": 50, "fg_components": {"volatility": 50}, "north_fund_3d_net": 0, "margin_5d_change_pct": 0},
        {"date": "2026-05-05", "fear_greed_index": 25, "fg_components": {"volatility": 75}, "north_fund_3d_net": -6_000_000_000, "margin_5d_change_pct": -3},
        {"date": "2026-05-05", "fear_greed_index": 75, "fg_components": {"volatility": 45}, "north_fund_3d_net": 6_000_000_000, "margin_5d_change_pct": 3},
    ]

    for snapshot in snapshots:
        spawner = StrategySpawner()
        candidates = spawner.spawn(snapshot)
        summary = spawner.get_last_report()["summary"]

        assert candidates
        assert summary["empty_param_candidate_count"] == 0
        assert summary["materialized_param_candidate_count"] == len(candidates)
        assert summary["strategy_type_coverage_count"] >= 12
        assert summary["coverage_target_met"] is True
        assert summary["single_type_dominance_ratio"] < 0.5
        assert all(has_executable_params(item["strategy_type"], item.get("params")) for item in candidates)


def test_gate0_blocks_empty_executable_params_before_backtest():
    result = gate_0_structural({"strategy_type": "momentum", "params": {}})

    assert result.passed is False
    assert any(reason.startswith("missing_executable_params") for reason in result.reasons)


def test_structural_dedup_handles_intra_batch_hash_without_pgvector():
    async def run():
        candidate_a = {
            "strategy_type": "momentum",
            "params": {"lookback": 10, "threshold": 0.02, "signal_rule": "close breakout"},
            "target_symbols": ["600000"],
        }
        candidate_b = {
            "strategy_type": "momentum",
            "params": {"lookback": 10, "threshold": 0.02, "signal_rule": "close breakout"},
            "target_symbols": ["600000"],
        }
        kept = await Deduplicator(vector_gateway=None).deduplicate([candidate_a, candidate_b], EmptyDB())
        dropped_detail = candidate_b["dedup_result"]

        assert len(kept) == 1
        assert dropped_detail["duplicate_level"] == "intra_batch_hash"
        assert dropped_detail["fallback_dedup_mode"] == "structural_hash"

    asyncio.run(run())


def test_backtest_shared_result_key_isolated_by_params_and_targets():
    backtest_filter = BacktestFilter()
    base = {"strategy_type": "momentum", "name": "same", "params": {"lookback": 10, "threshold": 0.02}, "target_symbols": ["600000"]}
    different_params = {"strategy_type": "momentum", "name": "same", "params": {"lookback": 20, "threshold": 0.02}, "target_symbols": ["600000"]}
    different_targets = {"strategy_type": "momentum", "name": "same", "params": {"lookback": 10, "threshold": 0.02}, "target_symbols": ["600519"]}

    assert backtest_filter._build_shared_result_key(base) != backtest_filter._build_shared_result_key(different_params)
    assert backtest_filter._build_shared_result_key(base) != backtest_filter._build_shared_result_key(different_targets)
    assert base["params"]["strategy_instance_hash"]
    assert base["params"]["tested_object_hash"]


def test_fallback_risk_validation_reports_are_diagnostic_and_block_live_gate():
    async def run():
        candidate = {
            "strategy_type": "momentum",
            "params": {"lookback": 10, "threshold": 0.02, "signal_rule": "close breakout"},
        }
        metrics = {"sharpe_ratio": 1.1, "total_return": 0.22, "max_drawdown": 0.05, "trade_count": 30, "trades_count": 30}
        validation_report = _build_validation_report_fallback(candidate, metrics, reason="unit_empty_validation")
        risk_report = _build_risk_report_fallback(candidate, metrics, reason="unit_empty_risk")

        gate = await run_submission_quality_gate(
            EmptyDB(),
            candidate,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics=metrics,
        )
        live_reasons = gate.get("admission_evaluations", {}).get("live", {}).get("reasons") or []

        assert validation_report["diagnostic_only"] is True
        assert risk_report["report_degraded"] is True
        assert gate["live_candidate_ready"] is False
        assert "formal_risk_validation_evidence_missing" in live_reasons

        quality_report = build_quality_report(
            strategy_id="unit_strategy",
            strategy_type="momentum",
            quality_gate=gate,
            validation_report=validation_report,
            risk_report=risk_report,
            dedup_report={},
            backtest_metrics=metrics,
            snapshot={},
            status_after_review="submitted",
            review_source="unit",
            report_type="submission",
        )
        summary = quality_report["summary"]
        assert summary["validation_report_available"] is True
        assert summary["risk_report_available"] is True
        assert summary["validation_evidence_mode"] == "backtest_derived_fallback"
        assert summary["risk_evidence_mode"] == "backtest_derived_fallback"
        assert "unit_empty_validation" in summary["report_degraded_reasons"]
        assert "unit_empty_risk" in summary["report_degraded_reasons"]

    asyncio.run(run())
