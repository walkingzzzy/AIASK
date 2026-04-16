"""Strategy manager lifecycle action handlers: submit, publish, archive, lifecycle_scan, quality gates."""

import inspect
import logging
from datetime import datetime, timezone
from typing import Optional

from ...utils import fail, ok
from .strategy_mgr_helpers import (
    build_factory_recent_run_diagnostics,
    build_factory_quality_baseline,
    build_incubation_overview,
    build_quality_report,
    get_latest_quality_report,
    list_quality_reports,
    merge_factory_run_summary_observability,
    normalize_factory_run_detail_contract,
    normalize_factory_run_summary_contract,
    normalize_quality_gate_result,
    parse_bool,
    refresh_factory_run_detail_quality_contract,
    refresh_factory_run_summary_quality_contract,
    save_quality_report,
    update_status,
    validate_transition,
)

logger = logging.getLogger(__name__)


def _load_signal_quality_registry_snapshot():
    try:
        from ...services.signal_quality_registry import (
            get_default_signal_quality_registry,
            get_default_signal_quality_registry_snapshot,
        )

        registry = get_default_signal_quality_registry()
        snapshot = dict(get_default_signal_quality_registry_snapshot() or {})
        return {
            **snapshot,
            "snapshot": snapshot,
            "drift": dict(registry.drift_check() or {}),
            "recent_probability": list(registry.recent_probability(5)),
            "recent_sentiment": list(registry.recent_sentiment(5)),
            "recent_factor": list(registry.recent_factor(5)),
        }
    except Exception:
        return {}


def _execution_audit_entity_chain_available(db) -> bool:
    required_methods = (
        "list_strategy_paper_orders",
        "list_strategy_paper_trades",
        "list_strategy_trade_positions",
        "list_strategy_trade_position_fills",
        "get_strategy_trade_audit_summary",
        "get_paper_nav_rows",
    )
    return all(hasattr(db, method) for method in required_methods)

_TRADE_AUDIT_BACKTEST_KEYS = (
    "post_cost_sharpe",
    "target_layer_oos_return",
    "target_layer_abnormal_return",
    "event_window_hit_ratio",
    "post_event_decay",
    "trade_density",
    "parameter_perturbation_trade_stability",
    "primary_validation_layer",
)


def _quality_report_submission_audit(report: Optional[dict]) -> dict:
    payload = dict(report or {})
    summary = dict(payload.get("summary") or {})
    fields = (
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
        "trend_cluster_ratio",
        "diversification_debt",
        "pool_profile_distribution",
        "review_issue_buckets",
        "review_issue_primary",
    )
    return {
        field: (payload.get(field) if payload.get(field) not in (None, "", [], {}) else summary.get(field))
        for field in fields
        if (
            payload.get(field) not in (None, "", [], {})
            or summary.get(field) not in (None, "", [], {})
        )
    }


def _run_once_accepts_db_arg(run_once) -> bool:
    """Prefer passing the current db, but tolerate legacy scheduler stubs."""
    try:
        params = list(inspect.signature(run_once).parameters.values())
    except (TypeError, ValueError):
        return True
    return any(
        param.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.VAR_KEYWORD,
        )
        for param in params
    )


def _select_latest_backtest_metrics(
    metrics_list: list[dict] | None,
    fallback: Optional[dict] = None,
) -> dict:
    items = list(metrics_list or [])
    fallback_payload = dict(fallback or {})
    preferred_periods = ("backtest", "all")
    for period in preferred_periods:
        matched = next((item for item in items if str(item.get("period") or "").strip().lower() == period), None)
        if matched:
            return {
                **fallback_payload,
                **dict(matched),
            }
    return fallback_payload


def _trade_audit_backtest_score(metrics: Optional[dict]) -> int:
    payload = dict(metrics or {})
    if not payload:
        return 0
    present_keys = sum(1 for key in _TRADE_AUDIT_BACKTEST_KEYS if payload.get(key) is not None)
    return present_keys * 100 + len(payload)


