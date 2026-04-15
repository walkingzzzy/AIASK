from akshare_mcp.services.strategy_hypothesis_generator import LLMHypothesisGenerator


def test_llm_hypothesis_generator_builds_structured_artifact_from_candidate_contract():
    result = LLMHypothesisGenerator.build(
        {
            "name": "structured-rsi",
            "strategy_type": "rsi",
            "hypothesis": "超跌修复更容易在 5-8 个交易日内兑现。",
            "target_symbols": ["603855", "603279"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["603855", "603279"],
            },
            "holding_horizon": {
                "max_days": 8,
                "rationale": "信号半衰期集中在一周左右。",
            },
            "trade_plan": {
                "entry_bias": "oversold_reversal",
                "exit_bias": "signal_or_time_stop",
            },
            "risk_rules": {
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "max_holding_days": 8,
            },
            "position_sizing": {
                "mode": "equal_weight",
                "position_assumption": "equal_weight_proxy",
            },
            "portfolio_spec": {
                "position_assumption": "equal_weight_proxy",
                "target_weight_scheme": "equal_weight",
                "max_position_pct": 0.2,
            },
            "execution_assumptions": {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_plus_representative",
                "primary_validation_layer": "target",
            },
        },
        research_task={
            "task_source": "snapshot",
            "task_id": "task_hypothesis_structured",
            "target_symbols": ["603855", "603279"],
        },
        provider_payload={"provider": "mock", "model": "mock-l2"},
    )

    assert result.accepted is True
    artifact = result.to_artifact()
    assert artifact["artifact_id"].startswith("hyp_")
    assert artifact["alpha_hypothesis"] == "超跌修复更容易在 5-8 个交易日内兑现。"
    assert artifact["family_hint"] == "rsi"
    assert artifact["alpha_half_life"] == 8.0
    assert artifact["cost_sensitivity_grid"]["base_case"]["slippage_bps"] == 5.0
    assert artifact["position_model"] == "equal_weight"
    assert artifact["validation_focus"] == "target_plus_representative"
    assert artifact["market_regime_assumption"]["preferred_regime"] == "short_term_dislocation_repair"
    assert artifact["economic_semantics_score"] == 100
    assert artifact["economic_semantics_complete"] is True


def test_llm_hypothesis_generator_rejects_when_economic_semantics_are_missing():
    result = LLMHypothesisGenerator.build(
        {
            "name": "broken-hypothesis",
            "strategy_type": "momentum",
            "hypothesis": "趋势可能延续。",
            "target_symbols": ["600519"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["600519"],
            },
        },
        research_task={
            "task_source": "snapshot",
            "task_id": "task_hypothesis_reject",
            "target_symbols": ["600519"],
        },
    )

    assert result.accepted is False
    assert "hypothesis_missing:holding_rationale" in result.reject_reasons
    assert "hypothesis_missing:cost_sensitivity_grid" in result.reject_reasons
    assert "hypothesis_missing:position_model" in result.reject_reasons


def test_llm_hypothesis_generator_populates_family_specific_hypothesis_for_momentum():
    result = LLMHypothesisGenerator.build(
        {
            "name": "structured-momentum",
            "strategy_type": "momentum",
            "hypothesis": "趋势扩张后更容易延续。",
            "target_symbols": ["300750"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["300750"],
            },
            "holding_horizon": {
                "min_days": 8,
                "max_days": 24,
                "rationale": "趋势通常需要两到四周扩散。",
            },
            "trade_plan": {
                "entry_bias": "trend_persistence_confirmation",
                "exit_bias": "false_breakout_or_momentum_decay",
            },
            "risk_rules": {
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.18,
                "max_holding_days": 24,
            },
            "position_sizing": {
                "mode": "equal_weight",
                "position_assumption": "equal_weight_proxy",
            },
            "portfolio_spec": {
                "position_assumption": "equal_weight_proxy",
                "target_weight_scheme": "equal_weight",
                "max_position_pct": 0.18,
            },
            "execution_assumptions": {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "candidate_target_only",
                "primary_validation_layer": "target",
            },
        },
        research_task={
            "task_source": "snapshot",
            "task_id": "task_hypothesis_momentum",
            "target_symbols": ["300750"],
            "allowed_strategy_types": ["momentum"],
        },
        provider_payload={"provider": "mock", "model": "mock-l2"},
    )

    assert result.accepted is True
    artifact = result.to_artifact()
    assert artifact["family_hint"] == "momentum"
    assert artifact["family_specific_complete"] is True
    assert artifact["family_specific_hypothesis"]["trend_persistence_logic"]
    assert artifact["family_specific_hypothesis"]["failure_scenario"]
    assert artifact["family_specific_hypothesis"]["false_breakout_filter"]


