"""Theme graph propagation algorithm (PR-3).

Implements BFS event-to-theme propagation with magnitude decay and
confidence thresholds. This module is the core of Layer B in the
event-driven upgrade plan.

Usage:
    impacts = await propagate_event_to_themes(db, event)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class NormalizedEvent:
    """Normalized event input for theme propagation."""

    event_id: str
    source: str = "manual"
    event_name: str = ""
    event_type: str = ""
    direction: Optional[str] = None
    confidence: float = 0.7
    intensity: float = 0.5
    horizon: str = "swing_5_20d"
    scope: str = "theme"
    primary_themes: list[dict[str, Any]] = field(default_factory=list)
    rationale: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedEvent":
        return cls(
            event_id=str(data.get("event_id") or "").strip(),
            source=str(data.get("source") or "manual").strip(),
            event_name=str(data.get("event_name") or "").strip(),
            event_type=str(data.get("event_type") or "").strip(),
            direction=data.get("direction"),
            confidence=float(data.get("confidence") or 0.7),
            intensity=float(data.get("intensity") or 0.5),
            horizon=str(data.get("horizon") or "swing_5_20d").strip(),
            scope=str(data.get("scope") or "theme").strip(),
            primary_themes=list(data.get("primary_themes") or []),
            rationale=data.get("rationale"),
        )


@dataclass
class ThemeImpact:
    """Result of theme propagation for a single theme."""

    theme_code: str
    direction_sign: int  # +1, -1, 0
    magnitude: float
    confidence: float
    lag_days: int = 0
    depth: int = 0
    breadth: str = "medium"
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme_code": self.theme_code,
            "direction_sign": self.direction_sign,
            "magnitude": round(self.magnitude, 4),
            "confidence": round(self.confidence, 4),
            "lag_days": self.lag_days,
            "depth": self.depth,
            "breadth": self.breadth,
            "source_path": self.source_path,
        }


def normalize_direction_sign(direction: Any) -> int:
    """Convert direction to numeric sign: +1, -1, or 0."""
    if isinstance(direction, int):
        return max(-1, min(1, direction))
    if isinstance(direction, float):
        return 1 if direction > 0 else (-1 if direction < 0 else 0)
    text = str(direction or "").strip().lower()
    if text in ("positive", "up", "bullish", "long", "+1", "1"):
        return 1
    if text in ("negative", "down", "bearish", "short", "-1"):
        return -1
    return 0


async def propagate_event_to_themes(
    db: Any,
    event: NormalizedEvent,
    *,
    max_depth: int = 2,
    min_magnitude: float = 0.15,
    min_confidence: float = 0.25,
) -> list[ThemeImpact]:
    """BFS propagation from event primary themes through the theme graph.

    Args:
        db: Database adapter with `list_theme_edges` and `get_theme_node` methods.
        event: Normalized event with primary themes.
        max_depth: Maximum graph traversal depth (default 2).
        min_magnitude: Prune branches below this magnitude.
        min_confidence: Prune branches below this confidence.

    Returns:
        List of ThemeImpact objects, one per affected theme.
    """
    impacts: dict[str, ThemeImpact] = {}

    # Initialize frontier from primary themes
    frontier: list[tuple[str, int, float, float, int, int, str]] = []
    for pt in event.primary_themes:
        if isinstance(pt, dict):
            theme_code = str(pt.get("theme_code") or "").strip()
            pt_direction = pt.get("direction") or event.direction
        else:
            theme_code = str(pt).strip()
            pt_direction = event.direction

        if not theme_code:
            continue

        dir_sign = normalize_direction_sign(pt_direction)
        frontier.append((
            theme_code,
            dir_sign,
            event.confidence,
            event.intensity,
            0,  # lag_days
            0,  # depth
            "primary",  # source_path
        ))

    # BFS traversal
    while frontier:
        theme_code, dir_sign, conf, mag, lag, depth, path = frontier.pop(0)

        # Resolve breadth from theme node
        breadth = "medium"
        node = None
        if hasattr(db, "get_theme_node"):
            node = await db.get_theme_node(theme_code)
        if node:
            breadth = str(node.get("breadth") or "medium").strip()

        # Merge: keep the stronger impact for each theme
        existing = impacts.get(theme_code)
        if existing is None or mag > existing.magnitude:
            impacts[theme_code] = ThemeImpact(
                theme_code=theme_code,
                direction_sign=dir_sign,
                magnitude=mag,
                confidence=conf,
                lag_days=lag,
                depth=depth,
                breadth=breadth,
                source_path=path,
            )

        # Don't expand beyond max_depth
        if depth >= max_depth:
            continue

        # Load outgoing edges
        edges = []
        if hasattr(db, "list_theme_edges"):
            edges = await db.list_theme_edges(source=theme_code, is_active=True, limit=50)

        for edge in edges:
            target = str(edge.get("target_theme_code") or "").strip()
            if not target:
                continue

            # Skip if edge is manually locked and we're at depth > 0
            # (locked edges still propagate from primary themes)

            new_dir = dir_sign * int(edge.get("direction_sign") or 1)
            new_mag = mag * float(edge.get("magnitude_factor") or 0.5)
            new_conf = conf * float(edge.get("confidence") or 0.5)
            new_lag = lag + int(edge.get("lag_days") or 0)

            # Prune weak signals
            if new_mag < min_magnitude or new_conf < min_confidence:
                continue

            new_path = f"{path} → {edge.get('relation_type', '?')} → {target}"
            frontier.append((
                target, new_dir, new_conf, new_mag,
                new_lag, depth + 1, new_path,
            ))

    return list(impacts.values())


__all__ = [
    "NormalizedEvent",
    "ThemeImpact",
    "normalize_direction_sign",
    "propagate_event_to_themes",
]
