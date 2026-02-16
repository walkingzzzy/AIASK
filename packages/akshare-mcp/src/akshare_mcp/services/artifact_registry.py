"""策略工件注册中心（P0）：DB 持久化 + 内存缓存。"""

from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── 内存缓存（DB 不可用时降级） ──────────────────────────
_ARTIFACTS: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db():
    """延迟导入，避免循环依赖。"""
    try:
        from ..storage.timescaledb import get_db
        return get_db()
    except Exception:
        return None


# ── 公开 API ────────────────────────────────────────────

def register_artifact(artifact: dict) -> dict:
    """注册策略工件：优先写 DB，同时更新内存缓存。"""
    aid = str((artifact or {}).get("artifact_id") or "").strip()
    if not aid:
        raise ValueError("artifact_id is required")

    payload = deepcopy(artifact)
    payload.setdefault("registered_at", _now_iso())
    payload["updated_at"] = _now_iso()

    # 内存缓存始终更新
    _ARTIFACTS[aid] = deepcopy(payload)

    # 尝试异步写 DB
    db = _get_db()
    if db is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_safe_save(db, payload))
        except RuntimeError:
            # 没有运行中的事件循环，跳过 DB 写入
            logger.debug("No running event loop; artifact %s cached in memory only", aid)

    return deepcopy(payload)


async def _safe_save(db, payload: dict) -> None:
    """安全写入 DB，失败不影响主流程。"""
    try:
        await db.save_artifact(payload)
    except Exception as exc:
        logger.warning("Failed to persist artifact %s to DB: %s",
                       payload.get("artifact_id"), exc)


def get_artifact(artifact_id: str) -> dict | None:
    """查询工件：先查内存缓存，缓存未命中则查 DB。"""
    aid = str(artifact_id or "").strip()
    if not aid:
        return None

    # 内存缓存命中
    item = _ARTIFACTS.get(aid)
    if item is not None:
        return deepcopy(item)

    # 尝试从 DB 加载
    db = _get_db()
    if db is not None:
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.ensure_future(_safe_get(db, aid))
            # 如果在异步上下文中，返回 None 让调用方自行 await
            # 但为了保持同步接口兼容，这里不阻塞
        except RuntimeError:
            pass

    return None


async def _safe_get(db, artifact_id: str) -> dict | None:
    """从 DB 加载并回填缓存。"""
    try:
        row = await db.get_artifact_by_id(artifact_id)
        if row is not None:
            _ARTIFACTS[artifact_id] = deepcopy(row)
        return row
    except Exception as exc:
        logger.warning("Failed to load artifact %s from DB: %s", artifact_id, exc)
        return None


async def get_artifact_async(artifact_id: str) -> dict | None:
    """异步版本：先查缓存，再查 DB。"""
    aid = str(artifact_id or "").strip()
    if not aid:
        return None

    item = _ARTIFACTS.get(aid)
    if item is not None:
        return deepcopy(item)

    db = _get_db()
    if db is not None:
        row = await _safe_get(db, aid)
        if row is not None:
            return deepcopy(row)

    return None


def list_artifacts(limit: int = 20) -> list[dict]:
    """按更新时间倒序返回工件摘要（内存缓存）。"""
    rows = list(_ARTIFACTS.values())
    rows.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    out = []
    for row in rows[: max(1, int(limit))]:
        out.append(
            {
                "artifact_id": row.get("artifact_id"),
                "strategy_version": row.get("strategy_version"),
                "code": row.get("code"),
                "strategy": row.get("strategy"),
                "updated_at": row.get("updated_at"),
            }
        )
    return out


async def list_artifacts_async(limit: int = 20) -> list[dict]:
    """异步版本：优先从 DB 获取。"""
    db = _get_db()
    if db is not None:
        try:
            return await db.list_artifacts_db(limit)
        except Exception as exc:
            logger.warning("Failed to list artifacts from DB: %s", exc)

    return list_artifacts(limit)
