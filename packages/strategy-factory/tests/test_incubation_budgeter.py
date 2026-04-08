import strategy_factory.application.incubation_budgeter as budgeter_mod
from strategy_factory.application._budget_feedback import (
    LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION,
)
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
                        "paper_hit_ratio": 0.41,
                        "runtime_alert_pressure": 0.45,
                        "realized_turnover": 0.80,
                        "capacity_crowding": 0.70,
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


def test_incubation_budgeter_hard_controls_defer_suppressed_candidates(monkeypatch):
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_FORMAL_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_OBSERVE_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_EXPLORATION_RATIO", 0.0)

    frozen_candidate = {
        "name": "frozen_momentum",
        "strategy_type": "momentum",
        "backtest_metrics": {"sharpe_ratio": 1.1, "total_return": 0.14, "max_drawdown": 0.08},
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
        "research_task": {"priority": 82, "candidate_family": "momentum"},
    }
    normal_candidate = {
        "name": "stable_quality",
        "strategy_type": "quality_factor",
        "backtest_metrics": {"sharpe_ratio": 0.9, "total_return": 0.12, "max_drawdown": 0.07},
        "params": {
            "candidate_provenance": {
                "candidate_family": "quality_factor",
                "generator_mode": "rule",
            }
        },
        "research_task": {"priority": 74, "candidate_family": "quality_factor"},
    }

    plan = IncubationBudgeter.plan(
        [frozen_candidate, normal_candidate],
        {
            "fear_greed_index": 54,
            "factor_research": {
                "summary": {"active_family_names": ["momentum", "quality_factor"]},
                "budget_feedback": {
                    "momentum": {
                        "paper_hit_ratio": 0.14,
                        "runtime_alert_pressure": 0.91,
                        "realized_turnover": 1.48,
                        "capacity_crowding": 1.22,
                        "ema_submit_count": 3.0,
                        "target_pool_feedback": {
                            "explicit:600519": {
                                "paper_hit_ratio": 0.12,
                                "runtime_alert_pressure": 0.95,
                                "realized_turnover": 1.55,
                                "capacity_crowding": 1.28,
                            }
                        },
                        "generator_mode_feedback": {
                            "external_llm": {
                                "paper_hit_ratio": 0.15,
                                "runtime_alert_pressure": 0.9,
                                "realized_turnover": 1.5,
                                "capacity_crowding": 1.2,
                            }
                        },
                    },
                    "quality_factor": {
                        "paper_hit_ratio": 0.63,
                        "runtime_alert_pressure": 0.08,
                        "realized_turnover": 0.22,
                        "capacity_crowding": 0.18,
                        "ema_submit_count": 2.2,
                    },
                },
            },
        },
    )

    frozen_plan = plan["plans"][id(frozen_candidate)]
    normal_plan = plan["plans"][id(normal_candidate)]

    assert frozen_plan["track"] == "deferred_budget_queue"
    assert frozen_plan["feedback_control_mode"] == "freeze"
    assert frozen_plan["feedback_suppressed"] is True
    assert frozen_plan["feedback_target_pool_freeze_active"] is True
    assert frozen_plan["feedback_generator_mode_freeze_active"] is True
    assert normal_plan["track"] in {"formal_incubation", "observe_incubation"}
    assert plan["summary"]["feedback_controlled_count"] == 1
    assert plan["summary"]["feedback_freeze_count"] == 1
    assert plan["summary"]["feedback_target_pool_freeze_count"] == 1
    assert plan["summary"]["feedback_generator_mode_freeze_count"] == 1


