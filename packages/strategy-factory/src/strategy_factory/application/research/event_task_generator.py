"""Event-driven task generator (PR-6).

Bridges the event injection system (PR-2) with the factory's existing
task generation pipeline. Reads active events, propagates through the
theme graph, resolves target baskets, and produces research tasks
compatible with the existing `_build_event_driven_tasks` output format.

This module is called by MarketOpportunityScanner.scan() when
STRATEGY_FACTORY_MANUAL_EVENT_ENABLED=true.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .theme_graph import NormalizedEvent, ThemeImpact, propagate_event_to_themes
from .target_basket import TargetBasket, resolve_target_basket, resolve_target_count

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on") if raw else default


MANUAL_EVENT_ENABLED = _env_bool("STRATEGY_FACTORY_MANUAL_EVENT_ENABLED", False)
THEME_GRAPH_ENABLED = _env_bool("STRATEGY_FACTORY_THEME_GRAPH_ENABLED", False)
DYNAMIC_TARGET_COUNT_ENABLED = _env_bool("STRATEGY_FACTORY_DYNAMIC_TARGET_COUNT_ENABLED", False)
TARGET_COUNT_MAX = int(os.getenv("STRATEGY_FACTORY_TARGET_COUNT_MAX") or 30)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_event_task(
    event: NormalizedEvent,
    impact: ThemeImpact,
    symbols: list[str],
    *,
    task_source: str = "manual_event",
) -> dict[str, Any]:
    """Build a research task dict compatible with existing factory pipeline.

    Output format matches `_opportunity_event.py:_finalize_task()`.
    """
    direction = "bullish" if impact.direction_sign > 0 else "bearish" if impact.direction_sign < 0 else "neutral"

    return {
        "task_id": f"event_{event.event_id}_{impact.theme_code}_{uuid4().hex[:8]}",
        "task_key": f"event:{event.event_id}:{impact.theme_code}",
        "task_source": task_source,
        "opportunity_type": f"event_{event.event_type}",
        "candidate_family": impact.theme_code,
        "factor_name": impact.theme_code,
        "generation_limit": 4,
        "target_symbols": symbols,
        "stock_pool": {
            "selection_mode": "event_theme_exposure",
            "symbols": symbols,
            "theme_code": impact.theme_code,
        },
        "event_context": {
            "event_id": event.event_id,
            "event_name": event.event_name,
            "event_type": event.event_type,
            "direction": direction,
            "confidence": round(impact.confidence, 4),
            "intensity": round(impact.magnitude, 4),
            "horizon": event.horizon,
            "lag_days": impact.lag_days,
            "propagation_depth": impact.depth,
            "source_path": impact.source_path,
        },
        "research_task": {
            "task_source": task_source,
            "opportunity_type": f"event_{event.event_type}",
            "preferred_strategy_types": _preferred_types_for_direction(direction),
            "target_symbols": symbols,
            "target_symbol_policy": "event_target_only" if len(symbols) <= 5 else "target_plus_representative",
            "validation_focus": "event_target_only" if len(symbols) <= 5 else "target_plus_representative",
            "event_window": {
                "horizon": event.horizon,
                "lag_days": impact.lag_days,
            },
        },
        "priority": _compute_task_priority(event, impact),
    }


def _preferred_types_for_direction(direction: str) -> list[str]:
    """Map event direction to preferred strategy types."""
    if direction == "bullish":
        return ["momentum", "event_structure_breakout", "ma_cross"]
    if direction == "bearish":
        return ["mean_reversion_short", "rsi", "gap_fill"]
    return ["multi_factor", "macro_timing"]


def _compute_task_priority(event: NormalizedEvent, impact: ThemeImpact) -> int:
    """Compute task priority (lower = higher priority)."""
    base = 50
    # Manual events get higher priority
    if event.source == "manual":
        base -= 20
    # Higher confidence/intensity = higher priority
    evidence = impact.confidence * 0.5 + impact.magnitude * 0.5
    base -= int(evidence * 20)
    # Deeper propagation = lower priority
    base += impact.depth * 5
    return max(1, min(100, base))


async def generate_tasks_from_active_events(
    db: Any,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Main entry point: load active events, propagate, generate tasks.

    Called by MarketOpportunityScanner.scan() when manual events are enabled.

    Returns:
        Dict with 'tasks' list and metadata.
    """
    if not MANUAL_EVENT_ENABLED:
        return {"enabled": False, "tasks": [], "reason": "MANUAL_EVENT_ENABLED=false"}

    if not THEME_GRAPH_ENABLED:
        return {"enabled": False, "tasks": [], "reason": "THEME_GRAPH_ENABLED=false"}

    # Load active events
    events_raw = []
    if hasattr(db, "list_event_injections"):
        events_raw = await db.list_event_injections(status="active", limit=20)

    if not events_raw:
        return {"enabled": True, "tasks": [], "event_count": 0}

    # Filter to currently valid events
    now = _now_iso()
    active_events = []
    for raw in events_raw:
        valid_until = str(raw.get("valid_until") or "").strip()
        if valid_until and valid_until < now:
            continue
        active_events.append(NormalizedEvent.from_dict(raw))

    if not active_events:
        return {"enabled": True, "tasks": [], "event_count": 0, "all_expired": True}

    # Generate tasks for each event
    all_tasks: list[dict[str, Any]] = []
    lineage_records: list[dict[str, Any]] = []
    feature_flag_max = TARGET_COUNT_MAX if DYNAMIC_TARGET_COUNT_ENABLED else 12

    for event in active_events:
        # Propagate through theme graph
        impacts = await propagate_event_to_themes(db, event)

        for impact in impacts:
            # Resolve target basket
            basket = await resolve_target_basket(
                db, impact,
                feature_flag_target_max=feature_flag_max,
            )

            if not basket.symbols:
                continue

            # Determine target count
            target_count = resolve_target_count(
                confidence=impact.confidence,
                intensity=impact.magnitude,
                theme_breadth=impact.breadth,
                task_source="manual_event" if event.source == "manual" else "auto_event",
                feature_flag_target_max=feature_flag_max,
            )

            symbols = basket.symbols[:target_count]
            if not symbols:
                continue

            # Build task
            task = _build_event_task(
                event, impact, symbols,
                task_source="manual_event" if event.source == "manual" else "auto_event",
            )
            all_tasks.append(task)

            # Record lineage
            lineage_records.append({
                "event_id": event.event_id,
                "task_id": task["task_id"],
                "theme_code": impact.theme_code,
                "impact_direction": "positive" if impact.direction_sign > 0 else "negative",
                "impact_magnitude": impact.magnitude,
                "target_symbols": symbols,
                "target_count": len(symbols),
                "breadth_resolved": impact.breadth,
            })

    # Persist lineage
    if lineage_records and hasattr(db, "upsert_event_task_lineage"):
        for record in lineage_records:
            try:
                await db.upsert_event_task_lineage(record)
            except Exception as exc:
                logger.debug("event_task_generator: lineage persist failed: %s", exc)

    return {
        "enabled": True,
        "tasks": all_tasks,
        "event_count": len(active_events),
        "impact_count": sum(1 for _ in all_tasks),
        "task_count": len(all_tasks),
        "lineage_count": len(lineage_records),
        "feature_flag_target_max": feature_flag_max,
    }


__all__ = [
    "generate_tasks_from_active_events",
    "MANUAL_EVENT_ENABLED",
    "THEME_GRAPH_ENABLED",
]
