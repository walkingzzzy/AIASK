from strategy_factory.application.quality_gates import _select_gate_2_candidates


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
                "strategy_type": "momentum",
                "parent_strategy_id": "sid_parent_1",
            },
            1.20,
        ),
        (
            {
                "strategy_type": "momentum",
                "parent_strategy_id": "sid_parent_1",
            },
            1.10,
        ),
        (
            {
                "strategy_type": "rsi",
                "research_task": {"task_key": "task_factor_reversal"},
            },
            0.90,
        ),
    ]

    selected = _select_gate_2_candidates(gate_1_scored, top_k=3)

    assert len(selected) == 3
    assert sum(1 for item in selected if item.get("parent_strategy_id") == "sid_parent_1") == 2
