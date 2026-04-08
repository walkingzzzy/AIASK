from strategy_factory.application.candidate_contract import (
    apply_resolved_candidate_envelope,
    build_alpha_identity_components,
    build_candidate_contract_hash,
    build_candidate_contract_backfill,
    build_candidate_identity_signature,
    build_execution_contract_hash,
    build_portfolio_candidate_contract,
    build_tested_object_hash,
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
    assert build_tested_object_hash(candidate_a) == build_tested_object_hash(candidate_b)
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
    assert build_tested_object_hash(base_candidate) == build_tested_object_hash(revised_candidate)
    assert build_candidate_identity_signature(base_candidate) != build_candidate_identity_signature(revised_candidate)


def test_tested_object_hash_changes_when_alpha_logic_changes_under_same_contract():
    base_candidate = {
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["600519"],
        },
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
            "target_symbols": ["600519"],
            "validation_focus": "target_plus_representative",
        },
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 9}},
                "metadata": {"target_symbols": ["600519"], "strategy_tags": ["trend"]},
            }
        },
    }
    revised_candidate = {
        **base_candidate,
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 12}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "metadata": {"target_symbols": ["600519"], "strategy_tags": ["trend", "revised"]},
            }
        },
    }

    assert build_candidate_contract_hash(base_candidate) == build_candidate_contract_hash(revised_candidate)
    assert build_execution_contract_hash(base_candidate) == build_execution_contract_hash(revised_candidate)
    assert build_tested_object_hash(base_candidate) != build_tested_object_hash(revised_candidate)
    assert build_candidate_identity_signature(base_candidate) != build_candidate_identity_signature(revised_candidate)


def test_alpha_identity_components_expose_explicit_signatures_for_dsl_variants():
    base_candidate = {
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["600519"],
        },
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
            "target_symbols": ["600519"],
            "validation_focus": "target_plus_representative",
        },
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 9}},
            }
        },
    }
    revised_candidate = {
        **base_candidate,
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 12}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 10}},
            }
        },
    }

    base_components = build_alpha_identity_components(base_candidate)
    revised_components = build_alpha_identity_components(revised_candidate)

    assert base_components["logic_signature"]
    assert base_components["dsl_signature"]
    assert base_components["entry_exit_signature"]
    assert base_components["factor_signature"] is None
    assert base_components["logic_signature"] != revised_components["logic_signature"]
    assert base_components["dsl_signature"] != revised_components["dsl_signature"]
    assert base_components["entry_exit_signature"] != revised_components["entry_exit_signature"]


def test_candidate_contract_backfill_marks_missing_logic_as_partial():
    candidate = {
        "strategy_type": "momentum",
        "target_symbols": ["600519"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["600519"],
        },
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519"],
            "validation_focus": "target_plus_representative",
        },
    }

    backfill = build_candidate_contract_backfill(candidate)

    assert backfill["candidate_contract_snapshot"]["targeting"]["target_pool_id"] == "explicit:600519"
    assert backfill["candidate_contract_hash"] == backfill["execution_contract_hash"]
    assert backfill["logic_signature"]
    assert backfill["legacy_identity_partial"] is True
    assert backfill["tested_object_backfill_incomplete"] is True


def test_apply_resolved_candidate_envelope_backfills_governance_contract_fields():
    candidate = apply_resolved_candidate_envelope(
        {
            "strategy_type": "ma_cross",
            "target_symbols": ["600519"],
            "research_task": {
                "task_source": "event_driven",
                "target_symbols": ["600519"],
            },
            "constraint_check": {
                "coverage_ratio": 1.0,
                "intersection_ratio": 1.0,
                "target_overlap_count": 1,
            },
        }
    )

    assert candidate["validation_profile"]["profile"] == "event_trade_validation"
    assert candidate["validation_profile"]["validation_focus"] == "event_target_only"
    assert candidate["params"]["validation_profile"]["profile"] == "event_trade_validation"
    assert candidate["targeting_policy"]["target_symbol_policy"] == "strict_intersection"
    assert candidate["targeting_policy"]["universe_expansion_policy"] == "allow_same_theme_only"
    assert candidate["targeting_policy"]["coverage_ratio"] == 1.0
    assert candidate["params"]["targeting_policy"]["validation_focus"] == "event_target_only"


def test_build_portfolio_candidate_contract_compacts_research_task_factor_research_metadata():
    candidate = {
        "strategy_type": "rsi",
        "target_symbols": ["600519", "000858"],
        "stock_pool": {
            "selection_mode": "explicit",
            "symbols": ["600519", "000858"],
        },
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858"],
            "metadata": {
                "factor_research": {
                    "active_factors": ["rsi_14", "turnover_ratio"],
                    "preferred_strategy_types": ["rsi", "momentum"],
                    "summary": {
                        "top_factor_names": ["rsi_14"],
                        "candidate_pool_size": 24,
                    },
                    "governed_candidates": [{"id": f"cand_{idx}"} for idx in range(50)],
                }
            },
        },
    }

    contract = build_portfolio_candidate_contract(candidate)
    factor_research = contract["research_task"]["metadata"]["factor_research"]

    assert factor_research["top_factor_names"] == ["rsi_14"]
    assert factor_research["preferred_strategy_types"] == ["rsi", "momentum"]
    assert factor_research["candidate_pool_size"] == 24
    assert "governed_candidates" not in factor_research
