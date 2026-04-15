from strategy_factory.application.hypothesis_lowering_compiler import HypothesisLoweringCompiler
from strategy_factory.application.semantic_contract import audit_candidate_semantic_contract


def _valid_hypothesis() -> dict:
    return {
        "artifact_id": "hyp_test_valid",
        "alpha_hypothesis": "超跌修复在一周左右兑现。",
        "failure_mode": {
            "primary_failure_mode": "signal_or_time_stop",
            "stop_loss_pct": 0.05,
        },
        "target_universe_hypothesis": {
            "target_symbols": ["603855", "603279"],
            "target_symbol_policy": "prefer_intersection",
        },
        "family_hint": "rsi",
        "holding_rationale": "信号半衰期集中在 5-8 个交易日。",
        "alpha_half_life": 8,
        "cost_sensitivity_grid": {
            "base_case": {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            },
        },
        "position_model": "equal_weight",
        "capacity_assumption": {
            "max_position_pct": 0.2,
            "symbol_count": 2,
        },
        "market_regime_assumption": {
            "summary": "短期情绪失衡后的修复阶段更有效。",
            "preferred_regime": "short_term_dislocation_repair",
            "avoid_regime": "persistent_one_way_trend",
        },
        "validation_focus": "target_plus_representative",
    }


def _valid_candidate() -> dict:
    return {
        "name": "hypothesis-lowered-rsi",
        "strategy_type": "rsi",
        "target_symbols": ["603855", "603279"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["603855", "603279"],
        },
        "dsl": {
            "version": "1.0",
            "timeframe": "daily",
            "entry": {
                "any": [
                    {
                        "op": "lt",
                        "left": {"indicator": "rsi", "field": "close", "window": 6},
                        "right": {"value": 26},
                    }
                ]
            },
            "exit": {
                "any": [
                    {
                        "op": "gt",
                        "left": {"indicator": "rsi", "field": "close", "window": 6},
                        "right": {"value": 60},
                    }
                ]
            },
            "metadata": {},
        },
        "holding_horizon": {"max_days": 8},
        "trade_plan": {
            "entry_bias": "oversold_reversal",
            "exit_bias": "signal_or_time_stop",
        },
        "risk_rules": {
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.12,
            "max_holding_days": 8,
        },
        "rebalance_rule": {
            "mode": "signal_rebalance",
            "frequency_days": 2,
        },
        "tags": ["external_llm"],
    }


def test_hypothesis_lowering_compiler_builds_explicit_candidate_contract():
    result = HypothesisLoweringCompiler.lower(
        _valid_candidate(),
        hypothesis=_valid_hypothesis(),
        research_task={
            "task_source": "snapshot",
            "task_id": "task_l2_compile",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855", "603279", "002833", "601766"],
            "validation_focus": "target_plus_representative",
        },
    )

    assert result.accepted is True
    assert result.candidate["hypothesis_artifact_id"] == "hyp_test_valid"
    assert result.candidate["portfolio_spec"]["target_weight_scheme"] == "equal_weight"
    assert result.candidate["execution_assumptions"]["slippage_bps"] == 5.0
    assert result.candidate["validation_profile"]["validation_focus"] == "target_plus_representative"
    assert result.candidate["holding_rationale"] == "信号半衰期集中在 5-8 个交易日。"
    assert result.candidate["candidate_provenance"]["generator_mode"] == "llm_hypothesis_compiler"
    assert result.candidate["holding_horizon"]["cooldown_window_days"] >= 1
    assert result.candidate["expected_turnover_band"] == "high"
    assert result.candidate["capacity_bucket"] == "mid"
    assert result.candidate["turnover_cost_class"] == "medium_touch"
    assert result.candidate["position_sizing_rationale"]
    assert result.audit["derived_holding_profile"]["expected_turnover_band"] == "high"


def test_hypothesis_lowering_compiler_fails_closed_when_hypothesis_is_incomplete():
    hypothesis = _valid_hypothesis()
    hypothesis.pop("cost_sensitivity_grid")

    result = HypothesisLoweringCompiler.lower(
        _valid_candidate(),
        hypothesis=hypothesis,
        research_task={
            "task_source": "snapshot",
            "task_id": "task_l2_compile_reject",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855", "603279", "002833", "601766"],
        },
    )

    assert result.accepted is False
    assert "hypothesis_missing:cost_sensitivity_grid" in result.reject_reasons
    assert result.audit["rejected_at"] == "pre_lowering"


