"""Strategy marketplace manager: CRUD, ranking, reviews, subscriptions, lifecycle."""

import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from ...services.ranking import rrf_rank
from ...storage import get_db
from ...utils import fail, ok

logger = logging.getLogger(__name__)


async def _compute_nav_series(db, strategy_id: str, max_points: int = 30) -> list:
    """从 signal_forward_returns 计算策略累计净值序列，降采样至 max_points 点"""
    try:
        async with db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ss.signal_date, ss.signal, sfr.actual_return
                FROM strategy_signals ss
                JOIN signal_forward_returns sfr ON sfr.signal_id = ss.id AND sfr.forward_days = 5
                WHERE ss.strategy_id = $1 AND ss.signal != 0
                ORDER BY ss.signal_date
            """, strategy_id)
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

# ── 生命周期状态转换规则 ──
LIFECYCLE_TRANSITIONS = {
    "draft": ["submitted"],
    "submitted": ["incubating", "rejected"],
    "rejected": ["draft"],
    "incubating": ["listed", "deprecated", "suspended"],
    "listed": ["deprecated", "suspended", "archived"],
    "suspended": ["listed", "deprecated", "incubating"],
    "deprecated": [],
    "published": ["deprecated", "suspended", "archived", "listed"],
    "archived": [],
}


def _normalize_status_alias(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    return "listed" if normalized == "published" else normalized


def _validate_transition(current: str, target: str) -> bool:
    current_normalized = _normalize_status_alias(current)
    target_normalized = _normalize_status_alias(target)
    return target_normalized in LIFECYCLE_TRANSITIONS.get(current_normalized, [])


async def _update_status(db, strategy_id: str, status: str, **kwargs) -> None:
    normalized = _normalize_status_alias(status)
    try:
        await db.update_strategy_status(strategy_id, normalized, **kwargs)
    except TypeError:
        await db.update_strategy_status(strategy_id, normalized)


async def _save_quality_report(db, strategy_id: str, report: dict, report_type: str = "submission") -> None:
    if hasattr(db, "save_strategy_quality_report"):
        await db.save_strategy_quality_report(strategy_id, report_type, report)


def _metric_bucket_value(metric: Optional[dict], key: int) -> Optional[float]:
    if not metric:
        return None
    value = metric.get(key)
    if value is None:
        value = metric.get(str(key))
    return None if value is None else float(value)


def _normalize_time_filter(value: Any, *, is_end: bool = False) -> Optional[str]:
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


def _quality_gate_reason_code(reason: str) -> str:
    text = str(reason or "").strip()
    if not text:
        return "unknown"
    lowered = text.lower()
    overrides = {
        "insufficient kline data": "insufficient_kline_data",
        "validation_grade_d": "validation_grade_d",
    }
    for needle, code in overrides.items():
        if needle in lowered:
            return code
    normalized = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    return normalized or "unknown"


def _normalize_quality_gate_result(result: Optional[dict]) -> dict:
    raw = dict(result or {})
    reasons: list[str] = []
    for item in raw.get("reasons") or []:
        text = str(item).strip()
        if text and text not in reasons:
            reasons.append(text)
    reason = str(raw.get("reason") or "").strip()
    if reason and reason not in reasons:
        reasons.append(reason)
    return {
        **raw,
        "passed": bool(raw.get("passed")),
        "reasons": reasons,
        "reason_codes": [_quality_gate_reason_code(item) for item in reasons],
    }


def _build_quality_report(
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
) -> dict:
    normalized_gate = _normalize_quality_gate_result(quality_gate)
    validation = dict(validation_report or {})
    rating = validation.get("rating") or {}
    summary = {
        "strategy_id": strategy_id,
        "strategy_type": strategy_type,
        "status_after_review": status_after_review,
        "validation_grade": rating.get("grade"),
        "review_source": review_source,
    }
    if spawn_reason:
        summary["spawn_reason"] = spawn_reason
    return {
        "report_type": report_type,
        "passed": bool(normalized_gate.get("passed")),
        "summary": summary,
        "quality_gate": normalized_gate,
        "validation_report": validation,
        "risk_report": dict(risk_report or {}),
        "dedup_report": dict(dedup_report or {}),
        "backtest_metrics": dict(backtest_metrics or {}),
        "snapshot": dict(snapshot or {}),
    }


async def _list_quality_reports(db, strategy_id: str, limit: int = 10) -> list[dict]:
    if hasattr(db, "list_strategy_quality_reports"):
        return await db.list_strategy_quality_reports(strategy_id, limit=limit)
    latest = None
    if hasattr(db, "get_latest_strategy_quality_report"):
        latest = await db.get_latest_strategy_quality_report(strategy_id)
    elif hasattr(db, "get_strategy_quality_report"):
        latest = await db.get_strategy_quality_report(strategy_id)
    return [latest] if latest else []


async def _get_latest_quality_report(db, strategy_id: str) -> Optional[dict]:
    rows = await _list_quality_reports(db, strategy_id, limit=1)
    return rows[0] if rows else None


async def _build_incubation_overview(db, strategy: dict) -> dict:
    metrics = await db.get_strategy_metrics(strategy["id"])
    all_m = next((m for m in metrics if m.get("period") == "all"), {})
    backtest_m = next((m for m in metrics if m.get("period") == "backtest"), all_m)
    quality_report = await _get_latest_quality_report(db, strategy["id"])
    signal_stats = await db.get_signal_stats(strategy["id"])

    sharpe = float((all_m or backtest_m).get("sharpe_ratio") or 0)
    mdd = abs(float((all_m or backtest_m).get("max_drawdown") or 0))
    total_signals = int(signal_stats.get("total_signals") or 0)
    min_signal_count = 10
    hit_rate_5d = _metric_bucket_value(signal_stats.get("hit_rate"), 5)
    forward_ic_5d = _metric_bucket_value(signal_stats.get("forward_ic"), 5)
    forward_sharpe_5d = _metric_bucket_value(signal_stats.get("forward_sharpe"), 5)

    blockers: list[str] = []
    risk_flags: list[str] = []
    blockers_by_period: dict[str, list[str]] = {}
    risk_flags_by_period: dict[str, list[str]] = {}
    observed_forward_days: list[int] = []
    forward_returns: list[dict] = []
    if sharpe <= 0.5:
        blockers.append(f"Sharpe {sharpe:.2f} ≤ 0.50")
    if mdd >= 0.20:
        blockers.append(f"最大回撤 {mdd:.1%} ≥ 20%")
    if total_signals < min_signal_count:
        blockers.append(f"有效信号数 {total_signals} < {min_signal_count}")
    if sharpe < 0:
        risk_flags.append(f"Sharpe {sharpe:.2f} < 0")
    if mdd > 0.30:
        risk_flags.append(f"最大回撤 {mdd:.1%} > 30%")

    for days in (1, 5, 10, 20):
        label = f"{days}D"
        hit_rate = _metric_bucket_value(signal_stats.get("hit_rate"), days)
        forward_ic = _metric_bucket_value(signal_stats.get("forward_ic"), days)
        forward_sharpe = _metric_bucket_value(signal_stats.get("forward_sharpe"), days)
        if hit_rate is None and forward_ic is None and forward_sharpe is None:
            continue
        observed_forward_days.append(days)
        period_blockers: list[str] = []
        period_risk_flags: list[str] = []
        if total_signals >= min_signal_count and days in (5, 10, 20) and hit_rate is not None and hit_rate < 0.45:
            period_blockers.append(f"{label}命中率 {hit_rate:.1%} < 45%")
        if total_signals >= min_signal_count and days in (5, 10, 20) and hit_rate is not None and hit_rate < 0.30:
            period_risk_flags.append(f"{label}命中率 {hit_rate:.1%} < 30%")
        if days >= 10 and forward_ic is not None and forward_ic < 0:
            period_risk_flags.append(f"{label}前向IC {forward_ic:.2f} < 0")
        if days >= 10 and forward_sharpe is not None and forward_sharpe < 0:
            period_risk_flags.append(f"{label}前向Sharpe {forward_sharpe:.2f} < 0")
        if period_blockers:
            blockers_by_period[label] = period_blockers
            blockers.extend(period_blockers)
        if period_risk_flags:
            risk_flags_by_period[label] = period_risk_flags
            risk_flags.extend(period_risk_flags)
        forward_returns.append({
            "forward_days": days,
            "label": label,
            "hit_rate": hit_rate,
            "forward_ic": forward_ic,
            "forward_sharpe": forward_sharpe,
            "blockers": period_blockers,
            "risk_flags": period_risk_flags,
        })

    missing_forward_days = [days for days in (1, 5, 10, 20) if days not in observed_forward_days]
    if total_signals >= min_signal_count and missing_forward_days:
        blockers.append("缺少前向收益观察窗口: " + ", ".join(f"{days}D" for days in missing_forward_days))

    promotion_ready = not blockers
    deprecation_risk = bool(risk_flags)

    return {
        "strategy_id": strategy["id"],
        "strategy_name": strategy.get("name"),
        "status": strategy.get("status"),
        "strategy_type": strategy.get("strategy_type"),
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
        "total_signals": total_signals,
        "minimum_signal_count": min_signal_count,
        "hit_rate_5d": hit_rate_5d,
        "forward_ic_5d": forward_ic_5d,
        "forward_sharpe_5d": forward_sharpe_5d,
        "promotion_ready": promotion_ready,
        "deprecation_risk": deprecation_risk,
        "blockers": blockers,
        "risk_flags": risk_flags,
        "observed_forward_days": observed_forward_days,
        "missing_forward_days": missing_forward_days,
        "forward_returns": forward_returns,
        "blockers_by_period": blockers_by_period,
        "risk_flags_by_period": risk_flags_by_period,
        "quality_passed": bool((quality_report or {}).get("passed")),
        "validation_grade": ((quality_report or {}).get("summary") or {}).get("validation_grade"),
    }


def register_strategy_manager(mcp):
    @mcp.tool()
    async def strategy_manager(action: str, kwargs: str = "{}") -> dict:
        """策略超市管理器 — 创建/发布/排名/评价/订阅/生命周期管理。

        Actions: create, publish, archive, list, detail, update_metrics, review, subscribe, unsubscribe, my_subscriptions, rank, submit, lifecycle_scan, get_signals, get_forward_returns, get_signal_stats, factory_status, factory_run_once, factory_runs, factory_run_detail, review_report, review_report_recheck, events, incubation_overview, help
        """
        try:
            params = json.loads(kwargs) if isinstance(kwargs, str) else (kwargs or {})
        except Exception:
            params = {}

        db = get_db()

        if action == "help":
            return ok({
                "actions": [
                    "create", "publish", "archive", "list", "detail",
                    "update_metrics", "review", "subscribe", "unsubscribe",
                    "my_subscriptions", "rank", "submit", "capabilities", "daily_snapshot", "daily_snapshots",
                    "incubation_accounts", "incubation_metrics", "risk_events", "resolve_risk_event",
                    "vector_profiles", "vector_indexes", "vector_reconcile", "vector_rebuild",
                    "ai_generate", "ai_experiments", "task_runs", "domain_events",
                    "runtime_cycle_run", "runtime_cycle_status", "lifecycle_scan", "get_signals", "get_forward_returns", "get_signal_stats",
                    "factory_status", "factory_run_once", "factory_runs", "factory_run_detail", "review_report", "review_report_recheck", "events",
                    "incubation_overview", "help",
                ],
                "description": "策略超市管理器（含生命周期与前向信号跟踪）",
            })

        if action == "create":
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

        if action == "publish":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            await _update_status(db, sid, "listed", actor_id="strategy_manager", reason="manual_publish")
            return ok({"strategy_id": sid, "status": "listed"})

        if action == "archive":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            await _update_status(db, sid, "archived", actor_id="strategy_manager", reason="manual_archive")
            return ok({"strategy_id": sid, "status": "archived"})

        if action == "list":
            status = _normalize_status_alias(str(params.get("status", "published")))
            strategy_type = params.get("strategy_type") or params.get("type")
            limit = min(max(int(params.get("limit", 20)), 1), 100)
            offset = max(int(params.get("offset", 0)), 0)
            rows = await db.list_strategies(status, strategy_type, limit, offset)
            return ok({"strategies": rows, "count": len(rows)})

        if action == "detail":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            strategy = await db.get_strategy(sid)
            if not strategy:
                return fail(f"Strategy not found: {sid}")
            metrics = await db.get_strategy_metrics(sid)
            reviews = await db.get_reviews(sid, limit=10)

            # IP 保护：非订阅者查看时对 NAV 指标添加噪声
            user_id = str(params.get("user_id", "default"))
            is_sub = await db.is_subscribed(sid, user_id)
            if not is_sub and metrics:
                noise = 1 + random.uniform(-0.001, 0.001)
                for m in metrics:
                    for key in ("total_return", "annual_return", "sharpe_ratio", "calmar_ratio"):
                        if m.get(key) is not None:
                            m[key] = round(float(m[key]) * noise, 6)
                    m["approximate"] = True

            latest_quality_report = await _get_latest_quality_report(db, sid)
            incubation_account = await db.get_strategy_incubation_account(sid) if hasattr(db, "get_strategy_incubation_account") else None
            incubation_metric = await db.get_latest_strategy_incubation_metric(sid) if hasattr(db, "get_latest_strategy_incubation_metric") else None
            risk_events = await db.list_strategy_runtime_risk_events(strategy_id=sid, status="open", limit=5) if hasattr(db, "list_strategy_runtime_risk_events") else []
            vector_profiles = await db.list_strategy_vector_profiles(strategy_id=sid, limit=3) if hasattr(db, "list_strategy_vector_profiles") else []
            domain_events = await db.list_strategy_domain_events(strategy_id=sid, limit=5) if hasattr(db, "list_strategy_domain_events") else []
            return ok({"strategy": strategy, "metrics": metrics, "reviews": reviews,
                       "nav_series": await _compute_nav_series(db, sid),
                       "latest_quality_report": latest_quality_report,
                       "incubation_account": incubation_account,
                       "latest_incubation_metric": incubation_metric,
                       "open_risk_events": risk_events,
                       "vector_profiles": vector_profiles,
                       "domain_events": domain_events})

        if action == "review_report":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            limit = min(max(int(params.get("limit", 10)), 1), 50)
            reports = await _list_quality_reports(db, sid, limit=limit)
            latest = reports[0] if reports else None
            return ok({**(latest or {}), "reports": reports})

        if action == "review_report_recheck":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            strategy = await db.get_strategy(sid)
            if not strategy:
                return fail(f"Strategy not found: {sid}")
            latest_report = await _get_latest_quality_report(db, sid)
            gate_result = _normalize_quality_gate_result(await _run_quality_gate(db, strategy))
            report_type = f"recheck:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
            report = _build_quality_report(
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
            await _save_quality_report(db, sid, report, report_type=report_type)
            return ok(report)

        if action == "events":
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
                        start_time=_normalize_time_filter(params.get("start_time")),
                        end_time=_normalize_time_filter(params.get("end_time"), is_end=True),
                        limit=limit,
                    )
                except TypeError:
                    rows = await db.list_strategy_status_events(sid, limit=limit)
            return ok({"events": rows, "count": len(rows)})

        if action == "update_metrics":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            metrics = params.get("metrics") or {}
            period = str(params.get("period", "all"))
            await db.save_strategy_metrics(sid, period, metrics)
            return ok({"strategy_id": sid, "period": period, "updated": True})

        if action == "review":
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

        if action == "subscribe":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            user_id = str(params.get("user_id", "default"))
            if not sid:
                return fail("strategy_id is required")
            await db.subscribe_strategy(sid, user_id)
            return ok({"strategy_id": sid, "user_id": user_id, "subscribed": True})

        if action == "unsubscribe":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            user_id = str(params.get("user_id", "default"))
            if not sid:
                return fail("strategy_id is required")
            await db.unsubscribe_strategy(sid, user_id)
            return ok({"strategy_id": sid, "user_id": user_id, "unsubscribed": True})

        if action == "my_subscriptions":
            user_id = str(params.get("user_id", "default"))
            rows = await db.list_user_subscriptions(user_id)
            return ok({"subscriptions": rows, "count": len(rows)})

        if action == "rank":
            status = _normalize_status_alias(str(params.get("status", "published")))
            strategy_type = params.get("strategy_type") or params.get("type")
            limit = min(max(int(params.get("limit", 50)), 1), 200)
            offset = max(int(params.get("offset", 0)), 0)
            rank_keys = params.get("rank_keys")

            fetch_limit = limit + offset
            strategies = await db.list_strategies(status, strategy_type, fetch_limit, 0)
            if not strategies:
                return ok({"strategies": [], "count": 0, "offset": offset, "limit": limit})

            # Attach metrics to each strategy for ranking
            enriched = []
            for s in strategies:
                metrics_list = await db.get_strategy_metrics(s["id"])
                all_period = next((m for m in metrics_list if m.get("period") == "all"), {})
                nav = await _compute_nav_series(db, s["id"])
                enriched.append({
                    **s,
                    "sharpe_ratio": all_period.get("sharpe_ratio"),
                    "total_return": all_period.get("total_return"),
                    "max_drawdown": all_period.get("max_drawdown"),
                    "win_rate": all_period.get("win_rate"),
                    "calmar_ratio": all_period.get("calmar_ratio"),
                    "nav_series": nav,
                })

            ranked = rrf_rank(enriched, rank_keys)
            page = ranked[offset:offset + limit]
            return ok({"strategies": page, "count": len(ranked), "offset": offset, "limit": limit})

        # ── P5: 生命周期管理 ──

        if action == "submit":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            strategy = await db.get_strategy(sid)
            if not strategy:
                return fail(f"Strategy not found: {sid}")
            current = strategy.get("status", "draft")
            if not _validate_transition(current, "submitted"):
                return fail(f"Cannot submit from status: {current}")

            await _update_status(db, sid, "submitted", actor_id="strategy_manager", reason="manual_submit")

            # 自动化质检
            gate_result = _normalize_quality_gate_result(await _run_quality_gate(db, strategy))
            next_status = "incubating" if gate_result["passed"] else "rejected"
            await _save_quality_report(db, sid, _build_quality_report(
                strategy_id=sid,
                strategy_type=strategy.get("strategy_type"),
                quality_gate=gate_result,
                validation_report={},
                risk_report={},
                dedup_report={},
                backtest_metrics={},
                snapshot={},
                status_after_review=next_status,
                review_source="manager_submit",
                report_type="submission",
            ))
            if gate_result["passed"]:
                incubation_binding = None
                vector_profile = None
                await _update_status(db, sid, "incubating", actor_id="strategy_manager", reason="quality_gate_passed", metadata={"quality_gate": gate_result})
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
                await _update_status(db, sid, "rejected", actor_id="strategy_manager", reason="quality_gate_failed", metadata={"quality_gate": gate_result})
                return ok({
                    "strategy_id": sid, "status": "rejected",
                    "quality_gate": "failed", "details": gate_result,
                })

        if action == "capabilities":
            return ok({
                "daily_snapshot": hasattr(db, "get_daily_snapshot") and hasattr(db, "list_daily_snapshots"),
                "paper_incubation": hasattr(db, "save_strategy_incubation_account") and hasattr(db, "save_strategy_incubation_metric"),
                "runtime_risk": hasattr(db, "save_strategy_runtime_risk_event"),
                "execution_risk": hasattr(db, "save_strategy_runtime_risk_event"),
                "vector_platform": hasattr(db, "save_strategy_vector_profile") and hasattr(db, "save_vector_index_registry"),
                "vector_governance": hasattr(db, "save_vector_index_registry") and hasattr(db, "list_strategy_vector_profiles"),
                "ai_generation": hasattr(db, "save_strategy_generation_experiment") and hasattr(db, "save_strategy_task_run"),
                "multi_agent_review": hasattr(db, "save_strategy_generation_experiment"),
                "quality_governance": hasattr(db, "save_strategy_quality_report") and hasattr(db, "list_strategy_status_events"),
                "domain_events": hasattr(db, "save_strategy_domain_event") and hasattr(db, "list_strategy_domain_events"),
                "runtime_cycle": hasattr(db, "save_strategy_task_run") and hasattr(db, "save_strategy_incubation_metric"),
            })

        if action == "daily_snapshot":
            snapshot_date = params.get("snapshot_date")
            row = await db.get_daily_snapshot(snapshot_date) if hasattr(db, "get_daily_snapshot") else None
            if not row:
                return fail("daily snapshot not found")
            return ok(row)

        if action == "daily_snapshots":
            limit = min(max(int(params.get("limit", 20)), 1), 200)
            rows = await db.list_daily_snapshots(
                limit=limit,
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
            ) if hasattr(db, "list_daily_snapshots") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "incubation_accounts":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip() or None
            limit = min(max(int(params.get("limit", 20)), 1), 200)
            rows = await db.list_strategy_incubation_accounts(strategy_id=sid, status=params.get("status"), limit=limit) if hasattr(db, "list_strategy_incubation_accounts") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "incubation_metrics":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            limit = min(max(int(params.get("limit", 30)), 1), 365)
            rows = await db.list_strategy_incubation_metrics(
                sid,
                limit=limit,
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
            ) if hasattr(db, "list_strategy_incubation_metrics") else []
            latest = rows[0] if rows else None
            return ok({"items": rows, "latest": latest, "count": len(rows)})

        if action == "risk_events":
            limit = min(max(int(params.get("limit", 50)), 1), 500)
            rows = await db.list_strategy_runtime_risk_events(
                strategy_id=(str(params.get("strategy_id") or params.get("id") or "").strip() or None),
                account_id=(str(params.get("account_id") or "").strip() or None),
                status=(str(params.get("status") or "").strip() or None),
                severity=(str(params.get("severity") or "").strip() or None),
                limit=limit,
            ) if hasattr(db, "list_strategy_runtime_risk_events") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "resolve_risk_event":
            event_id = params.get("event_id")
            if event_id is None:
                return fail("event_id is required")
            row = await db.resolve_strategy_runtime_risk_event(int(event_id), {
                "resolution": params.get("resolution") or "manual_resolved",
            }) if hasattr(db, "resolve_strategy_runtime_risk_event") else None
            if not row:
                return fail("risk event not found")
            return ok(row)

        if action == "vector_profiles":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip() or None
            limit = min(max(int(params.get("limit", 20)), 1), 200)
            if params.get("similar_to"):
                from ...services.vector_platform import get_strategy_vector_platform
                rows = await get_strategy_vector_platform().find_similar_profiles(db, str(params.get("similar_to")), limit=limit)
            else:
                rows = await db.list_strategy_vector_profiles(strategy_id=sid, profile_type=params.get("profile_type"), limit=limit) if hasattr(db, "list_strategy_vector_profiles") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "vector_indexes":
            limit = min(max(int(params.get("limit", 20)), 1), 200)
            rows = await db.list_vector_index_registry(index_name=params.get("index_name"), status=params.get("status"), limit=limit) if hasattr(db, "list_vector_index_registry") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "vector_reconcile":
            from ...services.vector_governance import get_strategy_vector_governance_service
            result = await get_strategy_vector_governance_service().reconcile_registry(
                db,
                index_name=(str(params.get("index_name") or "").strip() or None),
                profile_type=(str(params.get("profile_type") or "").strip() or None),
                limit_profiles=min(max(int(params.get("limit_profiles", 2000)), 1), 5000),
            )
            return ok(result)

        if action == "vector_rebuild":
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
                vector_method=str(params.get("vector_method") or 'price_volume'),
            )
            return ok(result)

        if action == "domain_events":
            limit = min(max(int(params.get("limit", 50)), 1), 500)
            rows = await db.list_strategy_domain_events(
                strategy_id=(str(params.get("strategy_id") or params.get("id") or "").strip() or None),
                aggregate_type=(str(params.get("aggregate_type") or "").strip() or None),
                event_type=(str(params.get("event_type") or "").strip() or None),
                source=(str(params.get("source") or "").strip() or None),
                correlation_id=(str(params.get("correlation_id") or "").strip() or None),
                limit=limit,
            ) if hasattr(db, "list_strategy_domain_events") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "runtime_cycle_status":
            from ...services.signal_tracker import get_signal_tracker
            return ok(get_signal_tracker().status())

        if action == "runtime_cycle_run":
            from ...services.signal_tracker import get_signal_tracker
            return ok(await get_signal_tracker().run_once())

        if action == "ai_generate":
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

        if action == "ai_experiments":
            experiment_id = str(params.get("experiment_id") or "").strip()
            if experiment_id:
                row = await db.get_strategy_generation_experiment(experiment_id) if hasattr(db, "get_strategy_generation_experiment") else None
                if not row:
                    return fail(f"experiment not found: {experiment_id}")
                return ok(row)
            limit = min(max(int(params.get("limit", 20)), 1), 200)
            rows = await db.list_strategy_generation_experiments(
                strategy_id=(str(params.get("strategy_id") or params.get("id") or "").strip() or None),
                status=(str(params.get("status") or "").strip() or None),
                source=(str(params.get("source") or "").strip() or None),
                limit=limit,
            ) if hasattr(db, "list_strategy_generation_experiments") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "task_runs":
            limit = min(max(int(params.get("limit", 20)), 1), 500)
            rows = await db.list_strategy_task_runs(
                task_name=(str(params.get("task_name") or "").strip() or None),
                task_scope=(str(params.get("task_scope") or "").strip() or None),
                status=(str(params.get("status") or "").strip() or None),
                limit=limit,
            ) if hasattr(db, "list_strategy_task_runs") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "factory_status":
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

        if action == "factory_run_once":
            from ...services.strategy_factory import get_strategy_factory_scheduler

            scheduler = get_strategy_factory_scheduler()
            return ok(await scheduler.run_once())

        if action == "factory_runs":
            limit = min(max(int(params.get("limit", 10)), 1), 100)
            rows = await db.list_strategy_factory_runs(limit=limit) if hasattr(db, "list_strategy_factory_runs") else []
            return ok({"items": rows, "count": len(rows)})

        if action == "factory_run_detail":
            run_id = str(params.get("run_id") or "").strip()
            if not run_id:
                return fail("run_id is required")
            row = await db.get_strategy_factory_run(run_id) if hasattr(db, "get_strategy_factory_run") else None
            if not row:
                return fail(f"Factory run not found: {run_id}")
            return ok(row)

        if action == "lifecycle_scan":
            results = await _lifecycle_scan(db)
            return ok(results)

        if action == "incubation_overview":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if sid:
                strategy = await db.get_strategy(sid)
                if not strategy:
                    return fail(f"Strategy not found: {sid}")
                return ok(await _build_incubation_overview(db, strategy))
            limit = min(max(int(params.get("limit", 20)), 1), 100)
            incubating = await db.list_strategies("incubating", limit=limit)
            items = [await _build_incubation_overview(db, s) for s in incubating]
            return ok({"items": items, "count": len(items)})

        # ── P5: 前向信号查询 ──

        if action == "get_signals":
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

        if action == "get_forward_returns":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            stats = await db.get_signal_stats(sid)
            return ok(stats)

        if action == "get_signal_stats":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            stats = await db.get_signal_stats(sid)
            return ok(stats)

        return fail(f"Unknown action: {action}. Use action='help' for available actions.")


async def _run_quality_gate(db, strategy: dict) -> dict:
    """运行自动化质检管线。复用 validation.py 的 Walk-Forward / Purged K-Fold / Bootstrap IC。"""
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
            return _normalize_quality_gate_result({"passed": False, "reason": f"Strategy type not in registry: {strategy_type}"})

        instance = klass()
        strategy_params = strategy.get("params") or {}
        instance.set_parameters(strategy_params)

        # 获取测试数据（使用沪深300成分股的因子值作为代理）
        codes = ["600519", "000858", "601318", "600036", "000333"]
        all_closes = []
        for code in codes:
            klines = await db.get_klines(code, limit=500)
            if klines and len(klines) >= 100:
                closes = np.array([float(k.get("close", 0)) for k in klines])
                all_closes.append(closes)

        if not all_closes:
            return _normalize_quality_gate_result({"passed": False, "reason": "Insufficient kline data for quality gate"})

        # 构建因子面板和收益面板 shape=(n_periods, n_stocks)
        min_len = min(len(c) for c in all_closes)
        n_stocks = len(all_closes)
        # 每只股票生成信号作为因子值
        factor_panel = np.zeros((min_len, n_stocks))
        return_panel = np.zeros((min_len, n_stocks))
        for j, closes in enumerate(all_closes):
            closes = closes[:min_len]
            signals = instance.generate_signals(closes)
            factor_panel[:, j] = signals[:min_len].astype(float)
            for i in range(min_len - 1):
                return_panel[i, j] = (closes[i + 1] - closes[i]) / closes[i] if closes[i] > 0 else 0

        # 同时保留1D数组用于 bootstrap_ic_ci
        flat_factors = factor_panel.flatten()
        flat_returns = return_panel.flatten()

        reasons = []

        # 1. Walk-Forward OOS IC IR > 0.3
        try:
            wf = WalkForwardValidator(train_window=60, test_window=20, step=20)
            wf_summary = wf.validate(factor_panel, return_panel)
            wf_sharpe = wf_summary.oos_ic_ir
            if wf_sharpe < 0.3:
                reasons.append(f"Walk-Forward IC IR {wf_sharpe:.3f} < 0.3")
        except Exception as e:
            reasons.append(f"Walk-Forward error: {e}")
            wf_sharpe = 0

        # 2. Purged K-Fold IC > 0.02
        try:
            pkf = PurgedKFoldCV(n_folds=5, purge_gap=5)
            pkf_summary = pkf.validate(factor_panel, return_panel)
            pkf_ic = pkf_summary.oos_ic_mean
            if pkf_ic < 0.02:
                reasons.append(f"Purged K-Fold IC {pkf_ic:.4f} < 0.02")
        except Exception as e:
            reasons.append(f"Purged K-Fold error: {e}")
            pkf_ic = 0

        # 3. Bootstrap CI 下界 > 0
        try:
            bs = bootstrap_ic_ci(flat_factors, flat_returns)
            ci_lower = bs.get("ci_lower", 0)
            if ci_lower <= 0:
                reasons.append(f"Bootstrap CI lower {ci_lower:.4f} <= 0")
        except Exception as e:
            reasons.append(f"Bootstrap error: {e}")
            ci_lower = 0

        # 4. 参数敏感性 < 30%
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
            if sensitivity > 0.30:
                reasons.append(f"Parameter sensitivity {sensitivity:.2%} > 30%")
        except Exception as e:
            reasons.append(f"Sensitivity error: {e}")

        passed = len(reasons) == 0
        return _normalize_quality_gate_result({
            "passed": passed,
            "wf_ic_ir": round(wf_sharpe, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(ci_lower, 4),
            "param_sensitivity": round(sensitivity, 4),
            "reasons": reasons,
        })
    except Exception as e:
        return _normalize_quality_gate_result({"passed": False, "reason": str(e)})


async def _lifecycle_scan(db) -> dict:
    """批量扫描策略状态转换"""
    transitions = []
    blocked = []

    # Incubating → listed (30天 Sharpe > 0.5 且 MDD < 20%)
    incubating = await db.list_strategies("incubating", limit=100)
    for s in incubating:
        overview = await _build_incubation_overview(db, s)
        if overview["promotion_ready"]:
            await _update_status(
                db,
                s["id"],
                "listed",
                actor_id="lifecycle_scan",
                reason="incubation_promoted",
                metadata=overview,
            )
            transitions.append({"id": s["id"], "from": "incubating", "to": "listed", "reason": "incubation_promoted"})
        elif overview["deprecation_risk"]:
            await _update_status(
                db,
                s["id"],
                "deprecated",
                actor_id="lifecycle_scan",
                reason="incubation_failed",
                metadata=overview,
            )
            transitions.append({"id": s["id"], "from": "incubating", "to": "deprecated", "reason": "incubation_failed"})
        else:
            blocked.append({"id": s["id"], "status": "incubating", "blockers": overview["blockers"]})

    # Listed → deprecated (30天 Sharpe < 0 或 MDD > 30%)
    listed = await db.list_strategies("listed", limit=200)
    for s in listed:
        overview = await _build_incubation_overview(db, s)
        if overview["deprecation_risk"]:
            await _update_status(
                db,
                s["id"],
                "deprecated",
                actor_id="lifecycle_scan",
                reason="listed_degraded",
                metadata=overview,
            )
            transitions.append({"id": s["id"], "from": "listed", "to": "deprecated", "reason": "listed_degraded"})

    return {"scanned": len(incubating) + len(listed), "transitions": transitions, "blocked": blocked}
