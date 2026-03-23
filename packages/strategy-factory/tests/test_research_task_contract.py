from strategy_factory.domain.targets import (
    _apply_target_symbol_policy,
    _normalize_research_task_contract,
)


def test_normalize_research_task_contract_for_event_task():
    task = _normalize_research_task_contract(
        {
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "ai",
            "target_symbols": ["600519", "000858"],
            "preferred_strategy_types": ["momentum", "ma_cross"],
            "allowed_strategy_types": ["momentum", "dsl_rule"],
        }
    )

    assert task["task_source"] == "event_driven"
    assert task["target_symbol_policy"] == "strict_intersection"
    assert task["universe_expansion_policy"] == "allow_same_theme_only"
    assert task["preference_strength"] == "medium"
    assert task["validation_focus"] == "event_target_only"
    assert task["allowed_strategy_types"] == ["momentum", "dsl_rule"]
    assert task["preference_reason"] == "event_theme_bias:momentum,ma_cross"
    assert task["event_window"]["pre_days"] == 1
    assert task["event_window"]["post_days"] == 10
    assert task["task_signature"] == "event_driven|evt_1|ai||event_target_only|000858,600519"


def test_normalize_research_task_contract_for_snapshot_task():
    task = _normalize_research_task_contract(
        {
            "task_source": "snapshot",
            "stock_pool": {"selection_mode": "explicit", "symbols": ["601398", "601288"]},
            "strategy_preferences": ["quality_factor"],
        }
    )

    assert task["task_source"] == "snapshot"
    assert task["target_symbol_policy"] == "prefer_intersection"
    assert task["universe_expansion_policy"] == "allow_market_fallback"
    assert task["preference_strength"] == "soft"
    assert task["validation_focus"] == "target_plus_representative"
    assert task["preferred_strategy_types"] == ["quality_factor"]
    assert task["strategy_preferences"] == ["quality_factor"]
    assert task["target_symbols"] == ["601398", "601288"]
    assert task["holding_window"]["max_days"] == 20
    assert task["preference_reason"] == "snapshot_regime_bias:quality_factor"


def test_apply_target_symbol_policy_strict_intersection_trims_to_task_targets():
    result = _apply_target_symbol_policy(
        ["600519", "000001"],
        {
            "task_source": "event_driven",
            "target_symbols": ["600519", "000858"],
        },
    )

    assert result["target_symbols"] == ["600519"]
    assert result["constraint_check"]["expansion_applied"] is True
    assert result["constraint_check"]["expansion_reason"] == "strict_intersection_trimmed"
    assert result["constraint_check"]["intersection_ratio"] == 0.5


def test_apply_target_symbol_policy_prefer_intersection_retains_candidate_when_no_overlap():
    result = _apply_target_symbol_policy(
        ["000001", "601318"],
        {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858"],
            "target_symbol_policy": "prefer_intersection",
        },
    )

    assert result["target_symbols"] == ["000001", "601318"]
    assert result["constraint_check"]["expansion_applied"] is True
    assert result["constraint_check"]["expansion_reason"] == "candidate_retained_without_intersection"
    assert result["constraint_check"]["expansion_source"] == "candidate_symbols"
    assert result["constraint_check"]["coverage_ratio"] == 0.0
    assert result["constraint_check"]["intersection_ratio"] == 0.0
