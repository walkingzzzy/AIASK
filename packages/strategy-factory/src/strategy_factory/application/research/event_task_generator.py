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
    event_source: str = "manual",
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Build a research task dict compatible with existing factory pipeline.

    PR-C (Phase 1, 2026-05-24): all event-driven tasks unified under
    ``task_source="event_driven"``; the 5 origins (manual / news_llm /
    macro_shock / market_anomaly / price_inference) are distinguished by
    ``event_source``. Downstream code that previously branched on
    ``manual_event``/``auto_event`` must read ``event_source`` instead.

    Output format matches `_opportunity_event.py:_finalize_task()`.
    """
    direction = "bullish" if impact.direction_sign > 0 else "bearish" if impact.direction_sign < 0 else "neutral"

    short_window = len(symbols) <= 5
    validation_focus = "event_target_only" if short_window else "target_plus_representative"
    target_symbol_policy = "event_target_only" if short_window else "target_plus_representative"

    event_context: dict[str, Any] = {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "event_type": event.event_type,
        "event_source": event_source,
        "direction": direction,
        "confidence": round(impact.confidence, 4),
        "intensity": round(impact.magnitude, 4),
        "horizon": event.horizon,
        "lag_days": impact.lag_days,
        "propagation_depth": impact.depth,
        "source_path": impact.source_path,
        # PR-C optional metadata. None values are acceptable for backwards
        # compatibility but downstream Phase 4/5 (Desktop preview, lineage)
        # is expected to fill them in.
        "valid_from": event.valid_from if hasattr(event, "valid_from") else None,
        "valid_until": event.valid_until if hasattr(event, "valid_until") else None,
        "dedupe_key": dedupe_key,
    }

    research_task: dict[str, Any] = {
        # PR-C: unified task_source + new event_source field
        "task_source": "event_driven",
        "event_source": event_source,
        "opportunity_type": f"event_{event.event_type}",
        "preferred_strategy_types": _preferred_types_for_direction(direction),
        "target_symbols": symbols,
        "target_symbol_policy": target_symbol_policy,
        "validation_focus": validation_focus,
        "event_window": {
            "horizon": event.horizon,
            "lag_days": impact.lag_days,
        },
    }

    return {
        "task_id": f"event_{event.event_id}_{impact.theme_code}_{uuid4().hex[:8]}",
        "task_key": f"event:{event.event_id}:{impact.theme_code}",
        # PR-C: top-level task_source unified
        "task_source": "event_driven",
        "event_source": event_source,
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
        "event_context": event_context,
        "research_task": research_task,
        "priority": _compute_task_priority(event, impact),
    }


_VALID_EVENT_SOURCES = {
    "manual",
    "news_llm",
    "macro_shock",
    "market_anomaly",
    "price_inference",
}


def _normalize_event_source(raw: str | None) -> str:
    """Map a `NormalizedEvent.source` string to the canonical event_source enum.

    Defaults to ``"manual"`` when the input is empty so that legacy events
    that pre-date the event_source field still get a sensible bucket.
    """
    token = str(raw or "").strip().lower()
    if token in _VALID_EVENT_SOURCES:
        return token
    # Common legacy aliases
    if token in ("auto", "automated"):
        return "price_inference"
    if token in ("news", "headline"):
        return "news_llm"
    if token in ("macro", "shock", "macro_event"):
        return "macro_shock"
    if token in ("anomaly", "market"):
        return "market_anomaly"
    return "manual"


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
    *,
    force_enabled: bool = False,
    persist_lineage: bool = True,
    event_limit: int = 20,
) -> dict[str, Any]:
    """Main entry point: load active events, propagate, generate tasks.

    Called by MarketOpportunityScanner.scan() when manual events are enabled.

    Returns:
        Dict with 'tasks' list and metadata.
    """
    if not force_enabled and not MANUAL_EVENT_ENABLED:
        return {"enabled": False, "tasks": [], "reason": "MANUAL_EVENT_ENABLED=false"}

    if not force_enabled and not THEME_GRAPH_ENABLED:
        return {"enabled": False, "tasks": [], "reason": "THEME_GRAPH_ENABLED=false"}

    # Load active events
    events_raw = []
    if hasattr(db, "list_event_injections"):
        events_raw = await db.list_event_injections(status="active", limit=max(1, int(event_limit or 20)))

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
        # PR-C: derive canonical event_source enum from raw event payload
        event_source = _normalize_event_source(event.source)

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

            # Determine target count.
            # PR-D (Phase 2): canonical task_source is now "event_driven";
            # the resolver still understands legacy "manual_event" /
            # "auto_event" but new code paths feed the unified value.
            target_count = resolve_target_count(
                confidence=impact.confidence,
                intensity=impact.magnitude,
                theme_breadth=impact.breadth,
                task_source="event_driven",
                feature_flag_target_max=feature_flag_max,
            )

            symbols = basket.symbols[:target_count]
            if not symbols:
                continue

            # PR-C: stable dedupe_key for outbox / scan idempotency.
            # Format: event_id:theme_code:N-symbols-checksum.
            symbols_signature = "-".join(symbols)[:64]
            dedupe_key = f"{event.event_id}:{impact.theme_code}:{symbols_signature}"

            # Build task with unified task_source="event_driven" + event_source
            task = _build_event_task(
                event,
                impact,
                symbols,
                event_source=event_source,
                dedupe_key=dedupe_key,
            )
            all_tasks.append(task)

            # Record lineage
            lineage_records.append({
                "dedupe_key": dedupe_key,
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
    if persist_lineage and lineage_records and hasattr(db, "upsert_event_task_lineage"):
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
        "lineage_records": lineage_records,
        "persist_lineage": bool(persist_lineage),
        "feature_flag_target_max": feature_flag_max,
    }


__all__ = [
    "generate_tasks_from_active_events",
    "MANUAL_EVENT_ENABLED",
    "THEME_GRAPH_ENABLED",
]
