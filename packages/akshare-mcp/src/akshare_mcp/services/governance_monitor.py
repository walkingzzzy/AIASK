"""Unified governance monitoring service.

Aggregates 5 monitoring dimensions into a single ``GovernanceReport``:

1. Factor Decay Monitor — detects IC degradation in factor candidates
2. Crowding Monitor — estimates factor crowding risk
3. Model Drift / Calibration Drift — flags model quality degradation
4. Strategy Runtime Health — surfaces strategy posture & alert state
5. Online/Offline Consistency — compares backtest vs execution assumptions

Usage::

    from akshare_mcp.services.governance_monitor import GovernanceMonitor

    monitor = GovernanceMonitor()
    report = monitor.run_full_check(target_type="system")
    report_dict = report.to_dict()

"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = _mean(values)
    if m is None:
        return None
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


# ── 1. Factor Decay Monitor ──────────────────────────────────────────────────

def check_factor_decay(
    factor_name: str,
    ic_history: list[float] | None = None,
    *,
    window: int = 8,
    decay_threshold: float = 0.015,
) -> dict[str, Any]:
    """Check whether a factor's IC is decaying over time.

    Parameters
    ----------
    factor_name:
        Human‐readable factor identifier.
    ic_history:
        Chronological list of IC values (e.g. weekly or monthly).
    window:
        Number of recent periods for the "recent" window.
    decay_threshold:
        Absolute drop from all-time mean that triggers "decaying" status.

    Returns
    -------
    dict with decay_status, rolling_ic_trend, half_life_estimate, etc.
    """
    values = [float(v) for v in (ic_history or []) if v is not None]
    if len(values) < 4:
        return {
            "factor_name": factor_name,
            "decay_status": "unknown",
            "reason": "insufficient_history",
            "evaluation_count": len(values),
            "action_recommended": "collect_more_data",
        }

    all_mean = _mean(values)
    all_std = _std(values)
    recent = values[-min(window, len(values)):]
    recent_mean = _mean(recent)

    # Trend detection: compare first half vs second half
    half = len(values) // 2
    early_mean = _mean(values[:max(half, 1)])
    late_mean = _mean(values[max(half, 1):])

    if early_mean is not None and late_mean is not None:
        if late_mean < early_mean - decay_threshold:
            trend = "decaying"
        elif late_mean > early_mean + decay_threshold:
            trend = "improving"
        else:
            trend = "stable"
    else:
        trend = "unknown"

    # Decay status
    degradation = (
        round(float(all_mean) - float(recent_mean), 6)
        if all_mean is not None and recent_mean is not None
        else None
    )
    if degradation is not None and degradation > decay_threshold * 2:
        status = "decayed"
    elif degradation is not None and degradation > decay_threshold:
        status = "decaying"
    else:
        status = "stable"

    # Half-life estimate (rough: number of periods for IC to halve)
    half_life: float | None = None
    if trend == "decaying" and early_mean and late_mean and early_mean > 0:
        decay_rate = (early_mean - late_mean) / max(half, 1)
        if decay_rate > 0:
            half_life = round(early_mean / (2 * decay_rate), 1)

    action = (
        "retire_or_replace" if status == "decayed"
        else "review_and_monitor" if status == "decaying"
        else "continue_monitoring"
    )

    return {
        "factor_name": factor_name,
        "decay_status": status,
        "evaluation_count": len(values),
        "all_time_ic_mean": round(float(all_mean), 6) if all_mean is not None else None,
        "all_time_ic_std": round(float(all_std), 6) if all_std is not None else None,
        "recent_ic_mean": round(float(recent_mean), 6) if recent_mean is not None else None,
        "degradation_vs_mean": degradation,
        "rolling_ic_trend": trend,
        "half_life_estimate_periods": half_life,
        "action_recommended": action,
    }


# ── 2. Crowding Monitor ──────────────────────────────────────────────────────

_CROWDED_CATEGORIES = {
    "momentum": 0.85,
    "reversal": 0.70,
    "value": 0.65,
    "size": 0.80,
    "volatility": 0.55,
    "volume": 0.50,
    "quality": 0.40,
    "growth": 0.45,
    "sentiment": 0.35,
    "technical": 0.60,
}

_CROWDED_TOKENS = {
    "momentum", "pct_change", "return", "reversal", "mean_revert",
    "sma", "ema", "rsi", "macd", "bollinger", "volume_ratio",
}


def check_crowding(
    factor_name: str,
    expression: str = "",
    category: str | None = None,
    existing_pool: list[str] | None = None,
) -> dict[str, Any]:
    """Estimate crowding risk for a factor.

    Returns
    -------
    dict with crowding_score, crowding_band, similar_factors, warning.
    """
    expr_lower = str(expression or factor_name or "").lower()
    pool = [str(f).lower() for f in (existing_pool or [])]

    # Category-based base score
    cat = str(category or "").strip().lower()
    base_score = _CROWDED_CATEGORIES.get(cat, 0.3)

    # Token-based boost
    token_hits = sum(1 for t in _CROWDED_TOKENS if t in expr_lower)
    token_boost = min(token_hits * 0.08, 0.3)

    # Pool similarity boost
    similar_count = 0
    if pool:
        name_tokens = set(expr_lower.replace("_", " ").replace("(", " ").split())
        for existing in pool:
            existing_tokens = set(existing.replace("_", " ").replace("(", " ").split())
            overlap = len(name_tokens & existing_tokens)
            if overlap >= 2 or existing in expr_lower or expr_lower in existing:
                similar_count += 1
    similarity_boost = min(similar_count * 0.05, 0.2)

    score = round(min(base_score + token_boost + similarity_boost, 1.0), 3)
    band = "high" if score >= 0.7 else ("medium" if score >= 0.4 else "low")

    warnings: list[str] = []
    if band == "high":
        warnings.append(f"因子 '{factor_name}' 拥挤度高 ({score:.2f})，alpha 衰减风险大")
    if similar_count >= 3:
        warnings.append(f"池中有 {similar_count} 个相似因子，需审视增量价值")

    return {
        "factor_name": factor_name,
        "crowding_score": score,
        "crowding_band": band,
        "category": cat or "unspecified",
        "token_hits": token_hits,
        "similar_factor_count": similar_count,
        "warnings": warnings,
    }


# ── 3. Model Drift / Calibration Drift ───────────────────────────────────────

def check_model_drift(
    model_name: str,
    current_metrics: dict[str, Any] | None = None,
    baseline_metrics: dict[str, Any] | None = None,
    *,
    brier_threshold: float = 0.03,
    ece_threshold: float = 0.05,
    ic_threshold: float = 0.02,
    stability_threshold: float = 0.50,
) -> dict[str, Any]:
    """Compare current model metrics against a baseline to detect drift.

    Parameters
    ----------
    current_metrics:
        Dict with optional keys: brier_score, ece, rank_ic_mean,
        stability_ratio, total_score.
    baseline_metrics:
        Same shape as current_metrics, representing historical baseline.

    Returns
    -------
    dict with drift_status, drift_dimensions, severity, action_recommended.
    """
    cur = dict(current_metrics or {})
    base = dict(baseline_metrics or {})

    dimensions: dict[str, dict[str, Any]] = {}
    issues: list[str] = []

    def _check(key: str, threshold: float, higher_is_better: bool = True) -> None:
        c = _safe_float(cur.get(key))
        b = _safe_float(base.get(key))
        if c is None or b is None:
            dimensions[key] = {"current": c, "baseline": b, "status": "unknown"}
            return
        delta = float(c) - float(b)
        if abs(delta) <= threshold:
            status = "stable"
        elif (delta > 0) == higher_is_better:
            status = "improved"
        else:
            status = "degraded"
            issues.append(key)
        dimensions[key] = {
            "current": round(c, 6),
            "baseline": round(b, 6),
            "delta": round(delta, 6),
            "status": status,
        }

    _check("brier_score", brier_threshold, higher_is_better=False)
    _check("ece", ece_threshold, higher_is_better=False)
    _check("rank_ic_mean", ic_threshold, higher_is_better=True)
    _check("stability_ratio", stability_threshold, higher_is_better=True)
    _check("total_score", 5.0, higher_is_better=True)

    overall = (
        "degraded" if len(issues) >= 2
        else "warning" if len(issues) == 1
        else "stable" if any(d["status"] != "unknown" for d in dimensions.values())
        else "unknown"
    )
    severity = (
        "high" if len(issues) >= 3
        else "medium" if overall in ("degraded", "warning")
        else "low"
    )
    action = (
        "retrain_or_retire" if overall == "degraded" and severity == "high"
        else "review_model" if overall in ("degraded", "warning")
        else "continue_monitoring"
    )

    return {
        "model_name": model_name,
        "drift_status": overall,
        "severity": severity,
        "degraded_dimensions": issues,
        "dimensions": dimensions,
        "action_recommended": action,
    }


# ── 4. Strategy Runtime Health ────────────────────────────────────────────────

def check_strategy_health(
    strategy_id: str,
    posture_level: str = "safe",
    control_mode: str = "active",
    open_alert_count: int = 0,
    recovery_eligible: bool = False,
    max_drawdown_pct: float | None = None,
    days_since_last_trade: int | None = None,
) -> dict[str, Any]:
    """Assess strategy runtime health from posture and alert data.

    Returns
    -------
    dict with health_status, issues, action_recommended.
    """
    issues: list[str] = []

    posture = str(posture_level or "safe").strip().lower()
    mode = str(control_mode or "active").strip().lower()

    if posture in ("critical", "guarded"):
        issues.append(f"posture:{posture}")
    if mode in ("halted", "manual_stop"):
        issues.append(f"control_mode:{mode}")
    if open_alert_count > 0:
        issues.append(f"open_alerts:{open_alert_count}")
    if max_drawdown_pct is not None and max_drawdown_pct > 15.0:
        issues.append(f"high_drawdown:{max_drawdown_pct:.1f}%")
    if days_since_last_trade is not None and days_since_last_trade > 10:
        issues.append(f"stale_strategy:{days_since_last_trade}d_no_trade")

    if len(issues) >= 3 or mode in ("halted", "manual_stop"):
        health = "critical"
    elif len(issues) >= 1:
        health = "warning"
    else:
        health = "healthy"

    action = (
        "halt_and_review" if health == "critical"
        else "investigate" if health == "warning"
        else "normal_operation"
    )

    return {
        "strategy_id": strategy_id,
        "health_status": health,
        "posture_level": posture,
        "control_mode": mode,
        "open_alert_count": open_alert_count,
        "recovery_eligible": recovery_eligible,
        "max_drawdown_pct": max_drawdown_pct,
        "days_since_last_trade": days_since_last_trade,
        "issues": issues,
        "action_recommended": action,
    }


# ── 5. Online/Offline Consistency ─────────────────────────────────────────────

def check_online_offline_consistency(
    backtest_assumptions: dict[str, Any] | None = None,
    execution_assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare backtest vs execution cost/fill assumptions.

    If no assumptions are provided, uses defaults from cost_model.

    Returns
    -------
    dict with consistency_status, gaps, warnings.
    """
    try:
        from .cost_model import resolve_cost_assumptions
        bt = resolve_cost_assumptions(dict(backtest_assumptions or {}), default_mode="backtest")
        ex = resolve_cost_assumptions(dict(execution_assumptions or {}), default_mode="execution")
    except Exception:
        bt = dict(backtest_assumptions or {
            "slippage_bps": 0.0,
            "market_impact_bps": 0.0,
            "commission_rate": 0.0003,
        })
        ex = dict(execution_assumptions or {
            "slippage_bps": 5.0,
            "market_impact_bps": 3.0,
            "commission_rate": 0.0003,
        })

    gaps: list[dict[str, Any]] = []
    warnings: list[str] = []

    for key in ("slippage_bps", "market_impact_bps", "commission_rate"):
        bt_val = _safe_float(bt.get(key), 0.0)
        ex_val = _safe_float(ex.get(key), 0.0)
        if bt_val is not None and ex_val is not None:
            delta = abs(float(ex_val) - float(bt_val))
            if delta > 0.001:
                gaps.append({
                    "parameter": key,
                    "backtest": bt_val,
                    "execution": ex_val,
                    "delta": round(delta, 4),
                })
                if key == "slippage_bps" and bt_val == 0.0:
                    warnings.append("回测使用零滑点假设，与执行模式差距显著")
                if key == "market_impact_bps" and bt_val == 0.0:
                    warnings.append("回测使用零市场冲击假设，AI 应注意此差距")

    status = (
        "inconsistent" if len(gaps) >= 2
        else "gap_detected" if len(gaps) == 1
        else "consistent"
    )

    return {
        "consistency_status": status,
        "backtest_assumptions": bt,
        "execution_assumptions": ex,
        "gaps": gaps,
        "gap_count": len(gaps),
        "warnings": warnings,
    }


