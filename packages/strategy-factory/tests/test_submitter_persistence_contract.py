from strategy_factory.application.submitter import StrategySubmitter


def test_build_strategy_data_persists_extended_strategy_contract():
    submitter = StrategySubmitter()

    data = submitter._build_strategy_data(
        "sid_contract",
        "合同策略",
        {
            "strategy_type": "dsl_rule",
            "params": {"dsl": {"entry": {"all": []}, "exit": {"any": []}, "metadata": {}}},
            "target_symbols": ["600519"],
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"], "rationale": "只做任务标的"},
            "research_task": {
                "task_id": "task_evt_1",
                "task_source": "event_driven",
                "target_symbols": ["600519"],
                "event_id": "evt_1",
                "theme_code": "ai",
            },
            "hypothesis": "事件驱动顺势",
            "holding_horizon": {"max_days": 10},
            "trade_plan": {"entry_bias": "event_follow_through"},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "position_sizing": {"mode": "single_name"},
            "execution_notes": "仅在流动性良好时段执行",
            "rebalance_rule": {"mode": "event_driven_hold"},
            "portfolio_spec": {"position_assumption": "single_name_full_notional"},
            "execution_assumptions": {"slippage_bps": 8, "tradability_filter": True},
            "validation_profile": {"profile": "event_trade_validation", "validation_focus": "event_target_only"},
            "targeting_policy": {"target_symbol_policy": "strict_intersection"},
            "constraint_check": {"intersection_ratio": 1.0},
            "source_candidate_artifact_id": "candidate_001",
            "candidate_family": "sentiment",
            "validation_score": 83.5,
            "expected_regime": ["trend", "event"],
        },
        {},
    )

    params = data["params"]

    assert params["hypothesis"] == "事件驱动顺势"
    assert params["holding_horizon"]["max_days"] == 10
    assert params["trade_plan"]["entry_bias"] == "event_follow_through"
    assert params["risk_rules"]["stop_loss_pct"] == 0.08
    assert params["position_sizing"]["mode"] == "single_name"
    assert params["execution_notes"] == "仅在流动性良好时段执行"
    assert params["validation_profile"]["profile"] == "event_trade_validation"
    assert params["targeting_policy"]["target_symbol_policy"] == "strict_intersection"
    assert params["task_signature"].startswith("event_driven|evt_1|ai|")
    assert params["candidate_provenance"]["source_candidate_artifact_id"] == "candidate_001"
    assert params["candidate_provenance"]["candidate_family"] == "sentiment"
    assert params["candidate_provenance"]["validation_score"] == 83.5
    assert params["candidate_provenance"]["expected_regime"] == ["trend", "event"]
    assert params["source_candidate_artifact_id"] == "candidate_001"
    assert params["candidate_family"] == "sentiment"
    assert params["candidate_validation_score"] == 83.5
    assert params["expected_regime"] == ["trend", "event"]
