"""Strategy manager lifecycle action handlers: submit, publish, archive, lifecycle_scan, quality gates."""

import inspect
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from ...services.strategy_lifecycle_shared import build_closure_review
from ...utils import fail, ok
from .strategy_mgr_helpers import (
    build_factory_recent_run_diagnostics,
    build_factory_capability_health,
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


def _factory_status_source(params: dict) -> str:
    raw = str(
        params.get("status_source")
        or params.get("source_mode")
        or os.getenv("STRATEGY_FACTORY_STATUS_SOURCE")
        or "db"
    ).strip().lower()
    if raw in {"live", "scheduler", "runtime"}:
        return "scheduler"
    return "db"


def _int_config(factory_constants: dict, key: str) -> int:
    try:
        return int(factory_constants.get(key) or 0)
    except Exception:
        return 0


def _default_bulk_config(factory_constants: dict) -> dict:
    return {
        "enabled": bool(factory_constants.get("STOCK_STRATEGY_MATRIX_ENABLED")),
        "universe_limit": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_UNIVERSE_LIMIT"),
        "families_per_stock": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_FAMILIES_PER_STOCK"),
        "max_tasks_per_run": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_MAX_TASKS_PER_RUN"),
        "max_candidates_per_run": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_MAX_CANDIDATES_PER_RUN"),
        "generation_limit_per_task": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_GENERATION_LIMIT_PER_TASK"),
        "batch_size": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_BATCH_SIZE"),
        "bulk_concurrency": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_BULK_CONCURRENCY"),
        "run_window": factory_constants.get("STOCK_STRATEGY_MATRIX_RUN_WINDOW"),
        "tasks_per_shard": _int_config(factory_constants, "STOCK_STRATEGY_MATRIX_TASKS_PER_SHARD"),
        "pre_gate_enabled": bool(factory_constants.get("FACTORY_PRE_GATE_ENABLED")),
    }


def _factory_run_status_brief(row: Optional[dict]) -> dict:
    payload = dict(row or {})
    if not payload:
        return {}
    summary = dict(payload.get("summary") or {})
    return {
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "execution_mode": payload.get("execution_mode") or "legacy_primary",
        "engine_version": payload.get("engine_version") or "strategy_factory.v2",
        "parity_status": payload.get("parity_status"),
        "parity_result": dict(payload.get("parity_result") or {}),
        "artifact_refs": list(payload.get("artifact_refs") or []),
        "summary": merge_factory_run_summary_observability(summary, payload),
        "snapshot_summary": dict(payload.get("snapshot_summary") or {}),
        "research_window": dict(summary.get("research_window") or {}),
        "full_market_topn": dict(summary.get("full_market_topn") or {}),
        "error": payload.get("error"),
    }


async def _build_db_factory_status(db, params: dict) -> dict:
    from strategy_factory import get_factory_constants

    factory_constants = get_factory_constants()
    latest_run = await db.get_latest_strategy_factory_run() if hasattr(db, "get_latest_strategy_factory_run") else None
    latest_run_summary = _factory_run_status_brief(latest_run)
    recent_run_limit = min(max(int(params.get("recent_run_limit", 5)), 1), 10)
    recent_rows = (
        await db.list_strategy_factory_runs(limit=recent_run_limit)
        if hasattr(db, "list_strategy_factory_runs")
        else []
    )
    recent_items = [_factory_run_status_brief(row) for row in recent_rows]
    recent_diagnostics = build_factory_recent_run_diagnostics(recent_items, limit=recent_run_limit)
    last_summary = merge_factory_run_summary_observability(
        latest_run_summary.get("summary") or {},
        latest_run_summary,
    )
    quality_baseline = {
        "available": bool(latest_run_summary),
        "source": "db_snapshot",
        "recent_run_diagnostics": recent_diagnostics,
    }
    return {
        "status": "idle",
        "running": False,
        "status_source": "db_snapshot",
        "scheduler_attached": False,
        "last_run": latest_run_summary.get("completed_at") or latest_run_summary.get("started_at"),
        "last_result": latest_run_summary,
        "last_summary": last_summary,
        "last_persisted_run": latest_run_summary,
        "recent_run_diagnostics": recent_diagnostics,
        "quality_baseline": quality_baseline,
        "bulk_stock_matrix_config": _default_bulk_config(factory_constants),
        "research_window": dict(last_summary.get("research_window") or {}),
        "full_market_topn": dict(last_summary.get("full_market_topn") or {}),
        "execution_mode": latest_run_summary.get("execution_mode") or "legacy_primary",
        "engine_version": latest_run_summary.get("engine_version") or "strategy_factory.v2",
        "latest_parity_result": dict(latest_run_summary.get("parity_result") or {}),
        "capability_health": build_factory_capability_health(
            db,
            factory_constants=factory_constants,
            latest_run=latest_run_summary,
        ),
        "high_confidence_enabled": bool(factory_constants.get("STRATEGY_FACTORY_HIGH_CONFIDENCE_ENABLED")),
        "evidence_contract_enabled": bool(factory_constants.get("STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED")),
        "confidence_diagnostics_enabled": bool(factory_constants.get("STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED")),
        "execution_audit_enabled": bool(factory_constants.get("STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED")),
        "quality_ui_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_QUALITY_UI_V2_ENABLED")),
        "research_protocol_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_RESEARCH_PROTOCOL_V2_ENABLED")),
        "gate_model_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_GATE_MODEL_V2_ENABLED")),
        "trace_ledger_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_TRACE_LEDGER_V2_ENABLED")),
        "feedback_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_FEEDBACK_V2_ENABLED")),
        "trace_ledger_v2_implemented": True,
        "governance_gate_report_v2_implemented": True,
        "execution_audit_entity_chain_available": _execution_audit_entity_chain_available(db),
        "spec_completeness_mode": str(factory_constants.get("STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE") or "warn"),
        "feature_flags": dict(factory_constants.get("HIGH_CONFIDENCE_FEATURE_FLAGS") or {}),
        "signal_quality_registry": {},
    }

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
    """Prefer passing the current db, but tolerate scheduler stubs used in tests."""
    try:
        params = list(inspect.signature(run_once).parameters.values())
    except (TypeError, ValueError):
        return True
    return any(
        param.name == "db"
        or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
        for param in params
    )


