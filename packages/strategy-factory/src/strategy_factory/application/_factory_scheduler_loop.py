"""策略工厂调度器实现。"""


from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import suppress
import inspect
import logging
import os
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..domain.constants import (
    AUTONOMY_MAX_RESEARCH_TASKS,
    AUTONOMY_MAX_BULK_RESEARCH_TASKS,
    AUTONOMY_RESERVED_BULK_RESEARCH_TASKS,
    AUTONOMY_CANDIDATES_PER_TASK,
    AUTONOMY_TASK_HARD_CAP,
    AUTONOMY_STARTUP_DELAY_SEC,
    FACTORY_DAILY_RUN_TIME,
    FACTORY_ERROR_BACKOFF_SEC,
    FACTORY_EVENT_RUNTIME_MODE,
    FACTORY_FACTOR_AUTO_REFRESH,
    FACTORY_FACTOR_REFRESH_TIMEOUT_SEC,
    FACTORY_MARKET_HOURS_INTERVAL_SEC,
    FACTORY_MAX_DAILY_RUNS,
    FACTORY_OFF_HOURS_INTERVAL_SEC,
    FACTORY_PRE_GATE_ENABLED,
    FACTORY_READINESS_HARD_BLOCK,
    FACTORY_READINESS_MIN_COMPLETION_RATIO,
    FACTORY_READINESS_MIN_SCORE,
    FACTORY_RUNTIME_ENABLED,
    FACTORY_SCHEDULE_MODE,
    FACTORY_STARTUP_WARMUP_ENABLED,
    FACTORY_STARTUP_WARMUP_FORCE,
    FACTORY_STARTUP_WARMUP_LIMIT,
    FACTORY_STARTUP_WARMUP_TASK_TYPE,
    RESEARCH_TASK_CONCURRENCY,
    STOCK_STRATEGY_MATRIX_BATCH_SIZE,
    STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY,
    STOCK_STRATEGY_MATRIX_ENABLED,
    STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK,
    STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK,
    STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN,
    STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN,
    STOCK_STRATEGY_MATRIX_RUN_WINDOW,
    STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD,
    STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT,
    is_factory_factor_auto_refresh_enabled,
    is_factory_readiness_hard_block_enabled,
    is_factory_runtime_enabled,
    resolve_event_runtime_mode,
)
from .cycle_runner import FactoryCycleRunner, FactoryRunContext
from .factory_execution import (
    FACTORY_ENGINE_VERSION,
    FactoryExecutionMode,
    build_artifact_refs,
    build_run_artifacts,
    build_shadow_parity_result,
    resolve_factory_engine_version,
    resolve_factory_execution_mode,
)
from .factory_market_views import build_portfolio_candidate_from_topn
from .runtime import (
    _call_optional_async as _runtime_call_optional_async,
    get_strategy_factory_package as _runtime_get_strategy_factory_package,
)
from .run_models import (
    FactoryRunStatus,
    StageStatus,
    build_stage_result,
    resolve_run_status,
    summarize_stage_results,
)
from ._budget_feedback import (
    CONTROL_MODE_SEVERITY,
    collect_generator_mode_feedback_controls,
    extract_feedback_root,
    normalize_text as _normalize_feedback_text,
    summarize_task_feedback_controls,
)
from ._autonomy_task_selection import (
    apply_scheduler_planning_controls as _apply_scheduler_planning_controls_payload,
    build_scan_only_task_budget_meta as _build_scan_only_task_budget_meta_payload,
    merge_autonomy_tasks_with_budget as _merge_autonomy_tasks_with_budget_payload,
)
from ._autonomy_task_executor import (
    AutonomyTaskExecutionContext as _AutonomyTaskExecutionContext,
    execute_autonomy_task as _execute_autonomy_task_payload,
)
from ._autonomy_stage_artifacts import (
    attach_autonomy_stage_artifacts as _attach_autonomy_stage_artifacts_payload,
)
from ._autonomy_stage_summary import (
    build_autonomy_stage_summary as _build_autonomy_stage_summary_payload,
)
from ._bulk_planner_summary import (
    build_bulk_planner_error_report as _build_bulk_planner_error_report_payload,
    build_default_bulk_report as _build_default_bulk_report_payload,
    normalize_bulk_report_summary as _normalize_bulk_report_summary_payload,
)
from ._combined_scan_report import build_combined_scan_report as _build_combined_scan_report_payload
from ._bulk_cursor import (
    extract_bulk_stock_cursor as _extract_bulk_stock_cursor_payload,
    resolve_bulk_stock_matrix_cursor as _resolve_bulk_stock_matrix_cursor_payload,
)
from .utils import _extract_event_context as _local_extract_event_context
from .research.matrix import StockStrategyMatrixPlanner
from .research_plane_contract import (
    build_candidate_artifact,
    build_research_evidence_artifact,
    build_task_artifact,
)
from ..domain.targets import (
    _extract_target_codes_from_payload,
    _normalize_research_task_contract,
    _normalize_target_codes,
)
from ..infrastructure.mcp_services import get_autonomy_lifecycle_runtime, get_runtime_warmup_runner

