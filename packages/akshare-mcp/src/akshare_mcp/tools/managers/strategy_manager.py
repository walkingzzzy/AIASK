"""Strategy marketplace manager: CRUD, ranking, reviews, subscriptions, lifecycle.

This module is the public entry-point.  Heavy handler logic lives in
``strategy_mgr_crud``, ``strategy_mgr_lifecycle``, ``strategy_mgr_incubation``,
``strategy_mgr_runtime``, and ``strategy_mgr_helpers``.
"""

import json
import logging

from ...storage import get_db
from ...utils import fail, ok

# ── Sub-module handler imports ───────────────────────────────────────────────
from .strategy_mgr_crud import (
    handle_archive,
    handle_capabilities,
    handle_create,
    handle_daily_snapshot,
    handle_daily_snapshots,
    handle_detail,
    handle_events,
    handle_get_forward_returns,
    handle_get_signal_stats,
    handle_get_signals,
    handle_help,
    handle_list,
    handle_my_subscriptions,
    handle_publish,
    handle_rank,
    handle_review,
    handle_review_report,
    handle_subscribe,
    handle_unsubscribe,
    handle_update_metrics,
)
from .strategy_mgr_lifecycle import (
    handle_factory_run_detail,
    handle_factory_run_once,
    handle_factory_runs,
    handle_factory_status,
    handle_incubation_overview,
    handle_lifecycle_scan,
    handle_review_report_recheck,
    handle_submit,
)
from .strategy_mgr_incubation import (
    handle_incubation_accounts,
    handle_incubation_metrics,
    handle_incubation_pipeline,
    handle_incubation_pipeline_run,
    handle_incubation_sync_run,
    handle_paper_account,
    handle_paper_nav,
    handle_paper_orders,
)
from .strategy_mgr_runtime import (
    handle_domain_events,
    handle_domain_projection,
    handle_domain_projection_rebuild,
    handle_domain_projection_snapshot,
    handle_promotion_review_run,
    handle_promotion_reviews,
    handle_resolve_risk_event,
    handle_risk_events,
    handle_risk_recovery,
    handle_risk_scan_run,
    handle_risk_snapshots,
    handle_runtime_alert_ack,
    handle_runtime_alert_dispatch_run,
    handle_runtime_alerts,
    handle_runtime_control,
    handle_runtime_control_set,
    handle_runtime_cycle_run,
    handle_runtime_cycle_status,
)
from .strategy_mgr_helpers import (
    parse_bool,
)

logger = logging.getLogger(__name__)


# ── Action dispatch table ────────────────────────────────────────────────────
# Maps action name -> async handler(db, params) -> dict
# Vector / AI actions are defined inline below because they're short and
# tightly coupled to register_strategy_manager.

ACTION_HANDLERS: dict[str, ...] = {
    # CRUD (strategy_mgr_crud)
    "help": handle_help,
    "create": handle_create,
    "publish": handle_publish,
    "archive": handle_archive,
    "list": handle_list,
    "detail": handle_detail,
    "review_report": handle_review_report,
    "events": handle_events,
    "update_metrics": handle_update_metrics,
    "review": handle_review,
    "subscribe": handle_subscribe,
    "unsubscribe": handle_unsubscribe,
    "my_subscriptions": handle_my_subscriptions,
    "rank": handle_rank,
    "capabilities": handle_capabilities,
    "daily_snapshot": handle_daily_snapshot,
    "daily_snapshots": handle_daily_snapshots,
    "get_signals": handle_get_signals,
    "get_forward_returns": handle_get_forward_returns,
    "get_signal_stats": handle_get_signal_stats,
    # Lifecycle (strategy_mgr_lifecycle)
    "review_report_recheck": handle_review_report_recheck,
    "submit": handle_submit,
    "lifecycle_scan": handle_lifecycle_scan,
    "incubation_overview": handle_incubation_overview,
    "factory_status": handle_factory_status,
    "factory_run_once": handle_factory_run_once,
    "factory_runs": handle_factory_runs,
    "factory_run_detail": handle_factory_run_detail,
    # Incubation (strategy_mgr_incubation)
    "incubation_accounts": handle_incubation_accounts,
    "incubation_metrics": handle_incubation_metrics,
    "paper_account": handle_paper_account,
    "paper_orders": handle_paper_orders,
    "paper_nav": handle_paper_nav,
    "incubation_sync_run": handle_incubation_sync_run,
    "incubation_pipeline": handle_incubation_pipeline,
    "incubation_pipeline_run": handle_incubation_pipeline_run,
    # Runtime (strategy_mgr_runtime)
    "risk_events": handle_risk_events,
    "risk_snapshots": handle_risk_snapshots,
    "risk_scan_run": handle_risk_scan_run,
    "risk_recovery": handle_risk_recovery,
    "resolve_risk_event": handle_resolve_risk_event,
    "runtime_alerts": handle_runtime_alerts,
    "runtime_alert_dispatch_run": handle_runtime_alert_dispatch_run,
    "runtime_alert_ack": handle_runtime_alert_ack,
    "runtime_control": handle_runtime_control,
    "runtime_control_set": handle_runtime_control_set,
    "promotion_reviews": handle_promotion_reviews,
    "promotion_review_run": handle_promotion_review_run,
    "runtime_cycle_status": handle_runtime_cycle_status,
    "runtime_cycle_run": handle_runtime_cycle_run,
    "domain_events": handle_domain_events,
    "domain_projection": handle_domain_projection,
    "domain_projection_snapshot": handle_domain_projection_snapshot,
    "domain_projection_rebuild": handle_domain_projection_rebuild,
}


