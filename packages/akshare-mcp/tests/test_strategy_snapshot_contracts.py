from akshare_mcp.services._strategy_generators_generate import _normalize_snapshot_pipeline_candidate


def test_snapshot_candidate_applies_high_vol_growth_atr_risk_contract():
    candidate = {
        "strategy_type": "volatility_breakout",
        "research_task": {
            "task_source": "snapshot",
            "pool_profile": "high_vol_growth",
            "volatility_bucket": "high",
            "liquidity_bucket": "high_liquidity",
            "target_symbols": ["601138"],
            "allowed_strategy_types": ["volatility_breakout", "gap_fill", "mean_reversion_short"],
        },
        "target_symbols": ["601138"],
        "risk_rules": {},
        "holding_horizon": {},
    }

    normalized = _normalize_snapshot_pipeline_candidate(candidate)

    assert normalized is not None
    assert normalized["risk_rules"]["stop_loss_mode"] == "atr_bucketed"
    assert normalized["risk_rules"]["atr_multiplier"] == 2.2
    assert normalized["risk_rules"]["time_stop_days"] == 8
    assert normalized["holding_horizon"]["max_days"] == 8
    assert normalized["pool_profile"] == "high_vol_growth"


def test_snapshot_candidate_blocks_ma_cross_in_high_vol_growth_pool():
    candidate = {
        "strategy_type": "ma_cross",
        "research_task": {
            "task_source": "snapshot",
            "pool_profile": "high_vol_growth",
            "volatility_bucket": "high",
            "liquidity_bucket": "high_liquidity",
            "target_symbols": ["601138"],
            "allowed_strategy_types": ["ma_cross"],
        },
        "target_symbols": ["601138"],
        "params": {"short_period": 6, "long_period": 24},
    }

    assert _normalize_snapshot_pipeline_candidate(candidate) is None