if TYPE_CHECKING:
    from ..api.contracts import (
        AutonomyGateway,
        FactorResearchGateway,
        IncubationGateway,
        RiskGateway,
        ValidationGateway,
        VectorSearchGateway,
    )
    from ..infrastructure.mcp_adapters import MCPRuntimeAdapters

logger = logging.getLogger(__name__)

_MARKET_TIMEZONE_NAME = str(os.getenv("STRATEGY_MARKET_TIMEZONE") or "Asia/Shanghai").strip() or "Asia/Shanghai"
try:
    _MARKET_TIMEZONE = ZoneInfo(_MARKET_TIMEZONE_NAME)
except Exception:
    _MARKET_TIMEZONE = timezone(timedelta(hours=8))

_FALLBACK_AUTONOMY_PHASE_ORDER = (
    "prepared",
    "generating",
    "reviewing",
    "recording",
    "submitting",
    "completed",
)


def _summarize_autonomy_lifecycle_fallback(lifecycle: Optional[dict[str, Any]]) -> dict[str, Any]:
    payload = dict(lifecycle or {})
    return {
        "state": payload.get("state"),
        "current_phase": payload.get("current_phase"),
        "failed_phase": payload.get("failed_phase"),
        "terminal_phase": payload.get("terminal_phase"),
        "phase_status_counts": dict(payload.get("phase_status_counts") or {}),
        "completed_phase_count": int(payload.get("completed_phase_count") or 0),
        "event_count": int(payload.get("event_count") or len(payload.get("events") or [])),
        "phase_order": list(payload.get("phase_order") or _FALLBACK_AUTONOMY_PHASE_ORDER),
    }


def _load_autonomy_lifecycle_runtime():
    try:
        return get_autonomy_lifecycle_runtime()
    except Exception:
        return SimpleNamespace(
            AUTONOMY_PHASE_ORDER=_FALLBACK_AUTONOMY_PHASE_ORDER,
            summarize_autonomy_lifecycle=_summarize_autonomy_lifecycle_fallback,
        )


_AUTONOMY_LIFECYCLE_RUNTIME = _load_autonomy_lifecycle_runtime()
AUTONOMY_PHASE_ORDER = _AUTONOMY_LIFECYCLE_RUNTIME.AUTONOMY_PHASE_ORDER
summarize_autonomy_lifecycle = _AUTONOMY_LIFECYCLE_RUNTIME.summarize_autonomy_lifecycle

def _extract_event_context(*args, **kwargs):
    return _local_extract_event_context(*args, **kwargs)


def get_strategy_factory_package():
    return _runtime_get_strategy_factory_package()


async def _call_optional_async(target: Any, method_name: str, *args, default=None, **kwargs):
    return await _runtime_call_optional_async(target, method_name, *args, default=default, **kwargs)


# P3 (R7.3): timeout-source classification used by the LLM research task
# scheduler. Maps to one of three buckets:
#   - external_llm_timeout: external LLM gateway (network) failed to respond
#   - pipeline_stage_timeout: gateway responded, but a pipeline stage took
#     longer than its per-stage budget
#   - bulk_research_timeout: bulk_stock_matrix task hit the bulk timeout cap
class ResearchTaskTimeoutKind:
    EXTERNAL_LLM = "external_llm_timeout"
    PIPELINE_STAGE = "pipeline_stage_timeout"
    BULK_RESEARCH = "bulk_research_timeout"


_GATE3_WEAK_STAT_REASON_MARKERS = (
    "weak_wf_ic_ir",
    "weak_pkf_ic",
    "weak_bootstrap_ci_lower",
    "weak_param_sensitivity",
    "missing_statistical_metrics",
    "missing_wf_ic_ir",
    "missing_pkf_ic",
    "missing_bootstrap_ci_lower",
    "win_rate_",
    "purged_kfold_ic_",
    "walk_forward_ic_ir_",
    "bootstrap_ci_lower_",
)


