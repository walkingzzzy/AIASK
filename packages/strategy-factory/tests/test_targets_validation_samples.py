from strategy_factory.domain.targets import (
    _resolve_strategy_sample_codes,
    _resolve_strategy_sample_selection,
)


def test_resolve_strategy_sample_codes_prefers_family_peers_for_target_only_quality():
    params = {
        "target_symbols": ["000776"],
        "validation_profile": {"validation_focus": "candidate_target_only"},
    }

    codes = _resolve_strategy_sample_codes("quality_factor", params, sample_size=6)

    assert codes[0] == "000776"
    assert "600519" in codes
    assert "000858" in codes
    assert len(codes) >= 6


def test_resolve_strategy_sample_codes_uses_family_peers_for_target_only_momentum():
    params = {
        "target_symbols": ["002594"],
        "research_task": {"validation_focus": "candidate_target_only"},
    }

    codes = _resolve_strategy_sample_codes("momentum", params, sample_size=6)

    assert codes[0] == "002594"
    assert "300750" in codes
    assert "601012" in codes


def test_resolve_strategy_sample_selection_promotes_target_codes_into_family_peer_panel():
    params = {
        "target_symbols": ["300750"],
        "validation_profile": {"validation_focus": "target_plus_representative"},
    }

    selection = _resolve_strategy_sample_selection("momentum", params, sample_size=6)

    assert selection["validation_focus_layer"] == "family_peer"
    assert selection["sample_selection_mode"] == "target_plus_dynamic_family_peer"
    assert selection["sample_alignment_reason"] == "target_codes_present_promoted_to_family_peer_panel"
    assert selection["sample_codes"][0] == "300750"
    assert "601012" in selection["sample_codes"]


def test_resolve_strategy_sample_selection_keeps_broad_market_mode_without_target_codes():
    selection = _resolve_strategy_sample_selection("value_factor", {}, sample_size=6)

    assert selection["validation_focus_layer"] == "broad_market"
    assert selection["sample_selection_mode"] == "representative_only"
    assert selection["sample_alignment_reason"] == "broad_market_representative_fallback"
