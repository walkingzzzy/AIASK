import pytest

from strategy_factory.application.candidate_contract import apply_resolved_candidate_envelope
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
        "strategy_type": "momentum",
        "target_symbols": ["600519"],
        "params": {
            "lookback": 20,
            "threshold": 0.02,
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


def test_deduplicator_spawns_revision_when_portfolio_identity_changes_even_with_same_task_signature():
    candidate = {
        "strategy_type": "momentum",
        "params": {"lookback": 20, "threshold": 0.02},
        "target_symbols": ["600519", "000858"],
        "portfolio_spec": {
            "position_assumption": "equal_weight_proxy",
            "target_weight_scheme": "equal_weight",
            "max_position_pct": 0.5,
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
    existing = {
        "id": "stg_existing",
        "status": "incubating",
        "target_symbols": ["600519", "000858"],
        "params": {
            "research_task": {
                "task_source": "snapshot",
                "target_symbols": ["600519", "000858"],
                "validation_focus": "target_plus_representative",
            },
            "portfolio_spec": {
                "position_assumption": "single_name_full_notional",
                "target_weight_scheme": "single_name",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_plus_representative",
            },
        },
    }
    match = {
        "matched_status": "incubating",
        "matched_strategy_id": "stg_existing",
        "target_overlap": 1.0,
    }

    assert Deduplicator._should_refresh_existing(candidate, match, existing) is False
    assert Deduplicator._should_spawn_revision_from_existing(candidate, match, existing) is True


def test_deduplicator_parent_lineage_no_longer_forces_refresh_when_tested_object_changes():
    candidate = {
        "strategy_type": "dsl_rule",
        "parent_strategy_id": "stg_existing",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519"],
            "validation_focus": "target_plus_representative",
        },
        "validation_profile": {
            "profile": "trade_rule_validation",
            "validation_focus": "target_plus_representative",
        },
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 12}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 10}},
            }
        },
    }
    existing = {
        "id": "stg_existing",
        "status": "listed",
        "target_symbols": ["600519"],
        "params": {
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "research_task": {
                "task_source": "snapshot",
                "target_symbols": ["600519"],
                "validation_focus": "target_plus_representative",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_plus_representative",
            },
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 9}},
            },
        },
    }
    match = {
        "matched_status": "listed",
        "matched_strategy_id": "stg_existing",
        "target_overlap": 1.0,
    }

    assert Deduplicator._should_refresh_existing(candidate, match, existing) is False
    assert Deduplicator._should_spawn_revision_from_existing(candidate, match, existing) is True


def test_deduplicator_exposes_revision_trigger_and_existing_contract_availability():
    candidate = {
        "strategy_type": "dsl_rule",
        "parent_strategy_id": "stg_existing",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "research_task": {
            "task_source": "snapshot",
            "target_symbols": ["600519"],
            "validation_focus": "target_plus_representative",
        },
        "validation_profile": {
            "profile": "trade_rule_validation",
            "validation_focus": "target_plus_representative",
        },
        "params": {
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 12}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 10}},
            }
        },
    }
    existing = {
        "id": "stg_existing",
        "status": "listed",
        "target_symbols": ["600519"],
        "params": {
            "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
            "research_task": {
                "task_source": "snapshot",
                "target_symbols": ["600519"],
                "validation_focus": "target_plus_representative",
            },
            "validation_profile": {
                "profile": "trade_rule_validation",
                "validation_focus": "target_plus_representative",
            },
            "dsl": {
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 10}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 9}},
            },
        },
    }
    match = {
        "matched_status": "listed",
        "matched_strategy_id": "stg_existing",
        "target_overlap": 1.0,
    }

    decision = Deduplicator._evaluate_existing_match_decision(candidate, match, existing)

    assert decision["refresh_existing"] is False
    assert decision["spawn_revision_from_existing"] is True
    assert decision["refresh_decision_basis"] == "tested_object_changed"
    assert decision["revision_trigger_reason"] == "tested_object_changed"
    assert decision["tested_object_changed"] is True
    assert decision["tested_object_hash_changed"] is True
    assert decision["existing_identity_available"] is True
    assert decision["existing_tested_object_available"] is True


@pytest.mark.asyncio
async def test_deduplicator_refreshes_semantic_same_tested_object_below_threshold(monkeypatch):
    candidate = apply_resolved_candidate_envelope({
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
    })
    existing = [apply_resolved_candidate_envelope({
        "id": "stg_existing",
        "status": "listed",
        "name": "same-tested-object",
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
    })]

    monkeypatch.setattr(Deduplicator, "_param_sim", staticmethod(lambda *_args, **_kwargs: 0.2))

    detail, _metrics = await Deduplicator()._find_duplicate(candidate, existing, db=object())

    assert detail["refresh_existing"] is True
    assert detail["match_type"] == "semantic"
    assert detail["refresh_mode"] == "refresh_metrics_only"
    assert detail["refresh_decision_basis"] == "same_tested_object_and_identity"


@pytest.mark.asyncio
async def test_deduplicator_spawns_semantic_revision_below_threshold_when_alpha_changes(monkeypatch):
    candidate = apply_resolved_candidate_envelope({
        "strategy_type": "dsl_rule",
        "parent_strategy_id": "stg_existing",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
                "entry": {"op": "gt", "left": {"indicator": "close"}, "right": {"value": 12}},
                "exit": {"op": "lt", "left": {"indicator": "close"}, "right": {"value": 10}},
            }
        },
    })
    existing = [apply_resolved_candidate_envelope({
        "id": "stg_existing",
        "status": "listed",
        "name": "alpha-parent",
        "strategy_type": "dsl_rule",
        "target_symbols": ["600519"],
        "stock_pool": {"selection_mode": "explicit", "symbols": ["600519"]},
        "portfolio_spec": {
            "position_assumption": "single_name_full_notional",
            "target_weight_scheme": "single_name",
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
    })]

    monkeypatch.setattr(Deduplicator, "_param_sim", staticmethod(lambda *_args, **_kwargs: 0.2))

    detail, _metrics = await Deduplicator()._find_duplicate(candidate, existing, db=object())

    assert detail["refresh_existing"] is False
    assert detail["match_type"] == "semantic"
    assert detail["refresh_mode"] == "spawn_revision_from_existing"
    assert detail["refresh_decision_basis"] == "tested_object_changed"