def test_hypothesis_lowering_compiler_requires_family_specific_hypothesis_for_momentum():
    hypothesis = _valid_hypothesis()
    hypothesis.update(
        {
            "family_hint": "momentum",
            "market_regime_assumption": {
                "summary": "趋势扩张阶段更有效。",
                "preferred_regime": "trend_expansion_with_persistence",
                "avoid_regime": "false_breakout_range_reversion",
            },
            "family_specific_hypothesis": {
                "trend_persistence_logic": "要求趋势斜率持续为正。",
                "false_breakout_filter": "需要量能确认。",
            },
        }
    )
    candidate = _valid_candidate()
    candidate["strategy_type"] = "momentum"
    candidate["name"] = "hypothesis-lowered-momentum"

    result = HypothesisLoweringCompiler.lower(
        candidate,
        hypothesis=hypothesis,
        research_task={
            "task_source": "snapshot",
            "task_id": "task_l2_compile_momentum_reject",
            "allowed_strategy_types": ["momentum"],
            "target_symbols": ["603855", "603279"],
            "validation_focus": "candidate_target_only",
        },
    )

    assert result.accepted is False
    assert "hypothesis_missing:family_specific_hypothesis.failure_scenario" in result.reject_reasons


def test_hypothesis_lowering_compiler_preserves_semantic_contract_fields():
    candidate = _valid_candidate()
    candidate.update(
        {
            "trade_plan": {
                "entry_bias": "oversold_reversal",
                "exit_bias": "signal_or_time_stop",
                "entry": {"node_id": "entry_1", "claim_ids": ["claim_1"], "evidence_ids": ["ev_1"]},
                "exit": {"node_id": "exit_1", "claim_ids": ["claim_1"]},
            },
            "dsl": {
                **candidate["dsl"],
                "entry": {
                    "trade_plan_node_id": "entry_1",
                    "any": candidate["dsl"]["entry"]["any"],
                },
                "exit": {
                    "trade_plan_node_id": "exit_1",
                    "any": candidate["dsl"]["exit"]["any"],
                },
            },
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev_1",
                        "source_type": "price_action",
                        "direction": "up",
                        "raw_confidence": 0.74,
                        "target_symbols": ["603855"],
                    }
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "expected_move": "up",
                        "expected_horizon": 8,
                        "evidence_ids": ["ev_1"],
                    }
                ]
            },
            "confidence_contract": {
                "prediction_quality": {"support_samples": 64, "ece": 0.05, "brier_score": 0.18}
            },
        }
    )

    result = HypothesisLoweringCompiler.lower(
        candidate,
        hypothesis=_valid_hypothesis(),
        research_task={
            "task_source": "snapshot",
            "task_id": "task_l2_compile_semantic_ok",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855", "603279"],
            "validation_focus": "target_plus_representative",
        },
    )

    assert result.accepted is True
    assert result.candidate["evidence_chain"]["evidences"][0]["evidence_id"] == "ev_1"
    assert result.candidate["prediction_contract"]["claims"][0]["claim_id"] == "claim_1"
    assert result.candidate["confidence_contract"]["prediction_quality"]["support_samples"] == 64
    assert result.candidate["evidence_alignment_audit"]["using_new_contract"] is True
    assert result.candidate["legacy_semantic_contract"] is False


def test_hypothesis_lowering_compiler_rejects_mixed_evidence_without_conflict_rule():
    candidate = _valid_candidate()
    candidate.update(
        {
            "trade_plan": {
                "entry_bias": "oversold_reversal",
                "exit_bias": "signal_or_time_stop",
                "entry": {"node_id": "entry_1", "claim_ids": ["claim_1"], "evidence_ids": ["ev_up", "ev_down"]},
                "exit": {"node_id": "exit_1", "claim_ids": ["claim_1"]},
            },
            "dsl": {
                **candidate["dsl"],
                "entry": {
                    "trade_plan_node_id": "entry_1",
                    "any": candidate["dsl"]["entry"]["any"],
                },
                "exit": {
                    "trade_plan_node_id": "exit_1",
                    "any": candidate["dsl"]["exit"]["any"],
                },
            },
            "evidence_chain": {
                "evidences": [
                    {"evidence_id": "ev_up", "source_type": "news", "direction": "up"},
                    {"evidence_id": "ev_down", "source_type": "news", "direction": "down"},
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "expected_move": "up",
                        "evidence_ids": ["ev_up", "ev_down"],
                    }
                ]
            },
        }
    )

    result = HypothesisLoweringCompiler.lower(
        candidate,
        hypothesis={**_valid_hypothesis(), "validation_focus": "event_target_only"},
        research_task={
            "task_source": "event_driven",
            "task_id": "task_l2_compile_conflict_rule_missing",
            "event_id": "evt_conflict_rule",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855", "603279"],
            "validation_focus": "event_target_only",
        },
    )

    assert result.accepted is False
    assert "prediction_contract_conflict_resolution_rule_missing" in result.reject_reasons
    assert result.audit["rejected_at"] == "semantic_contract"