def _select_rich_backtest_metrics_from_reports(
    reports: list[dict] | None,
    fallback: Optional[dict] = None,
) -> dict:
    fallback_payload = dict(fallback or {})
    best_payload = dict(fallback_payload)
    best_score = _trade_audit_backtest_score(best_payload)
    for report in list(reports or []):
        candidate = dict((report or {}).get("backtest_metrics") or {})
        candidate_score = _trade_audit_backtest_score(candidate)
        if candidate_score > best_score:
            best_payload = candidate
            best_score = candidate_score
    if not best_payload:
        return fallback_payload
    merged = dict(best_payload)
    for key, value in fallback_payload.items():
        if value is not None:
            merged[key] = value
    return merged


async def _run_recheck_validation_report(db, strategy: dict) -> dict:
    from strategy_factory.application import _run_validation_report

    return (
        await _run_validation_report(
            str(strategy.get("strategy_type") or ""),
            dict(strategy.get("params") or {}),
            db,
        )
    ) or {}


async def _run_recheck_risk_report(db, strategy: dict) -> dict:
    from strategy_factory.application import _run_risk_report

    return (
        await _run_risk_report(
            str(strategy.get("strategy_type") or ""),
            dict(strategy.get("params") or {}),
            db,
        )
    ) or {}


async def _build_recheck_quality_inputs(db, strategy: dict, latest_report: Optional[dict]) -> tuple[dict, dict, dict]:
    strategy_id = str(strategy.get("id") or "")
    recent_reports = await list_quality_reports(db, strategy_id, limit=12)
    submission_report = None
    if strategy_id and hasattr(db, "get_strategy_quality_report"):
        submission_report = await db.get_strategy_quality_report(strategy_id, "submission")
    validation_report = dict((latest_report or {}).get("validation_report") or {})
    risk_report = dict((latest_report or {}).get("risk_report") or {})
    backtest_metrics = dict((latest_report or {}).get("backtest_metrics") or {})
    backtest_metrics = _select_rich_backtest_metrics_from_reports(
        [dict(latest_report or {}), dict(submission_report or {}), *list(recent_reports or [])],
        backtest_metrics,
    )

    metrics_list = await db.get_strategy_metrics(strategy["id"]) if hasattr(db, "get_strategy_metrics") else []
    backtest_metrics = _select_latest_backtest_metrics(metrics_list, backtest_metrics)

    try:
        fresh_validation_report = await _run_recheck_validation_report(db, strategy)
    except Exception as exc:
        logger.warning(
            "strategy_manager.review_report_recheck validation recompute failed for %s: %s",
            strategy.get("id"),
            exc,
        )
        fresh_validation_report = {}
    if fresh_validation_report:
        validation_report = fresh_validation_report

    try:
        fresh_risk_report = await _run_recheck_risk_report(db, strategy)
    except Exception as exc:
        logger.warning(
            "strategy_manager.review_report_recheck risk recompute failed for %s: %s",
            strategy.get("id"),
            exc,
        )
        fresh_risk_report = {}
    if fresh_risk_report:
        risk_report = fresh_risk_report

    return validation_report, risk_report, backtest_metrics


async def handle_review_report_recheck(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    latest_report = await get_latest_quality_report(db, sid)
    validation_report, risk_report, backtest_metrics = await _build_recheck_quality_inputs(db, strategy, latest_report)
    gate_result = await run_quality_gate(
        db,
        strategy,
        validation_report=validation_report,
        risk_report=risk_report,
        backtest_metrics=backtest_metrics,
    )
    report_type = f"recheck:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    report = build_quality_report(
        strategy_id=sid,
        strategy_type=strategy.get("strategy_type"),
        quality_gate=gate_result,
        validation_report=validation_report,
        risk_report=risk_report,
        dedup_report=(latest_report or {}).get("dedup_report") or {},
        backtest_metrics=backtest_metrics,
        snapshot=(latest_report or {}).get("snapshot") or {},
        status_after_review=strategy.get("status"),
        review_source="review_report_recheck",
        report_type=report_type,
        spawn_reason=((latest_report or {}).get("summary") or {}).get("spawn_reason"),
        submission_audit=_quality_report_submission_audit(latest_report),
    )
    await save_quality_report(db, sid, report, report_type=report_type)
    return ok(report)


def _resolve_replay_strategy_ids(params: dict) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    raw_values = [
        params.get("strategy_id"),
        params.get("id"),
        params.get("strategy_ids"),
    ]
    queue = list(raw_values)
    while queue:
        value = queue.pop(0)
        if isinstance(value, (list, tuple, set)):
            queue[:0] = list(value)
            continue
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


