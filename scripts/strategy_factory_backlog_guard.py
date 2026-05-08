#!/usr/bin/env python3
"""Audit or supersede stale strategy factory queued task backlog.

Dry-run by default. With --cancel-stale-queued it marks matching queued rows as
cancelled and keeps payload/result for audit; it never deletes task history.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "akshare-mcp" / "src"))

TASK_SCOPE = "strategy_factory.worker"
DEFAULT_TASK_NAMES = ("factory_dispatch_run", "incubation_pipeline_run", "runtime_cycle_run")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit/cancel stale queued strategy factory tasks")
    parser.add_argument("--source", default="24h_scheduler")
    parser.add_argument("--older-than-minutes", type=int, default=30)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--task-name", action="append", dest="task_names")
    parser.add_argument("--cancel-stale-queued", action="store_true")
    parser.add_argument("--reason", default="superseded_by_backpressure_fix")
    return parser


async def _matching_rows(db, *, source: str, older_than_minutes: int, limit: int, task_names: list[str]) -> list[dict[str, Any]]:
    names = [str(item).strip() for item in task_names if str(item).strip()]
    async with db.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM strategy_task_runs
            WHERE task_scope = $1
              AND status = 'queued'
              AND (COALESCE(array_length($2::text[], 1), 0) = 0 OR task_name = ANY($2::text[]))
              AND (
                payload->>'source' = $3
                OR payload->'params'->>'source' = $3
                OR result->>'source' = $3
              )
              AND started_at < NOW() - ($4::int * INTERVAL '1 minute')
            ORDER BY started_at ASC, id ASC
            LIMIT $5
            """,
            TASK_SCOPE,
            names,
            source,
            max(0, int(older_than_minutes)),
            max(1, min(int(limit or 500), 5000)),
        )
    return [db._decode_task_run(dict(row)) for row in rows]


async def _cancel_rows(db, rows: list[dict[str, Any]], *, reason: str) -> list[int]:
    cancelled: list[int] = []
    for row in rows:
        run_id = int(row.get("id"))
        result = dict(row.get("result") or {})
        result["cancelled_by"] = "strategy_factory_backlog_guard"
        result["cancelled_reason"] = reason
        result["cancelled_at"] = _utc_now()
        result["previous_status"] = row.get("status")
        updated = await db.update_strategy_task_run(
            run_id,
            status="cancelled",
            result=result,
            error=reason,
            completed_at=_utc_now(),
            clear_lease=True,
        )
        if updated:
            cancelled.append(run_id)
    return cancelled


async def main() -> None:
    from akshare_mcp.storage import get_db

    args = _parser().parse_args()
    task_names = args.task_names or list(DEFAULT_TASK_NAMES)
    db = get_db()
    await db.initialize()
    rows = await _matching_rows(
        db,
        source=str(args.source or "24h_scheduler"),
        older_than_minutes=int(args.older_than_minutes),
        limit=int(args.limit),
        task_names=task_names,
    )
    summary: dict[str, Any] = {
        "generated_at": _utc_now(),
        "dry_run": not bool(args.cancel_stale_queued),
        "source": args.source,
        "older_than_minutes": int(args.older_than_minutes),
        "matched_count": len(rows),
        "matched_by_task": {},
        "sample_ids": [int(row.get("id")) for row in rows[:20]],
        "cancelled_count": 0,
        "cancelled_ids": [],
    }
    for row in rows:
        task_name = str(row.get("task_name") or "unknown")
        summary["matched_by_task"][task_name] = int(summary["matched_by_task"].get(task_name) or 0) + 1
    if args.cancel_stale_queued and rows:
        cancelled = await _cancel_rows(db, rows, reason=str(args.reason or "superseded_by_backpressure_fix"))
        summary["cancelled_count"] = len(cancelled)
        summary["cancelled_ids"] = cancelled[:50]
    print(json.dumps(summary, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    from akshare_mcp.storage import run_with_db_cleanup

    run_with_db_cleanup(main())
