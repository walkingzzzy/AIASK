"""TimescaleDB 适配器 — 策略工件持久化 Mixin"""

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ArtifactMixin:
    """策略工件 CRUD（strategy_artifacts 表）"""

    async def save_artifact(self, artifact: dict) -> dict:
        """写入或更新策略工件。"""
        aid = str((artifact or {}).get("artifact_id") or "").strip()
        if not aid:
            raise ValueError("artifact_id is required")

        now = datetime.now(timezone.utc).isoformat()
        payload = deepcopy(artifact)
        payload.setdefault("registered_at", now)
        payload["updated_at"] = now

        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO strategy_artifacts (artifact_id, strategy, strategy_version, code, payload, registered_at, updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::timestamptz, $7::timestamptz)
                ON CONFLICT (artifact_id) DO UPDATE SET
                    strategy = EXCLUDED.strategy,
                    strategy_version = EXCLUDED.strategy_version,
                    code = EXCLUDED.code,
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """,
                aid,
                str(payload.get("strategy") or ""),
                str(payload.get("strategy_version") or ""),
                str(payload.get("code") or ""),
                json.dumps(payload, ensure_ascii=False, default=str),
                now,
                now,
            )
        return payload

    async def get_artifact_by_id(self, artifact_id: str) -> Optional[dict]:
        aid = str(artifact_id or "").strip()
        if not aid:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT payload FROM strategy_artifacts WHERE artifact_id = $1", aid
            )
        if row is None:
            return None
        return json.loads(row["payload"])

    async def list_artifacts_db(self, limit: int = 20) -> list[dict]:
        """按更新时间倒序返回工件摘要。"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT artifact_id, strategy, strategy_version, code, updated_at
                FROM strategy_artifacts
                ORDER BY updated_at DESC
                LIMIT $1
                """,
                max(1, int(limit)),
            )
        return [dict(r) for r in rows]