async def handle_submission_replay(db, params: dict) -> dict:
    strategy_ids = _resolve_replay_strategy_ids(params)
    if not strategy_ids:
        return fail("strategy_id is required")
    recheck_reports = parse_bool(params.get("recheck_reports"), True)
    from strategy_factory import StrategySubmitter

    submitter = StrategySubmitter()
    items: list[dict] = []
    for sid in strategy_ids:
        strategy = await db.get_strategy(sid)
        if not strategy:
            return fail(f"Strategy not found: {sid}")
        latest_report = await get_latest_quality_report(db, sid)
        if recheck_reports:
            validation_report, risk_report, backtest_metrics = await _build_recheck_quality_inputs(
                db,
                strategy,
                latest_report,
            )
        else:
            validation_report = dict((latest_report or {}).get("validation_report") or {})
            risk_report = dict((latest_report or {}).get("risk_report") or {})
            backtest_metrics = _select_rich_backtest_metrics_from_reports(
                [dict(latest_report or {})],
                dict((latest_report or {}).get("backtest_metrics") or {}),
            )
        snapshot = dict((latest_report or {}).get("snapshot") or {})
        if not snapshot.get("date"):
            snapshot["date"] = datetime.now(timezone.utc).date().isoformat()
        replayed = await submitter.replay_existing_submission(
            strategy,
            snapshot,
            db,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics=backtest_metrics,
            latest_report=latest_report,
        )
        gate = dict(replayed.get("gate") or {})
        items.append(
            {
                "strategy_id": sid,
                "name": replayed.get("name") or strategy.get("name"),
                "status": replayed.get("status"),
                "submission_lane": replayed.get("submission_lane"),
                "incubation_budget_track": replayed.get("incubation_budget_track"),
                "passed": bool(gate.get("passed")),
                "strict_incubation_ready": bool(gate.get("strict_incubation_ready")),
                "validation_grade": (
                    dict((replayed.get("quality_report") or {}).get("summary") or {}).get("validation_grade")
                ),
                "submission_action_trigger": replayed.get("submission_action_trigger"),
                "paper_lane_ready": replayed.get("paper_lane_ready"),
                "live_review_ready": replayed.get("live_review_ready"),
            }
        )
    return ok({"count": len(items), "recheck_reports": recheck_reports, "items": items})


