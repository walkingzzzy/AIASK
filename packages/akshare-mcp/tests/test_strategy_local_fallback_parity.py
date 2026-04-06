from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator


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
