"""Strategy manager CRUD action handlers."""

import asyncio
import os
import random
import time
from uuid import uuid4

from ...storage import get_db
from ...utils import fail, ok
from .strategy_mgr_helpers import (
    build_incubation_overview,
    compute_nav_series,
    get_latest_quality_report,
    list_quality_reports,
    normalize_quality_report_contract,
    normalize_status_alias,
    normalize_time_filter,
    update_status,
)

import logging

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


async def _resolved(value):
    return value


def _resolve_strategy_status_filter(raw_status, *, default: str = "visible"):
    raw = str(raw_status or default).strip()
    if not raw:
        raw = default
    tokens = [item.strip() for item in raw.replace("|", ",").split(",") if item.strip()]
    lowered = [token.lower() for token in tokens]
    if any(token in {"all", "*"} for token in lowered):
        return None
    if len(lowered) == 1 and lowered[0] in {"visible", "active", "market", "marketplace"}:
        return ["incubating", "listed"]
    normalized = [normalize_status_alias(token) for token in tokens]
    normalized = [token for token in normalized if token]
    if not normalized:
        return ["incubating", "listed"]
    return normalized[0] if len(normalized) == 1 else normalized


async def _load_similar_vector_profiles(db, strategy_id: str) -> list:
    try:
        from ...services.vector_platform import get_strategy_vector_platform
        return await get_strategy_vector_platform().find_similar_profiles(db, strategy_id, limit=5)
    except Exception as exc:
        logger.warning("strategy_manager.detail similar profiles failed for %s: %s", strategy_id, exc)
        return []


async def _load_vector_profiles(db, strategy_id: str, *, limit: int = 3) -> list:
    try:
        from ...services.vector_platform import get_strategy_vector_platform

        return await get_strategy_vector_platform().list_profiles(
            db,
            strategy_id=strategy_id,
            limit=max(1, min(int(limit or 3), 20)),
        )
    except Exception as exc:
        logger.warning("strategy_manager.detail vector profiles failed for %s: %s", strategy_id, exc)
        if hasattr(db, "list_strategy_vector_profiles"):
            return await db.list_strategy_vector_profiles(strategy_id=strategy_id, limit=max(1, min(int(limit or 3), 20)))
        return []


async def _load_latest_vector_index_snapshot(db, index_name: str = "strategy_behavior") -> dict | None:
    try:
        from ...services.vector_platform import get_strategy_vector_platform

        rows = await get_strategy_vector_platform().list_index_snapshots(
            db,
            index_name=index_name,
            limit=1,
        )
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("strategy_manager.detail latest vector snapshot failed for %s: %s", index_name, exc)
        if hasattr(db, "get_latest_strategy_vector_index_snapshot"):
            return await db.get_latest_strategy_vector_index_snapshot(index_name)
        return None


def _extract_strategy_market_summary_value(strategy: dict, key: str):
    value = strategy.get(key)
    if value not in (None, ""):
        return value
    params = strategy.get("params")
    if isinstance(params, dict):
        return params.get(key)
    return None


def _build_strategy_market_summary(strategy: dict, *, metrics: dict | None = None) -> dict:
    summary = {
        "id": strategy.get("id"),
        "name": strategy.get("name"),
        "strategy_type": strategy.get("strategy_type"),
        "description": strategy.get("description"),
        "status": strategy.get("status"),
        "subscriber_count": strategy.get("subscriber_count"),
        "avg_rating": strategy.get("avg_rating"),
        "review_count": strategy.get("review_count"),
        "sample_start_date": _extract_strategy_market_summary_value(strategy, "sample_start_date"),
        "sample_end_date": _extract_strategy_market_summary_value(strategy, "sample_end_date"),
        "turnover_rate": _extract_strategy_market_summary_value(strategy, "turnover_rate"),
        "capacity": _extract_strategy_market_summary_value(strategy, "capacity"),
        "capacity_label": _extract_strategy_market_summary_value(strategy, "capacity_label"),
    }

    if metrics:
        metric_summary = {
            "total_return": metrics.get("total_return"),
            "annual_return": metrics.get("annual_return"),
            "sharpe_ratio": metrics.get("sharpe_ratio"),
            "max_drawdown": metrics.get("max_drawdown"),
            "win_rate": metrics.get("win_rate"),
        }
        summary["metrics"] = metric_summary
        summary["total_return"] = metric_summary["total_return"]
        summary["annual_return"] = metric_summary["annual_return"]
        summary["sharpe_ratio"] = metric_summary["sharpe_ratio"]
        summary["max_drawdown"] = metric_summary["max_drawdown"]
        summary["win_rate"] = metric_summary["win_rate"]

    return {key: value for key, value in summary.items() if value is not None or key in {"id", "name"}}