def _call_supports_parameter(callable_obj, name: str) -> bool:
    try:
        params = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    if name in params:
        return True
    return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())


def _hydrate_factory_run_artifacts(row: dict, artifacts: list[dict[str, Any]]) -> dict:
    payload = dict(row or {})
    artifact_items = [dict(item or {}) for item in list(artifacts or []) if isinstance(item, dict)]
    artifact_by_type = {
        str(item.get("artifact_type") or "").strip(): dict(item.get("payload_json") or {})
        for item in artifact_items
        if str(item.get("artifact_type") or "").strip()
    }
    if artifact_by_type.get("research_plane"):
        payload["research_plane"] = dict(artifact_by_type.get("research_plane") or {})
    if artifact_by_type.get("governance_plane"):
        payload["governance_plane"] = dict(artifact_by_type.get("governance_plane") or {})
    if artifact_by_type.get("quality_gate"):
        payload["quality_gate"] = dict(artifact_by_type.get("quality_gate") or {})
    if artifact_by_type.get("backtest_report"):
        payload["backtest_report"] = dict(artifact_by_type.get("backtest_report") or {})
    if artifact_by_type.get("shadow_diff"):
        payload["parity_result"] = dict(artifact_by_type.get("shadow_diff") or {})
    if artifact_by_type.get("task_artifact"):
        payload["task_artifact"] = dict(artifact_by_type.get("task_artifact") or {})
    if artifact_by_type.get("candidate_artifact"):
        payload["candidate_artifact"] = dict(artifact_by_type.get("candidate_artifact") or {})
    if artifact_by_type.get("evidence_artifact"):
        payload["evidence_artifact"] = dict(artifact_by_type.get("evidence_artifact") or {})
    if artifact_by_type.get("submission_audit"):
        payload["submission_artifact"] = dict(artifact_by_type.get("submission_audit") or {})
    payload["artifacts"] = artifact_items
    payload["artifact_refs"] = list(payload.get("artifact_refs") or [
        {
            "artifact_type": item.get("artifact_type"),
            "artifact_version": item.get("artifact_version"),
            "payload_hash": item.get("payload_hash"),
            "storage_mode": item.get("storage_mode"),
        }
        for item in artifact_items
    ])
    return payload


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


