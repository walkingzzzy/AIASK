import strategy_factory.application.incubation_budgeter as budgeter_mod
from strategy_factory.application.incubation_budgeter import IncubationBudgeter


def test_incubation_budgeter_reserves_exploration_quota(monkeypatch):
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_FORMAL_SLOT_COUNT", 2)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_OBSERVE_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_EXPLORATION_RATIO", 0.2)

    candidates = [
        {
            "name": "momentum_a",
            "strategy_type": "momentum",
            "backtest_metrics": {"sharpe_ratio": 1.2, "total_return": 0.18, "max_drawdown": 0.10},
            "research_task": {"priority": 80, "candidate_family": "momentum"},
        },
        {
            "name": "momentum_b",
            "strategy_type": "momentum",
            "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.16, "max_drawdown": 0.11},
            "research_task": {"priority": 78, "candidate_family": "momentum"},
        },
        {
            "name": "momentum_c",
            "strategy_type": "momentum",
            "backtest_metrics": {"sharpe_ratio": 1.0, "total_return": 0.14, "max_drawdown": 0.12},
            "research_task": {"priority": 75, "candidate_family": "momentum"},
        },
        {
            "name": "cold_start_vol",
            "strategy_type": "volatility_breakout",
            "backtest_metrics": {"sharpe_ratio": 0.55, "total_return": 0.07, "max_drawdown": 0.09},
            "research_task": {"priority": 62, "candidate_family": "volatility_breakout"},
        },
    ]

    plan = IncubationBudgeter.plan(
        candidates,
        {"fear_greed_index": 62, "factor_research": {"summary": {"active_family_names": ["momentum"]}}},
    )

    assigned_tracks = {
        candidate["name"]: plan["plans"][id(candidate)]["track"]
        for candidate in candidates
    }

    assert plan["summary"]["exploration_reserved_slots"] == 1
    assert plan["summary"]["exploration_selected_count"] >= 1
    assert assigned_tracks["cold_start_vol"] in {"formal_incubation", "observe_incubation"}


def test_incubation_budgeter_marks_single_candidate_as_formal():
    candidate = {
        "name": "single_formal",
        "strategy_type": "value_factor",
        "backtest_metrics": {"sharpe_ratio": 0.9, "total_return": 0.12, "max_drawdown": 0.08},
        "research_task": {"priority": 70, "candidate_family": "value_factor"},
    }

    plan = IncubationBudgeter.plan([candidate], {"fear_greed_index": 45})

    assert plan["plans"][id(candidate)]["track"] == "formal_incubation"
    assert plan["summary"]["track_counts"]["formal_incubation"] == 1
