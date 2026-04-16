from strategy_factory.domain.spawner import StrategySpawner


def test_spawn_event_ready_caps_local_sources_instead_of_disabling_them():
    spawner = StrategySpawner()
    candidates = spawner.spawn(
        {
            "fear_greed_index": 55,
            "fg_components": {"volatility": 50},
            "factor_ic": {},
            "factor_ic_trend": {},
            "north_fund_3d_net": 0,
            "margin_5d_change_pct": 0,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }
    )
    summary = spawner.get_last_report()["summary"]

    assert candidates
    assert summary["event_ready"] is True
    assert summary["event_ready_supplemental"] is False
    assert summary["source_counts"]["fear_greed"] > 0
    assert summary["source_raw_counts"]["fear_greed"] > summary["source_counts"]["fear_greed"]
    assert summary["source_counts"]["fear_greed"] <= summary["source_budget_caps"]["fear_greed"]
    assert summary["source_budget_weights"]["fear_greed"] == 0.45
    assert summary["source_budget_weights"]["factor_ic"] == 1.0
    assert summary["source_trimmed_count"] >= 1


def test_spawn_event_ready_preserves_controlled_strong_local_sources():
    spawner = StrategySpawner()
    candidates = spawner.spawn(
        {
            "fear_greed_index": 80,
            "fg_components": {"volatility": 72},
            "factor_ic": {"value": 0.05, "quality": 0.045},
            "factor_ic_trend": {"value": "rising", "quality": "rising"},
            "north_fund_3d_net": 8e9,
            "margin_5d_change_pct": 3.2,
            "event_driven": {"event_count": 1, "tasks_ready_count": 1},
            "completeness": {"completion_ratio": 1.0},
        }
    )
    summary = spawner.get_last_report()["summary"]

    assert candidates
    assert summary["event_ready"] is True
    assert summary["event_ready_supplemental"] is True
    assert summary["source_counts"]["fear_greed"] > 0
    assert summary["source_counts"]["volatility"] > 0
    assert summary["source_counts"]["fund_flow"] > 0
    assert summary["source_counts"]["fear_greed"] <= summary["source_budget_caps"]["fear_greed"]
    assert summary["source_counts"]["volatility"] <= summary["source_budget_caps"]["volatility"]
    assert summary["source_counts"]["fund_flow"] <= summary["source_budget_caps"]["fund_flow"]
    assert summary["source_raw_counts"]["fund_flow"] > summary["source_counts"]["fund_flow"]
    assert summary["source_budget_weights"]["fear_greed"] == 0.75
    assert summary["source_budget_weights"]["fund_flow"] == 0.8
    assert summary["source_budget_caps"]["factor_ic"] is None
    assert summary["source_trimmed_count"] >= 1


def test_varied_defaults_prefers_historical_parameter_distribution_samples():
    spawner = StrategySpawner()
    snapshot = {
        "parameter_distribution_samples": [
            {
                "strategy_id": "s1",
                "strategy_type": "momentum",
                "params": {"lookback": 52, "threshold": 0.039},
                "validation_grade": "A",
                "quality_passed": True,
                "total_signals": 24,
                "observed_forward_days": [1, 5, 10, 20],
                "sampling_weight": 1.0,
            },
            {
                "strategy_id": "s2",
                "strategy_type": "momentum",
                "params": {"lookback": 58, "threshold": 0.041},
                "validation_grade": "B",
                "quality_passed": True,
                "total_signals": 20,
                "observed_forward_days": [5, 10, 20],
                "sampling_weight": 0.9,
            },
            {
                "strategy_id": "s3",
                "strategy_type": "momentum",
                "params": {"lookback": 62, "threshold": 0.044},
                "validation_grade": "B",
                "quality_passed": True,
                "total_signals": 18,
                "observed_forward_days": [5, 10, 20],
                "sampling_weight": 0.85,
            },
        ]
    }

    params = spawner._varied_defaults("momentum", 0, snapshot)

    assert 50 <= params["lookback"] <= 62
    assert 0.038 <= params["threshold"] <= 0.044
    assert params["lookback"] > 40