# ── Vector / AI inline handlers (kept here to avoid circular deps) ───────────

async def _handle_vector_profiles(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip() or None
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    if params.get("similar_to"):
        from ...services.vector_platform import get_strategy_vector_platform
        rows = await get_strategy_vector_platform().find_similar_profiles(db, str(params.get("similar_to")), limit=limit)
    else:
        rows = await db.list_strategy_vector_profiles(strategy_id=sid, profile_type=params.get("profile_type"), limit=limit) if hasattr(db, "list_strategy_vector_profiles") else []
    return ok({"items": rows, "count": len(rows)})


async def _handle_vector_indexes(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    rows = await db.list_vector_index_registry(index_name=params.get("index_name"), status=params.get("status"), limit=limit) if hasattr(db, "list_vector_index_registry") else []
    return ok({"items": rows, "count": len(rows)})


async def _handle_vector_index_snapshots(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    rows = await db.list_strategy_vector_index_snapshots(
        index_name=(str(params.get("index_name") or "").strip() or None),
        index_version=(str(params.get("index_version") or "").strip() or None),
        status=(str(params.get("status") or "").strip() or None),
        limit=limit,
    ) if hasattr(db, "list_strategy_vector_index_snapshots") else []
    latest = rows[0] if rows else None
    return ok({"items": rows, "count": len(rows), "latest": latest})


async def _handle_vector_ann_search(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("similar_to") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    limit = min(max(int(params.get("limit", 10)), 1), 50)
    from ...services.vector_platform import get_strategy_vector_platform
    rows = await get_strategy_vector_platform().ann_search_profiles(
        db,
        sid,
        profile_type=str(params.get("profile_type") or 'behavior'),
        limit=limit,
        candidate_limit=min(max(int(params.get("candidate_limit", 80)), 1), 500),
        index_name=(str(params.get("index_name") or "").strip() or None),
        index_version=(str(params.get("index_version") or "").strip() or None),
    )
    return ok({"items": rows, "count": len(rows)})


async def _handle_vector_reconcile(db, params: dict) -> dict:
    from ...services.vector_governance import get_strategy_vector_governance_service
    result = await get_strategy_vector_governance_service().reconcile_registry(
        db,
        index_name=(str(params.get("index_name") or "").strip() or None),
        profile_type=(str(params.get("profile_type") or "").strip() or None),
        limit_profiles=min(max(int(params.get("limit_profiles", 2000)), 1), 5000),
    )
    return ok(result)


async def _handle_vector_rebuild(db, params: dict) -> dict:
    from ...services.vector_governance import get_strategy_vector_governance_service
    statuses = params.get("statuses") or ['incubating', 'listed']
    if isinstance(statuses, str):
        statuses = [item.strip() for item in statuses.split(',') if item.strip()]
    result = await get_strategy_vector_governance_service().rebuild_index(
        db,
        index_name=str(params.get("index_name") or 'strategy_behavior'),
        index_version=(str(params.get("index_version") or "").strip() or None),
        statuses=list(statuses or ['incubating', 'listed']),
        limit=min(max(int(params.get("limit", 200)), 1), 1000),
        profile_type=str(params.get("profile_type") or 'behavior'),
        vector_method=(str(params.get("vector_method") or "").strip() or None),
    )
    return ok(result)


async def _handle_vector_health(db, params: dict) -> dict:
    if not hasattr(db, "get_strategy_vector_health"):
        return fail("vector health unsupported")
    result = await db.get_strategy_vector_health(
        index_name=str(params.get("index_name") or 'strategy_behavior'),
        limit_versions=min(max(int(params.get("limit_versions", 20)), 1), 200),
        include_hnsw_indexes=parse_bool(params.get("include_hnsw_indexes"), False),
    )
    return ok(result)


async def _handle_vector_cleanup(db, params: dict) -> dict:
    if not hasattr(db, "cleanup_strategy_vector_history"):
        return fail("vector cleanup unsupported")
    protect_versions = params.get("protect_versions") or []
    if isinstance(protect_versions, str):
        protect_versions = [item.strip() for item in protect_versions.split(',') if item.strip()]
    result = await db.cleanup_strategy_vector_history(
        index_name=str(params.get("index_name") or 'strategy_behavior'),
        keep_versions=max(int(params.get("keep_versions", 1)), 0),
        dry_run=parse_bool(params.get("dry_run"), True),
        cleanup_hnsw=parse_bool(params.get("cleanup_hnsw"), True),
        limit_versions=min(max(int(params.get("limit_versions", 200)), 1), 500),
        protect_versions=protect_versions,
    )
    return ok(result)


async def _handle_ai_generate(db, params: dict) -> dict:
    from ...services.strategy_autonomy import get_strategy_autonomy_service
    result = await get_strategy_autonomy_service().run_cycle(
        db,
        snapshot=await db.get_daily_snapshot() if hasattr(db, "get_daily_snapshot") else None,
        limit=min(max(int(params.get("limit", 3)), 1), 10),
        source="strategy_manager",
        parent_strategy_id=(str(params.get("parent_strategy_id") or "").strip() or None),
        auto_submit=bool(params.get("auto_submit")),
    )
    return ok(result)


async def _handle_ai_experiments(db, params: dict) -> dict:
    experiment_id = str(params.get("experiment_id") or "").strip()
    if experiment_id:
        row = await db.get_strategy_generation_experiment(experiment_id) if hasattr(db, "get_strategy_generation_experiment") else None
        if not row:
            return fail(f"experiment not found: {experiment_id}")
        return ok(row)
    limit = min(max(int(params.get("limit", 20)), 1), 200)
    rows = await db.list_strategy_generation_experiments(
        strategy_id=(str(params.get("strategy_id") or params.get("id") or "").strip() or None),
        parent_strategy_id=(str(params.get("parent_strategy_id") or "").strip() or None),
        generated_strategy_id=(str(params.get("generated_strategy_id") or "").strip() or None),
        task_run_id=(int(params.get("task_run_id")) if params.get("task_run_id") is not None else None),
        status=(str(params.get("status") or "").strip() or None),
        source=(str(params.get("source") or "").strip() or None),
        limit=limit,
    ) if hasattr(db, "list_strategy_generation_experiments") else []
    return ok({"items": rows, "count": len(rows)})


async def _handle_task_runs(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 20)), 1), 500)
    rows = await db.list_strategy_task_runs(
        strategy_id=(str(params.get("strategy_id") or params.get("id") or "").strip() or None),
        task_name=(str(params.get("task_name") or "").strip() or None),
        task_scope=(str(params.get("task_scope") or "").strip() or None),
        status=(str(params.get("status") or "").strip() or None),
        limit=limit,
    ) if hasattr(db, "list_strategy_task_runs") else []
    return ok({"items": rows, "count": len(rows)})


# Register vector/AI handlers into dispatch table
ACTION_HANDLERS.update({
    "vector_profiles": _handle_vector_profiles,
    "vector_indexes": _handle_vector_indexes,
    "vector_index_snapshots": _handle_vector_index_snapshots,
    "vector_ann_search": _handle_vector_ann_search,
    "vector_reconcile": _handle_vector_reconcile,
    "vector_rebuild": _handle_vector_rebuild,
    "vector_health": _handle_vector_health,
    "vector_cleanup": _handle_vector_cleanup,
    "ai_generate": _handle_ai_generate,
    "ai_experiments": _handle_ai_experiments,
    "task_runs": _handle_task_runs,
})


# ── MCP tool registration ───────────────────────────────────────────────────

def register_strategy_manager(mcp):
    @mcp.tool()
    async def strategy_manager(action: str, kwargs: str = "{}") -> dict:
        """策略超市管理器 — 创建/发布/排名/评价/订阅/生命周期管理。

        Actions: create, publish, archive, list, detail, update_metrics, review, subscribe, unsubscribe, my_subscriptions, rank, submit, lifecycle_scan, get_signals, get_forward_returns, get_signal_stats, factory_status, factory_run_once, factory_runs, factory_run_detail, review_report, review_report_recheck, events, incubation_overview, vector_health, vector_cleanup, help
        """
        try:
            params = json.loads(kwargs) if isinstance(kwargs, str) else (kwargs or {})
        except Exception:
            params = {}

        db = get_db()

        handler = ACTION_HANDLERS.get(action)
        if handler is not None:
            return await handler(db, params)

        return fail(f"Unknown action: {action}. Use action='help' for available actions.")


# ── Backward-compatible re-exports ───────────────────────────────────────────
# External services do ``from ..tools.managers.strategy_manager import _xxx``.
# We re-export the underscore-prefixed aliases from helpers / lifecycle.

from .strategy_mgr_helpers import (  # noqa: E402, F401
    LIFECYCLE_TRANSITIONS,
    _build_incubation_overview,
    _build_quality_report,
    _compute_nav_series,
    _get_latest_quality_report,
    _has_only_statistical_gate_failures,
    _is_factory_ai_prototype_strategy,
    _list_quality_reports,
    _maybe_grant_provisional_incubation,
    _metric_bucket_value,
    _normalize_quality_gate_result,
    _normalize_status_alias,
    _normalize_time_filter,
    _parse_bool,
    _quality_gate_reason_code,
    _safe_metric_value,
    _save_quality_report,
    _update_status,
    _validate_transition,
)
from .strategy_mgr_lifecycle import (  # noqa: E402, F401
    _lifecycle_scan,
    _run_quality_gate,
)