def _scheduler_feedback_safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return int(default)


def _scheduler_feedback_safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _scheduler_feedback_family(value: Any) -> str:
    return str(value or "").strip().lower()


def _scheduler_feedback_is_weak_stat_reason(reason: Any) -> bool:
    token = str(reason or "").strip().lower()
    if not token:
        return False
    return any(marker in token for marker in _GATE3_WEAK_STAT_REASON_MARKERS)


def _scheduler_feedback_reason_topn(*reason_sources: Any, limit: int = 5) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for source in reason_sources:
        if isinstance(source, dict):
            reason = str(
                source.get("reason_code")
                or source.get("reason")
                or source.get("code")
                or ""
            ).strip()
            count = _scheduler_feedback_safe_int(source.get("count"), 1)
            if reason:
                counter[reason] += max(1, count)
            continue
        if isinstance(source, (list, tuple, set)):
            for item in source:
                if isinstance(item, dict):
                    reason = str(
                        item.get("reason_code")
                        or item.get("reason")
                        or item.get("code")
                        or ""
                    ).strip()
                    count = _scheduler_feedback_safe_int(item.get("count"), 1)
                else:
                    reason = str(item or "").strip()
                    count = 1
                if reason:
                    counter[reason] += max(1, count)
            continue
        reason = str(source or "").strip()
        if reason:
            counter[reason] += 1
    return [
        {"reason_code": reason, "count": int(count)}
        for reason, count in counter.most_common(max(1, int(limit or 5)))
    ]


def _scheduler_feedback_submission_payload(results: dict[str, Any]) -> dict[str, Any]:
    stages = dict((results or {}).get("stages") or {})
    return dict((results or {}).get("submit_result") or stages.get("submit") or {})


def _scheduler_feedback_submission_family(item: dict[str, Any]) -> str:
    payload = dict(item or {})
    family_summary = dict(payload.get("family_outcome_summary") or {})
    provenance = dict(payload.get("candidate_provenance") or {})
    params = dict(payload.get("params") or {})
    nested_provenance = dict(params.get("candidate_provenance") or {})
    return _scheduler_feedback_family(
        family_summary.get("candidate_family")
        or payload.get("candidate_family")
        or provenance.get("candidate_family")
        or nested_provenance.get("candidate_family")
        or payload.get("strategy_type")
        or family_summary.get("strategy_type")
    )


def _scheduler_feedback_submission_reasons(item: dict[str, Any]) -> list[str]:
    payload = dict(item or {})
    gate = dict(payload.get("gate_3") or {})
    reasons: list[str] = []
    for source in (
        payload.get("reason_codes"),
        payload.get("reasons"),
        payload.get("admission_block_reasons"),
        gate.get("reason_codes"),
        gate.get("reasons"),
        gate.get("admission_block_reasons"),
    ):
        if isinstance(source, (list, tuple, set)):
            for reason in source:
                token = str(reason or "").strip()
                if token:
                    reasons.append(token)
        else:
            token = str(source or "").strip()
            if token:
                reasons.append(token)
    return reasons