def test_llm_hypothesis_generator_rejects_prediction_contract_without_evidence_ids():
    result = LLMHypothesisGenerator.build(
        {
            "name": "semantic-broken",
            "strategy_type": "dsl_rule",
            "hypothesis": "趋势证据支持事件后的跟随。",
            "target_symbols": ["600519"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["600519"],
            },
            "holding_horizon": {"max_days": 5, "rationale": "事件后短窗口交易。"},
            "trade_plan": {
                "entry_bias": "event_follow_through",
                "exit_bias": "signal_or_time_stop",
            },
            "risk_rules": {
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "max_holding_days": 5,
            },
            "position_sizing": {
                "mode": "single_name",
                "position_assumption": "single_name_full_notional",
            },
            "portfolio_spec": {
                "position_assumption": "single_name_full_notional",
                "target_weight_scheme": "single_name",
                "max_position_pct": 0.25,
            },
            "execution_assumptions": {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_only",
                "primary_validation_layer": "target",
            },
            "prediction_contract": {
                "claims": [{"claim_id": "claim_1", "expected_move": "up", "evidence_ids": []}],
            },
        },
        research_task={
            "task_source": "event_driven",
            "task_id": "task_hypothesis_semantic_missing_ids",
            "event_id": "evt_001",
            "target_symbols": ["600519"],
        },
    )

    assert result.accepted is False
    assert "prediction_contract_missing_evidence_ids:claim_1" in result.reject_reasons


def test_llm_hypothesis_generator_requires_conflict_rule_for_mixed_claim_evidence():
    result = LLMHypothesisGenerator.build(
        {
            "name": "semantic-conflict",
            "strategy_type": "dsl_rule",
            "hypothesis": "事件后趋势跟随。",
            "target_symbols": ["600519"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["600519"],
            },
            "holding_horizon": {"max_days": 6, "rationale": "事件跟随后观察一周内兑现。"},
            "trade_plan": {
                "entry_bias": "event_follow_through",
                "exit_bias": "signal_or_time_stop",
            },
            "risk_rules": {
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "max_holding_days": 6,
            },
            "position_sizing": {
                "mode": "single_name",
                "position_assumption": "single_name_full_notional",
            },
            "portfolio_spec": {
                "position_assumption": "single_name_full_notional",
                "target_weight_scheme": "single_name",
                "max_position_pct": 0.25,
            },
            "execution_assumptions": {
                "commission_rate": 0.00025,
                "slippage_bps": 5,
                "tradability_filter": True,
                "slippage_model": "fixed",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_only",
                "primary_validation_layer": "target",
            },
            "evidence_chain": {
                "evidences": [
                    {"evidence_id": "ev_up", "direction": "up", "source_type": "news"},
                    {"evidence_id": "ev_down", "direction": "down", "source_type": "news"},
                ],
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_1",
                        "expected_move": "up",
                        "evidence_ids": ["ev_up", "ev_down"],
                    }
                ],
            },
        },
        research_task={
            "task_source": "event_driven",
            "task_id": "task_hypothesis_semantic_conflict",
            "event_id": "evt_002",
            "target_symbols": ["600519"],
        },
    )

    assert result.accepted is False
    assert "prediction_contract_missing_conflict_resolution_rule:claim_1" in result.reject_reasons
