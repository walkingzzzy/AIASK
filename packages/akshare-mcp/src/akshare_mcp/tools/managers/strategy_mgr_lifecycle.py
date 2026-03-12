"""Strategy manager lifecycle action handlers: submit, publish, archive, lifecycle_scan, quality gates."""

import logging
from datetime import datetime, timezone
from typing import Optional

from ...services.strategy_factory import QUALITY_GATE_THRESHOLDS
from ...services.strategy_factory.targets import _extract_target_codes_from_payload
from ...utils import fail, ok
from .strategy_mgr_helpers import (
    build_incubation_overview,
    build_quality_report,
    get_latest_quality_report,
    maybe_grant_provisional_incubation,
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
    gate_result = normalize_quality_gate_result(await run_quality_gate(db, strategy))
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

    gate_result = normalize_quality_gate_result(await run_quality_gate(db, strategy))
    metrics_list = await db.get_strategy_metrics(sid) if hasattr(db, 'get_strategy_metrics') else []
    backtest_metrics = next((item for item in metrics_list if item.get('period') in ('backtest', 'all')), {})
    latest_report = await get_latest_quality_report(db, sid)
    gate_result = maybe_grant_provisional_incubation(
        strategy,
        gate_result,
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
    from ...services.strategy_factory import get_strategy_factory_scheduler

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
    from ...services.strategy_factory import get_strategy_factory_scheduler

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

async def run_quality_gate(db, strategy: dict) -> dict:
    """Run automated quality-gate pipeline. Reuses validation.py Walk-Forward / Purged K-Fold / Bootstrap IC."""
    try:
        from ...services.validation import (
            WalkForwardValidator,
            PurgedKFoldCV,
            bootstrap_ic_ci,
        )
        from ...services.backtest.strategy_registry import StrategyRegistry
        import numpy as np

        strategy_type = strategy.get("strategy_type", "")
        klass = StrategyRegistry.get(strategy_type)
        if klass is None:
            return normalize_quality_gate_result({"passed": False, "reason": f"Strategy type not in registry: {strategy_type}"})

        instance = klass()
        strategy_params = strategy.get("params") or {}
        instance.set_parameters(strategy_params)

        target_codes = _extract_target_codes_from_payload(strategy)
        codes = list(dict.fromkeys([*target_codes, "600519", "000858", "601318", "600036", "000333"]))
        all_closes = []
        for code in codes:
            klines = await db.get_klines(code, limit=500)
            if klines and len(klines) >= 100:
                closes = np.array([float(k.get("close", 0)) for k in klines])
                all_closes.append(closes)

        if not all_closes:
            return normalize_quality_gate_result({"passed": False, "reason": "Insufficient kline data for quality gate"})

        min_len = min(len(c) for c in all_closes)
        n_stocks = len(all_closes)
        factor_panel = np.zeros((min_len, n_stocks))
        return_panel = np.zeros((min_len, n_stocks))
        for j, closes in enumerate(all_closes):
            closes = closes[:min_len]
            signals = instance.generate_signals(closes)
            factor_panel[:, j] = signals[:min_len].astype(float)
            for i in range(min_len - 1):
                return_panel[i, j] = (closes[i + 1] - closes[i]) / closes[i] if closes[i] > 0 else 0

        flat_factors = factor_panel.flatten()
        flat_returns = return_panel.flatten()

        reasons = []

        # 1. Walk-Forward OOS IC IR
        _wf_min = QUALITY_GATE_THRESHOLDS["walk_forward_ic_ir_min"]
        try:
            wf = WalkForwardValidator(train_window=60, test_window=20, step=20)
            wf_summary = wf.validate(factor_panel, return_panel)
            wf_sharpe = wf_summary.oos_ic_ir
            if wf_sharpe < _wf_min:
                reasons.append(f"Walk-Forward IC IR {wf_sharpe:.3f} < {_wf_min}")
        except Exception as e:
            reasons.append(f"Walk-Forward error: {e}")
            wf_sharpe = 0

        # 2. Purged K-Fold IC
        _pkf_min = QUALITY_GATE_THRESHOLDS["purged_kfold_ic_min"]
        try:
            pkf = PurgedKFoldCV(n_folds=5, purge_gap=5)
            pkf_summary = pkf.validate(factor_panel, return_panel)
            pkf_ic = pkf_summary.oos_ic_mean
            if pkf_ic < _pkf_min:
                reasons.append(f"Purged K-Fold IC {pkf_ic:.4f} < {_pkf_min}")
        except Exception as e:
            reasons.append(f"Purged K-Fold error: {e}")
            pkf_ic = 0

        # 3. Bootstrap CI lower bound
        _bs_min = QUALITY_GATE_THRESHOLDS["bootstrap_ci_lower_min"]
        try:
            bs = bootstrap_ic_ci(flat_factors, flat_returns)
            ci_lower = bs.get("ci_lower", 0)
            if ci_lower < _bs_min:
                reasons.append(f"Bootstrap CI lower {ci_lower:.4f} < {_bs_min}")
        except Exception as e:
            reasons.append(f"Bootstrap error: {e}")
            ci_lower = 0

        # 4. Parameter sensitivity
        _sens_max = QUALITY_GATE_THRESHOLDS["param_sensitivity_max"]
        sensitivity = 0.0
        try:
            ref_closes = all_closes[0][:min_len]
            ref_returns = return_panel[:, 0]
            base_signals = instance.generate_signals(ref_closes)[:min_len]
            base_ic = float(np.corrcoef(base_signals.astype(float), ref_returns)[0, 1])
            if not np.isnan(base_ic) and abs(base_ic) > 0.001:
                variations = []
                for key, val in strategy_params.items():
                    if isinstance(val, (int, float)) and val != 0:
                        for mult in [0.8, 1.2]:
                            test_params = {**strategy_params, key: type(val)(val * mult)}
                            test_instance = klass()
                            test_instance.set_parameters(test_params)
                            test_signals = test_instance.generate_signals(ref_closes)[:min_len]
                            test_ic = float(np.corrcoef(test_signals.astype(float), ref_returns)[0, 1])
                            if not np.isnan(test_ic):
                                variations.append(abs(test_ic - base_ic) / abs(base_ic))
                if variations:
                    sensitivity = float(np.mean(variations))
            if sensitivity > _sens_max:
                reasons.append(f"Parameter sensitivity {sensitivity:.2%} > {_sens_max:.0%}")
        except Exception as e:
            reasons.append(f"Sensitivity error: {e}")

        # 5. Multi-period robustness: split data into two halves, verify IC is positive in both
        period_robustness = {"first_half_ic": 0.0, "second_half_ic": 0.0, "ic_consistency": 0.0}
        try:
            half = min_len // 2
            if half >= 50:
                first_factors = factor_panel[:half, :].flatten()
                first_returns = return_panel[:half, :].flatten()
                second_factors = factor_panel[half:, :].flatten()
                second_returns = return_panel[half:, :].flatten()
                ic_first = float(np.corrcoef(first_factors, first_returns)[0, 1])
                ic_second = float(np.corrcoef(second_factors, second_returns)[0, 1])
                if np.isnan(ic_first):
                    ic_first = 0.0
                if np.isnan(ic_second):
                    ic_second = 0.0
                period_robustness = {
                    "first_half_ic": round(ic_first, 4),
                    "second_half_ic": round(ic_second, 4),
                    "ic_consistency": round(min(ic_first, ic_second), 4),
                }
                # Both halves must have non-negative IC
                if ic_first < -0.02 or ic_second < -0.02:
                    reasons.append(
                        f"Multi-period IC inconsistent: first_half={ic_first:.4f}, second_half={ic_second:.4f} (both must be >= -0.02)"
                    )
                # IC direction must be consistent (both positive or both near zero)
                elif ic_first > 0.01 and ic_second < -0.01:
                    reasons.append(
                        f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                    )
                elif ic_first < -0.01 and ic_second > 0.01:
                    reasons.append(
                        f"Multi-period IC direction reversal: first_half={ic_first:.4f}, second_half={ic_second:.4f}"
                    )
        except Exception as e:
            reasons.append(f"Multi-period robustness error: {e}")

        passed = len(reasons) == 0
        return normalize_quality_gate_result({
            "passed": passed,
            "wf_ic_ir": round(wf_sharpe, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(ci_lower, 4),
            "param_sensitivity": round(sensitivity, 4),
            "period_robustness": period_robustness,
            "reasons": reasons,
        })
    except Exception as e:
        return normalize_quality_gate_result({"passed": False, "reason": str(e)})


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
