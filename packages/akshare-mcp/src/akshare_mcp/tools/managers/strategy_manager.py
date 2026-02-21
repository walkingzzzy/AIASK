"""Strategy marketplace manager: CRUD, ranking, reviews, subscriptions."""

import json
import logging
import time
from typing import Any, Optional
from uuid import uuid4

from ...storage import get_db
from ...utils import fail, ok

logger = logging.getLogger(__name__)


def _rrf_rank(strategies: list, rank_keys: list = None, k: int = 60) -> list:
    """Reciprocal Rank Fusion across multiple metric dimensions."""
    if not rank_keys:
        rank_keys = ["sharpe_ratio", "total_return", "win_rate", "calmar_ratio", "max_drawdown"]
    scores = {s["id"]: 0.0 for s in strategies}
    for key in rank_keys:
        reverse = key != "max_drawdown"
        sorted_ids = [
            s["id"]
            for s in sorted(strategies, key=lambda x: float(x.get(key) or 0), reverse=reverse)
        ]
        for rank, sid in enumerate(sorted_ids):
            scores[sid] += 1.0 / (k + rank + 1)
    for s in strategies:
        s["rrf_score"] = round(scores[s["id"]], 6)
    return sorted(strategies, key=lambda x: x["rrf_score"], reverse=True)


def register_strategy_manager(mcp):
    @mcp.tool()
    async def strategy_manager(action: str, kwargs: str = "{}") -> dict:
        """策略超市管理器 — 创建/发布/排名/评价/订阅策略产品。

        Actions: create, publish, archive, list, detail, update_metrics, review, subscribe, unsubscribe, my_subscriptions, rank, help
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
                    "my_subscriptions", "rank", "help",
                ],
                "description": "策略超市管理器",
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
            return ok({"strategy": strategy, "metrics": metrics, "reviews": reviews})

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
            rank_keys = params.get("rank_keys")

            strategies = await db.list_strategies(status, strategy_type, limit, 0)
            if not strategies:
                return ok({"strategies": [], "count": 0})

            # Attach metrics to each strategy for ranking
            enriched = []
            for s in strategies:
                metrics_list = await db.get_strategy_metrics(s["id"])
                all_period = next((m for m in metrics_list if m.get("period") == "all"), {})
                enriched.append({
                    **s,
                    "sharpe_ratio": all_period.get("sharpe_ratio"),
                    "total_return": all_period.get("total_return"),
                    "max_drawdown": all_period.get("max_drawdown"),
                    "win_rate": all_period.get("win_rate"),
                    "calmar_ratio": all_period.get("calmar_ratio"),
                })

            ranked = _rrf_rank(enriched, rank_keys)
            return ok({"strategies": ranked, "count": len(ranked)})

        return fail(f"Unknown action: {action}. Use action='help' for available actions.")
