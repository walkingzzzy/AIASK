"""Incubation-stage planning helpers."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any, Optional

from .common import _safe_float, _safe_int, _string
from .confidence import evaluate_execution_audit_gate

# ── 样本量分层晋级常量（可通过环境变量覆盖）─────────────────────────────
_MIN_PRIMARY_EFFECTIVE_N: int = max(
    10, int(os.getenv("INCUBATION_MIN_PRIMARY_EFFECTIVE_N", "30") or "30")
)
_MIN_COVERAGE_RATIO: float = max(
    0.10, min(1.0, float(os.getenv("INCUBATION_MIN_COVERAGE_RATIO", "0.35") or "0.35"))
)
_GRADUATION_PRIMARY_EFFECTIVE_N: int = max(
    20, int(os.getenv("INCUBATION_GRADUATION_PRIMARY_EFFECTIVE_N", "70") or "70")
)
_GRADUATION_SECONDARY_EFFECTIVE_N: int = max(
    10, int(os.getenv("INCUBATION_GRADUATION_SECONDARY_EFFECTIVE_N", "35") or "35")
)
_GRADUATION_COVERAGE_RATIO: float = max(
    0.25, min(1.0, float(os.getenv("INCUBATION_GRADUATION_COVERAGE_RATIO", "0.80") or "0.80"))
)
# ── Skill trend 衰减阈值 ───────────────────────────────────────────────
_SKILL_TREND_CRITICAL: float = -0.010   # 每期衰减超过 1% → 降级
_SKILL_TREND_WARNING: float = -0.005    # 每期衰减超过 0.5% → 预警
# ─────────────────────────────────────────────────────────────────────────

def resolve_incubation_pipeline_stage(
    signal_quality: Optional[dict],
    *,
    open_risk_count: int = 0,
    audit_summary: Optional[dict[str, Any]] = None,
    execution_audit_gate_status: Optional[str] = None,
) -> str:
    quality = dict(signal_quality or {})
    primary_effective_n = _safe_int(quality.get("primary_effective_n"))
    secondary_effective_n = _safe_int(quality.get("secondary_effective_n"))
    primary_skill_lcb = _safe_float(
        quality.get("primary_skill_lcb") if quality.get("primary_skill_lcb") is not None else quality.get("primary_signal_skill_lcb")
    )
    secondary_skill_lcb = _safe_float(
        quality.get("secondary_skill_lcb") if quality.get("secondary_skill_lcb") is not None else quality.get("secondary_signal_skill_lcb")
    )
    recent_primary_skill_lcb = _safe_float(quality.get("recent_primary_skill_lcb"))
    coverage_ratio = _safe_float(quality.get("coverage_ratio")) or 0.0
    stability_gap = _safe_float(quality.get("stability_gap"))

    if primary_effective_n < _MIN_PRIMARY_EFFECTIVE_N or coverage_ratio < _MIN_COVERAGE_RATIO:
        signal_stage_without_execution_gate = "warmup"
    elif (recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03) or (
        stability_gap is not None and stability_gap > 0.10
    ) or open_risk_count >= 3:
        signal_stage_without_execution_gate = "failed"
    elif (
        primary_effective_n >= _GRADUATION_PRIMARY_EFFECTIVE_N
        and secondary_effective_n >= _GRADUATION_SECONDARY_EFFECTIVE_N
        and (primary_skill_lcb or 0.0) > 0.0
        and (secondary_skill_lcb or 0.0) > 0.0
        and (recent_primary_skill_lcb or 0.0) > 0.0
        and coverage_ratio >= _GRADUATION_COVERAGE_RATIO
        and (stability_gap is None or stability_gap <= 0.05)
        and open_risk_count == 0
    ):
        signal_stage_without_execution_gate = "graduation_ready"
    elif (
        primary_skill_lcb is None
        or primary_skill_lcb <= 0.0
        or coverage_ratio < 0.5
        or (stability_gap is not None and stability_gap > 0.08)
        or open_risk_count > 1
    ):
        signal_stage_without_execution_gate = "observe"
    else:
        signal_stage_without_execution_gate = "candidate"

    if signal_stage_without_execution_gate == "warmup":
        return "warmup"

    # ── Skill trend 衰减降级 (Gap 2) ────────────────────────────────
    skill_trend_5d = _safe_float(quality.get("skill_trend_5d"))
    if (
        skill_trend_5d is not None
        and skill_trend_5d < _SKILL_TREND_CRITICAL
        and signal_stage_without_execution_gate in {"candidate", "graduation_ready"}
    ):
        signal_stage_without_execution_gate = "observe"
    # ─────────────────────────────────────────────────────────────────

    gate_status = execution_audit_gate_status
    if not gate_status:
        gate_status, _reasons, _passes, _metrics = evaluate_execution_audit_gate(audit_summary)
    if gate_status == "failed_metrics":
        return "failed"
    if signal_stage_without_execution_gate == "failed":
        return "failed"
    if signal_stage_without_execution_gate == "graduation_ready" and gate_status == "passed":
        return "graduation_ready"
    if signal_stage_without_execution_gate == "candidate" and gate_status == "passed":
        return "candidate"
    return "observe"


def _parse_time(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.fromisoformat(f"{text}T00:00:00+00:00")
            except ValueError:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_date(value: Any) -> Optional[date]:
    dt = _parse_time(value)
    return dt.date() if dt is not None else None


def _estimate_stage_clock_days(
    strategy: Optional[dict[str, Any]],
    quality_report: Optional[dict[str, Any]],
    incubation_metrics: list[dict[str, Any]],
) -> int:
    strategy_payload = dict(strategy or {})
    report_payload = dict(quality_report or {})
    metric_times = [
        _parse_time(dict(item or {}).get("metric_date"))
        for item in list(incubation_metrics or [])
    ]
    metric_times = [item for item in metric_times if item is not None]
    if metric_times:
        return max(0, (max(metric_times).date() - min(metric_times).date()).days)
    start = (
        _parse_time(report_payload.get("created_at"))
        or _parse_time(report_payload.get("updated_at"))
        or _parse_time(strategy_payload.get("created_at"))
        or _parse_time(strategy_payload.get("updated_at"))
    )
    if start is None:
        return 0
    return max(0, (datetime.now(timezone.utc).date() - start.date()).days)


def _metric_signal_value(item: dict[str, Any], key: str) -> Optional[float]:
    payload = dict(item or {})
    value = payload.get(key)
    if value is None:
        value = dict(payload.get("signal_quality") or {}).get(key)
    return _safe_float(value)


def _recent_negative_skill_streak(incubation_metrics: list[dict[str, Any]]) -> int:
    streak = 0
    for metric in list(incubation_metrics or []):
        recent_skill_lcb = _metric_signal_value(metric, "recent_primary_skill_lcb")
        if recent_skill_lcb is None or recent_skill_lcb >= 0:
            break
        streak += 1
    return streak


async def resolve_incubation_action_plan(
    db,
    strategy: dict[str, Any],
    *,
    pipeline_stage: str,
    signal_quality: Optional[dict[str, Any]] = None,
    execution_quality: Optional[dict[str, Any]] = None,
    total_signals: int = 0,
    validation_grade: Optional[str] = None,
    quality_report: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    signal_payload = dict(signal_quality or {})
    execution_payload = dict(execution_quality or {})
    strategy_id = str(dict(strategy or {}).get("id") or "").strip()
    incubation_metrics: list[dict[str, Any]] = []
    list_metrics = getattr(db, "list_strategy_incubation_metrics", None)
    if callable(list_metrics) and strategy_id:
        try:
            incubation_metrics = list(await list_metrics(strategy_id, limit=10) or [])
        except Exception:
            incubation_metrics = []

    stage_clock_days = _estimate_stage_clock_days(strategy, quality_report, incubation_metrics)
    signal_vacuum_days = stage_clock_days if pipeline_stage == "warmup" and int(total_signals or 0) <= 0 else 0
    recent_primary_skill_lcb = _safe_float(signal_payload.get("recent_primary_skill_lcb"))
    stability_gap = _safe_float(signal_payload.get("stability_gap"))
    prediction_quality_label = _string(execution_payload.get("prediction_quality_label")) or "insufficient_evidence"
    execution_quality_label = _string(execution_payload.get("execution_quality_label")) or "insufficient_evidence"
    negative_skill_streak = _recent_negative_skill_streak(incubation_metrics)

    remediation_action = "continue_observe"
    remediation_reason = "stage_progression_normal"
    budget_action = "keep_bootstrap"
    runtime_control_mode = "observe_only"
    revision_required = False
    cleanup_recommended = False

    normalized_grade = _string(validation_grade).upper() or None
    if normalized_grade == "D":
        remediation_action = "cleanup_low_confidence_candidate"
        remediation_reason = "validation_grade_d_not_allowed_for_runtime"
        budget_action = "stop_runtime"
        runtime_control_mode = "research_only"
        cleanup_recommended = True
    elif (
        recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03
    ) or (
        stability_gap is not None and stability_gap > 0.10
    ) or pipeline_stage == "failed":
        remediation_action = "freeze_and_revise"
        remediation_reason = (
            "prediction_skill_negative"
            if recent_primary_skill_lcb is not None and recent_primary_skill_lcb < -0.03
            else "stability_break"
            if stability_gap is not None and stability_gap > 0.10
            else "pipeline_failed"
        )
        budget_action = "freeze_new_budget"
        runtime_control_mode = "exit_only"
        revision_required = True
    elif pipeline_stage == "warmup" and int(total_signals or 0) <= 0:
        remediation_reason = "signal_vacuum"
        if signal_vacuum_days >= 30:
            remediation_action = "return_to_research"
            budget_action = "stop_runtime"
            runtime_control_mode = "exit_only"
            revision_required = True
        elif signal_vacuum_days >= 20:
            remediation_action = "freeze_and_revise"
            budget_action = "freeze_new_budget"
            runtime_control_mode = "exit_only"
            revision_required = True
        elif signal_vacuum_days >= 5:
            remediation_action = "signal_vacuum_warning"
        else:
            remediation_action = "continue_observe"
    elif negative_skill_streak >= 5:
        remediation_action = "freeze_and_revise_signal_logic"
        remediation_reason = "prediction_skill_negative"
        budget_action = "freeze_new_budget"
        runtime_control_mode = "freeze_new_entries"
        revision_required = True
    elif prediction_quality_label in {"strong", "mixed"} and execution_quality_label == "weak":
        remediation_action = "execution_template_adjustment"
        remediation_reason = "execution_conversion_failure"
        budget_action = "budget_cut_50"
        runtime_control_mode = "marketable_limit_keep_observe"
        revision_required = True
    elif prediction_quality_label == "weak" and execution_quality_label != "weak":
        remediation_action = "freeze_and_revise_signal_logic"
        remediation_reason = "prediction_skill_negative"
        budget_action = "freeze_new_budget"
        runtime_control_mode = "freeze_new_entries"
        revision_required = True
    elif pipeline_stage == "candidate":
        remediation_action = "candidate_keep_observe"
        remediation_reason = "candidate_waiting_for_more_signal_and_execution_evidence"
    elif pipeline_stage == "graduation_ready":
        remediation_action = "ready_for_promotion_review"
        remediation_reason = "signal_and_execution_quality_ready"
        budget_action = "promote_budget"
        runtime_control_mode = "monitor"

    return {
        "stage_clock_days": stage_clock_days,
        "signal_vacuum_days": signal_vacuum_days,
        "remediation_action": remediation_action,
        "remediation_reason": remediation_reason,
        "budget_action": budget_action,
        "runtime_control_mode": runtime_control_mode,
        "revision_required": revision_required,
        "cleanup_recommended": cleanup_recommended,
        "negative_skill_metric_streak": negative_skill_streak,
    }


async def list_quality_reports(db, strategy_id: str, limit: int = 10) -> list[dict]:
    if hasattr(db, "list_strategy_quality_reports"):
        return await db.list_strategy_quality_reports(strategy_id, limit=limit)
    latest = None
    if hasattr(db, "get_latest_strategy_quality_report"):
        latest = await db.get_latest_strategy_quality_report(strategy_id)
    elif hasattr(db, "get_strategy_quality_report"):
        latest = await db.get_strategy_quality_report(strategy_id)
    return [latest] if latest else []


async def get_latest_quality_report(db, strategy_id: str) -> Optional[dict]:
    rows = await list_quality_reports(db, strategy_id, limit=1)
    return rows[0] if rows else None