async def handle_submit(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    current = strategy.get("status", "draft")
    if not validate_transition(current, "submitted"):
        return fail(f"Cannot submit from status: {current}")

    await update_status(db, sid, "submitted", actor_id="strategy_manager", reason="manual_submit")

    metrics_list = await db.get_strategy_metrics(sid) if hasattr(db, 'get_strategy_metrics') else []
    backtest_metrics = next((item for item in metrics_list if item.get('period') in ('backtest', 'all')), {})
    latest_report = await get_latest_quality_report(db, sid)
    gate_result = await run_quality_gate(
        db,
        strategy,
        validation_report=(latest_report or {}).get('validation_report') or {},
        risk_report=(latest_report or {}).get('risk_report') or {},
        backtest_metrics=backtest_metrics,
    )
    next_status = "incubating" if gate_result["passed"] else "rejected"
    # Fix #5: 将实际的回测指标和已有报告数据保存到质量报告中
    await save_quality_report(db, sid, build_quality_report(
        strategy_id=sid,
        strategy_type=strategy.get("strategy_type"),
        quality_gate=gate_result,
        validation_report=(latest_report or {}).get('validation_report') or {},
        risk_report=(latest_report or {}).get('risk_report') or {},
        dedup_report=(latest_report or {}).get('dedup_report') or {},
        backtest_metrics=backtest_metrics,
        snapshot=(latest_report or {}).get('snapshot') or {},
        status_after_review=next_status,
        review_source="manager_submit",
        report_type="submission",
        submission_audit=_quality_report_submission_audit(latest_report),
    ))
    if gate_result["passed"]:
        incubation_binding = None
        vector_profile = None
        await update_status(db, sid, "incubating", actor_id="strategy_manager", reason="quality_gate_provisional_passed" if gate_result.get("provisional_pass") else "quality_gate_passed", metadata={"quality_gate": gate_result})
        try:
            from ...services.incubation import get_strategy_incubation_service
            incubation_binding = await get_strategy_incubation_service().ensure_account(db, strategy)
        except Exception as exc:
            logger.warning("strategy_manager.submit ensure_account failed for %s: %s", sid, exc)
        try:
            from ...services.vector_platform import get_strategy_vector_platform
            vector_profile = await get_strategy_vector_platform().build_strategy_profile(db, strategy)
        except Exception as exc:
            logger.warning("strategy_manager.submit build_profile failed for %s: %s", sid, exc)
        return ok({
            "strategy_id": sid, "status": "incubating",
            "quality_gate": "passed", "details": gate_result,
            "incubation_account_id": ((incubation_binding or {}).get("account") or {}).get("id"),
            "vector_profile_id": (vector_profile or {}).get("id"),
        })
    else:
        await update_status(db, sid, "rejected", actor_id="strategy_manager", reason="quality_gate_failed", metadata={"quality_gate": gate_result})
        return ok({
            "strategy_id": sid, "status": "rejected",
            "quality_gate": "failed", "details": gate_result,
        })


async def handle_lifecycle_scan(db, params: dict) -> dict:
    results = await lifecycle_scan(db)
    return ok(results)


async def handle_incubation_overview(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if sid:
        strategy = await db.get_strategy(sid)
        if not strategy:
            return fail(f"Strategy not found: {sid}")
        return ok(await build_incubation_overview(db, strategy))
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    incubating = await db.list_strategies("incubating", limit=limit)
    items = [await build_incubation_overview(db, s) for s in incubating]
    return ok({"items": items, "count": len(items)})


async def handle_factory_status(db, params: dict) -> dict:
    from strategy_factory import get_factory_constants, get_strategy_factory_scheduler
    from strategy_factory.application._bulk_cursor import extract_bulk_stock_cursor
    from strategy_factory.api import FactoryStatusDTO

    scheduler = get_strategy_factory_scheduler()
    status = dict(scheduler.status() or {})
    current_last_result = dict(status.get("last_result") or {})
    current_last_summary = dict(status.get("last_summary") or {})
    if current_last_result:
        if current_last_summary and not current_last_result.get("summary"):
            current_last_result["summary"] = current_last_summary
        normalized_last_result = normalize_factory_run_summary_contract(current_last_result)
        status["last_result"] = normalized_last_result
        status["last_summary"] = merge_factory_run_summary_observability(
            normalized_last_result.get("summary") or current_last_summary,
            normalized_last_result,
        )
    factory_constants = get_factory_constants()
    high_confidence_feature_flags = dict(factory_constants.get("HIGH_CONFIDENCE_FEATURE_FLAGS") or {})

    def _default_bulk_config() -> dict:
        return {
            "enabled": bool(factory_constants.get("STOCK_STRATEGY_MATRIX_ENABLED")),
            "universe_limit": int(factory_constants.get("STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT") or 0),
            "families_per_stock": int(factory_constants.get("STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK") or 0),
            "max_tasks_per_run": int(factory_constants.get("STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN") or 0),
            "max_candidates_per_run": int(factory_constants.get("STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN") or 0),
            "generation_limit_per_task": int(factory_constants.get("STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK") or 0),
            "batch_size": int(factory_constants.get("STOCK_STRATEGY_MATRIX_BATCH_SIZE") or 0),
            "bulk_concurrency": int(factory_constants.get("STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY") or 0),
            "run_window": factory_constants.get("STOCK_STRATEGY_MATRIX_RUN_WINDOW"),
            "tasks_per_shard": int(factory_constants.get("STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD") or 0),
            "pre_gate_enabled": bool(factory_constants.get("FACTORY_PRE_GATE_ENABLED")),
        }

    def _coerce_status_timestamp(value) -> Optional[datetime]:
        if isinstance(value, datetime):
            ts = value
        else:
            raw = str(value or "").strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                ts = datetime.fromisoformat(raw)
            except ValueError:
                return None
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)

    def _current_status_timestamp(payload: dict) -> Optional[datetime]:
        last_result = dict(payload.get("last_result") or {})
        last_summary = dict(payload.get("last_summary") or {})
        return (
            _coerce_status_timestamp(last_result.get("completed_at"))
            or _coerce_status_timestamp(last_result.get("started_at"))
            or _coerce_status_timestamp(payload.get("last_run"))
            or _coerce_status_timestamp(last_summary.get("completed_at"))
            or _coerce_status_timestamp(last_summary.get("started_at"))
        )

    status["bulk_stock_matrix_config"] = {
        **_default_bulk_config(),
        **dict(status.get("bulk_stock_matrix_config") or {}),
    }
    latest_run = await db.get_latest_strategy_factory_run() if hasattr(db, "get_latest_strategy_factory_run") else None
    if latest_run:
        latest_run_summary = await refresh_factory_run_summary_quality_contract(db, latest_run)
        latest_run_timestamp = (
            _coerce_status_timestamp(latest_run_summary.get("completed_at"))
            or _coerce_status_timestamp(latest_run_summary.get("started_at"))
        )
        current_status_timestamp = _current_status_timestamp(status)
        prefer_persisted_run = not status.get("last_result") or (
            latest_run_timestamp is not None
            and (current_status_timestamp is None or latest_run_timestamp >= current_status_timestamp)
        )
        status["last_persisted_run"] = latest_run
        if prefer_persisted_run:
            status["last_run"] = latest_run_summary.get("completed_at") or latest_run_summary.get("started_at")
            status["last_result"] = latest_run_summary
            status["last_summary"] = merge_factory_run_summary_observability(
                latest_run_summary.get("summary") or {},
                latest_run_summary,
            )
        if not (status.get("bulk_stock_matrix_cursor") or {}).get("available"):
            status["bulk_stock_matrix_cursor"] = extract_bulk_stock_cursor(
                latest_run.get("summary") or {},
                source="persisted_run",
                run_id=latest_run.get("run_id"),
            )
    status["quality_baseline"] = await build_factory_quality_baseline(
        db,
        latest_run=status.get("last_result") or latest_run,
    )
    recent_run_limit = min(max(int(params.get("recent_run_limit", 5)), 1), 10)
    recent_run_rows = (
        await db.list_strategy_factory_runs(limit=recent_run_limit)
        if hasattr(db, "list_strategy_factory_runs")
        else []
    )
    recent_run_items = [
        await refresh_factory_run_summary_quality_contract(db, row)
        for row in recent_run_rows
    ]
    status["recent_run_diagnostics"] = build_factory_recent_run_diagnostics(
        recent_run_items,
        limit=recent_run_limit,
    )
    if isinstance(status.get("quality_baseline"), dict):
        status["quality_baseline"] = {
            **dict(status.get("quality_baseline") or {}),
            "recent_run_diagnostics": dict(status.get("recent_run_diagnostics") or {}),
        }
    status["high_confidence_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_HIGH_CONFIDENCE_ENABLED"))
    status["evidence_contract_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED"))
    status["confidence_diagnostics_enabled"] = bool(
        factory_constants.get("STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED")
    )
    status["execution_audit_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED"))
    status["quality_ui_v2_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_QUALITY_UI_V2_ENABLED"))
    status["research_protocol_v2_enabled"] = bool(
        factory_constants.get("STRATEGY_FACTORY_RESEARCH_PROTOCOL_V2_ENABLED")
    )
    status["gate_model_v2_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_GATE_MODEL_V2_ENABLED"))
    status["trace_ledger_v2_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_TRACE_LEDGER_V2_ENABLED"))
    status["feedback_v2_enabled"] = bool(factory_constants.get("STRATEGY_FACTORY_FEEDBACK_V2_ENABLED"))
    status["trace_ledger_v2_implemented"] = True
    status["governance_gate_report_v2_implemented"] = True
    status["execution_audit_entity_chain_available"] = _execution_audit_entity_chain_available(db)
    status["spec_completeness_mode"] = str(
        factory_constants.get("STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE") or "warn"
    )
    status["feature_flags"] = high_confidence_feature_flags
    status["signal_quality_registry"] = _load_signal_quality_registry_snapshot()
    status = {
        **status,
        **FactoryStatusDTO.from_dict(status).to_dict(),
    }
    return ok(status)


