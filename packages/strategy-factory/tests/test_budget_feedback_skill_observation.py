import pytest

from strategy_factory.application._budget_feedback import (
    apply_feedback_controls_to_task,
    normalize_feedback_input_contract,
    resolve_feedback_metrics,
    summarize_task_feedback_controls,
)
from strategy_factory.application.factor_research import FactorResearchBuilder
from strategy_factory.application.incubation_budgeter import IncubationBudgeter


def test_resolve_feedback_metrics_exposes_parallel_skill_controls():
    feedback_root = {
        "momentum": {
            "strategy_count": 3,
            "paper_hit_ratio": 0.64,
            "paper_skill_lcb": -0.09,
            "paper_recent_skill_lcb": -0.12,
            "paper_stability_gap": 0.14,
            "paper_coverage_ratio": 0.42,
            "runtime_alert_pressure": 0.05,
            "realized_turnover": 0.22,
            "capacity_crowding": 0.18,
            "forward_window_coverage_ratio": 0.82,
            "promotion_ready_ratio": 0.38,
        }
    }

    metrics = resolve_feedback_metrics(feedback_root, family="momentum")

    assert metrics["paper_skill_lcb"] == pytest.approx(-0.09)
    assert metrics["legacy_control_mode"] == "normal"
    assert metrics["skill_control_mode"] == "freeze"
    assert metrics["control_mode"] == "normal"
    assert metrics["effective_feedback_signal"] == "legacy_paper_hit_ratio"
    assert metrics["legacy_budget_multiplier"] > 1.0
    assert metrics["skill_budget_multiplier"] == pytest.approx(0.0)
    assert metrics["skill_priority_adjustment"] <= -24.0


def test_feedback_contract_summary_includes_skill_quality_and_control_counts():
    contract = normalize_feedback_input_contract(
        {
            "available": True,
            "feedback": {
                "momentum": {
                    "strategy_count": 2,
                    "paper_hit_ratio": 0.64,
                    "paper_skill_lcb": -0.09,
                    "paper_recent_skill_lcb": -0.12,
                    "paper_stability_gap": 0.14,
                    "paper_coverage_ratio": 0.42,
                },
                "quality_factor": {
                    "strategy_count": 2,
                    "paper_hit_ratio": 0.18,
                    "paper_skill_lcb": -0.02,
                    "paper_recent_skill_lcb": -0.01,
                    "paper_stability_gap": 0.03,
                    "paper_coverage_ratio": 0.88,
                },
            },
        }
    )

    summary = contract["summary"]

    assert summary["paper_hit_ratio"] == pytest.approx(0.41)
    assert summary["paper_skill_lcb"] == pytest.approx(-0.055)
    assert summary["paper_recent_skill_lcb"] == pytest.approx(-0.065)
    assert summary["paper_stability_gap"] == pytest.approx(0.085)
    assert summary["paper_coverage_ratio"] == pytest.approx(0.65)
    assert summary["legacy_control_mode_counts"] == {"normal": 1, "freeze": 1}
    assert summary["skill_control_mode_counts"] == {"freeze": 1, "cooldown": 1}


def test_feedback_routes_surface_paper_skill_lcb_for_family_and_scopes():
    feedback_root = {
        "momentum": {
            "strategy_count": 4,
            "paper_hit_ratio": 0.66,
            "paper_skill_lcb": 0.07,
            "paper_recent_skill_lcb": 0.05,
            "paper_stability_gap": 0.03,
            "paper_coverage_ratio": 0.82,
            "promotion_ready_ratio": 0.45,
            "forward_window_coverage_ratio": 0.72,
            "target_pool_feedback": {
                "theme:ai": {
                    "strategy_count": 2,
                    "paper_hit_ratio": 0.58,
                    "paper_skill_lcb": 0.04,
                    "paper_recent_skill_lcb": 0.02,
                    "paper_stability_gap": 0.04,
                    "paper_coverage_ratio": 0.75,
                    "promotion_ready_ratio": 0.50,
                    "forward_window_coverage_ratio": 0.75,
                }
            },
            "generator_mode_feedback": {
                "external_llm": {
                    "strategy_count": 3,
                    "paper_hit_ratio": 0.62,
                    "paper_skill_lcb": -0.05,
                    "paper_recent_skill_lcb": -0.06,
                    "paper_stability_gap": 0.12,
                    "paper_coverage_ratio": 0.55,
                    "zero_signal_ratio": 0.40,
                }
            },
        }
    }

    family_reward_table, _family_debt_table, _search_route_actions, _family_plans = (
        FactorResearchBuilder._build_search_route_feedback_snapshot(
            family_preference_order=["momentum"],
            budget_feedback_root=feedback_root,
        )
    )

    assert family_reward_table["momentum"]["paper_skill_lcb"] == pytest.approx(0.07)
    assert (
        family_reward_table["momentum"]["target_pool_routes"]["theme:ai"]["paper_skill_lcb"]
        == pytest.approx(0.0567, abs=1e-4)
    )
    assert (
        family_reward_table["momentum"]["generator_mode_routes"]["external_llm"]["paper_skill_lcb"]
        == pytest.approx(0.0227, abs=1e-4)
    )
    assert (
        family_reward_table["momentum"]["generator_mode_routes"]["external_llm"]["skill_control_mode"]
        == "suppress"
    )


