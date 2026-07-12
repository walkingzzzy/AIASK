from __future__ import annotations


def test_common_reexports_the_single_lifecycle_state_machine_authority() -> None:
    from akshare_mcp.services.strategy_lifecycle_shared import common, state_machine

    assert common.LIFECYCLE_TRANSITIONS is state_machine.LIFECYCLE_TRANSITIONS
    assert common.normalize_status_alias is state_machine.normalize_status_alias
    assert common.validate_transition is state_machine.validate_transition
    assert common.update_status is state_machine.update_status


def test_lifecycle_transition_contract_has_no_draft_to_rejected_shortcut() -> None:
    from akshare_mcp.services.strategy_lifecycle_shared.state_machine import (
        validate_transition,
    )

    assert validate_transition("draft", "submitted") is True
    assert validate_transition("submitted", "rejected") is True
    assert validate_transition("rejected", "draft") is True
    assert validate_transition("draft", "rejected") is False
    assert validate_transition("listed", "archived") is True
    assert validate_transition("suspended", "incubating") is True