async def handle_factory_run_once(db, params: dict) -> dict:
    from strategy_factory import get_strategy_factory_scheduler

    scheduler = get_strategy_factory_scheduler()
    run_once = scheduler.run_once
    if _run_once_accepts_db_arg(run_once):
        return ok(await run_once(db))
    return ok(await run_once())


async def handle_factory_runs(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 10)), 1), 100)
    rows = await db.list_strategy_factory_runs(limit=limit) if hasattr(db, "list_strategy_factory_runs") else []
    items = [await refresh_factory_run_summary_quality_contract(db, row) for row in rows]
    return ok({"items": items, "count": len(rows)})


async def handle_factory_run_detail(db, params: dict) -> dict:
    run_id = str(params.get("run_id") or "").strip()
    if not run_id:
        return fail("run_id is required")
    row = await db.get_strategy_factory_run(run_id) if hasattr(db, "get_strategy_factory_run") else None
    if not row:
        return fail(f"Factory run not found: {run_id}")
    return ok(await refresh_factory_run_detail_quality_contract(db, row))


async def handle_execution_audit_verification(db, params: dict) -> dict:
    if not hasattr(db, "get_execution_audit_verification"):
        return fail("execution audit verification is unavailable")
    strategy_id = str(params.get("strategy_id") or params.get("id") or "").strip() or None
    return ok(await db.get_execution_audit_verification(strategy_id=strategy_id))


