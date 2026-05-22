"""Dynamic target count resolution (PR-5, §4.1).

Replaces the fixed OPPORTUNITY_TARGET_SYMBOLS_PER_TASK = 8 with a
context-aware formula that considers event confidence, intensity,
theme breadth, and task source.

The feature flag STRATEGY_FACTORY_DYNAMIC_TARGET_COUNT_ENABLED controls
whether the dynamic formula is used. When disabled, falls back to the
legacy fixed value (8 for snapshot, 12 max for events).
"""

from __future__ import annotations

import os
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


DYNAMIC_TARGET_COUNT_ENABLED = _env_bool("STRATEGY_FACTORY_DYNAMIC_TARGET_COUNT_ENABLED", False)
TARGET_COUNT_MIN = int(os.getenv("STRATEGY_FACTORY_TARGET_COUNT_MIN") or 3)
TARGET_COUNT_MAX = int(os.getenv("STRATEGY_FACTORY_TARGET_COUNT_MAX") or 30)


def resolve_target_count(
    *,
    confidence: float = 0.7,
    intensity: float = 0.5,
    theme_breadth: str = "medium",
    task_source: str = "auto_event",
    feature_flag_target_max: Optional[int] = None,
) -> int:
    """Compute dynamic target count based on event/theme context.

    Args:
        confidence: Event confidence [0, 1].
        intensity: Event intensity [0, 1].
        theme_breadth: "narrow" / "medium" / "broad".
        task_source: "manual_event" / "auto_event" / "snapshot".
        feature_flag_target_max: Override max (if None, uses env config).

    Returns:
        Target count in [TARGET_COUNT_MIN, effective_max].
    """
    if feature_flag_target_max is None:
        feature_flag_target_max = TARGET_COUNT_MAX if DYNAMIC_TARGET_COUNT_ENABLED else 12

    base_by_breadth = {"narrow": 5, "medium": 10, "broad": 18}
    base = base_by_breadth.get(theme_breadth, 10)

    evidence = max(0.0, min(1.0, confidence)) * 0.55 + max(0.0, min(1.0, intensity)) * 0.45
    stretch = evidence ** 1.3
    dynamic = base + stretch * 12

    if task_source == "manual_event":
        dynamic += 3

    if task_source == "snapshot":
        dynamic = min(dynamic, 12)

    upper = max(TARGET_COUNT_MIN, min(feature_flag_target_max, 30))
    return max(TARGET_COUNT_MIN, min(upper, int(round(dynamic))))


def resolve_target_symbol_limit(
    *,
    task_source: str = "snapshot",
    validation_focus: Optional[str] = None,
    configured_target_count: Optional[int] = None,
) -> int:
    """Resolve the target symbol limit for a given context.

    This is the single entry point that replaces all hardcoded `limit=12`
    calls throughout the codebase (§4.2 stage 5a).

    Args:
        task_source: Origin of the task.
        validation_focus: Validation focus mode.
        configured_target_count: Explicit target count from research task.

    Returns:
        Maximum number of target symbols allowed.
    """
    if configured_target_count is not None and configured_target_count > 0:
        if not DYNAMIC_TARGET_COUNT_ENABLED:
            return min(configured_target_count, 12)
        return min(configured_target_count, TARGET_COUNT_MAX)

    if not DYNAMIC_TARGET_COUNT_ENABLED:
        return 12

    if task_source in ("manual_event", "auto_event"):
        return TARGET_COUNT_MAX

    if task_source == "bulk_stock_matrix":
        return 1

    # Default: snapshot and other sources
    return 12


__all__ = [
    "DYNAMIC_TARGET_COUNT_ENABLED",
    "TARGET_COUNT_MAX",
    "TARGET_COUNT_MIN",
    "resolve_target_count",
    "resolve_target_symbol_limit",
]
