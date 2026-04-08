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

READINESS_CONTRACT_VERSION = "strategy_factory.readiness.v1"
READINESS_AUTHORITY_CONTRACT_VERSION = "strategy_factory.readiness.authority.v1"


def _dedupe_reason_codes(values: list[str] | None = None) -> list[str]:
    codes: list[str] = []
    for value in list(values or []):
        code = str(value or "").strip()
        if code and code not in codes:
            codes.append(code)
    return codes


def build_readiness_authority(
    *,
    can_proceed: bool,
    hard_gate_enabled: bool,
    blocking_reason_codes: list[str] | None = None,
    critical_blocking_reason_codes: list[str] | None = None,
    warning_reason_codes: list[str] | None = None,
    skip_reason: str | None = None,
    blocking_stage: str = "readiness",
) -> dict[str, Any]:
    blocked = not bool(can_proceed)
    blocking_codes = _dedupe_reason_codes(blocking_reason_codes)
    critical_codes = _dedupe_reason_codes(critical_blocking_reason_codes)
    warning_codes = _dedupe_reason_codes(warning_reason_codes)
    return {
        "authority_contract_version": READINESS_AUTHORITY_CONTRACT_VERSION,
        "decision": "proceed" if not blocked else "blocked",
        "blocked": blocked,
        "hard_gate": bool(hard_gate_enabled),
        "gate_mode": "hard" if hard_gate_enabled else "soft",
        "blocking_stage": blocking_stage if blocked else None,
        "blocking_reason_codes": blocking_codes if blocked else [],
        "critical_blocking_reason_codes": critical_codes if blocked else [],
        "warning_reason_codes": warning_codes,
        "skip_reason": (str(skip_reason or "").strip() or None) if blocked else None,
    }


