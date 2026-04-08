from akshare_mcp.services.strategy_reviewer import MultiAgentStrategyReviewer
from akshare_mcp.services.strategy_spec import StrategySpec


def test_reviewer_exposes_execution_capacity_and_alignment_scores():
    reviewer = MultiAgentStrategyReviewer()

    weak_spec = StrategySpec(
        strategy_type="dsl_rule",
        params={"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
        name="weak",
        tags=["external_llm"],
        metadata={
            "research_task": {
                "preferred_strategy_types": ["dsl_rule"],
                "target_symbols": ["600519"],
            },
            "target_symbols": ["300750", "000858"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["300750", "000858"]},
        },
    )
    strong_spec = StrategySpec(
        strategy_type="dsl_rule",
        params={
            "dsl": {
                "entry": {"all": []},
                "exit": {"any": []},
                "metadata": {"target_symbols": ["600519"]},
                "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            }
        },
        name="strong",
        tags=["external_llm"],
        metadata={
            "research_task": {
                "preferred_strategy_types": ["dsl_rule"],
                "target_symbols": ["600519"],
            },
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"], "rationale": "任务单标的"},
            "holding_horizon": {"max_days": 10},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "execution_assumptions": {
                "tradability_filter": True,
                "slippage_bps": 5,
                "slippage_model": "fixed",
                "capacity_bucket": "mid",
                "capacity_participation_rate": 0.1,
                "adv_ratio_limit": 0.15,
            },
            "portfolio_spec": {
                "position_assumption": "single_name_full_notional",
                "target_weight_scheme": "single_name",
            },
        },
    )

    _, weak_review = reviewer.review(weak_spec, {"fear_greed_index": 55})
    _, strong_review = reviewer.review(strong_spec, {"fear_greed_index": 55})

    assert "execution_score" in weak_review
    assert "capacity_score" in weak_review
    assert "task_alignment_score" in weak_review
    assert "alignment_issues" in weak_review
    assert "execution_issues" in weak_review
    assert "capacity_issues" in weak_review
    assert "target_universe_drift" in weak_review["alignment_issues"]
    assert weak_review["final_score"] < strong_review["final_score"]


def test_reviewer_keeps_novelty_as_secondary_signal():
    reviewer = MultiAgentStrategyReviewer()

    external_llm_spec = StrategySpec(
        strategy_type="dsl_rule",
        params={"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
        name="novel",
        tags=["external_llm"],
        metadata={},
    )
    grounded_spec = StrategySpec(
        strategy_type="dsl_rule",
        params={
            "dsl": {
                "entry": {"all": []},
                "exit": {"any": []},
                "metadata": {"target_symbols": ["600519"]},
                "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            }
        },
        name="grounded",
        tags=["rule"],
        metadata={
            "holding_horizon": {"max_days": 10},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "execution_assumptions": {
                "tradability_filter": True,
                "slippage_bps": 5,
                "slippage_model": "fixed",
                "capacity_bucket": "mid",
            },
            "portfolio_spec": {"position_assumption": "single_name_full_notional"},
            "target_symbols": ["600519"],
        },
    )

    _, novel_review = reviewer.review(external_llm_spec, {"fear_greed_index": 55})
    _, grounded_review = reviewer.review(grounded_spec, {"fear_greed_index": 55})

    assert novel_review["novelty_score"] > grounded_review["novelty_score"]
    assert grounded_review["final_score"] > novel_review["final_score"]


def test_reviewer_accept_guardrail_blocks_high_novelty_but_weak_execution():
    reviewer = MultiAgentStrategyReviewer()

    novelty_heavy_spec = StrategySpec(
        strategy_type="dsl_rule",
        params={
            "dsl": {
                "entry": {"all": []},
                "exit": {"any": []},
                "metadata": {"target_symbols": ["600519"]},
            }
        },
        name="novelty-heavy",
        tags=["external_llm"],
        metadata={
            "research_task": {
                "preferred_strategy_types": ["dsl_rule"],
                "allowed_strategy_types": ["dsl_rule"],
                "target_symbols": ["600519"],
            },
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "portfolio_spec": {"position_assumption": "single_name_full_notional"},
        },
    )

    reviewed, review = reviewer.review(novelty_heavy_spec, {"fear_greed_index": 70})

    assert reviewed is not None
    assert review["decision"] == "revise"
    assert "execution_floor_failed" in review["accept_blockers"]
    assert review["novelty_score"] > 0.6
