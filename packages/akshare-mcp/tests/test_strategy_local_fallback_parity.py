from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator, RuleStrategyGenerator


def test_local_fallback_candidate_keeps_factory_contract_fields():
    generator = LLMProxyStrategyGenerator()
    spec = generator._local_candidate_to_spec(
        {
            "name": "事件动量候选",
            "description": "事件后延续性机会。",
            "category": "event",
            "rationale": "主题催化后的强势股通常会在短窗口内延续。",
            "engine": "local_rule_v1",
            "target_symbols": ["600519", "000858"],
        },
        research_task={
            "task_id": "task_evt_1",
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "baijiu",
            "target_symbols": ["600519", "000858"],
        },
    )

    assert spec is not None
    candidate = spec.to_candidate("strategy_factory:test", "exp_local_fallback")

    assert candidate["hypothesis"]
    assert candidate["holding_horizon"]["max_days"] == 10
    assert candidate["risk_rules"]["max_holding_days"] == 10
    assert candidate["trade_plan"]["entry_bias"] == "event_follow_through"
    assert candidate["portfolio_spec"]["target_weight_scheme"] == "equal_weight"
    assert candidate["execution_assumptions"]["tradability_filter"] is True
    assert candidate["validation_profile"]["profile"] == "event_trade_validation"
    assert candidate["targeting_policy"]["target_symbol_policy"] == "strict_intersection"
    assert candidate["constraint_check"]["target_symbol_policy"] == "strict_intersection"
    assert candidate["stock_pool"]["symbols"] == ["600519", "000858"]
    assert candidate["params"]["target_symbols"] == ["600519", "000858"]
    assert candidate["params"]["stock_pool"]["symbols"] == ["600519", "000858"]
    assert candidate["params"]["research_task"]["event_id"] == "evt_1"
    assert candidate["market_regime_assumption"]
    assert candidate["position_sizing_rationale"]
    assert candidate["capacity_bucket"] in {"small", "mid", "large"}
    assert candidate["turnover_cost_class"] in {"low_touch", "medium_touch", "high_touch"}


def test_local_fallback_expands_breakout_and_reversal_into_new_families():
    generator = LLMProxyStrategyGenerator()

    breakout_spec = generator._local_candidate_to_spec(
        {
            "name": "板块轮动候选",
            "description": "事件催化后优先做板块内轮动。",
            "category": "event",
            "rationale": "催化扩散时，龙头和跟随股会在板块内轮动接力。",
            "engine": "local_rule_v1",
            "target_symbols": ["688981", "002371"],
        },
        research_task={
            "task_id": "task_breakout",
            "task_source": "snapshot",
            "opportunity_type": "sector_breakout",
            "target_symbols": ["688981", "002371"],
        },
    )
    reversal_spec = generator._local_candidate_to_spec(
        {
            "name": "超跌修复候选",
            "description": "冷门板块超跌回补。",
            "category": "reversal",
            "rationale": "超跌后常出现缺口回补与短期均值回归。",
            "engine": "local_rule_v1",
            "target_symbols": ["600036", "601166"],
        },
        research_task={
            "task_id": "task_repair",
            "task_source": "snapshot",
            "opportunity_type": "oversold_repair",
            "target_symbols": ["600036", "601166"],
        },
    )
    volatility_spec = generator._local_candidate_to_spec(
        {
            "name": "波动突破候选",
            "description": "因子加速阶段更适合波动突破。",
            "category": "volatility",
            "rationale": "波动收敛后更容易出现有效突破。",
            "engine": "local_rule_v1",
            "target_symbols": ["300750", "002594"],
        },
        research_task={
            "task_id": "task_factor",
            "task_source": "snapshot",
            "opportunity_type": "factor_acceleration",
            "target_symbols": ["300750", "002594"],
        },
    )

    assert breakout_spec is not None
    assert reversal_spec is not None
    assert volatility_spec is not None
    assert breakout_spec.strategy_type == "sector_rotation"
    assert reversal_spec.strategy_type == "gap_fill"
    assert volatility_spec.strategy_type == "volatility_breakout"

    breakout_candidate = breakout_spec.to_candidate("strategy_factory:test", "exp_breakout")
    volatility_candidate = volatility_spec.to_candidate("strategy_factory:test", "exp_volatility")

    assert breakout_candidate["generation_reason"]["template_generation_profile"] == "conservative_rotation"
    assert breakout_candidate["generation_reason"]["rule_template_contract"]["portfolio_weight_method"] == "sector_score_tilt"
    assert volatility_candidate["generation_reason"]["template_generation_profile"] == "conservative_breakout"
    assert volatility_candidate["generation_reason"]["rule_template_contract"]["target_layer"] == "target"
    assert breakout_candidate["holding_horizon"]["max_days"] >= 20
    assert breakout_candidate["rebalance_rule"]["mode"] == "periodic_rebalance"
    assert breakout_candidate["rebalance_rule"]["frequency_days"] >= 5
    assert volatility_candidate["holding_horizon"]["max_days"] >= 20
    assert volatility_candidate["rebalance_rule"]["mode"] == "periodic_rebalance"