# ── GovernanceReport ──────────────────────────────────────────────────────────

@dataclass
class GovernanceReport:
    """Unified governance check result."""

    checked_at: str = ""
    target_type: str = "system"
    target_id: str | None = None
    factor_decay: dict[str, Any] | None = None
    crowding: dict[str, Any] | None = None
    model_drift: dict[str, Any] | None = None
    strategy_health: dict[str, Any] | None = None
    online_offline_consistency: dict[str, Any] | None = None
    overall_status: str = "unknown"
    issues: list[str] = field(default_factory=list)
    action_recommended: str = "review"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "checked_at": self.checked_at,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "overall_status": self.overall_status,
            "issues": self.issues,
            "action_recommended": self.action_recommended,
        }
        if self.factor_decay is not None:
            d["factor_decay"] = self.factor_decay
        if self.crowding is not None:
            d["crowding"] = self.crowding
        if self.model_drift is not None:
            d["model_drift"] = self.model_drift
        if self.strategy_health is not None:
            d["strategy_health"] = self.strategy_health
        if self.online_offline_consistency is not None:
            d["online_offline_consistency"] = self.online_offline_consistency
        return d


# ── GovernanceMonitor ─────────────────────────────────────────────────────────

class GovernanceMonitor:
    """Orchestrates all 5 governance checks.

    Usage::

        monitor = GovernanceMonitor()
        report = monitor.run_full_check(
            target_type="factor",
            target_id="momentum_20d",
            ic_history=[0.05, 0.04, 0.03, 0.02, 0.015],
        )
    """

    def run_full_check(
        self,
        *,
        target_type: str = "system",
        target_id: str | None = None,
        # Factor decay inputs
        ic_history: list[float] | None = None,
        factor_expression: str = "",
        factor_category: str | None = None,
        existing_factor_pool: list[str] | None = None,
        # Model drift inputs
        current_metrics: dict[str, Any] | None = None,
        baseline_metrics: dict[str, Any] | None = None,
        # Strategy health inputs
        posture_level: str = "safe",
        control_mode: str = "active",
        open_alert_count: int = 0,
        recovery_eligible: bool = False,
        max_drawdown_pct: float | None = None,
        days_since_last_trade: int | None = None,
        # Consistency inputs
        backtest_assumptions: dict[str, Any] | None = None,
        execution_assumptions: dict[str, Any] | None = None,
        # Feature flags
        include_factor_decay: bool = True,
        include_crowding: bool = True,
        include_model_drift: bool = True,
        include_strategy_health: bool = True,
        include_consistency: bool = True,
    ) -> GovernanceReport:
        """Run selected governance checks and return a unified report."""
        resolved_id = str(target_id or "system").strip()
        all_issues: list[str] = []

        # 1. Factor decay
        decay_result: dict[str, Any] | None = None
        if include_factor_decay:
            decay_result = check_factor_decay(
                resolved_id if target_type == "factor" else "system",
                ic_history,
            )
            if decay_result.get("decay_status") in ("decaying", "decayed"):
                all_issues.append(f"factor_decay:{decay_result['decay_status']}")

        # 2. Crowding
        crowding_result: dict[str, Any] | None = None
        if include_crowding:
            crowding_result = check_crowding(
                resolved_id if target_type == "factor" else "system",
                expression=factor_expression,
                category=factor_category,
                existing_pool=existing_factor_pool,
            )
            if crowding_result.get("crowding_band") == "high":
                all_issues.append(f"crowding:{crowding_result['crowding_band']}")

        # 3. Model drift
        drift_result: dict[str, Any] | None = None
        if include_model_drift:
            drift_result = check_model_drift(
                resolved_id if target_type == "model" else "system",
                current_metrics=current_metrics,
                baseline_metrics=baseline_metrics,
            )
            if drift_result.get("drift_status") in ("degraded", "warning"):
                all_issues.append(f"model_drift:{drift_result['drift_status']}")

        # 4. Strategy health
        health_result: dict[str, Any] | None = None
        if include_strategy_health:
            health_result = check_strategy_health(
                resolved_id if target_type == "strategy" else "system",
                posture_level=posture_level,
                control_mode=control_mode,
                open_alert_count=open_alert_count,
                recovery_eligible=recovery_eligible,
                max_drawdown_pct=max_drawdown_pct,
                days_since_last_trade=days_since_last_trade,
            )
            if health_result.get("health_status") in ("critical", "warning"):
                all_issues.append(f"strategy_health:{health_result['health_status']}")

        # 5. Online/offline consistency
        consistency_result: dict[str, Any] | None = None
        if include_consistency:
            consistency_result = check_online_offline_consistency(
                backtest_assumptions=backtest_assumptions,
                execution_assumptions=execution_assumptions,
            )
            if consistency_result.get("consistency_status") == "inconsistent":
                all_issues.append("online_offline:inconsistent")

        # Overall status
        if len(all_issues) >= 3:
            overall = "critical"
            action = "immediate_review_required"
        elif len(all_issues) >= 1:
            overall = "warning"
            action = "investigate_flagged_dimensions"
        else:
            overall = "healthy"
            action = "continue_monitoring"

        return GovernanceReport(
            checked_at=_now_iso(),
            target_type=target_type,
            target_id=target_id,
            factor_decay=decay_result,
            crowding=crowding_result,
            model_drift=drift_result,
            strategy_health=health_result,
            online_offline_consistency=consistency_result,
            overall_status=overall,
            issues=all_issues,
            action_recommended=action,
        )


# Module-level default monitor
default_governance_monitor = GovernanceMonitor()
"""Module-level singleton for convenience imports."""