def test_fill_gaps_uses_historical_distribution_when_available():
    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "north_fund_3d_net": 0,
        "margin_5d_change_pct": 0,
        "factor_ic": {},
        "factor_ic_trend": {},
        "event_driven": {"event_count": 0, "tasks_ready_count": 0},
        "completeness": {"completion_ratio": 1.0},
        "parameter_distribution_samples": [
            {
                "strategy_id": "m1",
                "strategy_type": "ma_cross",
                "params": {"short_period": 18, "long_period": 90},
                "validation_grade": "A",
                "quality_passed": True,
                "total_signals": 25,
                "observed_forward_days": [1, 5, 10, 20],
            },
            {
                "strategy_id": "m2",
                "strategy_type": "ma_cross",
                "params": {"short_period": 20, "long_period": 100},
                "validation_grade": "B",
                "quality_passed": True,
                "total_signals": 19,
                "observed_forward_days": [5, 10, 20],
            },
            {
                "strategy_id": "m3",
                "strategy_type": "ma_cross",
                "params": {"short_period": 22, "long_period": 110},
                "validation_grade": "B",
                "quality_passed": True,
                "total_signals": 17,
                "observed_forward_days": [5, 10, 20],
            },
        ],
    }

    candidates = spawner._fill_gaps(snapshot, current_candidates=[])

    assert candidates
    historical_candidates = [item for item in candidates if item.get("parameter_source") == "historical_distribution"]
    assert historical_candidates
    first = historical_candidates[0]
    assert first["quota_fill"]["parameter_source"] == "historical_distribution"
    assert first["quota_fill"]["parameter_sample_count"] >= 3
    assert first["quota_fill"]["fill_source_mode"] == "historical_guided"
    assert first["quota_fill"]["fill_quality_tier"] == "oos_validated_history"


def test_fill_gaps_marks_no_signal_fallback_when_no_history_and_no_current_candidates():
    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "north_fund_3d_net": 0,
        "margin_5d_change_pct": 0,
        "factor_ic": {},
        "factor_ic_trend": {},
        "event_driven": {"event_count": 0, "tasks_ready_count": 0},
        "completeness": {"completion_ratio": 1.0},
    }

    candidates = spawner._fill_gaps(snapshot, current_candidates=[])

    assert len(candidates) == 1
    assert candidates[0]["quota_fill"]["fill_source_mode"] == "no_signal_fallback"
    assert candidates[0]["quota_fill"]["fill_quality_tier"] == "fallback_only"


def test_spawn_summary_tracks_quota_fill_modes_and_effective_counts():
    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 50,
        "fg_components": {"volatility": 50},
        "factor_ic": {},
        "factor_ic_trend": {},
        "north_fund_3d_net": 0,
        "margin_5d_change_pct": 0,
        "event_driven": {"event_count": 0, "tasks_ready_count": 0},
        "completeness": {"completion_ratio": 1.0},
        "parameter_distribution_samples": [
            {
                "strategy_id": "q1",
                "strategy_type": "ma_cross",
                "params": {"short_period": 18, "long_period": 90},
                "validation_grade": "A",
                "quality_passed": True,
                "total_signals": 20,
                "observed_forward_days": [1, 5, 10, 20],
            },
            {
                "strategy_id": "q2",
                "strategy_type": "ma_cross",
                "params": {"short_period": 20, "long_period": 100},
                "validation_grade": "B",
                "quality_passed": True,
                "total_signals": 18,
                "observed_forward_days": [5, 10, 20],
            },
            {
                "strategy_id": "q3",
                "strategy_type": "ma_cross",
                "params": {"short_period": 22, "long_period": 110},
                "validation_grade": "B",
                "quality_passed": True,
                "total_signals": 16,
                "observed_forward_days": [5, 10, 20],
            },
        ],
    }

    candidates = spawner.spawn(snapshot)
    summary = spawner.get_last_report()["summary"]

    assert candidates
    assert summary["quota_fill_count"] >= 1
    assert summary["historical_guided_quota_fill_count"] >= 1
    assert summary["quota_fill_mode_counts"]["historical_guided"] >= 1
    assert summary["quota_fill_quality_counts"]["oos_validated_history"] >= 1
    assert summary["effective_quota_fill_count"] >= summary["historical_guided_quota_fill_count"]
    assert summary["no_signal_quota_fill_count"] == 0