async def _enrich_rank_strategy(db, strategy: dict, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        metrics_list = await db.get_strategy_metrics(strategy["id"])

    all_period = next((m for m in metrics_list if m.get("period") == "all"), {})
    return _build_strategy_market_summary(strategy, metrics=all_period)


async def handle_help(db, params: dict) -> dict:
    return ok({
        "actions": [
            "create", "publish", "archive", "list", "detail",
            "update_metrics", "review", "subscribe", "unsubscribe",
            "my_subscriptions", "rank", "submit", "capabilities", "daily_snapshot", "daily_snapshots",
            "incubation_accounts", "incubation_metrics", "paper_account", "paper_orders", "paper_nav", "incubation_sync_run", "risk_events", "risk_snapshots", "risk_scan_run", "risk_recovery", "resolve_risk_event", "runtime_alerts", "runtime_alert_dispatch_run", "runtime_alert_ack",
            "vector_profiles", "vector_indexes", "vector_reconcile", "vector_rebuild", "vector_health", "vector_cleanup",
            "ai_generate", "ai_experiments", "task_runs", "domain_events", "domain_projection", "domain_projection_snapshot", "domain_projection_rebuild",
            "runtime_control", "runtime_control_set", "promotion_reviews", "promotion_review_run",
            "runtime_cycle_run", "runtime_cycle_status", "lifecycle_scan", "get_signals", "get_forward_returns", "get_signal_stats",
            "factory_status", "factory_run_once", "factory_runs", "factory_run_detail", "execution_audit_verification", "review_report", "review_report_recheck", "submission_replay", "events",
            "incubation_overview", "help",
        ],
        "description": "策略超市管理器（含生命周期与前向信号跟踪）",
    })


async def handle_create(db, params: dict) -> dict:
    name = str(params.get("name", "")).strip()
    if not name:
        return fail("name is required")
    strategy_type = str(params.get("strategy_type") or params.get("type") or "custom").strip()
    sid = f"strat_{int(time.time())}_{uuid4().hex[:8]}"
    data = {
        "id": sid,
        "name": name,
        "description": params.get("description", ""),
        "author_id": str(params.get("author_id") or params.get("user_id") or "default"),
        "strategy_type": strategy_type,
        "params": params.get("params") or {},
        "factor_weights": params.get("factor_weights") or {},
        "status": "draft",
        "tags": params.get("tags") or [],
        "backtest_artifact_id": params.get("backtest_artifact_id"),
    }
    result = await db.save_strategy(data)
    return ok({"strategy_id": sid, "strategy": result})


async def handle_publish(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    await update_status(db, sid, "listed", actor_id="strategy_manager", reason="manual_publish")
    return ok({"strategy_id": sid, "status": "listed"})


async def handle_archive(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    await update_status(db, sid, "archived", actor_id="strategy_manager", reason="manual_archive")
    return ok({"strategy_id": sid, "status": "archived"})


async def handle_list(db, params: dict) -> dict:
    status = _resolve_strategy_status_filter(params.get("status"), default="visible")
    strategy_type = params.get("strategy_type") or params.get("type")
    limit = min(max(int(params.get("limit", 20)), 1), 100)
    offset = max(int(params.get("offset", 0)), 0)
    rows = await db.list_strategies(status, strategy_type, limit, offset)
    return ok({"strategies": [_build_strategy_market_summary(row) for row in rows], "count": len(rows)})


async def handle_detail(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")

    user_id = str(params.get("user_id", "default"))
    metrics, reviews, is_sub, latest_quality_report, incubation_overview, incubation_account, incubation_metric, risk_events, latest_runtime_risk_snapshot, runtime_control, runtime_alerts, latest_promotion_review, latest_projection_snapshot, latest_vector_index_snapshot, latest_incubation_pipeline_snapshot, vector_profiles, similar_vector_profiles, domain_events, task_runs, nav_series, signal_event_snapshots = await asyncio.gather(
        db.get_strategy_metrics(sid),
        db.get_reviews(sid, limit=10),
        db.is_subscribed(sid, user_id),
        get_latest_quality_report(db, sid),
        _resolve_strategy_incubation_overview(db, strategy),
        db.get_strategy_incubation_account(sid) if hasattr(db, "get_strategy_incubation_account") else _resolved(None),
        db.get_latest_strategy_incubation_metric(sid) if hasattr(db, "get_latest_strategy_incubation_metric") else _resolved(None),
        db.list_strategy_runtime_risk_events(strategy_id=sid, status="open", limit=5) if hasattr(db, "list_strategy_runtime_risk_events") else _resolved([]),
        db.get_latest_strategy_runtime_risk_snapshot(sid) if hasattr(db, "get_latest_strategy_runtime_risk_snapshot") else _resolved(None),
        db.get_strategy_runtime_control(sid) if hasattr(db, "get_strategy_runtime_control") else _resolved(None),
        db.list_strategy_runtime_alerts(strategy_id=sid, status="open_or_ack", limit=5) if hasattr(db, "list_strategy_runtime_alerts") else _resolved([]),
        db.get_latest_strategy_promotion_review(sid) if hasattr(db, "get_latest_strategy_promotion_review") else _resolved(None),
        db.get_latest_strategy_projection_snapshot(sid) if hasattr(db, "get_latest_strategy_projection_snapshot") else _resolved(None),
        _load_latest_vector_index_snapshot(db, 'strategy_behavior'),
        db.get_latest_strategy_incubation_pipeline_snapshot(sid) if hasattr(db, "get_latest_strategy_incubation_pipeline_snapshot") else _resolved(None),
        _load_vector_profiles(db, sid, limit=3),
        _load_similar_vector_profiles(db, sid),
        db.list_strategy_domain_events(strategy_id=sid, limit=5) if hasattr(db, "list_strategy_domain_events") else _resolved([]),
        db.list_strategy_task_runs(strategy_id=sid, limit=5) if hasattr(db, "list_strategy_task_runs") else _resolved([]),
        compute_nav_series(db, sid),
        db.list_strategy_signal_event_snapshots(strategy_id=sid, latest_only=True, limit=10) if hasattr(db, "list_strategy_signal_event_snapshots") else _resolved([]),
    )
    metric_noise_enabled = os.getenv("STRATEGY_METRIC_NOISE_ENABLED", "1").strip() not in ("0", "false", "no")
    if not is_sub and metrics and metric_noise_enabled:
        noise = 1 + random.uniform(-0.001, 0.001)
        for m in metrics:
            for key in ("total_return", "annual_return", "sharpe_ratio", "calmar_ratio"):
                if m.get(key) is not None:
                    m[key] = round(float(m[key]) * noise, 6)
            m["approximate"] = True
    latest_quality_report = normalize_quality_report_contract(
        latest_quality_report,
        strategy_id=sid,
        strategy_type=strategy.get("strategy_type"),
        default_review_source="strategy_manager.detail",
    )

    return ok({
        "strategy": strategy, "metrics": metrics, "reviews": reviews,
        "nav_series": nav_series,
        "latest_quality_report": latest_quality_report,
        "incubation_overview": incubation_overview,
        "incubation_account": incubation_account,
        "latest_incubation_metric": incubation_metric,
        "latest_promotion_review": latest_promotion_review,
        "latest_projection_snapshot": latest_projection_snapshot,
        "latest_vector_index_snapshot": latest_vector_index_snapshot,
        "latest_incubation_pipeline_snapshot": latest_incubation_pipeline_snapshot,
        "runtime_control": runtime_control,
        "runtime_alerts": runtime_alerts,
        "latest_runtime_risk_snapshot": latest_runtime_risk_snapshot,
        "signal_event_snapshots": signal_event_snapshots,
        "open_risk_events": risk_events,
        "vector_profiles": vector_profiles,
        "similar_vector_profiles": similar_vector_profiles,
        "domain_events": domain_events,
        "task_runs": task_runs,
    })


async def _resolve_strategy_incubation_overview(db, strategy: dict) -> dict | None:
    try:
        return await build_incubation_overview(db, strategy)
    except Exception as exc:
        logger.warning("strategy_manager.detail incubation overview failed for %s: %s", strategy.get("id"), exc)
        return None


async def handle_review_report(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    limit = min(max(int(params.get("limit", 10)), 1), 50)
    strategy = await db.get_strategy(sid) if hasattr(db, "get_strategy") else None
    strategy_type = str((strategy or {}).get("strategy_type") or "").strip() or None
    reports = [
        normalize_quality_report_contract(
            report,
            strategy_id=sid,
            strategy_type=strategy_type,
            default_review_source="strategy_manager.review_report",
        )
        for report in await list_quality_reports(db, sid, limit=limit)
    ]
    latest = reports[0] if reports else None
    return ok({**(latest or {}), "reports": reports})


async def handle_events(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    rows = []
    if hasattr(db, "list_strategy_status_events"):
        try:
            rows = await db.list_strategy_status_events(
                sid,
                event_type=str(params.get("event_type") or "").strip() or None,
                from_status=str(params.get("from_status") or "").strip() or None,
                to_status=str(params.get("to_status") or "").strip() or None,
                actor_id=str(params.get("actor_id") or "").strip() or None,
                start_time=normalize_time_filter(params.get("start_time")),
                end_time=normalize_time_filter(params.get("end_time"), is_end=True),
                limit=limit,
            )
        except TypeError:
            rows = await db.list_strategy_status_events(sid, limit=limit)
    return ok({"events": rows, "count": len(rows)})


async def handle_update_metrics(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    metrics = params.get("metrics") or {}
    period = str(params.get("period", "all"))
    await db.save_strategy_metrics(sid, period, metrics)
    return ok({"strategy_id": sid, "period": period, "updated": True})


async def handle_review(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    user_id = str(params.get("user_id", "default"))
    rating = int(params.get("rating", 3))
    comment = params.get("comment")
    if not sid:
        return fail("strategy_id is required")
    if rating < 1 or rating > 5:
        return fail("rating must be 1-5")
    await db.save_review(sid, user_id, rating, comment)
    return ok({"strategy_id": sid, "user_id": user_id, "rating": rating})


async def handle_subscribe(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    user_id = str(params.get("user_id", "default"))
    if not sid:
        return fail("strategy_id is required")
    await db.subscribe_strategy(sid, user_id)
    return ok({"strategy_id": sid, "user_id": user_id, "subscribed": True})


async def handle_unsubscribe(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    user_id = str(params.get("user_id", "default"))
    if not sid:
        return fail("strategy_id is required")
    await db.unsubscribe_strategy(sid, user_id)
    return ok({"strategy_id": sid, "user_id": user_id, "unsubscribed": True})


async def handle_my_subscriptions(db, params: dict) -> dict:
    user_id = str(params.get("user_id", "default"))
    rows = await db.list_user_subscriptions(user_id)
    return ok({"subscriptions": rows, "count": len(rows)})


async def handle_rank(db, params: dict) -> dict:
    from ...services.ranking import rrf_rank

    status = _resolve_strategy_status_filter(params.get("status"), default="visible")
    strategy_type = params.get("strategy_type") or params.get("type")
    limit = min(max(int(params.get("limit", 50)), 1), 200)
    offset = max(int(params.get("offset", 0)), 0)
    rank_keys = params.get("rank_keys")

    fetch_limit = limit + offset
    strategies = await db.list_strategies(status, strategy_type, fetch_limit, 0)
    if not strategies:
        return ok({"strategies": [], "count": 0, "offset": offset, "limit": limit})

    semaphore = asyncio.Semaphore(8)
    enriched = await asyncio.gather(*[
        _enrich_rank_strategy(db, strategy, semaphore)
        for strategy in strategies
    ])

    ranked = rrf_rank(enriched, rank_keys)
    page = ranked[offset:offset + limit]
    return ok({"strategies": page, "count": len(ranked), "offset": offset, "limit": limit})


async def handle_capabilities(db, params: dict) -> dict:
    from strategy_factory import get_factory_constants

    factory_constants = get_factory_constants()
    high_confidence_feature_flags = dict(factory_constants.get("HIGH_CONFIDENCE_FEATURE_FLAGS") or {})
    return ok({
        "daily_snapshot": hasattr(db, "get_daily_snapshot") and hasattr(db, "list_daily_snapshots"),
        "factory_runs": hasattr(db, "save_strategy_factory_run") and hasattr(db, "get_latest_strategy_factory_run"),
        "factory_bulk_lane": hasattr(db, "list_stock_universe") and hasattr(db, "save_strategy_factory_run"),
        "factory_bulk_lane_enabled": bool(factory_constants.get("STOCK_STRATEGY_MATRIX_ENABLED")),
        "factory_pre_gate_enabled": bool(factory_constants.get("FACTORY_PRE_GATE_ENABLED")),
        "high_confidence_enabled": bool(factory_constants.get("STRATEGY_FACTORY_HIGH_CONFIDENCE_ENABLED")),
        "evidence_contract_enabled": bool(factory_constants.get("STRATEGY_FACTORY_EVIDENCE_CONTRACT_ENABLED")),
        "confidence_diagnostics_enabled": bool(
            factory_constants.get("STRATEGY_FACTORY_CONFIDENCE_DIAGNOSTICS_ENABLED")
        ),
        "execution_audit_enabled": bool(factory_constants.get("STRATEGY_FACTORY_EXECUTION_AUDIT_ENABLED")),
        "execution_audit_verification": hasattr(db, "get_execution_audit_verification"),
        "quality_ui_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_QUALITY_UI_V2_ENABLED")),
        "research_protocol_v2_enabled": bool(
            factory_constants.get("STRATEGY_FACTORY_RESEARCH_PROTOCOL_V2_ENABLED")
        ),
        "gate_model_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_GATE_MODEL_V2_ENABLED")),
        "trace_ledger_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_TRACE_LEDGER_V2_ENABLED")),
        "feedback_v2_enabled": bool(factory_constants.get("STRATEGY_FACTORY_FEEDBACK_V2_ENABLED")),
        "trace_ledger_v2_implemented": True,
        "governance_gate_report_v2_implemented": True,
        "execution_audit_entity_chain_available": _execution_audit_entity_chain_available(db),
        "spec_completeness_mode": str(
            factory_constants.get("STRATEGY_FACTORY_SPEC_COMPLETENESS_MODE") or "warn"
        ),
        "high_confidence_feature_flags": high_confidence_feature_flags,
        "signal_quality_registry": _load_signal_quality_registry_snapshot(),
        "paper_incubation": hasattr(db, "save_strategy_incubation_account") and hasattr(db, "save_strategy_incubation_metric"),
        "paper_trading": hasattr(db, "save_paper_account") and hasattr(db, "save_paper_order") and hasattr(db, "get_paper_nav_rows"),
        "incubation_pipeline": hasattr(db, "save_strategy_incubation_pipeline_snapshot") and hasattr(db, "list_strategy_incubation_metrics"),
        "runtime_risk": hasattr(db, "save_strategy_runtime_risk_event"),
        "risk_snapshots": hasattr(db, "save_strategy_runtime_risk_snapshot") and hasattr(db, "list_strategy_runtime_risk_snapshots"),
        "risk_recovery": hasattr(db, "save_strategy_runtime_risk_snapshot") and hasattr(db, "save_strategy_runtime_control"),
        "execution_risk": hasattr(db, "save_strategy_runtime_risk_event"),
        "runtime_controls": hasattr(db, "save_strategy_runtime_control") and hasattr(db, "get_strategy_runtime_control"),
        "runtime_alerting": hasattr(db, "save_strategy_runtime_alert") and hasattr(db, "list_strategy_runtime_alerts"),
        "signal_event_snapshots": hasattr(db, "save_strategy_signal_event_snapshot") and hasattr(db, "list_strategy_signal_event_snapshots"),
        "promotion_pipeline": hasattr(db, "save_strategy_promotion_review") and hasattr(db, "get_latest_strategy_promotion_review"),
        "projection_snapshots": hasattr(db, "save_strategy_projection_snapshot") and hasattr(db, "get_latest_strategy_projection_snapshot"),
        "event_replay": hasattr(db, "save_strategy_projection_snapshot") and hasattr(db, "list_strategy_domain_events"),
        "vector_platform": hasattr(db, "save_strategy_vector_profile") and hasattr(db, "save_vector_index_registry"),
        "vector_governance": hasattr(db, "save_vector_index_registry") and hasattr(db, "list_strategy_vector_profiles"),
        "persistent_vector_index": hasattr(db, "save_strategy_vector_index_snapshot") and hasattr(db, "replace_strategy_vector_index_items"),
        "ann_vector_search": hasattr(db, "list_strategy_vector_index_items") and hasattr(db, "save_strategy_vector_index_snapshot"),
        "vector_health": hasattr(db, "get_strategy_vector_health") or (
            hasattr(db, "list_vector_collections") and hasattr(db, "list_vector_index_snapshots")
        ),
        "vector_cleanup": hasattr(db, "cleanup_strategy_vector_history") or hasattr(db, "cleanup_vector_collection_history"),
        "ai_generation": hasattr(db, "save_strategy_generation_experiment") and hasattr(db, "save_strategy_task_run"),
        "multi_agent_review": hasattr(db, "save_strategy_generation_experiment"),
        "quality_governance": hasattr(db, "save_strategy_quality_report") and hasattr(db, "list_strategy_status_events"),
        "domain_events": hasattr(db, "save_strategy_domain_event") and hasattr(db, "list_strategy_domain_events"),
        "domain_projection": hasattr(db, "list_strategy_status_events") and hasattr(db, "list_strategy_domain_events"),
        "runtime_cycle": hasattr(db, "save_strategy_task_run") and hasattr(db, "save_strategy_incubation_metric"),
    })


async def handle_daily_snapshot(db, params: dict) -> dict:
    snapshot_date = params.get("snapshot_date")
    row = await db.get_daily_snapshot(snapshot_date) if hasattr(db, "get_daily_snapshot") else None
    if not row:
        return fail("daily snapshot not found")
    return ok(row)


async def handle_daily_snapshots(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    rows = await db.list_daily_snapshots(
        limit=limit,
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
    ) if hasattr(db, "list_daily_snapshots") else []
    return ok({"items": rows, "count": len(rows)})


async def handle_get_signals(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    user_id = str(params.get("user_id", "default"))
    limit = min(max(int(params.get("limit", 100)), 1), 500)
    is_sub = await db.is_subscribed(sid, user_id)
    if is_sub:
        signals = await db.get_signals(sid, limit=limit)
    else:
        signals = await db.get_signals_public(sid, limit=limit)
    return ok({"signals": signals, "count": len(signals), "subscriber": is_sub})


async def handle_get_forward_returns(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    extra_kwargs = {}
    if params.get("lookback_days") is not None:
        extra_kwargs["lookback_days"] = int(params.get("lookback_days"))
    if params.get("eps") is not None:
        extra_kwargs["eps"] = float(params.get("eps"))
    stats = await db.get_signal_stats(sid, **extra_kwargs)
    return ok(stats)


async def handle_get_signal_stats(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    extra_kwargs = {}
    if params.get("lookback_days") is not None:
        extra_kwargs["lookback_days"] = int(params.get("lookback_days"))
    if params.get("eps") is not None:
        extra_kwargs["eps"] = float(params.get("eps"))
    stats = await db.get_signal_stats(sid, **extra_kwargs)
    return ok(stats)
