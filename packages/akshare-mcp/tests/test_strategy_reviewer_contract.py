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


def _semantic_ready_spec(*, confidence_contract=None, unsupported_rule_count=0):
    params = {
        "dsl": {
            "entry": {"all": []},
            "exit": {"any": []},
            "metadata": {"target_symbols": ["600519"]},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
        },
        "evidence_alignment_audit": {
            "evidence_alignment_score": 0.91,
            "semantic_integrity_score": 0.87,
            "hard_fail_reasons": [],
            "proxy_dependency_score": 0.0,
            "proxy_only_event_claim_count": 0,
        },
        "dsl_support_audit": {
            "unsupported_rule_count": unsupported_rule_count,
            "unsupported_fields": [],
            "unsupported_indicators": [],
            "unsupported_compare_ops": [],
            "unsupported_binary_ops": [],
            "malformed_node_count": 0,
            "fallback_node_count": 0,
        },
        "claim_to_trade_plan_map": {
            "claim_to_trade_step_ids": {"claim_uptrend": ["entry_step_1", "exit_step_1"]},
            "trade_step_to_claim_ids": {
                "entry_step_1": ["claim_uptrend"],
                "exit_step_1": ["claim_uptrend"],
            },
        },
        "trade_plan_to_dsl_map": {
            "trade_step_to_dsl_sections": {
                "entry_step_1": ["entry"],
                "exit_step_1": ["exit"],
            }
        },
        "runtime_playbook": {
            "entry_policy": {"order_style": "marketable_limit"},
            "exit_policy": {"failure_exit_rule": "opposite_signal_or_breakout_failure"},
            "adverse_move_policy": {"average_down": "forbid"},
            "reentry_policy": {"cooldown_days": 3},
            "position_policy": {"budget_mode": "fixed_fraction"},
            "incubation_policy": {"warmup_target_signals": 20},
            "source_claim_ids": ["claim_uptrend"],
            "source_trade_step_ids": ["entry_step_1", "exit_step_1"],
            "derived_from_defaults": False,
            "derivation_labels": ["runtime_playbook_provided", "trade_plan_driven", "claim_linked"],
            "_provenance": {
                "source_claim_ids": ["claim_uptrend"],
                "source_trade_step_ids": ["entry_step_1", "exit_step_1"],
                "derived_from_defaults": False,
                "derivation_labels": ["runtime_playbook_provided", "trade_plan_driven", "claim_linked"],
            },
        },
    }
    if confidence_contract is not None:
        params["confidence_contract"] = confidence_contract
    return StrategySpec(
        strategy_type="dsl_rule",
        params=params,
        name="semantic-ready",
        tags=["external_llm"],
        metadata={
            "research_task": {
                "preferred_strategy_types": ["dsl_rule"],
                "allowed_strategy_types": ["dsl_rule"],
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


def test_reviewer_rejects_when_dsl_support_audit_finds_unsupported_rules():
    reviewer = MultiAgentStrategyReviewer()
    contract = {
        "contract_version": "p2-stable/v1",
        "prediction_quality": {
            "support_samples": 120,
            "quality": "high",
            "contract_version": "p2-stable/v1",
            "contract_version_stable": True,
        },
    }

    reviewed, review = reviewer.review(
        _semantic_ready_spec(confidence_contract=contract, unsupported_rule_count=2),
        {"fear_greed_index": 55},
    )

    assert reviewed is None
    assert review["decision"] == "reject"
    assert review["semantic_context"]["unsupported_rule_count"] == 2
    assert "dsl_contains_unsupported_rules" in review["semantic_issues"]


def test_reviewer_revises_when_confidence_contract_is_missing_even_if_semantics_are_strong():
    reviewer = MultiAgentStrategyReviewer()

    reviewed, review = reviewer.review(
        _semantic_ready_spec(confidence_contract=None, unsupported_rule_count=0),
        {"fear_greed_index": 55},
    )

    assert reviewed is not None
    assert review["decision"] == "revise"
    assert review["confidence_contract_status"] == "missing"
    assert review["semantic_consistency_score"] < 0.75
    assert "confidence_contract_missing" in review["semantic_issues"]


def test_reviewer_revises_when_compile_stable_outputs_are_incomplete():
    reviewer = MultiAgentStrategyReviewer()
    spec = _semantic_ready_spec(
        confidence_contract={
            "contract_version": "p2-stable/v1",
            "prediction_quality": {
                "support_samples": 120,
                "quality": "high",
                "contract_version": "p2-stable/v1",
                "contract_version_stable": True,
            },
        }
    )
    spec.params.pop("claim_to_trade_plan_map", None)
    spec.params.pop("trade_plan_to_dsl_map", None)
    spec.params["runtime_playbook"] = {"entry_policy": {"order_style": "marketable_limit"}}

    reviewed, review = reviewer.review(spec, {"fear_greed_index": 55})

    assert reviewed is not None
    assert review["decision"] == "revise"
    assert "compile_stable_contract_missing" in review["accept_blockers"]
    assert any(item.startswith("compile_stable_field_missing:claim_to_trade_plan_map") for item in review["semantic_issues"])


def test_reviewer_blocks_single_name_trend_without_compiled_dsl():
    reviewer = MultiAgentStrategyReviewer()
    spec = StrategySpec(
        strategy_type="ma_cross",
        params={
            "short_period": 5,
            "long_period": 20,
            "target_symbols": ["688981"],
            "evidence_alignment_audit": {
                "evidence_alignment_score": 0.92,
                "semantic_integrity_score": 0.9,
                "hard_fail_reasons": [],
                "proxy_dependency_score": 0.0,
                "proxy_only_event_claim_count": 0,
            },
            "dsl_support_audit": {
                "unsupported_rule_count": 0,
                "unsupported_fields": [],
                "unsupported_indicators": [],
                "unsupported_compare_ops": [],
                "unsupported_binary_ops": [],
                "malformed_node_count": 0,
                "fallback_node_count": 0,
            },
            "claim_to_trade_plan_map": {
                "claim_to_trade_step_ids": {"claim_trend": ["entry_step_1", "exit_step_1"]},
                "trade_step_to_claim_ids": {
                    "entry_step_1": ["claim_trend"],
                    "exit_step_1": ["claim_trend"],
                },
            },
            "trade_plan_to_dsl_map": {
                "trade_step_to_dsl_sections": {
                    "entry_step_1": ["entry"],
                    "exit_step_1": ["exit"],
                }
            },
            "runtime_playbook": {
                "entry_policy": {"order_style": "marketable_limit"},
                "exit_policy": {"failure_exit_rule": "opposite_signal_or_breakout_failure"},
                "adverse_move_policy": {"average_down": "forbid"},
                "reentry_policy": {"cooldown_days": 5},
                "position_policy": {"budget_mode": "fixed_fraction"},
                "incubation_policy": {"warmup_target_signals": 6},
                "source_claim_ids": ["claim_trend"],
                "source_trade_step_ids": ["entry_step_1", "exit_step_1"],
                "derived_from_defaults": False,
                "derivation_labels": ["trade_plan_driven"],
            },
            "confidence_contract": {
                "contract_version": "p2-stable/v1",
                "prediction_quality": {
                    "support_samples": 120,
                    "quality": "high",
                    "ece": 0.03,
                    "brier_score": 0.16,
                    "contract_version": "p2-stable/v1",
                    "contract_version_stable": True,
                },
            },
            "dsl_required": True,
            "dsl_compiled": False,
            "execution_semantic_mode": "builtin_legacy",
            "execution_semantic_gap": True,
            "execution_semantic_gap_reasons": [
                "compiled_dsl_missing_for_single_name_trend_strategy",
            ],
        },
        name="trend-without-compiled-dsl",
        tags=["external_llm"],
        metadata={
            "research_task": {
                "preferred_strategy_types": ["ma_cross"],
                "allowed_strategy_types": ["ma_cross"],
                "target_symbols": ["688981"],
            },
            "target_symbols": ["688981"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["688981"], "rationale": "任务单标的"},
            "holding_horizon": {"max_days": 48},
            "risk_rules": {"stop_loss_pct": 0.1, "max_holding_days": 48},
            "execution_assumptions": {
                "tradability_filter": True,
                "slippage_bps": 5,
                "slippage_model": "fixed",
                "capacity_bucket": "small",
                "capacity_participation_rate": 0.05,
                "adv_ratio_limit": 0.1,
            },
            "portfolio_spec": {
                "position_assumption": "single_name_full_notional",
                "target_weight_scheme": "single_name",
            },
        },
    )

    reviewed, review = reviewer.review(spec, {"fear_greed_index": 62})

    assert reviewed is None
    assert review["decision"] == "reject"
    assert "execution_semantic_gap" in review["accept_blockers"]
    assert "compile_stable_contract_missing" in review["accept_blockers"]
    assert "execution_semantic_gap" in review["semantic_issues"]
    assert "final_strategy_missing_semantic_contract" in review["semantic_context"]["hard_fail_reasons"]
    assert any(item.startswith("compile_stable_field_missing:compiled_dsl") for item in review["semantic_issues"])


def test_reviewer_blocks_parameter_coherence_failure_and_execution_conversion_weak():
    reviewer = MultiAgentStrategyReviewer()
    spec = _semantic_ready_spec(
        confidence_contract={
            "contract_version": "p2-stable/v1",
            "prediction_quality": {
                "support_samples": 120,
                "quality": "high",
                "contract_version": "p2-stable/v1",
                "contract_version_stable": True,
            },
        }
    )
    spec.strategy_type = "ma_cross"
    spec.params.update(
        {
            "regime_filter_contract": {
                "quantified": True,
                "filters": [{"metric": "trend_efficiency_60d_realized", "op": "gte", "value": 0.2}],
            },
            "parameter_coherence_audit": {
                "status": "failed",
                "blockers": ["stop_vs_atr_too_tight"],
                "warnings": [],
            },
            "thesis_invalidation_contract": {
                "invalidates_when": [{"reason": "signal_failure_exit"}],
            },
            "drawdown_invalidation_contract": {
                "review_drawdown_pct": 0.18,
                "kill_drawdown_pct": 0.26,
                "apply_as_hard_gate": True,
            },
        }
    )
    spec.metadata["execution_quality"] = {
        "signal_to_order_conversion": 0.18,
        "filled_order_ratio": 0.52,
        "trade_expectancy": -0.01,
        "pnl_conversion_efficiency": 0.18,
        "execution_conversion_efficiency": 0.12,
    }

    reviewed, review = reviewer.review(spec, {"fear_greed_index": 62})

    assert reviewed is None
    assert review["decision"] == "reject"
    assert "parameter_coherence_audit_failed" in review["accept_blockers"]
    assert "execution_conversion_floor_failed" in review["accept_blockers"]
    assert "parameter_coherence_audit_failed" in review["semantic_issues"]
    assert "final_strategy_missing_semantic_contract" in review["semantic_context"]["hard_fail_reasons"]
    assert "execution_conversion_efficiency_weak" in review["execution_issues"]
