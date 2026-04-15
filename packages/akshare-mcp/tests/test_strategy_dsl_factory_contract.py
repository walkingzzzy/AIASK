import pytest
import pandas as pd


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
            "trade_plan": {
                "entry": {"node_id": "entry_step_1", "claim_ids": ["claim_uptrend"], "entry_bias": "trend_follow"},
                "exit": {"node_id": "exit_step_1", "claim_ids": ["claim_uptrend"]},
            },
            "prediction_contract": {
                "claims": [
                    {
                        "claim_id": "claim_uptrend",
                        "expected_move": "up",
                        "evidence_ids": ["ev_1"],
                    }
                ]
            },
            "risk_rules": {"stop_loss_pct": 0.08, "max_holding_days": 10},
            "position_sizing": {"mode": "single_name"},
            "execution_notes": "仅在流动性良好时段执行",
            "dsl": {
                **_minimal_dsl(),
                "entry": {
                    "all": [
                        {
                            "op": "gt",
                            "left": {"field": "close"},
                            "right": {"indicator": "sma", "field": "close", "window": 10},
                            "trade_plan_node_id": "entry_step_1",
                        }
                    ]
                },
                "exit": {
                    "any": [
                        {
                            "op": "lt",
                            "left": {"field": "close"},
                            "right": {"indicator": "sma", "field": "close", "window": 10},
                            "trade_plan_node_id": "exit_step_1",
                        }
                    ]
                },
            },
        },
        tune_for_factory=True,
    )

    assert compiled["metadata"]["hypothesis"] == "趋势延续"
    assert compiled["metadata"]["holding_horizon"]["max_days"] == 10
    assert compiled["metadata"]["trade_plan"]["entry"]["entry_bias"] == "trend_follow"
    assert compiled["metadata"]["risk_rules"]["stop_loss_pct"] == 0.08
    assert compiled["metadata"]["position_sizing"]["mode"] == "single_name"
    assert compiled["metadata"]["execution_notes"] == "仅在流动性良好时段执行"
    assert compiled["metadata"]["claim_to_trade_plan_map"]["claim_to_trade_step_ids"]["claim_uptrend"] == ["entry_step_1", "exit_step_1"]
    assert compiled["metadata"]["trade_plan_to_dsl_map"]["trade_step_to_dsl_sections"]["entry_step_1"] == ["entry"]
    assert compiled["metadata"]["trade_plan_to_dsl_map"]["trade_step_to_dsl_sections"]["exit_step_1"] == ["exit"]


def test_evaluate_dsl_masks_supports_trend_execution_indicators():
    from akshare_mcp.services.strategy_dsl import evaluate_dsl_masks

    frame = pd.DataFrame(
        [
            {
                "open": 99.7 + idx,
                "high": 100.15 + idx,
                "low": 99.55 + idx,
                "close": 100.0 + idx,
                "volume": 1000 + idx * 20,
                "turnover_rate": 1.35 + idx * 0.01,
            }
            for idx in range(18)
        ]
    )
    dsl = {
        "version": "1.0",
        "timeframe": "daily",
        "entry": {
            "all": [
                {
                    "op": "gte",
                    "left": {"indicator": "adx", "window": 5},
                    "right": {"value": 1.0},
                },
                {
                    "op": "gte",
                    "left": {"indicator": "turnover_rate", "window": 5},
                    "right": {"value": 1.2},
                },
                {
                    "op": "lt",
                    "left": {"indicator": "upper_shadow_ratio"},
                    "right": {"value": 0.35},
                },
                {
                    "op": "gt",
                    "left": {"indicator": "slope", "field": "close", "window": 5, "lookback": 2},
                    "right": {"value": 0.0},
                },
                {
                    "op": "gte",
                    "left": {
                        "indicator": "rolling_count",
                        "window": 5,
                        "condition": {
                            "op": "lt",
                            "left": {"indicator": "upper_shadow_ratio"},
                            "right": {"value": 0.35},
                        },
                    },
                    "right": {"value": 4.0},
                },
            ]
        },
        "exit": {
            "any": [
                {
                    "op": "lt",
                    "left": {"indicator": "slope", "field": "close", "window": 5, "lookback": 2},
                    "right": {"value": -0.5},
                }
            ]
        },
    }

    entry_mask, exit_mask = evaluate_dsl_masks(frame, dsl)

    assert bool(entry_mask[-1]) is True
    assert int(entry_mask.sum()) > 0
    assert bool(exit_mask[-1]) is False


def _market_frame(length: int) -> pd.DataFrame:
    rows = []
    for idx in range(length):
        close = 100 + idx * 0.3 + ((-1) ** idx) * 1.2
        rows.append(
            {
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "volume": 1000 + idx,
            }
        )
    return pd.DataFrame(rows)


def test_tune_strategy_dsl_prefers_predictive_edge_when_samples_are_sufficient():
    from akshare_mcp.services.strategy_dsl import tune_strategy_dsl

    tuned, metadata = tune_strategy_dsl(
        {
            **_minimal_dsl(),
            "metadata": {"holding_horizon": {"max_days": 10}},
        },
        _market_frame(120),
    )

    assert tuned
    assert metadata["selection_basis"] == "predictive_edge"
    assert metadata["primary_horizon"] == 10
    assert metadata["sample_count"] >= 20
    assert metadata["overall_skill"] is not None
    assert metadata["recent_skill"] is not None
    assert metadata["trade_expectancy"] is not None


def test_tune_strategy_dsl_falls_back_to_activity_when_predictive_samples_are_insufficient():
    from akshare_mcp.services.strategy_dsl import tune_strategy_dsl

    tuned, metadata = tune_strategy_dsl(
        {
            **_minimal_dsl(),
            "metadata": {"holding_horizon": {"max_days": 10}},
        },
        _market_frame(24),
    )

    assert tuned
    assert metadata["selection_basis"] == "activity_fallback"
    assert metadata["primary_horizon"] == 10
    assert metadata["sample_count"] == 0
    assert metadata["overall_skill"] is None
