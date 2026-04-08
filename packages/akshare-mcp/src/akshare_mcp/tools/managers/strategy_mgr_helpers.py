"""Strategy manager helpers: NAV calculation, state management, quality report, incubation overview."""

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from strategy_factory.api import normalize_run_result_to_detail, normalize_run_result_to_summary
from strategy_factory import (
    BACKTEST_AI_PROTOTYPE_THRESHOLDS,
    DEPRECATION_THRESHOLDS,
    PROMOTION_THRESHOLDS,
    PROVISIONAL_PASS_THRESHOLDS,
    QUALITY_GATE_THRESHOLDS,
    RISK_REPORT_THRESHOLDS,
)
from strategy_factory.application.quality_reporting import (
    build_quality_report as _shared_build_quality_report,
    normalize_quality_gate_result as _shared_normalize_quality_gate_result,
    quality_gate_reason_code as _shared_quality_gate_reason_code,
)

from ...services.strategy_lifecycle_shared import (
    LIFECYCLE_TRANSITIONS,
    build_incubation_overview,
    get_latest_quality_report,
    list_quality_reports,
    metric_bucket_value,
    normalize_status_alias,
    update_status,
    validate_transition,
)

logger = logging.getLogger(__name__)


# ── NAV calculation ──────────────────────────────────────────────────────────

