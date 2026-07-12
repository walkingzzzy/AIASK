"""Pure promotion-ready verdict schema owned by Strategy Factory.

Host overview builders may still load DB context; the boolean combination
and threshold floors for signal-quality promotion live here so they can be
unit-tested without MCP/DB.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


# Locked signal-quality floors used by build_incubation_overview promotion_ready.
PROMOTION_PRIMARY_EFFECTIVE_N_MIN: int = 60
PROMOTION_SECONDARY_EFFECTIVE_N_MIN: int = 30
PROMOTION_COVERAGE_RATIO_MIN: float = 0.75
PROMOTION_STABILITY_GAP_MAX: float = 0.05


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _string(value: Any) -> str:
    return str(value or "").strip()


def evaluate_promotion_ready(
    *,
    primary_effective_n: Any = 0,
    secondary_effective_n: Any = 0,
    primary_skill_lcb: Any = None,
    secondary_skill_lcb: Any = None,
    recent_primary_skill_lcb: Any = None,
    coverage_ratio: Any = 0.0,
    stability_gap: Any = None,
    execution_hard_gate_passed: bool = False,
    risk_hard_gate_status: str = "passed",
    blockers: Sequence[str] | None = None,
    cross_regime_enabled: bool = False,
    cross_regime_passed: bool = True,
    cross_regime_negative_labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Evaluate pure promotion_ready combination (no DB I/O).

    Mirrors the core boolean block in strategy lifecycle overview so hosts
    can delegate without duplicating floors.
    """
    primary_n = _safe_int(primary_effective_n)
    secondary_n = _safe_int(secondary_effective_n)
    primary_lcb = _safe_float(primary_skill_lcb)
    secondary_lcb = _safe_float(secondary_skill_lcb)
    recent_lcb = _safe_float(recent_primary_skill_lcb)
    coverage = _safe_float(coverage_ratio) or 0.0
    stability = _safe_float(stability_gap)
    risk_status = _string(risk_hard_gate_status) or "passed"
    blocker_list = [str(item) for item in list(blockers or []) if str(item)]

    checks = {
        "primary_effective_n": primary_n >= PROMOTION_PRIMARY_EFFECTIVE_N_MIN,
        "secondary_effective_n": secondary_n >= PROMOTION_SECONDARY_EFFECTIVE_N_MIN,
        "primary_skill_lcb": (primary_lcb or 0.0) > 0.0,
        "secondary_skill_lcb": (secondary_lcb or 0.0) > 0.0,
        "recent_primary_skill_lcb": (recent_lcb or 0.0) > 0.0,
        "coverage_ratio": coverage >= PROMOTION_COVERAGE_RATIO_MIN,
        "stability_gap": stability is not None and stability <= PROMOTION_STABILITY_GAP_MAX,
        "execution_hard_gate_passed": bool(execution_hard_gate_passed),
        "risk_hard_gate_status": risk_status == "passed",
        "no_blockers": not blocker_list,
    }
    promotion_ready = all(checks.values())
    extra_blockers: list[str] = list(blocker_list)
    if stability is None and "stability_gap_missing" not in extra_blockers:
        extra_blockers.append("stability_gap_missing")

    if cross_regime_enabled and promotion_ready and not cross_regime_passed:
        promotion_ready = False
        for tag in list(cross_regime_negative_labels or []):
            label = _string(tag)
            if not label:
                continue
            reason = f"cross_regime_skill_lcb_non_positive:{label}"
            if reason not in extra_blockers:
                extra_blockers.append(reason)
        checks["cross_regime_skill"] = False
    elif cross_regime_enabled:
        checks["cross_regime_skill"] = bool(cross_regime_passed)
    else:
        checks["cross_regime_skill"] = True

    failed = [name for name, ok in checks.items() if not ok]
    return {
        "promotion_ready": bool(promotion_ready),
        "checks": checks,
        "failed_checks": failed,
        "blockers": extra_blockers,
        "floors": {
            "primary_effective_n_min": PROMOTION_PRIMARY_EFFECTIVE_N_MIN,
            "secondary_effective_n_min": PROMOTION_SECONDARY_EFFECTIVE_N_MIN,
            "coverage_ratio_min": PROMOTION_COVERAGE_RATIO_MIN,
            "stability_gap_max": PROMOTION_STABILITY_GAP_MAX,
        },
    }


def evaluate_promotion_ready_from_signal_quality(
    signal_quality: Mapping[str, Any] | None,
    *,
    execution_hard_gate_passed: bool = False,
    risk_hard_gate_status: str = "passed",
    blockers: Sequence[str] | None = None,
    cross_regime_enabled: bool = False,
    cross_regime_passed: bool = True,
    cross_regime_negative_labels: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Convenience wrapper taking a signal-quality-like mapping."""
    quality = dict(signal_quality or {})
    return evaluate_promotion_ready(
        primary_effective_n=quality.get("primary_effective_n"),
        secondary_effective_n=quality.get("secondary_effective_n"),
        primary_skill_lcb=quality.get("primary_skill_lcb"),
        secondary_skill_lcb=quality.get("secondary_skill_lcb"),
        recent_primary_skill_lcb=quality.get("recent_primary_skill_lcb"),
        coverage_ratio=quality.get("coverage_ratio"),
        stability_gap=quality.get("stability_gap"),
        execution_hard_gate_passed=execution_hard_gate_passed,
        risk_hard_gate_status=risk_hard_gate_status,
        blockers=blockers,
        cross_regime_enabled=cross_regime_enabled,
        cross_regime_passed=cross_regime_passed,
        cross_regime_negative_labels=cross_regime_negative_labels,
    )


__all__ = [
    "PROMOTION_COVERAGE_RATIO_MIN",
    "PROMOTION_PRIMARY_EFFECTIVE_N_MIN",
    "PROMOTION_SECONDARY_EFFECTIVE_N_MIN",
    "PROMOTION_STABILITY_GAP_MAX",
    "evaluate_promotion_ready",
    "evaluate_promotion_ready_from_signal_quality",
]
