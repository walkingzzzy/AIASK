from strategy_factory.application.factory_scheduler import StrategyFactoryScheduler


def test_factory_scheduler_task_summary_exposes_normalized_preference_contract():
    summary = StrategyFactoryScheduler._summarize_research_task_for_task_run(
        {
            "task_id": "task_contract_summary",
            "preferred_strategy_types": ["rsi", "value_factor"],
            "allowed_strategy_types": ["rsi", "ma_cross"],
            "preference_strength": "hard",
            "validation_focus": "candidate_target_only",
            "target_symbols": ["300750"],
        }
    )

    assert summary["preferred_strategy_types"] == ["rsi", "value_factor"]
    assert summary["strategy_preferences"] == ["rsi", "value_factor"]
    assert summary["allowed_strategy_types"] == ["rsi", "ma_cross"]
    assert summary["preference_strength"] == "hard"
    assert summary["validation_focus"] == "candidate_target_only"
    assert summary["target_symbols"] == ["300750"]


def test_factory_scheduler_task_run_summary_preserves_normalized_task_contract():
    summary = StrategyFactoryScheduler._build_research_task_run_result_summary(
        {
            "task_run_id": 42,
            "task_source": "snapshot",
            "status": "completed",
            "generated_count": 2,
            "reviewed_count": 1,
            "evidence_count": 3,
            "task": {
                "task_id": "task_contract_summary",
                "preferred_strategy_types": ["rsi"],
                "allowed_strategy_types": ["rsi", "gap_fill"],
                "preference_strength": "medium",
                "validation_focus": "target_plus_representative",
                "target_symbols": ["300750"],
            },
        }
    )

    task = summary["task"]
    assert task["preferred_strategy_types"] == ["rsi"]
    assert task["strategy_preferences"] == ["rsi"]
    assert task["allowed_strategy_types"] == ["rsi", "gap_fill"]
    assert task["preference_strength"] == "medium"
    assert task["validation_focus"] == "target_plus_representative"
