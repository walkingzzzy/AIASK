from __future__ import annotations


def _healthy_snapshot() -> dict:
    return {
        "degraded": False,
        "completeness": {"completion_ratio": 1.0},
        "sources": {"event_driven": {"status": "success"}},
        "event_driven": {"tasks_ready_count": 1},
    }


def _missing_governed_pool_factor_research() -> dict:
    return {
        "summary": {
            "factor_source_mode": "seed_fallback",
            "active_candidate_count": 0,
            "governed_source_candidate_count": 0,
        },
        "freshness_repair": {
            "auto_refresh_enabled": False,
            "refresh_attempted": False,
            "refresh_status": "disabled",
        },
    }


def test_soft_readiness_allows_missing_governed_pool_with_observability(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "0")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _missing_governed_pool_factor_research(),
    )

    assert readiness["hard_block_enabled"] is False
    assert readiness["can_proceed"] is True
    assert "governed_candidate_pool_required" in readiness["blockers"]
    assert "governed_candidate_pool_unavailable_after_refresh" in readiness["blockers"]
    assert readiness["critical_blockers"] == []
    assert readiness["authority"]["decision"] == "proceed"


def test_hard_readiness_blocks_missing_governed_pool(monkeypatch):
    monkeypatch.setenv("STRATEGY_FACTORY_READINESS_HARD_BLOCK", "1")

    from strategy_factory.application.services.readiness_service import ReadinessService

    readiness = ReadinessService().evaluate(
        _healthy_snapshot(),
        _missing_governed_pool_factor_research(),
    )

    assert readiness["hard_block_enabled"] is True
    assert readiness["can_proceed"] is False
    assert "governed_candidate_pool_required" in readiness["critical_blockers"]
    assert "governed_candidate_pool_unavailable_after_refresh" in readiness["critical_blockers"]
    assert readiness["authority"]["decision"] == "blocked"
