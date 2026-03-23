from akshare_mcp.services.strategy_generators import LLMProxyStrategyGenerator


def test_local_fallback_candidate_keeps_factory_contract_fields():
    spec = LLMProxyStrategyGenerator._local_candidate_to_spec(
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
