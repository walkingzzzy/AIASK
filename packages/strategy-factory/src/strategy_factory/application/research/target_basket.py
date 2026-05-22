"""Target basket resolution from theme impacts (PR-3).

Implements Layer C: given a ThemeImpact, resolve which stocks to target
based on theme exposure scores, with industry diversification.

Usage:
    basket = await resolve_target_basket(db, impact)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .theme_graph import ThemeImpact


@dataclass
class TargetBasket:
    """Resolved stock basket for a theme impact."""

    theme_code: str
    symbols: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme_code": self.theme_code,
            "symbols": self.symbols,
            "symbol_count": len(self.symbols),
            "weights": self.weights,
            "evidence": self.evidence,
        }


def resolve_target_count(
    *,
    confidence: float,
    intensity: float,
    theme_breadth: str,
    task_source: str,
    feature_flag_target_max: int = 12,
) -> int:
    """Compute dynamic target count based on event/theme context.

    See §4.1 of the upgrade plan for the formula derivation.
    """
    base_by_breadth = {"narrow": 5, "medium": 10, "broad": 18}
    base = base_by_breadth.get(theme_breadth, 10)

    evidence = confidence * 0.55 + intensity * 0.45
    stretch = evidence ** 1.3
    dynamic = base + stretch * 12

    if task_source == "manual_event":
        dynamic += 3

    if task_source == "snapshot":
        dynamic = min(dynamic, 12)

    upper = max(3, min(feature_flag_target_max, 30))
    return max(3, min(upper, int(round(dynamic))))


def apply_industry_diversification(
    rows: list[dict[str, Any]],
    *,
    max_per_industry: int = 3,
    target_count: int = 30,
) -> list[dict[str, Any]]:
    """Select stocks with industry diversification constraint.

    Args:
        rows: Sorted by exposure_score descending.
        max_per_industry: Max stocks per industry.
        target_count: Total target count.

    Returns:
        Diversified subset of rows.
    """
    selected: list[dict[str, Any]] = []
    industry_counts: dict[str, int] = {}

    for row in rows:
        if len(selected) >= target_count:
            break
        industry = str(row.get("industry") or row.get("industry_tag") or "unknown").strip()
        current = industry_counts.get(industry, 0)
        if current >= max_per_industry:
            continue
        selected.append(row)
        industry_counts[industry] = current + 1

    return selected


async def resolve_target_basket(
    db: Any,
    impact: ThemeImpact,
    *,
    target_count: int | None = None,
    max_per_industry: int = 3,
    min_exposure: float = 0.3,
    feature_flag_target_max: int = 12,
) -> TargetBasket:
    """Resolve target stock basket for a theme impact.

    Args:
        db: Database adapter with `list_theme_exposure` or equivalent.
        impact: ThemeImpact from propagation.
        target_count: Override target count (if None, computed dynamically).
        max_per_industry: Industry diversification limit.
        min_exposure: Minimum exposure score threshold.
        feature_flag_target_max: Max target count allowed by feature flag.

    Returns:
        TargetBasket with selected symbols.
    """
    # Compute dynamic target count if not overridden
    if target_count is None:
        target_count = resolve_target_count(
            confidence=impact.confidence,
            intensity=impact.magnitude,
            theme_breadth=impact.breadth,
            task_source="manual_event",
            feature_flag_target_max=feature_flag_target_max,
        )

    # Load exposure data
    rows: list[dict[str, Any]] = []
    if hasattr(db, "list_theme_exposure"):
        # Future: dedicated exposure table query
        try:
            rows = await db.list_theme_exposure(
                theme_code=impact.theme_code,
                min_exposure=min_exposure,
                limit=50,
            )
        except Exception:
            rows = []

    if not rows:
        # Fallback: try concept_detail or return empty
        return TargetBasket(
            theme_code=impact.theme_code,
            symbols=[],
            evidence={
                "reason": "no_exposure_data",
                "theme_code": impact.theme_code,
                "min_exposure": min_exposure,
            },
        )

    # For negative impacts, filter out stocks already down significantly
    if impact.direction_sign < 0:
        rows = [r for r in rows if float(r.get("return_20d") or 0) > -0.15]

    # Apply industry diversification
    selected = apply_industry_diversification(
        rows,
        max_per_industry=max_per_industry,
        target_count=target_count,
    )

    symbols = [str(r.get("symbol") or "").strip() for r in selected if r.get("symbol")]

    # Compute exposure-weighted weights
    total_exposure = sum(float(r.get("exposure_score") or 0) for r in selected)
    weights = {}
    if total_exposure > 0:
        for r in selected:
            sym = str(r.get("symbol") or "").strip()
            if sym:
                weights[sym] = round(float(r.get("exposure_score") or 0) / total_exposure, 4)

    return TargetBasket(
        theme_code=impact.theme_code,
        symbols=symbols[:target_count],
        weights=weights,
        evidence={
            "exposure_rule_version": "v1",
            "target_count_resolved": target_count,
            "avg_exposure_score": round(
                sum(float(r.get("exposure_score") or 0) for r in selected) / max(len(selected), 1),
                4,
            ),
            "industry_count": len(set(
                str(r.get("industry") or "unknown") for r in selected
            )),
            "direction_sign": impact.direction_sign,
            "magnitude": impact.magnitude,
            "confidence": impact.confidence,
        },
    )


__all__ = [
    "TargetBasket",
    "apply_industry_diversification",
    "resolve_target_basket",
    "resolve_target_count",
]
