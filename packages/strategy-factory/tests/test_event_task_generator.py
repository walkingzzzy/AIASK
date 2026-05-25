"""Tests for event task generator (PR-6 + PR-C / Phase 1)."""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from strategy_factory.application.research.event_task_generator import (
    generate_tasks_from_active_events,
    _build_event_task,
    _compute_task_priority,
    _normalize_event_source,
)
from strategy_factory.application.research.theme_graph import NormalizedEvent, ThemeImpact


def test_build_event_task_unifies_task_source_to_event_driven():
    """PR-C: every event task must report task_source="event_driven" + event_source="manual"."""
    event = NormalizedEvent(
        event_id="test_001",
        event_name="Oil shock",
        event_type="commodity",
        source="manual",
        confidence=0.8,
        intensity=0.7,
        horizon="swing_5_20d",
        valid_from="2026-05-24T00:00:00+00:00",
        valid_until="2026-06-13T00:00:00+00:00",
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
    task = _build_event_task(
        event,
        impact,
        ["600028", "601857"],
        event_source="manual",
        dedupe_key="test_001:upstream_oil_gas:600028-601857",
    )

    # PR-C: top-level + research_task task_source unified
    assert task["task_source"] == "event_driven"
    assert task["research_task"]["task_source"] == "event_driven"
    # event_source recorded in three places: top-level, research_task, event_context
    assert task["event_source"] == "manual"
    assert task["research_task"]["event_source"] == "manual"
    assert task["event_context"]["event_source"] == "manual"
    # legacy fields still in place
    assert task["candidate_family"] == "upstream_oil_gas"
    assert task["target_symbols"] == ["600028", "601857"]
    assert task["event_context"]["event_id"] == "test_001"
    assert task["event_context"]["direction"] == "bullish"
    # PR-C event_context expansions
    assert task["event_context"]["valid_from"] == "2026-05-24T00:00:00+00:00"
    assert task["event_context"]["valid_until"] == "2026-06-13T00:00:00+00:00"
    assert task["event_context"]["dedupe_key"] == "test_001:upstream_oil_gas:600028-601857"
    assert "task_id" in task


def test_build_event_task_preserves_event_source_for_news_origin():
    """非 manual 来源也必须正确进入 event_source 槽位."""
    event = NormalizedEvent(
        event_id="news_evt_42",
        event_name="Tariff escalation",
        event_type="trade_tariff",
        source="news_llm",
        confidence=0.6,
        intensity=0.55,
    )
    impact = ThemeImpact(
        theme_code="trade_tariff_impacts",
        direction_sign=-1,
        magnitude=0.55,
        confidence=0.6,
    )
    task = _build_event_task(
        event,
        impact,
        ["000001", "000002", "000003"],
        event_source="news_llm",
    )
    assert task["task_source"] == "event_driven"
    assert task["event_source"] == "news_llm"
    assert task["event_context"]["event_source"] == "news_llm"


def test_normalize_event_source_handles_aliases():
    assert _normalize_event_source("manual") == "manual"
    assert _normalize_event_source("news_llm") == "news_llm"
    assert _normalize_event_source("macro_shock") == "macro_shock"
    assert _normalize_event_source("market_anomaly") == "market_anomaly"
    assert _normalize_event_source("price_inference") == "price_inference"
    # legacy aliases
    assert _normalize_event_source("auto") == "price_inference"
    assert _normalize_event_source("news") == "news_llm"
    assert _normalize_event_source("macro") == "macro_shock"
    assert _normalize_event_source("anomaly") == "market_anomaly"
    # unknown / empty → default manual
    assert _normalize_event_source("") == "manual"
    assert _normalize_event_source(None) == "manual"
    assert _normalize_event_source("garbage_value") == "manual"


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
async def test_generate_with_active_events_unifies_task_source():
    """Full flow with mocked DB and enabled flags — PR-C semantics check."""
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
                "valid_from": "2026-05-24T00:00:00",
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

        # PR-C: every produced task is event_driven + carries event_source
        for task in result["tasks"]:
            assert task["task_source"] == "event_driven", (
                f"task_source={task.get('task_source')!r} must be 'event_driven' "
                "after PR-C unification"
            )
            assert task["event_source"] in (
                "manual", "news_llm", "macro_shock",
                "market_anomaly", "price_inference",
            ), f"invalid event_source: {task.get('event_source')!r}"
            assert "dedupe_key" in task["event_context"]
            # event from "source": "manual" → event_source=="manual"
            assert task["event_source"] == "manual"

        # Restore module
        importlib.reload(mod)


@pytest.mark.asyncio
async def test_generate_dedupe_key_is_stable_across_runs():
    """同一事件 + 同一影响 + 同一目标股池必须产生相同的 dedupe_key（不算 task_id 的随机后缀）."""
    import importlib
    import strategy_factory.application.research.event_task_generator as mod

    with patch.dict(os.environ, {
        "STRATEGY_FACTORY_MANUAL_EVENT_ENABLED": "1",
        "STRATEGY_FACTORY_THEME_GRAPH_ENABLED": "1",
        "STRATEGY_FACTORY_DYNAMIC_TARGET_COUNT_ENABLED": "0",
    }):
        importlib.reload(mod)

        async def _run_once():
            db = MagicMock()
            db.list_event_injections = AsyncMock(return_value=[
                {
                    "event_id": "stable_dedupe_evt",
                    "source": "macro_shock",
                    "event_name": "rate hike",
                    "event_type": "policy_stimulus",
                    "direction": "negative",
                    "confidence": 0.7,
                    "intensity": 0.5,
                    "horizon": "swing_5_20d",
                    "primary_themes": [{"theme_code": "real_estate_dev", "direction": "negative"}],
                    "valid_from": "2026-05-24T00:00:00",
                    "valid_until": "2099-12-31T00:00:00",
                    "status": "active",
                }
            ])
            db.get_theme_node = AsyncMock(return_value={"theme_code": "real_estate_dev", "breadth": "medium"})
            db.list_theme_edges = AsyncMock(return_value=[])
            db.list_theme_exposure = AsyncMock(return_value=[
                {"symbol": "000002", "exposure_score": 0.8, "industry": "房地产"},
                {"symbol": "001979", "exposure_score": 0.7, "industry": "房地产"},
            ])
            db.upsert_event_task_lineage = AsyncMock(return_value=None)
            return await mod.generate_tasks_from_active_events(db)

        first = await _run_once()
        second = await _run_once()
        first_keys = {t["event_context"]["dedupe_key"] for t in first["tasks"]}
        second_keys = {t["event_context"]["dedupe_key"] for t in second["tasks"]}
        assert first_keys == second_keys
        assert all(
            t["event_source"] == "macro_shock"
            for t in (first["tasks"] + second["tasks"])
        )

        importlib.reload(mod)
