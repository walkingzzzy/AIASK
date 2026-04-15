from collections import Counter

from strategy_factory.application.quality_reporting import build_quality_report

_REPLAY_DATE = "2026-04-14"
_POOL_PROFILE_DISTRIBUTION = {
    "high_vol_growth": 8,
    "low_vol_defensive": 4,
    "cycle_resource": 4,
}


def _default_backtest_assumptions(pool_profile: str, strategy_type: str) -> dict:
    if pool_profile == "high_vol_growth":
        if strategy_type in {"volatility_breakout", "momentum"}:
            return {
                "stop_loss_mode": "atr_bucketed",
                "stop_rule_source": "atr_bucketed",
                "atr_window": 14,
                "atr_multiplier": 2.2,
                "time_stop_days": 6,
                "take_profit_pct": 0.09,
                "position_cap_pct": 0.10,
                "trailing_activation_r": 1.5,
            }
        return {
            "stop_loss_mode": "atr_bucketed",
            "stop_rule_source": "atr_bucketed",
            "atr_window": 14,
            "atr_multiplier": 1.8,
            "time_stop_days": 3,
            "take_profit_pct": 0.07,
            "position_cap_pct": 0.10,
            "trailing_activation_r": 1.2,
        }
    if pool_profile == "cycle_resource":
        return {
            "stop_loss_mode": "atr_bucketed",
            "stop_rule_source": "atr_bucketed",
            "atr_window": 14,
            "atr_multiplier": 2.5,
            "time_stop_days": 10,
            "take_profit_pct": 0.13,
            "position_cap_pct": 0.14,
            "trailing_activation_r": 1.8,
        }
    return {
        "stop_loss_mode": "atr_bucketed",
        "stop_rule_source": "atr_bucketed",
        "atr_window": 14,
        "atr_multiplier": 3.0,
        "time_stop_days": 18,
        "take_profit_pct": 0.12,
        "position_cap_pct": 0.18,
        "trailing_activation_r": 2.0,
    }


def _volatility_bucket(pool_profile: str) -> str:
    return {
        "high_vol_growth": "high",
        "low_vol_defensive": "low",
        "cycle_resource": "medium",
    }[pool_profile]


def _regime_fit(pool_profile: str) -> str:
    return {
        "high_vol_growth": "trend_expansion",
        "low_vol_defensive": "defensive_rotation",
        "cycle_resource": "commodity_rotation",
    }[pool_profile]


def _build_replay_report(case: dict) -> dict:
    pool_profile = case["pool_profile"]
    strategy_type = case["strategy_type"]
    assumptions = _default_backtest_assumptions(pool_profile, strategy_type)
    assumptions.update(case.get("assumption_overrides") or {})

    snapshot = {"date": _REPLAY_DATE}
    if case.get("market_facts") is not None:
        snapshot["market_facts"] = list(case["market_facts"])

    audit = {
        "candidate_provenance": {
            "pool_profile": pool_profile,
            "volatility_bucket": _volatility_bucket(pool_profile),
            "liquidity_bucket": "stable",
            "holding_period_bucket": case["holding_period_bucket"],
            "regime_fit": _regime_fit(pool_profile),
        },
        "pool_profile_distribution": dict(_POOL_PROFILE_DISTRIBUTION),
    }
    if case.get("trend_cluster_ratio") is not None:
        audit["trend_cluster_ratio"] = case["trend_cluster_ratio"]
    if case.get("diversification_debt"):
        audit["diversification_debt"] = list(case["diversification_debt"])

    return build_quality_report(
        strategy_id=case["strategy_id"],
        strategy_type=strategy_type,
        quality_gate={"passed": True, "validation_grade": "B"},
        validation_report={"rating": {"grade": "B", "total_score": 0.61}},
        risk_report={},
        dedup_report={},
        backtest_metrics={"backtest_assumptions": assumptions},
        snapshot=snapshot,
        status_after_review="reviewed",
        review_source="replay:2026-04-14",
        report_type="submission_replay",
        submission_audit=audit,
    )


