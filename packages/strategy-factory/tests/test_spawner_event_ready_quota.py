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
