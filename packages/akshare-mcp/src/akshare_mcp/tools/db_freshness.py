"""数据库 K 线新鲜度检测与自动同步。

核心能力:
  1. ensure_fresh_klines — 确保返回的 K 线数据足够新鲜,过期时自动从 API 获取并回写数据库
  2. check_freshness     — 批量检查数据库中多只股票的 K 线新鲜度
  3. sync_stale           — 批量同步过期 K 线数据
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from ..storage import get_db
from ..utils import fail, ok

logger = logging.getLogger(__name__)

_DEFAULT_STALE_DAYS = 5
_SYNC_CONCURRENCY = 3


def _calc_staleness(klines: list[dict]) -> int:
    """计算 K 线最后一根距今天数。"""
    if not klines:
        return 9999
    last_date = klines[-1].get("date", "")
    if not last_date:
        return 9999
    try:
        last_dt = datetime.strptime(str(last_date)[:10], "%Y-%m-%d")
        return (datetime.now() - last_dt).days
    except (ValueError, TypeError):
        return 9999


async def ensure_fresh_klines(
    code: str,
    *,
    limit: int = 250,
    max_stale_days: int = _DEFAULT_STALE_DAYS,
) -> tuple[list[dict], dict]:
    """确保返回新鲜的 K 线数据，过期时自动从 API 获取并回写数据库。

    Returns:
        (klines, freshness_info) 二元组。
        freshness_info 包含 staleness_days, source, synced 等元信息。
    """
    db = get_db()
    klines = await db.get_klines(code, limit=limit)

    info: dict[str, Any] = {
        "code": code,
        "source": "timescaledb",
        "synced": False,
        "staleness_days": 0,
        "kline_count": 0,
    }

    if klines:
        klines.sort(key=lambda k: k.get("date", ""))
        stale_days = _calc_staleness(klines)
        info["staleness_days"] = stale_days
        info["kline_count"] = len(klines)
        info["last_date"] = klines[-1].get("date", "")

        if stale_days <= max_stale_days:
            info["freshness"] = "fresh"
            return klines, info

        logger.info(
            "K 线过期 (%d 天 > %d)，code=%s，从 API 重新获取并同步",
            stale_days, max_stale_days, code,
        )

    # 从 API 获取最新数据 — 绕过 get_kline 的缓存和 DB 优先逻辑
    from .market.kline import _get_kline_impl
    from datetime import timezone

    started_at = datetime.now(timezone.utc)
    api_result = await _get_kline_impl(code, "daily", limit, started_at)
    if not api_result.get("success") or not api_result.get("data"):
        if klines:
            info["freshness"] = "stale_api_unavailable"
            info["warning"] = f"API 获取失败，使用过期数据（{info.get('staleness_days', '?')}天）"
            return klines, info
        info["freshness"] = "no_data"
        return [], info

    fresh_klines = api_result["data"]
    fresh_klines.sort(key=lambda k: k.get("date", ""))

    # get_kline 内部已通过 _async_save_klines_to_db 回写数据库
    # 但这里做一次显式同步确保落库成功
    sync_ok = await _sync_to_db(code, fresh_klines)

    info["source"] = api_result.get("source", "api")
    info["synced"] = sync_ok
    info["kline_count"] = len(fresh_klines)
    info["staleness_days"] = _calc_staleness(fresh_klines)
    info["last_date"] = fresh_klines[-1].get("date", "") if fresh_klines else ""
    info["freshness"] = "fresh" if info["staleness_days"] <= max_stale_days else "stale"

    return fresh_klines, info


async def _sync_to_db(code: str, klines: list[dict]) -> bool:
    """将 K 线数据同步写入数据库。"""
    try:
        db = get_db()
        result = await db.save_klines(code, klines)
        accepted = result.get("accepted_count", 0) if isinstance(result, dict) else 0
        logger.info(
            "K 线同步完成: code=%s, accepted=%d/%d",
            code, accepted, len(klines),
        )
        return accepted > 0
    except Exception as e:
        logger.warning("K 线同步失败: code=%s, error=%s", code, e)
        return False


async def check_freshness(
    codes: list[str],
    *,
    max_stale_days: int = _DEFAULT_STALE_DAYS,
) -> dict[str, Any]:
    """批量检查多只股票的 K 线新鲜度。

    Returns:
        包含 fresh/stale/missing 分类的报告。
    """
    db = get_db()
    fresh_list: list[dict] = []
    stale_list: list[dict] = []
    missing_list: list[str] = []

    for code in codes:
        try:
            klines = await db.get_klines(code, limit=1)
            if not klines:
                missing_list.append(code)
                continue

            stale_days = _calc_staleness(klines)
            entry = {
                "code": code,
                "last_date": klines[-1].get("date", ""),
                "staleness_days": stale_days,
            }

            if stale_days <= max_stale_days:
                fresh_list.append(entry)
            else:
                stale_list.append(entry)
        except Exception as e:
            logger.warning("检查 %s 新鲜度失败: %s", code, e)
            missing_list.append(code)

    return {
        "checked_at": datetime.now().isoformat(),
        "max_stale_days": max_stale_days,
        "total": len(codes),
        "fresh_count": len(fresh_list),
        "stale_count": len(stale_list),
        "missing_count": len(missing_list),
        "fresh": fresh_list,
        "stale": sorted(stale_list, key=lambda x: x["staleness_days"], reverse=True),
        "missing": missing_list,
    }


async def sync_stale(
    codes: list[str] | None = None,
    *,
    max_stale_days: int = _DEFAULT_STALE_DAYS,
    limit_per_stock: int = 250,
) -> dict[str, Any]:
    """批量同步过期 K 线数据到数据库。

    如果 codes 为 None，自动扫描数据库中所有股票进行检查。
    """
    db = get_db()

    if codes is None:
        codes = await _get_all_tracked_codes(db)

    report = await check_freshness(codes, max_stale_days=max_stale_days)
    stale_codes = [s["code"] for s in report.get("stale", [])]
    missing_codes = report.get("missing", [])
    to_sync = stale_codes + missing_codes

    if not to_sync:
        return {
            "checked": len(codes),
            "need_sync": 0,
            "synced": 0,
            "failed": 0,
            "detail": [],
            "message": "所有股票数据均为最新，无需同步",
        }

    sem = asyncio.Semaphore(_SYNC_CONCURRENCY)
    results: list[dict] = []

    async def _sync_one(c: str) -> dict:
        async with sem:
            try:
                _, info = await ensure_fresh_klines(
                    c, limit=limit_per_stock, max_stale_days=max_stale_days,
                )
                return {
                    "code": c,
                    "status": "synced" if info.get("synced") else "api_fetched",
                    "staleness_before": next(
                        (s["staleness_days"] for s in report.get("stale", []) if s["code"] == c),
                        None,
                    ),
                    "staleness_after": info.get("staleness_days"),
                    "kline_count": info.get("kline_count", 0),
                }
            except Exception as e:
                return {"code": c, "status": "failed", "error": str(e)}

    tasks = [_sync_one(c) for c in to_sync]
    results = await asyncio.gather(*tasks)

    synced = sum(1 for r in results if r["status"] in ("synced", "api_fetched"))
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "checked": len(codes),
        "need_sync": len(to_sync),
        "synced": synced,
        "failed": failed,
        "detail": results,
        "message": f"同步完成: {synced}/{len(to_sync)} 成功, {failed} 失败",
    }


async def _get_all_tracked_codes(db) -> list[str]:
    """获取数据库中已有的所有股票代码。"""
    try:
        async with db.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT code FROM kline_1d ORDER BY code",
            )
            return [row["code"] for row in rows]
    except Exception as e:
        logger.warning("获取已跟踪代码列表失败: %s", e)
        return []


# ── MCP 注册 ──────────────────────────────────────────────────────


def register(mcp):
    """注册数据库新鲜度检测工具。"""

    @mcp.tool()
    async def check_db_freshness(
        codes: list[str] | None = None,
        max_stale_days: int = 5,
    ):
        """检查数据库中 K 线数据的新鲜度

        扫描数据库中的股票 K 线数据，报告哪些过期、哪些缺失。

        Args:
            codes: 要检查的股票代码列表。为空时检查数据库中所有股票。
            max_stale_days: 最大允许过期天数（默认5天，即超过5天视为过期）
        """
        if not codes:
            db = get_db()
            codes = await _get_all_tracked_codes(db)
            if not codes:
                return ok({
                    "message": "数据库中暂无 K 线数据",
                    "total": 0,
                })

        result = await check_freshness(codes, max_stale_days=max_stale_days)
        return ok(result)

    @mcp.tool()
    async def sync_stale_klines(
        codes: list[str] | None = None,
        max_stale_days: int = 5,
    ):
        """同步过期的 K 线数据到数据库

        检查指定股票的 K 线新鲜度，对过期数据自动从 API 获取最新数据并写入数据库。

        Args:
            codes: 要同步的股票代码列表。为空时自动扫描数据库中所有过期股票。
            max_stale_days: 最大允许过期天数（默认5天）
        """
        result = await sync_stale(
            codes, max_stale_days=max_stale_days,
        )
        return ok(result)
