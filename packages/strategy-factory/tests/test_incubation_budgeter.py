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


def test_incubation_budgeter_applies_budget_feedback_to_priority(monkeypatch):
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_FORMAL_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_OBSERVE_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_EXPLORATION_RATIO", 0.0)

    momentum_candidate = {
        "name": "momentum_feedback",
        "strategy_type": "momentum",
        "backtest_metrics": {"sharpe_ratio": 0.8, "total_return": 0.10, "max_drawdown": 0.08},
        "candidate_contract_snapshot": {
            "targeting": {
                "target_pool_id": "explicit:600519",
                "target_symbols": ["600519"],
            }
        },
        "params": {
            "candidate_provenance": {
                "candidate_family": "momentum",
                "generator_mode": "external_llm",
            }
        },
        "research_task": {"priority": 72, "candidate_family": "momentum"},
    }
    mean_reversion_candidate = {
        "name": "mean_reversion_feedback",
        "strategy_type": "mean_reversion",
        "backtest_metrics": {"sharpe_ratio": 0.8, "total_return": 0.10, "max_drawdown": 0.08},
        "params": {
            "candidate_provenance": {
                "candidate_family": "mean_reversion",
                "generator_mode": "rule",
            }
        },
        "research_task": {"priority": 72, "candidate_family": "mean_reversion"},
    }

    plan = IncubationBudgeter.plan(
        [momentum_candidate, mean_reversion_candidate],
        {
            "fear_greed_index": 55,
            "factor_research": {
                "summary": {"active_family_names": ["momentum"]},
                "budget_feedback": {
                    "momentum": {
                        "paper_hit_ratio": 0.76,
                        "runtime_alert_pressure": 0.02,
                        "realized_turnover": 0.18,
                        "capacity_crowding": 0.14,
                        "ema_submit_count": 4.0,
                        "target_pool_feedback": {
                            "explicit:600519": {
                                "paper_hit_ratio": 0.82,
                                "runtime_alert_pressure": 0.0,
                                "realized_turnover": 0.12,
                                "capacity_crowding": 0.1,
                            }
                        },
                        "generator_mode_feedback": {
                            "external_llm": {
                                "paper_hit_ratio": 0.8,
                                "runtime_alert_pressure": 0.01,
                                "realized_turnover": 0.16,
                                "capacity_crowding": 0.12,
                            }
                        },
                    },
                    "mean_reversion": {
                        "paper_hit_ratio": 0.32,
                        "runtime_alert_pressure": 0.74,
                        "realized_turnover": 1.12,
                        "capacity_crowding": 0.88,
                        "ema_submit_count": 0.1,
                    },
                },
            },
        },
    )

    momentum_plan = plan["plans"][id(momentum_candidate)]
    mean_reversion_plan = plan["plans"][id(mean_reversion_candidate)]

    assert momentum_plan["track"] == "formal_incubation"
    assert mean_reversion_plan["track"] == "observe_incubation"
    assert momentum_plan["feedback_budget_multiplier"] > 1.0
    assert mean_reversion_plan["feedback_budget_multiplier"] < 1.0
    assert momentum_plan["feedback_scope"]["target_pool_feedback_available"] is True
    assert momentum_plan["feedback_scope"]["generator_mode_feedback_available"] is True
    assert momentum_plan["feedback_priority_adjustment"] > 0.0
    assert mean_reversion_plan["feedback_priority_adjustment"] < 0.0
    assert momentum_plan["priority_score"] > mean_reversion_plan["priority_score"]
    assert plan["summary"]["feedback_available"] is True
    assert plan["summary"]["feedback_candidate_count"] == 2
    assert plan["summary"]["feedback_family_count"] == 2
    assert plan["summary"]["feedback_target_pool_scope_count"] == 1
    assert plan["summary"]["feedback_generator_mode_scope_count"] == 1