# ── Quality gate runner ──────────────────────────────────────────────────────

async def run_quality_gate(
    db,
    strategy: dict,
    *,
    validation_report: Optional[dict] = None,
    risk_report: Optional[dict] = None,
    backtest_metrics: Optional[dict] = None,
) -> dict:
    """Run the shared submission-stage quality gate and normalize the result."""
    from strategy_factory import run_submission_quality_gate

    return normalize_quality_gate_result(
        await run_submission_quality_gate(
            db,
            strategy,
            validation_report=validation_report,
            risk_report=risk_report,
            backtest_metrics=backtest_metrics,
        )
    )


# ── Lifecycle scan ───────────────────────────────────────────────────────────

async def lifecycle_scan(db) -> dict:
    """Batch scan for strategy status transitions."""
    from ...services.promotion_pipeline import get_strategy_promotion_pipeline_service

    transitions = []
    blocked = []
    reviews = []
    promotion_service = get_strategy_promotion_pipeline_service()

    incubating = await db.list_strategies("incubating", limit=100)
    for s in incubating:
        review_result = await promotion_service.review(db, s, source='lifecycle_scan', auto_apply=True)
        review = review_result.get('review') or {}
        overview = review_result.get('overview') or {}
        reviews.append(review)
        if review_result.get('applied_transition'):
            transition = review_result['applied_transition']
            reason = 'incubation_promoted' if transition.get('to') == 'listed' else 'incubation_failed'
            transitions.append({
                'id': s['id'],
                **transition,
                'reason': reason,
            })
        else:
            blocked.append({'id': s['id'], 'status': 'incubating', 'blockers': overview.get('blockers') or []})

    listed = await db.list_strategies("listed", limit=200)
    for s in listed:
        overview = await build_incubation_overview(db, s)
        if overview["deprecation_risk"]:
            # Fix #13: 要求连续多期触发降级风险才执行降级，避免单次波动误杀
            deprecation_confirmed = False
            if hasattr(db, 'list_strategy_incubation_metrics'):
                recent_metrics = await db.list_strategy_incubation_metrics(s["id"], limit=3)
                if len(recent_metrics) >= 2:
                    # 最近 2 期以上连续 decision=halt 才确认降级
                    halt_streak = sum(1 for m in recent_metrics if str(m.get('decision') or '') == 'halt')
                    deprecation_confirmed = halt_streak >= 2
                else:
                    # 数据不足时不急于降级
                    deprecation_confirmed = False
            else:
                deprecation_confirmed = True  # 无法查询历史时保持原行为

            if deprecation_confirmed:
                await update_status(
                    db,
                    s["id"],
                    "deprecated",
                    actor_id="lifecycle_scan",
                    reason="listed_degraded",
                    metadata=overview,
                )
                transitions.append({"id": s["id"], "from": "listed", "to": "deprecated", "reason": "listed_degraded"})
            else:
                blocked.append({"id": s["id"], "status": "listed", "blockers": ["deprecation_risk_unconfirmed"]})

    return {"scanned": len(incubating) + len(listed), "transitions": transitions, "blocked": blocked, 'reviews': reviews}


# Backward-compatible aliases
_run_quality_gate = run_quality_gate
_lifecycle_scan = lifecycle_scan