def test_fill_gaps_avoids_momentum_quota_fill_and_limits_trend_cluster_ratio():
    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 80,
        "fg_components": {"volatility": 72},
        "factor_ic": {},
        "factor_ic_trend": {},
        "north_fund_3d_net": 0,
        "margin_5d_change_pct": 0,
        "event_driven": {"event_count": 0, "tasks_ready_count": 0},
        "completeness": {"completion_ratio": 1.0},
    }
    current_candidates = [
        {"strategy_type": "momentum"},
        {"strategy_type": "ma_cross"},
        {"strategy_type": "volatility_breakout"},
    ]

    filled = spawner._fill_gaps(snapshot, current_candidates=current_candidates)

    assert filled
    assert all(item["strategy_type"] != "momentum" for item in filled)
    assert all(item["strategy_type"] not in {"momentum", "ma_cross", "volatility_breakout"} for item in filled)

    summary = spawner._build_spawn_report([*current_candidates, *filled])["summary"]
    assert summary["trend_cluster_ratio"] <= 0.5
    assert "pool_profile_distribution" in summary
    assert "diversification_debt" in summary


def test_spawn_targets_snapshot_candidates_from_stock_family_allocation():
    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 55,
        "fg_components": {"volatility": 52},
        "factor_ic": {},
        "factor_ic_trend": {},
        "north_fund_3d_net": 0,
        "margin_5d_change_pct": 0,
        "event_driven": {"event_count": 0, "tasks_ready_count": 0},
        "completeness": {"completion_ratio": 1.0},
        "factor_research": {
            "stock_family_allocation": {
                "600001": {
                    "priority": 0.95,
                    "top_family": "ma_cross",
                    "source_mode": "stock_universe_projection",
                    "family_plans": [
                        {"family": "ma_cross", "family_rank": 1, "budget_weight": 0.55, "failure_penalty": 0.08},
                        {"family": "quality_factor", "family_rank": 2, "budget_weight": 0.30, "failure_penalty": 0.12},
                    ],
                },
                "600002": {
                    "priority": 0.90,
                    "top_family": "ma_cross",
                    "source_mode": "stock_universe_projection",
                    "family_plans": [
                        {"family": "ma_cross", "family_rank": 1, "budget_weight": 0.50, "failure_penalty": 0.10},
                    ],
                },
                "600003": {
                    "priority": 0.82,
                    "top_family": "momentum",
                    "source_mode": "stock_universe_projection",
                    "family_plans": [
                        {"family": "momentum", "family_rank": 1, "budget_weight": 0.42, "failure_penalty": 0.16},
                    ],
                },
            },
        },
    }

    candidates = spawner.spawn(snapshot)
    ma_cross = next(item for item in candidates if item["strategy_type"] == "ma_cross")

    assert ma_cross["requested_target_symbols"][:2] == ["600001", "600002"]
    assert ma_cross["target_symbols"][:2] == ["600001", "600002"]
    assert ma_cross["stock_pool"]["symbols"][:2] == ["600001", "600002"]
    assert ma_cross["research_task"]["synthetic_local_spawn"] is True
    assert ma_cross["research_task"]["validation_focus"] == "candidate_target_only"
    assert ma_cross["research_task"]["gate_1_representative_count"] >= 2
    assert "targeted_universe" in ma_cross["tags"]


def test_fill_gaps_caps_mean_reversion_short_after_first_local_candidate():
    spawner = StrategySpawner()
    snapshot = {
        "fear_greed_index": 28,
        "fg_components": {"volatility": 38},
        "factor_ic": {},
        "factor_ic_trend": {},
        "north_fund_3d_net": -6e9,
        "margin_5d_change_pct": -2.5,
        "event_driven": {"event_count": 0, "tasks_ready_count": 0},
        "completeness": {"completion_ratio": 1.0},
    }
    current_candidates = [
        {"strategy_type": "mean_reversion_short"},
        {"strategy_type": "rsi"},
    ]

    filled = spawner._fill_gaps(snapshot, current_candidates=current_candidates)

    assert all(item["strategy_type"] != "mean_reversion_short" for item in filled)