def test_build_quality_report_classifies_2026_04_14_replay_sample_pool():
    replay_cases = [
        {
            "strategy_id": "replay_20260414_01",
            "strategy_type": "volatility_breakout",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "long",
            "expected_buckets": ["signal_lag"],
        },
        {
            "strategy_id": "replay_20260414_02",
            "strategy_type": "gap_fill",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "long",
            "expected_buckets": ["signal_lag"],
        },
        {
            "strategy_id": "replay_20260414_03",
            "strategy_type": "mean_reversion_short",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "long",
            "expected_buckets": ["signal_lag"],
        },
        {
            "strategy_id": "replay_20260414_04",
            "strategy_type": "ma_cross",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "short",
            "expected_buckets": ["signal_lag", "pool_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_05",
            "strategy_type": "volatility_breakout",
            "pool_profile": "low_vol_defensive",
            "holding_period_bucket": "short",
            "expected_buckets": ["pool_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_06",
            "strategy_type": "gap_fill",
            "pool_profile": "cycle_resource",
            "holding_period_bucket": "medium",
            "expected_buckets": ["pool_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_07",
            "strategy_type": "north_capital_track",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "short",
            "expected_buckets": ["pool_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_08",
            "strategy_type": "sector_rotation",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "short",
            "expected_buckets": ["pool_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_09",
            "strategy_type": "volatility_breakout",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "short",
            "assumption_overrides": {"stop_loss_mode": "fixed_pct_legacy", "stop_rule_source": "fixed_pct_legacy"},
            "expected_buckets": ["risk_parameter_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_10",
            "strategy_type": "gap_fill",
            "pool_profile": "high_vol_growth",
            "holding_period_bucket": "short",
            "assumption_overrides": {"take_profit_pct": 0.12},
            "expected_buckets": ["risk_parameter_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_11",
            "strategy_type": "ma_cross",
            "pool_profile": "cycle_resource",
            "holding_period_bucket": "medium",
            "assumption_overrides": {"position_cap_pct": 0.20},
            "expected_buckets": ["risk_parameter_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_12",
            "strategy_type": "quality_factor",
            "pool_profile": "low_vol_defensive",
            "holding_period_bucket": "short",
            "assumption_overrides": {"time_stop_days": 10},
            "expected_buckets": ["risk_parameter_mismatch"],
        },
        {
            "strategy_id": "replay_20260414_13",
            "strategy_type": "quality_factor",
            "pool_profile": "low_vol_defensive",
            "holding_period_bucket": "short",
            "trend_cluster_ratio": 0.75,
            "expected_buckets": ["homogeneous_exposure"],
        },
        {
            "strategy_id": "replay_20260414_14",
            "strategy_type": "quality_factor",
            "pool_profile": "cycle_resource",
            "holding_period_bucket": "medium",
            "diversification_debt": ["missing_mean_reversion_coverage"],
            "expected_buckets": ["homogeneous_exposure"],
        },
        {
            "strategy_id": "replay_20260414_15",
            "strategy_type": "quality_factor",
            "pool_profile": "low_vol_defensive",
            "holding_period_bucket": "medium",
            "market_facts": [
                {
                    "metric": "volume_ratio",
                    "trade_date": _REPLAY_DATE,
                    "source_as_of_date": _REPLAY_DATE,
                    "window_scope": "same_day",
                    "unit": "ratio",
                }
            ],
            "expected_buckets": ["data_threshold_idle"],
            "expected_gate_status": "degraded_only",
        },
        {
            "strategy_id": "replay_20260414_16",
            "strategy_type": "north_capital_track",
            "pool_profile": "cycle_resource",
            "holding_period_bucket": "medium",
            "market_facts": [
                {
                    "metric": "close",
                    "trade_date": _REPLAY_DATE,
                    "source_as_of_date": _REPLAY_DATE,
                    "window_scope": "same_day",
                    "unit": "cny",
                },
                {
                    "metric": "5d_fund_flow",
                    "trade_date": _REPLAY_DATE,
                    "source_as_of_date": "2026-04-11",
                    "window_scope": "5d",
                    "unit": "cny",
                },
            ],
            "expected_buckets": ["data_threshold_idle"],
            "expected_gate_status": "mixed_with_degraded",
        },
    ]

    primary_counter = Counter()
    pool_counter = Counter()
    coverage = set()

    for case in replay_cases:
        report = _build_replay_report(case)
        expected_primary = case["expected_buckets"][0]

        assert report["summary"]["review_issue_buckets"] == case["expected_buckets"]
        assert report["review_issue_buckets"] == case["expected_buckets"]
        assert report["summary"]["review_issue_primary"] == expected_primary
        assert report["review_issue_primary"] == expected_primary
        assert report["summary"]["pool_profile"] == case["pool_profile"]
        assert report["pool_profile"] == case["pool_profile"]
        assert report["summary"]["pool_profile_distribution"] == _POOL_PROFILE_DISTRIBUTION
        assert report["pool_profile_distribution"] == _POOL_PROFILE_DISTRIBUTION

        if case.get("expected_gate_status"):
            assert report["summary"]["evidence_gate_status"] == case["expected_gate_status"]
            assert report["evidence_gate_status"] == case["expected_gate_status"]

        primary_counter[expected_primary] += 1
        pool_counter[case["pool_profile"]] += 1
        coverage.update(report["summary"]["review_issue_buckets"])

    assert len(replay_cases) == 16
    assert primary_counter == Counter(
        {
            "signal_lag": 4,
            "pool_mismatch": 4,
            "risk_parameter_mismatch": 4,
            "homogeneous_exposure": 2,
            "data_threshold_idle": 2,
        }
    )
    assert pool_counter == Counter(_POOL_PROFILE_DISTRIBUTION)
    assert coverage == {
        "signal_lag",
        "pool_mismatch",
        "risk_parameter_mismatch",
        "homogeneous_exposure",
        "data_threshold_idle",
    }