def _scheduler_feedback_family_observations(
    results: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payload = dict(results or {})
    submit = _scheduler_feedback_submission_payload(payload)
    summary = dict(payload.get("summary") or {})
    family_counts = dict(
        (submit.get("incubation_budget_summary") or {}).get("family_counts")
        or summary.get("incubation_budget_family_counts")
        or {}
    )
    topn = _scheduler_feedback_reason_topn(
        submit.get("gate_3_failure_reason_topn"),
        submit.get("gate_3_failure_topn"),
        summary.get("gate_3_failure_reason_topn"),
        summary.get("gate_3_failure_topn"),
    )
    total_input = _scheduler_feedback_safe_int(
        submit.get("gate_3_input"),
        _scheduler_feedback_safe_int(summary.get("gate_3_input")),
    )
    total_passed = _scheduler_feedback_safe_int(
        submit.get("gate_3_passed"),
        _scheduler_feedback_safe_int(summary.get("gate_3_passed")),
    )
    total_submitted = _scheduler_feedback_safe_int(
        submit.get("submitted"),
        _scheduler_feedback_safe_int(summary.get("submitted")),
    )
    total_failed = _scheduler_feedback_safe_int(
        submit.get("gate_3_failed"),
        max(total_input - total_passed, 0),
    )
    total_audit_only = _scheduler_feedback_safe_int(
        submit.get("created_audit_only"),
        _scheduler_feedback_safe_int(summary.get("created_audit_only")),
    )
    observations: dict[str, dict[str, Any]] = {}

    for raw_item in list(submit.get("strategies") or []):
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item or {})
        family = _scheduler_feedback_submission_family(item)
        if not family:
            continue
        gate = dict(item.get("gate_3") or {})
        status = str(item.get("status") or "").strip().lower()
        passed = bool(item.get("passed") or gate.get("passed"))
        submitted = bool(item.get("submitted") or status in {"submitted", "incubating", "listed"})
        audit_only = bool(
            item.get("created_audit_only")
            or item.get("diagnostic_only")
            or status in {"diagnostic", "rejected"}
        )
        reasons = _scheduler_feedback_submission_reasons(item)
        bucket = observations.setdefault(
            family,
            {
                "gate_3_input_count": 0,
                "gate_3_passed_count": 0,
                "submitted_count": 0,
                "gate_3_failed_count": 0,
                "created_audit_only_count": 0,
                "weak_stat_failure_count": 0,
                "reasons": [],
            },
        )
        bucket["gate_3_input_count"] += 1
        if passed:
            bucket["gate_3_passed_count"] += 1
        else:
            bucket["gate_3_failed_count"] += 1
        if submitted:
            bucket["submitted_count"] += 1
        if audit_only:
            bucket["created_audit_only_count"] += 1
        if not passed and any(_scheduler_feedback_is_weak_stat_reason(reason) for reason in reasons):
            bucket["weak_stat_failure_count"] += 1
        bucket["reasons"].extend(reasons)

    if not observations and family_counts:
        family_total = sum(max(0, _scheduler_feedback_safe_int(value)) for value in family_counts.values())
        pass_ratio = (float(total_passed) / float(total_input)) if total_input > 0 else 0.0
        submitted_ratio = (float(total_submitted) / float(total_input)) if total_input > 0 else 0.0
        audit_ratio = (float(total_audit_only) / float(total_input)) if total_input > 0 else 0.0
        weak_topn_total = sum(
            int(item.get("count") or 0)
            for item in topn
            if _scheduler_feedback_is_weak_stat_reason(item.get("reason_code"))
        )
        weak_ratio = (float(weak_topn_total) / float(total_failed)) if total_failed > 0 else 0.0
        for family, raw_count in family_counts.items():
            token = _scheduler_feedback_family(family)
            input_count = max(0, _scheduler_feedback_safe_int(raw_count))
            if not token or input_count <= 0:
                continue
            passed_count = min(input_count, int(round(input_count * pass_ratio)))
            submitted_count = min(input_count, int(round(input_count * submitted_ratio)))
            failed_count = max(input_count - passed_count, 0)
            observations[token] = {
                "gate_3_input_count": input_count,
                "gate_3_passed_count": passed_count,
                "submitted_count": submitted_count,
                "gate_3_failed_count": failed_count,
                "created_audit_only_count": min(input_count, int(round(input_count * audit_ratio))),
                "weak_stat_failure_count": min(failed_count, int(round(failed_count * weak_ratio))),
                "reasons": [
                    item.get("reason_code")
                    for item in topn
                    if item.get("reason_code")
                ],
                "fallback_from_family_counts": True,
                "family_total": family_total,
            }

    aggregate = {
        "gate_3_input": total_input,
        "gate_3_passed": total_passed,
        "gate_3_failed": total_failed,
        "submitted": total_submitted,
        "created_audit_only": total_audit_only,
        "gate_3_failure_reason_topn": topn,
        "weak_stat_failure_count": sum(
            int(item.get("count") or 0)
            for item in topn
            if _scheduler_feedback_is_weak_stat_reason(item.get("reason_code"))
        ),
    }
    return observations, aggregate


