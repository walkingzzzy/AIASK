from strategy_factory.application.candidate_contract import (
    build_candidate_contract_hash,
    build_candidate_identity_signature,
    build_portfolio_candidate_contract,
)


def test_candidate_contract_hash_ignores_target_order_and_dynamic_alignment_metrics():
    candidate_a = {
        "strategy_type": "momentum",
        "target_symbols": ["600519", "000858"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["600519", "000858"],
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
        "execution_assumptions": {
            "initial_capital": 1_000_000,
            "commission_rate": 0.00025,
            "tradability_filter": True,
        },
        "validation_profile": {
            "profile": "trade_rule_validation",
            "validation_focus": "target_plus_representative",
        },
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["600519", "000858"],
            },
            "validation_focus": "target_plus_representative",
        },
        "constraint_check": {
            "coverage_ratio": 0.25,
            "intersection_ratio": 0.4,
            "target_overlap_count": 1,
        },
    }
    candidate_b = {
        **candidate_a,
        "target_symbols": ["000858", "600519"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["000858", "600519"],
        },
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["000858", "600519"],
            "stock_pool": {
                "selection_mode": "explicit",
                "symbols": ["000858", "600519"],
            },
            "validation_focus": "target_plus_representative",
        },
        "constraint_check": {
            "coverage_ratio": 1.0,
            "intersection_ratio": 1.0,
            "target_overlap_count": 2,
        },
    }

    contract_a = build_portfolio_candidate_contract(candidate_a)
    contract_b = build_portfolio_candidate_contract(candidate_b)

    assert contract_a["targeting"]["target_pool_id"] == "explicit:000858,600519"
    assert contract_b["targeting"]["target_pool_id"] == "explicit:000858,600519"
    assert build_candidate_contract_hash(candidate_a) == build_candidate_contract_hash(candidate_b)
    assert build_candidate_contract_hash(contract=contract_a) == build_candidate_contract_hash(contract=contract_b)
    assert build_candidate_identity_signature(candidate_a) == build_candidate_identity_signature(candidate_b)


def test_candidate_contract_hash_changes_when_portfolio_semantics_change():
    base_candidate = {
        "strategy_type": "momentum",
        "target_symbols": ["600519", "000858"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["600519", "000858"],
        },
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
        },
        "execution_assumptions": {
            "initial_capital": 1_000_000,
            "commission_rate": 0.00025,
            "tradability_filter": True,
        },
        "validation_profile": {
            "profile": "trade_rule_validation",
            "validation_focus": "target_plus_representative",
        },
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858"],
            "validation_focus": "target_plus_representative",
        },
    }
    revised_candidate = {
        **base_candidate,
        "portfolio_spec": {
            "position_assumption": "target_weight_map_proxy",
            "target_weight_scheme": "target_weight_map",
            "target_weight_map": {"600519": 0.7, "000858": 0.3},
        },
    }

    assert build_candidate_contract_hash(base_candidate) != build_candidate_contract_hash(revised_candidate)
    assert build_candidate_identity_signature(base_candidate) != build_candidate_identity_signature(revised_candidate)