def resolve_governed_pool_state(factor_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = dict(factor_summary or {})
    factor_source_mode = str(summary.get("factor_source_mode") or "").strip().lower()
    active_candidate_count = int(summary.get("active_candidate_count") or 0)
    governed_source_candidate_count = int(summary.get("governed_source_candidate_count") or 0)
    governed_candidate_pool_mode = (
        str(
            summary.get("governed_candidate_pool_mode")
            or summary.get("active_pool_mode")
            or ""
        ).strip().lower()
        or None
    )
    governed_candidate_pool_provisional = bool(
        summary.get("governed_candidate_pool_provisional")
    ) or governed_candidate_pool_mode == "provisional_validated_watch"
    governed_candidate_pool_active = bool(
        active_candidate_count > 0
        and (
            factor_source_mode == "governed_candidate_pool"
            or governed_source_candidate_count > 0
            or governed_candidate_pool_mode in {"strict_governed", "provisional_validated_watch"}
        )
    )
    return {
        "mode": governed_candidate_pool_mode,
        "active": governed_candidate_pool_active,
        "provisional": governed_candidate_pool_provisional,
    }


def _has_legacy_factor_signal_summary(factor_summary: dict[str, Any] | None = None) -> bool:
    summary = dict(factor_summary or {})
    factor_source_mode = str(summary.get("factor_source_mode") or "").strip().lower()
    if factor_source_mode:
        return False
    if int(summary.get("active_factor_count") or 0) > 0:
        return True
    if list(summary.get("top_factor_names") or []):
        return True
    if list(summary.get("preferred_strategy_types") or []):
        return True
    return False


def resolve_factor_refresh_trigger(
    factor_research: dict[str, Any] | None = None,
    *,
    factor_summary: dict[str, Any] | None = None,
) -> str | None:
    """Return the preferred scheduler refresh trigger for a factor artifact."""

    artifact = dict(factor_research or {})
    summary = dict(factor_summary or artifact.get("summary") or {})
    if bool(artifact.get("lightweight_mock_fallback")) or bool(summary.get("lightweight_mock_fallback")):
        return None
    factor_source_mode = str(summary.get("factor_source_mode") or "").strip().lower()
    active_candidate_count = int(summary.get("active_candidate_count") or 0)
    governed_source_candidate_count = int(summary.get("governed_source_candidate_count") or 0)
    scheduler_recent_success = bool(summary.get("scheduler_recent_success"))
    scheduler_last_run = summary.get("scheduler_last_run")
    governed_pool_state = resolve_governed_pool_state(summary)
    governed_candidate_pool_active = bool(governed_pool_state.get("active"))

    if bool(summary.get("stale")):
        return "stale_artifact"
    if bool(summary.get("governed_pool_missing_after_scheduler_success")) or (
        scheduler_recent_success and not governed_candidate_pool_active
    ):
        return "governed_pool_missing_after_scheduler_success"
    if governed_candidate_pool_active:
        return None
    if _has_legacy_factor_signal_summary(summary):
        return None
    if factor_source_mode == "seed_fallback":
        return (
            "seed_fallback_without_governed_pool"
            if scheduler_last_run
            else "scheduler_warmup_missing_governed_pool"
        )
    if not scheduler_last_run and active_candidate_count <= 0 and governed_source_candidate_count <= 0:
        return "scheduler_warmup_missing_governed_pool"
    return None


def resolve_governed_pool_runtime_state(
    factor_summary: dict[str, Any] | None = None,
    *,
    factor_refresh: dict[str, Any] | None = None,
    factor_refresh_recommendation_reason: str | None = None,
) -> str:
    summary = dict(factor_summary or {})
    refresh = dict(factor_refresh or {})
    governed_pool_state = resolve_governed_pool_state(summary)
    governed_candidate_pool_active = bool(governed_pool_state.get("active"))
    scheduler_recent_success = bool(summary.get("scheduler_recent_success"))
    factor_source_mode = str(summary.get("factor_source_mode") or "").strip().lower()
    refresh_attempted = bool(refresh.get("refresh_attempted"))
    refresh_status = str(refresh.get("refresh_status") or "").strip().lower()
    auto_refresh_enabled = bool(refresh.get("auto_refresh_enabled"))
    governed_pool_missing_after_scheduler_success = bool(
        factor_source_mode == "governed_pool_missing_after_scheduler_success"
        or bool(summary.get("governed_pool_missing_after_scheduler_success"))
        or (scheduler_recent_success and not governed_candidate_pool_active)
    )
    if governed_candidate_pool_active:
        return "governed_pool_active"
    if governed_pool_missing_after_scheduler_success:
        return "blocked_by_governed_pool"
    if refresh_attempted and refresh_status in {"failed", "timeout"}:
        return "blocked_by_governed_pool"
    if auto_refresh_enabled and (refresh_attempted or factor_refresh_recommendation_reason):
        return "refreshing_pool"
    return "blocked_by_governed_pool"


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
        factor_refresh_recommendation_reason = resolve_factor_refresh_trigger(
            factor_artifact,
            factor_summary=factor_summary,
        )
        factor_source_mode = str(factor_summary.get("factor_source_mode") or "").strip().lower()
        active_candidate_count = int(factor_summary.get("active_candidate_count") or 0)
        governed_source_candidate_count = int(
            factor_summary.get("governed_source_candidate_count") or 0
        )
        governed_pool_state = resolve_governed_pool_state(factor_summary)
        governed_candidate_pool_mode = governed_pool_state.get("mode")
        governed_candidate_pool_provisional = bool(governed_pool_state.get("provisional"))
        governed_blocked_candidate_count = int(
            factor_summary.get("governed_blocked_candidate_count") or 0
        )
        governed_blocked_ratio = self._safe_float(
            factor_summary.get("governed_blocked_ratio"),
            default=0.0,
        )
        governed_freshness_days = factor_summary.get("governed_freshness_days")
        scheduler_recent_success = bool(factor_summary.get("scheduler_recent_success"))
        scheduler_llm_validation_status = factor_summary.get("scheduler_llm_validation_status")
        governed_exclusion_reason_counts = dict(
            factor_summary.get("governed_exclusion_reason_counts") or {}
        )
        governed_risk_counts = dict(factor_summary.get("governed_risk_counts") or {})
        governed_candidate_pool_active = bool(governed_pool_state.get("active"))
        governed_pool_missing_after_scheduler_success = bool(
            factor_source_mode == "governed_pool_missing_after_scheduler_success"
            or bool(factor_summary.get("governed_pool_missing_after_scheduler_success"))
            or (scheduler_recent_success and not governed_candidate_pool_active)
        )
        governed_pool_runtime_state = resolve_governed_pool_runtime_state(
            factor_summary,
            factor_refresh=factor_refresh,
            factor_refresh_recommendation_reason=factor_refresh_recommendation_reason,
        )

        sources = dict(snapshot.get("sources") or {})
        event_source = dict(sources.get("event_driven") or {})
        event_state = dict(snapshot.get("event_driven") or {})
        completion = dict(snapshot.get("completeness") or {})
        completion_ratio = self._safe_float(completion.get("completion_ratio"), default=1.0)

        warnings: list[str] = []
        blockers: list[str] = []
        critical_blockers: list[str] = []
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
        if governed_candidate_pool_provisional:
            warnings.append("governed_candidate_pool_provisional")
            score -= 0.04
        if not governed_candidate_pool_active:
            warnings.append("governed_candidate_pool_inactive")
            blockers.append("governed_candidate_pool_required")
            critical_blockers.append("governed_candidate_pool_required")
            score -= 0.22
        if governed_blocked_candidate_count > 0:
            warnings.append("governed_candidate_pool_blocked_candidates")
        if governed_blocked_ratio >= 0.75:
            warnings.append("governed_candidate_pool_blocked_ratio_high")
            score -= 0.12
        elif governed_blocked_ratio >= 0.40:
            warnings.append("governed_candidate_pool_blocked_ratio_elevated")
            score -= 0.06
        if governed_pool_missing_after_scheduler_success:
            warnings.append("factor_scheduler_recent_success_without_governed_pool")
            blockers.append("governed_candidate_pool_missing_after_scheduler_success")
            critical_blockers.append("governed_candidate_pool_missing_after_scheduler_success")
            score -= 0.18
        if governed_pool_runtime_state == "refreshing_pool":
            warnings.append("governed_candidate_pool_refreshing")
            score -= 0.05
        elif governed_pool_runtime_state == "blocked_by_governed_pool" and not governed_pool_missing_after_scheduler_success:
            warnings.append("governed_candidate_pool_refresh_blocked")
            blockers.append("governed_candidate_pool_unavailable_after_refresh")
            critical_blockers.append("governed_candidate_pool_unavailable_after_refresh")
            score -= 0.18
        if bool(factor_summary.get("stale")):
            if governed_candidate_pool_active:
                warnings.append("factor_research_history_stale_governed_pool_active")
                score -= 0.06
            else:
                blockers.append("factor_research_stale")
                score -= 0.32
        if governed_candidate_pool_active:
            if governed_freshness_days is None:
                warnings.append("governed_candidate_pool_freshness_unknown")
                score -= 0.05
            elif self._safe_float(governed_freshness_days, default=0.0) > 2:
                warnings.append("governed_candidate_pool_stale")
                score -= 0.08
        refresh_status = str(factor_refresh.get("refresh_status") or "").strip().lower()
        if bool(factor_refresh.get("refresh_attempted")) and refresh_status not in {
            "success",
            "not_needed",
        }:
            warnings.append(f"factor_refresh_{refresh_status or 'unknown'}")
            score -= 0.08

        score = max(min(round(score, 4), 1.0), 0.0)
        hard_block = is_factory_readiness_hard_block_enabled()
        can_proceed = not critical_blockers and (
            not hard_block or (score >= FACTORY_READINESS_MIN_SCORE and not blockers)
        )
        authority = build_readiness_authority(
            can_proceed=can_proceed,
            hard_gate_enabled=hard_block,
            blocking_reason_codes=blockers,
            critical_blocking_reason_codes=critical_blockers,
            warning_reason_codes=warnings,
            skip_reason="readiness_blocked",
        )

        return {
            "readiness_contract_version": READINESS_CONTRACT_VERSION,
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
            "critical_blockers": critical_blockers,
            "critical_blocker_count": len(critical_blockers),
            "snapshot_completion_ratio": completion_ratio,
            "snapshot_degraded": bool(snapshot.get("degraded")),
            "event_status": event_status,
            "event_task_ready_count": int(event_state.get("tasks_ready_count") or 0),
            "factor_research_stale": bool(factor_summary.get("stale")),
            "factor_research_degraded": bool(factor_summary.get("degraded")),
            "factor_source_mode": factor_summary.get("factor_source_mode"),
            "governed_candidate_pool_active": governed_candidate_pool_active,
            "governed_candidate_pool_runtime_state": governed_pool_runtime_state,
            "governed_candidate_pool_mode": governed_candidate_pool_mode,
            "governed_candidate_pool_provisional": governed_candidate_pool_provisional,
            "governed_pool_missing_after_scheduler_success": governed_pool_missing_after_scheduler_success,
            "active_candidate_count": active_candidate_count,
            "governed_source_candidate_count": governed_source_candidate_count,
            "governed_blocked_candidate_count": governed_blocked_candidate_count,
            "governed_blocked_ratio": governed_blocked_ratio,
            "governed_freshness_days": governed_freshness_days,
            "governed_exclusion_reason_counts": governed_exclusion_reason_counts,
            "governed_risk_counts": governed_risk_counts,
            "active_family_count": len(list(factor_summary.get("active_family_names") or [])),
            "active_regime_count": len(list(factor_summary.get("active_regime_names") or [])),
            "scheduler_recent_success": scheduler_recent_success,
            "scheduler_llm_validation_status": scheduler_llm_validation_status,
            "factor_refresh_attempted": bool(factor_refresh.get("refresh_attempted")),
            "factor_refresh_status": factor_refresh.get("refresh_status"),
            "factor_refresh_recommended": factor_refresh_recommendation_reason is not None,
            "factor_refresh_recommendation_reason": factor_refresh_recommendation_reason,
            "authority": authority,
            "authority_contract_version": authority.get("authority_contract_version"),
            "decision": authority.get("decision"),
            "blocked": authority.get("blocked"),
            "hard_gate": authority.get("hard_gate"),
            "gate_mode": authority.get("gate_mode"),
            "blocking_stage": authority.get("blocking_stage"),
            "blocking_reason_codes": list(authority.get("blocking_reason_codes") or []),
            "critical_blocking_reason_codes": list(
                authority.get("critical_blocking_reason_codes") or []
            ),
            "warning_reason_codes": list(authority.get("warning_reason_codes") or []),
            "skip_reason": authority.get("skip_reason"),
        }

    @staticmethod
    def _safe_float(value: Any, *, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

__all__ = [
    "ReadinessService",
    "READINESS_AUTHORITY_CONTRACT_VERSION",
    "READINESS_CONTRACT_VERSION",
    "build_readiness_authority",
    "resolve_factor_refresh_trigger",
    "resolve_governed_pool_runtime_state",
    "resolve_governed_pool_state",
]