def test_incubation_budgeter_accepts_lifecycle_feedback_input_contract(monkeypatch):
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_FORMAL_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_OBSERVE_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_EXPLORATION_RATIO", 0.0)

    candidate = {
        "name": "momentum_contract_feedback",
        "strategy_type": "momentum",
        "backtest_metrics": {"sharpe_ratio": 0.85, "total_return": 0.11, "max_drawdown": 0.08},
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
        "research_task": {"priority": 75, "candidate_family": "momentum"},
    }

    plan = IncubationBudgeter.plan(
        [candidate],
        {
            "fear_greed_index": 58,
            "factor_research": {
                "summary": {"active_family_names": ["momentum"]},
                "lifecycle_feedback_input": {
                    "contract_version": LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION,
                    "available": True,
                    "feedback": {
                        "momentum": {
                            "paper_hit_ratio": 0.78,
                            "runtime_alert_pressure": 0.02,
                            "realized_turnover": 0.16,
                            "capacity_crowding": 0.12,
                            "ema_submit_count": 4.0,
                            "target_pool_feedback": {
                                "explicit:600519": {
                                    "paper_hit_ratio": 0.82,
                                    "runtime_alert_pressure": 0.01,
                                    "realized_turnover": 0.12,
                                    "capacity_crowding": 0.1,
                                }
                            },
                            "generator_mode_feedback": {
                                "external_llm": {
                                    "paper_hit_ratio": 0.8,
                                    "runtime_alert_pressure": 0.01,
                                    "realized_turnover": 0.14,
                                    "capacity_crowding": 0.1,
                                }
                            },
                        }
                    },
                    "summary": {
                        "family_count": 1,
                        "target_pool_scope_count": 1,
                        "generator_mode_scope_count": 1,
                    },
                },
            },
        },
    )

    candidate_plan = plan["plans"][id(candidate)]

    assert candidate_plan["track"] == "formal_incubation"
    assert candidate_plan["feedback_scope"]["feedback_available"] is True
    assert candidate_plan["feedback_scope"]["target_pool_feedback_available"] is True
    assert candidate_plan["feedback_scope"]["generator_mode_feedback_available"] is True
    assert candidate_plan["feedback_budget_multiplier"] > 1.0
    assert plan["summary"]["feedback_available"] is True
    assert plan["summary"]["feedback_family_count"] == 1
    assert plan["summary"]["feedback_target_pool_scope_count"] == 1
    assert plan["summary"]["feedback_generator_mode_scope_count"] == 1


def test_incubation_budgeter_uses_promotion_review_feedback_to_freeze_budget(monkeypatch):
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_FORMAL_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_OBSERVE_SLOT_COUNT", 1)
    monkeypatch.setattr(budgeter_mod, "FACTORY_INCUBATION_EXPLORATION_RATIO", 0.0)

    rejected_candidate = {
        "name": "momentum_rejected_review",
        "strategy_type": "momentum",
        "backtest_metrics": {"sharpe_ratio": 0.92, "total_return": 0.13, "max_drawdown": 0.08},
        "params": {
            "candidate_provenance": {
                "candidate_family": "momentum",
                "generator_mode": "external_llm",
            }
        },
        "research_task": {"priority": 78, "candidate_family": "momentum"},
    }
    approved_candidate = {
        "name": "quality_approved_review",
        "strategy_type": "quality_factor",
        "backtest_metrics": {"sharpe_ratio": 0.88, "total_return": 0.11, "max_drawdown": 0.07},
        "params": {
            "candidate_provenance": {
                "candidate_family": "quality_factor",
                "generator_mode": "rule",
            }
        },
        "research_task": {"priority": 76, "candidate_family": "quality_factor"},
    }

    plan = IncubationBudgeter.plan(
        [rejected_candidate, approved_candidate],
        {
            "fear_greed_index": 52,
            "factor_research": {
                "summary": {"active_family_names": ["momentum", "quality_factor"]},
                "lifecycle_feedback_input": {
                    "contract_version": LIFECYCLE_FEEDBACK_INPUT_CONTRACT_VERSION,
                    "available": True,
                    "feedback": {
                        "momentum": {
                            "paper_hit_ratio": 0.62,
                            "runtime_alert_pressure": 0.04,
                            "realized_turnover": 0.22,
                            "capacity_crowding": 0.18,
                            "promotion_review_count": 1,
                            "promotion_review_status": "rejected",
                            "promotion_review_recommendation": "deprecate",
                            "promotion_review_score": 0.18,
                        },
                        "quality_factor": {
                            "paper_hit_ratio": 0.68,
                            "runtime_alert_pressure": 0.03,
                            "realized_turnover": 0.2,
                            "capacity_crowding": 0.16,
                            "promotion_review_count": 1,
                            "promotion_review_status": "approved",
                            "promotion_review_recommendation": "promote",
                            "promotion_review_score": 0.82,
                        },
                    },
                    "summary": {
                        "family_count": 2,
                        "promotion_review_count": 2,
                        "promotion_review_status_counts": {"rejected": 1, "approved": 1},
                    },
                },
            },
        },
    )

    rejected_plan = plan["plans"][id(rejected_candidate)]
    approved_plan = plan["plans"][id(approved_candidate)]

    assert rejected_plan["track"] == "deferred_budget_queue"
    assert rejected_plan["feedback_control_mode"] == "freeze"
    assert rejected_plan["feedback_suppressed"] is True
    assert approved_plan["track"] in {"formal_incubation", "observe_incubation"}
    assert approved_plan["feedback_budget_multiplier"] > rejected_plan["feedback_budget_multiplier"]