def test_scheduler_feedback_summary_keeps_legacy_live_and_tracks_skill_comparison():
    task = apply_feedback_controls_to_task(
        {
            "task_id": "snapshot_1",
            "task_source": "snapshot",
            "candidate_family": "momentum",
        },
        {
            "momentum": {
                "strategy_count": 3,
                "paper_hit_ratio": 0.64,
                "paper_skill_lcb": -0.09,
                "paper_recent_skill_lcb": -0.12,
                "paper_stability_gap": 0.14,
                "paper_coverage_ratio": 0.42,
            }
        },
    )

    summary = summarize_task_feedback_controls([task])

    assert summary["feedback_control_mode_counts"] == {"normal": 1}
    assert summary["feedback_legacy_control_mode_counts"] == {"normal": 1}
    assert summary["feedback_skill_control_mode_counts"] == {"freeze": 1}


def test_incubation_budgeter_surfaces_skill_feedback_observation_fields(monkeypatch):
    monkeypatch.setattr(
        "strategy_factory.application.incubation_budgeter.FACTORY_INCUBATION_FORMAL_SLOT_COUNT",
        1,
    )
    monkeypatch.setattr(
        "strategy_factory.application.incubation_budgeter.FACTORY_INCUBATION_OBSERVE_SLOT_COUNT",
        0,
    )
    monkeypatch.setattr(
        "strategy_factory.application.incubation_budgeter.FACTORY_INCUBATION_EXPLORATION_RATIO",
        0.0,
    )

    candidate = {
        "name": "momentum_skill_watch",
        "strategy_type": "momentum",
        "backtest_metrics": {
            "sharpe_ratio": 0.8,
            "total_return": 0.10,
            "max_drawdown": 0.08,
        },
        "params": {
            "candidate_provenance": {
                "candidate_family": "momentum",
                "generator_mode": "external_llm",
            }
        },
        "research_task": {"priority": 72, "candidate_family": "momentum"},
    }

    plan = IncubationBudgeter.plan(
        [candidate],
        {
            "fear_greed_index": 55,
            "factor_research": {
                "summary": {"active_family_names": ["momentum"]},
                "budget_feedback": {
                    "momentum": {
                        "strategy_count": 3,
                        "paper_hit_ratio": 0.64,
                        "paper_skill_lcb": -0.09,
                        "paper_recent_skill_lcb": -0.12,
                        "paper_stability_gap": 0.14,
                        "paper_coverage_ratio": 0.42,
                        "runtime_alert_pressure": 0.05,
                        "realized_turnover": 0.22,
                        "capacity_crowding": 0.18,
                        "generator_mode_feedback": {
                            "external_llm": {
                                "strategy_count": 2,
                                "paper_hit_ratio": 0.63,
                                "paper_skill_lcb": -0.08,
                                "paper_recent_skill_lcb": -0.10,
                                "paper_stability_gap": 0.10,
                                "paper_coverage_ratio": 0.50,
                            }
                        },
                    }
                },
            },
        },
    )

    candidate_plan = plan["plans"][id(candidate)]

    assert candidate_plan["feedback_control_mode"] == "normal"
    assert candidate_plan["feedback_legacy_control_mode"] == "normal"
    assert candidate_plan["feedback_skill_control_mode"] == "freeze"
    assert candidate_plan["feedback_budget_multiplier"] > 1.0
    assert candidate_plan["feedback_skill_budget_multiplier"] == pytest.approx(0.0)
    assert candidate_plan["feedback_paper_skill_lcb"] == pytest.approx(-0.0861)
    assert candidate_plan["feedback_scope"]["skill_control_mode"] == "freeze"
    assert plan["summary"]["feedback_skill_controlled_count"] == 1
    assert plan["summary"]["feedback_paper_skill_lcb_avg"] == pytest.approx(-0.0861)