def update_scheduler_family_gate_feedback(
    existing_feedback: dict[str, dict[str, Any]] | None,
    results: dict[str, Any],
    *,
    cycle_count: int,
    alpha: float = 0.3,
    ema_floor: float = 0.15,
    exploration_reset_interval: int = 20,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    observations, aggregate = _scheduler_feedback_family_observations(results)
    feedback: dict[str, dict[str, Any]] = {
        _scheduler_feedback_family(family): dict(bucket or {})
        for family, bucket in dict(existing_feedback or {}).items()
        if _scheduler_feedback_family(family)
    }
    active_families = set(observations.keys())
    alpha = min(max(float(alpha), 0.01), 1.0)
    ema_floor = max(0.0, float(ema_floor))

    for family, obs in observations.items():
        previous = dict(feedback.get(family) or {})
        input_count = max(0, _scheduler_feedback_safe_int(obs.get("gate_3_input_count")))
        passed_count = max(0, _scheduler_feedback_safe_int(obs.get("gate_3_passed_count")))
        submitted_count = max(0, _scheduler_feedback_safe_int(obs.get("submitted_count")))
        failed_count = max(0, _scheduler_feedback_safe_int(obs.get("gate_3_failed_count")))
        audit_only_count = max(0, _scheduler_feedback_safe_int(obs.get("created_audit_only_count")))
        weak_count = max(0, _scheduler_feedback_safe_int(obs.get("weak_stat_failure_count")))
        pass_signal = float(max(passed_count, submitted_count))
        prev_submit_ema = _scheduler_feedback_safe_float(previous.get("ema_submit_count"))
        submit_ema = round(alpha * pass_signal + (1.0 - alpha) * prev_submit_ema, 4)
        prev_input_ema = _scheduler_feedback_safe_float(previous.get("gate_3_input_count_ema"))
        input_ema = round(alpha * float(input_count) + (1.0 - alpha) * prev_input_ema, 4)
        prev_pass_ema = _scheduler_feedback_safe_float(previous.get("gate_3_passed_count_ema"))
        pass_ema = round(alpha * float(passed_count) + (1.0 - alpha) * prev_pass_ema, 4)
        prev_fail_ema = _scheduler_feedback_safe_float(previous.get("gate_3_failed_count_ema"))
        fail_ema = round(alpha * float(failed_count) + (1.0 - alpha) * prev_fail_ema, 4)
        failure_rate = round(float(failed_count) / float(input_count), 4) if input_count > 0 else 0.0
        pass_rate = round(float(passed_count) / float(input_count), 4) if input_count > 0 else 1.0
        weak_rate = round(float(weak_count) / float(input_count), 4) if input_count > 0 else 0.0
        previous_streak = _scheduler_feedback_safe_int(previous.get("gate_3_failure_streak"))
        failure_streak = previous_streak + 1 if input_count > 0 and passed_count <= 0 and failed_count > 0 else 0
        cooldown_active = bool(previous.get("cooldown_active")) and failure_rate >= 0.55
        suppressed = bool(previous.get("suppressed")) and failure_rate >= 0.70
        freeze_active = bool(previous.get("freeze_active")) and failure_rate >= 0.85
        if input_count >= 2 and failure_rate >= 0.75:
            cooldown_active = True
        if (input_count >= 3 and failure_rate >= 0.95) or (failure_streak >= 2 and failure_rate >= 0.90):
            suppressed = True
        if failure_streak >= 3 and input_ema >= 8.0 and failure_rate >= 0.98:
            freeze_active = True
        if passed_count > 0:
            cooldown_active = failure_rate >= 0.75
            suppressed = failure_rate >= 0.95 and input_count >= 4
            freeze_active = False
        reasons = _scheduler_feedback_reason_topn(obs.get("reasons"), aggregate.get("gate_3_failure_reason_topn"))
        entry = {
            **previous,
            "ema_submit_count": submit_ema,
            "strategy_count": max(input_count, int(round(input_ema))),
            "gate_3_input_count": input_count,
            "gate_3_passed_count": passed_count,
            "submitted_count": submitted_count,
            "gate_3_failed_count": failed_count,
            "created_audit_only_count": audit_only_count,
            "weak_stat_failure_count": weak_count,
            "gate_3_input_count_ema": input_ema,
            "gate_3_passed_count_ema": pass_ema,
            "gate_3_failed_count_ema": fail_ema,
            "gate_failure_rate": failure_rate,
            "submission_gate_failure_rate": failure_rate,
            "weak_stat_failure_rate": weak_rate,
            "paper_hit_ratio": pass_rate,
            "promotion_ready_ratio": pass_rate,
            "raw_validation_c_rate": min(1.0, failure_rate),
            "raw_validation_d_rate": min(1.0, weak_rate if weak_count > 0 else failure_rate),
            "strict_incubation_ready_rate": pass_rate,
            "last_failure_reason_topn": reasons,
            "gate_3_failure_streak": failure_streak,
            "cooldown_active": cooldown_active,
            "suppressed": suppressed,
            "suppress_active": suppressed,
            "freeze_active": freeze_active,
        }
        feedback[family] = entry

    for family in list(feedback.keys()):
        if family in active_families:
            continue
        previous = dict(feedback.get(family) or {})
        prev_submit_ema = _scheduler_feedback_safe_float(previous.get("ema_submit_count"))
        previous["ema_submit_count"] = max(ema_floor, round((1.0 - alpha) * prev_submit_ema, 4))
        previous["gate_3_input_count_ema"] = round(
            (1.0 - alpha) * _scheduler_feedback_safe_float(previous.get("gate_3_input_count_ema")),
            4,
        )
        previous["gate_3_passed_count_ema"] = round(
            (1.0 - alpha) * _scheduler_feedback_safe_float(previous.get("gate_3_passed_count_ema")),
            4,
        )
        previous["gate_3_failed_count_ema"] = round(
            (1.0 - alpha) * _scheduler_feedback_safe_float(previous.get("gate_3_failed_count_ema")),
            4,
        )
        decayed_failure_rate = round(
            (1.0 - alpha) * _scheduler_feedback_safe_float(previous.get("gate_failure_rate")),
            4,
        )
        previous["gate_failure_rate"] = decayed_failure_rate
        previous["submission_gate_failure_rate"] = decayed_failure_rate
        if decayed_failure_rate < 0.55:
            previous["cooldown_active"] = False
            previous["suppressed"] = False
            previous["suppress_active"] = False
            previous["freeze_active"] = False
        feedback[family] = previous

    if exploration_reset_interval > 0 and cycle_count > 0 and cycle_count % exploration_reset_interval == 0:
        for data in feedback.values():
            if _scheduler_feedback_safe_float(data.get("ema_submit_count")) < ema_floor + 0.05:
                data["ema_submit_count"] = 0.5

    update_summary = {
        **aggregate,
        "updated_family_count": len(active_families),
        "tracked_family_count": len(feedback),
        "active_families": sorted(active_families),
        "control_counts": dict(
            Counter(
                "freeze"
                if bucket.get("freeze_active")
                else "suppress"
                if bucket.get("suppressed")
                else "cooldown"
                if bucket.get("cooldown_active")
                else "normal"
                for bucket in feedback.values()
            )
        ),
    }
    return feedback, update_summary


def _classify_research_task_timeout_kind(
    task: dict[str, Any] | None,
    *,
    base_timeout_sec: float,
    effective_timeout_sec: float | None,
) -> str:
    """Pick a ResearchTaskTimeoutKind based on the task and the actual
    timeout budget that fired.

    Heuristic (kept conservative — see design.md E4):
      - If the task is a bulk_stock_matrix task, classify as BULK_RESEARCH.
      - Else if the effective timeout matches the bulk timeout cap (>= 240s
        as a soft signal), still classify as BULK_RESEARCH.
      - Else if the effective timeout matches the external LLM cap
        (typically 120s), classify as EXTERNAL_LLM.
      - Else default to PIPELINE_STAGE.
    """
    payload = dict(task or {})
    task_source = str(payload.get("task_source") or "").strip().lower()
    if task_source == "bulk_stock_matrix":
        return ResearchTaskTimeoutKind.BULK_RESEARCH

    eff = float(effective_timeout_sec or 0.0)
    base = float(base_timeout_sec or 0.0)

    # The bulk timeout cap is typically >= 240s; if the effective timeout
    # is close to that, treat it as bulk.
    if eff >= 240.0 and eff > base:
        return ResearchTaskTimeoutKind.BULK_RESEARCH

    # External LLM cap is typically <= 180s. If the effective timeout
    # equals (or is bound by) the external cap and the task uses external
    # LLM, classify as EXTERNAL_LLM.
    if (
        not bool(payload.get("disable_external_llm"))
        and eff <= 180.0
        and (eff < base if base > 0 else True)
    ):
        return ResearchTaskTimeoutKind.EXTERNAL_LLM

    return ResearchTaskTimeoutKind.PIPELINE_STAGE


from strategy_factory._fragment_loader import exec_block as _exec_block

_exec_block(
    globals(),
    '_factory_scheduler_loop_parts',
    'class _StrategyFactorySchedulerLoopMixin:\n        @staticmethod\n',
    ['normalizers.py', 'policy.py', 'evaluation.py', 'reporting.py', 'models.py'],
    future_annotations=True,
)