def test_hypothesis_lowering_compiler_rejects_proxy_only_event_evidence():
    candidate = _valid_candidate()
    candidate.update(
        {
            "trade_plan": {
                "entry_bias": "event_follow_through",
                "exit_bias": "signal_or_time_stop",
                "entry": {"node_id": "entry_1", "claim_ids": ["claim_1"], "evidence_ids": ["ev_1"]},
                "exit": {"node_id": "exit_1", "claim_ids": ["claim_1"]},
            },
            "dsl": {
                **candidate["dsl"],
                "entry": {
                    "trade_plan_node_id": "entry_1",
                    "any": candidate["dsl"]["entry"]["any"],
                },
                "exit": {
                    "trade_plan_node_id": "exit_1",
                    "any": candidate["dsl"]["exit"]["any"],
                },
            },
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev_1",
                        "source_type": "news",
                        "direction": "up",
                        "proxy_only": True,
                    }
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "expected_move": "up",
                        "evidence_ids": ["ev_1"],
                    }
                ]
            },
        }
    )

    result = HypothesisLoweringCompiler.lower(
        candidate,
        hypothesis={**_valid_hypothesis(), "validation_focus": "event_target_only"},
        research_task={
            "task_source": "event_driven",
            "task_id": "task_l2_compile_proxy_only",
            "event_id": "evt_proxy_only",
            "allowed_strategy_types": ["rsi"],
            "target_symbols": ["603855"],
            "validation_focus": "event_target_only",
        },
    )

    assert result.accepted is False
    assert "proxy_only_event_evidence_not_allowed" in result.reject_reasons
    assert result.audit["rejected_at"] == "semantic_contract"


def test_semantic_contract_audit_rejects_lagging_trend_without_quantified_regime_and_temporal_mismatch():
    audit = audit_candidate_semantic_contract(
        {
            "strategy_type": "ma_cross",
            "holding_horizon": {"max_days": 20},
            "trade_plan": {
                "entry_bias": "golden cross confirmation",
                "entry": {"node_id": "entry_1", "claim_ids": ["claim_trend"], "evidence_ids": ["ev_price"]},
                "exit": {"node_id": "exit_1", "claim_ids": ["claim_trend"]},
            },
            "dsl": {
                "version": "1.0",
                "timeframe": "daily",
                "entry": {
                    "trade_plan_node_id": "entry_1",
                    "op": "cross_above",
                    "left": {"indicator": "sma", "field": "close", "window": 5},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                },
                "exit": {
                    "trade_plan_node_id": "exit_1",
                    "op": "cross_below",
                    "left": {"indicator": "sma", "field": "close", "window": 5},
                    "right": {"indicator": "sma", "field": "close", "window": 20},
                },
            },
            "evidence_chain": {
                "evidences": [
                    {
                        "evidence_id": "ev_price",
                        "source_type": "price_action",
                        "direction": "up",
                        "summary": "短均线上穿长均线",
                    }
                ]
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_trend",
                        "expected_move": "up",
                        "expected_horizon": 48,
                        "evidence_ids": ["ev_price"],
                    }
                ]
            },
            "market_regime_assumption": {
                "summary": "市场不处于明显震荡时更有效",
                "preferred_regime": "趋势较强",
                "avoid_regime": "明显震荡",
            },
        }
    )

    assert audit["lagging_entry_without_lead_evidence"]["status"] == "failed"
    assert audit["temporal_coherence_audit"]["status"] == "failed"
    assert audit["ambiguous_regime_condition_audit"]["status"] == "failed"
    assert "lagging_entry_without_lead_evidence" in audit["hard_fail_reasons"]
    assert "temporal_coherence_audit_failed" in audit["hard_fail_reasons"]
    assert "ambiguous_regime_condition_not_allowed" in audit["hard_fail_reasons"]
