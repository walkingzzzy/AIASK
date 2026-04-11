from strategy_factory.application.research import (
    EXTERNAL_AUTONOMY_CANDIDATE_ORIGIN,
    GOVERNED_CANDIDATE_ACTIVATION_ORIGIN,
    LOCAL_RULE_CANDIDATE_ORIGIN,
    OPEN_RESEARCH_TASK_ORIGIN,
    classify_research_candidate_origin,
    classify_research_task_origin,
    count_candidate_origins,
    count_task_origins,
)


def test_classify_research_candidate_origin_distinguishes_local_autonomy_and_governed():
    local_candidate = {
        "strategy_type": "momentum",
        "spawn_reason": "fear_greed local rule",
        "generation_reason": {"source": "fear_greed"},
    }
    autonomy_candidate = {
        "strategy_type": "momentum",
        "research_task": {"task_source": "snapshot"},
        "experiment_id": "exp_alpha",
        "params": {"generator_type": "external_llm"},
    }
    governed_candidate = {
        "strategy_type": "momentum",
        "research_task": {
            "task_source": "bulk_stock_matrix",
            "source_candidate_artifact_id": "candidate_alpha",
        },
        "params": {"generator_type": "external_llm"},
    }

    assert classify_research_candidate_origin(local_candidate) == LOCAL_RULE_CANDIDATE_ORIGIN
    assert classify_research_candidate_origin(autonomy_candidate) == EXTERNAL_AUTONOMY_CANDIDATE_ORIGIN
    assert classify_research_candidate_origin(governed_candidate) == GOVERNED_CANDIDATE_ACTIVATION_ORIGIN
    assert count_candidate_origins([local_candidate, autonomy_candidate, governed_candidate]) == {
        "local_rule": 1,
        "external_autonomy": 1,
        "governed_candidate_activation": 1,
    }


def test_classify_research_task_origin_distinguishes_governed_activation_tasks():
    open_task = {"task_id": "snapshot_1", "task_source": "snapshot"}
    governed_task = {
        "task_id": "bulk_1",
        "task_source": "bulk_stock_matrix",
        "source_candidate_artifact_id": "candidate_alpha",
    }

    assert classify_research_task_origin(open_task) == OPEN_RESEARCH_TASK_ORIGIN
    assert classify_research_task_origin(governed_task) == GOVERNED_CANDIDATE_ACTIVATION_ORIGIN
    assert count_task_origins([open_task, governed_task]) == {
        "open_research": 1,
        "governed_candidate_activation": 1,
    }
