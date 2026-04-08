from strategy_factory.domain.targets import (
    _apply_target_symbol_policy,
    _build_target_alignment_contract,
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
    assert task["target_symbol_policy"] == "strict_intersection"
    assert task["universe_expansion_policy"] == "forbid"
    assert task["preference_strength"] == "soft"
    assert task["validation_focus"] == "target_plus_representative"
    assert task["preferred_strategy_types"] == ["quality_factor"]
    assert task["strategy_preferences"] == ["quality_factor"]
    assert task["target_symbols"] == ["601398", "601288"]
    assert task["holding_window"]["max_days"] == 20
    assert task["preference_reason"] == "snapshot_regime_bias:quality_factor"
    assert task["target_alignment_contract"]["profile"] == "snapshot_targeted"
    assert task["target_alignment_contract"]["market_fallback_allowed"] is False
    assert task["target_alignment_contract"]["max_candidate_target_symbols"] == 2


def test_normalize_research_task_contract_for_single_target_snapshot_task():
    task = _normalize_research_task_contract(
        {
            "task_source": "snapshot",
            "target_symbols": ["600519"],
            "allowed_strategy_types": ["ma_cross"],
        }
    )

    assert task["task_source"] == "snapshot"
    assert task["target_symbols"] == ["600519"]
    assert task["target_symbol_policy"] == "strict_intersection"
    assert task["universe_expansion_policy"] == "forbid"
    assert task["target_alignment_contract"]["profile"] in {"snapshot_targeted", "pipeline_staged_ma_cross"}
    assert task["target_alignment_contract"]["market_fallback_allowed"] is False
    assert task["target_alignment_contract"]["min_required_overlap_count"] == 1
    assert task["target_alignment_contract"]["min_target_sample_count"] == 1


def test_normalize_research_task_contract_compacts_factor_research_metadata():
    task = _normalize_research_task_contract(
        {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858"],
            "metadata": {
                "factor_research": {
                    "active_factors": ["momentum_20d", "rsi_14", "turnover_ratio"],
                    "preferred_strategy_types": ["momentum", "rsi"],
                    "degraded": True,
                    "summary": {
                        "top_factor_names": ["momentum_20d", "rsi_14"],
                        "active_candidate_count": 128,
                        "candidate_pool_size": 32,
                        "registry_size": 512,
                        "freshness_days": 2,
                        "refresh_status": "fresh",
                    },
                    "active_candidate_pool": {"items": [{"id": "candidate_001"} for _ in range(100)]},
                },
                "raw_blob": {"too": "large", "nested": {"ignored": True}},
            },
        }
    )

    factor_research = task["metadata"]["factor_research"]
    assert factor_research["top_factor_names"] == ["momentum_20d", "rsi_14"]
    assert factor_research["preferred_strategy_types"] == ["momentum", "rsi"]
    assert factor_research["active_candidate_count"] == 128
    assert "active_candidate_pool" not in factor_research
    assert task["metadata"]["raw_blob"] == {"too": "large"}


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
            "universe_expansion_policy": "allow_market_fallback",
        },
    )

    assert result["target_symbols"] == ["000001", "601318"]
    assert result["constraint_check"]["expansion_applied"] is True
    assert result["constraint_check"]["expansion_reason"] == "candidate_retained_without_intersection"
    assert result["constraint_check"]["expansion_source"] == "candidate_symbols"
    assert result["constraint_check"]["coverage_ratio"] == 0.0
    assert result["constraint_check"]["intersection_ratio"] == 0.0


def test_apply_target_symbol_policy_strict_intersection_without_overlap_does_not_fallback_to_market_universe():
    result = _apply_target_symbol_policy(
        ["000001", "601318"],
        {
            "task_source": "event_driven",
            "target_symbols": ["600519", "000858"],
            "target_symbol_policy": "strict_intersection",
            "universe_expansion_policy": "allow_same_theme_only",
        },
        fallback_symbols=["000001", "601318", "002594"],
    )

    assert result["target_symbols"] == []
    assert result["constraint_check"]["expansion_applied"] is False
    assert result["constraint_check"]["constraint_violation"] == "strict_intersection_empty"
    assert result["constraint_check"]["expansion_blocked_reason"] == "same_theme_symbols_unavailable"


def test_apply_target_symbol_policy_blocks_default_snapshot_market_fallback_when_contract_requires_target_pool():
    result = _apply_target_symbol_policy(
        ["000001", "601318"],
        {
            "task_source": "snapshot",
            "target_symbols": ["600519", "000858", "601398", "601939"],
        },
        fallback_symbols=["000001", "601318", "002594"],
    )

    assert result["target_symbols"] == []
    assert result["constraint_check"]["constraint_violation"] == "strict_intersection_empty"
    assert result["constraint_check"]["alignment_contract_violation"] == "empty_target_symbols_after_alignment"


def test_build_target_alignment_contract_tightens_pipeline_rsi_snapshot_requirements():
    contract = _build_target_alignment_contract(
        {
            "task_source": "snapshot",
            "target_symbols": ["603855", "603279", "002833", "601766", "600528", "600582", "600894", "920599"],
            "allowed_strategy_types": ["rsi"],
        },
        candidate={
            "strategy_type": "rsi",
            "generator_type": "pipeline_staged",
            "tags": ["pipeline_staged", "generator_pipeline_staged"],
        },
    )

    assert contract["profile"] == "pipeline_staged_rsi"
    assert contract["min_intersection_ratio"] == 0.5
    assert contract["min_required_overlap_count"] == 4
    assert contract["min_target_sample_count"] == 4
    assert contract["max_candidate_target_symbols"] == 4
