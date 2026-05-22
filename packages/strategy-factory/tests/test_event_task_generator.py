"""Tests for event task generator (PR-6)."""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from strategy_factory.application.research.event_task_generator import (
    generate_tasks_from_active_events,
    _build_event_task,
    _compute_task_priority,
)
from strategy_factory.application.research.theme_graph import NormalizedEvent, ThemeImpact


def test_build_event_task_structure():
    event = NormalizedEvent(
        event_id="test_001",
        event_name="Oil shock",
        event_type="commodity",
        source="manual",
        confidence=0.8,
        intensity=0.7,
        horizon="swing_5_20d",
    )
    impact = ThemeImpact(
        theme_code="upstream_oil_gas",
        direction_sign=1,
        magnitude=0.7,
        confidence=0.8,
        lag_days=1,
        depth=0,
        breadth="narrow",
    )
    task = _build_event_task(event, impact, ["600028", "601857"])

    assert task["task_source"] == "manual_event"
    assert task["candidate_family"] == "upstream_oil_gas"
    assert task["target_symbols"] == ["600028", "601857"]
    assert task["event_context"]["event_id"] == "test_001"
    assert task["event_context"]["direction"] == "bullish"
    assert "task_id" in task
    assert "research_task" in task


def test_task_priority_manual_higher():
    event_manual = NormalizedEvent(event_id="m1", source="manual", confidence=0.8, intensity=0.7)
    event_auto = NormalizedEvent(event_id="a1", source="price_inference", confidence=0.8, intensity=0.7)
    impact = ThemeImpact(theme_code="t", direction_sign=1, magnitude=0.7, confidence=0.8)

    priority_manual = _compute_task_priority(event_manual, impact)
    priority_auto = _compute_task_priority(event_auto, impact)
    assert priority_manual < priority_auto  # Lower number = higher priority


@pytest.mark.asyncio
async def test_generate_disabled_when_flag_off():
    with patch.dict(os.environ, {"STRATEGY_FACTORY_MANUAL_EVENT_ENABLED": "0"}):
        # Need to reimport to pick up env change
        import importlib
        import strategy_factory.application.research.event_task_generator as mod
        importlib.reload(mod)

        db = MagicMock()
        result = await mod.generate_tasks_from_active_events(db)
        assert result["enabled"] is False

        # Restore
        importlib.reload(mod)


@pytest.mark.asyncio
async def test_generate_with_active_events():
    """Test full flow with mocked DB and enabled flags."""
    import importlib
    import strategy_factory.application.research.event_task_generator as mod

    with patch.dict(os.environ, {
        "STRATEGY_FACTORY_MANUAL_EVENT_ENABLED": "1",
        "STRATEGY_FACTORY_THEME_GRAPH_ENABLED": "1",
        "STRATEGY_FACTORY_DYNAMIC_TARGET_COUNT_ENABLED": "0",
    }):
        importlib.reload(mod)

        db = MagicMock()
        db.list_event_injections = AsyncMock(return_value=[
            {
                "event_id": "manual_test123",
                "source": "manual",
                "event_name": "Test event",
                "event_type": "commodity",
                "direction": "positive",
                "confidence": 0.8,
                "intensity": 0.7,
                "horizon": "swing_5_20d",
                "primary_themes": [{"theme_code": "upstream_oil_gas", "direction": "positive"}],
                "valid_from": "2020-01-01T00:00:00",
                "valid_until": "2099-12-31T00:00:00",
                "status": "active",
            }
        ])
        db.get_theme_node = AsyncMock(return_value={"theme_code": "upstream_oil_gas", "breadth": "narrow"})
        db.list_theme_edges = AsyncMock(return_value=[
            {
                "target_theme_code": "airlines",
                "relation_type": "supply_shock",
                "direction_sign": -1,
                "magnitude_factor": 0.7,
                "confidence": 0.65,
                "lag_days": 1,
            }
        ])
        db.list_theme_exposure = AsyncMock(return_value=[
            {"symbol": "600028", "exposure_score": 0.8, "industry": "石油化工"},
            {"symbol": "601857", "exposure_score": 0.9, "industry": "石油开采"},
        ])
        db.upsert_event_task_lineage = AsyncMock(return_value=None)

        result = await mod.generate_tasks_from_active_events(db)

        assert result["enabled"] is True
        assert result["event_count"] == 1
        assert result["task_count"] >= 1
        assert len(result["tasks"]) >= 1

        # Verify task structure
        task = result["tasks"][0]
        assert "target_symbols" in task
        assert "event_context" in task
        assert task["event_context"]["event_id"] == "manual_test123"

        # Restore module
        importlib.reload(mod)
