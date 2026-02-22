"""Strategy marketplace manager: CRUD, ranking, reviews, subscriptions, lifecycle."""

import json
import logging
import random
import time
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
    "draft":       ["submitted"],
    "submitted":   ["incubating", "rejected"],
    "rejected":    ["draft"],
    "incubating":  ["listed", "rejected"],
    "listed":      ["deprecated", "suspended"],
    "suspended":   ["listed", "deprecated"],
    "deprecated":  [],
    "published":   ["deprecated", "suspended", "archived", "listed"],
    "archived":    [],
}


def _validate_transition(current: str, target: str) -> bool:
    return target in LIFECYCLE_TRANSITIONS.get(current, [])


def register_strategy_manager(mcp):
    @mcp.tool()
    async def strategy_manager(action: str, kwargs: str = "{}") -> dict:
        """策略超市管理器 — 创建/发布/排名/评价/订阅/生命周期管理。

        Actions: create, publish, archive, list, detail, update_metrics, review, subscribe, unsubscribe, my_subscriptions, rank, submit, lifecycle_scan, get_signals, get_forward_returns, get_signal_stats, help
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
                    "my_subscriptions", "rank", "submit", "lifecycle_scan",
                    "get_signals", "get_forward_returns", "get_signal_stats", "help",
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
            await db.update_strategy_status(sid, "published")
            return ok({"strategy_id": sid, "status": "published"})

        if action == "archive":
            sid = str(params.get("strategy_id") or params.get("id") or "").strip()
            if not sid:
                return fail("strategy_id is required")
            await db.update_strategy_status(sid, "archived")
            return ok({"strategy_id": sid, "status": "archived"})

        if action == "list":
            status = str(params.get("status", "published"))
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

            return ok({"strategy": strategy, "metrics": metrics, "reviews": reviews,
                       "nav_series": await _compute_nav_series(db, sid)})

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
            status = str(params.get("status", "published"))
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

            await db.update_strategy_status(sid, "submitted")

            # 自动化质检
            gate_result = await _run_quality_gate(db, strategy)
            if gate_result["passed"]:
                await db.update_strategy_status(sid, "incubating")
                return ok({
                    "strategy_id": sid, "status": "incubating",
                    "quality_gate": "passed", "details": gate_result,
                })
            else:
                await db.update_strategy_status(sid, "rejected")
                return ok({
                    "strategy_id": sid, "status": "rejected",
                    "quality_gate": "failed", "details": gate_result,
                })

        if action == "lifecycle_scan":
            results = await _lifecycle_scan(db)
            return ok(results)

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
            return {"passed": False, "reason": f"Strategy type not in registry: {strategy_type}"}

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
            return {"passed": False, "reason": "Insufficient kline data for quality gate"}

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
        return {
            "passed": passed,
            "wf_ic_ir": round(wf_sharpe, 4),
            "pkf_ic": round(pkf_ic, 4),
            "bootstrap_ci_lower": round(ci_lower, 4),
            "param_sensitivity": round(sensitivity, 4),
            "reasons": reasons,
        }
    except Exception as e:
        return {"passed": False, "reason": str(e)}


async def _lifecycle_scan(db) -> dict:
    """批量扫描策略状态转换"""
    transitions = []

    # Incubating → listed (30天 Sharpe > 0.5 且 MDD < 20%)
    incubating = await db.list_strategies("incubating", limit=100)
    for s in incubating:
        metrics = await db.get_strategy_metrics(s["id"])
        all_m = next((m for m in metrics if m.get("period") == "all"), {})
        sharpe = float(all_m.get("sharpe_ratio") or 0)
        mdd = abs(float(all_m.get("max_drawdown") or 0))
        if sharpe > 0.5 and mdd < 0.20:
            await db.update_strategy_status(s["id"], "listed")
            transitions.append({"id": s["id"], "from": "incubating", "to": "listed"})
        elif sharpe < 0 or mdd > 0.30:
            await db.update_strategy_status(s["id"], "deprecated")
            transitions.append({"id": s["id"], "from": "incubating", "to": "deprecated"})

    # Listed → deprecated (30天 Sharpe < 0 或 MDD > 30%)
    listed = await db.list_strategies("listed", limit=200)
    for s in listed:
        metrics = await db.get_strategy_metrics(s["id"])
        all_m = next((m for m in metrics if m.get("period") == "all"), {})
        sharpe = float(all_m.get("sharpe_ratio") or 0)
        mdd = abs(float(all_m.get("max_drawdown") or 0))
        if sharpe < 0 or mdd > 0.30:
            await db.update_strategy_status(s["id"], "deprecated")
            transitions.append({"id": s["id"], "from": "listed", "to": "deprecated"})

    return {"scanned": len(incubating) + len(listed), "transitions": transitions}
