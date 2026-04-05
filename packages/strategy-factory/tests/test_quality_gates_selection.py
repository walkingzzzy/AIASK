from strategy_factory.application.quality_gates import (
    _post_gate_1_target_quality_block_reason,
    _select_gate_2_candidates,
)


def test_select_gate_2_candidates_prefers_group_diversity_before_duplicate_variants():
    gate_1_scored = [
        (
            {
                "strategy_type": "momentum",
                "parent_strategy_id": "sid_parent_1",
                "research_task": {"task_key": "task_hot_bank"},
            },
            1.20,
        ),
        (
            {
                "strategy_type": "momentum",
                "parent_strategy_id": "sid_parent_1",
                "research_task": {"task_key": "task_hot_bank"},
            },
            1.10,
        ),
        (
            {
                "strategy_type": "rsi",
                "research_task": {"task_key": "task_factor_reversal"},
                "target_symbols": ["600036", "601398"],
            },
            1.00,
        ),
        (
            {
                "strategy_type": "ma_cross",
                "research_task": {"task_key": "task_regime"},
                "target_symbols": ["601857", "600938"],
            },
            0.95,
        ),
    ]

    selected = _select_gate_2_candidates(gate_1_scored, top_k=3)

    assert len(selected) == 3
    assert sum(1 for item in selected if item.get("parent_strategy_id") == "sid_parent_1") == 1
    assert {item.get("strategy_type") for item in selected} == {"momentum", "rsi", "ma_cross"}


def test_select_gate_2_candidates_allows_fill_back_from_same_group_when_slots_remain():
    gate_1_scored = [
        (
            {
                "candidate_id": "parent_variant_a",
                "strategy_type": "momentum",
                "parent_strategy_id": "sid_parent_1",
                "candidate_family": "rotation_balanced",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["600519", "000858"],
            },
            1.20,
        ),
        (
            {
                "candidate_id": "parent_variant_b",
                "strategy_type": "momentum",
                "parent_strategy_id": "sid_parent_1",
                "candidate_family": "rotation_balanced",
                "params": {"lookback": 30, "threshold": 0.02},
                "target_symbols": ["600519", "000858"],
            },
            1.10,
        ),
        (
            {
                "candidate_id": "unique_rsi",
                "strategy_type": "rsi",
                "research_task": {"task_key": "task_factor_reversal"},
            },
            0.90,
        ),
    ]

    selected = _select_gate_2_candidates(gate_1_scored, top_k=3)

    assert len(selected) == 3
    assert sum(1 for item in selected if item.get("parent_strategy_id") == "sid_parent_1") == 2


def test_select_gate_2_candidates_skips_exact_duplicate_signatures_even_when_slots_remain():
    gate_1_scored = [
        (
            {
                "candidate_id": "dup_a",
                "strategy_type": "momentum",
                "candidate_family": "rotation_balanced",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["600519", "000858"],
                "research_task": {"task_key": "task_rotation"},
            },
            1.20,
        ),
        (
            {
                "candidate_id": "dup_b",
                "strategy_type": "momentum",
                "candidate_family": "rotation_balanced",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["600519", "000858"],
                "research_task": {"task_key": "task_rotation"},
            },
            1.10,
        ),
        (
            {
                "candidate_id": "unique_rsi",
                "strategy_type": "rsi",
                "candidate_family": "industry_leadership",
                "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
                "target_symbols": ["601318", "600036"],
                "research_task": {"task_key": "task_industry"},
            },
            1.00,
        ),
        (
            {
                "candidate_id": "unique_quality",
                "strategy_type": "quality_factor",
                "candidate_family": "sector_breakout",
                "params": {"lookback": 60},
                "target_symbols": ["300750", "002594"],
                "research_task": {"task_key": "task_sector"},
            },
            0.95,
        ),
    ]

    selected = _select_gate_2_candidates(gate_1_scored, top_k=3)

    assert [item.get("candidate_id") for item in selected] == ["dup_a", "unique_rsi", "unique_quality"]


def test_select_gate_2_candidates_does_not_backfill_rl_bandit_snapshot_variants_from_same_task():
    gate_1_scored = [
        (
            {
                "candidate_id": "rl_primary",
                "strategy_type": "momentum",
                "generator_type": "rl_bandit",
                "candidate_family": "rotation_balanced",
                "params": {"lookback": 20, "threshold": 0.02},
                "target_symbols": ["601628", "600030", "601211", "000776"],
                "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
                "constraint_check": {"coverage_ratio": 0.2, "intersection_ratio": 0.25},
                "research_task": {
                    "task_key": "task_rotation",
                    "task_source": "snapshot",
                    "validation_focus": "target_plus_representative",
                },
            },
            1.20,
        ),
        (
            {
                "candidate_id": "rl_fill",
                "strategy_type": "momentum",
                "generator_type": "rl_bandit",
                "candidate_family": "rotation_balanced",
                "params": {"lookback": 30, "threshold": 0.02},
                "target_symbols": ["601628", "600030", "601211", "000776"],
                "tags": ["targeted_universe", "generator_rl_bandit", "rl_evolved"],
                "constraint_check": {"coverage_ratio": 0.25, "intersection_ratio": 0.375},
                "research_task": {
                    "task_key": "task_rotation",
                    "task_source": "snapshot",
                    "validation_focus": "target_plus_representative",
                },
            },
            1.10,
        ),
        (
            {
                "candidate_id": "unique_rsi",
                "strategy_type": "rsi",
                "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
                "target_symbols": ["601318", "600036"],
                "research_task": {"task_key": "task_industry"},
            },
            1.00,
        ),
        (
            {
                "candidate_id": "unique_quality",
                "strategy_type": "quality_factor",
                "params": {"lookback": 60},
                "target_symbols": ["300750", "002594"],
                "research_task": {"task_key": "task_sector"},
            },
            0.95,
        ),
    ]

    selected = _select_gate_2_candidates(gate_1_scored, top_k=4)

    assert [item.get("candidate_id") for item in selected] == ["rl_primary", "unique_rsi", "unique_quality"]


def test_post_gate_1_filter_blocks_high_turnover_pipeline_staged_ma_cross_snapshot_candidate():
    candidate = {
        "strategy_type": "ma_cross",
        "generator_type": "pipeline_staged",
        "target_symbols": ["601857", "600938", "600028", "600941"],
        "tags": ["targeted_universe", "pipeline_staged", "generator_pipeline_staged"],
        "constraint_check": {"coverage_ratio": 1.0, "intersection_ratio": 0.75},
        "research_task": {
            "task_source": "snapshot",
            "task_id": "task_energy_rotation",
            "validation_focus": "target_plus_representative",
            "target_symbols": ["601857", "600938", "600028", "600941"],
        },
        "gate_1_result": {
            "metrics": {
                "avg_turnover_proxy": 1.7,
                "avg_total_return": 0.008,
            }
        },
    }

    assert _post_gate_1_target_quality_block_reason(candidate, 0.82) == "snapshot_turnover_fragility_too_high"
