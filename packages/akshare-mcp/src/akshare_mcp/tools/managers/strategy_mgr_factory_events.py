"""Strategy Manager handlers for factory event injection (PR-2).

Actions:
  factory_event_create         — Create a new event injection
  factory_event_list           — List event injections (filterable)
  factory_event_update         — Update event (pause/expire/edit)
  factory_event_approve        — Approve a pending_review event
  factory_event_record_outcome — Record actual outcome after event expires
  factory_event_preview_tasks  — Preview tasks that would be generated (dry-run)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string(value: Any) -> str:
    return str(value or "").strip()


async def handle_factory_event_create(db, params: dict[str, Any]) -> dict[str, Any]:
    """Create a new event injection."""
    event_name = _string(params.get("event_name"))
    event_type = _string(params.get("event_type"))
    if not event_name or not event_type:
        return {"success": False, "error": "event_name and event_type are required"}

    primary_themes = params.get("primary_themes") or []
    if not primary_themes:
        return {"success": False, "error": "primary_themes is required (at least one theme)"}

    confidence = float(params.get("confidence") or 0.7)
    intensity = float(params.get("intensity") or 0.5)

    # High intensity or market scope requires approval
    scope = _string(params.get("scope")) or "theme"
    require_approval = (
        intensity >= 0.8
        or scope == "market"
        or len(primary_themes) >= 10
    )
    initial_status = "pending_review" if require_approval else "active"
    if params.get("force_pending"):
        initial_status = "pending_review"

    event_id = _string(params.get("event_id")) or f"manual_{uuid4().hex[:12]}"
    valid_from = _string(params.get("valid_from")) or _now_iso()
    valid_until = _string(params.get("valid_until")) or ""

    # Default valid_until based on horizon
    if not valid_until:
        horizon = _string(params.get("horizon")) or "swing_5_20d"
        from datetime import timedelta
        horizon_days = {
            "intraday": 1,
            "swing_1_5d": 5,
            "swing_5_20d": 20,
            "macro_1m": 30,
            "macro_3m": 90,
        }.get(horizon, 20)
        try:
            start = datetime.fromisoformat(valid_from.replace("Z", "+00:00"))
        except Exception:
            start = datetime.now(timezone.utc)
        valid_until = (start + timedelta(days=horizon_days)).isoformat()

    payload = {
        "event_id": event_id,
        "source": _string(params.get("source")) or "manual",
        "event_name": event_name,
        "event_type": event_type,
        "direction": params.get("direction"),
        "confidence": confidence,
        "intensity": intensity,
        "horizon": _string(params.get("horizon")) or "swing_5_20d",
        "scope": scope,
        "primary_themes": primary_themes,
        "rationale": params.get("rationale"),
        "evidence": params.get("evidence") or {},
        "valid_from": valid_from,
        "valid_until": valid_until,
        "status": initial_status,
        "operator_id": params.get("operator_id"),
    }

    result = await db.upsert_event_injection(payload)
    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "status": initial_status,
            "require_approval": require_approval,
            "valid_from": valid_from,
            "valid_until": valid_until,
        },
    }


async def handle_factory_event_list(db, params: dict[str, Any]) -> dict[str, Any]:
    """List event injections with optional filters."""
    status = params.get("status")
    source = params.get("source")
    limit = int(params.get("limit") or 50)

    events = await db.list_event_injections(
        status=status,
        source=source,
        limit=limit,
    )
    return {
        "success": True,
        "data": {
            "events": events,
            "count": len(events),
            "filters": {"status": status, "source": source},
        },
    }


async def handle_factory_event_update(db, params: dict[str, Any]) -> dict[str, Any]:
    """Update an event (pause, expire, edit fields)."""
    event_id = _string(params.get("event_id") or params.get("id"))
    if not event_id:
        return {"success": False, "error": "event_id is required"}

    action = _string(params.get("action"))
    if action == "pause":
        payload = {"event_id": event_id, "status": "paused"}
    elif action == "expire":
        payload = {"event_id": event_id, "status": "expired"}
    elif action == "activate":
        payload = {"event_id": event_id, "status": "active"}
    elif action == "reject":
        payload = {"event_id": event_id, "status": "rejected"}
    else:
        # General update — pass through allowed fields
        payload = {"event_id": event_id}
        for field in ("event_name", "event_type", "direction", "confidence",
                      "intensity", "horizon", "scope", "primary_themes",
                      "rationale", "evidence", "valid_from", "valid_until", "status"):
            if field in params:
                payload[field] = params[field]

    result = await db.upsert_event_injection(payload)
    return {"success": True, "data": {"event_id": event_id, "updated": True}}


async def handle_factory_event_approve(db, params: dict[str, Any]) -> dict[str, Any]:
    """Approve a pending_review event (dual-person review)."""
    event_id = _string(params.get("event_id") or params.get("id"))
    approver_id = _string(params.get("approver_id"))
    if not event_id:
        return {"success": False, "error": "event_id is required"}

    # Fetch current event to verify it's pending
    events = await db.list_event_injections(status="pending_review", limit=200)
    target = next((e for e in events if e.get("event_id") == event_id), None)
    if target is None:
        return {"success": False, "error": f"Event {event_id} not found or not in pending_review status"}

    # Cannot self-approve
    operator = _string(target.get("operator_id"))
    if approver_id and approver_id == operator:
        return {"success": False, "error": "Cannot self-approve: approver must differ from operator"}

    payload = {
        "event_id": event_id,
        "status": "active",
    }
    await db.upsert_event_injection(payload)
    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "status": "active",
            "approved_by": approver_id,
            "approved_at": _now_iso(),
        },
    }


async def handle_factory_event_record_outcome(db, params: dict[str, Any]) -> dict[str, Any]:
    """Record actual outcome after event expires."""
    event_id = _string(params.get("event_id") or params.get("id"))
    actual_outcome = _string(params.get("actual_outcome"))
    if not event_id or not actual_outcome:
        return {"success": False, "error": "event_id and actual_outcome are required"}

    if actual_outcome not in ("positive", "negative", "mixed", "no_effect"):
        return {"success": False, "error": f"actual_outcome must be one of: positive, negative, mixed, no_effect"}

    outcome_notes = params.get("outcome_notes")
    result = await db.update_event_outcome(
        event_id,
        actual_outcome=actual_outcome,
        outcome_notes=outcome_notes,
    )
    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "actual_outcome": actual_outcome,
            "recorded_at": _now_iso(),
        },
    }


async def handle_factory_event_preview_tasks(db, params: dict[str, Any]) -> dict[str, Any]:
    """Preview tasks that would be generated from an event (dry-run, no side effects).

    This is a simplified preview that shows theme propagation results.
    Full task generation requires PR-3 (theme_graph.py) and PR-6 (scan integration).
    """
    event_id = _string(params.get("event_id") or params.get("id"))
    primary_themes = params.get("primary_themes") or []
    confidence = float(params.get("confidence") or 0.7)
    intensity = float(params.get("intensity") or 0.5)
    direction = params.get("direction")

    if not primary_themes and event_id:
        # Try to load from DB
        events = await db.list_event_injections(limit=200)
        target = next((e for e in events if e.get("event_id") == event_id), None)
        if target:
            primary_themes = target.get("primary_themes") or []
            confidence = float(target.get("confidence") or confidence)
            intensity = float(target.get("intensity") or intensity)
            direction = target.get("direction") or direction

    if not primary_themes:
        return {"success": False, "error": "No primary_themes found for preview"}

    # Load theme edges for propagation preview
    preview_impacts = []
    for pt in primary_themes:
        theme_code = pt.get("theme_code") if isinstance(pt, dict) else str(pt)
        pt_direction = (pt.get("direction") if isinstance(pt, dict) else direction) or "positive"
        dir_sign = 1 if pt_direction == "positive" else (-1 if pt_direction == "negative" else 0)

        # Direct impact
        preview_impacts.append({
            "theme_code": theme_code,
            "direction_sign": dir_sign,
            "magnitude": intensity,
            "confidence": confidence,
            "depth": 0,
            "source": "primary",
        })

        # Load edges from this theme (depth=1)
        edges = await db.list_theme_edges(source=theme_code, is_active=True, limit=50)
        for edge in edges:
            new_dir = dir_sign * int(edge.get("direction_sign") or 1)
            new_mag = intensity * float(edge.get("magnitude_factor") or 0.5)
            new_conf = confidence * float(edge.get("confidence") or 0.5)
            if new_mag < 0.15 or new_conf < 0.25:
                continue
            preview_impacts.append({
                "theme_code": edge.get("target_theme_code"),
                "direction_sign": new_dir,
                "magnitude": round(new_mag, 4),
                "confidence": round(new_conf, 4),
                "depth": 1,
                "source": f"{theme_code} → {edge.get('relation_type')}",
                "lag_days": int(edge.get("lag_days") or 0),
            })

    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "primary_theme_count": len(primary_themes),
            "total_impacts": len(preview_impacts),
            "impacts": preview_impacts,
            "note": "This is a preview. Full task generation requires PR-3/PR-6 integration.",
        },
    }
