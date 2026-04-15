from __future__ import annotations

from datetime import date, timedelta

import pytest

from akshare_mcp.services import strategy_lifecycle_shared as lifecycle_mod
from akshare_mcp.services.strategy_lifecycle_shared import (
    build_incubation_overview,
    evaluate_confidence_contract,
)
from akshare_mcp.services.strategy_spec import StrategySpec
from akshare_mcp.tools.managers.strategy_mgr_helpers import build_factory_quality_baseline

from ._strategy_factory_test_support import _StrategyDB


@pytest.mark.asyncio
async def test_factory_quality_baseline_does_not_treat_missing_forward_returns_as_zero_signal():
    db = _StrategyDB()
    strategy = {
        "id": "factory_raw_only",
        "name": "Raw Signal Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "momentum",
        "status": "submitted",
        "tags": ["factory", "auto_generated"],
        "params": {"lookback": 20},
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics("factory_raw_only", "all", {"sharpe_ratio": 0.8, "max_drawdown": 0.12})
    await db.save_strategy_quality_report(
        "factory_raw_only",
        "submission",
        {
            "passed": False,
            "summary": {
                "validation_grade": "C",
                "raw_validation_grade": "C",
                "effective_validation_grade": "C",
                "raw_validation_total_score": 58.0,
                "validation_total_score": 58.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    db._signal_stats["factory_raw_only"] = {
        "hit_rate": {},
        "forward_ic": {},
        "forward_sharpe": {},
        "total_signals": 12,
        "raw_signal_count": 12,
        "signals_with_forward_returns_count": 0,
        "observed_forward_return_count": 0,
    }

    overview = await build_incubation_overview(db, strategy)
    baseline = await build_factory_quality_baseline(db)
    cohort = baseline["submitted_strategy_cohort"]

    assert overview["total_signals"] == 12
    assert overview["raw_signal_count"] == 12
    assert overview["signals_with_forward_returns_count"] == 0
    assert overview["observed_forward_return_count"] == 0
    assert overview["missing_forward_days"] == [1, 5, 10, 20]
    assert cohort["zero_signal_count"] == 0
    assert cohort["forward_coverage_count"] == 0
    assert cohort["zero_signal_definition"] == "raw_signal_count <= 0"


@pytest.mark.asyncio
async def test_incubation_overview_keeps_warmup_execution_gap_and_slight_mdd_as_risk_flags():
    db = _StrategyDB()
    strategy = {
        "id": "factory_warmup_observe_band",
        "name": "Warmup Observe Band Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "momentum",
        "status": "incubating",
        "tags": ["factory", "auto_generated"],
        "params": {"lookback": 20},
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics(
        "factory_warmup_observe_band",
        "all",
        {"sharpe_ratio": 0.92, "max_drawdown": 0.204},
    )
    await db.save_strategy_quality_report(
        "factory_warmup_observe_band",
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "A",
                "raw_validation_grade": "A",
                "effective_validation_grade": "A",
                "raw_validation_total_score": 74.0,
                "validation_total_score": 74.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
                "strict_incubation_ready": True,
                "incubation_candidate_ready": True,
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    db._signal_stats["factory_warmup_observe_band"] = {
        "hit_rate": {1: 0.58, 5: 0.61, 10: 0.59, 20: 0.57},
        "hit_rate_lcb": {1: 0.53, 5: 0.56, 10: 0.53, 20: 0.50},
        "skill_lcb": {1: 0.03, 5: 0.06, 10: 0.04, 20: 0.02},
        "recent_hit_rate": {1: 0.57, 5: 0.60, 10: 0.58, 20: 0.56},
        "recent_skill_lcb": {1: 0.02, 5: 0.05, 10: 0.03, 20: 0.01},
        "stability_gap": {1: 0.01, 5: 0.01, 10: 0.01, 20: 0.01},
        "sample_count": {1: 9, 5: 9, 10: 9, 20: 9},
        "effective_n": {1: 9, 5: 3, 10: 3, 20: 2},
        "forward_ic": {1: 0.02, 5: 0.05, 10: 0.03, 20: 0.01},
        "forward_sharpe": {1: 0.10, 5: 0.28, 10: 0.16, 20: 0.08},
        "total_signals": 9,
        "raw_signal_count": 9,
        "signals_with_forward_returns_count": 9,
        "observed_forward_return_count": 36,
    }

    overview = await build_incubation_overview(db, strategy)

    assert overview["signal_stage_without_execution_gate"] == "warmup"
    assert overview["pipeline_stage"] == "warmup"
    assert overview["execution_audit_gate_status"] == "missing"
    assert "execution_audit_gate:missing" not in overview["blockers"]
    assert "execution_audit_gate:missing" in overview["risk_flags"]
    assert not any("最大回撤" in blocker for blocker in overview["blockers"])
    assert any("最大回撤" in flag for flag in overview["risk_flags"])


@pytest.mark.asyncio
async def test_incubation_overview_surfaces_confidence_diagnostics_without_changing_legacy_fields(monkeypatch):
    monkeypatch.setattr(lifecycle_mod, "STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED", True)
    db = _StrategyDB()
    strategy = {
        "id": "factory_confidence_contract",
        "name": "Confidence Contract Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "momentum",
        "status": "incubating",
        "tags": ["factory", "auto_generated"],
        "params": {
            "lookback": 20,
            "confidence_contract": {
                "prediction_quality": {
                    "sample_size": 18,
                    "ece": 0.07,
                    "brier_score": 0.19,
                    "calibration_gap": 0.05,
                    "quality": "medium",
                },
                "prediction_interval": {
                    "coverage_proxy": 0.78,
                    "observed_coverage": 0.74,
                    "coverage_gap": -0.04,
                },
            },
        },
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics("factory_confidence_contract", "all", {"sharpe_ratio": 0.9, "max_drawdown": 0.1})
    await db.save_strategy_quality_report(
        "factory_confidence_contract",
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 68.0,
                "validation_total_score": 68.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    db._signal_stats["factory_confidence_contract"] = {
        "hit_rate": {1: 0.55, 5: 0.58, 10: 0.56, 20: 0.53},
        "hit_rate_lcb": {1: 0.51, 5: 0.54, 10: 0.51, 20: 0.48},
        "skill_lcb": {1: 0.01, 5: 0.04, 10: 0.02, 20: 0.01},
        "recent_hit_rate": {1: 0.54, 5: 0.57, 10: 0.55, 20: 0.52},
        "recent_skill_lcb": {1: 0.0, 5: 0.03, 10: 0.01, 20: 0.0},
        "stability_gap": {1: 0.01, 5: 0.01, 10: 0.01, 20: 0.01},
        "sample_count": {1: 40, 5: 40, 10: 32, 20: 28},
        "effective_n": {1: 40, 5: 20, 10: 16, 20: 14},
        "forward_ic": {1: 0.01, 5: 0.04, 10: 0.03, 20: 0.02},
        "forward_sharpe": {1: 0.08, 5: 0.26, 10: 0.14, 20: 0.09},
        "total_signals": 40,
        "raw_signal_count": 40,
        "signals_with_forward_returns_count": 40,
        "observed_forward_return_count": 160,
    }

    overview = await build_incubation_overview(db, strategy)

    assert overview["validation_grade"] == "B"
    assert overview["signal_quality"]["primary_effective_n"] == 20
    assert overview["prediction_quality_label"] in {"mixed", "strong", "insufficient_evidence"}
    assert overview["confidence_contract_status"] == "insufficient"
    assert overview["confidence_diagnostics"]["ece"] == pytest.approx(0.07)
    assert overview["confidence_diagnostics"]["brier_score"] == pytest.approx(0.19)
    assert overview["confidence_diagnostics"]["prediction_interval"]["coverage_proxy"] == pytest.approx(0.78)
    assert overview["confidence_diagnostics"]["diagnostic_only"] is True


@pytest.mark.parametrize(
    ("support_samples", "contract_version", "expected_status"),
    [
        (49, "p2-stable/v1", "insufficient"),
        (50, None, "diagnostic_ready"),
        (99, "draft/v1", "diagnostic_ready"),
        (100, "p2-stable/v1", "comparable_ready"),
    ],
)
def test_evaluate_confidence_contract_uses_fixed_support_sample_bands(
    support_samples: int,
    contract_version: str | None,
    expected_status: str,
):
    status, diagnostics = evaluate_confidence_contract(
        {
            "prediction_quality": {
                "support_samples": support_samples,
                "ece": 0.04,
                "brier_score": 0.17,
            },
            "prediction_interval": {
                "observed_coverage": 0.81,
            },
            "contract_version": contract_version,
        }
    )

    assert status == expected_status
    assert diagnostics["status"] == expected_status
    assert diagnostics["support_samples"] == support_samples
    assert diagnostics["diagnostic_only"] is (expected_status != "comparable_ready")


def test_strategy_spec_emits_runtime_playbook_defaults():
    candidate = StrategySpec(
        strategy_type="momentum",
        params={"lookback": 20, "threshold": 0.02},
        name="runtime-playbook-candidate",
    ).to_candidate(source="unit_test", experiment_id="exp_runtime_pb")

    runtime_playbook = dict(candidate.get("runtime_playbook") or {})
    assert runtime_playbook["entry_policy"]["order_style"] == "marketable_limit"
    assert runtime_playbook["adverse_move_policy"]["average_down"] == "forbid"
    assert runtime_playbook["exit_policy"]["failure_exit_rule"] == "opposite_signal_or_breakout_failure"
    assert candidate["params"]["runtime_playbook"]["incubation_policy"]["warmup_hard_timeout_days"] == 20
    assert candidate["params"]["runtime_playbook"]["derived_from_defaults"] is True
    assert candidate["params"]["runtime_playbook"]["source_trade_step_ids"] == ["entry_step_1", "exit_step_1"]


@pytest.mark.asyncio
async def test_incubation_overview_prefers_latest_signal_snapshot_over_today_zero_signal():
    db = _StrategyDB()
    strategy_id = "factory_recent_exit_snapshot"
    strategy = {
        "id": strategy_id,
        "name": "Recent Exit Snapshot Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "momentum",
        "status": "incubating",
        "target_symbols": ["300750"],
        "tags": ["factory", "auto_generated"],
        "params": {
            "lookback": 20,
            "semantic_runtime_match": True,
            "execution_readiness_tier": "formal_runtime_ready",
            "instrument_profile": {
                "measurement_source": "realized_market_profile",
                "measured_profile_complete": True,
            },
            "evidence_chain": {
                "claims": [{"claim_id": "claim_1", "statement": "trend persistence", "evidence_ids": ["ev_1"]}],
                "evidences": [{"evidence_id": "ev_1", "source_type": "market_data"}],
            },
            "prediction_contract": {"primary_horizon_days": 5, "target": "forward_return_positive"},
            "confidence_contract": {"prediction_quality": {"support_samples": 50, "ece": 0.05, "brier_score": 0.18}},
        },
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics(strategy_id, "all", {"sharpe_ratio": 0.88, "max_drawdown": 0.12})
    await db.save_strategy_quality_report(
        strategy_id,
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 68.0,
                "validation_total_score": 68.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    db._signal_stats[strategy_id] = {
        "hit_rate": {1: 0.55, 5: 0.58, 10: 0.56, 20: 0.53},
        "hit_rate_lcb": {1: 0.51, 5: 0.54, 10: 0.51, 20: 0.48},
        "skill_lcb": {1: 0.01, 5: 0.04, 10: 0.02, 20: 0.01},
        "recent_hit_rate": {1: 0.54, 5: 0.57, 10: 0.55, 20: 0.52},
        "recent_skill_lcb": {1: 0.0, 5: 0.03, 10: 0.01, 20: 0.0},
        "stability_gap": {1: 0.01, 5: 0.01, 10: 0.01, 20: 0.01},
        "sample_count": {1: 40, 5: 40, 10: 32, 20: 28},
        "effective_n": {1: 40, 5: 20, 10: 16, 20: 14},
        "forward_ic": {1: 0.01, 5: 0.04, 10: 0.03, 20: 0.02},
        "forward_sharpe": {1: 0.08, 5: 0.26, 10: 0.14, 20: 0.09},
        "total_signals": 40,
        "raw_signal_count": 40,
        "signals_with_forward_returns_count": 40,
        "observed_forward_return_count": 160,
    }
    today = date.today()
    exit_date = today - timedelta(days=1)
    await db.save_strategy_signal_event_snapshot(
        {
            "strategy_id": strategy_id,
            "code": "300750",
            "as_of_date": today.isoformat(),
            "latest_bar_date": today.isoformat(),
            "latest_bar_signal": 0,
            "execution_semantic_mode": "compiled_dsl",
            "latest_event_index": 7,
            "latest_event_date": exit_date.isoformat(),
            "latest_event_signal": -1,
            "latest_event_action": "exit",
            "latest_event_action_source": "runtime_playbook_stop",
            "latest_event_reason": "trailing_stop",
            "event_count": 7,
            "recent_events": [
                {
                    "bar_date": exit_date.isoformat(),
                    "signal": -1,
                    "action": "exit",
                    "action_source": "runtime_playbook_stop",
                    "reason": "trailing_stop",
                }
            ],
            "metadata": {
                "latest_nonzero_signal_date": exit_date.isoformat(),
                "runtime_cycle_seen_today": True,
            },
        }
    )

    overview = await build_incubation_overview(db, strategy)

    assert overview["latest_bar_signal"] == 0
    assert overview["latest_event_action"] == "exit"
    assert overview["latest_event_date"] == exit_date.isoformat()
    assert overview["latest_nonzero_signal_date"] == exit_date.isoformat()
    assert overview["latest_event_action_source"] == "runtime_playbook_stop"
    assert overview["recent_events"]
    assert overview["runtime_cycle_seen_today"] is True


def test_strategy_spec_builds_compiled_dsl_and_vol_calibrated_playbook_for_single_name_ma_cross():
    high_vol_candidate = StrategySpec(
        strategy_type="ma_cross",
        params={
            "short_period": 5,
            "long_period": 20,
            "target_symbols": ["688981"],
            "evidence_chain": {
                "claims": [{"claim_id": "claim_1", "statement": "trend persistence", "evidence_ids": ["ev_1"]}],
                "evidences": [{"evidence_id": "ev_1", "source_type": "market_data"}],
            },
            "prediction_contract": {"primary_horizon_days": 5, "target": "forward_return_positive"},
            "confidence_contract": {"prediction_quality": {"support_samples": 50, "ece": 0.05, "brier_score": 0.18}},
            "instrument_profile": {
                "annual_volatility": 0.47,
                "atr14_pct": 0.044,
                "gap_p95": 0.051,
                "intraday_range_p90": 0.0682,
                "trend_efficiency_60d": 0.24,
                "turnover_median": 1.8,
                "volume_ratio_p80": 1.42,
                "volume_ratio_p90": 1.78,
                "turnover_rate_p80": 2.35,
                "turnover_rate_p90": 2.91,
                "board_bucket": "star",
            },
        },
        name="compiled-ma-cross-high-vol",
    ).to_candidate(source="unit_test", experiment_id="exp_dsl_ma_cross_high")
    low_vol_candidate = StrategySpec(
        strategy_type="ma_cross",
        params={
            "short_period": 5,
            "long_period": 20,
            "target_symbols": ["600938"],
            "evidence_chain": {
                "claims": [{"claim_id": "claim_1", "statement": "trend persistence", "evidence_ids": ["ev_1"]}],
                "evidences": [{"evidence_id": "ev_1", "source_type": "market_data"}],
            },
            "prediction_contract": {"primary_horizon_days": 5, "target": "forward_return_positive"},
            "confidence_contract": {"prediction_quality": {"support_samples": 50, "ece": 0.05, "brier_score": 0.18}},
            "instrument_profile": {
                "annual_volatility": 0.24,
                "atr14_pct": 0.018,
                "gap_p95": 0.020,
                "intraday_range_p90": 0.028,
                "trend_efficiency_60d": 0.42,
                "turnover_median": 0.9,
                "volume_ratio_p80": 1.08,
                "volume_ratio_p90": 1.21,
                "turnover_rate_p80": 0.82,
                "turnover_rate_p90": 0.96,
                "board_bucket": "main_board",
            },
        },
        name="compiled-ma-cross-low-vol",
    ).to_candidate(source="unit_test", experiment_id="exp_dsl_ma_cross_low")

    high_params = dict(high_vol_candidate.get("params") or {})
    low_params = dict(low_vol_candidate.get("params") or {})

    assert high_params["dsl_required"] is True
    assert high_params["dsl_compiled"] is True
    assert high_params["execution_semantic_mode"] == "compiled_dsl"
    assert high_params["execution_semantic_gap"] is False
    assert high_params["trade_plan_to_dsl_map"]["mapped_trade_step_count"] >= 2
    assert high_params["dsl"]["metadata"]["instrument_profile"]["board_bucket"] == "star"
    assert high_params["instrument_profile"]["measurement_source"] == "measured"
    assert high_params["instrument_profile"]["annual_volatility_realized_252d"] == pytest.approx(0.47)
    assert high_params["runtime_playbook"]["cooldown_by_exit_reason"]["gap_through_stop"] >= high_params["runtime_playbook"]["reentry_policy"]["cooldown_days"]
    assert high_params["runtime_playbook"]["stop_execution_mode"] == "gap_aware_ohlc"
    assert high_params["regime_filter_contract"]["quantified"] is True
    assert high_params["drawdown_invalidation_contract"]["apply_as_hard_gate"] is True
    assert high_params["parameter_coherence_audit"]["status"] in {"passed", "passed_with_warnings"}
    assert high_params["runtime_playbook"]["exit_policy"]["initial_stop_loss_pct"] > low_params["runtime_playbook"]["exit_policy"]["initial_stop_loss_pct"]
    assert high_params["runtime_playbook"]["exit_policy"]["trailing_stop_pct"] > low_params["runtime_playbook"]["exit_policy"]["trailing_stop_pct"]
    assert 4 <= high_params["runtime_playbook"]["incubation_policy"]["warmup_target_signals"] <= 8
    assert "default_runtime_playbook" in high_params["runtime_playbook"]["derivation_labels"]


@pytest.mark.asyncio
async def test_incubation_overview_surfaces_signal_vacuum_remediation_plan():
    db = _StrategyDB()
    strategy = {
        "id": "factory_signal_vacuum_timeout",
        "name": "Signal Vacuum Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "momentum",
        "status": "submitted",
        "tags": ["factory", "auto_generated"],
        "params": {
            "lookback": 20,
            "runtime_playbook": {
                "entry_policy": {"order_style": "marketable_limit"},
                "incubation_policy": {"warmup_soft_timeout_days": 5, "warmup_hard_timeout_days": 20, "warmup_max_days": 30},
            },
        },
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics("factory_signal_vacuum_timeout", "all", {"sharpe_ratio": 0.6, "max_drawdown": 0.08})
    await db.save_strategy_quality_report(
        "factory_signal_vacuum_timeout",
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
                "runtime_bootstrap_eligible": True,
                "runtime_bootstrap_budget_tier": "standard",
                "runtime_playbook_present": True,
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    await db.save_strategy_incubation_metric(
        "factory_signal_vacuum_timeout",
        "2026-03-01",
        {"recent_primary_skill_lcb": None, "total_signals": 0},
    )
    await db.save_strategy_incubation_metric(
        "factory_signal_vacuum_timeout",
        "2026-03-26",
        {"recent_primary_skill_lcb": None, "total_signals": 0},
    )
    db._signal_stats["factory_signal_vacuum_timeout"] = {
        "hit_rate": {},
        "forward_ic": {},
        "forward_sharpe": {},
        "total_signals": 0,
        "raw_signal_count": 0,
        "signals_with_forward_returns_count": 0,
        "observed_forward_return_count": 0,
    }

    overview = await build_incubation_overview(db, strategy)

    assert overview["pipeline_stage"] == "warmup"
    assert overview["runtime_bootstrap_eligible"] is True
    assert overview["runtime_playbook_present"] is True
    assert overview["signal_vacuum_days"] == 25
    assert overview["remediation_action"] == "freeze_and_revise"
    assert overview["remediation_reason"] == "signal_vacuum"
    assert overview["budget_action"] == "freeze_new_budget"
    assert overview["revision_required"] is True
    assert overview["hard_gate_result"]["pipeline_stage"] == "warmup"
    assert overview["hard_gate_result"]["execution_audit_gate_status"] == "missing"


@pytest.mark.asyncio
async def test_incubation_overview_exposes_risk_hard_gate_from_drawdown_contract():
    db = _StrategyDB()
    strategy = {
        "id": "factory_risk_hard_gate_review",
        "name": "Risk Hard Gate Review Strategy",
        "author_id": "strategy_factory",
        "strategy_type": "ma_cross",
        "status": "incubating",
        "tags": ["factory", "auto_generated"],
        "params": {
            "drawdown_invalidation_contract": {
                "review_drawdown_pct": 0.18,
                "kill_drawdown_pct": 0.26,
                "apply_as_hard_gate": True,
            },
            "parameter_coherence_audit": {"status": "passed", "blockers": [], "warnings": []},
        },
    }
    await db.save_strategy(strategy)
    await db.save_strategy_metrics(
        "factory_risk_hard_gate_review",
        "all",
        {"sharpe_ratio": 1.05, "max_drawdown": 0.21},
    )
    await db.save_strategy_quality_report(
        "factory_risk_hard_gate_review",
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "A",
                "raw_validation_grade": "A",
                "effective_validation_grade": "A",
                "raw_validation_total_score": 76.0,
                "validation_total_score": 76.0,
                "candidate_family": "ma_cross",
                "holding_period_bucket": "swing",
            },
            "validation_profile": {"validation_focus": "target_only"},
        },
    )
    db._signal_stats["factory_risk_hard_gate_review"] = {
        "hit_rate": {1: 0.58, 5: 0.61, 10: 0.59, 20: 0.57},
        "hit_rate_lcb": {1: 0.53, 5: 0.56, 10: 0.53, 20: 0.50},
        "skill_lcb": {1: 0.03, 5: 0.06, 10: 0.04, 20: 0.02},
        "recent_hit_rate": {1: 0.57, 5: 0.60, 10: 0.58, 20: 0.56},
        "recent_skill_lcb": {1: 0.02, 5: 0.05, 10: 0.03, 20: 0.01},
        "stability_gap": {1: 0.01, 5: 0.01, 10: 0.01, 20: 0.01},
        "sample_count": {1: 60, 5: 60, 10: 48, 20: 40},
        "effective_n": {1: 60, 5: 30, 10: 24, 20: 20},
        "forward_ic": {1: 0.02, 5: 0.05, 10: 0.03, 20: 0.01},
        "forward_sharpe": {1: 0.10, 5: 0.28, 10: 0.16, 20: 0.08},
        "total_signals": 60,
        "raw_signal_count": 60,
        "signals_with_forward_returns_count": 60,
        "observed_forward_return_count": 240,
    }

    overview = await build_incubation_overview(db, strategy)

    assert overview["risk_hard_gate_status"] == "forced_review"
    assert "max_drawdown>=18%" in overview["risk_hard_gate_reasons"]
    assert overview["hard_gate_result"]["risk_hard_gate_status"] == "forced_review"
    assert overview["hard_gate_result"]["passed"] is False


@pytest.mark.asyncio
async def test_factory_quality_baseline_surfaces_high_confidence_distributions_for_cohort(monkeypatch):
    monkeypatch.setattr(lifecycle_mod, "STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED", True)
    db = _StrategyDB()
    strategies = [
        {
            "id": "hc_strong",
            "name": "HC Strong",
            "author_id": "strategy_factory",
            "strategy_type": "momentum",
            "status": "listed",
            "tags": ["factory", "auto_generated"],
            "params": {
                "holding_period_bucket": "swing",
                "confidence_contract": {
                    "prediction_quality": {
                        "support_samples": 120,
                        "ece": 0.03,
                    },
                    "prediction_interval": {
                        "observed_coverage": 0.81,
                    },
                    "contract_version": "p2-stable/v1",
                },
                "evidence_alignment_audit": {
                    "evidence_alignment_status": "aligned",
                },
            },
        },
        {
            "id": "hc_mixed",
            "name": "HC Mixed",
            "author_id": "strategy_factory",
            "strategy_type": "mean_reversion",
            "status": "incubating",
            "tags": ["factory", "auto_generated"],
            "params": {
                "holding_period_bucket": "swing",
                "confidence_contract": {
                    "prediction_quality": {
                        "support_samples": 50,
                        "ece": 0.08,
                    },
                },
                "evidence_alignment_audit": {
                    "evidence_alignment_status": "legacy",
                },
            },
        },
    ]
    for strategy in strategies:
        await db.save_strategy(strategy)

    await db.save_strategy_metrics("hc_strong", "all", {"sharpe_ratio": 1.1, "max_drawdown": 0.08})
    await db.save_strategy_metrics("hc_mixed", "all", {"sharpe_ratio": 0.7, "max_drawdown": 0.12})
    await db.save_strategy_quality_report(
        "hc_strong",
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "A",
                "raw_validation_grade": "A",
                "effective_validation_grade": "A",
                "raw_validation_total_score": 82.0,
                "candidate_family": "momentum",
                "holding_period_bucket": "swing",
            },
        },
    )
    await db.save_strategy_quality_report(
        "hc_mixed",
        "submission",
        {
            "passed": True,
            "summary": {
                "validation_grade": "B",
                "raw_validation_grade": "B",
                "effective_validation_grade": "B",
                "raw_validation_total_score": 71.0,
                "candidate_family": "mean_reversion",
                "holding_period_bucket": "swing",
            },
        },
    )

    db._signal_stats["hc_strong"] = {
        "hit_rate": {1: 0.62, 5: 0.63, 10: 0.61, 20: 0.6},
        "hit_rate_lcb": {1: 0.57, 5: 0.58, 10: 0.56, 20: 0.55},
        "skill_lcb": {1: 0.05, 5: 0.08, 10: 0.06, 20: 0.04},
        "recent_hit_rate": {1: 0.61, 5: 0.62, 10: 0.6, 20: 0.59},
        "recent_skill_lcb": {1: 0.03, 5: 0.05, 10: 0.03, 20: 0.02},
        "stability_gap": {1: 0.02, 5: 0.02, 10: 0.02, 20: 0.02},
        "sample_count": {1: 120, 5: 120, 10: 90, 20: 70},
        "effective_n": {1: 120, 5: 70, 10: 48, 20: 36},
        "forward_ic": {1: 0.05, 5: 0.07, 10: 0.05, 20: 0.04},
        "forward_sharpe": {1: 0.36, 5: 0.42, 10: 0.35, 20: 0.28},
        "total_signals": 80,
        "raw_signal_count": 80,
        "signals_with_forward_returns_count": 80,
        "observed_forward_return_count": 160,
    }
    db._signal_stats["hc_mixed"] = {
        "hit_rate": {1: 0.53, 5: 0.56},
        "hit_rate_lcb": {1: 0.51, 5: 0.52},
        "skill_lcb": {1: 0.01, 5: 0.02},
        "recent_hit_rate": {1: 0.52, 5: 0.55},
        "recent_skill_lcb": {1: 0.0, 5: 0.0},
        "stability_gap": {1: 0.03, 5: 0.04},
        "sample_count": {1: 40, 5: 40},
        "effective_n": {1: 40, 5: 24},
        "forward_ic": {1: 0.01, 5: 0.02},
        "forward_sharpe": {1: 0.05, 5: 0.08},
        "total_signals": 32,
        "raw_signal_count": 32,
        "signals_with_forward_returns_count": 32,
        "observed_forward_return_count": 64,
    }

    baseline = await build_factory_quality_baseline(db)
    cohort = baseline["submitted_strategy_cohort"]

    assert cohort["prediction_quality_distribution"]["strong"] == 1
    assert cohort["prediction_quality_distribution"]["mixed"] == 1
    assert cohort["execution_quality_distribution"] == {"insufficient_evidence": 2}
    assert cohort["evidence_alignment_distribution"] == {"aligned": 1, "legacy": 1}
    assert cohort["confidence_contract_ready_rate"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_factory_quality_baseline_latest_run_surfaces_high_confidence_snapshot_without_db():
    baseline = await build_factory_quality_baseline(
        None,
        latest_run={
            "run_id": "run_hc_demo",
            "submission_artifact": {
                "strategy_briefs": [
                    {
                        "strategy_id": "hc_strong",
                        "prediction_quality_label": "strong",
                        "execution_quality_label": "mixed",
                        "confidence_contract_status": "diagnostic_ready",
                        "evidence_alignment_status": "aligned",
                    },
                    {
                        "strategy_id": "hc_watch",
                        "prediction_quality_label": "weak",
                        "execution_quality_label": "weak",
                        "confidence_contract_status": "missing",
                        "evidence_alignment_status": "legacy",
                    },
                ],
            },
        },
    )

    latest_run = baseline["latest_run"]

    assert latest_run["prediction_quality_distribution"] == {"strong": 1, "weak": 1}
    assert latest_run["execution_quality_distribution"] == {"mixed": 1, "weak": 1}
    assert latest_run["evidence_alignment_distribution"] == {"aligned": 1, "legacy": 1}
    assert latest_run["confidence_contract_ready_rate"] == pytest.approx(0.5)