def test_local_fallback_precompile_rejects_outside_allowed_strategy_types():
    generator = LLMProxyStrategyGenerator()
    candidate = {
        "name": "超跌修复候选",
        "description": "冷门板块超跌回补。",
        "category": "reversal",
        "rationale": "超跌后常出现缺口回补与短期均值回归。",
        "engine": "local_rule_v1",
        "target_symbols": ["600036"],
    }

    spec = generator._local_candidate_to_spec(
        candidate,
        research_task={
            "task_id": "task_single_target_guard",
            "task_source": "snapshot",
            "target_symbols": ["600036"],
            "allowed_strategy_types": ["momentum"],
        },
    )

    assert spec is None
    assert candidate["_generator_precompile_reject_reasons"] == ["outside_allowed_strategy_types"]


def test_local_fallback_specializes_quality_and_trend_families_for_ab_quality():
    generator = LLMProxyStrategyGenerator()

    quality_spec = RuleStrategyGenerator._build_rule_spec(
        "quality_factor",
        fg=55,
        regime="neutral",
        source="factor_research",
        factor_summary={"top_factor_names": ["quality_factor"]},
    )
    trend_spec = generator._local_candidate_to_spec(
        {
            "name": "均线趋势候选",
            "description": "趋势扩张且量能确认。",
            "category": "trend",
            "rationale": "均线张口扩大且量能配合时，趋势跟随更稳定。",
            "engine": "local_rule_v1",
            "target_symbols": ["300750", "601012"],
        },
        research_task={
            "task_id": "task_trend_ab",
            "task_source": "snapshot",
            "opportunity_type": "industry_leadership",
            "target_symbols": ["300750", "601012"],
        },
    )

    assert quality_spec is not None
    assert trend_spec is not None

    quality_candidate = quality_spec.to_candidate("strategy_factory:test", "exp_quality_ab")
    trend_candidate = trend_spec.to_candidate("strategy_factory:test", "exp_trend_ab")

    assert quality_candidate["strategy_type"] == "quality_factor"
    assert quality_candidate["holding_horizon"]["max_days"] >= 84
    assert quality_candidate["rebalance_rule"]["frequency_days"] >= 21
    assert quality_candidate["validation_profile"]["validation_focus"] == "candidate_target_only"
    assert quality_candidate["family_specialization"]["quality_drift_detection"]
    assert quality_candidate["family_specialization"]["quality_trend_resonance"]
    assert quality_candidate["family_specialization"]["peer_selection_mode"] == "target_plus_dynamic_family_peer"

    assert trend_candidate["strategy_type"] == "ma_cross"
    assert trend_candidate["rebalance_rule"]["frequency_days"] >= 7
    assert trend_candidate["family_specialization"]["range_filter"]
    assert trend_candidate["family_specialization"]["volume_confirmation"]


def test_local_fallback_momentum_uses_slower_medium_horizon_profile():
    momentum_spec = RuleStrategyGenerator._build_rule_spec(
        "momentum",
        fg=68,
        regime="greed",
        source="factor_research",
        factor_summary={"top_factor_names": ["momentum"]},
    )

    assert momentum_spec is not None

    momentum_candidate = momentum_spec.to_candidate("strategy_factory:test", "exp_momentum_medium")

    assert momentum_candidate["strategy_type"] == "momentum"
    assert momentum_candidate["holding_horizon"]["min_days"] >= 14
    assert momentum_candidate["holding_horizon"]["max_days"] >= 42
    assert momentum_candidate["rebalance_rule"]["mode"] == "periodic_rebalance"
    assert momentum_candidate["rebalance_rule"]["frequency_days"] >= 14
    assert momentum_candidate["risk_rules"]["max_holding_days"] >= 42
    assert momentum_candidate["family_specialization"]["holding_bias"].startswith("hold_for_")