async def _refresh_closure_review_after_mutation(
    db,
    strategy: dict,
    *,
    as_of: Optional[str],
    correlation_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_roles: Any = None,
) -> Optional[dict]:
    try:
        return await build_closure_review(
            db,
            strategy,
            as_of=as_of,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_roles=actor_roles,
            force_recompute=True,
        )
    except TypeError:
        return await build_closure_review(
            db,
            strategy,
            as_of=as_of,
            correlation_id=correlation_id,
            actor_id=actor_id,
            actor_roles=actor_roles,
        )
    except Exception as exc:
        logger.warning(
            "strategy_manager closure review refresh failed for %s: %s",
            strategy.get("id"),
            exc,
        )
        return None


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
    recomputed_as_of = datetime.now(timezone.utc).date().isoformat()
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
    report["recomputed"] = True
    report["as_of"] = recomputed_as_of
    await save_quality_report(db, sid, report, report_type=report_type)
    closure_review = await _refresh_closure_review_after_mutation(
        db,
        strategy,
        as_of=recomputed_as_of,
        correlation_id=str(
            dict((report.get("summary") or {})).get("correlation_id") or ""
        ).strip() or None,
    )
    return ok(
        {
            **report,
            "recomputed": True,
            "as_of": recomputed_as_of,
            "closure_review": closure_review,
        }
    )


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
    recomputed_as_of = datetime.now(timezone.utc).date().isoformat()
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
                "execution_audit_snapshot_id": replayed.get("execution_audit_snapshot_id"),
                "correlation_id": replayed.get("correlation_id"),
                "factory_run_id": replayed.get("factory_run_id"),
                "trace_id": replayed.get("trace_id"),
                "lifecycle_task_run_id": replayed.get("lifecycle_task_run_id"),
                "recomputed": bool(recheck_reports),
                "as_of": recomputed_as_of,
            }
        )
    return ok(
        {
            "count": len(items),
            "recheck_reports": recheck_reports,
            "recomputed": bool(recheck_reports),
            "as_of": recomputed_as_of,
            "items": items,
        }
    )


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

    latest_report = await get_latest_quality_report(db, sid)
    validation_report, risk_report, backtest_metrics = await _build_recheck_quality_inputs(
        db,
        strategy,
        latest_report,
    )
    from strategy_factory import StrategySubmitter

    submitter = StrategySubmitter()
    snapshot = dict((latest_report or {}).get("snapshot") or {})
    if not snapshot.get("date"):
        snapshot["date"] = datetime.now(timezone.utc).date().isoformat()
    recomputed_as_of = datetime.now(timezone.utc).date().isoformat()
    replayed = await submitter.replay_existing_submission(
        strategy,
        snapshot,
        db,
        validation_report=validation_report,
        risk_report=risk_report,
        backtest_metrics=backtest_metrics,
        latest_report=latest_report,
    )
    gate_result = dict(replayed.get("gate") or {})
    closure_review = await _refresh_closure_review_after_mutation(
        db,
        {**strategy, "status": replayed.get("status") or strategy.get("status")},
        as_of=recomputed_as_of,
        correlation_id=str(replayed.get("correlation_id") or "").strip() or None,
    )
    return ok({
        "strategy_id": sid,
        "status": replayed.get("status"),
        "quality_gate": "passed" if gate_result.get("passed") else "failed",
        "details": gate_result,
        "submission_lane": replayed.get("submission_lane"),
        "incubation_budget_track": replayed.get("incubation_budget_track"),
        "submission_action_trigger": replayed.get("submission_action_trigger"),
        "paper_lane_ready": replayed.get("paper_lane_ready"),
        "live_review_ready": replayed.get("live_review_ready"),
        "incubation_account_id": ((replayed.get("incubation_binding") or {}).get("account") or {}).get("id"),
        "vector_profile_id": (replayed.get("vector_profile") or {}).get("id"),
        "execution_audit_snapshot_id": replayed.get("execution_audit_snapshot_id"),
        "correlation_id": replayed.get("correlation_id"),
        "factory_run_id": replayed.get("factory_run_id"),
        "trace_id": replayed.get("trace_id"),
        "lifecycle_task_run_id": replayed.get("lifecycle_task_run_id"),
        "recomputed": True,
        "as_of": recomputed_as_of,
        "closure_review": closure_review,
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


async def handle_closure_review(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    return ok(
        await build_closure_review(
            db,
            strategy,
            as_of=params.get("as_of"),
            correlation_id=str(params.get("correlation_id") or "").strip() or None,
            actor_id=str(params.get("actor_id") or params.get("user_id") or "").strip() or None,
            actor_roles=params.get("actor_roles") or params.get("roles") or params.get("actor_role") or params.get("role"),
        )
    )


async def handle_factory_status(db, params: dict) -> dict:
    if _factory_status_source(params) == "db":
        return ok(await _build_db_factory_status(db, params))

    from strategy_factory import get_factory_constants, get_strategy_factory_scheduler
    from strategy_factory.application._bulk_cursor import extract_bulk_stock_cursor
    from strategy_factory.application.factory_market_views import (
        build_research_window_status,
        hydrate_full_market_topn_payload,
    )
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
    research_window = {
        **dict(
            status.get("research_window")
            or dict(status.get("last_summary") or {}).get("research_window")
            or dict(status.get("last_result") or {}).get("research_window")
            or {}
        ),
        **build_research_window_status(status.get("last_summary") or {}),
    }
    resolved_run_id = str(
        (status.get("last_result") or {}).get("run_id")
        or (latest_run or {}).get("run_id")
        or ""
    ).strip()
    full_market_topn = {}
    if resolved_run_id and hasattr(db, "get_strategy_factory_topn_snapshot"):
        full_market_topn = dict(
            await db.get_strategy_factory_topn_snapshot(resolved_run_id)
            or {}
        )
    if not full_market_topn and hasattr(db, "get_latest_strategy_factory_topn_snapshot"):
        full_market_topn = dict(await db.get_latest_strategy_factory_topn_snapshot() or {})
    if not full_market_topn:
        full_market_topn = dict(
            status.get("full_market_topn")
            or dict(status.get("last_summary") or {}).get("full_market_topn")
            or dict(status.get("last_result") or {}).get("full_market_topn")
            or {}
        )
    full_market_topn = hydrate_full_market_topn_payload(full_market_topn)
    status["research_window"] = research_window
    status["full_market_topn"] = full_market_topn
    status["execution_mode"] = (
        str(status.get("execution_mode") or "").strip()
        or str((status.get("last_result") or {}).get("execution_mode") or "").strip()
        or str((latest_run or {}).get("execution_mode") or "").strip()
        or "legacy_primary"
    )
    status["engine_version"] = (
        str(status.get("engine_version") or "").strip()
        or str((status.get("last_result") or {}).get("engine_version") or "").strip()
        or str((latest_run or {}).get("engine_version") or "").strip()
        or "strategy_factory.v2"
    )
    status["latest_parity_result"] = dict(
        status.get("latest_parity_result")
        or (status.get("last_result") or {}).get("parity_result")
        or (latest_run or {}).get("parity_result")
        or {}
    )
    status["capability_health"] = build_factory_capability_health(
        db,
        factory_constants=factory_constants,
        latest_run=status.get("last_result") or latest_run,
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
    execution_mode = params.get("execution_mode")
    if _run_once_accepts_db_arg(run_once):
        if _call_supports_parameter(run_once, "execution_mode"):
            return ok(await run_once(db=db, execution_mode=execution_mode))
        return ok(await run_once(db=db))
    return ok(await run_once())


async def handle_factory_dispatch_run(db, params: dict) -> dict:
    from strategy_factory import get_strategy_factory_scheduler

    scheduler = get_strategy_factory_scheduler()
    dispatch_run = getattr(scheduler, "dispatch_run", None)
    if not callable(dispatch_run):
        return fail("factory dispatch is unavailable")
    execution_mode = params.get("execution_mode")
    if _run_once_accepts_db_arg(dispatch_run):
        if _call_supports_parameter(dispatch_run, "execution_mode"):
            return ok(await dispatch_run(db=db, execution_mode=execution_mode))
        return ok(await dispatch_run(db=db))
    return ok(await dispatch_run())


async def handle_factory_dispatch_status(db, params: dict) -> dict:
    from strategy_factory import get_strategy_factory_scheduler

    dispatch_id = str(params.get("dispatch_id") or "").strip()
    if not dispatch_id:
        return fail("dispatch_id is required")
    scheduler = get_strategy_factory_scheduler()
    get_dispatch_status = getattr(scheduler, "get_dispatch_status", None)
    if not callable(get_dispatch_status):
        return fail("factory dispatch is unavailable")
    if _run_once_accepts_db_arg(get_dispatch_status):
        row = await get_dispatch_status(dispatch_id, db=db)
    else:
        row = await get_dispatch_status(dispatch_id)
    if not row:
        return fail(f"Factory dispatch not found: {dispatch_id}")
    return ok(row)


async def handle_factory_runs(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 10)), 1), 100)
    rows = await db.list_strategy_factory_runs(limit=limit) if hasattr(db, "list_strategy_factory_runs") else []
    items = [await refresh_factory_run_summary_quality_contract(db, row) for row in rows]
    return ok({"items": items, "count": len(rows)})


async def handle_factory_run_detail(db, params: dict) -> dict:
    from strategy_factory.application.factory_market_views import (
        build_research_window_status,
        hydrate_full_market_topn_payload,
    )

    run_id = str(params.get("run_id") or "").strip()
    if not run_id:
        return fail("run_id is required")
    row = await db.get_strategy_factory_run(run_id) if hasattr(db, "get_strategy_factory_run") else None
    if not row:
        return fail(f"Factory run not found: {run_id}")
    artifact_rows = (
        await db.list_strategy_factory_run_artifacts(run_id)
        if hasattr(db, "list_strategy_factory_run_artifacts")
        else []
    )
    hydrated_row = _hydrate_factory_run_artifacts(row, artifact_rows)
    detail = await refresh_factory_run_detail_quality_contract(db, hydrated_row)
    research_window = {
        **dict(
            detail.get("research_window")
            or dict(detail.get("summary") or {}).get("research_window")
            or {}
        ),
        **build_research_window_status(detail.get("summary") or {}),
    }
    full_market_topn = dict(
        detail.get("full_market_topn")
        or dict(detail.get("summary") or {}).get("full_market_topn")
        or {}
    )
    if hasattr(db, "get_strategy_factory_topn_snapshot"):
        topn_snapshot = await db.get_strategy_factory_topn_snapshot(run_id)
        if topn_snapshot:
            full_market_topn = {**full_market_topn, **dict(topn_snapshot or {})}
    if full_market_topn and hasattr(db, "count_strategy_factory_full_market_scores"):
        full_market_topn["score_row_count"] = await db.count_strategy_factory_full_market_scores(run_id)
    full_market_topn = hydrate_full_market_topn_payload(full_market_topn)
    detail["research_window"] = research_window
    detail["full_market_topn"] = full_market_topn
    detail["artifacts"] = artifact_rows
    detail["artifact_refs"] = list(
        detail.get("artifact_refs")
        or hydrated_row.get("artifact_refs")
        or []
    )
    return ok(detail)


async def handle_factory_topn_latest(db, params: dict) -> dict:
    from strategy_factory.application.factory_market_views import hydrate_full_market_topn_payload

    if not hasattr(db, "get_latest_strategy_factory_topn_snapshot"):
        return fail("factory Top N snapshots are unavailable")
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    snapshot = await db.get_latest_strategy_factory_topn_snapshot()
    if not snapshot:
        return ok(
            {
                "available": False,
                "snapshot": None,
                "top_scores": [],
                "score_row_count": 0,
                "requested_limit": limit,
            }
        )
    snapshot = hydrate_full_market_topn_payload(snapshot)
    run_id = str((snapshot or {}).get("run_id") or "").strip()
    top_scores = (
        await db.list_strategy_factory_full_market_scores(run_id, limit=limit)
        if run_id and hasattr(db, "list_strategy_factory_full_market_scores")
        else []
    )
    score_row_count = (
        await db.count_strategy_factory_full_market_scores(run_id)
        if run_id and hasattr(db, "count_strategy_factory_full_market_scores")
        else len(top_scores)
    )
    return ok(
        {
            "available": True,
            "snapshot": snapshot,
            "top_scores": list(top_scores or []),
            "score_row_count": int(score_row_count or 0),
            "requested_limit": limit,
        }
    )


async def handle_factory_run_topn(db, params: dict) -> dict:
    from strategy_factory.application.factory_market_views import hydrate_full_market_topn_payload

    run_id = str(params.get("run_id") or "").strip()
    if not run_id:
        return fail("run_id is required")
    if not hasattr(db, "get_strategy_factory_topn_snapshot"):
        return fail("factory Top N snapshots are unavailable")
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    snapshot = await db.get_strategy_factory_topn_snapshot(run_id)
    if not snapshot:
        return fail(f"Factory Top N snapshot not found: {run_id}")
    snapshot = hydrate_full_market_topn_payload(snapshot)
    top_scores = (
        await db.list_strategy_factory_full_market_scores(run_id, limit=limit)
        if hasattr(db, "list_strategy_factory_full_market_scores")
        else []
    )
    score_row_count = (
        await db.count_strategy_factory_full_market_scores(run_id)
        if hasattr(db, "count_strategy_factory_full_market_scores")
        else len(top_scores)
    )
    return ok(
        {
            "available": True,
            "snapshot": snapshot,
            "top_scores": list(top_scores or []),
            "score_row_count": int(score_row_count or 0),
            "requested_limit": limit,
        }
    )


async def handle_execution_audit_verification(db, params: dict) -> dict:
    if not hasattr(db, "get_execution_audit_verification"):
        return fail("execution audit verification is unavailable")
    strategy_id = str(params.get("strategy_id") or params.get("id") or "").strip() or None
    return ok(await db.get_execution_audit_verification(strategy_id=strategy_id))


async def handle_execution_audit_acceptance(db, params: dict) -> dict:
    if not hasattr(db, "run_execution_audit_acceptance"):
        return fail("execution audit acceptance is unavailable")
    strategy_id = str(params.get("strategy_id") or params.get("id") or "").strip() or None
    backfill = bool(params.get("backfill", True))
    return ok(
        await db.run_execution_audit_acceptance(
            strategy_id=strategy_id,
            backfill=backfill,
        )
    )


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