async def compute_nav_series(db, strategy_id: str, max_points: int = 30) -> list:
    """Return paper-trading NAV; fall back to signal_forward_returns derived NAV."""
    try:
        if hasattr(db, "get_paper_account_by_strategy") and hasattr(db, "get_paper_nav_rows"):
            account = await db.get_paper_account_by_strategy(strategy_id)
            if account:
                nav_rows = await db.get_paper_nav_rows(account["id"], limit=max(max_points * 4, 60))
                if nav_rows:
                    nav = [
                        round(
                            float(row.get("total_value") or 0.0)
                            / max(float(account.get("initial_capital") or 1.0), 1.0),
                            4,
                        )
                        for row in reversed(nav_rows)
                    ]
                    if len(nav) > max_points:
                        step = max(1, len(nav) // max_points)
                        nav = nav[::step][:max_points]
                    return nav
        async with db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ss.signal_date, ss.signal, sfr.actual_return
                FROM strategy_signals ss
                JOIN signal_forward_returns sfr ON sfr.signal_id = ss.id AND sfr.forward_days = 5
                WHERE ss.strategy_id = $1 AND ss.signal != 0
                ORDER BY ss.signal_date
                """,
                strategy_id,
            )
        if not rows:
            return []
        daily: dict = {}
        for r in rows:
            d = r["signal_date"]
            ret = float(r["actual_return"] or 0) * (1 if r["signal"] == 1 else -1)
            daily.setdefault(d, []).append(ret)
        nav = [1.0]
        for d in sorted(daily):
            avg = sum(daily[d]) / len(daily[d])
            nav.append(round(nav[-1] * (1 + avg), 4))
        if len(nav) > max_points:
            step = max(1, len(nav) // max_points)
            nav = nav[::step][:max_points]
        return nav
    except Exception:
        return []


# ── Lifecycle state management (imported from strategy_lifecycle_shared) ─────


# ── Quality report helpers ───────────────────────────────────────────────────

async def save_quality_report(db, strategy_id: str, report: dict, report_type: str = "submission") -> None:
    if hasattr(db, "save_strategy_quality_report"):
        await db.save_strategy_quality_report(strategy_id, report_type, report)


# metric_bucket_value imported from strategy_lifecycle_shared


def normalize_time_filter(value: Any, *, is_end: bool = False) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 10:
        dt = datetime.fromisoformat(text)
        if is_end:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        else:
            dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def quality_gate_reason_code(reason: str) -> str:
    return _shared_quality_gate_reason_code(reason)


def normalize_quality_gate_result(result: Optional[dict]) -> dict:
    return _shared_normalize_quality_gate_result(result)


def is_factory_ai_prototype_strategy(strategy: Optional[dict]) -> bool:
    payload = dict(strategy or {})
    strategy_type = str(payload.get("strategy_type") or "").strip().lower()
    tags = {str(tag).strip().lower() for tag in list(payload.get("tags") or [])}
    if "factory" not in tags and "auto_generated" not in tags:
        return False
    if "external_llm" in tags or "ai_generated" in tags:
        return True
    return strategy_type == "dsl_rule"


def has_only_statistical_gate_failures(gate_result: Optional[dict]) -> bool:
    gate = normalize_quality_gate_result(gate_result)
    codes = list(gate.get("reason_codes") or [])
    if not codes:
        return False
    allowed_prefixes = (
        "walk_forward_ic_ir",
        "purged_k_fold_ic",
        "bootstrap_ci_lower",
        "parameter_sensitivity",
        "multi_period_ic",
    )
    return all(any(str(code).startswith(prefix) for prefix in allowed_prefixes) for code in codes)


def safe_metric_value(payload: Optional[dict], *keys: str) -> float:
    data = dict(payload or {})
    for key in keys:
        if key in data and data.get(key) is not None:
            try:
                return float(data.get(key) or 0.0)
            except Exception:
                return 0.0
    return 0.0


def _count_statistical_checks_passed(gate: dict) -> tuple[int, list[str], list[str]]:
    """统计质量门 5 项统计检查中通过了几项，返回 (通过数, 通过项列表, 失败项列表)。"""
    check_map = {
        "walk_forward_ic_ir": ("wf_ic_ir", QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"], ">="),
        "purged_kfold_ic": ("pkf_ic", QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"], ">="),
        "bootstrap_ci_lower": ("bootstrap_ci_lower", QUALITY_GATE_THRESHOLDS["bootstrap_ci_lower_min"], ">="),
        "param_sensitivity": ("param_sensitivity", QUALITY_GATE_THRESHOLDS["param_sensitivity_max"], "<="),
    }
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    for check_name, (key, threshold, op) in check_map.items():
        value = gate.get(key)
        if value is None:
            failed_checks.append(check_name)
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            failed_checks.append(check_name)
            continue
        if op == ">=" and val >= threshold:
            passed_checks.append(check_name)
        elif op == "<=" and val <= threshold:
            passed_checks.append(check_name)
        else:
            failed_checks.append(check_name)

    # 5th check: multi-period robustness (from period_robustness dict in gate)
    pr = gate.get("period_robustness") or {}
    first_ic = pr.get("first_half_ic")
    second_ic = pr.get("second_half_ic")
    if first_ic is not None and second_ic is not None:
        try:
            f_ic, s_ic = float(first_ic), float(second_ic)
            direction_consistent = not (f_ic > 0.01 and s_ic < -0.01) and not (f_ic < -0.01 and s_ic > 0.01)
            both_non_negative = f_ic >= -0.02 and s_ic >= -0.02
            if both_non_negative and direction_consistent:
                passed_checks.append("multi_period_robustness")
            else:
                failed_checks.append("multi_period_robustness")
        except (TypeError, ValueError):
            failed_checks.append("multi_period_robustness")
    else:
        # Data not available — treat as not checked (don't count as failed)
        pass

    return len(passed_checks), passed_checks, failed_checks


# 临时孵化要求至少通过的统计检查项数（5 项中至少通过 2 项）
PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED = 2


def maybe_grant_provisional_incubation(
    strategy: Optional[dict],
    quality_gate: Optional[dict],
    *,
    validation_report: Optional[dict] = None,
    risk_report: Optional[dict] = None,
    backtest_metrics: Optional[dict] = None,
) -> dict:
    gate = normalize_quality_gate_result(quality_gate)
    if gate.get("passed"):
        return gate
    if not is_factory_ai_prototype_strategy(strategy):
        return gate
    if not has_only_statistical_gate_failures(gate):
        return gate

    # Fix #3: 风险报告为空时不能通过临时孵化（0.0 默认值会绕过阈值检查）
    if not risk_report:
        return gate

    # Fix #7: AI 原型不能完全绕过统计验证 — 至少通过 4 项中的 2 项
    checks_passed, passed_names, failed_names = _count_statistical_checks_passed(gate)
    if checks_passed < PROVISIONAL_MIN_STATISTICAL_CHECKS_PASSED:
        logger.info(
            "Provisional incubation denied: only %d/%d statistical checks passed (%s failed)",
            checks_passed, checks_passed + len(failed_names), ", ".join(failed_names),
        )
        return gate

    metrics = dict(backtest_metrics or {})
    # Fix #1/#2: 使用独立的临时孵化阈值，比回测初筛更严格
    sharpe_ratio = safe_metric_value(metrics, "sharpe_ratio")
    max_drawdown = abs(safe_metric_value(metrics, "max_drawdown"))
    trades_count = safe_metric_value(metrics, "trade_count", "trades_count")
    if (
        sharpe_ratio < PROVISIONAL_PASS_THRESHOLDS["sharpe_min"]
        or max_drawdown > PROVISIONAL_PASS_THRESHOLDS["mdd_max"]
        or trades_count < PROVISIONAL_PASS_THRESHOLDS["trades_min"]
    ):
        return gate

    risk = dict(risk_report or {})
    var_percent = safe_metric_value(risk, "var_percent")
    cvar_percent = safe_metric_value(risk, "cvar_percent")
    stress_loss_percent = safe_metric_value(risk, "stress_loss_percent")
    if (
        var_percent > RISK_REPORT_THRESHOLDS["var_percent_max"]
        or cvar_percent > RISK_REPORT_THRESHOLDS["cvar_percent_max"]
        or stress_loss_percent <= RISK_REPORT_THRESHOLDS["stress_loss_percent_min"]
    ):
        return gate

    validation = dict(validation_report or {})
    rating = dict(validation.get("rating") or {})
    validation_grade = str(rating.get("grade") or "").strip().upper()

    warnings = list(gate.get("reasons") or [])
    if validation_grade == "D" and "validation_grade_d" not in warnings:
        warnings.append("validation_grade_d")
    # 将未通过的统计检查加入 warnings（而非彻底忽略）
    for fname in failed_names:
        tag = f"provisional_skip:{fname}"
        if tag not in warnings:
            warnings.append(tag)
    warnings = list(dict.fromkeys(warnings))
    return normalize_quality_gate_result({
        **gate,
        "passed": True,
        "passed_strict": False,
        "provisional_pass": True,
        "review_mode": "incubation_only",
        "reasons": [],
        "reason": "",
        "warnings": warnings,
        "original_reasons": gate.get("reasons") or [],
        "original_reason_codes": gate.get("reason_codes") or [],
        "statistical_checks_passed": checks_passed,
        "statistical_checks_passed_names": passed_names,
        "statistical_checks_failed_names": failed_names,
    })


def build_quality_report(
    strategy_id: str,
    strategy_type: Optional[str],
    quality_gate: Optional[dict],
    validation_report: Optional[dict],
    risk_report: Optional[dict],
    dedup_report: Optional[dict],
    backtest_metrics: Optional[dict],
    snapshot: Optional[dict],
    status_after_review: Optional[str],
    review_source: str,
    report_type: str,
    spawn_reason: Optional[str] = None,
    submission_audit: Optional[dict] = None,
) -> dict:
    return _shared_build_quality_report(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        quality_gate=quality_gate,
        validation_report=validation_report,
        risk_report=risk_report,
        dedup_report=dedup_report,
        backtest_metrics=backtest_metrics,
        snapshot=snapshot,
        status_after_review=status_after_review,
        review_source=review_source,
        report_type=report_type,
        spawn_reason=spawn_reason,
        submission_audit=submission_audit,
    )


def normalize_quality_report_contract(
    report: Optional[dict],
    *,
    strategy_id: Optional[str] = None,
    strategy_type: Optional[str] = None,
    default_review_source: str = "strategy_manager.review_report",
) -> dict:
    raw = dict(report or {})
    if not raw:
        return {}

    summary = dict(raw.get("summary") or {})
    quality_gate = dict(raw.get("quality_gate") or {})
    validation_profile = dict(raw.get("validation_profile") or {})
    run_correction = dict(raw.get("run_correction") or {})
    attempt_adjustment = dict(raw.get("attempt_adjustment") or {})
    backtest_metrics = dict(raw.get("backtest_metrics") or {})

    mirrored_backtest_fields = (
        "constraint_check",
        "event_window_config",
        "event_window_metrics",
        "position_assumption",
        "cost_assumptions",
        "explicit_cost_breakdown",
        "implicit_cost_breakdown",
        "tradability_summary",
        "capacity_summary",
        "implementation_shortfall_model_source",
        "implementation_shortfall_components",
        "backtest_assumptions",
    )
    for field_name in mirrored_backtest_fields:
        if backtest_metrics.get(field_name) in (None, "", [], {}) and raw.get(field_name) not in (None, "", [], {}):
            backtest_metrics[field_name] = deepcopy(raw.get(field_name))

    if quality_gate.get("attempt_adjustment") in (None, "", [], {}) and attempt_adjustment:
        quality_gate["attempt_adjustment"] = attempt_adjustment
    if not quality_gate.get("primary_validation_layer"):
        quality_gate["primary_validation_layer"] = (
            summary.get("primary_validation_layer")
            or validation_profile.get("primary_validation_layer")
        )
    if not quality_gate.get("profile"):
        quality_gate["profile"] = validation_profile.get("profile")
    if not quality_gate.get("validation_focus"):
        quality_gate["validation_focus"] = validation_profile.get("validation_focus")
    run_correction_key_map = {
        "mode": "run_correction_mode",
        "raw_sharpe_proxy": "raw_sharpe_proxy",
        "deflated_sharpe_proxy": "deflated_sharpe_proxy",
        "pbo_proxy": "pbo_proxy",
        "reality_check_pvalue_proxy": "reality_check_pvalue_proxy",
        "spa_pvalue_proxy": "spa_pvalue_proxy",
        "multiple_testing_mode": "multiple_testing_mode",
        "deflated_sharpe_ratio": "deflated_sharpe_ratio",
        "deflated_sharpe_reference_sharpe": "deflated_sharpe_reference_sharpe",
        "deflated_sharpe_effective_trials": "deflated_sharpe_effective_trials",
        "pbo": "pbo",
        "white_reality_check_pvalue": "white_reality_check_pvalue",
        "hansen_spa_pvalue": "hansen_spa_pvalue",
        "multiple_testing": "multiple_testing",
    }
    for source_key, target_key in run_correction_key_map.items():
        if quality_gate.get(target_key) in (None, "", [], {}) and run_correction.get(source_key) not in (None, "", [], {}):
            quality_gate[target_key] = deepcopy(run_correction.get(source_key))

    submission_audit_fields = (
        "committee_review",
        "task_signature",
        "refresh_mode",
        "submission_lane",
        "direct_trade_candidate",
        "live_review_ready",
        "paper_lane_ready",
        "paper_account_id",
        "paper_account_status",
        "runtime_control_mode",
        "runtime_control_status",
        "promotion_review_id",
        "promotion_review_status",
        "promotion_review_recommendation",
        "pool_admission_applied",
        "promotion_applied_transition",
        "submission_action",
        "submission_action_type",
        "submission_action_trigger",
        "submission_action_gaps",
        "submission_action_fallback_conditions",
        "submission_action_next_step",
        "submission_action_completed",
        "task_preference",
        "candidate_provenance",
    )
    submission_audit = {}
    for field_name in submission_audit_fields:
        value = raw.get(field_name)
        if value in (None, "", [], {}):
            value = summary.get(field_name)
        if value not in (None, "", [], {}):
            submission_audit[field_name] = deepcopy(value)

    raw_strategy = raw.get("strategy")
    strategy_payload = dict(raw_strategy) if isinstance(raw_strategy, dict) else {}

    normalized = _shared_build_quality_report(
        strategy_id=str(strategy_id or summary.get("strategy_id") or raw.get("strategy_id") or "").strip(),
        strategy_type=(
            strategy_type
            or summary.get("strategy_type")
            or raw.get("strategy_type")
            or strategy_payload.get("strategy_type")
        ),
        quality_gate=quality_gate,
        validation_report=dict(raw.get("validation_report") or {}),
        risk_report=dict(raw.get("risk_report") or {}),
        dedup_report=dict(raw.get("dedup_report") or {}),
        backtest_metrics=backtest_metrics,
        snapshot=dict(raw.get("snapshot") or {}),
        status_after_review=summary.get("status_after_review") or raw.get("status_after_review"),
        review_source=summary.get("review_source") or default_review_source,
        report_type=str(raw.get("report_type") or "submission"),
        spawn_reason=summary.get("spawn_reason"),
        submission_audit=submission_audit or None,
    )
    return {**raw, **normalized}


def normalize_factory_run_summary_contract(row: Optional[dict]) -> dict:
    raw = dict(row or {})
    if not raw:
        return {}
    dto = normalize_run_result_to_summary(raw).to_dict()
    return {**raw, **dto}


def normalize_factory_run_detail_contract(row: Optional[dict]) -> dict:
    raw = dict(row or {})
    if not raw:
        return {}
    dto = normalize_run_result_to_detail(raw).to_dict()
    return {
        **raw,
        **dto,
        "summary": dict(raw.get("summary") or {}),
        "stages": dict(raw.get("stages") or {}),
        "snapshot_summary": dict(raw.get("snapshot_summary") or dto.get("snapshot_summary") or {}),
        "quality_gate": dict(raw.get("quality_gate") or raw.get("gate_report") or dto.get("quality_gate") or {}),
        "research_summary": dict(dto.get("research_summary") or {}),
        "research_plane": dict(dto.get("research_plane") or raw.get("research_plane") or {}),
        "research_artifact": dict(dto.get("research_artifact") or {}),
        "task_artifact": dict(dto.get("task_artifact") or {}),
        "candidate_artifact": dict(dto.get("candidate_artifact") or {}),
        "evidence_artifact": dict(dto.get("evidence_artifact") or {}),
        "governance_plane": dict(dto.get("governance_plane") or raw.get("governance_plane") or {}),
        "gate_artifact": dict(dto.get("gate_artifact") or {}),
        "dedup_artifact": dict(dto.get("dedup_artifact") or {}),
        "submission_artifact": dict(dto.get("submission_artifact") or {}),
        "governance_evidence_artifact": dict(dto.get("governance_evidence_artifact") or {}),
        "feedback_summary": dict(dto.get("feedback_summary") or {}),
        "incubation_summary": dict(dto.get("incubation_summary") or {}),
        "live_ready_summary": dict(dto.get("live_ready_summary") or {}),
    }


# list_quality_reports, get_latest_quality_report imported from strategy_lifecycle_shared


# ── Incubation overview builder (imported from strategy_lifecycle_shared) ────


# ── Backward-compatible aliases (underscore-prefixed names) ──────────────────
# External services import these via ``from ..tools.managers.strategy_manager import _xxx``.
# The main strategy_manager.py re-exports them, but we also define them here so that
# the helpers module itself is self-contained for direct imports.

_compute_nav_series = compute_nav_series
_normalize_status_alias = normalize_status_alias
_validate_transition = validate_transition
_update_status = update_status
_save_quality_report = save_quality_report
_metric_bucket_value = metric_bucket_value
_normalize_time_filter = normalize_time_filter
_parse_bool = parse_bool
_quality_gate_reason_code = quality_gate_reason_code
_normalize_quality_gate_result = normalize_quality_gate_result
_is_factory_ai_prototype_strategy = is_factory_ai_prototype_strategy
_has_only_statistical_gate_failures = has_only_statistical_gate_failures
_safe_metric_value = safe_metric_value
_maybe_grant_provisional_incubation = maybe_grant_provisional_incubation
_build_quality_report = build_quality_report
_list_quality_reports = list_quality_reports
_get_latest_quality_report = get_latest_quality_report
_build_incubation_overview = build_incubation_overview
