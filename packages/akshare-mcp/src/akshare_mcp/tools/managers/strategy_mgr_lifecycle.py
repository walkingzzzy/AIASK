"""Strategy manager lifecycle action handlers: submit, publish, archive, lifecycle_scan, quality gates."""

import logging
from datetime import datetime, timezone
from typing import Optional

from ...utils import fail, ok
from .strategy_mgr_helpers import (
    build_incubation_overview,
    build_quality_report,
    get_latest_quality_report,
    normalize_quality_gate_result,
    save_quality_report,
    update_status,
    validate_transition,
)

logger = logging.getLogger(__name__)


async def handle_review_report_recheck(db, params: dict) -> dict:
    sid = str(params.get("strategy_id") or params.get("id") or "").strip()
    if not sid:
        return fail("strategy_id is required")
    strategy = await db.get_strategy(sid)
    if not strategy:
        return fail(f"Strategy not found: {sid}")
    latest_report = await get_latest_quality_report(db, sid)
    gate_result = await run_quality_gate(
        db,
        strategy,
        validation_report=(latest_report or {}).get("validation_report") or {},
        risk_report=(latest_report or {}).get("risk_report") or {},
        backtest_metrics=(latest_report or {}).get("backtest_metrics") or {},
    )
    report_type = f"recheck:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    report = build_quality_report(
        strategy_id=sid,
        strategy_type=strategy.get("strategy_type"),
        quality_gate=gate_result,
        validation_report=(latest_report or {}).get("validation_report") or {},
        risk_report=(latest_report or {}).get("risk_report") or {},
        dedup_report=(latest_report or {}).get("dedup_report") or {},
        backtest_metrics=(latest_report or {}).get("backtest_metrics") or {},
        snapshot=(latest_report or {}).get("snapshot") or {},
        status_after_review=strategy.get("status"),
        review_source="review_report_recheck",
        report_type=report_type,
        spawn_reason=((latest_report or {}).get("summary") or {}).get("spawn_reason"),
    )
    await save_quality_report(db, sid, report, report_type=report_type)
    return ok(report)


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
    from strategy_factory import get_strategy_factory_scheduler

    scheduler = get_strategy_factory_scheduler()
    status = scheduler.status()
    latest_run = await db.get_latest_strategy_factory_run() if hasattr(db, "get_latest_strategy_factory_run") else None
    if latest_run:
        status["last_persisted_run"] = latest_run
        if not status.get("last_result"):
            status["last_run"] = latest_run.get("completed_at") or latest_run.get("started_at")
            status["last_result"] = {
                "status": latest_run.get("status"),
                "error": latest_run.get("error"),
            }
            status["last_summary"] = latest_run.get("summary") or {}
    return ok(status)


async def handle_factory_run_once(db, params: dict) -> dict:
    from strategy_factory import get_strategy_factory_scheduler

    scheduler = get_strategy_factory_scheduler()
    return ok(await scheduler.run_once())


async def handle_factory_runs(db, params: dict) -> dict:
    limit = min(max(int(params.get("limit", 10)), 1), 100)
    rows = await db.list_strategy_factory_runs(limit=limit) if hasattr(db, "list_strategy_factory_runs") else []
    return ok({"items": rows, "count": len(rows)})


async def handle_factory_run_detail(db, params: dict) -> dict:
    run_id = str(params.get("run_id") or "").strip()
    if not run_id:
        return fail("run_id is required")
    row = await db.get_strategy_factory_run(run_id) if hasattr(db, "get_strategy_factory_run") else None
    if not row:
        return fail(f"Factory run not found: {run_id}")
    return ok(row)


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
