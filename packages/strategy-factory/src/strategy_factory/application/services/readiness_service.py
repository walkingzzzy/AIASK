"""ReadinessService – evaluates factory readiness from snapshot + factor data.

Extracted from FactoryCycleRunner._build_factory_readiness (P4 refactor).
The service is stateless and can be called independently of the scheduler.
"""

from __future__ import annotations

from typing import Any

from ...domain.constants import (
    FACTORY_READINESS_MIN_COMPLETION_RATIO,
    FACTORY_READINESS_MIN_SCORE,
    is_factory_factor_auto_refresh_enabled,
    is_factory_readiness_hard_block_enabled,
    is_factory_runtime_enabled,
    resolve_event_runtime_mode,
)


class ReadinessService:
    """Stateless evaluator for factory readiness.

    Accepts a market snapshot and factor research artifact, returns a
    structured readiness dict that drives the run/skip decision.
    """

    def evaluate(
        self,
        snapshot: dict[str, Any],
        factor_research: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return readiness assessment dict.

        Args:
            snapshot: Market data snapshot from DataCollector.
            factor_research: Factor research artifact (may be None/empty).

        Returns:
            Dict with ``can_proceed``, ``readiness_score``, ``warnings``,
            ``blockers`` and various diagnostic fields.
        """
        factor_artifact = dict(factor_research or {})
        factor_summary = dict(factor_artifact.get("summary") or {})
        factor_refresh = dict(factor_artifact.get("freshness_repair") or {})
        factor_source_mode = str(factor_summary.get("factor_source_mode") or "").strip().lower()
        active_candidate_count = int(factor_summary.get("active_candidate_count") or 0)
        governed_source_candidate_count = int(
            factor_summary.get("governed_source_candidate_count") or 0
        )
        governed_blocked_candidate_count = int(
            factor_summary.get("governed_blocked_candidate_count") or 0
        )
        governed_exclusion_reason_counts = dict(
            factor_summary.get("governed_exclusion_reason_counts") or {}
        )
        governed_risk_counts = dict(factor_summary.get("governed_risk_counts") or {})
        governed_candidate_pool_active = bool(
            factor_source_mode == "governed_candidate_pool" or active_candidate_count > 0
        )

        sources = dict(snapshot.get("sources") or {})
        event_source = dict(sources.get("event_driven") or {})
        event_state = dict(snapshot.get("event_driven") or {})
        completion = dict(snapshot.get("completeness") or {})
        completion_ratio = self._safe_float(completion.get("completion_ratio"), default=1.0)

        warnings: list[str] = []
        blockers: list[str] = []
        score = 1.0

        if bool(snapshot.get("degraded")):
            warnings.append("snapshot_degraded")
            score -= 0.12
        if completion_ratio < FACTORY_READINESS_MIN_COMPLETION_RATIO:
            blockers.append("snapshot_completion_too_low")
            score -= 0.28
        elif completion_ratio < 0.9:
            warnings.append("snapshot_completion_low")
            score -= 0.08

        event_status = str(event_source.get("status") or "unknown").strip().lower() or "unknown"
        if event_status != "success":
            warnings.append(f"event_driven_{event_status}")
            score -= 0.08 if event_status == "partial" else 0.14
        if event_status == "success" and int(event_state.get("tasks_ready_count") or 0) <= 0:
            warnings.append("event_driven_no_ready_tasks")
            score -= 0.03

        if bool(factor_summary.get("degraded")):
            warnings.append("factor_research_degraded")
            score -= 0.14
        if governed_blocked_candidate_count > 0:
            warnings.append("governed_candidate_pool_blocked_candidates")
        if bool(factor_summary.get("stale")):
            if governed_candidate_pool_active:
                warnings.append("factor_research_history_stale_governed_pool_active")
                score -= 0.06
            else:
                blockers.append("factor_research_stale")
                score -= 0.32
        refresh_status = str(factor_refresh.get("refresh_status") or "").strip().lower()
        if bool(factor_refresh.get("refresh_attempted")) and refresh_status not in {
            "success",
            "not_needed",
        }:
            warnings.append(f"factor_refresh_{refresh_status or 'unknown'}")
            score -= 0.08

        score = max(min(round(score, 4), 1.0), 0.0)
        hard_block = is_factory_readiness_hard_block_enabled()
        can_proceed = not hard_block or (score >= FACTORY_READINESS_MIN_SCORE and not blockers)

        return {
            "runtime_enabled": is_factory_runtime_enabled(),
            "event_runtime_mode": resolve_event_runtime_mode(),
            "auto_refresh_enabled": bool(
                is_factory_factor_auto_refresh_enabled()
                and bool(factor_refresh.get("auto_refresh_enabled"))
            ),
            "hard_block_enabled": hard_block,
            "min_score": FACTORY_READINESS_MIN_SCORE,
            "min_completion_ratio": FACTORY_READINESS_MIN_COMPLETION_RATIO,
            "readiness_score": score,
            "can_proceed": can_proceed,
            "warnings": warnings,
            "warning_count": len(warnings),
            "blockers": blockers,
            "blocker_count": len(blockers),
            "snapshot_completion_ratio": completion_ratio,
            "snapshot_degraded": bool(snapshot.get("degraded")),
            "event_status": event_status,
            "event_task_ready_count": int(event_state.get("tasks_ready_count") or 0),
            "factor_research_stale": bool(factor_summary.get("stale")),
            "factor_research_degraded": bool(factor_summary.get("degraded")),
            "factor_source_mode": factor_summary.get("factor_source_mode"),
            "governed_candidate_pool_active": governed_candidate_pool_active,
            "active_candidate_count": active_candidate_count,
            "governed_source_candidate_count": governed_source_candidate_count,
            "governed_blocked_candidate_count": governed_blocked_candidate_count,
            "governed_exclusion_reason_counts": governed_exclusion_reason_counts,
            "governed_risk_counts": governed_risk_counts,
            "active_family_count": len(list(factor_summary.get("active_family_names") or [])),
            "active_regime_count": len(list(factor_summary.get("active_regime_names") or [])),
            "factor_refresh_attempted": bool(factor_refresh.get("refresh_attempted")),
            "factor_refresh_status": factor_refresh.get("refresh_status"),
        }

    @staticmethod
    def _safe_float(value: Any, *, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


__all__ = ["ReadinessService"]
