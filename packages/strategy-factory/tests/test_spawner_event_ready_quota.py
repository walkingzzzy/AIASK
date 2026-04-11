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
