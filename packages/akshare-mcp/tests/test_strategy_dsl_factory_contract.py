import pytest


def _minimal_dsl():
    return {
        "version": "1.0",
        "timeframe": "daily",
        "entry": {
            "all": [
                {
                    "op": "gt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 10},
                }
            ]
        },
        "exit": {
            "any": [
                {
                    "op": "lt",
                    "left": {"field": "close"},
                    "right": {"indicator": "sma", "field": "close", "window": 10},
                }
            ]
        },
    }


def test_compile_strategy_blueprint_rejects_missing_factory_contract_fields():
    from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

    with pytest.raises(ValueError, match="risk_rules"):
        compile_strategy_blueprint(
            {
                "name": "缺少风控",
                "hypothesis": "工厂候选",
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "dsl": _minimal_dsl(),
            },
            tune_for_factory=True,
        )

    with pytest.raises(ValueError, match="holding_horizon"):
        compile_strategy_blueprint(
            {
                "name": "事件缺少持有期",
                "hypothesis": "事件候选",
                "target_symbols": ["600519"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
                "research_task": {"task_source": "event_driven", "target_symbols": ["600519"]},
                "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
                "dsl": _minimal_dsl(),
            },
            tune_for_factory=True,
        )

    with pytest.raises(ValueError, match="rationale"):
        compile_strategy_blueprint(
            {
                "name": "扩池缺少理由",
                "hypothesis": "扩池候选",
                "target_symbols": ["600519", "000858"],
                "stock_pool": {"selection_mode": "explicit", "symbols": ["600519", "000858"]},
                "research_task": {"task_source": "snapshot", "target_symbols": ["600519"]},
                "holding_horizon": {"max_days": 10},
                "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
                "dsl": _minimal_dsl(),
            },
            tune_for_factory=True,
        )


def test_compile_strategy_blueprint_preserves_extended_factory_metadata():
    from akshare_mcp.services.strategy_dsl import compile_strategy_blueprint

    compiled = compile_strategy_blueprint(
        {
            "name": "完整工厂候选",
            "hypothesis": "趋势延续",
            "target_symbols": ["600519"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["600519"],
                "rationale": "只交易任务目标股票",
            },
            "holding_horizon": {"max_days": 10},
            "trade_plan": {"entry_bias": "trend_follow"},
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "position_sizing": {"mode": "single_name"},
            "execution_notes": "仅在流动性良好时段执行",
            "dsl": _minimal_dsl(),
        },
        tune_for_factory=True,
    )

    assert compiled["metadata"]["hypothesis"] == "趋势延续"
    assert compiled["metadata"]["holding_horizon"]["max_days"] == 10
    assert compiled["metadata"]["trade_plan"]["entry_bias"] == "trend_follow"
    assert compiled["metadata"]["risk_rules"]["stop_loss_pct"] == 0.08
    assert compiled["metadata"]["position_sizing"]["mode"] == "single_name"
    assert compiled["metadata"]["execution_notes"] == "仅在流动性良好时段执行"
