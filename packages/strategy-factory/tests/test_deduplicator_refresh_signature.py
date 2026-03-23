from strategy_factory.application.deduplicator import Deduplicator


def test_deduplicator_refreshes_when_task_signature_matches():
    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "baijiu",
            "target_symbols": ["600519"],
            "validation_focus": "event_target_only",
        },
    }
    existing = {
        "id": "stg_existing",
        "status": "incubating",
        "params": {
            "research_task": {
                "task_source": "event_driven",
                "event_id": "evt_1",
                "theme_code": "baijiu",
                "target_symbols": ["600519"],
                "validation_focus": "event_target_only",
            }
        },
    }
    match = {
        "matched_status": "incubating",
        "matched_strategy_id": "stg_existing",
        "target_overlap": 1.0,
    }

    assert Deduplicator._should_refresh_existing(candidate, match, existing) is True
    assert Deduplicator._should_spawn_revision_from_existing(candidate, match, existing) is False


def test_deduplicator_spawns_revision_when_validation_focus_changes_signature():
    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519"],
        "research_task": {
            "task_source": "event_driven",
            "event_id": "evt_1",
            "theme_code": "baijiu",
            "target_symbols": ["600519"],
            "validation_focus": "broad_generalization",
        },
    }
    existing = {
        "id": "stg_existing",
        "status": "incubating",
        "params": {
            "research_task": {
                "task_source": "event_driven",
                "event_id": "evt_1",
                "theme_code": "baijiu",
                "target_symbols": ["600519"],
                "validation_focus": "event_target_only",
            }
        },
    }
    match = {
        "matched_status": "incubating",
        "matched_strategy_id": "stg_existing",
        "target_overlap": 1.0,
    }

    assert Deduplicator._should_refresh_existing(candidate, match, existing) is False
    assert Deduplicator._should_spawn_revision_from_existing(candidate, match, existing) is True
