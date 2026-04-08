from strategy_factory.application.precompile_contract import (
    validate_precompile_candidate_contract,
)


def test_precompile_validator_accepts_single_target_snapshot_contract():
    candidate = {
        "strategy_type": "ma_cross",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
            "primary_validation_layer": "combined",
        },
        "constraint_check": {
            "coverage_ratio": 1.0,
            "intersection_ratio": 1.0,
            "target_overlap_count": 1,
        },
    }
    research_task = {
        "task_source": "snapshot",
        "target_symbols": ["600519"],
        "allowed_strategy_types": ["ma_cross"],
    }

    result = validate_precompile_candidate_contract(
        candidate,
        research_task=research_task,
        source="unit_test",
    )

    assert result.accepted is True
    assert result.reject_reasons == []
    assert result.normalized_research_task["target_symbol_policy"] == "strict_intersection"
    assert result.normalized_research_task["universe_expansion_policy"] == "forbid"
    assert result.target_alignment_contract["market_fallback_allowed"] is False
    assert result.target_alignment_contract["min_required_overlap_count"] == 1


def test_precompile_validator_rejects_single_target_snapshot_alignment_drift():
    candidate = {
        "strategy_type": "ma_cross",
        "target_symbols": ["000001"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["000001"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
        "constraint_check": {
            "coverage_ratio": 0.0,
            "intersection_ratio": 0.0,
            "target_overlap_count": 0,
        },
    }
    research_task = {
        "task_source": "snapshot",
        "target_symbols": ["600519"],
        "allowed_strategy_types": ["ma_cross"],
    }

    result = validate_precompile_candidate_contract(candidate, research_task=research_task)

    assert result.accepted is False
    assert "target_universe_alignment_too_low" in result.reject_reasons
    assert result.alignment_reject_reasons
    assert result.constraint_check["alignment_contract_ok"] is False


def test_precompile_validator_rejects_outside_allowed_strategy_types():
    candidate = {
        "strategy_type": "rsi",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
            "primary_validation_layer": "combined",
        },
        "constraint_check": {
            "coverage_ratio": 1.0,
            "intersection_ratio": 1.0,
            "target_overlap_count": 1,
        },
    }
    research_task = {
        "task_source": "snapshot",
        "target_symbols": ["600519"],
        "allowed_strategy_types": ["ma_cross"],
    }

    result = validate_precompile_candidate_contract(candidate, research_task=research_task)

    assert result.accepted is False
    assert result.reject_reasons == ["outside_allowed_strategy_types"]
